# DigitalOcean Spaces Asset Bucket

Supports the DAreconstructedGLYPH asset pipeline by storing selected static assets in DigitalOcean Spaces for consumption by the Render-hosted application at `eightglyphs27.onrender.com`.

## Purpose

This bucket is not the source of truth. It is a deployment-facing asset surface used to move approved DAreconstructedGLYPH files into object storage so the Render app can reference them without restructuring the core repository.

The sync process is handled by `sync_to_spaces.py`.

## Authority Boundary

- The repository remains the canonical development and record surface.
- DigitalOcean Spaces is only an asset delivery layer.
- Render remains the application host.
- The bucket is not a live editor, canonical archive, patent record, or replacement for the local/repository ledger.

## Expected Use

Use this bucket for assets that are approved for deployment-facing access, required by the Render app, safe to serve as static or media assets, and already classified for the correct public/private handling level.

Do not use this bucket for raw patent drafting records, unreviewed source material, private ledger files, credential files, secrets, API keys, tokens, environment files, or files whose authority status has not been confirmed.

## Patent-Pending Notice

DAreconstructedGLYPH and related GLYPH system materials may contain patent-pending intellectual property, including process logic, classification structures, schema methods, asset routing logic, convergence analysis, and system architecture associated with Heyer Livin LLC.

Uploading files to this bucket does not grant permission to copy, reuse, reverse engineer, train on, reproduce, redistribute, or derive systems from the protected materials.

## Operation

```bash
export DO_SPACES_KEY=...
export DO_SPACES_SECRET=...
export DO_SPACES_REGION=nyc3      # or your region
export DO_SPACES_BUCKET=...
pip install boto3
python sync_to_spaces.py --dry-run    # preview
python sync_to_spaces.py              # live sync
```

Files under `public/` are uploaded with `public-read` ACL. All others are `private`.

All rights reserved, Heyer Livin LLC.
