"""
ResumeAI text extraction.

A resume PDF can be one of two very different things:

1. A real text PDF  - the words are stored as characters.
   These are read directly, quickly and perfectly.
2. A scanned PDF    - the page is just a picture of the words.
   There is no text layer at all, so OCR is required.

This module tries the cheap, exact methods first and only
pays for OCR when there is genuinely no usable text. It also
reports *why* extraction failed so the API can return a
message that actually helps the user.

Order of attempts
-----------------
1. pypdf      - fast, works for most text PDFs
2. PyMuPDF    - better at odd encodings / broken text layers
3. OCR        - only when steps 1-2 found no usable text

OCR engines are optional. RapidOCR (bundled ONNX models) is
preferred because it needs no external install. Tesseract via
pytesseract is used as a second opinion when it is available.

DOCX
----
A .docx is a zip archive holding word/document.xml. Its text is
read straight out of that XML with the standard library, so DOCX
support costs no new dependency. The file is dispatched here on
its extension, and a file that claims to be a .docx but is not a
zip is rejected rather than silently analysed as an empty
document.
"""

import os
import re
import threading
import zipfile
from xml.sax.saxutils import unescape

import numpy as np
import pymupdf
from pypdf import PdfReader


# ============================================================
# CONFIGURATION
# ============================================================

# A text layer must clear both bars to be trusted as real text.
# This stops a scanned PDF that yields a stray header or page
# number from skipping OCR.
MIN_TEXT_CHARS = 80
MIN_TEXT_WORDS = 15

# Rendering resolution for OCR. Measured on a real scanned
# resume: 300 DPI recovered more small text than 200 DPI for
# about one extra second, while 400 DPI gained nothing more.
OCR_DPI = int(os.environ.get("RESUMEAI_OCR_DPI", "300"))

# Safety valve so a huge document cannot stall a request.
MAX_OCR_PAGES = int(os.environ.get("RESUMEAI_MAX_OCR_PAGES", "10"))

WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'+/.\-#]*")

# OCR engines are expensive to build, so each one is created
# once and reused.
_engine_lock = threading.Lock()
_rapid_engine = None
_rapid_failed = False


# ============================================================
# HELPERS
# ============================================================

def _looks_usable(text):
    """
    Decide whether extracted text is real content or just
    noise such as a page number or a stray header.
    """

    if not text:
        return False

    stripped = text.strip()

    if len(stripped) < MIN_TEXT_CHARS:
        return False

    words = WORD_PATTERN.findall(stripped)

    return len(words) >= MIN_TEXT_WORDS


def _ocr_engine():
    """
    Return a cached RapidOCR engine, or None when it cannot be
    used. Never raises.
    """

    global _rapid_engine, _rapid_failed

    if _rapid_failed:
        return None

    if _rapid_engine is not None:
        return _rapid_engine

    with _engine_lock:

        if _rapid_engine is not None:
            return _rapid_engine

        if _rapid_failed:
            return None

        try:
            from rapidocr_onnxruntime import RapidOCR

            _rapid_engine = RapidOCR()

            print("OCR ready: RapidOCR")

            return _rapid_engine

        except Exception as error:  # noqa: BLE001
            print("RapidOCR unavailable:", error)
            _rapid_failed = True
            return None


def _tesseract_cmd():
    """
    Locate the Tesseract binary, including the usual Windows
    install folder, so PATH is not the only place it can be.
    """

    override = os.environ.get("TESSERACT_CMD")

    if override and os.path.exists(override):
        return override

    try:
        import pytesseract
        from pytesseract import pytesseract as _pt

        _pt.tesseract_cmd = override or getattr(
            _pt, "tesseract_cmd", _pt.tesseract_cmd
        )

        if pytesseract.get_tesseract_version():
            return getattr(_pt, "tesseract_cmd", None) or "tesseract"

    except Exception:  # noqa: BLE001
        pass

    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(
            r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"
        ),
    ):
        if candidate and os.path.exists(candidate):
            return candidate

    return None


def _page_to_array(page, dpi=OCR_DPI):
    """
    Render one page to a plain RGB numpy array for OCR.
    """

    pix = page.get_pixmap(dpi=dpi)

    array = np.frombuffer(
        pix.samples, dtype=np.uint8
    ).reshape(pix.height, pix.width, pix.n)

    # Drop the alpha channel when present.
    if array.shape[2] == 4:
        array = array[:, :, :3]

    elif array.shape[2] == 1:
        array = np.repeat(array, 3, axis=2)

    return np.ascontiguousarray(array)


def _run_rapidocr(page):
    """OCR one page with RapidOCR. Returns text or ''."""

    engine = _ocr_engine()

    if engine is None:
        return ""

    try:
        result, _ = engine(_page_to_array(page))
    except Exception as error:  # noqa: BLE001
        print("RapidOCR page failed:", error)
        return ""

    if not result:
        return ""

    lines = []

    for item in result:
        # Each entry is (box, text, confidence).
        try:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                lines.append(str(item[1]))
        except Exception:  # noqa: BLE001
            continue

    return "\n".join(lines)


def _run_tesseract(page):
    """OCR one page with Tesseract. Returns text or ''."""

    command = _tesseract_cmd()

    if not command:
        return ""

    try:
        import pytesseract

        from PIL import Image

        pytesseract.pytesseract.tesseract_cmd = command

        image = Image.fromarray(_page_to_array(page))

        return pytesseract.image_to_string(image) or ""

    except Exception as error:  # noqa: BLE001
        print("Tesseract page failed:", error)
        return ""


# ============================================================
# STRATEGY 1 + 2: TEXT LAYER
# ============================================================

def _text_via_pypdf(file_path):
    """Normal text extraction. Returns text or ''."""

    try:
        reader = PdfReader(file_path)

        if getattr(reader, "is_encrypted", False):
            # An empty user password is common and still opens.
            try:
                if reader.decrypt("") == 0:
                    return ""
            except Exception:  # noqa: BLE001
                return ""

        pages = []

        for page in reader.pages:

            try:
                page_text = page.extract_text()
            except Exception:  # noqa: BLE001
                page_text = ""

            if page_text and page_text.strip():
                pages.append(page_text.strip())

        return "\n\n".join(pages).strip()

    except Exception as error:  # noqa: BLE001
        print("pypdf extraction failed:", error)
        return ""


def _text_via_pymupdf(file_path):
    """
    Second text attempt. Handles PDFs whose text layer pypdf
    mangles, and reports a real error for damaged files.
    """

    try:
        doc = pymupdf.open(file_path)

    except Exception as error:  # noqa: BLE001
        print("PyMuPDF could not open the file:", error)
        return ""

    try:
        if doc.needs_pass:
            if not doc.authenticate(""):
                return ""

        pages = []

        for page in doc:
            page_text = page.get_text("text")

            if page_text and page_text.strip():
                pages.append(page_text.strip())

        return "\n\n".join(pages).strip()

    except Exception as error:  # noqa: BLE001
        print("PyMuPDF extraction failed:", error)
        return ""

    finally:
        doc.close()


# ============================================================
# STRATEGY 3: OCR
# ============================================================

def _text_via_ocr(file_path):
    """
    OCR every page until usable text is found. Returns text or
    '' when no OCR engine could run.
    """

    try:
        doc = pymupdf.open(file_path)

    except Exception as error:  # noqa: BLE001
        print("PyMuPDF could not open the file for OCR:", error)
        return ""

    try:
        if doc.needs_pass and not doc.authenticate(""):
            return ""

        total_pages = doc.page_count
        page_limit = min(total_pages, MAX_OCR_PAGES)

        collected = []
        engine_used = None

        for index in range(page_limit):

            page = doc[index]

            page_text = _run_rapidocr(page)

            if page_text.strip():
                engine_used = "RapidOCR"
            else:
                page_text = _run_tesseract(page)

                if page_text.strip():
                    engine_used = "Tesseract"

            if page_text.strip():
                collected.append(page_text.strip())

            # Stop early once we have enough to analyse.
            if _looks_usable("\n\n".join(collected)):
                break

        if page_limit < total_pages:
            print(
                f"OCR stopped after {page_limit} of "
                f"{total_pages} pages"
            )

        text = "\n\n".join(collected).strip()

        if text:
            print(f"OCR ({engine_used}) recovered {len(text)} chars")

        return text

    except Exception as error:  # noqa: BLE001
        print("OCR extraction failed:", error)
        return ""

    finally:
        doc.close()


# ============================================================
# PUBLIC API
# ============================================================

def _text_via_docx(file_path):
    """
    Read a .docx with the standard library only.

    A .docx is a zip archive. The body of the document is
    word/document.xml, and the text is every <w:t> inside it.
    Word stores each paragraph separately, so paragraph ends have
    to become newlines again after the tags are stripped -
    otherwise the whole resume arrives as one unbroken line and
    every section heading runs into the sentence beneath it.

    Raises on anything that is not a readable Word document, which
    the caller turns into "not_a_docx".
    """

    with zipfile.ZipFile(file_path) as archive:

        if "word/document.xml" not in archive.namelist():
            raise ValueError("archive has no word/document.xml")

        xml = archive.read("word/document.xml").decode(
            "utf-8", "replace"
        )

    # Paragraph, cell and line boundaries -> real breaks. Done
    # before the tags are dropped, while the names still say which
    # is which.
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab\b[^>]*/>", "\t", xml)
    xml = re.sub(r"<w:br\b[^>]*/>", "\n", xml)
    xml = re.sub(r"</w:tc>", "\t", xml)

    # Everything else is formatting: drop it.
    xml = re.sub(r"<[^>]+>", "", xml)

    text = unescape(xml)

    # Collapse the runs of spaces and blank lines that removing
    # the markup leaves behind, without touching the single spaces
    # that separate real words.
    text = re.sub(r"[ \xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_text_detailed(file_path):
    """
    Extract resume text and explain what happened.

    Returns a dict:
        text     the extracted text ('' when nothing was read)
        method   'pypdf' | 'pymupdf' | 'ocr' | 'docx' | ''
        pages    number of pages in the document
        reason   '' | 'encrypted' | 'damaged' | 'no_text'
                  | 'ocr_unavailable' | 'no_readable_text'
                  | 'not_a_docx'
    """

    result = {
        "text": "",
        "method": "",
        "pages": 0,
        "reason": "",
    }

    # ---- a .docx is not a PDF and must not be sent to PyMuPDF ----
    if str(file_path).lower().endswith(".docx"):
        try:
            text = _text_via_docx(file_path)
        except Exception as error:  # noqa: BLE001
            print("DOCX could not be parsed:", error)
            result["reason"] = "not_a_docx"
            return result

        if not _looks_usable(text):
            result["reason"] = "no_readable_text"
            return result

        result["text"] = text
        result["method"] = "docx"
        # Word documents do not expose a reliable page count
        # without rendering them, and nothing downstream needs one.
        result["pages"] = 0
        return result

    # ---- can the document be opened at all? ----
    try:
        with pymupdf.open(file_path) as probe:
            result["pages"] = probe.page_count

            if probe.needs_pass and not probe.authenticate(""):
                result["reason"] = "encrypted"
                return result

    except Exception as error:  # noqa: BLE001
        print("File could not be parsed:", error)
        result["reason"] = "damaged"
        return result

    # ---- strategy 1 + 2: the text layer ----
    text = _text_via_pypdf(file_path)

    if _looks_usable(text):
        result["text"] = text
        result["method"] = "pypdf"
        return result

    pymupdf_text = _text_via_pymupdf(file_path)

    if _looks_usable(pymupdf_text):
        result["text"] = pymupdf_text
        result["method"] = "pymupdf"
        return result

    # Prefer whichever partial text we managed to get.
    partial = pymupdf_text if len(pymupdf_text) > len(text) else text

    # ---- strategy 3: OCR ----
    print("No usable text layer. Trying OCR...")

    ocr_text = _text_via_ocr(file_path)

    if _looks_usable(ocr_text):
        result["text"] = ocr_text
        result["method"] = "ocr"
        return result

    if ocr_text.strip():
        # OCR produced something, just not much of it.
        result["text"] = ocr_text
        result["method"] = "ocr"
        result["reason"] = "no_readable_text"
        return result

    if partial.strip():
        result["text"] = partial
        result["method"] = "pypdf"
        result["reason"] = "no_readable_text"
        return result

    if _ocr_engine() is None and not _tesseract_cmd():
        result["reason"] = "ocr_unavailable"
        return result

    result["reason"] = "no_text"
    return result


def extract_text(file_path):
    """
    Extract text from a resume PDF.

    Text PDFs are read directly. Scanned PDFs fall back to OCR.
    Returns '' only when nothing at all could be read.
    """

    return extract_text_detailed(file_path)["text"]


# Messages kept here so the API and the tests agree on wording.
ERROR_MESSAGES = {
    "encrypted": (
        "This PDF is password protected. "
        "Please upload an unlocked copy of your resume."
    ),
    "damaged": (
        "This PDF could not be opened. "
        "It may be corrupted - please try exporting it again."
    ),
    "no_text": (
        "No readable text was found in this PDF. "
        "If it is a scanned document it may be too blurry to read."
    ),
    "ocr_unavailable": (
        "This looks like a scanned PDF, but OCR is not available "
        "on the server. Please install an OCR engine, or upload "
        "a text-based PDF."
    ),
    "no_readable_text": (
        "Only a very small amount of text could be read from this "
        "file. Please upload a clearer or text-based version, or "
        "save it as a proper PDF or DOCX."
    ),
    "not_a_docx": (
        "This DOCX file could not be opened. If it is a Word "
        "document, save it as .docx (not .doc) and try again."
    ),
}


def friendly_error(reason):
    """A clear, actionable message for the given failure."""

    return ERROR_MESSAGES.get(
        reason,
        "Could not extract readable text from this file."
    )
