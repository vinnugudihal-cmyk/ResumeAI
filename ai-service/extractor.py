import fitz
import pytesseract
from PIL import Image
import io
from pypdf import PdfReader


def extract_text(file_path):
    """
    Extract text from a PDF.

    First tries normal PDF text extraction.
    If the PDF contains scanned/image-based pages,
    falls back to OCR.
    """

    # =====================================================
    # STEP 1 — NORMAL PDF TEXT EXTRACTION
    # =====================================================

    try:

        reader = PdfReader(file_path)

        extracted_pages = []

        for page in reader.pages:

            page_text = page.extract_text()

            if page_text:

                cleaned_text = page_text.strip()

                if cleaned_text:
                    extracted_pages.append(cleaned_text)

        normal_text = "\n\n".join(extracted_pages).strip()

        # If enough text was extracted, use it.
        if len(normal_text) >= 50:

            print("PDF text extracted normally.")

            return normal_text

    except Exception as error:

        print(
            "Normal PDF extraction failed:",
            str(error)
        )


    # =====================================================
    # STEP 2 — OCR FALLBACK
    # =====================================================

    print(
        "No usable PDF text found. "
        "Starting OCR..."
    )

    extracted_ocr_pages = []

    try:

        pdf = fitz.open(file_path)

        for page_number, page in enumerate(pdf):

            print(
                f"OCR processing page "
                f"{page_number + 1}/{len(pdf)}..."
            )

            # Render page at high resolution
            matrix = fitz.Matrix(2, 2)

            pix = page.get_pixmap(
                matrix=matrix,
                alpha=False
            )

            # Convert rendered page to PIL image
            image_bytes = pix.tobytes("png")

            image = Image.open(
                io.BytesIO(image_bytes)
            )

            # OCR
            page_text = pytesseract.image_to_string(
                image
            )

            if page_text:

                cleaned_text = page_text.strip()

                if cleaned_text:
                    extracted_ocr_pages.append(
                        cleaned_text
                    )

        pdf.close()

        ocr_text = "\n\n".join(
            extracted_ocr_pages
        ).strip()

        print(
            "OCR extracted characters:",
            len(ocr_text)
        )

        return ocr_text

    except Exception as error:

        print(
            "OCR extraction failed:",
            str(error)
        )

        return ""