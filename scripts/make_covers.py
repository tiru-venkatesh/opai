#!/usr/bin/env python3
"""Regenerates the product page image, OG image and cover images from the one source illustration.

  python3 scripts/make_covers.py          (needs: pillow, fonttools, brotli)

Source: assets/marketing/source/rag-illustration-662x492.png (662x492). It is never scaled UP: every layout
places it at or below native size. The bottom 80px are cropped, which removes the generator's corner sparkle.
Outputs:
  frontend/products/img/rag-illustration.webp   page figure (662x412)
  frontend/products/img/rag-og.jpg              1200x630, Open Graph / Twitter card
  content/covers/devto-1000x420.jpg             Dev.to article cover
  content/covers/gumroad-1280x720.jpg           Gumroad product cover
"""
from pathlib import Path
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets/marketing/source/rag-illustration-662x492.png"
FONTS = ROOT / "frontend/newdemotiru/fonts"
TMP = Path("/tmp/opai-fonts"); TMP.mkdir(exist_ok=True)
BG, INK, MUT, SAGE = (11, 11, 10), (241, 241, 238), (142, 142, 137), (155, 174, 126)


def font(name, size):
    ttf = TMP / (name + ".ttf")
    if not ttf.exists():
        f = TTFont(FONTS / (name + ".woff2")); f.flavor = None; f.save(ttf)
    return ImageFont.truetype(str(ttf), size)


def card(img, width, radius):
    h = round(img.height * width / img.width)
    im = img.resize((width, h), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius, fill=255)
    im.putalpha(mask)
    return im


def compose(W, H, lines, size, chip, foot, card_w, pad, out, quality=88):
    canvas = Image.new("RGB", (W, H), BG)
    glow = Image.new("RGB", (W, H), BG)
    ImageDraw.Draw(glow).ellipse((W * .35, -H * .5, W * 1.15, H * .75), fill=(34, 40, 28))
    canvas = Image.blend(canvas, glow.filter(ImageFilter.GaussianBlur(W // 8)), .9)
    art = card(Image.open(SRC).convert("RGB").crop((0, 0, 662, 412)), card_w, 22)
    x, y = W - pad - art.width, (H - art.height) // 2
    shadow = Image.new("RGBA", (art.width + 120, art.height + 120), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((60, 70, 60 + art.width, 70 + art.height), 22, fill=(0, 0, 0, 190))
    canvas.paste(shadow.filter(ImageFilter.GaussianBlur(28)), (x - 60, y - 60), shadow.filter(ImageFilter.GaussianBlur(28)))
    canvas.paste(art, (x, y), art)
    d = ImageDraw.Draw(canvas)
    d.text((pad, pad), chip.upper(), font=font("manrope-latin-600-normal", max(12, size // 4)), fill=MUT, spacing=2)
    ty = H // 2 - int(len(lines) * size * 1.08 / 2)
    f = font("outfit-latin-600-normal", size)
    for i, (text, color) in enumerate(lines):
        d.text((pad, ty + int(i * size * 1.08)), text, font=f, fill=color)
    d.text((pad, H - pad - size // 3), foot, font=font("manrope-latin-500-normal", max(13, size // 3)), fill=MUT)
    assert x > pad + 40, "layout overlap: art too close to text"
    canvas.convert("RGB").save(out, quality=quality, optimize=True)
    print(f"{out.relative_to(ROOT)}  {W}x{H}  {out.stat().st_size // 1024} KB")


def main():
    page = Image.open(SRC).convert("RGB").crop((0, 0, 662, 412))
    p = ROOT / "frontend/products/img/rag-illustration.webp"
    page.save(p, quality=84, method=6); print(f"{p.relative_to(ROOT)}  {page.width}x{page.height}  {p.stat().st_size // 1024} KB")
    L = [("Ask your documents.", INK), ("Get answers with", INK), ("page numbers.", SAGE)]
    foot = "Free Lite on GitHub  ·  Pro: pgvector, eval harness, API keys"
    compose(1200, 630, L, 54, "Python RAG Starter Kit", foot, 520, 56, ROOT / "frontend/products/img/rag-og.jpg")
    compose(1280, 720, L, 62, "Python RAG Starter Kit", foot, 560, 64, ROOT / "content/covers/gumroad-1280x720.jpg")
    compose(1000, 420, [("RAG from zero", INK), ("and the one-word bug", INK), ("my eval caught", SAGE)], 40,
            "Python · hybrid search · citations", "opai.live", 400, 44, ROOT / "content/covers/devto-1000x420.jpg")


if __name__ == "__main__":
    main()
