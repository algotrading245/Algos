"""Prints the text of a paper's PDF, so the researcher agent can read the full paper (tables, definitions) and not
only the abstract.  Works on a link (arXiv, NY Fed, SSRN delivery links, journal PDFs) or a local file.

    python tools/pdf_text.py https://arxiv.org/pdf/2101.01234                 # first 12 pages
    python tools/pdf_text.py https://www.newyorkfed.org/.../sr125.pdf --pages 5-20
    python tools/pdf_text.py marketdata/papers/osler2002.pdf --pages all --find "Table 3"

Downloads are kept under marketdata/papers/ (named after the link), so a second read does not fetch again.  The
file is only parsed as a PDF, never opened or run.  A page that is not a PDF (a login wall, an SSRN 403) is
reported as such: say the paper could not be read rather than guessing its content.
"""
import argparse
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

PAPERS = Path(__file__).resolve().parent.parent / "marketdata" / "papers"
AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def fetch(url):
    if "arxiv.org/abs/" in url:
        url = url.replace("/abs/", "/pdf/")
    name = re.sub(r"[^\w.-]+", "_", url.split("//", 1)[-1])[-80:]
    path = PAPERS / (name if name.lower().endswith(".pdf") else name + ".pdf")
    if path.exists():
        return path
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/pdf,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception as e:
        sys.exit(f"could not fetch {url}: {e}")
    if not data.startswith(b"%PDF"):
        sys.exit(f"{url} did not return a PDF ({len(data)} bytes, starts {data[:40]!r}); the paper is not readable here")
    PAPERS.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"saved {path.relative_to(PAPERS.parent.parent)} ({len(data) // 1024} kB, sha1 {hashlib.sha1(data).hexdigest()[:10]})")
    return path


def pages_text(path):
    try:
        import fitz
        with fitz.open(path) as doc:
            return [p.get_text() for p in doc]
    except ImportError:
        from pypdf import PdfReader
        return [p.extract_text() or "" for p in PdfReader(path).pages]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="link or local path of the PDF")
    ap.add_argument("--pages", default="1-12", help='"3", "5-20" or "all" (default 1-12)')
    ap.add_argument("--find", help="print only the pages that contain this text (case-insensitive)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    path = fetch(a.source) if re.match(r"https?://", a.source) else Path(a.source)
    if not path.exists():
        sys.exit(f"no file {path}")
    texts = pages_text(path)
    n = len(texts)
    if a.pages == "all":
        lo, hi = 1, n
    else:
        lo, _, hi = a.pages.partition("-")
        lo, hi = int(lo), int(hi or lo)
    print(f"{path.name}: {n} pages, showing {lo}-{min(hi, n)}")
    for i in range(max(lo, 1), min(hi, n) + 1):
        t = texts[i - 1]
        if a.find and a.find.lower() not in t.lower():
            continue
        print(f"\n===== page {i} =====\n{t.strip()}")


if __name__ == "__main__":
    main()
