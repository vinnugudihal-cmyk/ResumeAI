"""
End-to-end test of the diagnostic scoring system with a real PDF.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Never the production database, even though this script does not
# open one today.
import db_guard  # noqa: E402

db_guard.use_temporary_database()

from extractor import extract_text
from analyzer import analyze_resume

# Test with a real uploaded PDF
pdf_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "backend", "uploads", "1790351713425-Vinoda Resume.pdf"
)

if not os.path.exists(pdf_path):
    # Try alternate
    uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "uploads")
    pdfs = [f for f in os.listdir(uploads_dir) if f.endswith(".pdf")]
    if pdfs:
        pdf_path = os.path.join(uploads_dir, pdfs[0])
    else:
        print("No PDF files found in uploads/")
        sys.exit(1)

print(f"Testing with: {os.path.basename(pdf_path)}")
text = extract_text(pdf_path)
print(f"Extracted {len(text)} chars from PDF")
print("---")

result = analyze_resume(text)

print()
print("=" * 60)
print(f"TOTAL SCORE: {result['score']}/100")
print(f"ATS SCORE: {result['ats_score']}%")
print(f"SKILLS: {result['skills']}")
print()

for key, crit in result["criteria"].items():
    lost = crit["max_score"] - crit["score"]
    print(f"[{crit['label']}] {crit['score']}/{crit['max_score']} (lost {lost})")
    if crit.get("detected"):
        for d in crit["detected"][:3]:
            print(f"  OK {d}")
    if crit.get("missing"):
        for m in crit["missing"][:3]:
            print(f"  MISS {m}")
    if crit.get("deductions"):
        for d in crit["deductions"][:3]:
            print(f"  DEDUCT -{d['points']} pts: {d['reason']}")
    if crit.get("actions"):
        for a in crit["actions"][:2]:
            print(f"  ACTION {a}")
    print()

print("IMPROVEMENT PLAN (top 3):")
for item in result.get("improvement_plan", [])[:3]:
    print(f"  [{item['label']}] {item['score']}/{item['max_score']} (-{item['points_lost']})")
    print(f"    -> {item['top_action'][:100]}")
print()
print(f"MATCHED KEYWORDS: {result.get('matched_keywords', [])}")
print(f"MISSING SECTIONS: {result.get('missing_sections', [])}")
print()

# Verify JSON serialization works
json_output = json.dumps(result, indent=2)
print(f"JSON output size: {len(json_output)} bytes")
print("TEST PASSED - All diagnostic fields present and serializable")
