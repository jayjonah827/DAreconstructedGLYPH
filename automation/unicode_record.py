#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEGMENT_LEDGER = ROOT / "events_raw" / "segmented_events.jsonl"
ABSENCE_LEDGER = ROOT / "events_raw" / "absence_records.jsonl"
BRANCH_SCHEMA_VERSION = "branch_authority_schema_v1"
ABSENCE_SCHEMA_VERSION = "absence_record_schema_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def absence_record(source_id: str, source_path: str, meaning: str, next_action: str) -> dict:
    return {
        "record_id": f"abs_{uuid.uuid4().hex}",
        "source_id": source_id,
        "branch": "absence",
        "event_kind": "unicode_input_absence",
        "source_path": source_path,
        "observed_state": "empty",
        "meaning": meaning,
        "next_action": next_action,
        "timestamp": utc_now(),
        "status": "observed",
        "schema_version": ABSENCE_SCHEMA_VERSION,
    }


def glyph_record(source_id: str, speaker: str, ch: str, index: int) -> dict:
    utf8_bytes = ch.encode("utf-8")
    codepoint = f"U+{ord(ch):04X}"
    return {
        "record_id": f"ugr_{uuid.uuid4().hex}",
        "source_id": source_id,
        "speaker": speaker,
        "branch": "glyph_identity",
        "event_kind": "unicode_glyph_identity",
        "raw": ch,
        "normalized": None,
        "glyph_tags": ["UGR-001", "preserve_codepoint_before_semantic_translation"],
        "relation_to": [],
        "authority_level": "glyph_identity",
        "status": "observed",
        "action": "store_glyph_identity_before_normalization",
        "timestamp": utc_now(),
        "schema_version": BRANCH_SCHEMA_VERSION,
        "glyph_identity": {
            "displayed_glyph": ch,
            "codepoint": codepoint,
            "utf8_bytes": utf8_bytes.hex(" ").upper(),
            "unicode_name": unicodedata.name(ch, "UNKNOWN"),
            "unicode_category": unicodedata.category(ch),
            "ucd_version": unicodedata.unidata_version,
            "normalization_allowed": False,
            "normalized_forms": {
                "NFC": unicodedata.normalize("NFC", ch),
                "NFD": unicodedata.normalize("NFD", ch),
                "NFKC": unicodedata.normalize("NFKC", ch),
                "NFKD": unicodedata.normalize("NFKD", ch),
            },
            "transformation_status": "original_codepoint_preserved",
            "character_index": index,
        },
    }


def read_text(args: argparse.Namespace) -> tuple[str, str]:
    if args.input_file:
        path = Path(args.input_file)
        return path.read_text(encoding="utf-8"), str(path)
    return args.text or "", "direct_text"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record Unicode glyph identity before semantic interpretation or normalization.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--speaker", default="user")
    parser.add_argument("--text")
    parser.add_argument("--input-file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text, source_path = read_text(args)
    if text == "":
        append_jsonl(
            ABSENCE_LEDGER,
            absence_record(
                args.source_id,
                source_path,
                "unicode_record received no glyph input",
                "provide text or input file before recording glyph identity",
            ),
        )
        print("UNICODE_ABSENCE records=1")
        return 0

    count = 0
    for index, ch in enumerate(text, start=1):
        append_jsonl(SEGMENT_LEDGER, glyph_record(args.source_id, args.speaker, ch, index))
        count += 1
    print(f"UNICODE_RECORDED records={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
