# smart-trash-bin

## Backend setup (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `RESEND_API_KEY`, `EMAIL_FROM`, and `BIN_API_KEY` in `.env`. `EMAIL_FROM` must be a sender address configured in Resend. `EMAIL_ADDRESS` is an optional backup recipient, used only when the dashboard has no saved recipients. Keep the API key and bin key private.

Open the dashboard at `http://localhost:5000` to add or remove notification email addresses. Saved addresses receive alerts for every bin; the `.env` backup is used only when the list is empty.

Choose **Send a test email** in the notification panel to send a test message to an address without changing the saved recipient list or bin status.

Each bin reports to `POST /api/bin-status` with the `X-API-Key` header and a JSON body containing `fullness` from 0 to 100. Include a unique `bin_id` to track multiple bins; if omitted, it defaults to `bin-1`.

Run the backend from the project root with:

```powershell
python backend\app.py
```

## Deploy to Render

The root `render.yaml` defines a Render Blueprint for this app. Push the repository to GitHub, then in Render choose **New + → Blueprint** and connect the repository. Render will build with `requirements.txt`, start the app with Gunicorn, and check `/healthz`.

When prompted, provide `RESEND_API_KEY` and `EMAIL_FROM`. Render generates `BIN_API_KEY` and `FLASK_SECRET_KEY`; copy `BIN_API_KEY` from the Render environment settings into the device configuration. `EMAIL_ADDRESS` is optional; set it in the Render environment settings if you want a backup recipient when the dashboard list is empty.

The Blueprint mounts a 1 GB persistent disk at `/var/data` and stores SQLite at `/var/data/smart_bin.db`, so saved bins and recipients survive restarts and deploys. Persistent disks require a paid Render web service; the Blueprint selects the smallest paid compute plan. Render Free services cannot attach persistent disks, so SQLite data would be lost on restarts or deploys if you switch to Free.
