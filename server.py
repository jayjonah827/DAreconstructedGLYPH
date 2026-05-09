from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from glyph_constraint import (
    DOMINANT,
    LOWER_THRESHOLD,
    REFERENCE_POINT,
    SCHEMA_VERSION,
    STRUCTURAL,
    SUBORDINATED,
    UPPER_THRESHOLD,
    Partitions,
    classify_zone,
    compute_structural_constraint_ratio,
)

BASE = Path(__file__).parent
EVENTS_DIR = BASE / "events"
EVENTS_DIR.mkdir(exist_ok=True)
EVENTS_RAW_DIR = BASE / "events_raw"
HANDOFF_STATUS_PATH = BASE / "reports" / "cloud_handoff" / "glyph_voice_status.json"

app = FastAPI(
    title="Glyph Assembly API",
    description="Event-first structural constraint engine",
    version="1.0.0",
)

if (BASE / "static").is_dir():
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_clock_config() -> dict[str, Any]:
    clock_path = BASE / "site" / "clock.json"
    if not clock_path.exists():
        raise HTTPException(status_code=404, detail="site/clock.json not found")
    return json.loads(clock_path.read_text(encoding="utf-8"))


def _jsonl_count(path: Path) -> int | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return None


def _safe_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _active_source_layers() -> dict[str, Any]:
    layers = [
        ("canonical_ssd_repo", BASE),
        ("operator_contract", BASE / "glyph_operator_contract.md"),
        ("workspace_policy", BASE / "GLYPH_WORKSPACE_POLICY.json"),
        ("heart", BASE / "python_engine" / "glyph_heart.py"),
        ("voice", BASE / "python_engine" / "glyph_voice.py"),
        ("terminal_bridge", BASE / "python_engine" / "glyph_terminal.py"),
        ("disc_workflow", BASE / "automation" / "disc_workflow.py"),
        ("controller", BASE / "controller" / "main.py"),
        ("handoff_status", HANDOFF_STATUS_PATH),
        ("heyer_livin_site_bundle", BASE / "heyer-livin-site" / "index.html"),
        ("deploy_server", BASE / "server.py"),
        ("render_blueprint", BASE / "render.yaml"),
        ("ai_book_ledger", BASE / "docs" / "ai_book" / "ledger_event.json"),
    ]
    active = [name for name, path in layers if path.exists()]
    missing = [name for name, path in layers if not path.exists()]
    return {
        "schema": "glyph_source_layers_v1",
        "generated_at": _utc_now_iso(),
        "active": active,
        "missing": missing,
        "ledger_counts": {
            "raw_capture": _jsonl_count(EVENTS_RAW_DIR / "raw_capture.jsonl"),
            "segmented_events": _jsonl_count(EVENTS_RAW_DIR / "segmented_events.jsonl"),
            "absence_records": _jsonl_count(EVENTS_RAW_DIR / "absence_records.jsonl"),
            "disc_reports": len(list((BASE / "reports" / "disc").glob("disc_report_*.json")))
            if (BASE / "reports" / "disc").is_dir()
            else 0,
        },
        "source_authority": "ssd_repo_and_raw_ledgers",
        "render_role": "public_output_surface",
        "source_mutation_allowed": False,
        "raw_payload_exported": False,
        "full_raw_archive_export": False,
    }


def _build_unified_event(*, x: float, y: float, ratio: float, zone: str, domain: str, output: str | None) -> dict[str, Any]:
    return {
        "record_id": f"gev_{uuid.uuid4().hex[:12]}",
        "input_values": {"x": x, "y": y},
        "x": x,
        "y": y,
        "r_value": round(ratio, 6),
        "zone": zone,
        "domain": domain,
        "timestamp": _utc_now_iso(),
        "mapping_rule_version": "mapping_v1_assembled",
        "output_produced": output,
        "thresholds": {
            "lower": LOWER_THRESHOLD,
            "upper": UPPER_THRESHOLD,
            "reference": REFERENCE_POINT,
        },
        "schema_version": SCHEMA_VERSION,
    }


def _persist_event(event: dict[str, Any]) -> None:
    target = EVENTS_DIR / f"{event['record_id']}.json"
    target.write_text(json.dumps(event, indent=2), encoding="utf-8")


def _compute_zone_from_payload(payload: dict[str, Any]) -> tuple[float, float, float, str]:
    try:
        x = float(payload.get("x"))
        y = float(payload.get("y"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="x and y must be numbers")

    if x < 0 or y < 0:
        raise HTTPException(status_code=400, detail="x and y must be non-negative")

    ratio = compute_structural_constraint_ratio(Partitions(x=x, y=y))
    zone = classify_zone(ratio)
    return x, y, ratio, zone


@app.get("/health")
def health_render() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "live",
        "engine": "GLYPH",
        "schema_version": SCHEMA_VERSION,
        "thresholds": {"lower": LOWER_THRESHOLD, "upper": UPPER_THRESHOLD, "reference": REFERENCE_POINT},
    }


@app.post("/api/compute")
async def compute(request: Request) -> dict[str, Any]:
    payload = await request.json()
    x, y, ratio, zone = _compute_zone_from_payload(payload)
    domain = str(payload.get("domain", "general"))
    event = _build_unified_event(x=x, y=y, ratio=ratio, zone=zone, domain=domain, output="compute")
    _persist_event(event)
    return event


@app.post("/api/ingest-survey")
async def ingest_survey(request: Request) -> dict[str, Any]:
    payload = await request.json()
    x, y, ratio, zone = _compute_zone_from_payload(payload)
    domain = str(payload.get("domain", "community"))
    event = _build_unified_event(x=x, y=y, ratio=ratio, zone=zone, domain=domain, output="survey_ingestion")
    _persist_event(event)
    return {"layer": "CommunitySurveyIngestion", "event": event}


@app.post("/api/compass")
async def cultural_compass(request: Request) -> dict[str, Any]:
    payload = await request.json()
    x, y, ratio, zone = _compute_zone_from_payload(payload)
    domain = str(payload.get("domain", "compass"))
    output = "artifact_allowed" if zone in {STRUCTURAL, DOMINANT} else "artifact_blocked"
    event = _build_unified_event(x=x, y=y, ratio=ratio, zone=zone, domain=domain, output=output)
    _persist_event(event)
    return {"layer": "CulturalCompass", "event": event}


@app.post("/api/artifact")
async def artifact_generation(request: Request) -> dict[str, Any]:
    payload = await request.json()
    x, y, ratio, zone = _compute_zone_from_payload(payload)
    domain = str(payload.get("domain", "artifact"))
    if zone == SUBORDINATED:
        output = "artifact_deferred_pending_structural_band"
    elif zone == STRUCTURAL:
        output = "artifact_blueprint"
    else:
        output = "artifact_release_candidate"
    event = _build_unified_event(x=x, y=y, ratio=ratio, zone=zone, domain=domain, output=output)
    _persist_event(event)
    return {"layer": "ArtifactGeneration", "event": event}


@app.get("/api/archive")
def archive() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(EVENTS_DIR.glob("gev_*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    return {"layer": "HieroglyphArchive", "count": len(rows), "events": rows}


@app.get("/api/convergence")
def convergence() -> dict[str, Any]:
    aggregates: dict[str, list[float]] = {}
    for path in EVENTS_DIR.glob("gev_*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        aggregates.setdefault(row.get("domain", "general"), []).append(float(row.get("r_value", 0)))

    summary = []
    for domain, ratios in sorted(aggregates.items()):
        avg = sum(ratios) / len(ratios)
        summary.append(
            {
                "domain": domain,
                "count": len(ratios),
                "avg_r_value": round(avg, 6),
                "distance_to_0_39": round(abs(avg - REFERENCE_POINT), 6),
            }
        )
    return {"layer": "CrossDomainConvergenceTracking", "reference_point": REFERENCE_POINT, "domains": summary}


@app.get("/api/schema")
def schema() -> dict[str, Any]:
    schema_path = BASE / "event_schema_v1.json"
    if not schema_path.exists():
        return {"error": "schema not found"}
    return json.loads(schema_path.read_text(encoding="utf-8"))


@app.get("/api/layers")
def layers() -> dict[str, Any]:
    return {
        "layers": {
            "glyph_engine": "/api/compute",
            "cultural_compass": "/api/compass",
            "hieroglyph_archive": "/api/archive",
            "artifact_generation": "/api/artifact",
            "community_survey_ingestion": "/api/ingest-survey",
            "cross_domain_convergence_tracking": "/api/convergence",
            "orbital_clock": "/api/clock",
            "glyph_source_layers": "/api/glyph/source-layers",
            "glyph_voice_handoff": "/api/glyph/voice-handoff",
            "glyph_local_to_public_bridge": "/api/glyph/bridge",
        }
    }


@app.get("/api/glyph/source-layers")
def glyph_source_layers() -> dict[str, Any]:
    return _active_source_layers()


@app.get("/api/glyph/voice-handoff")
def glyph_voice_handoff() -> dict[str, Any]:
    handoff = _safe_json(HANDOFF_STATUS_PATH)
    if handoff is None:
        return {
            "schema": "glyph_voice_handoff_public_v1",
            "generated_at": _utc_now_iso(),
            "status": "missing",
            "path": str(HANDOFF_STATUS_PATH),
            "source_mutation_allowed": False,
            "raw_payload_exported": False,
            "full_raw_archive_export": False,
        }
    return {
        "schema": "glyph_voice_handoff_public_v1",
        "generated_at": _utc_now_iso(),
        "status": "present",
        "voice_schema": handoff.get("schema"),
        "voice_generated_at": handoff.get("generated_at"),
        "latest_event": handoff.get("latest_event"),
        "event_counts": handoff.get("event_counts", {}),
        "events_kept": handoff.get("events_kept", 0),
        "persisted_event_kinds": handoff.get("persisted_event_kinds", []),
        "source_mutation_allowed": False,
        "raw_payload_exported": False,
        "full_raw_archive_export": False,
    }


@app.get("/api/glyph/bridge")
def glyph_bridge() -> dict[str, Any]:
    return {
        "schema": "glyph_local_to_public_bridge_v1",
        "generated_at": _utc_now_iso(),
        "local_bot": {
            "browser_surface": "http://localhost:8788/",
            "terminal_command": "bin/glyph-chat",
            "service_command": "bin/glyph-service status",
            "cloud_visible_directly": False,
        },
        "public_surfaces": {
            "source_layers": "/api/glyph/source-layers",
            "voice_handoff": "/api/glyph/voice-handoff",
            "health": "/api/health",
            "homepage": "/",
        },
        "boundary": {
            "ssd_reads_raw_sources": True,
            "render_reads_ssd_directly": False,
            "public_api_exports_raw_payloads": False,
            "source_mutation_allowed": False,
        },
        "source_layers": _active_source_layers(),
        "voice_handoff": glyph_voice_handoff(),
    }


@app.get("/api/clock")
def orbital_clock() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    seconds = now.second + (now.microsecond / 1_000_000)
    minutes = now.minute + (seconds / 60)
    hours = (now.hour % 12) + (minutes / 60)
    long_angle = (minutes * 6) - 90
    short_angle = (hours * 30) - 90
    config = _load_clock_config()
    return {
        "schema": "glyph_orbital_clock_state_v1",
        "generated_at": _utc_now_iso(),
        "source": "server",
        "clock": {
            "short_angle_degrees": round(short_angle, 6),
            "long_angle_degrees": round(long_angle, 6),
            "earth_fixed_north": True,
            "short_hand": config.get("clock", {}).get("short_hand", {}),
            "long_hand": config.get("clock", {}).get("long_hand", {}),
        },
        "route_declarations": config.get("route_declarations", []),
        "backend": config.get("backend", {}),
    }


@app.get("/api/terminal-dashboard")
def terminal_dashboard_summary() -> dict[str, Any]:
    event_files = sorted(EVENTS_DIR.glob("gev_*.json"))
    event_rows: list[dict[str, Any]] = []
    for path in event_files:
        event_rows.append(json.loads(path.read_text(encoding="utf-8")))

    domain_counts: dict[str, int] = {}
    for row in event_rows:
        domain = str(row.get("domain", "general"))
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

    data_messages_path = BASE / "data" / "messages.json"
    message_total = 0
    if data_messages_path.exists():
        payload = json.loads(data_messages_path.read_text(encoding="utf-8"))
        message_total = int(payload.get("total", 0))

    return {
        "ui": "TerminalDashboard",
        "entry_point": "/terminal",
        "events_count": len(event_rows),
        "domains": domain_counts,
        "messages_dataset_total": message_total,
        "layers": {
            "glyph_engine": "/api/compute",
            "cultural_compass": "/api/compass",
            "hieroglyph_archive": "/api/archive",
            "artifact_generation": "/api/artifact",
            "community_survey_ingestion": "/api/ingest-survey",
            "cross_domain_convergence_tracking": "/api/convergence",
            "orbital_clock": "/api/clock",
            "glyph_source_layers": "/api/glyph/source-layers",
            "glyph_voice_handoff": "/api/glyph/voice-handoff",
            "glyph_local_to_public_bridge": "/api/glyph/bridge",
        },
    }


@app.post("/api/run-full-tool")
async def run_full_tool(request: Request) -> dict[str, Any]:
    payload = await request.json()
    x, y, ratio, zone = _compute_zone_from_payload(payload)
    domain = str(payload.get("domain", "full_tool"))
    if zone == SUBORDINATED:
        artifact_state = "artifact_deferred_pending_structural_band"
    elif zone == STRUCTURAL:
        artifact_state = "artifact_blueprint"
    else:
        artifact_state = "artifact_release_candidate"
    event = _build_unified_event(x=x, y=y, ratio=ratio, zone=zone, domain=domain, output=artifact_state)
    _persist_event(event)
    return {
        "glyph_engine": {"ratio": round(ratio, 6), "zone": zone},
        "cultural_compass": {"decision": "allow" if zone != SUBORDINATED else "defer"},
        "hieroglyph_archive": {"record_id": event["record_id"]},
        "artifact_generation": {"status": artifact_state},
        "community_survey_ingestion": {"accepted": True, "domain": domain},
        "cross_domain_convergence_tracking": {"reference_point": REFERENCE_POINT},
        "event": event,
    }


@app.get("/terminal", response_class=HTMLResponse)
def terminal_dashboard() -> HTMLResponse:
    terminal_ui = BASE / "docs_index.html"
    if terminal_ui.exists():
        return HTMLResponse(terminal_ui.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Terminal Dashboard</h1><p>docs_index.html not found.</p>", status_code=404)


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    heyer_livin_home = BASE / "heyer-livin-site" / "index.html"
    if heyer_livin_home.exists():
        return HTMLResponse(heyer_livin_home.read_text(encoding="utf-8"))
    launch_page = BASE / "site" / "glyph-launch.html"
    if launch_page.exists():
        return HTMLResponse(launch_page.read_text(encoding="utf-8"))
    dashboard = BASE / "docs_index.html"
    if dashboard.exists():
        return HTMLResponse(dashboard.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Glyph</h1><p>Engine running.</p>")


@app.get("/launch", response_class=HTMLResponse)
def launch() -> HTMLResponse:
    launch_page = BASE / "site" / "glyph-launch.html"
    if launch_page.exists():
        return HTMLResponse(launch_page.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>GLYPH launch page not found.</h1><p>site/glyph-launch.html is missing.</p>", status_code=404)


@app.get("/clock.json")
def clock_json() -> FileResponse:
    clock_path = BASE / "site" / "clock.json"
    if clock_path.exists():
        return FileResponse(clock_path, media_type="application/json")
    raise HTTPException(status_code=404, detail="site/clock.json not found")


@app.get("/simulator", response_class=HTMLResponse)
def simulator() -> HTMLResponse:
    simulator_ui = BASE / "index.html"
    if simulator_ui.exists():
        return HTMLResponse(simulator_ui.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Glyph Simulator</h1><p>index.html not found.</p>", status_code=404)


@app.get("/{filename:path}")
async def static_file(filename: str):
    if filename.startswith("api/"):
        return JSONResponse(status_code=404, content={"error": "not found"})
    filepath = (BASE / filename).resolve()
    if filepath.is_file() and filepath.is_relative_to(BASE.resolve()):
        return FileResponse(filepath)
    return JSONResponse(status_code=404, content={"error": "not found"})
