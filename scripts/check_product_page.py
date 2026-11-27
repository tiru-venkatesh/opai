#!/usr/bin/env python3
"""Pre-launch checks for frontend/products/python-rag-starter.html.

  python3 scripts/check_product_page.py            # structural checks; placeholders are warnings
  python3 scripts/check_product_page.py --release  # placeholders ({{GUMROAD_URL}}, {{GITHUB_URL}}) are errors
  python3 scripts/check_product_page.py --fill GUMROAD_URL=https://... GITHUB_URL=https://...   # fill in place
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "frontend/products/python-rag-starter.html"
LITE_SRC = ROOT / "packages/opai-rag-starter-lite/src"
VOID = {"meta", "link", "br", "img", "input", "hr", "source"}


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.ids, self.hrefs, self.ext, self.errors = [], [], [], [], []
        self.h1 = 0
        self.imgs, self.og_image = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "img":
            self.imgs.append(a)
        if tag == "meta" and a.get("property") == "og:image":
            self.og_image = a.get("content")
        if tag == "h1":
            self.h1 += 1
        if tag == "a" and "href" in a:
            self.hrefs.append(a["href"])
        if tag in ("script", "img", "iframe", "source") and a.get("src", "").startswith(("http:", "https:", "//")):
            self.ext.append(a["src"])
        if tag == "link" and a.get("rel") in ("stylesheet", "preload") and a.get("href", "").startswith(("http", "//")):
            self.ext.append(a["href"])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unbalanced </{tag}> (open: {self.stack[-3:]})")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()


def main(argv):
    if "--fill" in argv:
        text = PAGE.read_text(encoding="utf-8")
        for kv in argv[argv.index("--fill") + 1:]:
            k, _, v = kv.partition("=")
            if not v.startswith("https://"):
                print(f"refusing {k}: value must start with https://"); return 1
            text = text.replace("{{" + k + "}}", v)
        PAGE.write_text(text, encoding="utf-8")
    release = "--release" in argv
    text = PAGE.read_text(encoding="utf-8")
    errors, warns = [], []

    p = P(); p.feed(text)
    errors += p.errors + ([f"unclosed tags: {p.stack}"] if p.stack else [])
    if p.h1 != 1:
        errors.append(f"expected exactly one <h1>, found {p.h1}")
    dup = {i for i in p.ids if p.ids.count(i) > 1}
    if dup:
        errors.append(f"duplicate ids: {sorted(dup)}")
    for h in p.hrefs:
        if h.startswith("#") and h[1:] not in p.ids:
            errors.append(f"anchor {h} has no matching id")
        if h.startswith("http://"):
            errors.append(f"insecure link: {h}")
    if p.ext:
        errors.append(f"external resources would be loaded: {p.ext}")
    if "<title>" not in text or 'name="description"' not in text:
        errors.append("missing <title> or meta description")

    web = ROOT / "frontend"
    for a in p.imgs:
        src = a.get("src", "")
        if not a.get("alt"):
            errors.append(f"<img {src}> has no alt text")
        if not (a.get("width") and a.get("height")):
            errors.append(f"<img {src}> needs width and height (prevents layout shift)")
        f = web / src.lstrip("/")
        if src.startswith("/") and not f.exists():
            errors.append(f"<img> file missing: {f}")
        elif src.startswith("/") and f.stat().st_size > 300 * 1024:
            errors.append(f"<img> {src} is {f.stat().st_size // 1024} KB (max 300 KB)")
    if p.og_image:
        og = web / p.og_image.replace("https://opai.live", "").lstrip("/")
        if not og.exists():
            errors.append(f"og:image file missing: {og}")
    else:
        warns.append("no og:image (link previews will be bare)")

    left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", text)))
    if left:
        (errors if release else warns).append(f"unfilled placeholders: {left}")

    loc = sum(len(f.read_text().splitlines()) for f in LITE_SRC.rglob("*.py"))
    if "under 800 lines" in text and loc >= 800:
        errors.append(f"page says Lite is under 800 lines but it is {loc}")

    for w in warns: print("WARN ", w)
    for e in errors: print("ERROR", e)
    print(f"ok: {len(p.ids)} ids, {len(p.hrefs)} links, Lite is {loc} lines" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
