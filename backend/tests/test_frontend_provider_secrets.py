from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_provider_credentials_are_backend_only():
    frontend = ROOT / "frontend"
    shipped_sources = [
        frontend / "app.js",
        frontend / "attach.js",
        frontend / "README.md",
        ROOT / "backend" / "static" / "app.js",
        ROOT / "backend" / "static" / "attach.js",
    ]
    forbidden = (
        "api.groq.com",
        "api.openrouter.ai",
        "generativelanguage.googleapis.com",
        "S.profile.groqKey =",
        "jv-groqKey",
    )
    for path in shipped_sources:
        source = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{marker} found in frontend source {path.relative_to(ROOT)}"


def test_legacy_browser_provider_key_is_removed_from_saved_profile():
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "delete o.profile.groqKey" in source
    assert "delete S.profile.groqKey" in source
