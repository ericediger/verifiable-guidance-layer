"""Render docs/vgl-walkthrough.pdf from docs/pdf/walkthrough.html (Letter, landscape).

    pip install playwright && playwright install chromium
    python docs/pdf/render.py

The page is plain HTML and CSS so the PDF can be regenerated after any change; every
number in it traces to docs/eval-report.json and the recorded output behind the walkthrough.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto((HERE / "walkthrough.html").as_uri(), wait_until="networkidle")
    page.wait_for_timeout(400)
    page.pdf(path=str(HERE.parent / "vgl-walkthrough.pdf"), format="Letter", landscape=True,
             print_background=True, prefer_css_page_size=True)
    browser.close()
print("wrote", HERE.parent / "vgl-walkthrough.pdf")
