"""TLS comparisons must mask only per-connection randomness."""

import ssl

from htfa.monitoring.uae.jobs.diagnose_endpoints import _client_hello_template


def context():
    result = ssl.create_default_context()
    result.minimum_version = result.maximum_version = ssl.TLSVersion.TLSv1_2
    result.set_ciphers("ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256")
    return result


def test_fresh_handshakes_compare_equally_without_reusing_sessions():
    assert _client_hello_template(context(), "data.dubai") == _client_hello_template(context(), "data.dubai")


def test_handshake_comparison_detects_different_protocol_offers():
    changed = context()
    changed.set_alpn_protocols(["http/1.1"])
    assert _client_hello_template(context(), "data.dubai") != _client_hello_template(changed, "data.dubai")
