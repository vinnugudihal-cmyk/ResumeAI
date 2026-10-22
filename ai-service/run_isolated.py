"""
Start the API on a throwaway database, for browser testing.

The gallery sits behind the sign-in wall, so checking the preview,
the editor and the PDF download in a browser needs a session. Doing
that against the real database would mean writing a test account
into the user's data.

This runs the same application on a temporary SQLite file and a
different port, so the browser can exercise the real code paths
without touching anything that matters.

    python run_isolated.py            # port 8001, temp database
"""

import os
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))

WORK = os.path.join(tempfile.gettempdir(), "resumeai_browser_sandbox")

os.makedirs(WORK, exist_ok=True)

os.environ["RESUMEAI_DB"] = os.path.join(WORK, "sandbox.db")
os.environ["RESUMEAI_UPLOADS"] = os.path.join(WORK, "uploads")
os.environ["RESUMEAI_SECRET_KEY"] = "browser-sandbox-secret"
os.environ["PORT"] = "8001"

import app  # noqa: E402

if __name__ == "__main__":

    print("SANDBOX: " + os.environ["RESUMEAI_DB"])
    print("SANDBOX PORT: 8001")

    app.app.run(host="127.0.0.1", port=8001, debug=False)