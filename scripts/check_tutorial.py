#!/usr/bin/env python3
"""Keeps tutorials honest.

For every content/*.md article:
  <!-- excerpt: path -->  + a code fence  -> every line of the fence must appear, contiguously, in that source file
  <!-- run -->            + a code fence  -> the code is executed; stdout must equal the next <!-- output --> fence
  front matter             -> `tags` has at most 4 entries (Dev.to limit); `published` is present
For content/*.social.md: every numbered X post ("1/ ...") must fit in 280 characters (links count as 23).

  python3 scripts/check_tutorial.py                    # checks; unfilled {{PLACEHOLDERS}} are warnings
  python3 scripts/check_tutorial.py --release          # placeholders are errors
  python3 scripts/check_tutorial.py --build KEY=https://...   # write dist/content/* with comments stripped and values filled
Run it with the Python environment that has opai-rag-starter-lite installed (make setup).
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
FENCE = re.compile(r"(?:<!--\s*(excerpt:[^>]*?|run|output)\s*-->\s*\n)?```([^\n]*)\n(.*?)\n```", re.S)
PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")


def check_article(path: Path, errors: list):
    text = path.read_text(encoding="utf-8")
    fm = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if fm:
        tags = re.search(r"^tags:\s*(.+)$", fm.group(1), re.M)
        if tags and len([t for t in tags.group(1).split(",") if t.strip()]) > 4:
            errors.append(f"{path.name}: more than 4 tags")
        if "published:" not in fm.group(1):
            errors.append(f"{path.name}: front matter missing 'published'")
    blocks = [(m.group(1), m.group(3), m.start()) for m in FENCE.finditer(text)]
    n_ex = n_run = 0
    for i, (kind, body, pos) in enumerate(blocks):
        line = text.count("\n", 0, pos) + 1
        if kind and kind.startswith("excerpt:"):
            n_ex += 1
            src = ROOT / kind.split(":", 1)[1].strip()
            if not src.exists():
                errors.append(f"{path.name}:{line}: excerpt source {src} not found"); continue
            hay = "\n".join(l.rstrip() for l in src.read_text(encoding="utf-8").splitlines())
            needle = "\n".join(l.rstrip() for l in body.splitlines())
            if needle not in hay:
                first = next((l for l in needle.splitlines() if l.strip()), "")
                errors.append(f"{path.name}:{line}: excerpt is not verbatim in {src.name} (first line: {first[:60]!r})")
        elif kind == "run":
            n_run += 1
            nxt = blocks[i + 1] if i + 1 < len(blocks) else None
            if not nxt or nxt[0] != "output":
                errors.append(f"{path.name}:{line}: run block has no following output block"); continue
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            env["OPAI_RAG_EMBEDDER"] = "hash"
            with tempfile.TemporaryDirectory() as tmp:
                r = subprocess.run([sys.executable, "-c", body], capture_output=True, text=True, cwd=tmp, env=env, timeout=120)
            if r.returncode != 0:
                errors.append(f"{path.name}:{line}: run block failed: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}")
            elif r.stdout.strip() != nxt[1].strip():
                errors.append(f"{path.name}:{line}: output differs.\n--- expected\n{nxt[1].strip()}\n--- actual\n{r.stdout.strip()}")
    return n_ex, n_run


def check_social(path: Path, errors: list):
    posts = re.findall(r"^(\d+)/ (.*?)(?=^\d+/ |\Z)", path.read_text(encoding="utf-8"), re.S | re.M)
    for num, body in posts:
        body = PLACEHOLDER.sub("x" * 23, re.sub(r"https?://\S+", "x" * 23, body.strip()))
        if len(body) + len(num) + 2 > 280:
            errors.append(f"{path.name}: X post {num}/ is {len(body) + len(num) + 2} characters (max 280)")
    return len(posts)


def build(values: dict):
    out = ROOT / "dist/content"; out.mkdir(parents=True, exist_ok=True)
    for f in sorted(CONTENT.glob("*.md")):
        t = re.sub(r"<!--\s*(?:excerpt:[^>]*?|run|output)\s*-->\s*\n", "", f.read_text(encoding="utf-8"))
        for k, v in values.items():
            t = t.replace("{{" + k + "}}", v)
        (out / f.name).write_text(t, encoding="utf-8")
        print(f"built {out / f.name}")


def main(argv):
    values = {}
    if "--build" in argv:
        for kv in argv[argv.index("--build") + 1:]:
            k, _, v = kv.partition("=")
            if not v.startswith("https://"):
                print(f"refusing {k}: value must start with https://"); return 1
            values[k] = v
    errors, warns = [], []
    for f in sorted(CONTENT.glob("*.md")):
        if f.name.endswith(".social.md"):
            n = check_social(f, errors); print(f"{f.name}: {n} X posts checked")
        else:
            ex, run = check_article(f, errors); print(f"{f.name}: {ex} excerpts verified verbatim, {run} snippets executed")
        left = sorted(set(PLACEHOLDER.findall(f.read_text(encoding='utf-8'))) - {"{{" + k + "}}" for k in values})
        if left:
            (errors if "--release" in argv else warns).append(f"{f.name}: unfilled placeholders {left}")
    for w in warns: print("WARN ", w)
    for e in errors: print("ERROR", e)
    if errors:
        return 1
    if "--build" in argv:
        build(values)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
