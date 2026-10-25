# smart-trash-bin

## Backend setup (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `RESEND_API_KEY`, `EMAIL_FROM`, and `BIN_API_KEY` in `.env`. `EMAIL_FROM` must be a sender address configured in Resend. `EMAIL_ADDRESS` is an optional backup recipient, used only when the dashboard has no saved recipients. Keep the API key and bin key private.

The app uses SQLite (`smart_bin.db`) by default for local development. To use a hosted PostgreSQL database such as Neon, set `DATABASE_URL` in `.env` to its PostgreSQL connection string. Keep the `sslmode=require` option from Neon, for example:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

The app creates its tables automatically on startup. Existing SQLite records are not copied automatically to PostgreSQL.

Open the dashboard at `http://localhost:5000` to add or remove notification email addresses. Saved addresses receive alerts for every bin; the `.env` backup is used only when the list is empty.

Choose **Send a test email** in the notification panel to send a test message to an address without changing the saved recipient list or bin status.

Each bin reports to `POST /api/bin-status` with the `X-API-Key` header and a JSON body containing `fullness` from 0 to 100. Include a unique `bin_id` to track multiple bins; if omitted, it defaults to `bin-1`.

Run the backend from the project root with:

```powershell
python backend\app.py
```

## Deploy to Render

The root `render.yaml` defines a Render Blueprint for this app. Push the repository to GitHub, then in Render choose **New + → Blueprint** and connect the repository. Render will build with `requirements.txt`, start the app with Gunicorn, and check `/healthz`.

When prompted, provide `DATABASE_URL`, `RESEND_API_KEY`, and `EMAIL_FROM`. Set `DATABASE_URL` to your Neon PostgreSQL connection string (including `sslmode=require`); use Neon’s pooled connection string if you expect multiple app connections. Render generates `BIN_API_KEY` and `FLASK_SECRET_KEY`; copy `BIN_API_KEY` from the Render environment settings into the device configuration. `EMAIL_ADDRESS` is optional and is used as a backup recipient when the dashboard list is empty.

The Blueprint uses the external PostgreSQL database, so dashboard recipients and bin status persist independently of the Render service filesystem. Set `DATABASE_URL` before the first deployment; if it is omitted, the app falls back to SQLite on Render’s ephemeral filesystem and its data can be lost on restarts or deploys.
