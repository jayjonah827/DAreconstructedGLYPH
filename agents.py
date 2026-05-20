"""KairoGLYPH — agentic execution layer (additive).

The blueprint's Authority Hierarchy places agents at level 4: an
*execution surface only*. They run tasks under permission; they do not
own schema, rules, or the ledger-as-authority. Concretely, every agent
here may only **append** (raw_event, glyph_event, absence_record,
ledger_entry) — never delete, never overwrite, never alter schema.

Each agent run is itself recorded as an `action`-branch raw_event plus a
ledger entry, so the system logs its own workers in its own ledger.

Agents
  IngestAgent    pulls a batch of inputs into the intake chain
  MappingAgent   ensures every raw_event has a glyph_event or an absence
  LedgerAgent    verifies the hash chain; appends entries for any record
                 missing one (the ledger writer)
  AnalysisAgent  computes aggregate structure (mean R, zones, domains)

Run them via kairo_agents (the /api/agents routes) or directly:
    from agents import REGISTRY
    print(REGISTRY["analysis_agent"]().run())
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import kairo_intake as ki


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Agent:
    """Base agent. Authority level 4 — execution only, append-only."""

    name = "agent"
    kind = "generic"
    description = "generic agent"
    AUTHORITY = "agent"  # never sets policy, truth, or history

    def _run(self, conn) -> dict[str, Any]:
        raise NotImplementedError

    def run(self) -> dict[str, Any]:
        started = _now()
        with ki._connect() as conn:
            result = self._run(conn)
            run_id = _new_id("rev")
            summary = {
                "agent": self.name,
                "kind": self.kind,
                "started": started.isoformat(),
                "result": result,
            }
            raw = json.dumps(summary, default=str, sort_keys=True)
            raw_bytes = raw.encode("utf-8")
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO raw_event
                       (record_id, source_id, speaker, branch, event_kind, raw,
                        raw_sha256, raw_byte_count, authority_level, status,
                        action, schema_version, event_timestamp)
                       VALUES (%s,%s,%s,'action','agent_run',%s,%s,%s,%s,
                               'recorded','created','v1',%s)""",
                    (run_id, self.name, self.name, raw,
                     hashlib.sha256(raw_bytes).hexdigest(), len(raw_bytes),
                     self.AUTHORITY, started),
                )
                ki._append_ledger(cur, "raw_event", run_id)
        return {"agent": self.name, "kind": self.kind, "run_id": run_id, **result}


class IngestAgent(Agent):
    """Pulls a batch of inputs into the intake chain. Each item is run
    through process_intake — raw preserved, glyph_event or absence
    produced. 'The agent that pulls intake.'"""

    name = "ingest_agent"
    kind = "ingest"
    description = "pulls a batch of inputs into the intake chain"

    def __init__(self, items: list[dict] | None = None) -> None:
        self.items = items or []

    def _run(self, conn) -> dict[str, Any]:
        events, absences = [], []
        for item in self.items:
            if not isinstance(item, dict):
                item = {"value": item}
            res = ki.process_intake(item, conn)
            if res.get("glyph_event"):
                events.append(res["glyph_event"]["record_id"])
            if res.get("absence"):
                absences.append(res["absence"])
        return {
            "items_pulled": len(self.items),
            "glyph_events": events,
            "absences": absences,
        }


class MappingAgent(Agent):
    """Ensures every non-action raw_event has a downstream glyph_event or
    an absence_record. Where neither exists, records the gap as an
    absence — never invents an event."""

    name = "mapping_agent"
    kind = "mapping"
    description = "records an absence for any raw_event with no structural mapping"

    def _run(self, conn) -> dict[str, Any]:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT re.record_id FROM raw_event re
                   WHERE re.branch <> 'action'
                     AND NOT EXISTS (SELECT 1 FROM glyph_event g
                                     WHERE g.raw_event_id = re.record_id)
                     AND NOT EXISTS (SELECT 1 FROM absence_record a
                                     WHERE a.source_id = re.record_id)"""
            )
            unresolved = [r[0] for r in cur.fetchall()]
        recorded = []
        for rid in unresolved:
            abs_id = _new_id("abs")
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO absence_record
                       (record_id, source_id, branch, event_kind, source_path,
                        observed_state, meaning, next_action, status,
                        schema_version, event_timestamp)
                       VALUES (%s,%s,'absence','mapping_gap','raw_event',
                               'not_available',
                               'Raw event has no glyph_event and no absence — '
                               'structural mapping is missing.',
                               'Supply x and y, or confirm it is non-structural.',
                               'recorded','v1',%s)""",
                    (abs_id, rid, _now()),
                )
                ki._append_ledger(cur, "absence_record", abs_id)
            recorded.append(abs_id)
        return {"unresolved_scanned": len(unresolved),
                "absences_recorded": len(recorded)}


class LedgerAgent(Agent):
    """Verifies the append-only hash chain (each entry's prev_hash must
    match the prior entry's hash) and appends a ledger entry for any
    record that lacks one. 'The agent that writes the ledger.'"""

    name = "ledger_agent"
    kind = "ledger"
    description = "verifies the hash chain and appends missing ledger entries"

    def _run(self, conn) -> dict[str, Any]:
        with conn.cursor() as cur:
            cur.execute("SELECT seq, entry_hash, prev_hash FROM ledger_entry "
                        "ORDER BY seq")
            entries = cur.fetchall()
        broken_at, prev = [], None
        for seq, entry_hash, prev_hash in entries:
            if prev_hash != prev:
                broken_at.append(seq)
            prev = entry_hash

        with conn.cursor() as cur:
            cur.execute(
                """SELECT 'raw_event' AS t, record_id FROM raw_event
                   WHERE record_id NOT IN
                     (SELECT ref_id FROM ledger_entry WHERE ref_type='raw_event')
                   UNION ALL
                   SELECT 'glyph_event', record_id FROM glyph_event
                   WHERE record_id NOT IN
                     (SELECT ref_id FROM ledger_entry WHERE ref_type='glyph_event')
                   UNION ALL
                   SELECT 'absence_record', record_id FROM absence_record
                   WHERE record_id NOT IN
                     (SELECT ref_id FROM ledger_entry WHERE ref_type='absence_record')"""
            )
            missing = cur.fetchall()
        appended = []
        with conn.cursor() as cur:
            for ref_type, ref_id in missing:
                ki._append_ledger(cur, ref_type, ref_id)
                appended.append(ref_id)
        return {
            "ledger_entries": len(entries),
            "chain_intact": not broken_at,
            "broken_at": broken_at,
            "missing_entries_appended": len(appended),
        }


class AnalysisAgent(Agent):
    """Computes aggregate structure across glyph_event — overall mean R,
    distance to the 0.39 attractor, per-domain and per-zone breakdowns."""

    name = "analysis_agent"
    kind = "analysis"
    description = "computes mean R, attractor distance, domain and zone splits"

    def _run(self, conn) -> dict[str, Any]:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT count(*) AS n, avg(r_value) AS mean_r, "
                        "stddev_pop(r_value) AS sd FROM glyph_event")
            agg = cur.fetchone()
            cur.execute("SELECT domain, count(*) AS n, "
                        "round(avg(r_value)::numeric, 4) AS mean_r "
                        "FROM glyph_event GROUP BY domain ORDER BY n DESC")
            by_domain = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT zone, count(*) AS n FROM glyph_event "
                        "GROUP BY zone ORDER BY n DESC")
            by_zone = [dict(r) for r in cur.fetchall()]
        mean_r = float(agg["mean_r"]) if agg["mean_r"] is not None else None
        sd = float(agg["sd"]) if agg["sd"] is not None else None
        return {
            "event_count": agg["n"],
            "mean_r": round(mean_r, 6) if mean_r is not None else None,
            "sd": round(sd, 6) if sd is not None else None,
            "distance_to_attractor": (round(abs(mean_r - 0.39), 6)
                                      if mean_r is not None else None),
            "by_domain": by_domain,
            "by_zone": by_zone,
        }


REGISTRY: dict[str, type[Agent]] = {
    IngestAgent.name: IngestAgent,
    MappingAgent.name: MappingAgent,
    LedgerAgent.name: LedgerAgent,
    AnalysisAgent.name: AnalysisAgent,
}


def catalog() -> list[dict[str, str]]:
    return [{"name": cls.name, "kind": cls.kind, "description": cls.description}
            for cls in REGISTRY.values()]
