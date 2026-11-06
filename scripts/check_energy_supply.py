"""Verify the native energy dashboard in a real local or deployed browser."""

import argparse
import json
from pathlib import Path
import time

from playwright.sync_api import expect, sync_playwright


def check(url, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100}, accept_downloads=True)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            frame = None
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                for candidate in page.frames:
                    if candidate.get_by_role("button", name="能源保供", exact=True).count():
                        frame = candidate
                        break
                    wake = candidate.get_by_role("button", name="Yes, get this app back up!", exact=True)
                    if wake.count() and wake.is_visible():
                        wake.click()
                if frame:
                    break
                page.wait_for_timeout(1000)
            if frame is None:
                raise RuntimeError("HTFA 导航未加载或部署尚未更新")
            energy_button = frame.get_by_role("button", name="能源保供", exact=True)
            bounds = energy_button.bounding_box()
            if not energy_button.is_visible() or bounds is None or bounds["x"] < 0:
                expand = frame.locator('[data-testid="stSidebarCollapsedControl"] button, [data-testid="stExpandSidebarButton"]')
                expand.first.click()
            energy_button.click()
            expect(frame.get_by_role("tab", name="地图", exact=True)).to_be_visible(timeout=90000)
            expect(frame.locator('[data-testid="stException"]')).to_have_count(0)
            expect(frame.locator('[data-testid="stFileUploader"]')).to_have_count(0)
            map_frame = None
            for _ in range(60):
                for candidate in page.frames:
                    if candidate.locator("#map").count():
                        map_frame = candidate
                        break
                if map_frame:
                    break
                page.wait_for_timeout(500)
            if map_frame is None:
                raise RuntimeError("本地地图组件未加载")
            expect(map_frame.locator(".leaflet-container")).to_be_visible()
            expect(map_frame.locator(".leaflet-tile-loaded").first).to_be_visible(timeout=45000)
            # Trigger a genuine Leaflet popup through its searchable marker.
            search = frame.get_by_text("查找对象", exact=True)
            expect(search).to_be_visible()
            frame.get_by_text("输气管线", exact=True).click()
            expect(frame.get_by_role("checkbox", name="输气管线", exact=True)).not_to_be_checked()
            frame.get_by_text("输气管线", exact=True).click()
            expect(frame.get_by_role("checkbox", name="输气管线", exact=True)).to_be_checked()
            selector = frame.locator('.st-key-energy_supply_map_search_object').get_by_role("combobox")
            selector.click()
            frame.get_by_role("option").first.click()
            for candidate in page.frames:
                if candidate.locator("#map").count():
                    map_frame = candidate
                    break
            expect(map_frame.locator(".leaflet-popup")).to_be_visible(timeout=30000)
            with page.expect_download(timeout=60000) as map_download_info:
                frame.get_by_role("button", name="保存图片", exact=True).click()
            map_download = map_download_info.value
            map_download.save_as(str(output / map_download.suggested_filename))
            page.screenshot(path=str(output / "map.png"), full_page=True)
            for label in ("港口", "船舶", "油气"):
                frame.get_by_role("tab", name=label, exact=True).click()
                expect(frame.locator('[data-testid="stDataFrame"]').first).to_be_visible(timeout=90000)
                expect(frame.locator('[data-testid="stException"]')).to_have_count(0)
                if label == "港口":
                    expect(frame.locator('[data-testid="stExpander"]')).to_have_count(0)
                    expect(frame.get_by_role("button", name="生成下载数据", exact=True)).to_have_count(0)
                page.screenshot(path=str(output / f"tab-{label}.png"), full_page=True)
            with page.expect_download() as download_info:
                frame.get_by_role("button", name="下载数据", exact=True).click()
            download = download_info.value
            download.save_as(str(output / download.suggested_filename))
            if Path(download.path()).stat().st_size == 0:
                raise RuntimeError("油气 CSV 下载为空")
            page.emulate_media(media="print")
            expect(frame.locator(".print-report").first).to_be_visible(timeout=30000)
            page.pdf(path=str(output / "energy-report.pdf"), print_background=True)
            page.emulate_media(media="screen")
            frame.get_by_role("button", name="阿联酋", exact=True).click()
            expect(frame.get_by_role("heading", name="阿联酋经济监测", exact=True)).to_be_visible(timeout=90000)
            expect(frame.locator('[data-testid="stException"]')).to_have_count(0)
            page.set_viewport_size({"width": 820, "height": 1000})
            expect(frame.get_by_role("heading", name="阿联酋经济监测", exact=True)).to_be_visible()
            print(json.dumps({"status": "ready", "url": url, "tabs": ["地图", "港口", "船舶", "油气"],
                              "csv": download.suggested_filename, "print": True, "return_to_uae": True}, ensure_ascii=False))
        finally:
            page.screenshot(path=str(output / "last-page.png"), full_page=True)
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8511")
    parser.add_argument("--output", default=".cache/energy-browser")
    args = parser.parse_args()
    check(args.url, args.output)
