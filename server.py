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

app = FastAPI(
    title="Glyph Assembly API",
    description="Event-first structural constraint engine",
    version="1.0.0",
)

if (BASE / "static").is_dir():
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
        }
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


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    index = BASE / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Glyph</h1><p>Engine running.</p>")


@app.get("/{filename:path}")
async def static_file(filename: str):
    if filename.startswith("api/"):
        return JSONResponse(status_code=404, content={"error": "not found"})
    filepath = (BASE / filename).resolve()
    if filepath.is_file() and filepath.is_relative_to(BASE.resolve()):
        return FileResponse(filepath)
    return JSONResponse(status_code=404, content={"error": "not found"})
