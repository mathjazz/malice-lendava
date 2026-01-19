import argparse
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

POPaj_URL = "https://pizzeria-popaj.si/"
BAJZ_URL = "https://www.bajzovidvori.com/index.php/gableci"


def is_target_time(tz_name: str, force: bool = False) -> bool:
    if force:
        return True
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    if now.weekday() > 4:
        return False
    return now.hour == 10 and now.minute == 0


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def fetch_popaj() -> dict:
    r = requests.get(POPaj_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    wanted = ["Brezmesna malica", "Mesna malica", "Solatna malica"]
    result = {}

    # Find the "Dnevne malice" header to narrow the search area (best effort)
    dnevne = None
    for h in soup.find_all(["h1", "h2", "h3"]):
        if norm(h.get_text()) == "Dnevne malice":
            dnevne = h
            break

    for name in wanted:
        # Locate the H2 heading for the malica
        h2 = None
        if dnevne:
            for cand in dnevne.find_all_next("h2", limit=40):
                if norm(cand.get_text()) == name:
                    h2 = cand
                    break
        if not h2:
            for cand in soup.find_all("h2"):
                if norm(cand.get_text()) == name:
                    h2 = cand
                    break

        if not h2:
            result[name] = ["(not found)"]
            continue

        # Try to identify the container for this malica.
        # Commonly the <h2> and a <header> live inside a shared wrapper.
        container = h2
        for _ in range(4):
            if container and getattr(container, "name", None) in ("section", "article", "div"):
                # If this container has a header, it's a strong signal
                if container.find("header"):
                    break
            container = container.parent

        lines = []

        # 1) Extract from <header> inside the container (if present)
        hdr = container.find("header") if container else None
        if hdr:
            hdr_text = norm(hdr.get_text(" "))
            if hdr_text and "Your browser does not support SVG" not in hdr_text:
                hdr_text = hdr_text.replace("~", "").strip()
                if hdr_text:
                    lines.append(hdr_text)

            # 2) Extract all <p> elements at the SAME nesting level as <header>
            # یعنی: <p> siblings that share the same parent as <header>
            for sib in hdr.next_siblings:
                if not hasattr(sib, "name"):
                    continue
                if sib.name == "p" and sib.parent == hdr.parent:
                    p_text = norm(sib.get_text(" "))
                    if p_text and "Your browser does not support SVG" not in p_text:
                        p_text = p_text.replace("~", "").strip()
                        if p_text:
                            lines.append(p_text)

        # Fallback: if we didn't find a <header> container pattern, keep the older behavior
        if not lines:
            for sib in h2.next_siblings:
                if getattr(sib, "name", None) == "h2":
                    break
                if hasattr(sib, "get_text"):
                    t = norm(sib.get_text(" "))
                else:
                    t = norm(str(sib))
                if t and "Your browser does not support SVG" not in t:
                    t = t.replace("~", "").strip()
                    if t:
                        lines.append(t)

        # Deduplicate while preserving order
        out, seen = [], set()
        for ln in lines:
            key = ln.lower()
            if key not in seen:
                seen.add(key)
                out.append(ln)

        result[name] = out or ["(no items parsed)"]

    return result


def fetch_bajz_image(dest_path: str) -> str:
    r = requests.get(BAJZ_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    header = None
    for h in soup.find_all(["h1", "h2", "h3"]):
        if norm(h.get_text()).lower() == "mursko središće":
            header = h
            break

    img = header.find_next("img") if header else None

    if not img:
        for cand in soup.find_all("img"):
            src = (cand.get("src") or "").lower()
            if "mursko" in src and src.endswith((".jpg", ".jpeg", ".png")):
                img = cand
                break

    if not img or not img.get("src"):
        raise RuntimeError("Could not find Mursko Središće image.")

    src = img["src"].strip()
    if src.startswith("/"):
        src = "https://www.bajzovidvori.com" + src
    elif src.startswith("tjednigableci/"):
        src = "https://www.bajzovidvori.com/" + src

    img_r = requests.get(src, timeout=60)
    img_r.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(img_r.content)
    return src


def try_ocr(image_path: str) -> str:
    # Optional dependency; if OCR isn't available locally, we just skip it.
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return ""

    try:
        im = Image.open(image_path)
        for lang in ("slv", "eng"):
            try:
                text = pytesseract.image_to_string(im, lang=lang)
                text = norm(text)
                if text:
                    return text
            except Exception:
                pass
    except Exception:
        return ""
    return ""


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&#39;")
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site_dir", default="site")
    ap.add_argument("--tz", default="Europe/Ljubljana")
    ap.add_argument("--force", action="store_true", help="Build even if it's not 10:00 (useful for local testing).")
    args = ap.parse_args()

    site_dir = args.site_dir
    assets_dir = os.path.join(site_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    popaj = fetch_popaj()

    bajz_img_fs = os.path.join(assets_dir, "bajz_mursko.jpg")
    bajz_img_url = fetch_bajz_image(bajz_img_fs)
    bajz_ocr = try_ocr(bajz_img_fs)

    now = datetime.now(ZoneInfo(args.tz)).strftime("%Y-%m-%d %H:%M %Z")

    # Raw text report
    report_txt = []
    report_txt.append(f"Malice report ({now})\n")
    report_txt.append("Pizzeria Popaj — Dnevne malice\n")
    for k, items in popaj.items():
        report_txt.append(f"\n{k}:\n" + "\n".join(items))
    report_txt.append("\n\nBajzovi dvori — Mursko Središće\n")
    report_txt.append(f"Image URL: {bajz_img_url}\n")
    report_txt.append("OCR:\n" + (bajz_ocr or "(none)"))
    with open(os.path.join(assets_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report_txt))

    # Build HTML sections
    sections_html = []
    for k, items in popaj.items():
        li = "\n".join(f"<li>{html_escape(x)}</li>" for x in items)
        sections_html.append(f"""
          <section class="card">
            <h2>{html_escape(k)}</h2>
            <ul>{li}</ul>
          </section>
        """)

    ocr_block = ""
    if bajz_ocr:
        ocr_block = f"""
          <details class="card">
            <summary><strong>OCR (best effort)</strong></summary>
            <pre>{html_escape(bajz_ocr)}</pre>
          </details>
        """

    html = f"""<!doctype html>
<html lang="sl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dnevne malice</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 24px; background: #f6f7f9; }}
    .wrap {{ max-width: 980px; margin: 0 auto; }}
    header {{ margin-bottom: 16px; }}
    .meta {{ color: #555; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
    .card {{ background: white; border-radius: 14px; padding: 14px 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.06); }}
    h1 {{ margin: 0 0 6px 0; font-size: 22px; }}
    h2 {{ margin: 0 0 10px 0; font-size: 18px; }}
    ul {{ margin: 0; padding-left: 18px; }}
    img {{ width: 100%; height: auto; border-radius: 12px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
    a {{ color: inherit; }}
    footer {{ margin-top: 18px; color: #666; font-size: 13px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Dnevne malice</h1>
      <div class="meta">Last updated: {html_escape(now)}</div>
    </header>

    <h2>Pizzeria Popaj — “Dnevne malice”</h2>
    <div class="grid">
      {''.join(sections_html)}
    </div>

    <h2 style="margin-top:18px;">Bajzovi dvori — Mursko Središće</h2>
    <div class="card">
      <div style="margin-bottom:8px;">
        Source page: <a href="{BAJZ_URL}">{BAJZ_URL}</a><br/>
        Image URL: <a href="{html_escape(bajz_img_url)}">{html_escape(bajz_img_url)}</a>
      </div>
      <img src="assets/bajz_mursko.jpg" alt="Bajzovi dvori — Mursko Središće gableci" />
    </div>

    {ocr_block}

    <footer>
      <div class="card">
        Raw text report: <a href="assets/report.txt">assets/report.txt</a>
      </div>
    </footer>
  </div>
</body>
</html>
"""

    os.makedirs(site_dir, exist_ok=True)
    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Built site into: {site_dir}")


if __name__ == "__main__":
    main()
