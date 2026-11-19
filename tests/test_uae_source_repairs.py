"""Checks for official source discovery and transport repairs."""

from types import SimpleNamespace


from htfa.monitoring.uae.jobs import source_employment










def test_google_429_retries_same_session(monkeypatch):
    calls = []
    def get(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=429 if len(calls) == 1 else 200,
                               headers={"Retry-After": "1"}, text=')]}\'\n{"widgets":[]}',
                               raise_for_status=lambda: None)
    delays = []
    monkeypatch.setattr(source_employment.time, "sleep", delays.append)
    session = SimpleNamespace(get=get)
    assert source_employment._google_request_json("url", params={}, session=session) == {"widgets": []}
    assert len(calls) == 2
    assert delays == [1]
