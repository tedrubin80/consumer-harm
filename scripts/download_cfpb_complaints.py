#!/usr/bin/env python3
"""
Download CFPB Consumer Complaint Database bulk exports.

Source: https://www.consumerfinance.gov/data-research/consumer-complaints/
Bulk files: https://files.consumerfinance.gov/ccdb/

The database updates daily. CSV is the usual choice for pandas analysis;
JSON preserves nested structure if needed.

Usage:
    python download_cfpb_complaints.py
    python download_cfpb_complaints.py --format csv
    python download_cfpb_complaints.py --format csv json
    python download_cfpb_complaints.py --output-dir ~/opportunity_harm/cfpb
    python download_cfpb_complaints.py --dry-run
    python download_cfpb_complaints.py --no-extract
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from paths import data_root

CFPB_COMPLAINTS_PAGE = "https://www.consumerfinance.gov/data-research/consumer-complaints/"
CFPB_API_DOCS = "https://cfpb.github.io/ccdb5-api/"
CFPB_FIELDS = "https://cfpb.github.io/api/ccdb/fields.html"

BULK_URLS = {
    "csv": "https://files.consumerfinance.gov/ccdb/complaints.csv.zip",
    "json": "https://files.consumerfinance.gov/ccdb/complaints.json.zip",
}


def human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    for unit in ("KB", "MB", "GB", "TB"):
        num_bytes /= 1024
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
    return f"{num_bytes:.1f} PB"


def head_remote(url: str, timeout: int = 60) -> tuple[int, str | None]:
    curl = shutil.which("curl")
    if not curl:
        return 0, None

    # Do not send a browser User-Agent — Akamai returns 403 for those on this host.
    cmd = [curl, "-sI", "--max-time", str(timeout), url]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return 0, None

    headers = result.stdout
    length_match = re.search(r"(?im)^content-length:\s*(\d+)", headers)
    modified_match = re.search(r"(?im)^last-modified:\s*(.+)$", headers)
    remote_size = int(length_match.group(1)) if length_match else 0
    last_modified = modified_match.group(1).strip() if modified_match else None
    return remote_size, last_modified


def download_with_curl(url: str, dest: Path, resume: bool) -> None:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("`curl` not found; install curl to download large CFPB files with resume support")

    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    target = partial if resume and partial.exists() else dest

    cmd = [
        curl,
        "-L",
        "--fail",
        "--retry",
        "5",
        "--retry-delay",
        "3",
        "--progress-bar",
        "-o",
        str(target),
        url,
    ]
    if resume:
        cmd.insert(1, "-C")
        cmd.insert(2, "-")

    print(f"  curl -> {target.name}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed with exit code {result.returncode}")

    if target is partial and partial.exists():
        partial.rename(dest)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def extract_zip(zip_path: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = out_dir / Path(info.filename).name
            print(f"  extracting {info.filename} -> {target.name}")
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
    return extracted


def write_source_manifest(
    output_dir: Path,
    records: list[dict[str, object]],
) -> None:
    lines = [
        "CFPB Consumer Complaint Database — bulk export",
        f"Downloaded: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Project: opportunity-harm",
        f"Landing page: {CFPB_COMPLAINTS_PAGE}",
        f"API docs: {CFPB_API_DOCS}",
        f"Field reference: {CFPB_FIELDS}",
        "",
        "Files:",
    ]
    for rec in records:
        lines.append(f"  - {rec['format']}: {rec['url']}")
        if rec.get("zip_path"):
            lines.append(f"      zip: {rec['zip_path']} ({human_size(int(rec.get('zip_bytes', 0)))})")
        if rec.get("extracted_paths"):
            for p in rec["extracted_paths"]:
                lines.append(f"      extracted: {p}")
        if rec.get("last_modified"):
            lines.append(f"      remote last-modified: {rec['last_modified']}")
        if rec.get("sha256"):
            lines.append(f"      sha256: {rec['sha256']}")
        lines.append("")

    manifest = output_dir / "SOURCE.txt"
    manifest.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def download_format(
    fmt: str,
    output_dir: Path,
    *,
    dry_run: bool,
    extract: bool,
    resume: bool,
    checksum: bool,
) -> dict[str, object]:
    url = BULK_URLS[fmt]
    remote_size, last_modified = head_remote(url)

    raw_dir = output_dir / "raw"
    extracted_dir = output_dir / "extracted"
    zip_name = f"complaints.{fmt}.zip"
    zip_path = raw_dir / zip_name

    print(f"\n[{fmt.upper()}]")
    print(f"  URL:          {url}")
    print(f"  Remote size:  {human_size(remote_size) if remote_size else 'unknown'}")
    if last_modified:
        print(f"  Last-Modified:{last_modified}")
    print(f"  Local zip:    {zip_path}")

    record: dict[str, object] = {
        "format": fmt,
        "url": url,
        "last_modified": last_modified,
        "zip_path": str(zip_path),
        "zip_bytes": 0,
        "extracted_paths": [],
    }

    if dry_run:
        print("  [dry-run] skipping download")
        return record

    if zip_path.exists() and remote_size and zip_path.stat().st_size == remote_size:
        print("  zip already complete; skipping download")
    else:
        download_with_curl(url, zip_path, resume=resume)

    zip_bytes = zip_path.stat().st_size
    record["zip_bytes"] = zip_bytes
    print(f"  downloaded:   {human_size(zip_bytes)}")

    if checksum:
        digest = sha256_file(zip_path)
        record["sha256"] = digest
        print(f"  sha256:       {digest}")

    if extract:
        paths = extract_zip(zip_path, extracted_dir)
        record["extracted_paths"] = [str(p) for p in paths]
        for p in paths:
            print(f"  ready:        {p} ({human_size(p.stat().st_size)})")

    return record


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download CFPB Consumer Complaint Database bulk exports (opportunity-harm)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(data_root() / "cfpb"),
        help="Directory for raw zips and extracted files (default: data_root()/cfpb)",
    )
    parser.add_argument(
        "--format",
        nargs="+",
        choices=sorted(BULK_URLS),
        default=["csv"],
        help="Which bulk export(s) to fetch (default: csv)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show planned downloads only")
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="Keep zip only; do not unzip into extracted/",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Do not resume partial downloads",
    )
    parser.add_argument(
        "--checksum",
        action="store_true",
        help="Compute sha256 after download (slower on multi-GB files)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("CFPB Consumer Complaint Database — opportunity-harm")
    print("=" * 60)
    print(f"  Source:   {CFPB_COMPLAINTS_PAGE}")
    print(f"  Output:   {output_dir.resolve()}")
    print(f"  Formats:  {', '.join(args.format)}")
    print(f"  Extract:  {not args.no_extract}")
    print()

    records: list[dict[str, object]] = []
    for fmt in args.format:
        try:
            records.append(
                download_format(
                    fmt,
                    output_dir,
                    dry_run=args.dry_run,
                    extract=not args.no_extract,
                    resume=not args.no_resume,
                    checksum=args.checksum,
                )
            )
        except Exception as exc:
            print(f"  [ERROR] {fmt}: {exc}", file=sys.stderr)
            raise

    if not args.dry_run:
        write_source_manifest(output_dir, records)

    print(f"\n{'=' * 60}")
    print("SUMMARY — CFPB complaints")
    print(f"{'=' * 60}")
    for rec in records:
        print(f"  {rec['format']}: {human_size(int(rec.get('zip_bytes', 0)))}")
        for p in rec.get("extracted_paths") or []:
            print(f"    -> {p}")
    print(f"  Manifest: {output_dir / 'SOURCE.txt'}")


if __name__ == "__main__":
    main()
