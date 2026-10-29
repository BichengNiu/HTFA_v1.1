"""Read-only public endpoint checks; never publish data or expose session tokens."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 HTFA/1.1"
)
DATA_DUBAI_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
PROBES = (
    ("baker_hughes", "report listing", "https://rigcount.bakerhughes.com/intl-rig-count", False, {"User-Agent": "Mozilla/5.0"}),
    ("oil", "EIA daily API", "https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key=DEMO_KEY&frequency=daily&data[0]=value&facets[series][]=RBRTE&length=1", False, {}),
    ("oil", "EIA XLS", "https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls", False, {}),
    ("oil", "IMF Dubai crude", "https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS/G001.POILDUB.USD.M?startPeriod=1992-01", False, {}),
    ("oil", "OPEC MOMR", "https://publications.opec.org/momr/", True, {}),
    ("cbuae", "statistics listing", "https://centralbank.ae/en/research-and-statistics/latest-statistics/", True, {"Referer": "https://centralbank.ae/en/research-and-statistics/latest-statistics/"}),
    ("ded", "dataset page", "https://data.dubai/en/l/460521?com_dda_data_and_statistics_ThemeId=36962", False, {"User-Agent": DATA_DUBAI_UA}),
    ("dld", "dataset page", "https://data.dubai/en/l/470061?com_dda_data_and_statistics_ThemeId=62035", False, {"User-Agent": DATA_DUBAI_UA}),
    ("dubai_customs_air", "download manifest", "https://data.dubai/o/dda/data-services/dataset-download?datasetId=459114&page=1&pageSize=30&sortDir=desc", False, {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json"}),
    ("steel", "monthly prices API", "https://mesteel.com/newsletter/get_monthly_prices.php", False, {"User-Agent": "HTFA-MEsteel-data-collector/1.0", "Accept": "application/json"}),
    ("fcsc", "CPI SDMX", "https://releaseeuaestat.fcsc.gov.ae/rest/data/FCSA,DF_CPI/all?startPeriod=2021-01&dimensionAtObservation=AllDimensions", True, {"Accept": "application/vnd.sdmx.data+csv;version=2.0.0", "Referer": "https://uaestat.fcsc.gov.ae/"}),
    ("public_market", "EIBOR", "https://www.centralbank.ae/umbraco/surface/eibor/GetEiborData", True, {}),
    ("public_market", "FX", "https://www.centralbank.ae/umbraco/Surface/Exchange/GetExchangeRateData?lang=en", True, {}),
    ("public_market", "DFM client", "https://www.dfm.ae/the-exchange/statistics-reports/historical-data/dfmgi", True, {}),
    ("public_market", "ADX client", "https://www.adx.ae/", True, {}),
    ("public_market", "NY Fed EFFR", "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2023-01-01", True, {}),
)


def public_url(url):
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))


def describe(body, *, truncated=False):
    """Return structure and known blocking signals, never full HTML or cookies."""
    text = body.decode("utf-8", errors="replace")
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    result = {"title": html.unescape(re.sub(r"\s+", " ", title[1])).strip()[:160] if title else None}
    markers = ("access denied", "request rejected", "forbidden", "incapsula", "imperva",
               "akamai", "cloudflare", "captcha", "enable javascript", "javascript required",
               "document.cookie", "window.location", "smartsso.dubai.gov.ae", "liferay")
    result["signals"] = [marker for marker in markers if marker in text.lower()]
    result["csrf_assignment_present"] = bool(re.search(r"Liferay\.authToken\s*=\s*['\"]", text))
    result["json_valid"] = None if truncated else False
    try:
        data = json.loads(text)
        result["json_valid"] = True
        result["json_keys"] = list(data)[:12] if isinstance(data, dict) else []
    except (ValueError, TypeError):
        pass
    return result


def probe(item):
    source, label, url, browser, headers = item
    result = {"source": source, "endpoint": label, "url": public_url(url),
              "transport": "curl_cffi Chrome" if browser else "urllib"}
    try:
        if browser:
            from curl_cffi import requests
            response = requests.get(url, impersonate="chrome", timeout=60, headers=headers)
            status, final, content_type = response.status_code, response.url, response.headers.get("Content-Type", "")
            truncated = len(response.content) > 262144
            body = response.content[:262144]
        else:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*", **headers})
            try:
                response = urlopen(request, timeout=60)
            except HTTPError as error:
                response = error
            with response:
                status, final, content_type = response.code, response.url, response.headers.get("Content-Type", "")
                body = response.read(262145)
                truncated = len(body) > 262144
                body = body[:262144]
        result.update(status=status, final_url=public_url(final), content_type=content_type,
                      sampled_bytes=len(body), body_truncated=truncated,
                      **describe(body, truncated=truncated))
    except Exception as error:
        # Do not serialize exception strings; they can include redirects/query credentials.
        result["error_type"] = type(error).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(probe, PROBES))
    document = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "probes": results}
    for result in results:
        print(json.dumps(result, ensure_ascii=False), flush=True)
    if args.output:
        args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
