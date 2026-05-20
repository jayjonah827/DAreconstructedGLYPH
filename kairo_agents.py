"""KairoGLYPH — agent execution routes (additive).

Exposes the agentic execution layer over HTTP:

  GET  /api/agents              list the available agents
  POST /api/agents/run/{name}   run one agent (ingest_agent takes a JSON
                                body {"items": [...]}; others take none)
  GET  /api/agents/runs         recent agent runs from the ledger

Agents are append-only execution surfaces — see agents.py. server.py
mounts this router; a failure to load can never stop the server booting.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import agents
import kairo_intake as ki

router = APIRouter(prefix="/api", tags=["kairo-agents"])


@router.get("/agents")
def list_agents():
    return {"count": len(agents.REGISTRY), "agents": agents.catalog()}


@router.post("/agents/run/{name}")
async def run_agent(name: str, request: Request):
    cls = agents.REGISTRY.get(name)
    if cls is None:
        return JSONResponse(status_code=404,
                            content={"error": f"unknown agent: {name}"})
    try:
        if name == "ingest_agent":
            try:
                body = await request.json()
            except Exception:
                body = {}
            items = body.get("items", []) if isinstance(body, dict) else []
            agent = cls(items)
        else:
            agent = cls()
        return {"status": "ran", **agent.run()}
    except Exception as exc:
        return JSONResponse(status_code=503, content={
            "status": "error", "agent": name, "detail": str(exc)})


@router.get("/agents/runs")
def recent_runs(limit: int = 20):
    limit = max(1, min(limit, 200))
    from psycopg.rows import dict_row
    try:
        with ki._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT record_id, source_id AS agent, event_timestamp, raw "
                "FROM raw_event WHERE event_kind = 'agent_run' "
                "ORDER BY event_timestamp DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
        return {"count": len(rows), "runs": rows}
    except Exception as exc:
        return JSONResponse(status_code=503,
                            content={"error": str(exc), "runs": []})
