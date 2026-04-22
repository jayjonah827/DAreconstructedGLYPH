# GLYPH — one system document

**Version:** 1.0 canonical · **Date:** 2026-04-22

> **Only Glyph exists. Everything else is a window, operator, source, or artifact of Glyph.**

This is the one thing to read. Every other surface — the Google Site, the repo, Notion, Fourthwall, decks, caches, prior drafts — feeds this document or is rendered from it. If two places disagree, **this document is right**.

---

## 0 · How to read this

Top to bottom once, to absorb the whole thought. By section afterwards for specific tasks. Every section is load-bearing; nothing is optional context.

- §1 language — the vocabulary
- §2 math — the law
- §3 structure — primitives, composite states, the three matrix layers
- §4 purpose — what Glyph is for
- §5 windows — the nine
- §6 canonical IDs — the full flat index
- §7 rules — for humans, for machines
- §8 operators — who acts on Glyph and how
- §9 surfaces — delivery layers (never canonical)
- §10 source map — existing content → canonical ID
- §11 fold decisions — what was consolidated, with flags
- §12 open questions — waiting on the rename map
- §13 provenance — how this document was assembled

---

## 1 · Language

Words have exact meanings here. Do not interchange.

| word | meaning |
|---|---|
| **Glyph** | the single object being built. Every other noun is a view / operator / source / artifact of this. |
| **window** | a rendered view onto Glyph. Nine windows exist (§5). |
| **canonical ID** | the stable machine address of a window or sub-window. Form: `glyph.<window>[.<sub>]`. |
| **public path** | URL a public window is rendered at: `/glyph/<window>[/sub]`. |
| **surface** | a delivery layer (Google Site, repo-html, Notion, Fourthwall, deck, other). Many surfaces per window. Surfaces are never in canonical IDs. |
| **operator** | an agent / script / tool that acts on Glyph (Codex, Notion MCP, Automator, Claude). |
| **source** | a record that feeds Glyph (cached file, draft, transmission). |
| **artifact** | an output produced by Glyph. |
| **evidence** | a file or reference that supports a canonical ID (e.g. `portal.html` evidences `glyph.enter`). |
| **role** | the instrument a window acts as. One of: `coin`, `clock`, `compass`, `eye`, `floor`, `hierarchy`, `generator`, `field`. |
| **claim order** | level of assertion: `chance` (1), `choice` (2), `structural_bounds` (3). Relative, not absolute. |
| **mode** | `inner` or `outer`. Meaningful only for the pyramid primitive. Outer pyramid field is never scored. |
| **composite state** | one of `seed`, `system_with_frame`, `system_without_frame`, `system_3d`. |
| **parallax** | gap between roles within one ecosystem. Off-diagonals of the ladder matrix (§3). |
| **combination distance** | gap between composite states. Off-diagonals of the transition matrix (§3). |
| **unmeasured** | the value returned by the outer pyramid field. Never scored. Type-level invariant. |
| **core** | `glyph.core` — the protected private branch. Never in public navigation. |
| **seed** | the origin-only composite state. `r = 0`. Entry point to any building sequence. |

---

## 2 · Math (the law)

### 2.1 Constants

| symbol | value | meaning |
|---|---|---|
| π/8 | 0.39270 | octant angle · 3-binary-axis half-tick |
| 1/φ² = 2 − φ | 0.38197 | golden ratio inverse squared |
| sin(π/8) | 0.38268 | octagon half-side in unit circle |
| ε = tan(π/8) = √2 − 1 | 0.41421 | irreducible play · tangent overshoot at octant |
| 3√3 / (4π) | 0.41349 | equilateral triangle area / unit circle area |
| σ ≈ π² / 512 | 0.01929 | declared 0.019778 · within 2.5% |

### 2.2 Identities (exact)

- `1/φ² = 2 − φ`
- `tan(π/8) = √2 − 1 = ε`
- Regular n-gon side in unit circle: `s_n = 2 · sin(π/n)` → triangle √3, square √2, octagon 2·sin(π/8)
- `(2/5) − (π/8) = (16 − 5π) / 40 = 0.00730`
- `1/2 − 2/5 = 1/10 = 0.10000`
- `1/2 − π/8 = (4 − π) / 8 = 0.10730`

### 2.3 R-function (the one dynamic law)

`R(x, y) = x / (x + y²)`

Constraint locus: `x = (π / (8 − π)) · y² = 0.6466 · y²` makes `R = π/8`.

On the unit clock (`x = cos t`, `y = sin t`):

| t | cos t | R |
|---|---|---|
| 0 | 1 | 1 |
| ≈ 51.83° | 1/φ | **1/2** |
| 60° (= π/3) | 1/2 | **2/5** |
| ≈ 60.63° | 0.4908 | **π/8** |
| 90° (= π/2) | 0 | 0 |

### 2.4 Three-tier ladder

| order | label | R | t | ruling constant |
|---|---|---|---|---|
| 3 | structural_bounds | 1/2 | arccos(1/φ) ≈ 51.83° | 1/φ |
| 2 | choice | 2/5 | π/3 = 60° | triangle corner |
| 1 | chance | π/8 | ≈ 60.63° | octant |

### 2.5 Gaps

- struct − choice = 0.10000
- choice − chance = 0.00730
- struct − chance = 0.10730
- ratio `(choice → struct) / (chance → choice)` ≈ 13.7

### 2.6 Mean of five constants

Of `{π/8, 1/φ², sin(π/8), 2 − φ, 3√3/(4π)}`:
- arithmetic 0.39056 · geometric 0.39037 · harmonic 0.39018 · median 0.38268
- centroid lands within 0.001 of π/8 → the chance row is **anchored**, not arbitrary

### 2.7 What the math means for the system

Every window of Glyph sits somewhere on the ladder. Parallax gaps are recorded inside `glyph.schema.ladder`. The R-function is the only dynamic law — everything else is identity, placement, or consequence.

---

## 3 · Structure

### 3.1 Shape primitives

```
ShapePrimitive {
  shape: {circle, square, triangle, pyramid, origin, gesture_hand}
  role:  {clock, compass, coin, hierarchy, field, generator}
  mode:  {inner, outer}     // meaningful only for pyramid
}
```

Native mappings:

- circle × clock — continuity, phase; one DOF = r
- square × compass — orthogonal axes, boundary
- triangle × coin — 3-branch decision
- pyramid × hierarchy [inner] — claim-stacking upward, scored
- pyramid × field [outer] — containing universe, **never scored**
- origin × generator — `r = 0`, seed point
- gesture_hand — polyvalent; derives in every role

### 3.2 Axes

- **N–S asymmetric** (intake ≠ outtake)
- **E–W symmetric** (reversible)
- **8-spoke radial** = coin / clock / compass instrument cluster
- **grid_8×8** = 3 binary axes → 2³ = 8 states

### 3.3 Claim orders (concentric, not stacked)

- order 1 **chance** — outermost ring · role = coin
- order 2 **choice** — middle ring · role = clock
- order 3 **structural_bounds** — innermost ring · role = compass
- distance metric: radial from origin

No claim order ranks above another. The ladder is relative within a single ecosystem.

### 3.4 Composite states

- `seed` — outer_field + continuity_field + origin (ONE)
- `system_with_frame` — seed + 3 claim_order rings + 8-spoke + cardinals + intercardinals (BASELINE)
- `system_without_frame` — `system_with_frame` minus outer_field (clock-compass only)
- `system_3d` — pyramid [inner, lit apex] + pyramid [outer, shadowed base]

### 3.5 Operations

- `separate(reading)` — distinguish roles within one ecosystem
- `combine(readings)` — recover unity across distance
- gap **within** ecosystem → **parallax** (instrument tolerance)
- gap **across** ecosystems → **combination_distance** (recovered unity)

### 3.6 Matrix layers (the structural form of the law)

**Layer A — ladder matrix** (3 × 3, claim_order × role). Diagonal = native binding. Off-diagonals = parallax.

|  | coin | clock | compass |
|---|---|---|---|
| chance | **π/8** | 0.00730 | 0.10730 |
| choice | 0.00730 | **2/5** | 0.10000 |
| structural_bounds | 0.10730 | 0.10000 | **1/2** |

Stored at: `glyph.schema.ladder`.

**Layer B — primitive tensor** (shape × role × mode). Codes: N = native, D = derived, U = unmeasured. The one hard invariant: `pyramid × field × outer = U` (the type system must refuse to score it).

Stored at: `glyph.schema.primitives`.

**Layer C — composite-state transitions** (4 × 4). Identity on diagonal. Asymmetric: `combine` builds up, `separate` peels down.

Stored at: `glyph.schema.transitions`.

### 3.7 Load-bearing constraints (carried forward)

1. Outer pyramid field is never scored → returns `unmeasured`.
2. No claim_order ranks above another → no absolute apex.
3. All constants are relative within the visible system.
4. 8×8 grid is the measurable interior; outer field is the unmeasurable frame.
5. Heartbeat is remote (Render worker). Local-machine heartbeat is diagnostic only.

---

## 4 · Purpose

Glyph is a **cultural-intelligence artifact**. Its job is to hold one coherent thought across math, structure, language, and delivery — so that any reader, human or machine, can enter at any window and reach the same center.

The ecosystem exists so that:
- writers place content into **windows**, not branches or platforms
- operators bind to **canonical IDs**, not paths
- surfaces (Google Site, repo, Notion, Fourthwall, decks) render the same thing without competing for truth
- the protected core stays private without needing a separate system

Glyph is not a product, a site, a deck, or a workspace. Those are surfaces. Glyph is the object they all render.

---

## 5 · The 9 windows

| # | canonical ID | public path | role | claim order | purpose |
|---|---|---|---|---|---|
| 1 | `glyph.enter` | `/glyph/enter` | generator | — | entry — first contact with Glyph (the "hi, I'm Kairo" identity / Try Me! surface) |
| 2 | `glyph.overview` | `/glyph/overview` | eye | — | readable explanation of the ecosystem |
| 3 | `glyph.compass` | `/glyph/compass` | compass | structural_bounds | 4-cardinal navigation / orientation |
| 4 | `glyph.schema` | `/glyph/schema` | compass | structural_bounds | the law — equation, identities, claims, specification, definitions, rules |
| 5 | `glyph.lab` | `/glyph/lab` | coin | chance | research and testing — data, Glyph-8, graphs, convergence |
| 6 | `glyph.artifacts` | `/glyph/artifacts` | clock | choice | outputs — portfolio, storefront, arcade, exhibit, story, voice |
| 7 | `glyph.journal` | `/glyph/journal` | clock | choice | signals — blog, bulletin, forums |
| 8 | `glyph.operator` | `/glyph/operator` | hierarchy + generator | — | console — Notion OS, syllabus, modules, support, Automator, agents |
| 9 | `glyph.core` | *(private — no public path)* | field/outer + hierarchy/inner | — | protected core — ADS, statement, assignments, content hash |

---

## 6 · Canonical IDs (flat index)

Machine code and agent scripts bind to this list. 49 IDs total (48 public leaves + 1 private branch with 4 private leaves). Every ID below is valid. Nothing outside this list is valid.

```
glyph.enter

glyph.overview
glyph.overview.anthropology
glyph.overview.statistics
glyph.overview.social-studies
glyph.overview.marketing-psychology

glyph.compass
glyph.compass.coin              # North — TreeOfLife
glyph.compass.clock             # East — BookOfLife
glyph.compass.eye               # West — FountainOfTruth
glyph.compass.floor             # South — SourceOfTruth

glyph.schema
glyph.schema.equation           # R, π/8, 2/5, 1/2, ε, σ, identities
glyph.schema.ladder             # Layer A matrix
glyph.schema.primitives         # Layer B tensor
glyph.schema.transitions        # Layer C matrix
glyph.schema.claims             # from NONPRO.VISION → Claims (public)
glyph.schema.specification      # from NONPRO.VISION → Specification
glyph.schema.cross-reference    # from NONPRO.VISION → Cross-reference
glyph.schema.glossary           # definitions (was REVIEW → DEFINITIONS)
glyph.schema.rules              # governance (was REVIEW → RULES & REGULATIONS)

glyph.lab
glyph.lab.data
glyph.lab.glyph-8
glyph.lab.graphs
glyph.lab.physics
glyph.lab.convergence
glyph.lab.research-tracker

glyph.artifacts
glyph.artifacts.portfolio
glyph.artifacts.storefront      # transaction sub-window
glyph.artifacts.arcade
glyph.artifacts.exhibit
glyph.artifacts.story
glyph.artifacts.voice

glyph.journal
glyph.journal.blog
glyph.journal.bulletin
glyph.journal.forums

glyph.operator
glyph.operator.notion-os
glyph.operator.syllabus
glyph.operator.modules
glyph.operator.support
glyph.operator.automator
glyph.operator.agents

# PRIVATE — never in public navigation
glyph.core
glyph.core.ads                  # Application Data Sheets
glyph.core.statement            # inventor statement
glyph.core.assignments          # IP assignments
glyph.core.hash                 # QmPYcVJCV8277
```

---

## 7 · Rules

### 7.1 For humans writing content

1. Write to a canonical ID. If no ID fits, send a rename-map update — do not invent an ID.
2. Surfaces are delivery only. Never name content after a surface (no "the Fourthwall thing," no "the Notion page").
3. `glyph.core` is private. Do not link to it from any public window. Do not reference its contents in public prose.
4. Language is from §1. Do not substitute "window" for "page," "canonical ID" for "slug," etc.

### 7.2 For machines (binding contract)

1. Bind to canonical IDs. Never to surfaces or file paths.
2. A page is a **rendering** of an ID; it is not the ID.
3. A file is **evidence** for an ID; it is not the ID.
4. A tool operates **on** IDs; it does not declare IDs.
5. `glyph.core` never appears in any public index, sitemap, menu, or search result.
6. Unmappable content → `glyph.schema.glossary` as `UNMAPPED: <slug>` until a human classifies. No top-level label invented.
7. Outer pyramid field is never scored. Attempts to score it must return `unmeasured`.
8. No claim_order ranks above another. No absolute apex. Ranking is forbidden at system level.
9. Heartbeat is remote (Render worker). Local-machine heartbeat is diagnostic only and never the liveness signal.
10. Canonical ID, Role, Claim order, Window, Visibility values are fixed by this document. Operators do not change them.

### 7.3 Public / private boundary

Public windows: `glyph.enter`, `glyph.overview`, `glyph.compass`, `glyph.schema`, `glyph.lab`, `glyph.artifacts`, `glyph.journal`, `glyph.operator`.

Private: `glyph.core` and all `glyph.core.*`.

Access-controlled. No public URL. No sitemap entry. No Notion public view.

---

## 8 · Operators

| operator | what it does | narrow prompt |
|---|---|---|
| **Codex** | read-only repo inventory. Assigns every file to a canonical ID. Writes `inventory.md`. | `~/Glyph/matrix/components/codex-prompt.md` |
| **Claude + Notion MCP** | builds the `glyph · canonical` database; one page per ID; empty bodies; properties filled. | `~/Glyph/matrix/components/notion-prompt.md` |
| **Automator.app** (macOS) | disk / project / sampling workflows, tagged `(claim_order, role, mode)`. Reports only, never deletes. | `~/.claude/plans/this-is-apart-of-velvety-sutherland.md` |
| **Claude (this session)** | maintains this document. Proposes rename-map updates. Does not commit to the Glyph repo without explicit instruction. | this file |

**Rule:** Every operator reads §1 (language), §6 (IDs), §7 (rules) before acting. No operator acts on something that is not in §6.

---

## 9 · Surfaces

All equal, none canonical. Each window may render on many. A surface that contradicts §5 or §6 is wrong — fix the surface, not the document.

| surface | what it is | example |
|---|---|---|
| `google-site` | the public Google Site | `sites.google.com/view/heyerlivin-kairo-glyph` |
| `repo-html` | static HTML in the canonical repo | `portal.html`, `story.html`, etc. |
| `notion` | the `glyph · canonical` database | built by the Notion operator |
| `fourthwall` | transaction / storefront surface | storefront render of `glyph.artifacts.storefront` |
| `deck` | slide exports | presentation renders of any window |
| `repo-py`, `repo-ts`, `repo-json`, `repo-md` | code / data in the canonical repo | `server.py`, `state/notion_content_cache.json`, etc. |
| `other` | anything else | tagged as `other` in inventories |

---

## 10 · Source map (existing content → canonical ID)

High-confidence mappings so far. The Codex inventory (§8) will fill in the rest.

| source | canonical ID | confidence |
|---|---|---|
| repo `portal.html` | `glyph.enter` | high |
| repo `story.html` | `glyph.artifacts.story` | medium (FOLD — could be overview) |
| repo `dictionary.html` | `glyph.schema.glossary` | high |
| repo `arcade.html` + `arcade/` | `glyph.artifacts.arcade` | high |
| repo `research.html` | `glyph.schema.equation` or `glyph.lab.research-tracker` | low |
| repo `filing.html` | `glyph.schema.claims` + `glyph.schema.specification` (public) + `glyph.core.*` (private) | medium (FOLD — public/private split) |
| repo `scholarship.html` | `glyph.operator.syllabus` or `glyph.operator.modules` | medium |
| repo `full_transmission.html` | `glyph.schema.specification` | medium |
| repo `glyph_voice_render.html` | `glyph.artifacts.voice` | high |
| repo `heyer_livin_clock.html` | `glyph.compass.clock` | high |
| repo `research_tracker_v2.html` | `glyph.lab.research-tracker` | high |
| repo `state/notion_content_cache.json` | transport layer — not a canonical ID (bridges `notion` surface → `repo-html` surface) | — |
| repo `MAC_PROOF_BUNDLE.txt` | audit artifact — not a canonical ID | — |
| repo `render.yaml` + `workflows-demo/*` | `glyph.operator.automator` or deploy infrastructure | medium |
| Google Site "hi, I'm Kairo" | `glyph.enter` | high |
| Google Site ABOUT: OVERVIEW | `glyph.overview` + 4 children | high |
| Google Site Cultural Compass | `glyph.compass` + 4 children | high |
| Google Site Institute of Roughery → Syllabus | `glyph.operator.syllabus` | high |
| Google Site Institute of Roughery → Cultural Intelligence Modules | `glyph.operator.modules` | high |
| Google Site Institute of Roughery → Tech-Human Support | `glyph.operator.support` | high |
| Google Site Institute of Roughery → Bulletin Board | `glyph.journal.bulletin` | high |
| Google Site REVIEW → NONPRO.VISION → Claims / Specification / Cross-reference | `glyph.schema.{claims, specification, cross-reference}` | high |
| Google Site REVIEW → NONPRO.VISION → Application Data Sheets / Statement | `glyph.core.{ads, statement}` | medium (FOLD) |
| Google Site REVIEW → DEFINITIONS | `glyph.schema.glossary` | high |
| Google Site REVIEW → ASSIGNMENTS | `glyph.core.assignments` | medium (FOLD) |
| Google Site REVIEW → FORUMS | `glyph.journal.forums` | high |
| Google Site REVIEW → RULES & REGULATIONS | `glyph.schema.rules` | high |
| content hash `QmPYcVJCV8277` | `glyph.core.hash` | high |
| MATH/STRUCTURE spec (this document, §§2–3) | `glyph.schema.equation` + `glyph.schema.ladder` + `glyph.schema.primitives` + `glyph.schema.transitions` | high |

---

## 11 · Fold decisions

Changes made during canonicalization. All reversible via rename map.

1. **REVIEW branch disbanded.** Public items (Claims, Specification, Cross-reference, Definitions, Rules & Regulations) → `glyph.schema`. Private items (ADS, Statement, Assignments) → `glyph.core`. `[FOLD]`
2. **Institute of Roughery disbanded.** Syllabus / Modules / Support → `glyph.operator`. Bulletin Board → `glyph.journal.bulletin`. `[FOLD]`
3. **Statistics sub-items split.** Proof / Probability / Formula → `glyph.schema`. Graph / AP Physics → `glyph.lab`. Portfolio → `glyph.artifacts.portfolio`. `[FOLD]`
4. **Social Studies → Structural Architecture** → `glyph.schema.primitives`. `[FOLD]`
5. **Marketing Psychology → Design + Exhibit** → `glyph.artifacts.exhibit`. `[FOLD]`
6. **Glyph-8** placed in `glyph.lab.glyph-8`. If it is a deliverable rather than a harness, move to `glyph.artifacts`. `[FOLD]`
7. **`story.html`** placed in `glyph.artifacts.story`. If it is the master narrative, move to `glyph.overview`. `[FOLD]`

---

## 12 · Open questions

Sent rename map closes these:

1. Is the public/private split inside NONPRO.VISION exactly `{Claims, Specification, Cross-reference} → public / {ADS, Statement, Assignments} → private`? (Fold 1)
2. Is `Glyph-8` a research harness (`glyph.lab`) or a deliverable (`glyph.artifacts`)? (Fold 6)
3. Is `story.html` an artifact or the master overview? (Fold 7)
4. Does `glyph.journal.forums` stay under journal, or move to operator?
5. `glyph.operator.agents` holds prompt files — correct home, or should prompts sit under `glyph.schema.rules`?

---

## 13 · Provenance

| source | contribution |
|---|---|
| MATH/STRUCTURE spec (author, 2026-04-22) | §2 math · §3 structure |
| Google Sites WebFetch (2026-04-22) | §5 windows topology · §10 source map |
| Canonical-law declaration (author, 2026-04-22; three transmissions) | §1 language · §4 purpose · §5 windows · §7 rules |
| Pre-correction skeleton (`~/Glyph/matrix/pre-correction/skeleton.md`) | historical artifact only; superseded by this document |
| Component operator prompts (`~/Glyph/matrix/components/*.md`) | narrow instructions for Codex and Notion · subordinate to §§1, 6, 7 |

### Change log

- **2026-04-22 v1.0** — first canonical document. Consolidates MATH spec, public ecosystem inventory, canonical-law declaration, and the three prior scaffold files into one thought. Fold decisions 1–7 recorded at §11.

### Authority

This document is the truth. The three operator prompts in `components/` are subordinate. Pre-correction material is archived at `~/Glyph/matrix/pre-correction/` for audit only.

---

*End of document.*
