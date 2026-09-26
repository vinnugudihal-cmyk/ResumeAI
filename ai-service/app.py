from flask import Flask, request, jsonify
from flask_cors import CORS
from extractor import extract_text
from analyzer import analyze_resume

import os
import tempfile


app = Flask(__name__)

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

CORS(app)

# Maximum upload size: 5 MB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "ResumeAI AI service is running",
        "status": "online"
    })


# ---------------------------------------------------------
# RESUME ANALYSIS
# ---------------------------------------------------------

@app.route("/analyze", methods=["POST"])
def analyze():

    # Check that a file was actually uploaded
    if "resume" not in request.files:
        return jsonify({
            "error": "No resume uploaded."
        }), 400

    file = request.files["resume"]

    # Check filename
    if not file.filename:
        return jsonify({
            "error": "No file selected."
        }), 400

    # Only allow PDF files
    filename = file.filename.lower()

    if not filename.endswith(".pdf"):
        return jsonify({
            "error": "Only PDF resume files are supported."
        }), 400

    temp_path = None

    try:

        # -------------------------------------------------
        # CREATE TEMPORARY FILE
        # -------------------------------------------------

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        ) as temp_file:

            temp_path = temp_file.name

            file.save(temp_path)

        # -------------------------------------------------
        # EXTRACT TEXT
        # -------------------------------------------------

        text = extract_text(temp_path)

        if not text or not text.strip():

            return jsonify({
                "error": (
                    "Could not extract readable text "
                    "from this PDF."
                )
            }), 422

        # -------------------------------------------------
        # ANALYZE RESUME
        # Optional job_description is used by the ATS criterion
        # (jd_comparison + missing-keyword actions). Scoring still
        # works the same when it is omitted.
        # -------------------------------------------------

        job_description = (
            request.form.get("job_description")
            or request.form.get("jobDescription")
            or ""
        )
        if not isinstance(job_description, str):
            job_description = ""
        job_description = job_description.strip()[:20000]

        result = analyze_resume(text, job_description=job_description)

        # -------------------------------------------------
        # RETURN RESULT
        # -------------------------------------------------

        return jsonify(result), 200

    except Exception as error:

        print(
            "Resume analysis error:",
            str(error)
        )

        return jsonify({
            "error": (
                "An unexpected error occurred "
                "while analyzing the resume."
            )
        }), 500

    finally:

        # -------------------------------------------------
        # DELETE TEMPORARY FILE
        # -------------------------------------------------

        if temp_path and os.path.exists(temp_path):

            try:
                os.remove(temp_path)

            except OSError as cleanup_error:

                print(
                    "Temporary file cleanup failed:",
                    str(cleanup_error)
                )


# ---------------------------------------------------------
# FILE TOO LARGE
# ---------------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({
        "error": "Resume file is too large. Maximum size is 5MB."
    }), 413


# ---------------------------------------------------------
# START SERVER
# ---------------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=8000,
        debug=True
    )