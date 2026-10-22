# Running ResumeAI

Everything below is for **Windows PowerShell**. Run each command in
its own window, or split them with a new line.

---

## What you need running

ResumeAI is three small services. Two must be running for the app
to work; the third is optional.

| Service | Port | Needed? |
|---|---|---|
| Flask AI service | 8000 | **Yes** - all data and the API |
| Vite frontend | 5173 | **Yes** - the pages you click |
| Express proxy | 5000 | Optional - only a fallback path |

The Flask service owns the SQLite database. The Express proxy just
forwards cookies to Flask, so you can skip it entirely.

---

## Start it

### 1. Flask AI service (window 1)

```powershell
cd "C:\Users\VANDANA GUDIHAL\OneDrive\Desktop\ResumeAI\ai-service"
python app.py
```

It prints `Running on http://127.0.0.1:8000` when ready. Migrations
run automatically on start, and a backup is taken before any of them
changes the schema. You do not need to run a migration by hand.

### 2. Frontend (window 2)

```powershell
cd "C:\Users\VANDANA GUDIHAL\OneDrive\Desktop\ResumeAI\frontend"
npm run dev
```

It prints `Local: http://localhost:5173/`.

### 3. Open it

Go to **<http://localhost:5173>**.

Signed out, that shows Login. Signed in, it shows your dashboard.

> Use `localhost`, not `127.0.0.1`. The browser treats them as
> different sites, so a `127.0.0.1` page cannot use the session
> cookie set for `localhost` and login silently fails.

---

## Running it as a real server (optional)

`python app.py` starts Flask's **development** server. That is what
you want while working on the app, and it is why you see:

```
WARNING: This is a development server. Do not use it in a
production deployment. Use a production WSGI server instead.
```

The warning is accurate, not a fault. The backend did start, and
`http://127.0.0.1:8000/health` answers `200` with `"status": "ok"`.
Nothing is broken. Leave the development command as it is for local
work.

When you want the same application served by a real WSGI server — on
this machine, or behind your own reverse proxy — use **Waitress** on
Windows:

```powershell
cd "C:\Users\VANDANA GUDIHAL\OneDrive\Desktop\ResumeAI\ai-service"

# one time
python -m pip install -r requirements-prod.txt

# serve on 127.0.0.1:8000 (the address the frontend expects)
python wsgi.py

# or choose the interface and port
python wsgi.py --host 0.0.0.0 --port 8000
```

On Linux or macOS, use Gunicorn instead:

```bash
python -m pip install gunicorn
gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app
```

`wsgi.py` imports the existing `app` object, so every route,
migration, upload path and environment variable behaves exactly as it
does in development. The database bootstrap (including the automatic
pre-migration backup) still runs on import. The debugger is off,
because the development `app.run(debug=True)` is never called.

`HOST` and `PORT` are read as defaults if you prefer environment
variables to flags. If you terminate HTTPS in front of the app, set
`RESUMEAI_HTTPS=1` so the session cookie is marked `Secure` — the same
switch the development setup already uses.

**This does not make the app production-ready by itself.** There is
still no HTTPS between the browser and the server, CORS is still the
development setting, and SQLite is still a single local file. Read the
next section before letting anyone else reach it.

---

## Stop it

Press `Ctrl + C` in both windows. If something is still holding a
port:

```powershell
Get-Process python,node -ErrorAction SilentlyContinue | Stop-Process -Force
```

Do this before copying `resumeai.db`. The project sits inside
OneDrive, which can lock the file mid-write and produce a corrupt
copy.

---

## Run the tests

### Backend (17 suites)

```powershell
cd "C:\Users\VANDANA GUDIHAL\OneDrive\Desktop\ResumeAI\ai-service"
```

Then one at a time, or all of them:

```powershell
$suites = @(
  "test_skill_detection.py","test_database.py","test_auth.py",
  "test_isolation.py","test_roles.py","test_api_contract.py",
  "test_pdf_extraction.py","test_migrations.py",
  "test_account_isolation.py","test_career_profile.py",
  "test_career_mission.py","test_resume_builder.py",
  "test_career_platform.py","test_logout_flow.py",
  "test_feature_integration.py","test_diagnostic.py",
  "test_jd_passthrough.py"
)
foreach ($t in $suites) {
  $out = python $t
  "{0,-28} {1}" -f $t, (($out | Select-String "RESULT:") -join "")
}
```

Every suite points `RESUMEAI_DB` at a throwaway file before it
imports the app, so **the tests never touch your real data**.

### Frontend

```powershell
cd "C:\Users\VANDANA GUDIHAL\OneDrive\Desktop\ResumeAI\frontend"
npm run verify
```

That runs the linter, the route check and a production build.

To check only that no link points at a missing page:

```powershell
npm run verify:routes
```

---

## Using it on your phone over Wi-Fi

Your phone and this computer must be on **the same Wi-Fi network**.

### 1. Find this computer's IP

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } |
  Select-Object InterfaceAlias, IPAddress
```

You want the `Wi-Fi` row. At the time of writing it is
`192.168.29.88`, but that changes when you rejoin a network, so read
it fresh each time.

### 2. Start Vite listening on the network

By default Vite only accepts connections from this computer. Start it
with `--host`:

```powershell
cd "C:\Users\VANDANA GUDIHAL\OneDrive\Desktop\ResumeAI\frontend"
npm run dev -- --host
```

### 3. Allow the port through Windows Firewall

Run this once, from an **administrator** PowerShell:

```powershell
New-NetFirewallRule -DisplayName "ResumeAI Vite 5173" `
  -Direction Inbound -LocalPort 5173 -Protocol TCP `
  -Action Allow -Profile Private
```

Rule it to `-Profile Private` only. Your home Wi-Fi is a private
profile; a coffee-shop or airport network is public, and you do not
want this open there.

### 4. Allow the Flask port too

The browser on your phone talks to Flask directly for the API, so
port 8000 has to be reachable as well:

```powershell
New-NetFirewallRule -DisplayName "ResumeAI Flask 8000" `
  -Direction Inbound -LocalPort 8000 -Protocol TCP `
  -Action Allow -Profile Private
```

### 5. Open it on the phone

```
http://192.168.29.88:5173
```

Replace with whatever your step 1 printed.

### Two things that will bite you

**1. "localhost" will not work on the phone.** It means *the phone
itself*. The frontend on the phone points at `http://localhost:8000`
for the API, which on the phone is the phone. You will see the login
page, and logging in will hang or fail.

To fix it, point the frontend at this computer's LAN address before
you start it:

```powershell
cd "C:\Users\VANDANA GUDIHAL\OneDrive\Desktop\ResumeAI\frontend"
$env:VITE_API_BASE = "http://192.168.29.88:8000"
npm run dev -- --host
```

Then put it back afterwards, because a LAN-only address breaks the
same app on this computer:

```powershell
Remove-Item Env:\VITE_API_BASE
```

**2. Cookies need a secure context.** Browsers only keep a session
cookie for plain `http://` on some devices, and some will refuse it
outright on a non-localhost origin. If login appears to succeed and
then bounces you back to the Login page, this is the cause. A phone
browser cannot be talked out of it from here; the reliable fix is to
put a real HTTPS address in front of it, which means deploying
rather than exposing the dev server.

---

## About exposing this

**Do not put this on the public internet as it stands.** `npm run dev
-- --host` plus a firewall rule is fine for your own Wi-Fi and
nothing more. It is a development server:

- Flask runs with the debugger enabled
- CORS allows the Vite origin, which is not an access control
- There is no HTTPS, so the session cookie travels in the clear

For anything beyond your own network, deploy it behind a real HTTPS
host, run it under the WSGI server above (which leaves the debugger
off), and review the CORS setting first.

---

## Optional: live job listings

With no provider configured, Find Jobs returns **real search links to
real job sites**, labelled as links and not as listings. That is the
default and it works with no setup.

For actual listings in the page, sign up for a free Adzuna key at
<https://developer.adzuna.com/> and add to `ai-service/.env`:

```
ADZUNA_APP_ID=your_app_id
ADZUNA_APP_KEY=your_app_key
```

Restart Flask. The page will then say "Live listings" instead of
"Search links".

ResumeAI never invents a vacancy, a company, a salary or a URL, in
either mode. With no provider and no key it says so rather than
filling the gap.