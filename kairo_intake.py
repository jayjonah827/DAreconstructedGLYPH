"""KairoGLYPH — intake + content API (additive).

A FastAPI APIRouter wired to the Render PostgreSQL database. It adds:

  POST /api/intake            the universal intake "door" — preserve raw,
                              compute a glyph_event if x/y are present,
                              otherwise record an absence
  GET  /api/events            recent glyph_events (optional ?domain=)
  GET  /api/absences          recent absence_records
  GET  /api/content/{route}   editable site text for a route
  PUT  /api/content/{id}      edit a content row (token-gated)
  POST /api/subscribe         create a subscriber
  GET  /api/db/health         database connectivity + table counts

It does not touch the GLYPH engine. The constraint math
(R = x / (x + y^2), zone classification) is reused from
glyph_constraint — not reimplemented. server.py mounts this router
via app.include_router(); if anything here fails to load, the server
still boots (see the try/except in server.py).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["kairo"])

SCHEMA_VERSION = "v1"
MAPPING_RULE_VERSION = "kairo_intake_v1"
ALLOWED_BRANCHES = {
    "observed", "transcript", "model_output", "metadata",
    "glyph_identity", "absence", "action", "raw_source_capture",
}


# ---- helpers --------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _connect():
    """Open a psycopg connection, retrying transient connection
    failures (remote Postgres can briefly refuse a fresh connection).
    psycopg is imported lazily so this module never breaks server
    import when the driver or DATABASE_URL is absent."""
    import time

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    import psycopg  # lazy

    last_error = None
    for attempt in range(3):
        try:
            return psycopg.connect(url, connect_timeout=15)
        except psycopg.OperationalError as exc:  # transient: retry
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise last_error


def _compute(x: float, y: float) -> tuple[float, str]:
    """Return (R, zone). Reuses glyph_constraint; falls back to the
    documented formula + thresholds if the import is unavailable."""
    try:
        from glyph_constraint import (
            Partitions, classify_zone, compute_structural_constraint_ratio,
        )
        r = float(compute_structural_constraint_ratio(Partitions(x, y)))
        return r, str(classify_zone(r))
    except ImportError:
        denom = x + (y * y)
        if denom <= 0:
            raise ValueError("x + y^2 must be greater than zero")
        r = x / denom
        zone = "SUBORDINATED" if r < 0.33 else ("STRUCTURAL" if r <= 0.50 else "DOMINANT")
        return r, zone


def _append_ledger(cur, ref_type: str, ref_id: str) -> str:
    """Append one tamper-evident ledger entry, chained to the prior hash."""
    cur.execute("SELECT entry_hash FROM ledger_entry ORDER BY seq DESC LIMIT 1")
    row = cur.fetchone()
    prev_hash = row[0] if row else None
    payload = f"{prev_hash or ''}|{ref_type}|{ref_id}|{_utc_now().isoformat()}"
    entry_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    cur.execute(
        "INSERT INTO ledger_entry (entry_hash, prev_hash, ref_type, ref_id) "
        "VALUES (%s, %s, %s, %s)",
        (entry_hash, prev_hash, ref_type, ref_id),
    )
    return entry_hash


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---- the chain : raw -> (glyph_event | absence) ---------------------

def process_intake(body: dict, conn) -> dict:
    """Core intake chain. Writes a raw_event always; then a glyph_event
    if x and y are present, else an absence_record. Appends a ledger
    entry per record. Uses the given connection; does NOT commit —
    the caller owns the transaction."""
    now = _utc_now()
    raw_text = json.dumps(body, ensure_ascii=False, sort_keys=True)
    raw_bytes = raw_text.encode("utf-8")

    branch = body.get("branch") if body.get("branch") in ALLOWED_BRANCHES else "observed"
    raw_id = _new_id("rev")

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO raw_event
               (record_id, source_id, speaker, branch, event_kind, raw,
                raw_sha256, raw_byte_count, authority_level, status, action,
                schema_version, event_timestamp)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                raw_id,
                str(body.get("source") or "api_intake"),
                str(body.get("speaker") or "anonymous"),
                branch,
                str(body.get("event_kind") or "intake"),
                raw_text,
                hashlib.sha256(raw_bytes).hexdigest(),
                len(raw_bytes),
                str(body.get("authority_level") or "observer"),
                "captured",
                "created",
                SCHEMA_VERSION,
                now,
            ),
        )
        _append_ledger(cur, "raw_event", raw_id)

        result: dict[str, Any] = {
            "raw_event": raw_id,
            "glyph_event": None,
            "absence": None,
        }

        x, y = _num(body.get("x")), _num(body.get("y"))
        if x is not None and y is not None:
            try:
                r_value, zone = _compute(x, y)
            except ValueError as exc:
                abs_id = _new_id("abs")
                cur.execute(
                    """INSERT INTO absence_record
                       (record_id, source_id, branch, event_kind, source_path,
                        observed_state, meaning, next_action, status,
                        schema_version, event_timestamp)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (abs_id, raw_id, "absence", "computation_failed", "api_intake",
                     "unsupported_operation", f"Ratio undefined: {exc}",
                     "Submit x and y such that x + y^2 > 0.", "recorded",
                     SCHEMA_VERSION, now),
                )
                _append_ledger(cur, "absence_record", abs_id)
                result["absence"] = abs_id
                return result

            gev_id = _new_id("gev")
            cur.execute(
                """INSERT INTO glyph_event
                   (record_id, raw_event_id, domain, x, y, r_value, zone,
                    input_values, thresholds, mapping_rule_version,
                    output_produced, provenance, schema_version, event_timestamp)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,%s,%s)""",
                (
                    gev_id, raw_id,
                    str(body.get("domain") or "unsorted"),
                    x, y, r_value, zone,
                    json.dumps({"x": x, "y": y}),
                    json.dumps({"lower": 0.33, "upper": 0.50, "reference": 0.39}),
                    MAPPING_RULE_VERSION,
                    "computed",
                    json.dumps({"raw_event_id": raw_id, "source": body.get("source")}),
                    SCHEMA_VERSION, now,
                ),
            )
            _append_ledger(cur, "glyph_event", gev_id)
            result["glyph_event"] = {
                "record_id": gev_id, "domain": str(body.get("domain") or "unsorted"),
                "x": x, "y": y, "r_value": r_value, "zone": zone,
            }
            return result

        # No x/y — cannot compute. Absence is a record, not nothing.
        abs_id = _new_id("abs")
        cur.execute(
            """INSERT INTO absence_record
               (record_id, source_id, branch, event_kind, source_path,
                observed_state, meaning, next_action, status,
                schema_version, event_timestamp)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (abs_id, raw_id, "absence", "computation_deferred", "api_intake",
             "not_available",
             "Raw event captured but x and y were not provided; the structural "
             "ratio is not yet computable.",
             "Provide x and y, or let a mapping agent decompose the raw event.",
             "recorded", SCHEMA_VERSION, now),
        )
        _append_ledger(cur, "absence_record", abs_id)
        result["absence"] = abs_id
        return result


# ---- routes ---------------------------------------------------------

@router.post("/intake")
async def intake(request: Request):
    """Universal intake. Accepts any JSON object, JSON scalar/array, or
    plain text. Always records the raw event; computes a glyph_event
    when x and y are present, otherwise records an absence."""
    raw = (await request.body()).decode("utf-8", errors="replace")
    try:
        body = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        body = {"text": raw}
    if not isinstance(body, dict):
        body = {"value": body}
    try:
        with _connect() as conn:
            result = process_intake(body, conn)
        return {"status": "accepted", **result}
    except Exception as exc:  # transport / db failure — a real error
        return JSONResponse(status_code=503,
                            content={"status": "error", "detail": str(exc)})


@router.get("/events")
def list_events(domain: str | None = None, limit: int = 50):
    limit = max(1, min(limit, 500))
    from psycopg.rows import dict_row
    try:
        with _connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            if domain:
                cur.execute(
                    "SELECT record_id, domain, x, y, r_value, zone, "
                    "output_produced, event_timestamp FROM glyph_event "
                    "WHERE domain = %s ORDER BY event_timestamp DESC LIMIT %s",
                    (domain, limit))
            else:
                cur.execute(
                    "SELECT record_id, domain, x, y, r_value, zone, "
                    "output_produced, event_timestamp FROM glyph_event "
                    "ORDER BY event_timestamp DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
        return {"count": len(rows), "events": rows}
    except Exception as exc:
        return JSONResponse(status_code=503,
                            content={"error": str(exc), "events": []})


@router.get("/absences")
def list_absences(limit: int = 50):
    limit = max(1, min(limit, 500))
    from psycopg.rows import dict_row
    try:
        with _connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT record_id, source_id, observed_state, meaning, "
                "next_action, status, event_timestamp FROM absence_record "
                "ORDER BY recorded_at DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
        return {"count": len(rows), "absences": rows}
    except Exception as exc:
        return JSONResponse(status_code=503,
                            content={"error": str(exc), "absences": []})


@router.get("/content/{route}")
def get_content(route: str):
    from psycopg.rows import dict_row
    try:
        with _connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, route, section, title, body, position, status, "
                "updated_at FROM content WHERE route = %s ORDER BY position",
                (route,))
            rows = cur.fetchall()
        return {"route": route, "count": len(rows), "sections": rows}
    except Exception as exc:
        return JSONResponse(status_code=503,
                            content={"error": str(exc), "sections": []})


@router.put("/content/{section_id}")
def edit_content(section_id: str, payload: dict,
                 x_edit_token: str | None = Header(default=None)):
    """Edit a content row — the text-editing write path. Gated by the
    KAIRO_EDIT_TOKEN env var: if it is not set, editing is disabled."""
    expected = os.environ.get("KAIRO_EDIT_TOKEN")
    if not expected:
        return JSONResponse(status_code=503, content={
            "error": "editing not configured — set KAIRO_EDIT_TOKEN"})
    if x_edit_token != expected:
        return JSONResponse(status_code=403, content={"error": "invalid edit token"})
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE content SET title = COALESCE(%s, title), "
                "body = COALESCE(%s, body), status = COALESCE(%s, status), "
                "updated_at = now(), updated_by = %s WHERE id = %s",
                (payload.get("title"), payload.get("body"),
                 payload.get("status"), payload.get("updated_by") or "editor",
                 section_id))
            updated = cur.rowcount
        if not updated:
            return JSONResponse(status_code=404, content={"error": "section not found"})
        return {"status": "updated", "id": section_id}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})


@router.post("/subscribe")
def subscribe(payload: dict):
    email = str(payload.get("email") or "").strip().lower()
    if "@" not in email or len(email) < 5:
        return JSONResponse(status_code=400, content={"error": "valid email required"})
    slug = "u_" + hashlib.sha256(email.encode("utf-8")).hexdigest()[:10]
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO subscriber (email, display_name, dashboard_slug) "
                "VALUES (%s, %s, %s) ON CONFLICT (email) DO UPDATE "
                "SET display_name = COALESCE(EXCLUDED.display_name, subscriber.display_name) "
                "RETURNING dashboard_slug, status",
                (email, payload.get("display_name"), slug))
            slug_out, status = cur.fetchone()
        return {"status": "subscribed", "dashboard_slug": slug_out,
                "subscriber_status": status, "dashboard_path": f"/dashboard/{slug_out}"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})


@router.get("/db/health")
def db_health():
    try:
        counts = {}
        with _connect() as conn, conn.cursor() as cur:
            for table in ("raw_event", "glyph_event", "absence_record",
                          "ledger_entry", "content", "subscriber"):
                cur.execute(f"SELECT count(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
        return {"status": "ok", "database": "connected", "counts": counts}
    except Exception as exc:
        return JSONResponse(status_code=503, content={
            "status": "error", "database": "unreachable", "detail": str(exc)})
