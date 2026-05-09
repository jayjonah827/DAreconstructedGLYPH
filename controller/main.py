from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import pstdev
from typing import Any

ALLOWED_ISSUE_STATES = {"OPEN", "PARTIAL", "RESOLVED", "BLOCKED", "WAIVED"}
UNRESOLVED_ISSUE_STATES = {"OPEN", "PARTIAL", "BLOCKED"}
CANONICAL_REPO_ROOT = Path(
    os.environ.get("GLYPH_CANONICAL_REPO_ROOT", "/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH")
).resolve()
APPROVED_ENTRYPOINT_ENV = "GLYPH_ENTRYPOINT_APPROVED"
ENTRYPOINT_NAME_ENV = "GLYPH_ENTRYPOINT_NAME"
ALLOW_DIRECT_CLI_ENV = "GLYPH_ALLOW_DIRECT_CLI"

DEFAULT_WRITING_RULES = {
    "version": "1.0.0",
    "policy": {
        "unresolved_states_block_ship": ["OPEN", "PARTIAL", "BLOCKED"],
        "waiver_policy_marker_prefix": "POLICY-WAIVER:",
        "controller_only_ship_allowed": True,
        "conservative_revision_requires_exact_flags": True,
    },
    "known_conservative_flags": [
        "preserve_order",
        "preserve_claims",
        "preserve_terminology",
        "preserve_sentence_count",
        "preserve_paragraph_count",
        "no_new_metaphors",
        "no_new_headings",
        "no_new_lists",
    ],
    "markers": {
        "op_ed": [
            "the point is",
            "what matters is",
            "make no mistake",
            "we need to",
            "it is time to",
        ],
        "thesis_framing": [
            "the thesis is",
            "this means",
            "the point is",
            "what this shows",
            "in short",
        ],
        "credentialing": [
            "as someone who",
            "in my experience",
            "i have worked",
            "i've worked",
            "my background",
            "my experience",
        ],
        "metaphor_framing": [
            "metaphor",
            "think of this as",
            "imagine",
            "picture this",
            "as if",
        ],
        "policy_brief_openers": [
            "One concrete change:",
            "One policy change:",
            "One practical fix:",
        ],
        "rhetorical_symmetry_patterns": [
            r"\bnot\b.+\bbut\b",
            r"\beither\b.+\bor\b",
            r"\bboth\b.+\band\b",
        ],
    },
    "thresholds": {
        "repetition_ngram_size": 3,
        "repetition_ngram_occurrences": 3,
        "repetition_cluster_size": 2,
        "mirrored_open_close_similarity": 0.72,
        "uniform_sentence_count_min": 5,
        "uniform_sentence_stddev_max": 1.35,
        "marker_repeat_count": 2,
        "four_item_list_repeat_count": 2,
    },
}

DEFAULT_SYSTEMS_RULES = {
    "version": "1.0.0",
    "policy": {
        "unresolved_states_block_ship": ["OPEN", "PARTIAL", "BLOCKED"],
        "waiver_policy_marker_prefix": "POLICY-WAIVER:",
        "controller_only_ship_allowed": True,
    },
    "required_authoritative_files": [
        "controller/main.py",
        "rules/writing_structural_rules.json",
        "rules/systems_governance_rules.json",
        "issues/open_issues.json",
        "state/run_history.json",
    ],
    "markers": {
        "false_completion": [
            "already fixed",
            "already resolved",
            "done already",
            "resolved already",
        ],
        "planning": [
            "i will",
            "plan to",
            "next step",
            "roadmap",
            "todo",
            "later",
            "going to",
        ],
    },
}

DEFAULT_ISSUE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Persistent agent issue",
    "type": "object",
    "required": [
        "issue_id",
        "title",
        "category",
        "status",
        "severity",
        "blocking",
        "purpose",
        "rule_id",
        "history",
        "first_seen",
        "last_seen",
    ],
    "properties": {
        "issue_id": {"type": "string"},
        "title": {"type": "string"},
        "category": {"type": "string"},
        "status": {"enum": ["OPEN", "PARTIAL", "RESOLVED", "BLOCKED", "WAIVED"]},
        "severity": {"enum": ["warning", "error", "critical"]},
        "blocking": {"type": "boolean"},
        "purpose": {"type": "string"},
        "rule_id": {"type": "string"},
        "scope": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "history": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["run_id", "timestamp", "event", "status"],
                "properties": {
                    "run_id": {"type": "string"},
                    "timestamp": {"type": "string"},
                    "event": {"type": "string"},
                    "status": {"enum": ["OPEN", "PARTIAL", "RESOLVED", "BLOCKED", "WAIVED"]},
                    "note": {"type": "string"},
                },
            },
        },
        "first_seen": {"type": "string"},
        "last_seen": {"type": "string"},
        "waiver": {
            "type": "object",
            "properties": {
                "policy_marker": {"type": "string"},
                "reason": {"type": "string"},
            },
        },
        "resolution": {
            "type": "object",
            "properties": {
                "evidence": {"type": "string"},
                "timestamp": {"type": "string"},
                "run_id": {"type": "string"},
            },
        },
    },
}

DEFAULT_AUDIT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Persistent agent audit result",
    "type": "object",
    "required": [
        "run_id",
        "timestamp",
        "task_type",
        "audit_types",
        "findings",
        "ship_allowed",
        "decision",
    ],
    "properties": {
        "run_id": {"type": "string"},
        "timestamp": {"type": "string"},
        "task_type": {"type": "string"},
        "audit_types": {"type": "array", "items": {"type": "string"}},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["issue_id", "rule_id", "title", "status", "blocking"],
                "properties": {
                    "issue_id": {"type": "string"},
                    "rule_id": {"type": "string"},
                    "title": {"type": "string"},
                    "status": {"enum": ["OPEN", "PARTIAL", "RESOLVED", "BLOCKED", "WAIVED"]},
                    "blocking": {"type": "boolean"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "ship_allowed": {"type": "boolean"},
        "decision": {
            "type": "object",
            "required": ["route", "blocked", "reason"],
            "properties": {
                "route": {"type": "string"},
                "blocked": {"type": "boolean"},
                "reason": {"type": "string"},
            },
        },
        "unresolved_issue_ids": {"type": "array", "items": {"type": "string"}},
    },
}

DEFAULT_ISSUE_REGISTRY = {
    "version": "1.0.0",
    "policy": {
        "allowed_states": ["OPEN", "PARTIAL", "RESOLVED", "BLOCKED", "WAIVED"],
        "unresolved_states_block_ship": ["OPEN", "PARTIAL", "BLOCKED"],
        "partial_never_resolves_shipping": True,
        "waiver_policy_marker_prefix": "POLICY-WAIVER:",
        "controller_only_ship_allowed": True,
    },
    "issues": [],
}

DEFAULT_RUN_HISTORY = {
    "version": "1.0.0",
    "runs": [],
}

DEFAULT_AUDIT_INDEX = {
    "version": "1.0.0",
    "canonical_repo_root": str(CANONICAL_REPO_ROOT),
    "audit_storage_root": "audits/by_agent",
    "output_storage_root": "outputs/by_agent",
    "submission_storage_root": "inputs/by_agent",
    "latest_by_agent": {},
    "latest_heartbeat_phase_by_agent": {},
    "runs": [],
}

DEFAULT_WORKSPACE_POLICY = {
    "version": "1.0.0",
    "canonical_repo_root": str(CANONICAL_REPO_ROOT),
    "canonical_workspace_doc": "CANONICAL_WORKSPACE.md",
    "readme_path": "README.md",
    "approved_entrypoints": [
        "bin/glyph-controller",
        "bin/glyph-audit-submit",
        "bin/glyph-audit-summary",
    ],
    "direct_cli_policy": {
        "default_behavior": "reject",
        "override_env": ALLOW_DIRECT_CLI_ENV,
    },
    "audit_submission": {
        "required_context_fields": ["agent_id", "task_type", "task_scope", "purpose", "governance_refs"],
        "preferred_entrypoint": "bin/glyph-audit-submit",
        "audit_index_path": "state/audit_index.json",
        "run_history_path": "state/run_history.json",
        "issue_registry_path": "issues/open_issues.json",
        "audit_root": "audits/by_agent",
        "output_root": "outputs/by_agent",
        "submission_root": "inputs/by_agent",
    },
    "heartbeat": {
        "state_path": "state/heartbeat_state.json",
        "event_retention_limit": 200,
        "window_sequence": [10, 20, 40],
    },
    "content": {
        "route_map_path": "GLYPH_ROUTE_MAP.json",
        "cache_path": "state/notion_content_cache.json",
        "default_portal_route": "portal",
        "notion_token_env": ["NOTION_TOKEN", "NOTION_API_TOKEN"],
    },
    "preflight_chain": {
        "default": [
            "README.md",
            "CANONICAL_WORKSPACE.md",
            "GLYPH_WORKSPACE_POLICY.json",
        ],
        "actions": {
            "agent_audit": ["DAILY_AGENT_AUDIT_PROTOCOL.md"],
            "audit_summary": ["DAILY_AGENT_AUDIT_PROTOCOL.md"],
            "route_content": ["GLYPH_ROUTE_MAP.json"],
            "heartbeat": [],
        },
    },
}

DEFAULT_AGENT_SUBMISSION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Glyph agent audit submission",
    "type": "object",
    "required": ["task_type"],
    "properties": {
        "task_type": {"enum": ["writing", "systems", "mixed"]},
        "task_id": {"type": "string"},
        "task_scope": {"type": "string"},
        "purpose": {"type": "string"},
        "agent_id": {"type": "string"},
        "audit_scope": {"type": "string"},
        "governance_refs": {"type": "array", "items": {"type": "string"}},
        "claims": {"type": "array", "items": {}},
        "deltas": {"type": "array", "items": {}},
        "routes": {"type": "array", "items": {}},
        "pages": {"type": "array", "items": {}},
        "entities": {"type": "array", "items": {}},
        "executed_changes": {"type": "array", "items": {}},
        "resolution_attempts": {"type": "array", "items": {}},
        "metadata": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "agent_role": {"type": "string"},
                "audit_scope": {"type": "string"},
                "schedule_name": {"type": "string"},
                "heartbeat_phase": {"type": "string"},
            },
        },
    },
}

DEFAULT_HEARTBEAT_STATE = {
    "version": "1.0.0",
    "cycle": 1,
    "window_index": 0,
    "window_sequence": [10, 20, 40],
    "current_window": 10,
    "tick_in_cycle": 0,
    "ticks_while_waiting": 0,
    "waiting_for_tock": False,
    "phase": "active",
    "created_at": None,
    "updated_at": None,
    "last_tock_at": None,
    "last_cycle_close_at": None,
    "last_convergence_at": None,
    "last_event": None,
    "agent_activity": {},
    "counters": {
        "tock": 0,
        "cycle_close": 0,
        "convergence": 0,
        "artifact_dispatch": 0,
        "agent_audit": 0,
        "health_transition": 0,
    },
    "recent_events": [],
}

DEFAULT_NOTION_CONTENT_CACHE = {
    "version": "1.0.0",
    "updated_at": None,
    "routes": {},
}

DEFAULT_ROUTE_MAP = {
    "version": "1.0.0",
    "public_title": "The Glyph Study",
    "routes": {
        "home": {
            "path": "/",
            "legacy_paths": ["/docs_index.html", "/index.html"],
            "page_id": "f87a5404-841c-4d39-bd23-69b980001e14",
            "page_url": "https://www.notion.so/f87a5404841c4d39bd2369b980001e14",
            "page_title": "PUBLIC DIRECTORY — Heyer Livin’ / Glyph Ecosystem",
            "content_role": "landing",
        },
        "research": {
            "path": "/research",
            "legacy_paths": ["/research.html"],
            "page_id": "32a7097e-f44e-81a1-bffd-ff3dabc94977",
            "page_url": "https://www.notion.so/32a7097ef44e81a1bffdff3dabc94977",
            "page_title": "RESEARCH — Jonah Study",
            "content_role": "study",
        },
        "story": {
            "path": "/story",
            "legacy_paths": ["/story.html"],
            "page_id": "908c53bf-a8c5-4ec6-9fb8-d0b156a48dd1",
            "page_url": "https://www.notion.so/908c53bfa8c54ec69fb8d0b156a48dd1",
            "page_title": "STORY (NARRATIVE)",
            "content_role": "narrative",
        },
        "dictionary": {
            "path": "/dictionary",
            "legacy_paths": ["/dictionary.html"],
            "page_id": "33d7097e-f44e-8188-b665-fabb8ee3f352",
            "page_url": "https://www.notion.so/33d7097ef44e8188b665fabb8ee3f352",
            "page_title": "GLYPH_DICTIONARY",
            "content_role": "reference",
        },
        "filing": {
            "path": "/filing",
            "legacy_paths": ["/filing.html"],
            "page_id": "32a7097e-f44e-815a-ae00-cc6d11a4e909",
            "page_url": "https://www.notion.so/32a7097ef44e815aae00cc6d11a4e909",
            "page_title": "LEGAL — Documentation",
            "content_role": "legal",
        },
        "scholarship": {
            "path": "/scholarship",
            "legacy_paths": ["/scholarship.html"],
            "page_id": "320260af-09af-415f-9141-985c437a9277",
            "page_url": "https://www.notion.so/320260af09af415f9141985c437a9277",
            "page_title": "Public Portfolio — Stream",
            "content_role": "portfolio",
        },
        "portal": {
            "path": "/portal",
            "legacy_paths": ["/portal.html"],
            "page_id": "320260af-09af-415f-9141-985c437a9277",
            "page_url": "https://www.notion.so/320260af09af415f9141985c437a9277",
            "page_title": "Public Portfolio — Stream",
            "content_role": "blog",
            "blog_database_id": "5d1374c3-b39b-496b-ab60-86ab136e900e",
            "blog_data_source_id": "d2accd5f-4558-4116-bdc1-0b96ca65713e",
        },
        "arcade": {
            "path": "/arcade",
            "legacy_paths": ["/arcade.html"],
            "page_title": "Glyph Arcade",
            "content_role": "tools",
            "static_source": "repo",
        },
    },
}

DEFAULT_AGENT_SUBMISSION_TEMPLATE = {
    "task_type": "systems",
    "task_id": "daily-pass",
    "task_scope": "daily-pass",
    "purpose": "Audit the current state against the canonical repo rules.",
    "metadata": {
        "agent_id": "replace-with-agent-id",
        "agent_role": "daily-auditor",
        "audit_scope": "daily-pass",
        "schedule_name": "daily-pass",
    },
    "governance_refs": [
        "controller/main.py",
        "rules/writing_structural_rules.json",
        "rules/systems_governance_rules.json",
        "issues/open_issues.json",
        "state/run_history.json",
    ],
    "executed_changes": [],
    "claims": [],
    "deltas": [],
}

DEFAULT_PROMPTS = {
    "prompts/writer.md": """# Writer

The repo is the source of truth. Write to real repo files. Do not declare success.
The controller decides whether shipping is allowed.

Before producing output:
- read the controller rulepacks
- preserve unresolved issue context from `issues/open_issues.json`
- keep purpose explicit
- avoid editorial smoothing and patterned rhetoric
""",
    "prompts/writing_auditor.md": """# Writing Auditor

Audit structure, not authorship. Look for repeated framing, mirrored open/close shape,
policy-brief opener habits, rhetorical symmetry, repeated thesis claims, credentialing,
uniform cadence, announced metaphors, and repeated four-item list habits.

Do not clear issues. Emit findings only. The controller manages issue state.
""",
    "prompts/systems_auditor.md": """# Systems Auditor

Check the output against repo governance and execution reality.

Audit for:
- contradiction between claim and rule
- false completion
- missing purpose
- naming drift
- routes with no consumer
- pages that do not fulfill purpose
- governance drift
- unresolved deltas
- planning instead of execution
- partial rectification without resolution
""",
    "prompts/reviser.md": """# Reviser

Address only the specific unresolved issues in the issue registry. Do not mark work
resolved. Do not call partial work complete. Preserve repo terminology and structure
unless exact revision flags allow a broader rewrite.
""",
    "prompts/daily_agent_operator.md": """# Daily Agent Operator

Read these first:
- `README.md`
- `CANONICAL_WORKSPACE.md`
- `GLYPH_WORKSPACE_POLICY.json`
- `DAILY_AGENT_AUDIT_PROTOCOL.md`

Rules:
- Use only the canonical Glyph workspace.
- Submit audits through `bin/glyph-audit-submit`.
- Do not write directly into `audits/`, `outputs/`, `inputs/`, `state/`, or `issues/`.
- Always include your `agent_id`, `task_type`, `task_scope`, and the canonical governance refs.
- Report the returned `audit_path` and unresolved issue ids.
""",
}

DEFAULT_REPO_README = """# The Glyph Study

This repository is the canonical Glyph workspace and the single operational root for:

- repo-owned public routes
- Notion-backed study content rendering
- heartbeat state
- agent audit ingestion
- cleanup and cross-agent summaries

Required preflight chain for governed actions:

1. `README.md`
2. `CANONICAL_WORKSPACE.md`
3. `GLYPH_WORKSPACE_POLICY.json`
4. the task-specific governance file named by policy

Start here:

- [CANONICAL_WORKSPACE.md](/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/CANONICAL_WORKSPACE.md)
- [GLYPH_WORKSPACE_POLICY.json](/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/GLYPH_WORKSPACE_POLICY.json)
- [GLYPH_ROUTE_MAP.json](/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/GLYPH_ROUTE_MAP.json)
- [DAILY_AGENT_AUDIT_PROTOCOL.md](/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/DAILY_AGENT_AUDIT_PROTOCOL.md)

Canonical entrypoints:

- [bin/glyph-controller](/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/bin/glyph-controller)
- [bin/glyph-audit-submit](/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/bin/glyph-audit-submit)
- [bin/glyph-audit-summary](/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/bin/glyph-audit-summary)

Canonical state files:

- [state/audit_index.json](/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/state/audit_index.json)
- [state/heartbeat_state.json](/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/state/heartbeat_state.json)
- [state/notion_content_cache.json](/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/state/notion_content_cache.json)

Public route model:

- `/` home hub
- `/research`
- `/story`
- `/dictionary`
- `/filing`
- `/scholarship`
- `/portal` daily blog plus separate system updates
- `/arcade` repo-owned tools

Notion content is rendered into repo-owned pages on the server. The portal keeps authored stream content separate from audit and heartbeat status by design.
"""

DEFAULT_CANONICAL_WORKSPACE = """# Canonical Workspace

This repository is the canonical source of truth for the Glyph controller workspace.

Canonical repository root:

`/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH`

Canonical launcher:

`/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH/bin/glyph-controller`

## Reality Rule

There is one real workspace for this system:

`/Volumes/G-Workspace/Repos/active/DAreconstructedGLYPH`

Any symlink, alias path, shortcut, or alternate entry path is only an alias to this same workspace and must resolve back to the canonical repository root above.

## Operational Rules

1. Do not create a second live copy of this repository for normal operation.
2. Do not rename the canonical repository without intentionally migrating the full audit and issue history.
3. Treat all audits, issue registries, run history, rules, outputs, and state files in this repository as the single active record.
4. Read the required governance preflight chain before acting: `README.md`, `CANONICAL_WORKSPACE.md`, `GLYPH_WORKSPACE_POLICY.json`, then the task-specific governance file.
5. If a tool is launched from an alias or symlink, it should still resolve to the canonical repository root before writing files.
6. If a tool cannot access this repository, it should report that explicitly instead of silently creating a parallel workspace elsewhere.

## Important Scope

This document defines the canonical structure for the Glyph workspace. It does not force every application on the computer to obey automatically, but it establishes the intended source of truth for operators, agents, wrappers, and launchers.
"""

DEFAULT_DAILY_AGENT_PROTOCOL = """# Daily Agent Audit Protocol

All external agent passes must submit into the canonical Glyph workspace.

## Required fields

- `agent_id`
- `task_type`
- `task_scope`
- `purpose`
- `governance_refs`

## Canonical flow

1. Read `README.md`.
2. Read `CANONICAL_WORKSPACE.md`.
3. Read `GLYPH_WORKSPACE_POLICY.json`.
4. Submit through `bin/glyph-audit-submit`.
5. Let the controller place snapshots in:
   - `inputs/by_agent/...`
   - `outputs/by_agent/...`
   - `audits/by_agent/...`
6. Read aggregate status from `state/audit_index.json`.

## Separation rule

- Authored content stays separate from system-generated status.
- Audit metadata must not be mixed into authored route content.
- Portal/blog uses authored stream content first and system status second.
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _timestamp_parts(timestamp: str) -> tuple[str, str, str]:
    date_part = timestamp.split("T", 1)[0]
    year, month, day = date_part.split("-")
    return year, month, day


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _deep_merge_defaults(current: Any, default: Any) -> Any:
    if isinstance(current, dict) and isinstance(default, dict):
        merged = dict(current)
        for key, default_value in default.items():
            if key not in merged:
                merged[key] = _json_clone(default_value)
            else:
                merged[key] = _deep_merge_defaults(merged[key], default_value)
        return merged
    if isinstance(current, list):
        return current
    return current


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return _json_clone(default)
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _safe_slug(value: str, *, default: str = "manual") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
    return slug or default


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _split_sentences(text: str) -> list[str]:
    raw_parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [part.strip() for part in raw_parts if part and part.strip()]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _ngram_counts(tokens: list[str], size: int) -> Counter[str]:
    grams = [" ".join(tokens[index : index + size]) for index in range(max(0, len(tokens) - size + 1))]
    return Counter(gram for gram in grams if gram.strip())


def _sentence_similarity(left: str, right: str) -> float:
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    base = min(len(left_tokens), len(right_tokens))
    return overlap / base


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _stable_issue_id(rule_id: str, scope: str) -> str:
    digest = hashlib.sha1(f"{rule_id}:{scope}".encode("utf-8")).hexdigest()[:12]
    return f"{rule_id}:{digest}"


def _validate_waiver(issue: dict[str, Any], policy_prefix: str) -> bool:
    if issue.get("status") != "WAIVED":
        return True
    waiver = issue.get("waiver") or {}
    marker = waiver.get("policy_marker", "")
    return isinstance(marker, str) and marker.startswith(policy_prefix)


def _default_status_blocks(status: str) -> bool:
    return status in UNRESOLVED_ISSUE_STATES


def _allow_noncanonical_repo_root() -> bool:
    return os.environ.get("GLYPH_ALLOW_NONCANONICAL_REPO_ROOT", "").strip() == "1"


def _allow_direct_cli() -> bool:
    return os.environ.get(ALLOW_DIRECT_CLI_ENV, "").strip() == "1"


def _require_approved_entrypoint() -> None:
    approved = os.environ.get(APPROVED_ENTRYPOINT_ENV, "").strip() == "1"
    if approved or _allow_direct_cli():
        return
    raise SystemExit(
        "Refusing direct controller CLI access. Use bin/glyph-controller, "
        "bin/glyph-audit-submit, or bin/glyph-audit-summary."
    )


def _validate_repo_root(repo_root: Path, *, allow_noncanonical: bool) -> Path:
    resolved = repo_root.resolve()
    if allow_noncanonical or _allow_noncanonical_repo_root():
        return resolved
    if resolved != CANONICAL_REPO_ROOT:
        raise ValueError(
            "Refusing to run against a non-canonical repo root. "
            f"Expected {CANONICAL_REPO_ROOT}, received {resolved}."
        )
    return resolved


class PersistentController:
    def __init__(self, repo_root: str | Path, *, allow_noncanonical: bool = False):
        self.repo_root = _validate_repo_root(Path(repo_root), allow_noncanonical=allow_noncanonical)
        self.bootstrap_repository()

    @property
    def issues_path(self) -> Path:
        return self.repo_root / "issues" / "open_issues.json"

    @property
    def run_history_path(self) -> Path:
        return self.repo_root / "state" / "run_history.json"

    @property
    def audit_index_path(self) -> Path:
        return self.repo_root / "state" / "audit_index.json"

    @property
    def workspace_policy_path(self) -> Path:
        return self.repo_root / "GLYPH_WORKSPACE_POLICY.json"

    @property
    def readme_path(self) -> Path:
        return self.repo_root / "README.md"

    @property
    def canonical_workspace_path(self) -> Path:
        return self.repo_root / "CANONICAL_WORKSPACE.md"

    @property
    def route_map_path(self) -> Path:
        return self.repo_root / "GLYPH_ROUTE_MAP.json"

    @property
    def daily_agent_protocol_path(self) -> Path:
        return self.repo_root / "DAILY_AGENT_AUDIT_PROTOCOL.md"

    @property
    def writing_rules_path(self) -> Path:
        return self.repo_root / "rules" / "writing_structural_rules.json"

    @property
    def systems_rules_path(self) -> Path:
        return self.repo_root / "rules" / "systems_governance_rules.json"

    def bootstrap_repository(self) -> list[str]:
        created_or_upgraded: list[str] = []
        for relative_dir in (
            "rules",
            "issues",
            "audits",
            "audits/by_agent",
            "state",
            "outputs",
            "outputs/by_agent",
            "inputs",
            "inputs/by_agent",
            "prompts",
            "schemas",
            "templates",
            "tests",
        ):
            directory = self.repo_root / relative_dir
            directory.mkdir(parents=True, exist_ok=True)

        template_map: dict[str, Any] = {
            "rules/writing_structural_rules.json": DEFAULT_WRITING_RULES,
            "rules/systems_governance_rules.json": DEFAULT_SYSTEMS_RULES,
            "schemas/issue.schema.json": DEFAULT_ISSUE_SCHEMA,
            "schemas/audit_result.schema.json": DEFAULT_AUDIT_SCHEMA,
            "schemas/agent_submission.schema.json": DEFAULT_AGENT_SUBMISSION_SCHEMA,
            "issues/open_issues.json": DEFAULT_ISSUE_REGISTRY,
            "state/run_history.json": DEFAULT_RUN_HISTORY,
            "state/audit_index.json": DEFAULT_AUDIT_INDEX,
            "state/heartbeat_state.json": DEFAULT_HEARTBEAT_STATE,
            "state/notion_content_cache.json": DEFAULT_NOTION_CONTENT_CACHE,
            "templates/agent_submission_template.json": DEFAULT_AGENT_SUBMISSION_TEMPLATE,
            "GLYPH_WORKSPACE_POLICY.json": DEFAULT_WORKSPACE_POLICY,
            "GLYPH_ROUTE_MAP.json": DEFAULT_ROUTE_MAP,
        }
        for relative_path, template in template_map.items():
            path = self.repo_root / relative_path
            if path.exists():
                current = _read_json(path, template)
                merged = _deep_merge_defaults(current, template)
                if merged != current:
                    _write_json(path, merged)
                    created_or_upgraded.append(relative_path)
            else:
                _write_json(path, template)
                created_or_upgraded.append(relative_path)

        for relative_path, content in DEFAULT_PROMPTS.items():
            path = self.repo_root / relative_path
            if not path.exists():
                path.write_text(content.rstrip() + "\n", encoding="utf-8")
                created_or_upgraded.append(relative_path)

        markdown_templates = {
            "README.md": DEFAULT_REPO_README,
            "CANONICAL_WORKSPACE.md": DEFAULT_CANONICAL_WORKSPACE,
            "DAILY_AGENT_AUDIT_PROTOCOL.md": DEFAULT_DAILY_AGENT_PROTOCOL,
        }
        for relative_path, content in markdown_templates.items():
            path = self.repo_root / relative_path
            if not path.exists():
                path.write_text(content.rstrip() + "\n", encoding="utf-8")
                created_or_upgraded.append(relative_path)

        return created_or_upgraded

    def load_workspace_policy(self) -> dict[str, Any]:
        policy = _read_json(self.workspace_policy_path, DEFAULT_WORKSPACE_POLICY)
        return _deep_merge_defaults(policy, DEFAULT_WORKSPACE_POLICY)

    def governance_preflight(self, *, action: str) -> dict[str, Any]:
        policy = self.load_workspace_policy()
        chain_config = policy.get("preflight_chain", {})
        ordered_paths: list[str] = []
        for relative_path in chain_config.get("default", []):
            relative = str(relative_path)
            if relative not in ordered_paths:
                ordered_paths.append(relative)
        for relative_path in chain_config.get("actions", {}).get(action, []):
            relative = str(relative_path)
            if relative not in ordered_paths:
                ordered_paths.append(relative)

        loaded_at = _utc_now_iso()
        loaded_files: list[dict[str, Any]] = []
        for relative_path in ordered_paths:
            path = self.repo_root / relative_path
            if not path.exists():
                raise FileNotFoundError(
                    f"Missing governance file required before action '{action}': {relative_path}"
                )
            raw_text = path.read_text(encoding="utf-8")
            loaded_files.append(
                {
                    "path": relative_path,
                    "sha256": _sha256_text(raw_text),
                    "bytes": len(raw_text.encode("utf-8")),
                    "loaded_at": loaded_at,
                }
            )

        return {
            "action": action,
            "canonical_repo_root": str(self.repo_root),
            "policy_version": str(policy.get("version") or "unknown"),
            "required_paths": ordered_paths,
            "files": loaded_files,
            "loaded_at": loaded_at,
        }

    def _resolve_audit_context(self, submission: dict[str, Any], *, task_type: str, timestamp: str) -> dict[str, Any]:
        metadata = dict(submission.get("metadata") or {})
        agent = submission.get("agent")

        raw_agent_id = (
            submission.get("agent_id")
            or metadata.get("agent_id")
            or (agent.get("id") if isinstance(agent, dict) else None)
            or (agent if isinstance(agent, str) else None)
            or "manual"
        )
        agent_label = (
            submission.get("agent_label")
            or metadata.get("agent_label")
            or (agent.get("name") if isinstance(agent, dict) else None)
            or str(raw_agent_id)
        )
        agent_role = (
            submission.get("agent_role")
            or metadata.get("agent_role")
            or (agent.get("role") if isinstance(agent, dict) else None)
            or "unspecified"
        )
        audit_scope = (
            submission.get("audit_scope")
            or metadata.get("audit_scope")
            or metadata.get("schedule_name")
            or task_type
        )
        task_scope = str(submission.get("task_scope") or submission.get("task_id") or audit_scope or task_type)
        year, month, day = _timestamp_parts(timestamp)
        return {
            "agent_id": _safe_slug(str(raw_agent_id), default="manual"),
            "agent_label": str(agent_label),
            "agent_role": str(agent_role),
            "audit_scope": _safe_slug(str(audit_scope), default=task_type),
            "task_scope": task_scope,
            "schedule_name": str(metadata.get("schedule_name") or ""),
            "entrypoint": os.environ.get(ENTRYPOINT_NAME_ENV, "programmatic"),
            "canonical_repo_root": str(self.repo_root),
            "date": f"{year}-{month}-{day}",
        }

    def _structured_json_path(self, base_dir: str, *, agent_id: str, audit_scope: str, run_id: str, timestamp: str) -> Path:
        year, month, day = _timestamp_parts(timestamp)
        filename = f"{audit_scope}_{run_id}.json"
        return self.repo_root / base_dir / "by_agent" / agent_id / year / month / day / filename

    def rebuild_audit_index(self) -> dict[str, Any]:
        run_history = _read_json(self.run_history_path, DEFAULT_RUN_HISTORY)
        run_history = _deep_merge_defaults(run_history, DEFAULT_RUN_HISTORY)
        rebuilt = _json_clone(DEFAULT_AUDIT_INDEX)
        rebuilt["canonical_repo_root"] = str(self.repo_root)

        for run in run_history.get("runs", []):
            agent_id = _safe_slug(str(run.get("agent_id") or "manual"), default="manual")
            entry = {
                "run_id": str(run.get("run_id") or ""),
                "timestamp": str(run.get("timestamp") or ""),
                "task_type": str(run.get("task_type") or ""),
                "agent_id": agent_id,
                "audit_scope": str(run.get("audit_scope") or ""),
                "entrypoint": str(run.get("entrypoint") or ""),
                "ship_allowed": bool(run.get("ship_allowed")),
                "route": str(run.get("route") or ""),
                "agent_label": str(run.get("agent_label") or agent_id),
                "agent_role": str(run.get("agent_role") or ""),
                "schedule_name": str(run.get("schedule_name") or ""),
                "heartbeat_phase": str(run.get("heartbeat_phase") or ""),
                "audit_path": str(run.get("audit_path") or ""),
                "raw_output_path": str(run.get("raw_output_path") or ""),
                "submission_snapshot_path": str(run.get("submission_snapshot_path") or ""),
                "unresolved_issue_ids": list(run.get("unresolved_issue_ids") or []),
            }
            rebuilt["runs"].append(entry)
            latest = rebuilt["latest_by_agent"].get(agent_id)
            if not latest or entry["timestamp"] >= str(latest.get("timestamp") or ""):
                rebuilt["latest_by_agent"][agent_id] = entry
            if entry["heartbeat_phase"]:
                rebuilt["latest_heartbeat_phase_by_agent"][agent_id] = entry["heartbeat_phase"]

        _write_json(self.audit_index_path, rebuilt)
        return rebuilt

    def audit_summary(self, agent_id: str | None = None) -> dict[str, Any]:
        governance_preflight = self.governance_preflight(action="audit_summary")
        index = _read_json(self.audit_index_path, DEFAULT_AUDIT_INDEX)
        index = _deep_merge_defaults(index, DEFAULT_AUDIT_INDEX)
        normalized_agent = _safe_slug(agent_id, default="manual") if agent_id else None
        runs = index.get("runs", [])
        if normalized_agent:
            runs = [run for run in runs if _safe_slug(str(run.get("agent_id") or "manual"), default="manual") == normalized_agent]

        registry = self.load_issue_registry()
        unresolved = self._collect_unresolved_issues(registry)
        latest_by_agent = index.get("latest_by_agent", {})
        agents = {
            key: {
                "latest_run_id": value.get("run_id"),
                "latest_timestamp": value.get("timestamp"),
                "audit_path": value.get("audit_path"),
                "raw_output_path": value.get("raw_output_path"),
                "submission_snapshot_path": value.get("submission_snapshot_path"),
                "unresolved_issue_ids": value.get("unresolved_issue_ids", []),
                "last_heartbeat_phase": value.get("heartbeat_phase") or index.get("latest_heartbeat_phase_by_agent", {}).get(key),
                "agent_label": value.get("agent_label", key),
                "agent_role": value.get("agent_role", ""),
                "schedule_name": value.get("schedule_name", ""),
            }
            for key, value in latest_by_agent.items()
            if not normalized_agent or key == normalized_agent
        }
        return {
            "canonical_repo_root": str(self.repo_root),
            "agent_filter": normalized_agent,
            "run_count": len(runs),
            "latest_by_agent": latest_by_agent,
            "agents": agents,
            "unresolved_issue_count": len(unresolved),
            "unresolved_issue_ids": [issue["issue_id"] for issue in unresolved],
            "audit_storage_root": index.get("audit_storage_root"),
            "output_storage_root": index.get("output_storage_root"),
            "submission_storage_root": index.get("submission_storage_root"),
            "governance_preflight": governance_preflight,
        }

    def classify_task_type(self, submission: dict[str, Any]) -> str:
        explicit = str(submission.get("task_type", "")).strip().lower()
        if explicit in {"writing", "systems", "mixed"}:
            return explicit
        if any(key in submission for key in ("routes", "pages", "claims", "deltas", "governance_refs", "rule_checks")):
            return "systems"
        return "writing"

    def load_issue_registry(self) -> dict[str, Any]:
        registry = _read_json(self.issues_path, DEFAULT_ISSUE_REGISTRY)
        registry = _deep_merge_defaults(registry, DEFAULT_ISSUE_REGISTRY)
        policy_prefix = registry["policy"]["waiver_policy_marker_prefix"]
        for issue in registry.get("issues", []):
            if issue.get("status") == "WAIVED" and not _validate_waiver(issue, policy_prefix):
                issue["status"] = "OPEN"
                issue.setdefault("history", []).append(
                    {
                        "run_id": "bootstrap",
                        "timestamp": _utc_now_iso(),
                        "event": "invalid_waiver_rejected",
                        "status": "OPEN",
                        "note": "WAIVED requires an explicit policy marker in file.",
                    }
                )
        return registry

    def run(self, submission: dict[str, Any]) -> dict[str, Any]:
        run_id = f"run_{_timestamp_slug()}_{uuid.uuid4().hex[:8]}"
        timestamp = _utc_now_iso()
        task_type = self.classify_task_type(submission)
        governance_preflight = self.governance_preflight(action="agent_audit")
        audit_context = self._resolve_audit_context(submission, task_type=task_type, timestamp=timestamp)
        metadata = dict(submission.get("metadata") or {})
        heartbeat_phase = str(
            submission.get("heartbeat_phase")
            or metadata.get("heartbeat_phase")
            or audit_context["audit_scope"]
        )
        submission_snapshot_path = self._structured_json_path(
            "inputs",
            agent_id=audit_context["agent_id"],
            audit_scope=audit_context["audit_scope"],
            run_id=run_id,
            timestamp=timestamp,
        )
        raw_output_path = self._structured_json_path(
            "outputs",
            agent_id=audit_context["agent_id"],
            audit_scope=audit_context["audit_scope"],
            run_id=run_id,
            timestamp=timestamp,
        )
        audit_path = self._structured_json_path(
            "audits",
            agent_id=audit_context["agent_id"],
            audit_scope=audit_context["audit_scope"],
            run_id=run_id,
            timestamp=timestamp,
        )
        submission_snapshot = copy.deepcopy(submission)
        submission_snapshot.setdefault("metadata", {})
        submission_snapshot["metadata"].update(
            {
                "agent_id": audit_context["agent_id"],
                "agent_label": audit_context["agent_label"],
                "agent_role": audit_context["agent_role"],
                "audit_scope": audit_context["audit_scope"],
                "schedule_name": audit_context["schedule_name"],
                "heartbeat_phase": heartbeat_phase,
                "entrypoint": audit_context["entrypoint"],
            }
        )
        _write_json(
            submission_snapshot_path,
            {
                "run_id": run_id,
                "timestamp": timestamp,
                "task_type": task_type,
                "governance_preflight": governance_preflight,
                "submission": submission_snapshot,
            },
        )
        _write_json(
            raw_output_path,
            {
                "run_id": run_id,
                "timestamp": timestamp,
                "task_type": task_type,
                "audit_context": audit_context,
                "heartbeat_phase": heartbeat_phase,
                "governance_preflight": governance_preflight,
                "submission": submission_snapshot,
            },
        )

        registry = self.load_issue_registry()
        preexisting_unresolved = self._collect_unresolved_issues(registry)
        findings: list[dict[str, Any]] = []
        audit_types: list[str] = []

        if task_type in {"writing", "mixed"}:
            findings.extend(self._run_writing_audit(submission))
            audit_types.append("writing")
        if task_type in {"systems", "mixed"}:
            findings.extend(self._run_systems_audit(submission, preexisting_unresolved))
            audit_types.append("systems")

        registry, unresolved_issue_ids = self._merge_findings(
            registry=registry,
            findings=findings,
            run_id=run_id,
            timestamp=timestamp,
            resolution_attempts=self._normalize_resolution_attempts(submission),
        )

        ship_allowed = not unresolved_issue_ids
        decision = {
            "route": "finalize" if ship_allowed else "revision",
            "blocked": not ship_allowed,
            "reason": "no unresolved issues remain" if ship_allowed else "unresolved issues block finalization",
        }
        audit_result = {
            "run_id": run_id,
            "timestamp": timestamp,
            "task_type": task_type,
            "audit_types": audit_types,
            "findings": findings,
            "ship_allowed": ship_allowed,
            "decision": decision,
            "unresolved_issue_ids": unresolved_issue_ids,
            "agent_id": audit_context["agent_id"],
            "agent_label": audit_context["agent_label"],
            "agent_role": audit_context["agent_role"],
            "task_scope": audit_context["task_scope"],
            "audit_scope": audit_context["audit_scope"],
            "schedule_name": audit_context["schedule_name"],
            "heartbeat_phase": heartbeat_phase,
            "entrypoint": audit_context["entrypoint"],
            "governance_preflight": governance_preflight,
            "submission_snapshot_path": _repo_relative(submission_snapshot_path, self.repo_root),
            "raw_output_path": _repo_relative(raw_output_path, self.repo_root),
            "registry_path": _repo_relative(self.issues_path, self.repo_root),
        }
        _write_json(audit_path, audit_result)
        audit_result["audit_path"] = _repo_relative(audit_path, self.repo_root)

        run_history = _read_json(self.run_history_path, DEFAULT_RUN_HISTORY)
        run_history = _deep_merge_defaults(run_history, DEFAULT_RUN_HISTORY)
        run_history["runs"].append(
            {
                "run_id": run_id,
                "timestamp": timestamp,
                "task_type": task_type,
                "audit_types": audit_types,
                "ship_allowed": ship_allowed,
                "route": decision["route"],
                "agent_id": audit_context["agent_id"],
                "agent_label": audit_context["agent_label"],
                "agent_role": audit_context["agent_role"],
                "audit_scope": audit_context["audit_scope"],
                "task_scope": audit_context["task_scope"],
                "schedule_name": audit_context["schedule_name"],
                "heartbeat_phase": heartbeat_phase,
                "entrypoint": audit_context["entrypoint"],
                "raw_output_path": audit_result["raw_output_path"],
                "audit_path": audit_result["audit_path"],
                "submission_snapshot_path": audit_result["submission_snapshot_path"],
                "unresolved_issue_ids": unresolved_issue_ids,
                "governance_paths": governance_preflight["required_paths"],
            }
        )

        _write_json(self.issues_path, registry)
        _write_json(self.run_history_path, run_history)
        _write_json(audit_path, audit_result)
        self.rebuild_audit_index()
        return audit_result

    def _normalize_resolution_attempts(self, submission: dict[str, Any]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for item in _as_list(submission.get("resolution_attempts")):
            if isinstance(item, str):
                normalized[item] = {"issue_id": item}
            elif isinstance(item, dict) and item.get("issue_id"):
                normalized[str(item["issue_id"])] = dict(item)
        return normalized

    def _run_writing_audit(self, submission: dict[str, Any]) -> list[dict[str, Any]]:
        rules = _read_json(self.writing_rules_path, DEFAULT_WRITING_RULES)
        thresholds = rules["thresholds"]
        markers = rules["markers"]
        text = str(submission.get("content") or submission.get("output") or submission.get("raw_output") or "")
        metadata = submission.get("metadata") or {}
        scope_base = str(submission.get("task_scope") or submission.get("task_id") or "writing-output")

        findings: list[dict[str, Any]] = []
        tokens = _tokenize(text)
        sentences = _split_sentences(text)
        normalized_sentences = [_normalize_text(sentence) for sentence in sentences]

        repeated_ngrams = {
            gram: count
            for gram, count in _ngram_counts(tokens, thresholds["repetition_ngram_size"]).items()
            if count >= thresholds["repetition_ngram_occurrences"] and len(gram.split()) >= 3
        }
        if len(repeated_ngrams) >= thresholds["repetition_cluster_size"]:
            findings.append(
                self._build_finding(
                    rule_id="repetition_clusters",
                    scope=f"{scope_base}:repetition_clusters",
                    title="Repeated phrase cluster detected",
                    category="writing_structure",
                    severity="error",
                    status="OPEN",
                    purpose="Writing outputs should not rely on repeated thesis-shaped phrase clusters.",
                    evidence=[f"{gram} ({count}x)" for gram, count in sorted(repeated_ngrams.items())[:5]],
                )
            )

        if len(sentences) >= 4 and _sentence_similarity(sentences[0], sentences[-1]) >= thresholds["mirrored_open_close_similarity"]:
            findings.append(
                self._build_finding(
                    rule_id="mirrored_open_close",
                    scope=f"{scope_base}:mirrored_open_close",
                    title="Opening and closing sentences mirror each other too closely",
                    category="writing_structure",
                    severity="warning",
                    status="OPEN",
                    purpose="Mirrored openings and closings are audited as ring composition rather than neutral revision.",
                    evidence=[sentences[0], sentences[-1]],
                )
            )

        op_ed_hits = self._count_marker_hits(text, markers["op_ed"])
        if op_ed_hits >= thresholds["marker_repeat_count"]:
            findings.append(
                self._build_finding(
                    rule_id="op_ed_cadence",
                    scope=f"{scope_base}:op_ed_cadence",
                    title="Op-ed cadence markers repeat",
                    category="writing_structure",
                    severity="warning",
                    status="OPEN",
                    purpose="The writing audit blocks editorialized cadence from replacing direct execution.",
                    evidence=self._matching_markers(text, markers["op_ed"]),
                )
            )

        thesis_hits = self._count_marker_hits(text, markers["thesis_framing"])
        if thesis_hits >= thresholds["marker_repeat_count"]:
            findings.append(
                self._build_finding(
                    rule_id="repeated_thesis_framing",
                    scope=f"{scope_base}:repeated_thesis_framing",
                    title="Repeated thesis framing detected",
                    category="writing_structure",
                    severity="error",
                    status="OPEN",
                    purpose="Outputs should not repeatedly restate the thesis instead of progressing the task.",
                    evidence=self._matching_markers(text, markers["thesis_framing"]),
                )
            )

        credential_hits = self._count_marker_hits(text, markers["credentialing"])
        if credential_hits >= thresholds["marker_repeat_count"]:
            findings.append(
                self._build_finding(
                    rule_id="repeated_credentialing",
                    scope=f"{scope_base}:repeated_credentialing",
                    title="Repeated credentialing language detected",
                    category="writing_structure",
                    severity="warning",
                    status="OPEN",
                    purpose="Outputs should not lean on repeated self-credentialing.",
                    evidence=self._matching_markers(text, markers["credentialing"]),
                )
            )

        four_item_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.count(",") == 3:
                four_item_lines.append(stripped)
        if len(four_item_lines) >= thresholds["four_item_list_repeat_count"]:
            findings.append(
                self._build_finding(
                    rule_id="repeated_four_item_lists",
                    scope=f"{scope_base}:repeated_four_item_lists",
                    title="Repeated four-item list pattern detected",
                    category="writing_structure",
                    severity="warning",
                    status="OPEN",
                    purpose="Repeated four-item list structures are audited as a machine-smoothing pattern.",
                    evidence=four_item_lines[:4],
                )
            )

        rhetorical_hits: list[str] = []
        for pattern in markers["rhetorical_symmetry_patterns"]:
            rhetorical_hits.extend(re.findall(pattern, text.lower()))
        if len(rhetorical_hits) >= thresholds["marker_repeat_count"]:
            findings.append(
                self._build_finding(
                    rule_id="rhetorical_symmetry",
                    scope=f"{scope_base}:rhetorical_symmetry",
                    title="Rhetorical symmetry pattern repeats",
                    category="writing_structure",
                    severity="warning",
                    status="OPEN",
                    purpose="Repeated rhetorical symmetry is audited because it can flatten the output into a machine-smoothed pattern.",
                    evidence=rhetorical_hits[:4],
                )
            )

        metaphor_hits = self._count_marker_hits(text, markers["metaphor_framing"])
        if metaphor_hits >= thresholds["marker_repeat_count"]:
            findings.append(
                self._build_finding(
                    rule_id="announced_metaphor_framing",
                    scope=f"{scope_base}:announced_metaphor_framing",
                    title="Announced metaphor framing repeats",
                    category="writing_structure",
                    severity="warning",
                    status="OPEN",
                    purpose="Announced metaphor framing is tracked as a structural habit, not a style preference.",
                    evidence=self._matching_markers(text, markers["metaphor_framing"]),
                )
            )

        stripped_text = text.lstrip()
        policy_brief_hit = next(
            (marker for marker in markers["policy_brief_openers"] if stripped_text.startswith(marker)),
            None,
        )
        if policy_brief_hit:
            findings.append(
                self._build_finding(
                    rule_id="policy_brief_opener",
                    scope=f"{scope_base}:policy_brief_opener",
                    title="Policy-brief opener detected",
                    category="writing_structure",
                    severity="error",
                    status="OPEN",
                    purpose="The writing audit blocks policy-brief openers such as 'One concrete change:' when they smooth the structure into a template.",
                    evidence=[policy_brief_hit],
                )
            )

        if len(sentences) >= thresholds["uniform_sentence_count_min"]:
            word_counts = [len(_tokenize(sentence)) for sentence in sentences if sentence]
            if len(word_counts) >= thresholds["uniform_sentence_count_min"] and pstdev(word_counts) <= thresholds["uniform_sentence_stddev_max"]:
                findings.append(
                    self._build_finding(
                        rule_id="uniform_sentence_cadence",
                        scope=f"{scope_base}:uniform_sentence_cadence",
                        title="Sentence cadence is overly uniform",
                        category="writing_structure",
                        severity="warning",
                        status="OPEN",
                        purpose="Overly uniform sentence cadence is audited as structural smoothing.",
                        evidence=[f"word_counts={word_counts}"],
                    )
                )

        revision_mode = str(metadata.get("revision_mode", "")).strip().lower()
        exact_flags = _as_list(metadata.get("exact_flags"))
        if revision_mode == "conservative":
            if not exact_flags:
                findings.append(
                    self._build_finding(
                        rule_id="conservative_revision_exact_flags",
                        scope=f"{scope_base}:conservative_revision_exact_flags",
                        title="Conservative revision mode is missing exact flags",
                        category="writing_governance",
                        severity="error",
                        status="OPEN",
                        purpose="Conservative revision mode must be tied to exact flags, not an implied rewrite allowance.",
                        evidence=["metadata.revision_mode=conservative", "metadata.exact_flags missing"],
                    )
                )
            else:
                unknown_flags = [
                    flag for flag in exact_flags if str(flag) not in set(rules["known_conservative_flags"])
                ]
                if unknown_flags:
                    findings.append(
                        self._build_finding(
                            rule_id="conservative_revision_unknown_flags",
                            scope=f"{scope_base}:conservative_revision_unknown_flags",
                            title="Conservative revision mode includes unknown exact flags",
                            category="writing_governance",
                            severity="error",
                            status="OPEN",
                            purpose="Conservative revision flags must be explicit and recognized by policy.",
                            evidence=[str(flag) for flag in unknown_flags],
                        )
                    )

        return findings

    def _run_systems_audit(
        self,
        submission: dict[str, Any],
        preexisting_unresolved: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rules = _read_json(self.systems_rules_path, DEFAULT_SYSTEMS_RULES)
        text = str(submission.get("content") or submission.get("output") or submission.get("raw_output") or "")
        purpose = str(submission.get("purpose") or submission.get("metadata", {}).get("purpose") or "").strip()
        scope_base = str(submission.get("task_scope") or submission.get("task_id") or "systems-output")
        findings: list[dict[str, Any]] = []

        if submission.get("rule_checks"):
            contradictions = []
            for check in _as_list(submission.get("rule_checks")):
                if not isinstance(check, dict):
                    continue
                if check.get("expected") != check.get("actual"):
                    contradictions.append(
                        f"{check.get('rule_id', 'unknown_rule')}: expected {check.get('expected')} actual {check.get('actual')}"
                    )
            if contradictions:
                findings.append(
                    self._build_finding(
                        rule_id="claim_rule_contradiction",
                        scope=f"{scope_base}:claim_rule_contradiction",
                        title="Claim contradicts recorded rule state",
                        category="systems_governance",
                        severity="critical",
                        status="BLOCKED",
                        purpose="System outputs cannot contradict controller law or recorded rule state.",
                        evidence=contradictions[:5],
                    )
                )

        false_completion_hits: list[str] = []
        for claim in _as_list(submission.get("claims")):
            if isinstance(claim, dict):
                claim_text = str(claim.get("text") or claim.get("claim") or "")
            else:
                claim_text = str(claim)
            normalized = claim_text.lower()
            if any(marker in normalized for marker in rules["markers"]["false_completion"]):
                false_completion_hits.append(claim_text)
        if false_completion_hits and (
            preexisting_unresolved
            or any(str(delta.get("status")) in UNRESOLVED_ISSUE_STATES for delta in _as_list(submission.get("deltas")) if isinstance(delta, dict))
        ):
            findings.append(
                self._build_finding(
                    rule_id="false_already_fixed",
                    scope=f"{scope_base}:false_already_fixed",
                    title="Output claims work is already fixed while unresolved blockers remain",
                    category="systems_governance",
                    severity="critical",
                    status="BLOCKED",
                    purpose="The system audit blocks false completion claims.",
                    evidence=false_completion_hits[:5],
                )
            )

        if not purpose:
            findings.append(
                self._build_finding(
                    rule_id="missing_purpose",
                    scope=f"{scope_base}:missing_purpose",
                    title="System output is missing an explicit purpose",
                    category="systems_governance",
                    severity="error",
                    status="OPEN",
                    purpose="Every system output must state what the page, route, or artifact is for.",
                    evidence=["submission purpose missing"],
                )
            )

        entity_name_map: dict[str, set[str]] = {}
        for entity in _as_list(submission.get("entities")):
            if not isinstance(entity, dict):
                continue
            entity_id = str(entity.get("id") or entity.get("entity_id") or "")
            entity_name = str(entity.get("name") or "")
            if entity_id and entity_name:
                entity_name_map.setdefault(entity_id, set()).add(entity_name)
        naming_drift_evidence = [
            f"{entity_id}: {sorted(names)}"
            for entity_id, names in entity_name_map.items()
            if len({_normalize_label(name) for name in names}) > 1 or len(names) > 1
        ]
        if naming_drift_evidence:
            findings.append(
                self._build_finding(
                    rule_id="naming_drift",
                    scope=f"{scope_base}:naming_drift",
                    title="Naming drift detected across the same entity",
                    category="systems_governance",
                    severity="error",
                    status="OPEN",
                    purpose="The controller treats naming drift as a governance issue because it breaks durable references.",
                    evidence=naming_drift_evidence[:5],
                )
            )

        routes_without_consumers = []
        for route in _as_list(submission.get("routes")):
            if not isinstance(route, dict):
                continue
            exists = bool(route.get("exists", True))
            consumers = _as_list(route.get("consumers"))
            if exists and not consumers:
                routes_without_consumers.append(str(route.get("name") or route.get("route") or "unnamed-route"))
        if routes_without_consumers:
            findings.append(
                self._build_finding(
                    rule_id="route_without_consumer",
                    scope=f"{scope_base}:route_without_consumer",
                    title="A route exists without a consuming system",
                    category="systems_governance",
                    severity="error",
                    status="OPEN",
                    purpose="Routes must have a declared consumer or they become dead surfaces.",
                    evidence=routes_without_consumers[:5],
                )
            )

        page_failures = []
        for page in _as_list(submission.get("pages")):
            if not isinstance(page, dict):
                continue
            page_name = str(page.get("name") or page.get("path") or "unnamed-page")
            page_purpose = str(page.get("purpose") or "").strip()
            fulfills_purpose = page.get("fulfills_purpose")
            if page_purpose and fulfills_purpose is False:
                page_failures.append(page_name)
        if page_failures:
            findings.append(
                self._build_finding(
                    rule_id="page_without_purpose_fulfillment",
                    scope=f"{scope_base}:page_without_purpose_fulfillment",
                    title="A page exists but does not fulfill its stated purpose",
                    category="systems_governance",
                    severity="error",
                    status="OPEN",
                    purpose="Pages cannot count as complete when they do not satisfy their declared purpose.",
                    evidence=page_failures[:5],
                )
            )

        governance_refs = {str(item) for item in _as_list(submission.get("governance_refs"))}
        missing_governance = [
            path for path in rules["required_authoritative_files"] if path not in governance_refs
        ]
        if missing_governance:
            findings.append(
                self._build_finding(
                    rule_id="governance_drift",
                    scope=f"{scope_base}:governance_drift",
                    title="System output does not cite the authoritative governance files",
                    category="systems_governance",
                    severity="critical",
                    status="BLOCKED",
                    purpose="Governance drift occurs when execution stops referencing the durable controller, rulepack, issue, and run-history files.",
                    evidence=missing_governance[:5],
                )
            )

        unresolved_deltas = []
        for delta in _as_list(submission.get("deltas")):
            if not isinstance(delta, dict):
                continue
            if str(delta.get("status")) in UNRESOLVED_ISSUE_STATES:
                unresolved_deltas.append(
                    f"{delta.get('name', 'unnamed-delta')}={delta.get('status')}"
                )
        if unresolved_deltas or preexisting_unresolved:
            evidence = unresolved_deltas[:]
            if preexisting_unresolved:
                evidence.append(f"preexisting_unresolved={len(preexisting_unresolved)}")
            findings.append(
                self._build_finding(
                    rule_id="unresolved_delta_accumulation",
                    scope=f"{scope_base}:unresolved_delta_accumulation",
                    title="Unresolved deltas are accumulating across runs",
                    category="systems_governance",
                    severity="critical",
                    status="BLOCKED",
                    purpose="Unresolved deltas must persist across runs and block finalization until explicitly resolved or waived.",
                    evidence=evidence[:6],
                )
            )

        if any(marker in text.lower() for marker in rules["markers"]["planning"]) and not _as_list(submission.get("executed_changes")):
            findings.append(
                self._build_finding(
                    rule_id="planning_instead_of_execution",
                    scope=f"{scope_base}:planning_instead_of_execution",
                    title="System output plans work instead of executing it",
                    category="systems_governance",
                    severity="error",
                    status="OPEN",
                    purpose="The controller blocks planning-only output when execution was required.",
                    evidence=[text[:200] or "planning markers present with no executed_changes"],
                )
            )

        partial_claims = []
        for claim in _as_list(submission.get("claims")):
            claim_text = str(claim.get("text") if isinstance(claim, dict) else claim)
            if "partial" in claim_text.lower():
                partial_claims.append(claim_text)
        if partial_claims or any(str(delta.get("status")) == "PARTIAL" for delta in _as_list(submission.get("deltas")) if isinstance(delta, dict)):
            findings.append(
                self._build_finding(
                    rule_id="partial_without_resolution",
                    scope=f"{scope_base}:partial_without_resolution",
                    title="Partial rectification is present without a resolved state",
                    category="systems_governance",
                    severity="critical",
                    status="BLOCKED",
                    purpose="PARTIAL is never treated as RESOLVED and cannot ship.",
                    evidence=partial_claims[:5] or ["delta status PARTIAL present"],
                )
            )

        return findings

    def _count_marker_hits(self, text: str, markers: list[str]) -> int:
        normalized = text.lower()
        return sum(normalized.count(marker.lower()) for marker in markers)

    def _matching_markers(self, text: str, markers: list[str]) -> list[str]:
        normalized = text.lower()
        return [marker for marker in markers if marker.lower() in normalized]

    def _build_finding(
        self,
        *,
        rule_id: str,
        scope: str,
        title: str,
        category: str,
        severity: str,
        status: str,
        purpose: str,
        evidence: list[str],
    ) -> dict[str, Any]:
        issue_id = _stable_issue_id(rule_id, scope)
        return {
            "issue_id": issue_id,
            "rule_id": rule_id,
            "scope": scope,
            "title": title,
            "category": category,
            "severity": severity,
            "status": status,
            "blocking": _default_status_blocks(status),
            "purpose": purpose,
            "evidence": evidence,
        }

    def _merge_findings(
        self,
        *,
        registry: dict[str, Any],
        findings: list[dict[str, Any]],
        run_id: str,
        timestamp: str,
        resolution_attempts: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], list[str]]:
        issues = registry.setdefault("issues", [])
        issues_by_id = {issue["issue_id"]: issue for issue in issues}
        seen_issue_ids: set[str] = set()
        policy_prefix = registry["policy"]["waiver_policy_marker_prefix"]

        for finding in findings:
            seen_issue_ids.add(finding["issue_id"])
            existing = issues_by_id.get(finding["issue_id"])
            if existing is None:
                existing = {
                    "issue_id": finding["issue_id"],
                    "title": finding["title"],
                    "category": finding["category"],
                    "status": finding["status"],
                    "severity": finding["severity"],
                    "blocking": finding["blocking"],
                    "purpose": finding["purpose"],
                    "rule_id": finding["rule_id"],
                    "scope": finding["scope"],
                    "evidence": finding["evidence"],
                    "history": [],
                    "first_seen": timestamp,
                    "last_seen": timestamp,
                }
                issues.append(existing)
                issues_by_id[existing["issue_id"]] = existing
            else:
                existing.update(
                    {
                        "title": finding["title"],
                        "category": finding["category"],
                        "severity": finding["severity"],
                        "blocking": finding["blocking"],
                        "purpose": finding["purpose"],
                        "rule_id": finding["rule_id"],
                        "scope": finding["scope"],
                        "evidence": finding["evidence"],
                        "last_seen": timestamp,
                    }
                )
                if existing.get("status") == "RESOLVED":
                    existing["status"] = finding["status"]
                elif existing.get("status") == "WAIVED" and not _validate_waiver(existing, policy_prefix):
                    existing["status"] = finding["status"]

            if finding["issue_id"] in resolution_attempts and finding["status"] != "BLOCKED":
                existing["status"] = "PARTIAL"
            elif finding["status"] == "BLOCKED":
                existing["status"] = "BLOCKED"
            elif existing.get("status") not in {"PARTIAL", "BLOCKED", "WAIVED"}:
                existing["status"] = finding["status"]

            existing.setdefault("history", []).append(
                {
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "event": "observed",
                    "status": existing["status"],
                    "note": finding["title"],
                }
            )

        for issue_id, attempt in resolution_attempts.items():
            issue = issues_by_id.get(issue_id)
            if issue is None:
                continue
            if issue_id in seen_issue_ids:
                continue
            if attempt.get("waiver"):
                waiver = attempt["waiver"]
                policy_marker = str(waiver.get("policy_marker") or "")
                if policy_marker.startswith(policy_prefix):
                    issue["status"] = "WAIVED"
                    issue["waiver"] = {
                        "policy_marker": policy_marker,
                        "reason": str(waiver.get("reason") or ""),
                    }
                    issue.setdefault("history", []).append(
                        {
                            "run_id": run_id,
                            "timestamp": timestamp,
                            "event": "waived",
                            "status": "WAIVED",
                            "note": policy_marker,
                        }
                    )
                else:
                    issue.setdefault("history", []).append(
                        {
                            "run_id": run_id,
                            "timestamp": timestamp,
                            "event": "invalid_waiver_rejected",
                            "status": issue["status"],
                            "note": "WAIVED requires an explicit policy marker in file.",
                        }
                    )
                continue

            evidence = str(attempt.get("evidence") or "").strip()
            if evidence:
                issue["status"] = "RESOLVED"
                issue["resolution"] = {
                    "evidence": evidence,
                    "timestamp": timestamp,
                    "run_id": run_id,
                }
                issue.setdefault("history", []).append(
                    {
                        "run_id": run_id,
                        "timestamp": timestamp,
                        "event": "resolved",
                        "status": "RESOLVED",
                        "note": evidence,
                    }
                )
            else:
                issue["status"] = "PARTIAL"
                issue.setdefault("history", []).append(
                    {
                        "run_id": run_id,
                        "timestamp": timestamp,
                        "event": "partial_attempt",
                        "status": "PARTIAL",
                        "note": "Resolution attempt lacked evidence.",
                    }
                )

        unresolved_issue_ids = [
            issue["issue_id"] for issue in issues if issue.get("status") in UNRESOLVED_ISSUE_STATES
        ]
        return registry, unresolved_issue_ids

    def _collect_unresolved_issues(self, registry: dict[str, Any]) -> list[dict[str, Any]]:
        return [issue for issue in registry.get("issues", []) if issue.get("status") in UNRESOLVED_ISSUE_STATES]


def bootstrap_repository(repo_root: str | Path) -> list[str]:
    return PersistentController(repo_root).bootstrap_repository()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persistent controller for repo-governed agent output.")
    parser.add_argument("--repo-root", default=".", help="Repository root to bootstrap or run against.")
    parser.add_argument("--bootstrap", action="store_true", help="Create or upgrade the persistent controller scaffold.")
    parser.add_argument("--input", help="Path to a JSON submission file to audit and persist.")
    parser.add_argument("--audit-summary", action="store_true", help="Print the aggregate audit summary instead of running a submission.")
    parser.add_argument("--agent-id", help="Override or inject the agent id for this submission or summary filter.")
    parser.add_argument("--agent-role", help="Override or inject the agent role for this submission.")
    parser.add_argument("--task-type", choices=["writing", "systems", "mixed"], help="Override the task type.")
    parser.add_argument("--task-scope", help="Override or inject the task scope.")
    parser.add_argument("--audit-scope", help="Override or inject the audit scope.")
    parser.add_argument("--schedule-name", help="Override or inject the schedule name.")
    parser.add_argument("--purpose", help="Override or inject the submission purpose.")
    parser.add_argument("--heartbeat-phase", help="Override or inject the heartbeat phase for this submission.")
    parser.add_argument(
        "--governance-ref",
        action="append",
        dest="governance_refs",
        help="Add a governance reference path. Can be supplied multiple times.",
    )
    return parser.parse_args()


def main() -> None:
    _require_approved_entrypoint()
    args = _parse_args()
    controller = PersistentController(args.repo_root)
    if args.bootstrap:
        print(json.dumps({"created_or_upgraded": controller.bootstrap_repository()}, indent=2))
        return
    if args.audit_summary:
        print(json.dumps(controller.audit_summary(agent_id=args.agent_id), indent=2))
        return
    if not args.input:
        raise SystemExit("--input is required unless --bootstrap or --audit-summary is supplied")
    submission_path = Path(args.input).resolve()
    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    submission.setdefault("metadata", {})
    if args.task_type:
        submission["task_type"] = args.task_type
    if args.task_scope:
        submission["task_scope"] = args.task_scope
    if args.purpose:
        submission["purpose"] = args.purpose
    if args.agent_id:
        submission["agent_id"] = args.agent_id
        submission["metadata"]["agent_id"] = args.agent_id
    if args.agent_role:
        submission["agent_role"] = args.agent_role
        submission["metadata"]["agent_role"] = args.agent_role
    if args.audit_scope:
        submission["audit_scope"] = args.audit_scope
        submission["metadata"]["audit_scope"] = args.audit_scope
    if args.schedule_name:
        submission["metadata"]["schedule_name"] = args.schedule_name
    if args.heartbeat_phase:
        submission["heartbeat_phase"] = args.heartbeat_phase
        submission["metadata"]["heartbeat_phase"] = args.heartbeat_phase
    if args.governance_refs:
        existing_refs = list(submission.get("governance_refs") or [])
        submission["governance_refs"] = existing_refs + args.governance_refs
    result = controller.run(submission)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
