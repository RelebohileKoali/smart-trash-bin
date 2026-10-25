import hmac
import math
import os
import sqlite3

import psycopg
import resend
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from psycopg.rows import dict_row

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(32)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL.removeprefix("postgres://")

DATABASE = os.getenv("DATABASE_PATH", "smart_bin.db")
USE_POSTGRES = bool(DATABASE_URL)
FULL_THRESHOLD = 90
DEFAULT_BIN_ID = "bin-1"


def get_connection():
    if USE_POSTGRES:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def db_execute(connection, query, parameters=()):
    if USE_POSTGRES:
        query = query.replace("?", "%s")
    return connection.execute(query, parameters)


def create_database():
    if USE_POSTGRES:
        with get_connection() as connection:
            db_execute(connection, """
                CREATE TABLE IF NOT EXISTS subscribers (
                    id BIGSERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL
                )
            """)
            db_execute(connection, """
                CREATE TABLE IF NOT EXISTS bins (
                    bin_id TEXT PRIMARY KEY,
                    fullness INTEGER NOT NULL DEFAULT 0,
                    notification_sent INTEGER NOT NULL DEFAULT 0
                )
            """)
        return

    os.makedirs(os.path.dirname(os.path.abspath(DATABASE)), exist_ok=True)
    with get_connection() as connection:
        db_execute(connection, """
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL
            )
        """)

        db_execute(connection, """
            CREATE TABLE IF NOT EXISTS bins (
                bin_id TEXT PRIMARY KEY,
                fullness INTEGER NOT NULL DEFAULT 0,
                notification_sent INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Carry forward the original single-bin status if this database has it.
        legacy_table = db_execute(connection,
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'bin_status'"
        ).fetchone()
        if legacy_table:
            legacy_status = db_execute(connection,
                "SELECT fullness, notification_sent FROM bin_status WHERE id = 1"
            ).fetchone()
            if legacy_status:
                db_execute(connection,
                    """
                    INSERT OR IGNORE INTO bins (bin_id, fullness, notification_sent)
                    VALUES (?, ?, ?)
                    """,
                    (DEFAULT_BIN_ID, legacy_status["fullness"], legacy_status["notification_sent"]),
                )


def get_notification_recipients():
    with get_connection() as connection:
        subscribers = db_execute(connection,
            "SELECT email FROM subscribers ORDER BY lower(email)"
        ).fetchall()

    if subscribers:
        return [subscriber["email"] for subscriber in subscribers]

    # EMAIL_ADDRESS is a backup recipient when nobody is configured in the UI.
    fallback_email = os.getenv("EMAIL_ADDRESS", "").strip()
    return [fallback_email] if fallback_email else []


def send_resend_message(receiver_email, subject, text):
    resend.api_key = os.environ["RESEND_API_KEY"]
    resend.Emails.send({
        "from": os.environ["EMAIL_FROM"],
        "to": [receiver_email],
        "subject": subject,
        "text": text,
    })


def send_email(receiver_email, bin_id, fullness):
    send_resend_message(
        receiver_email,
        f"Smart bin alert: {bin_id} is full",
        f"Bin {bin_id} is {fullness}% full. Please empty it.",
    )


def send_test_email(receiver_email):
    send_resend_message(
        receiver_email,
        "Smart Bin Monitor test email",
        "This is a test email from Smart Bin Monitor. If you received it, email delivery is working.",
    )


def email_notification_recipients(bin_id, fullness):
    recipients = get_notification_recipients()
    if not recipients:
        return [], False

    failures = []
    for recipient in recipients:
        try:
            send_email(recipient, bin_id, fullness)
        except Exception as error:
            app.logger.exception("Email failed for %s", recipient, exc_info=error)
            failures.append(recipient)

    return failures, True


@app.route("/")
def index():
    with get_connection() as connection:
        bins = db_execute(connection,
            "SELECT bin_id, fullness FROM bins ORDER BY lower(bin_id)"
        ).fetchall()
        subscribers = db_execute(connection,
            "SELECT email FROM subscribers ORDER BY lower(email)"
        ).fetchall()

    return render_template(
        "index.html",
        bins=bins,
        subscribers=subscribers,
        fallback_configured=bool(os.getenv("EMAIL_ADDRESS", "").strip()),
        threshold=FULL_THRESHOLD,
    )


@app.get("/healthz")
def health_check():
    try:
        with get_connection() as connection:
            db_execute(connection, "SELECT 1")
    except (sqlite3.Error, psycopg.Error):
        app.logger.exception("Health check failed")
        return jsonify({"status": "unhealthy"}), 503

    return jsonify({"status": "ok"})


@app.post("/subscribe")
def subscribe():
    email = request.form.get("email", "").strip().lower()

    if not email or "@" not in email or any(character.isspace() for character in email):
        flash("Enter a valid email address.", "error")
        return redirect(url_for("index"))

    try:
        with get_connection() as connection:
            db_execute(connection,
                "INSERT INTO subscribers (email) VALUES (?)",
                (email,),
            )
    except (sqlite3.IntegrityError, psycopg.IntegrityError):
        flash("That email is already on the notification list.", "error")
    else:
        flash("Email added. It will receive alerts for every bin.", "success")

    return redirect(url_for("index"))


@app.post("/unsubscribe")
def unsubscribe():
    email = request.form.get("email", "").strip().lower()
    with get_connection() as connection:
        result = db_execute(connection,
            "DELETE FROM subscribers WHERE email = ?",
            (email,),
        )

    if result.rowcount:
        flash("Email removed from the notification list.", "success")
    else:
        flash("That email was not on the notification list.", "error")

    return redirect(url_for("index"))


@app.route("/test-email", methods=["GET", "POST"])
def test_email():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email or "@" not in email or any(character.isspace() for character in email):
            flash("Enter a valid email address.", "error")
        elif not os.getenv("RESEND_API_KEY") or not os.getenv("EMAIL_FROM"):
            flash("Set RESEND_API_KEY and EMAIL_FROM in .env before sending a test.", "error")
        else:
            try:
                send_test_email(email)
            except Exception:
                app.logger.exception("Test email failed for %s", email)
                flash("Resend could not send the test email. Check your API key and sender address.", "error")
            else:
                flash(f"Test email sent to {email}.", "success")

        return redirect(url_for("test_email"))

    return render_template(
        "test_email.html",
        email_configured=bool(os.getenv("RESEND_API_KEY") and os.getenv("EMAIL_FROM")),
    )


@app.post("/api/bin-status")
def update_bin_status():
    data = request.get_json(silent=True) or {}
    fullness = data.get("fullness")
    bin_id = data.get("bin_id", DEFAULT_BIN_ID)
    api_key = request.headers.get("X-API-Key")

    expected_api_key = os.environ.get("BIN_API_KEY")
    if not expected_api_key or not hmac.compare_digest(api_key or "", expected_api_key):
        return jsonify({"error": "Unauthorized"}), 401

    if not isinstance(bin_id, str) or not bin_id.strip() or len(bin_id.strip()) > 64:
        return jsonify({"error": "bin_id must be a non-empty string of at most 64 characters."}), 400
    bin_id = bin_id.strip()

    if isinstance(fullness, bool) or not isinstance(fullness, (int, float)):
        return jsonify({"error": "Fullness must be a number."}), 400

    if fullness < 0 or fullness > 100 or not math.isfinite(fullness):
        return jsonify({"error": "Fullness must be between 0 and 100."}), 400
    fullness = round(fullness)

    with get_connection() as connection:
        current = db_execute(connection,
            "SELECT notification_sent FROM bins WHERE bin_id = ?",
            (bin_id,),
        ).fetchone()

        notification_sent = current["notification_sent"] if current else 0
        should_notify = fullness >= FULL_THRESHOLD and not notification_sent

        if fullness < FULL_THRESHOLD:
            notification_sent = 0

        db_execute(connection,
            """
            INSERT INTO bins (bin_id, fullness, notification_sent)
            VALUES (?, ?, ?)
            ON CONFLICT(bin_id) DO UPDATE SET
                fullness = excluded.fullness,
                notification_sent = excluded.notification_sent
            """,
            (bin_id, fullness, notification_sent),
        )

    failures = []
    recipients_configured = True
    if should_notify:
        failures, recipients_configured = email_notification_recipients(bin_id, fullness)

        if recipients_configured and not failures:
            with get_connection() as connection:
                db_execute(connection,
                    "UPDATE bins SET notification_sent = 1 WHERE bin_id = ?",
                    (bin_id,),
                )

    response = {
        "message": "Bin status updated.",
        "bin_id": bin_id,
        "fullness": fullness,
        "notification_attempted": should_notify and recipients_configured,
        "email_failures": failures,
    }
    if should_notify and not recipients_configured:
        response["email_error"] = "No notification recipients are configured."

    return jsonify(response)


create_database()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
