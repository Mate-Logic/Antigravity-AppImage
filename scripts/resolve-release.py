#!/usr/bin/env python3
"""Resolve, download, and fingerprint the current official Linux package.

The download page is the source of truth.  Google does not publish a checksum
for this archive, so the workflow fingerprints the bytes it downloads and then
passes that digest to appimage-python, which verifies its own download before
building.  A release is considered unchanged only when its source digest is
available in the latest release.
"""

from __future__ import annotations

import hashlib
import html.parser
import json
import os
import re
import sys
import gzip
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DOWNLOAD_PAGE = "https://antigravity.google/download"
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")


class DownloadParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_antigravity = False
        self.section_depth = 0
        self.anchor: tuple[str, list[str]] | None = None
        self.download_url = ""
        self.version = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "section" and attributes.get("id") == "antigravity-2":
            self.in_antigravity = True
            self.section_depth = 1
        elif self.in_antigravity and tag == "section":
            self.section_depth += 1
        if self.in_antigravity and tag == "a":
            href = attributes.get("href", "") or ""
            self.anchor = (href, [])
        if self.in_antigravity and attributes.get("class") == "nav-version-chip":
            self.version = ""

    def handle_data(self, data: str) -> None:
        if self.anchor:
            self.anchor[1].append(data)
        if self.in_antigravity and not self.version:
            match = re.search(r"v?(\d+(?:\.\d+)+)", data)
            if match:
                self.version = match.group(1)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.anchor:
            href, text = self.anchor
            label = " ".join("".join(text).split()).lower()
            if "linux-x64" in href and href.endswith(".tar.gz") and "x64" in label:
                self.download_url = href
            self.anchor = None
        if tag == "section" and self.in_antigravity:
            self.section_depth -= 1
            if self.section_depth == 0:
                self.in_antigravity = False


def request(url: str) -> bytes:
    """Fetch bytes without changing archive contents."""
    return urlopen(
        Request(url, headers={"User-Agent": "AntigravityIDE-AppImage"}), timeout=60
    ).read()


def request_text(url: str) -> bytes:
    """Fetch a possibly gzip-compressed text response."""
    data = request(url)
    return gzip.decompress(data) if data.startswith(b"\x1f\x8b") else data


def latest_source_hash() -> str | None:
    if "/" not in REPOSITORY:
        return None
    api = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
    headers = {"User-Agent": "AntigravityIDE-AppImage", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        release = json.loads(urlopen(Request(api, headers=headers), timeout=30).read())
    except HTTPError as error:
        if error.code == 404:
            return None
        raise
    for asset in release.get("assets", []):
        if asset.get("name") == "SOURCE-SHA256":
            value = request_text(asset["browser_download_url"]).decode().strip().split()
            return value[0].lower() if value else None
    return None


def output(name: str, value: str) -> None:
    print(f"{name}={value}")
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with Path(output_file).open("a", encoding="utf-8") as file:
            file.write(f"{name}={value}\n")


def main() -> int:
    parser = DownloadParser()
    parser.feed(request_text(DOWNLOAD_PAGE).decode("utf-8"))
    if not parser.download_url or not parser.version:
        raise RuntimeError("Could not find the current Linux x64 package on the download page")

    archive = Path.cwd() / "source" / "Antigravity.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(request(parser.download_url))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    output("download_url", parser.download_url)
    output("version", parser.version)
    output("sha256", digest)
    output("archive_path", str(archive))
    output("changed", str(digest.lower() != (latest_source_hash() or "").lower()).lower())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
