from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import markdown as markdown_lib
except ImportError:  # pragma: no cover - exercised only in sparse environments.
    markdown_lib = None

from controller.main import CANONICAL_REPO_ROOT, PersistentController

ALLOWED_HEARTBEAT_EVENTS = {
    "tock",
    "cycle_close",
    "convergence",
    "artifact_dispatch",
    "agent_audit",
    "health_transition",
}

DEFAULT_ARCADE_ITEMS = [
    {"title": "The Coin", "href": "/game/index.html", "summary": "Primary interactive simulator and field-choice experience."},
    {"title": "Glyph Voice Render", "href": "/glyph_voice_render.html", "summary": "Readout page for the voice stream and observation layer."},
    {"title": "Research Tracker", "href": "/research_tracker_v2.html", "summary": "Tracking, convergence, and study instrumentation."},
    {"title": "Full Transmission", "href": "/full_transmission.html", "summary": "Transmission interface and archive-facing output surface."},
    {"title": "Seven-Sided Clock", "href": "/heyer_livin_clock.html", "summary": "Clock-facing time and structural rhythm interface."},
    {"title": "Proof Engine", "href": "/arcade/proof-engine.html", "summary": "Structured proof interaction page."},
    {"title": "Northstar Navigator", "href": "/arcade/northstar-navigator.html", "summary": "Navigation glyph model and directional testing surface."},
    {"title": "Book of Life", "href": "/arcade/book-of-life.html", "summary": "Book-opening probability visualization."},
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return json.loads(json.dumps(default))
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _safe_slug(value: str, *, default: str = "manual") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
    return slug or default


def _strip_emoji(value: str) -> str:
    return re.sub(r"^[^\w]+", "", value).strip()


def _join_text(parts: list[str]) -> str:
    return "\n".join(part for part in parts if part).strip()


def _fallback_markdown_to_html(text: str) -> str:
    paragraphs = []
    for raw_block in text.split("\n\n"):
        block = raw_block.strip()
        if not block:
            continue
        if block.startswith("### "):
            paragraphs.append(f"<h3>{html.escape(block[4:])}</h3>")
            continue
        if block.startswith("## "):
            paragraphs.append(f"<h2>{html.escape(block[3:])}</h2>")
            continue
        if block.startswith("# "):
            paragraphs.append(f"<h1>{html.escape(block[2:])}</h1>")
            continue
        lines = block.splitlines()
        if all(line.lstrip().startswith(("- ", "1. ")) for line in lines):
            tag = "ol" if all(line.lstrip().startswith("1. ") for line in lines) else "ul"
            items = []
            for line in lines:
                item_text = re.sub(r"^(\-\s|1\.\s)", "", line.strip())
                items.append(f"<li>{html.escape(item_text)}</li>")
            paragraphs.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        paragraphs.append(f"<p>{html.escape(block)}</p>")
    return "".join(paragraphs)


class GlyphRuntime:
    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or os.environ.get("GLYPH_RUNTIME_ROOT") or Path(__file__).parent).resolve()
        allow_noncanonical = self.base_dir != CANONICAL_REPO_ROOT
        self.controller = PersistentController(self.base_dir, allow_noncanonical=allow_noncanonical)
        self.controller.bootstrap_repository()

    @property
    def workspace_policy_path(self) -> Path:
        return self.base_dir / "GLYPH_WORKSPACE_POLICY.json"

    @property
    def route_map_path(self) -> Path:
        return self.base_dir / "GLYPH_ROUTE_MAP.json"

    @property
    def audit_index_path(self) -> Path:
        return self.base_dir / "state" / "audit_index.json"

    @property
    def heartbeat_state_path(self) -> Path:
        return self.base_dir / "state" / "heartbeat_state.json"

    @property
    def content_cache_path(self) -> Path:
        return self.base_dir / "state" / "notion_content_cache.json"

    @property
    def events_dir(self) -> Path:
        events_dir = self.base_dir / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        return events_dir

    def load_workspace_policy(self) -> dict[str, Any]:
        return _read_json(self.workspace_policy_path, {})

    def load_route_map(self) -> dict[str, Any]:
        return _read_json(self.route_map_path, {"routes": {}})

    def load_content_cache(self) -> dict[str, Any]:
        return _read_json(self.content_cache_path, {"version": "1.0.0", "updated_at": None, "routes": {}})

    def load_heartbeat_state(self) -> dict[str, Any]:
        state = _read_json(
            self.heartbeat_state_path,
            {
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
            },
        )
        if not state.get("created_at"):
            now = _utc_now_iso()
            state["created_at"] = now
            state["updated_at"] = now
            _write_json(self.heartbeat_state_path, state)
        return state

    def get_route(self, route_key: str) -> dict[str, Any]:
        route = self.load_route_map().get("routes", {}).get(route_key)
        if not route:
            raise KeyError(f"Unknown route key: {route_key}")
        return route

    def notion_token(self) -> str | None:
        policy = self.load_workspace_policy()
        env_names = policy.get("content", {}).get("notion_token_env") or ["NOTION_TOKEN", "NOTION_API_TOKEN"]
        for name in env_names:
            token = os.environ.get(name, "").strip()
            if token:
                return token
        return None

    def governance_preflight(self, *, action: str) -> dict[str, Any]:
        return self.controller.governance_preflight(action=action)

    def _notion_request(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self.notion_token()
        if not token:
            raise RuntimeError("No Notion token configured.")
        request = urllib.request.Request(
            f"https://api.notion.com/v1/{path.lstrip('/')}",
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": os.environ.get("NOTION_API_VERSION", "2022-06-28"),
                "Content-Type": "application/json",
            },
        )
        if payload is not None:
            request.data = json.dumps(payload).encode("utf-8")
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def _rich_text_to_markdown(self, value: list[dict[str, Any]]) -> str:
        pieces: list[str] = []
        for part in value or []:
            text = part.get("plain_text", "")
            href = part.get("href") or part.get(part.get("type", ""), {}).get("link", {}).get("url")
            annotations = part.get("annotations") or {}
            if href:
                text = f"[{text}]({href})"
            if annotations.get("code"):
                text = f"`{text}`"
            if annotations.get("bold"):
                text = f"**{text}**"
            if annotations.get("italic"):
                text = f"*{text}*"
            if annotations.get("strikethrough"):
                text = f"~~{text}~~"
            pieces.append(text)
        return "".join(pieces).strip()

    def _page_title_from_properties(self, payload: dict[str, Any], fallback: str) -> str:
        properties = payload.get("properties") or {}
        for value in properties.values():
            if value.get("type") == "title":
                title = self._rich_text_to_markdown(value.get("title") or [])
                if title:
                    return title
        return fallback

    def _fetch_block_children(self, block_id: str) -> list[dict[str, Any]]:
        cursor = None
        blocks: list[dict[str, Any]] = []
        while True:
            path = f"blocks/{block_id}/children?page_size=100"
            if cursor:
                path += f"&start_cursor={cursor}"
            payload = self._notion_request(path)
            blocks.extend(payload.get("results", []))
            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")
        return blocks

    def _blocks_to_markdown(self, blocks: list[dict[str, Any]], *, depth: int = 0) -> str:
        lines: list[str] = []
        indent = "  " * depth
        for block in blocks:
            block_type = block.get("type", "")
            data = block.get(block_type, {})
            line = ""
            if block_type == "paragraph":
                line = self._rich_text_to_markdown(data.get("rich_text") or [])
            elif block_type == "heading_1":
                line = "# " + self._rich_text_to_markdown(data.get("rich_text") or [])
            elif block_type == "heading_2":
                line = "## " + self._rich_text_to_markdown(data.get("rich_text") or [])
            elif block_type == "heading_3":
                line = "### " + self._rich_text_to_markdown(data.get("rich_text") or [])
            elif block_type == "bulleted_list_item":
                line = indent + "- " + self._rich_text_to_markdown(data.get("rich_text") or [])
            elif block_type == "numbered_list_item":
                line = indent + "1. " + self._rich_text_to_markdown(data.get("rich_text") or [])
            elif block_type == "to_do":
                checked = "x" if data.get("checked") else " "
                line = indent + f"- [{checked}] " + self._rich_text_to_markdown(data.get("rich_text") or [])
            elif block_type == "quote":
                line = "> " + self._rich_text_to_markdown(data.get("rich_text") or [])
            elif block_type == "callout":
                line = "> " + self._rich_text_to_markdown(data.get("rich_text") or [])
            elif block_type == "code":
                code_text = self._rich_text_to_markdown(data.get("rich_text") or [])
                language = data.get("language") or ""
                line = f"```{language}\n{code_text}\n```"
            elif block_type == "divider":
                line = "---"
            elif block_type == "toggle":
                line = indent + "- " + self._rich_text_to_markdown(data.get("rich_text") or [])
            elif block_type == "child_page":
                line = indent + "- " + str(data.get("title") or "Untitled page")
            elif block_type == "bookmark":
                url = str(data.get("url") or "")
                line = f"- [{url}]({url})" if url else ""
            else:
                line = self._rich_text_to_markdown(data.get("rich_text") or [])
            if line:
                lines.append(line)
            if block.get("has_children"):
                nested = self._fetch_block_children(block["id"])
                nested_text = self._blocks_to_markdown(nested, depth=depth + 1)
                if nested_text:
                    lines.append(nested_text)
        return _join_text(lines)

    def _fetch_page_markdown(self, route: dict[str, Any]) -> dict[str, Any] | None:
        page_id = route.get("page_id")
        if not page_id or not self.notion_token():
            return None
        try:
            page = self._notion_request(f"pages/{page_id}")
            blocks = self._fetch_block_children(page_id)
        except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
            return None
        title = self._page_title_from_properties(page, route.get("page_title", "Untitled"))
        markdown_body = self._blocks_to_markdown(blocks)
        return {
            "title": _strip_emoji(title),
            "markdown": markdown_body,
            "source_url": route.get("page_url") or page.get("url", ""),
            "source_type": "notion_api",
            "fetched_at": _utc_now_iso(),
        }

    def _extract_property(self, payload: dict[str, Any], property_name: str) -> Any:
        value = (payload.get("properties") or {}).get(property_name) or {}
        value_type = value.get("type")
        if value_type == "title":
            return self._rich_text_to_markdown(value.get("title") or [])
        if value_type == "rich_text":
            return self._rich_text_to_markdown(value.get("rich_text") or [])
        if value_type == "select":
            option = value.get("select") or {}
            return option.get("name")
        if value_type == "multi_select":
            return [item.get("name") for item in value.get("multi_select") or []]
        if value_type == "url":
            return value.get("url")
        if value_type in {"created_time", "last_edited_time"}:
            return value.get(value_type)
        return None

    def _fetch_recent_portal_items(self, route: dict[str, Any], *, limit: int = 6) -> list[dict[str, Any]]:
        database_id = route.get("blog_database_id")
        if not database_id or not self.notion_token():
            return []
        query_payload = {
            "page_size": limit,
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
            "filter": {
                "property": "Public status",
                "select": {"equals": "Public"},
            },
        }
        try:
            response = self._notion_request(f"databases/{database_id}/query", method="POST", payload=query_payload)
        except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
            return []

        items: list[dict[str, Any]] = []
        for result in response.get("results", []):
            title = self._extract_property(result, "Item") or "Untitled"
            items.append(
                {
                    "title": title,
                    "summary": self._extract_property(result, "Public summary") or "",
                    "domain": self._extract_property(result, "Domain") or "",
                    "status": self._extract_property(result, "Public status") or "",
                    "url": self._extract_property(result, "Public URL") or result.get("url", ""),
                    "tags": self._extract_property(result, "Tags") or [],
                    "last_edited": self._extract_property(result, "Last edited") or result.get("last_edited_time"),
                    "added": self._extract_property(result, "Added") or result.get("created_time"),
                }
            )
        return items

    def get_route_payload(self, route_key: str, *, force_refresh: bool = False) -> dict[str, Any]:
        governance_preflight = self.governance_preflight(action="route_content")
        route = self.get_route(route_key)
        cache = self.load_content_cache()
        cached = (cache.get("routes") or {}).get(route_key) or {}
        live = self._fetch_page_markdown(route) if force_refresh or self.notion_token() else None
        if live:
            cached = {**cached, **live}
            if route_key == "portal":
                recent_items = self._fetch_recent_portal_items(route)
                if recent_items:
                    cached["recent_items"] = recent_items
            cache.setdefault("routes", {})[route_key] = cached
            cache["updated_at"] = _utc_now_iso()
            _write_json(self.content_cache_path, cache)

        markdown_body = str(cached.get("markdown") or "").strip()
        if not markdown_body:
            markdown_body = f"## {route.get('page_title', route_key.title())}\n\nNotion content will render here when the cache is seeded or a Notion token is configured."

        if markdown_lib is not None:
            rendered_html = markdown_lib.markdown(
                markdown_body,
                extensions=["tables", "fenced_code", "sane_lists"],
            )
        else:
            rendered_html = _fallback_markdown_to_html(markdown_body)
        return {
            "route_key": route_key,
            "path": route.get("path"),
            "title": cached.get("title") or route.get("page_title", route_key.title()),
            "page_title": route.get("page_title", route_key.title()),
            "content_role": route.get("content_role", "page"),
            "source_url": cached.get("source_url") or route.get("page_url", ""),
            "markdown": markdown_body,
            "html": rendered_html,
            "recent_items": cached.get("recent_items", []),
            "cached_at": cached.get("fetched_at"),
            "using_live_notion": bool(live),
            "governance_preflight": governance_preflight,
        }

    def get_arcade_payload(self) -> dict[str, Any]:
        return {
            "route_key": "arcade",
            "title": "Glyph Arcade",
            "path": "/arcade",
            "items": list(DEFAULT_ARCADE_ITEMS),
        }

    def _append_heartbeat_event(self, state: dict[str, Any], *, event_type: str, source: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if event_type not in ALLOWED_HEARTBEAT_EVENTS:
            raise ValueError(f"Unsupported heartbeat event type: {event_type}")
        timestamp = _utc_now_iso()
        event = {
            "event_type": event_type,
            "timestamp": timestamp,
            "cycle": state.get("cycle"),
            "phase": state.get("phase"),
            "source": source,
            "payload": payload or {},
        }
        retention = (
            self.load_workspace_policy()
            .get("heartbeat", {})
            .get("event_retention_limit", 200)
        )
        recent_events = list(state.get("recent_events") or [])
        recent_events.append(event)
        state["recent_events"] = recent_events[-int(retention) :]
        counters = state.setdefault("counters", {})
        counters[event_type] = int(counters.get(event_type, 0)) + 1
        state["last_event"] = event
        state["updated_at"] = timestamp
        if event_type == "tock":
            state["last_tock_at"] = timestamp
        elif event_type == "cycle_close":
            state["last_cycle_close_at"] = timestamp
        elif event_type == "convergence":
            state["last_convergence_at"] = timestamp
        return event

    def _persist_heartbeat_state(self, state: dict[str, Any]) -> dict[str, Any]:
        _write_json(self.heartbeat_state_path, state)
        return state

    def heartbeat_summary(self) -> dict[str, Any]:
        governance_preflight = self.governance_preflight(action="heartbeat")
        state = self.load_heartbeat_state()
        return {
            "cycle": state.get("cycle"),
            "current_window": state.get("current_window"),
            "tick_in_cycle": state.get("tick_in_cycle"),
            "ticks_while_waiting": state.get("ticks_while_waiting"),
            "waiting_for_tock": state.get("waiting_for_tock"),
            "phase": state.get("phase"),
            "last_tock_at": state.get("last_tock_at"),
            "last_cycle_close_at": state.get("last_cycle_close_at"),
            "last_convergence_at": state.get("last_convergence_at"),
            "last_event": state.get("last_event"),
            "counters": state.get("counters", {}),
            "agent_activity": state.get("agent_activity", {}),
            "updated_at": state.get("updated_at"),
            "governance_preflight": governance_preflight,
        }

    def heartbeat_events(self, *, limit: int = 25) -> list[dict[str, Any]]:
        self.governance_preflight(action="heartbeat")
        state = self.load_heartbeat_state()
        recent_events = list(state.get("recent_events") or [])
        return recent_events[-limit:]

    def record_internal_tick(self, *, source: str = "glyph-heartbeat") -> dict[str, Any]:
        self.governance_preflight(action="heartbeat")
        state = self.load_heartbeat_state()
        timestamp = _utc_now_iso()
        state["updated_at"] = timestamp
        if state.get("waiting_for_tock"):
            state["ticks_while_waiting"] = int(state.get("ticks_while_waiting", 0)) + 1
            return self._persist_heartbeat_state(state)

        next_tick = int(state.get("tick_in_cycle", 0)) + 1
        state["tick_in_cycle"] = next_tick
        current_window = int(state.get("current_window", 10))
        if next_tick >= current_window:
            state["waiting_for_tock"] = True
            state["phase"] = "awaiting_tock"
            state["tick_in_cycle"] = 0
            state["ticks_while_waiting"] = 0
            self._append_heartbeat_event(
                state,
                event_type="cycle_close",
                source=source,
                payload={"window": current_window},
            )
        return self._persist_heartbeat_state(state)

    def record_tock(self, *, source: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.governance_preflight(action="heartbeat")
        state = self.load_heartbeat_state()
        sequence = list(state.get("window_sequence") or [10, 20, 40])
        next_index = (int(state.get("window_index", 0)) + 1) % len(sequence)
        state["cycle"] = int(state.get("cycle", 1)) + 1
        state["window_index"] = next_index
        state["current_window"] = int(sequence[next_index])
        state["tick_in_cycle"] = 0
        state["ticks_while_waiting"] = 0
        state["waiting_for_tock"] = False
        state["phase"] = "active"
        event = self._append_heartbeat_event(state, event_type="tock", source=source, payload=payload or {})
        self._persist_heartbeat_state(state)
        return {"event": event, "state": self.heartbeat_summary()}

    def record_heartbeat_event(self, event_type: str, *, source: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.governance_preflight(action="heartbeat")
        state = self.load_heartbeat_state()
        event = self._append_heartbeat_event(state, event_type=event_type, source=source, payload=payload or {})
        self._persist_heartbeat_state(state)
        return {"event": event, "state": self.heartbeat_summary()}

    def submit_agent_audit(self, submission: dict[str, Any]) -> dict[str, Any]:
        result = self.controller.run(submission)
        state = self.load_heartbeat_state()
        agent_id = _safe_slug(str(result.get("agent_id") or "manual"), default="manual")
        state.setdefault("agent_activity", {})[agent_id] = {
            "agent_label": result.get("agent_label", agent_id),
            "agent_role": result.get("agent_role", ""),
            "audit_path": result.get("audit_path"),
            "raw_output_path": result.get("raw_output_path"),
            "submission_snapshot_path": result.get("submission_snapshot_path"),
            "latest_run_id": result.get("run_id"),
            "latest_timestamp": result.get("timestamp"),
            "unresolved_issue_ids": result.get("unresolved_issue_ids", []),
            "heartbeat_phase": result.get("heartbeat_phase", ""),
            "schedule_name": result.get("schedule_name", ""),
        }
        self._append_heartbeat_event(
            state,
            event_type="agent_audit",
            source=result.get("entrypoint", "api"),
            payload={
                "agent_id": agent_id,
                "audit_path": result.get("audit_path"),
                "unresolved_issue_ids": result.get("unresolved_issue_ids", []),
            },
        )
        self._persist_heartbeat_state(state)
        return result

    def portal_payload(self, *, force_refresh: bool = False) -> dict[str, Any]:
        content = self.get_route_payload("portal", force_refresh=force_refresh)
        recent_items = list(content.get("recent_items") or [])
        newest_item = recent_items[0] if recent_items else None
        audit_summary = self.controller.audit_summary()
        heartbeat = self.heartbeat_summary()
        return {
            "content": content,
            "newest_item": newest_item,
            "recent_items": recent_items[1:] if newest_item else recent_items,
            "system_status": {
                "heartbeat": heartbeat,
                "audit_summary": audit_summary,
            },
        }


def render_html_panel(title: str, body: str, *, accent: str | None = None) -> str:
    accent_class = f" panel-accent-{accent}" if accent else ""
    return (
        f"<section class='content-panel{accent_class}'>"
        f"<div class='panel-label'>{html.escape(title)}</div>"
        f"{body}"
        "</section>"
    )
