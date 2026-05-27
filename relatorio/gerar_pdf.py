"""
Gera o PDF dos slides em dois passos:
  1. Marp CLI: SLIDES.md → SLIDES.html
  2. Playwright: SLIDES.html → SLIDES.pdf

Uso (dentro da pasta relatorio/):
    python3 gerar_pdf.py
"""

import subprocess
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT     = Path(__file__).parent   # relatorio/
SLIDES   = ROOT / "SLIDES.md"
HTML_OUT = ROOT / "SLIDES.html"
PDF_OUT  = ROOT / "SLIDES.pdf"

# ── Passo 1: Marp → HTML ─────────────────────────────────────────────────────
print("▶ Gerando HTML com Marp...")
result = subprocess.run(
    ["npx", "@marp-team/marp-cli", str(SLIDES),
     "--html", "--output", str(HTML_OUT), "--no-stdin"],
    capture_output=True, text=True
)
if result.returncode != 0:
    print("Erro no Marp:")
    print(result.stderr)
    sys.exit(1)
print(f"  ✔ HTML gerado: {HTML_OUT}")

# ── Passo 2: HTML → PDF via Playwright ───────────────────────────────────────
print("▶ Convertendo para PDF com Playwright...")
with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
    page = browser.new_page()
    page.goto(f"file://{HTML_OUT.resolve()}", wait_until="networkidle")
    page.pdf(path=str(PDF_OUT), print_background=True, width="1280px", height="720px")
    browser.close()

print(f"  ✔ PDF gerado: {PDF_OUT}")
