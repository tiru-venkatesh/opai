import json

from provider_quota import available, limits


def test_configured_provider_limits_block_requests_and_reserved_tokens(monkeypatch):
    monkeypatch.setenv("KARNA_PROVIDER_LIMITS_JSON", json.dumps({
        "groq": {"requests_per_minute": 10, "tokens_per_day": 1000},
    }))
    monkeypatch.setattr("provider_quota._usage", lambda provider: {
        "requests_per_minute": 10, "tokens_per_day": 700,
    })
    assert not available("groq", reserved_tokens=10)
    monkeypatch.setattr("provider_quota._usage", lambda provider: {
        "requests_per_minute": 4, "tokens_per_day": 950,
    })
    assert not available("groq", reserved_tokens=60)
    assert available("groq", reserved_tokens=40)


def test_quota_parser_ignores_unverified_or_invalid_values(monkeypatch):
    monkeypatch.setenv("KARNA_PROVIDER_LIMITS_JSON", '{"groq":{"requests_per_minute":5,"tokens_per_day":-1,"nonsense":9},"unknown":{"requests_per_day":1}}')
    assert limits() == {"groq": {"requests_per_minute": 5}}
