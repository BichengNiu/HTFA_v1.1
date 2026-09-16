from htfa.app.ui.style_loader import load_cached_styles


def test_print_page_number_uses_page_margin_box() -> None:
    css = load_cached_styles()

    assert "@bottom-center" in css
    assert 'content: "第 " counter(page) " 页";' in css
    assert ".uae-print-page-number" not in css
