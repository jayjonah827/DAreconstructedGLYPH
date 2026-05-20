# KairoGLYPH — Database

PostgreSQL schema for the live KairoGLYPH service (Render Postgres
`ledger_postgres_ymoc`).

## Apply

    psql "$DATABASE_URL" -f db/schema.sql

Idempotent — `CREATE ... IF NOT EXISTS` only, no `DROP`, no destructive
statements. Safe to run repeatedly.

## Tables

| Table | Purpose |
|---|---|
| `raw_event` | Append-only universal intake — mirrors `raw_event_schema_v1.json` |
| `glyph_event` | Structured events, `R = x / (x + y^2)` — mirrors `event_schema_v1.json` |
| `absence_record` | Missing / empty / unreadable as first-class records |
| `ledger_entry` | Append-only, tamper-evident hash chain (replay spine) |
| `content` | Editable site text, route-keyed — replaces the Notion source |
| `subscriber` | Subscription page → personal dashboard |

The three event tables are the existing GLYPH JSON schemas expressed as
durable tables — not a redesign. The engine still owns the schemas.

## Connection

`DATABASE_URL` lives in `.env` (gitignored). Local/dev uses the **External**
URL; the Render web service uses the **Internal** URL. Never commit the
credential.

## Zones

`SUBORDINATED` R < 0.33 · `STRUCTURAL` 0.33 ≤ R ≤ 0.50 · `DOMINANT` R > 0.50
· reference point 0.39.
