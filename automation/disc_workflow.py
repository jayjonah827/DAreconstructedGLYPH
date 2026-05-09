#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVENTS_RAW = ROOT / "events_raw"
SEGMENT_LEDGER = EVENTS_RAW / "segmented_events.jsonl"
ABSENCE_LEDGER = EVENTS_RAW / "absence_records.jsonl"
REPORT_DIR = ROOT / "reports" / "disc"
BRANCH_SCHEMA_VERSION = "branch_authority_schema_v1"
ABSENCE_SCHEMA_VERSION = "absence_record_schema_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def stable_source_id(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return f"disc_{digest}"


def sha256_file(path: Path, *, limit_bytes: int | None = None) -> tuple[str | None, int, str | None]:
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if limit_bytes is not None and total > limit_bytes:
                    return None, total, "hash_limit_exceeded"
                digest.update(chunk)
    except OSError as exc:
        return None, total, f"{exc.__class__.__name__}: {exc}"
    return digest.hexdigest(), total, None


def classify_cloud_placeholder(path: Path, size: int | None) -> bool:
    suffix = path.suffix.lower()
    if suffix in {".icloud", ".cloud", ".download"}:
        return True
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode) and size == 0 and "Mobile Documents" in str(path)


def branch_record(
    *,
    source_id: str,
    branch: str,
    event_kind: str,
    raw: str,
    glyph_tags: list[str],
    payload: dict[str, Any],
    relation_to: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "record_id": f"discseg_{uuid.uuid4().hex}",
        "source_id": source_id,
        "speaker": "disc_workflow",
        "branch": branch,
        "event_kind": event_kind,
        "raw": raw,
        "normalized": None,
        "glyph_tags": glyph_tags,
        "relation_to": relation_to or [],
        "authority_level": "source_observation",
        "status": "observed",
        "action": "record_only_no_source_mutation",
        "timestamp": utc_now(),
        "schema_version": BRANCH_SCHEMA_VERSION,
        "disc": payload,
    }


def absence_record(
    *,
    source_id: str,
    source_path: str,
    observed_state: str,
    meaning: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "record_id": f"discabs_{uuid.uuid4().hex}",
        "source_id": source_id,
        "branch": "absence",
        "event_kind": "disc_absence",
        "source_path": source_path,
        "observed_state": observed_state,
        "meaning": meaning,
        "next_action": next_action,
        "timestamp": utc_now(),
        "status": "observed",
        "schema_version": ABSENCE_SCHEMA_VERSION,
    }


def iter_paths(source: Path) -> list[Path]:
    if not source.exists():
        return [source]
    if source.is_file() or source.is_symlink():
        return [source]
    paths = [source]
    for current, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "__pycache__"})
        base = Path(current)
        for dirname in dirs:
            paths.append(base / dirname)
        for filename in sorted(files):
            paths.append(base / filename)
    return paths


def scan_path(path: Path, *, source_root: Path, hash_limit_bytes: int | None) -> list[dict[str, Any]]:
    source_id = stable_source_id(path)
    if not path.exists() and not path.is_symlink():
        return [
            absence_record(
                source_id=source_id,
                source_path=str(path),
                observed_state="missing",
                meaning="DISC source path is missing",
                next_action="confirm source path or provide mounted/cloud-local bytes",
            )
        ]

    try:
        lstat = path.lstat()
    except OSError as exc:
        return [
            absence_record(
                source_id=source_id,
                source_path=str(path),
                observed_state="unreadable",
                meaning=f"DISC could not stat source path: {exc}",
                next_action="inspect permissions or cloud placeholder state",
            )
        ]

    rel = str(path)
    try:
        rel = str(path.relative_to(source_root))
    except ValueError:
        pass

    payload: dict[str, Any] = {
        "source_path": str(path),
        "relative_path": rel,
        "is_dir": path.is_dir(),
        "is_file": path.is_file(),
        "is_symlink": path.is_symlink(),
        "size": lstat.st_size,
        "mode": oct(lstat.st_mode),
        "mtime_ns": lstat.st_mtime_ns,
    }

    records: list[dict[str, Any]] = []
    if path.is_symlink():
        payload["symlink_target"] = os.readlink(path)
        records.append(
            branch_record(
                source_id=source_id,
                branch="metadata_branch",
                event_kind="disc_symlink_observed",
                raw=str(path),
                glyph_tags=["DISC", "metadata_branch", "symlink"],
                payload=payload,
            )
        )
        return records

    if classify_cloud_placeholder(path, lstat.st_size):
        records.append(
            absence_record(
                source_id=source_id,
                source_path=str(path),
                observed_state="cloud_placeholder_only",
                meaning="DISC observed metadata without usable local source bytes",
                next_action="hydrate cloud file before content-level intake",
            )
        )
        return records

    if path.is_file():
        file_hash, byte_count, error = sha256_file(path, limit_bytes=hash_limit_bytes)
        payload["sha256"] = file_hash
        payload["byte_count_read"] = byte_count
        if error:
            payload["hash_error"] = error
            records.append(
                branch_record(
                    source_id=source_id,
                    branch="metadata_branch",
                    event_kind="disc_file_metadata_observed",
                    raw=str(path),
                    glyph_tags=["DISC", "metadata_branch", "hash_not_complete"],
                    payload=payload,
                )
            )
        else:
            records.append(
                branch_record(
                    source_id=source_id,
                    branch="observed_file",
                    event_kind="disc_file_observed",
                    raw=str(path),
                    glyph_tags=["DISC", "observed_file", "sha256"],
                    payload=payload,
                )
            )
        return records

    records.append(
        branch_record(
            source_id=source_id,
            branch="observed_file",
            event_kind="disc_directory_observed",
            raw=str(path),
            glyph_tags=["DISC", "observed_directory"],
            payload=payload,
        )
    )
    return records


def duplicate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hash: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        file_hash = (record.get("disc") or {}).get("sha256")
        if file_hash:
            by_hash.setdefault(file_hash, []).append(record)

    out: list[dict[str, Any]] = []
    for file_hash, group in by_hash.items():
        if len(group) < 2:
            continue
        source_paths = [(item.get("disc") or {}).get("source_path") for item in group]
        for item in group:
            out.append(
                branch_record(
                    source_id=item["source_id"],
                    branch="duplicate_candidate",
                    event_kind="disc_duplicate_candidate",
                    raw=str((item.get("disc") or {}).get("source_path")),
                    glyph_tags=["DISC", "duplicate_candidate", "no_delete_authority"],
                    relation_to=[entry["record_id"] for entry in group],
                    payload={
                        "sha256": file_hash,
                        "candidate_paths": source_paths,
                        "rule": "same_sha256",
                        "source_mutation_allowed": False,
                    },
                )
            )
    return out


def write_report(source: Path, records: list[dict[str, Any]]) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    source_digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:10]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"disc_report_{timestamp}_{source_digest}.json"
    counts: dict[str, int] = {}
    for record in records:
        key = str(record.get("branch") or record.get("observed_state") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    report = {
        "schema": "disc_report_v1",
        "source": str(source),
        "generated_at": utc_now(),
        "record_count": len(records),
        "counts": counts,
        "ledgers": {
            "segmented_events": str(SEGMENT_LEDGER.relative_to(ROOT)),
            "absence_records": str(ABSENCE_LEDGER.relative_to(ROOT)),
        },
        "source_mutation_allowed": False,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only DISC file intake: discover, ingest, separate, commit/report.")
    parser.add_argument("source", help="File or folder to scan. The source is never deleted, moved, renamed, or overwritten.")
    parser.add_argument("--hash-limit-mb", type=int, default=256, help="Skip full hashing for files larger than this size.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    hash_limit = args.hash_limit_mb * 1024 * 1024 if args.hash_limit_mb > 0 else None
    records: list[dict[str, Any]] = []
    for path in iter_paths(source):
        records.extend(scan_path(path, source_root=source if source.is_dir() else source.parent, hash_limit_bytes=hash_limit))
    records.extend(duplicate_records(records))

    for record in records:
        if record.get("branch") == "absence":
            append_jsonl(ABSENCE_LEDGER, record)
        else:
            append_jsonl(SEGMENT_LEDGER, record)

    report_path = write_report(source, records)
    print(f"DISC_RECORDED source={source} records={len(records)} report={report_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
