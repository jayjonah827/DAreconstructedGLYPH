# Glyph App Assembly Runbook

## Entry Point

- Runtime entry: `server.py`
- Web root: `index.html`

## Layer Endpoints

- Glyph Engine: `POST /api/compute`
- Cultural Compass: `POST /api/compass`
- Hieroglyph Archive: `GET /api/archive`
- Artifact Generation: `POST /api/artifact`
- Community Survey Ingestion: `POST /api/ingest-survey`
- Cross-Domain Convergence Tracking: `GET /api/convergence`
- Full tool pass: `POST /api/run-full-tool`

## Event Schema

- Stored schema file: `event_schema_v1.json`
- Persisted records directory: `events/`

## Local Run

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

## Render Run

- Config file: `render.yaml`
- Glyph App (web): `uvicorn server:app --host 0.0.0.0 --port $PORT`
- Glyph Workflows (worker): `npm start` (root: `workflows-demo/`)

## Workflows (Render Workflows)

- Source: `workflows-demo/src/main.ts`
- Tasks: `calculateSquare`, `processClaim`
- Local dev: `cd workflows-demo && render workflows dev -- npm start`
- Local test: `render workflows tasks start calculateSquare --local --input='[5]'`

## Existing Pages Assembled

- `index.html`
- `docs_index.html`
- `research.html`
- `filing.html`
- `scholarship.html`

