"""
Shape binding for the 9 windows.

Derived verbatim from GLYPH.md §3 (shape primitives, native mappings) and §5
(the 9 windows). Names (`view_name`, `canonical_id`) are a derived view —
the binding layer is (shape, role, mode).

Do not edit this table. If a mapping looks wrong, the fix is in GLYPH.md,
not here.
"""

from pathlib import Path

GLYPH_MD = Path(__file__).parent / "GLYPH.md"

WINDOWS = [
    {
        "view_name": "enter",
        "canonical_id": "glyph.enter",
        "signatures": [("origin", "generator", "inner")],
        "claim_order": None,
    },
    {
        "view_name": "overview",
        "canonical_id": "glyph.overview",
        "signatures": [("gesture_hand", "eye", "inner")],
        "claim_order": None,
    },
    {
        "view_name": "compass",
        "canonical_id": "glyph.compass",
        "signatures": [("square", "compass", "inner")],
        "claim_order": "structural_bounds",
    },
    {
        "view_name": "schema",
        "canonical_id": "glyph.schema",
        "signatures": [("square", "compass", "inner")],
        "claim_order": "structural_bounds",
    },
    {
        "view_name": "lab",
        "canonical_id": "glyph.lab",
        "signatures": [("triangle", "coin", "inner")],
        "claim_order": "chance",
    },
    {
        "view_name": "artifacts",
        "canonical_id": "glyph.artifacts",
        "signatures": [("circle", "clock", "inner")],
        "claim_order": "choice",
    },
    {
        "view_name": "journal",
        "canonical_id": "glyph.journal",
        "signatures": [("circle", "clock", "inner")],
        "claim_order": "choice",
    },
    {
        "view_name": "operator",
        "canonical_id": "glyph.operator",
        "signatures": [
            ("pyramid", "hierarchy", "inner"),
            ("origin", "generator", "inner"),
        ],
        "claim_order": None,
    },
    {
        "view_name": "core",
        "canonical_id": "glyph.core",
        "signatures": [
            ("pyramid", "field", "outer"),
            ("pyramid", "hierarchy", "inner"),
        ],
        "claim_order": None,
    },
]

UNMEASURED = ("pyramid", "field", "outer")


def windows_at(shape=None, role=None, mode=None):
    out = []
    for w in WINDOWS:
        for sig in w["signatures"]:
            s, r, m = sig
            if (shape is None or s == shape) and (role is None or r == role) and (mode is None or m == mode):
                out.append(w)
                break
    return out


def score_allowed(shape, role, mode):
    return (shape, role, mode) != UNMEASURED


def read_glyph_md():
    if not GLYPH_MD.exists():
        return None
    return GLYPH_MD.read_text()
