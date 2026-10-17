"""Model picker: server-side validation, mode restrictions, daily caps, fallback labelling. No network."""
import os
from types import SimpleNamespace

import pytest

from agent import llm, model_catalog as mc


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "HUGGINGFACE_API_KEY", "KARNA_HF_MODELS", "KARNA_HF_WORKSPACE", "KARNA_DAILY_CAPS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    mc._USAGE.clear()


def _reply(text, model="m"):
    return SimpleNamespace(model=model, choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_auto_and_empty_mean_default():
    assert mc.resolve(None, "general") is None
    assert mc.resolve("", "workspace") is None
    assert mc.resolve("auto", "general") is None


def test_unknown_key_rejected():
    with pytest.raises(mc.ModelChoiceError) as e:
        mc.resolve("meta-llama/anything", "general")
    assert e.value.status == 400


def test_client_cannot_inject_provider_model_id():
    # raw provider ids are not catalog keys
    with pytest.raises(mc.ModelChoiceError):
        mc.resolve("openai/gpt-oss-120b", "general")


def test_provider_without_key_is_unavailable():
    with pytest.raises(mc.ModelChoiceError):
        mc.resolve("hf-llama-3-3-70b", "general")           # HUGGINGFACE_API_KEY unset


def test_hf_allowed_in_general_blocked_in_workspace(monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "x")
    assert mc.resolve("hf-llama-3-3-70b", "general").provider == "hf"
    with pytest.raises(mc.ModelChoiceError) as e:
        mc.resolve("hf-llama-3-3-70b", "workspace")
    assert "third-party" in e.value.message
    monkeypatch.setenv("KARNA_HF_WORKSPACE", "on")
    assert mc.resolve("hf-llama-3-3-70b", "workspace") is not None


def test_hf_catalog_from_env(monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "x")
    monkeypatch.setenv("KARNA_HF_MODELS", '[{"key":"hf-x","label":"X","model_id":"org/x"}]')
    keys = [e.key for e in mc.catalog()]
    assert "hf-x" in keys and "hf-llama-3-3-70b" not in keys


def test_public_list_hides_provider_ids():
    rows = mc.public_list("workspace")
    assert all("model_id" not in r and "claude_tier" not in r for r in rows)
    assert next(r for r in rows if r["key"] == "hf-llama-3-3-70b")["available"] is False


def test_daily_cap_per_tier(monkeypatch):
    monkeypatch.setenv("KARNA_DAILY_CAPS", "deep:2")
    deep = mc.get("claude-deep")
    mc.charge(deep, "u1"); mc.charge(deep, "u1")
    with pytest.raises(mc.ModelChoiceError) as e:
        mc.charge(deep, "u1")
    assert e.value.status == 429
    mc.charge(deep, "u2")                                   # other users unaffected
    mc.charge(mc.get("claude-fast"), "u1")                  # other tiers unaffected


def test_selected_model_is_labelled(monkeypatch):
    llm.select("claude-deep", "general", "u")
    entry = llm._sel.get()[0]
    monkeypatch.setattr(llm, "_call_entry", lambda *a, **k: _reply("hi", "claude-opus-5-5"))
    out = llm.final_answer([{"role": "user", "content": "q"}], default_model="d", max_tokens=10)
    assert out == "hi"
    m = llm.last_meta()
    assert (m["key"], m["provider"], m["fallback"]) == ("claude-deep", "anthropic", False)
    assert entry.claude_tier == "deep"


def test_failed_selected_model_labels_fallback(monkeypatch):
    llm.select("claude-deep", "general", "u")
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(llm, "_call_entry", boom)
    monkeypatch.setattr(llm, "_create", lambda **k: _reply("fallback text", "claude-sonnet-5-5"))
    assert llm.final_answer([{"role": "user", "content": "q"}], default_model="d", max_tokens=10) == "fallback text"
    assert llm.last_meta()["fallback"] is True


def test_auto_path_unchanged(monkeypatch):
    llm.select(None, "general", "u")
    seen = {}
    def fake(**k):
        seen.update(k); return _reply("ok", "claude-sonnet-5-5")
    monkeypatch.setattr(llm, "_create", fake)
    assert llm.final_answer([{"role": "user", "content": "q"}], default_model="openai/gpt-oss-20b", max_tokens=5) == "ok"
    assert seen["model"] == "openai/gpt-oss-20b" and llm.last_meta()["key"] == "auto"
