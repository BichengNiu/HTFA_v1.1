from unittest.mock import MagicMock

from htfa.monitoring.uae import report


def test_high_frequency_topics_are_isolated_when_oil_fails(monkeypatch) -> None:
    events: list[str] = []

    def fail_oil(*args):
        events.append("oil")
        raise ValueError("oil unavailable")

    def render_finance(*args):
        events.append("government_finance")
        return {"status": "success", "value": 1}

    def render_real_estate(*args):
        events.append("real_estate")
        return {"status": "no_data", "message": "empty"}

    def render_transport(*args):
        events.append("transport")
        return {"status": "success", "value": 2}

    monkeypatch.setattr(
        report,
        "TOPIC_RENDERERS",
        (
            ("oil", "石油生产与收入", fail_oil),
            ("government_finance", "政府金融", render_finance),
            ("real_estate", "房地产", render_real_estate),
            ("transport", "交通物流", render_transport),
        ),
    )
    st_obj = MagicMock()

    results = report.render_high_frequency_topics(
        st_obj,
        (b"workbook", "test.xlsx"),
    )

    assert events == ["oil", "government_finance", "real_estate", "transport"]
    assert results["oil"].status == "failed"
    assert results["oil"].error == "oil unavailable"
    assert results["government_finance"].status == "ok"
    assert results["real_estate"].status == "empty"
    assert results["transport"].status == "ok"
    st_obj.error.assert_called_once_with("石油生产与收入主题渲染失败：oil unavailable")
