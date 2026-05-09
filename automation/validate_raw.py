#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATION_TARGETS = [
    ("raw_event_schema_v1.json", "events_raw/raw_capture.jsonl"),
    ("branch_authority_schema_v1.json", "events_raw/segmented_events.jsonl"),
    ("absence_record_schema_v1.json", "events_raw/absence_records.jsonl"),
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def type_matches(value: Any, expected: str | list[str]) -> bool:
    options = expected if isinstance(expected, list) else [expected]
    for option in options:
        if option == "str" and isinstance(value, str):
            return True
        if option == "int" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if option == "float" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if option == "bool" and isinstance(value, bool):
            return True
        if option == "list" and isinstance(value, list):
            return True
        if option == "dict" and isinstance(value, dict):
            return True
        if option == "null" and value is None:
            return True
    return False


def validate_record(record: dict[str, Any], schema: dict[str, Any], label: str, line_number: int) -> list[str]:
    errors = []
    for field in schema.get("required_fields", []):
        if field not in record:
            errors.append(f"{label}:{line_number}: missing required field {field}")

    field_types = schema.get("field_types", {})
    for field, expected in field_types.items():
        if field in record and not type_matches(record[field], expected):
            errors.append(f"{label}:{line_number}: field {field} has invalid type")

    if "allowed_branches" in schema and "branch" in record:
        if record["branch"] not in schema["allowed_branches"]:
            errors.append(f"{label}:{line_number}: branch {record['branch']} not allowed")

    if "allowed_observed_states" in schema and "observed_state" in record:
        if record["observed_state"] not in schema["allowed_observed_states"]:
            errors.append(f"{label}:{line_number}: observed_state {record['observed_state']} not allowed")

    return errors


def validate_jsonl(schema_path: Path, ledger_path: Path) -> tuple[int, list[str]]:
    schema = load_json(schema_path)
    if not ledger_path.exists():
        return 0, [f"{ledger_path}: missing ledger file"]

    count = 0
    errors: list[str] = []
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip() == "":
                errors.append(f"{ledger_path}:{line_number}: blank line is not valid JSONL")
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{ledger_path}:{line_number}: invalid JSON: {exc.msg}")
                continue
            if not isinstance(record, dict):
                errors.append(f"{ledger_path}:{line_number}: JSONL record must be an object")
                continue
            count += 1
            errors.extend(validate_record(record, schema, str(ledger_path), line_number))
    return count, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate raw-first JSONL ledgers against repo-local schemas.")
    parser.add_argument("--root", default=str(ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    all_errors: list[str] = []

    for schema_name, ledger_name in VALIDATION_TARGETS:
        schema_path = root / schema_name
        ledger_path = root / ledger_name
        if not schema_path.exists():
            all_errors.append(f"{schema_path}: missing schema file")
            continue
        count, errors = validate_jsonl(schema_path, ledger_path)
        if errors:
            print(f"FAIL {ledger_name} records={count}")
            all_errors.extend(errors)
        else:
            print(f"PASS {ledger_name} records={count}")

    if all_errors:
        for error in all_errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
