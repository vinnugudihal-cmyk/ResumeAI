"""
WSGI entry point for running ResumeAI under a production server.

`python app.py` starts Flask's own development server. That is the
right thing for local work and the wrong thing for anything other
people can reach: it is not built to take real traffic, and when
`debug=True` it exposes the Werkzeug debugger. Werkzeug prints

    WARNING: This is a development server. Do not use it in a
    production deployment. Use a production WSGI server instead.

precisely because `app.run()` is not a production server.

This module hands the *same* `app` object to a real WSGI server. No
route, migration, model or configuration value is changed or
duplicated - the application is imported, not reimplemented. Because
`app.py` runs its database bootstrap at import time, migrations (and
their automatic pre-migration backup) still happen no matter which
server starts the process.

Windows - Waitress (the supported choice here):

    python -m pip install -r requirements-prod.txt
    python wsgi.py                          # 127.0.0.1:8000
    python wsgi.py --host 0.0.0.0 --port 8000

Linux / macOS - Gunicorn:

    python -m pip install gunicorn
    gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app

`waitress-serve wsgi:app` works too, if you prefer the console script.

Every existing environment variable is honoured, because the
application is imported by name: RESUMEAI_DB, RESUMEAI_UPLOADS,
RESUMEAI_SECRET_KEY, RESUMEAI_HTTPS, RESUMEAI_SESSION_HOURS,
RESUMEAI_IDLE_MINUTES, RESUMEAI_OCR_DPI, RESUMEAI_MAX_OCR_PAGES,
GEMINI_API_KEY, ADZUNA_APP_ID, ADZUNA_APP_KEY.

This file makes the warning *correct to act on*, not disappear: it
does not silence anything and it does not by itself make the app
production-ready. See RUNNING.md for the remaining caveats (HTTPS,
CORS) before exposing it beyond your own machine.
"""

import argparse
import os

# Importing is the whole job for gunicorn and `waitress-serve`.
# The bootstrap in app.py runs here, once, before serving begins.
from app import app

__all__ = ["app"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_THREADS = 4


def _env_int(name, fallback):
    """Read a whole number from the environment, tolerating junk."""

    raw = os.environ.get(name)

    if raw is None or not str(raw).strip():
        return fallback

    try:
        return int(str(raw).strip())

    except ValueError:
        return fallback


def build_parser():
    parser = argparse.ArgumentParser(
        description="Serve ResumeAI with Waitress (production WSGI).",
    )

    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", DEFAULT_HOST),
        help="Interface to bind (default: $HOST or 127.0.0.1).",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=_env_int("PORT", DEFAULT_PORT),
        help="Port to bind (default: $PORT or 8000).",
    )

    parser.add_argument(
        "--threads",
        type=int,
        default=_env_int("WAITRESS_THREADS", DEFAULT_THREADS),
        help="Request worker threads (default: 4).",
    )

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        from waitress import serve

    except ImportError:
        raise SystemExit(
            "Waitress is not installed. Install the production "
            "requirements first:\n"
            "    python -m pip install -r requirements-prod.txt"
        )

    print(
        "ResumeAI (Waitress) listening on http://%s:%d"
        % (args.host, args.port)
    )
    print(
        "Database:",
        os.environ.get("RESUMEAI_DB")
        or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "resumeai.db"),
    )

    serve(
        app,
        host=args.host,
        port=args.port,
        threads=args.threads,
        ident="ResumeAI",
    )


if __name__ == "__main__":
    main()
