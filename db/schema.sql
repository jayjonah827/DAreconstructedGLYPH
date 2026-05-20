-- ============================================================
-- KairoGLYPH — PostgreSQL schema v1
-- 2026-05-20
--
-- Additive only: CREATE ... IF NOT EXISTS, no DROP, no destructive
-- statements. Safe to run repeatedly (idempotent).
--
-- The event tables mirror the existing GLYPH JSON schemas exactly:
--   raw_event       <- raw_event_schema_v1.json
--   glyph_event     <- event_schema_v1.json   (R = x / (x + y^2))
--   absence_record  <- absence_record_schema_v1.json
-- They are not a redesign — the engine still owns the schemas; this
-- is those schemas expressed as durable tables on the live service.
--
-- content + subscriber support the KairoGLYPH site:
--   content     -> editable site text (replaces the Notion source)
--   subscriber  -> the subscription page -> personal dashboard
--
-- Apply with:  psql "$DATABASE_URL" -f db/schema.sql
-- gen_random_uuid() is core in PostgreSQL 13+ (Render runs 16).
-- ============================================================

-- ---- raw_event : append-only universal intake ----------------
-- "Preserve raw first, segment second, compute third."
CREATE TABLE IF NOT EXISTS raw_event (
    record_id        text PRIMARY KEY,
    source_id        text NOT NULL,
    speaker          text,
    branch           text NOT NULL,   -- observed|transcript|model_output|metadata|glyph_identity|absence|action|raw_source_capture
    event_kind       text NOT NULL,
    raw              text,            -- immutable once written
    raw_sha256       text NOT NULL,   -- immutable
    raw_byte_count   integer NOT NULL,-- immutable
    authority_level  text NOT NULL,
    status           text NOT NULL,
    action           text NOT NULL,
    schema_version   text NOT NULL DEFAULT 'v1',
    event_timestamp  timestamptz NOT NULL,
    ingested_at      timestamptz NOT NULL DEFAULT now()
);

-- ---- glyph_event : structured output, R = x / (x + y^2) -------
-- zones: SUBORDINATED R<0.33 | STRUCTURAL 0.33<=R<=0.50 | DOMINANT R>0.50
CREATE TABLE IF NOT EXISTS glyph_event (
    record_id            text PRIMARY KEY,
    raw_event_id         text REFERENCES raw_event(record_id),
    domain               text NOT NULL,
    x                    double precision NOT NULL,
    y                    double precision NOT NULL,
    r_value              double precision NOT NULL,
    zone                 text NOT NULL,
    input_values         jsonb,
    thresholds           jsonb,
    mapping_rule_version text NOT NULL,
    output_produced      text,
    provenance           jsonb,
    schema_version       text NOT NULL DEFAULT 'v1',
    event_timestamp      timestamptz NOT NULL,
    created_at           timestamptz NOT NULL DEFAULT now()
);

-- ---- absence_record : missing/empty/unreadable as records -----
-- "Absence is recorded as an event, not ignored as nothing."
CREATE TABLE IF NOT EXISTS absence_record (
    record_id        text PRIMARY KEY,
    source_id        text NOT NULL,
    branch           text NOT NULL DEFAULT 'absence',
    event_kind       text NOT NULL,
    source_path      text NOT NULL,
    observed_state   text NOT NULL,   -- empty|missing|unreadable|cloud_placeholder_only|external_tool_required|unsupported_operation|not_available
    meaning          text NOT NULL,
    next_action      text NOT NULL,
    status           text NOT NULL,
    schema_version   text NOT NULL DEFAULT 'v1',
    event_timestamp  timestamptz NOT NULL,
    recorded_at      timestamptz NOT NULL DEFAULT now()
);

-- ---- ledger_entry : append-only, tamper-evident chain ---------
-- Each entry references the previous entry's hash (replay spine).
CREATE TABLE IF NOT EXISTS ledger_entry (
    seq          bigserial PRIMARY KEY,
    entry_hash   text NOT NULL,
    prev_hash    text,
    ref_type     text NOT NULL,       -- raw_event|glyph_event|absence_record|content
    ref_id       text NOT NULL,
    recorded_at  timestamptz NOT NULL DEFAULT now()
);

-- ---- content : editable site text (the Notion replacement) ----
-- Route-keyed. The React app reads content by route; the edit UI
-- writes back here. Routes: home|research|filing|about|subscribe.
CREATE TABLE IF NOT EXISTS content (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    route        text NOT NULL,
    section      text NOT NULL,
    title        text,
    body         text,                -- markdown
    position     integer NOT NULL DEFAULT 0,
    status       text NOT NULL DEFAULT 'draft',  -- draft|published
    updated_at   timestamptz NOT NULL DEFAULT now(),
    updated_by   text,
    UNIQUE (route, section)
);

-- ---- subscriber : subscription page -> personal dashboard -----
CREATE TABLE IF NOT EXISTS subscriber (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email           text NOT NULL UNIQUE,
    display_name    text,
    status          text NOT NULL DEFAULT 'pending',  -- pending|active|cancelled
    dashboard_slug  text UNIQUE,        -- the user's personal dashboard path
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- ---- indexes --------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_glyph_event_domain ON glyph_event (domain);
CREATE INDEX IF NOT EXISTS idx_glyph_event_zone   ON glyph_event (zone);
CREATE INDEX IF NOT EXISTS idx_glyph_event_ts     ON glyph_event (event_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_event_status   ON raw_event (status);
CREATE INDEX IF NOT EXISTS idx_absence_state      ON absence_record (observed_state);
CREATE INDEX IF NOT EXISTS idx_content_route      ON content (route);

-- ---- content seed : section scaffolding for the new routes ----
-- Starter rows so the edit UI and the React app have content to
-- render immediately. Real copy is edited later via the edit UI.
INSERT INTO content (route, section, title, body, position, status) VALUES
  ('home',      'hero',         'KairoGLYPH', 'A structured-intelligence terminal. Pour in unstructured life and read back structured events.', 0, 'draft'),
  ('home',      'how-it-works', 'How it works', 'Any input enters the ledger, GLYPH converts it into events, the terminal shows them.', 1, 'draft'),
  ('research',  'overview',     'The Jonah Study', 'Cross-domain convergence of distributional ratios in choice-absent systems.', 0, 'draft'),
  ('research',  'sources',      'Sources', 'Citations and primary sources behind the study.', 1, 'draft'),
  ('filing',    'overview',     'Filing', 'Data drawn from the repository and the running app.', 0, 'draft'),
  ('about',     'mission',      'About KairoGLYPH', 'What the terminal is for and who it serves.', 0, 'draft'),
  ('subscribe', 'pitch',        'Subscribe', 'Create an account to open your personal dashboard.', 0, 'draft')
ON CONFLICT (route, section) DO NOTHING;
