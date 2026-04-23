# The reconstruction of Glyph

Glyph 2.0 — the reconstructed ecosystem.

## Canon

`GLYPH.md` at the repo root is the canonical document. If two places disagree, GLYPH.md is right.

## Binding

`shape_index.py` maps the 9 windows onto `(shape, role, mode)` per GLYPH.md §3 and §5. Names (`enter`, `compass`, `lab`, etc.) are a derived view — the binding is the shape coordinate. `(pyramid, field, outer)` is unmeasured by invariant.

## Deploy

`main` auto-deploys to Render service `8glyphs27` → https://eightglyphs27.onrender.com

## Entry points

- `server.py` — running web service
- `glyph_constraint.py` — math / constraint layer
- `shape_index.py` — shape binding for the 9 windows
- `GLYPH.md` — the one document
- `index.html` — entry surface
