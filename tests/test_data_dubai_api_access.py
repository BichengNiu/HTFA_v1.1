"""Official dataset grants must be verified separately; never expose secrets."""

from types import SimpleNamespace

import pytest

from htfa.monitoring.uae.jobs.verify_data_dubai_access import verify_access


def response(status, payload):
    return SimpleNamespace(status_code=status, json=lambda: payload)


def test_missing_credentials_do_not_issue_requests():
    with pytest.raises(ValueError, match="Missing DATA_DUBAI"):
        verify_access(None, "", "")


def test_oauth_failure_does_not_expose_error_body_or_credentials():
    session = SimpleNamespace(post=lambda *a, **k: response(401, {"error": "private-secret"}))
    with pytest.raises(RuntimeError) as error:
        verify_access(session, "private-key", "private-secret")
    assert "401" in str(error.value)
    assert "private-key" not in str(error.value)
    assert "private-secret" not in str(error.value)


def test_a_single_dataset_grant_does_not_authorize_other_datasets(capsys):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return (response(200, {"records": [{"private-record": "private-value"}]})
                if "/ded/" in url else response(401, {"error": "denied"}))

    session = SimpleNamespace(
        post=lambda *a, **k: response(200, {"access_token": "private-token"}), get=get,
    )
    result = verify_access(session, "private-key", "private-secret")
    assert result["status"] == "error"
    assert result["sources"]["ded"]["status"] == "ok"
    assert result["sources"]["dld"]["status"] == "error"
    assert result["sources"]["dubai_customs_air"]["status"] == "error"
    assert len(calls) == 3
    assert all(c[1]["params"] == {"limit": 1} for c in calls)
    assert "private" not in str(result) + capsys.readouterr().out


def test_http_200_gateway_error_is_not_success():
    session = SimpleNamespace(
        post=lambda *a, **k: response(200, {"access_token": "token"}),
        get=lambda *a, **k: response(200, {"Exception": "Unauthorized application"}),
    )
    result = verify_access(session, "key", "secret")
    assert result["status"] == "error"
    assert all(r["status"] == "error" for r in result["sources"].values())
