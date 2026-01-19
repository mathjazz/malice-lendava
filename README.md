# Daily malice publisher (GitHub Pages)

This repo uses GitHub Actions to fetch:
- Pizzeria Popaj “Dnevne malice” (Brezmesna / Mesna / Solatna)
- Bajzovi dvori “Mursko Središće” gableci image (+ optional OCR)

…and publishes a simple static site to **GitHub Pages**.

## One-time setup (GitHub)
1. Push this repo to GitHub.
2. In **Settings → Pages**, set **Source** to **GitHub Actions**.

## Local run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Build site into ./site (force build even if not 10:00)
python scripts/build_site.py --site_dir site --force
```

Open:
- `site/index.html`

## Notes
- The workflow triggers hourly on weekdays and the script only generates output at **10:00 Europe/Ljubljana**.
- For local OCR you need Tesseract installed. If you don't have it, OCR is skipped automatically.
