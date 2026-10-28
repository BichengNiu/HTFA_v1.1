"""Download UAE-filtered BTS international segment annual files from its official form."""

import csv
from datetime import date
from html.parser import HTMLParser
import io
import os
from pathlib import Path
import tempfile
import zipfile

from curl_cffi import requests

FORM_URL = "https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FJE&QO_fu146_anzr="


class DownloadForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = {}
        self.fields = []
        self.selected = []

    def handle_starttag(self, tag, attributes):
        item = dict(attributes)
        if tag == "input" and item.get("type") == "hidden" and item.get("name"):
            self.hidden[item["name"]] = item.get("value", "")
        if tag == "input" and item.get("type") == "checkbox" and item.get("name", "").isupper():
            self.fields.append(item["name"])
        if tag == "option" and "selected" in item:
            self.selected.append(item.get("value"))


def filter_zip(content, destination, year):
    """Preserve official fields and units, retaining only US↔AE segment records."""
    from .source_dot_t100 import FIELDS_REQUIRED

    count = 0
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        files = []
        for name in archive.namelist():
            if not name.lower().endswith((".csv", ".txt", ".asc")):
                continue
            with archive.open(name) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
                header = next(csv.reader(text), [])
                if set(FIELDS_REQUIRED) <= {field.strip().upper() for field in header}:
                    files.append(name)
        if len(files) != 1:
            raise ValueError("BTS response must contain exactly one matching segment CSV")
        with archive.open(files[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = [name.strip().upper() for name in reader.fieldnames or []]
            if not set(FIELDS_REQUIRED) <= set(headers):
                raise ValueError("BTS annual archive is missing required segment fields")
            reader.fieldnames = headers
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as output:
                with output.open(f"uae_{year}.csv", "w") as target, io.TextIOWrapper(target, encoding="utf-8", newline="") as text:
                    writer = csv.DictWriter(text, fieldnames=headers)
                    writer.writeheader()
                    for row in reader:
                        if int(row["YEAR"]) != year:
                            raise ValueError("BTS annual archive contains a different year")
                        if {row["ORIGIN_COUNTRY"].strip(), row["DEST_COUNTRY"].strip()} == {"US", "AE"}:
                            writer.writerow(row)
                            count += 1
    return count


def download_year(session, year, directory):
    from .source_dot_t100 import FIELDS_REQUIRED

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    response = session.get(FORM_URL, timeout=60)
    response.raise_for_status()
    form = DownloadForm()
    form.feed(response.text)
    if not set(FIELDS_REQUIRED) <= set(form.fields):
        raise ValueError("BTS form is not the international segment all-carrier table")
    payload = {**form.hidden, **{field: "on" for field in form.fields},
               "cboGeography": "United Arab Emirates", "cboYear": str(year),
               "cboPeriod": "All", "chkDownloadZip": "on", "chkMergeSub": "on", "btnDownload": "Download"}
    response = session.post(FORM_URL, data=payload, timeout=180)
    response.raise_for_status()
    target = directory / f"uae_{year}.zip"
    no_data = directory / f"uae_{year}.nodata"
    if not response.content.startswith(b"PK"):
        result = DownloadForm()
        result.feed(response.text)
        verified_empty = (f"No data available for All Months {year}" in response.text
                          and {"United Arab Emirates", str(year), "All"} <= set(result.selected))
        if not verified_empty:
            raise ValueError(f"BTS did not return a ZIP or a verified no-data response for {year}")
        no_data.write_text(f"Verified official UAE filter returned no data for {year}\n{FORM_URL}\n")
        target.unlink(missing_ok=True)
        return 0
    fd, name = tempfile.mkstemp(prefix=".bts-download-", suffix=".zip", dir=directory)
    os.close(fd)
    temporary = Path(name)
    try:
        count = filter_zip(response.content, temporary, year)
        if count:
            os.replace(temporary, target)
            no_data.unlink(missing_ok=True)
        else:
            no_data.write_text(f"Verified official archive contains no US↔AE segments for {year}\n{FORM_URL}\n")
            target.unlink(missing_ok=True)
        return count
    finally:
        temporary.unlink(missing_ok=True)


def download_recent(directory, *, today=None):
    current = (today or date.today()).year
    # 1990 establishes the historical no-data flag required by the source validator.
    years = sorted({1990, *range(current - 2, current + 1)})
    with requests.Session(impersonate="chrome") as session:
        counts = {year: download_year(session, year, directory) for year in years}
    return "Official BTS annual download: " + ", ".join(f"{year}={count} segments" for year, count in counts.items())
