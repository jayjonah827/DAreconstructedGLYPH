#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVENTS_RAW = ROOT / "events_raw"
RAW_LEDGER = EVENTS_RAW / "raw_capture.jsonl"
SEGMENT_LEDGER = EVENTS_RAW / "segmented_events.jsonl"
RAW_SCHEMA_VERSION = "raw_event_schema_v1"
BRANCH_SCHEMA_VERSION = "branch_authority_schema_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_source_bytes(args: argparse.Namespace) -> bytes:
    if args.input_file:
        return Path(args.input_file).read_bytes()
    if args.raw_text is not None:
        return args.raw_text.encode("utf-8")
    return sys.stdin.buffer.read()


def decode_raw(raw_bytes: bytes) -> tuple[str | None, str | None]:
    try:
        return raw_bytes.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, base64.b64encode(raw_bytes).decode("ascii")


def make_raw_record(args: argparse.Namespace, raw_bytes: bytes) -> dict:
    raw_text, raw_b64 = decode_raw(raw_bytes)
    record = {
        "record_id": f"raw_{uuid.uuid4().hex}",
        "source_id": args.source_id,
        "speaker": args.speaker,
        "branch": args.branch,
        "event_kind": args.event_kind,
        "raw": raw_text,
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "raw_byte_count": len(raw_bytes),
        "timestamp": utc_now(),
        "authority_level": args.authority_level,
        "status": "observed",
        "action": "preserve_raw_before_segmentation",
        "schema_version": RAW_SCHEMA_VERSION,
    }
    if raw_b64 is not None:
        record["raw_bytes_base64"] = raw_b64
        record["raw_encoding"] = "bytes_base64"
    else:
        record["raw_encoding"] = "utf-8"
    return record


def derive_line_segments(raw_record: dict, raw_text: str) -> list[dict]:
    records = []
    for index, line in enumerate(raw_text.splitlines(), start=1):
        if line == "":
            continue
        records.append(
            {
                "record_id": f"seg_{uuid.uuid4().hex}",
                "source_id": raw_record["source_id"],
                "speaker": raw_record["speaker"],
                "branch": "derived_segment",
                "event_kind": "line_segment",
                "raw": line,
                "normalized": None,
                "glyph_tags": ["derived_from_raw_capture"],
                "relation_to": [raw_record["record_id"]],
                "authority_level": "representation",
                "status": "observed",
                "action": "preserve_derived_segment_without_changing_raw",
                "timestamp": utc_now(),
                "schema_version": BRANCH_SCHEMA_VERSION,
                "segment_index": index,
            }
        )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append raw source captures before any interpretation or computation.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--speaker", default="user")
    parser.add_argument(
        "--branch",
        default="observed",
        choices=["observed", "transcript", "model_output", "metadata", "glyph_identity", "absence", "action", "raw_source_capture"],
    )
    parser.add_argument("--event-kind", default="raw_source_capture")
    parser.add_argument("--authority-level", default="source")
    parser.add_argument("--input-file")
    parser.add_argument("--raw-text")
    parser.add_argument("--segment-lines", action="store_true", help="Create derived line records linked to the raw capture.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_bytes = read_source_bytes(args)
    raw_record = make_raw_record(args, raw_bytes)
    append_jsonl(RAW_LEDGER, raw_record)

    segment_count = 0
    if args.segment_lines:
        if raw_record["raw"] is None:
            print("SKIP segmentation: raw source is not UTF-8 text", file=sys.stderr)
        else:
            for segment in derive_line_segments(raw_record, raw_record["raw"]):
                append_jsonl(SEGMENT_LEDGER, segment)
                segment_count += 1

    print(f"RAW_CAPTURED record_id={raw_record['record_id']} bytes={raw_record['raw_byte_count']} segments={segment_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
