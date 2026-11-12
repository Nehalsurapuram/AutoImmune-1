"""Unit test verifying that PDF generation tools produce valid PDF documents."""

from pathlib import Path
import pytest
from tools.generate_pdf import render_markdown_to_pdf

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_markdown_to_pdf_generation(tmp_path):
    md_content = """# Test Title
## Section 1
This is a test paragraph for AutoImmune PDF generation.

| Col A | Col B |
| --- | --- |
| Val 1 | Val 2 |

```
code block line 1
code block line 2
```
"""
    test_pdf = tmp_path / "output.pdf"
    size, pages = render_markdown_to_pdf(md_content, test_pdf, "Test Title")
    
    assert test_pdf.is_file()
    assert size > 500
    assert pages >= 1
    
    data = test_pdf.read_bytes()
    assert data.startswith(b"%PDF-1.4")
    assert b"%%EOF" in data
    assert b"/Type /Catalog" in data
    assert b"/Type /Pages" in data


def test_generated_reports_exist():
    review_pdf = REPO_ROOT / "docs" / "research" / "final_review.pdf"
    paper_pdf = REPO_ROOT / "docs" / "research" / "AutoImmune_research_paper.pdf"
    
    assert review_pdf.is_file(), f"Missing {review_pdf}"
    assert paper_pdf.is_file(), f"Missing {paper_pdf}"
    assert review_pdf.stat().st_size > 10000
    assert paper_pdf.stat().st_size > 20000
