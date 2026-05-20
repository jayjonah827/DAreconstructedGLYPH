"""Load The Jonah Study datasets into KairoGLYPH as glyph_events.

Reads data/research_data.json and runs each dataset through the verified
intake chain (kairo_intake.process_intake). Each dataset's measured ratio
(`constant`) is the event's R; x and y use the canonical y=1
normalization  x = R / (1 - R), so x / (x + y^2) reproduces the measured
ratio exactly. The full dataset record is preserved in raw_event.

Idempotent: if events from source 'the_jonah_study' already exist, it
exits without reloading. Run with:  python3 db/load_jonah_study.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

for _line in (BASE / ".env").read_text().splitlines():
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k, _v.strip())

import kairo_intake as ki  # noqa: E402


def xy_from_ratio(r: float) -> tuple[float, float]:
    """y = 1 normalization: x / (x + 1) = r  ->  x = r / (1 - r)."""
    return r / (1.0 - r), 1.0


def main() -> int:
    data = json.loads((BASE / "data" / "research_data.json").read_text())
    datasets = data.get("datasets", [])
    meta = data.get("metadata", {})
    finding = data.get("core_finding", {})

    conn = ki._connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM raw_event WHERE source_id = %s",
                        ("the_jonah_study",))
            if cur.fetchone()[0] > 0:
                print("the_jonah_study already loaded — nothing to do.")
                return 0

        loaded = []
        for ds in datasets:
            r = float(ds["constant"])
            x, y = xy_from_ratio(r)
            body = {
                "source": "the_jonah_study",
                "domain": ds.get("domain", "unsorted"),
                "branch": "metadata",
                "event_kind": "study_dataset",
                "x": x,
                "y": y,
                "dataset": ds.get("name"),
                "period": ds.get("year") or ds.get("year_range") or ds.get("era"),
                "measured_ratio": r,
                "normalization": "y=1; x=r/(1-r)",
                "study": meta.get("title"),
            }
            res = ki.process_intake(body, conn)
            loaded.append((ds.get("name"), res.get("glyph_event")))

        overview = (
            f"{meta.get('title', 'The Jonah Study')} — "
            f"{meta.get('subtitle', '')}. Across {len(datasets)} datasets the "
            f"structural constraint ratio R = x / (x + y²) converges to a grand "
            f"mean of {finding.get('grand_mean')} "
            f"(SD {finding.get('standard_deviation')}, p {finding.get('p_value')})."
        )
        sources = (
            "Datasets analysed: "
            + "; ".join(d.get("name", "") for d in datasets)
            + f". Author: {meta.get('author')}, {meta.get('entity')}, "
            f"{meta.get('institution')}."
        )
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE content SET body = %s, status = 'published', "
                "updated_at = now(), updated_by = 'jonah_study_loader' "
                "WHERE route = 'research' AND section = 'overview'", (overview,))
            cur.execute(
                "UPDATE content SET body = %s, status = 'published', "
                "updated_at = now(), updated_by = 'jonah_study_loader' "
                "WHERE route = 'research' AND section = 'sources'", (sources,))

        conn.commit()
        print(f"loaded {len(loaded)} datasets into glyph_event:")
        for name, gev in loaded:
            if gev:
                print(f"  {name:28s}  {gev['domain']:22s}  "
                      f"R={gev['r_value']:.4f}  {gev['zone']}")
        print("research content (overview + sources): updated and published")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"FAILED — rolled back: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
