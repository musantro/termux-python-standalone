#!/usr/bin/env python3
"""Synchronize final CPython releases from the Python Foundation metadata."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import gzip
import html
import json
import pathlib
import re
import sys
from urllib.request import Request, urlopen


VERSION_RE = re.compile(r"^3\.(?P<minor>[0-9]+)\.(?P<patch>[0-9]+)$")
DIRECTORY_RE = re.compile(r'href="(3\.[0-9]+\.[0-9]+)/"')
CHECKSUM_RE = re.compile(
    r'<code[^>]*class="checksum"[^>]*>(?P<body>.*?)</code>', re.DOTALL
)


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "Accept-Encoding": "identity",
            "User-Agent": "termux-python-standalone release synchronizer",
        },
    )
    with urlopen(request, timeout=60) as response:
        payload = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            payload = gzip.decompress(payload)
        return payload.decode("utf-8")


def parse_source_checksum(page: str, version: str) -> str | None:
    rows = re.findall(r"<tr.*?</tr>", page, re.DOTALL)
    row = next(
        (
            candidate
            for candidate in rows
            if f"Python-{version}.tar.xz" in candidate
            and "XZ compressed source tarball" in candidate
        ),
        None,
    )
    if row is None:
        raise ValueError(f"release page has no XZ source for Python {version}")

    for match in CHECKSUM_RE.finditer(row):
        body = html.unescape(re.sub(r"<[^>]+>", "", match.group("body")))
        digest = re.sub(r"\s+", "", body).lower()
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            return digest
    # Older release pages expose only MD5. The caller computes the SHA-256
    # directly from the immutable official source archive in that case.
    return None


def download_source_checksum(version: str, ftp_index_url: str) -> str:
    url = f"{ftp_index_url.rstrip('/')}/{version}/Python-{version}.tar.xz"
    request = Request(
        url,
        headers={
            "Accept-Encoding": "identity",
            "User-Agent": "termux-python-standalone release synchronizer",
        },
    )
    digest = hashlib.sha256()
    with urlopen(request, timeout=120) as response:
        for block in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def has_source_archive(version: str, ftp_index_url: str) -> bool:
    page = fetch_text(f"{ftp_index_url.rstrip('/')}/{version}/")
    return f'href="Python-{version}.tar.xz"' in page


def compact_version(version: str) -> str:
    return "".join(version.split("."))


def resolve_release(version: str, source: dict[str, object]) -> dict[str, str] | None:
    if not has_source_archive(version, str(source["ftp_index_url"])):
        return None
    release_page = str(source["release_page_url"]).format(compact=compact_version(version))
    digest = parse_source_checksum(fetch_text(release_page), version)
    if digest is None:
        digest = download_source_checksum(version, str(source["ftp_index_url"]))
    return {
        "python": ".".join(version.split(".")[:2]),
        "version": version,
        "source_sha256": digest,
        "status": "supported",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=pathlib.Path)
    parser.add_argument(
        "--refresh-metadata",
        action="store_true",
        help="refresh hashes available on release pages without redownloading older sources",
    )
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text())
        source = manifest["source"]
        cycle = json.loads(fetch_text(source["release_cycle_url"]))
        ftp_page = fetch_text(source["ftp_index_url"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
        print(f"could not load release metadata: {exc}", file=sys.stderr)
        return 1

    allowed_statuses = set(source.get("statuses", []))
    streams = {
        stream["python"]: stream
        for stream in manifest["streams"]
        if stream["status"] == "supported"
    }
    existing = {
        release["version"]: release
        for release in manifest.get("releases", [])
    }

    if args.refresh_metadata:
        for version, release in existing.items():
            try:
                release_page = source["release_page_url"].format(compact=compact_version(version))
                digest = parse_source_checksum(fetch_text(release_page), version)
            except (OSError, ValueError) as exc:
                print(f"failed to refresh Python {version}: {exc}", file=sys.stderr)
                return 1
            if digest is not None and digest != release.get("source_sha256"):
                release["source_sha256"] = digest
                print(f"refreshed SHA-256 for Python {version}")

    candidates: list[str] = []
    for match in DIRECTORY_RE.finditer(ftp_page):
        version = match.group(1)
        parsed = VERSION_RE.fullmatch(version)
        if parsed is None:
            continue
        minor = f"3.{parsed.group('minor')}"
        if minor not in streams or cycle.get(minor, {}).get("status") not in allowed_statuses:
            continue
        candidates.append(version)

    # The catalog intentionally contains one release per supported minor
    # stream: the newest final patch available from the Python Foundation.
    # Selecting before resolving checksums avoids downloading or inspecting
    # historical archives on every scheduled sync.
    latest_candidates: dict[str, str] = {}
    for version in candidates:
        minor = ".".join(version.split(".")[:2])
        current = latest_candidates.get(minor)
        if current is None or tuple(map(int, version.split("."))) > tuple(
            map(int, current.split("."))
        ):
            latest_candidates[minor] = version

    pending = [
        version
        for version in sorted(latest_candidates.values(), key=lambda value: tuple(map(int, value.split("."))))
        if not existing.get(version, {}).get("source_sha256")
    ]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(resolve_release, version, source): version for version in pending}
        for future in as_completed(futures):
            version = futures[future]
            try:
                release = future.result()
            except (OSError, ValueError) as exc:
                print(f"failed to inspect Python {version}: {exc}", file=sys.stderr)
                return 1
            if release is not None:
                existing[version] = release
                print(f"discovered Python {version}")

    # Keep disabled streams/releases for auditability, but replace the
    # supported set with only the latest patch for each supported minor.
    latest_supported: dict[str, dict[str, str]] = {}
    for stream in streams:
        version = latest_candidates.get(stream)
        if version is None:
            fallback = [
                release
                for release in existing.values()
                if release["python"] == stream and release.get("status") == "supported"
            ]
            if fallback:
                latest_supported[stream] = max(
                    fallback,
                    key=lambda release: tuple(map(int, release["version"].split("."))),
                )
            continue
        release = existing.get(version)
        if release and release.get("source_sha256"):
            latest_supported[stream] = release

    missing = [stream for stream in streams if stream not in latest_supported]
    if missing:
        print(f"no Python releases discovered for streams: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1

    retained = [
        release
        for release in existing.values()
        if release.get("status") != "supported"
    ] + list(latest_supported.values())
    manifest["releases"] = sorted(
        retained,
        key=lambda release: tuple(map(int, release["version"].split("."))),
    )
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"synchronized {len(manifest['releases'])} CPython releases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
