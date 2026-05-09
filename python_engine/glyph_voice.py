"""
glyph_voice.py
Output adapter for Heart/Spine. Gives the mechanism three voices that do
NOT require Terminal to be heard:

  1. G-Workspace log file  — runtime/glyph_voice.log
                             mechanism appends inside the SSD repo
  2. macOS notifications   — system notification on key events
  3. Localhost web view    — http://localhost:8788
                             browser shows the live event stream

Terminal is only needed to start the mechanism once. After that, the
mechanism speaks through the Mac's own channels. Terminal can stay closed.
"""

from __future__ import annotations
import hashlib
import os
import json
import re
import time
import sys
import threading
import subprocess
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

from glyph_heart import Heart, HeartEvent, Server

REPO_ROOT = Path(os.environ.get("GLYPH_RUNTIME_ROOT", Path(__file__).resolve().parents[1])).resolve()
LOG_PATH = os.environ.get("GLYPH_VOICE_LOG_PATH", str(REPO_ROOT / "runtime" / "glyph_voice.log"))
PORT = 8788
PERSISTED_EVENT_KINDS = {"intake", "cycle_close_input", "silent_cycle", "reflection", "activity_check"}
LOG_ALL_EVENTS = os.environ.get("GLYPH_VOICE_LOG_ALL_EVENTS", "").strip().lower() in {"1", "true", "yes", "all"}
HANDOFF_DIR = Path(os.environ.get("GLYPH_HANDOFF_DIR", str(REPO_ROOT / "reports" / "cloud_handoff"))).expanduser()
HANDOFF_MAX_EVENTS = int(os.environ.get("GLYPH_HANDOFF_MAX_EVENTS", "200"))
EVENTS_RAW_DIR = REPO_ROOT / "events_raw"
RAW_LEDGER = EVENTS_RAW_DIR / "raw_capture.jsonl"
SEGMENT_LEDGER = EVENTS_RAW_DIR / "segmented_events.jsonl"
RAW_SCHEMA_VERSION = "raw_event_schema_v1"
BRANCH_SCHEMA_VERSION = "branch_authority_schema_v1"
ENTERPRISE_ROOT = Path(os.environ.get(
    "GLYPH_ENTERPRISE_ROOT",
    "/Volumes/G-Workspace/Claude/Projects/Glyph, the final mark/enterprise_runtime",
)).expanduser()
DISC_KEYWORDS = ("disc", "scan", "ingest", "route", "learn", "record", "archive", "index", "source")
CONTROLLER_KEYWORDS = ("controller", "audit", "governance", "gate", "issue", "issues")
ENTERPRISE_KEYWORDS = ("enterprise", "ceo", "packet", "queue", "worker", "order")
MAX_DISC_SOURCES = 5


def event_record(evt: HeartEvent) -> Dict[str, Any]:
    return {
        "stamp": str(evt.stamp),
        "kind": evt.kind,
        "state": evt.state,
        "cycle": evt.cycle,
        "tick": evt.tick,
        "tock": evt.tock,
        "phase": round(evt.phase, 3),
        "window": evt.window,
        "payload": evt.payload,
        "wall_time": evt.wall_time,
    }


def should_persist(evt: HeartEvent) -> bool:
    return LOG_ALL_EVENTS or evt.kind in PERSISTED_EVENT_KINDS


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def capture_chat_raw(message: str, *, speaker: str, event_stamp: str) -> Dict[str, Any]:
    raw_bytes = message.encode("utf-8")
    raw_record = {
        "record_id": f"raw_{uuid.uuid4().hex}",
        "source_id": f"glyph_chat_{event_stamp.replace('.', '_')}",
        "speaker": speaker or "glyph_chat",
        "branch": "transcript",
        "event_kind": "local_plain_english_chat",
        "raw": message,
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "raw_byte_count": len(raw_bytes),
        "timestamp": utc_now(),
        "authority_level": "source",
        "status": "observed",
        "action": "preserve_raw_before_response",
        "schema_version": RAW_SCHEMA_VERSION,
        "raw_encoding": "utf-8",
    }
    try:
        append_jsonl(RAW_LEDGER, raw_record)
    except OSError as exc:
        raw_record["status"] = "blocked"
        raw_record["action"] = "raw_preservation_failed_before_response"
        raw_record["write_error"] = f"{exc.__class__.__name__}: {exc}"
        return raw_record
    for index, line in enumerate(message.splitlines(), start=1):
        if not line:
            continue
        try:
            append_jsonl(SEGMENT_LEDGER, {
                "record_id": f"seg_{uuid.uuid4().hex}",
                "source_id": raw_record["source_id"],
                "speaker": raw_record["speaker"],
                "branch": "derived_segment",
                "event_kind": "local_chat_line_segment",
                "raw": line,
                "normalized": None,
                "glyph_tags": ["derived_from_raw_capture", "local_chat"],
                "relation_to": [raw_record["record_id"]],
                "authority_level": "representation",
                "status": "observed",
                "action": "preserve_derived_segment_without_changing_raw",
                "timestamp": utc_now(),
                "schema_version": BRANCH_SCHEMA_VERSION,
                "segment_index": index,
            })
        except OSError as exc:
            raw_record["segment_write_error"] = f"{exc.__class__.__name__}: {exc}"
            break
    return raw_record


# ---------------------------------------------------------------------------
# Voice 1 — Desktop log file
# ---------------------------------------------------------------------------
class FileVoice:
    def __init__(self, path: str = LOG_PATH):
        self.path = path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # announce start
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"\n=== glyph voice started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    def say(self, evt: HeartEvent) -> None:
        if not should_persist(evt):
            return
        line = json.dumps(event_record(evt), ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


class HandoffVoice:
    """Bounded local handoff: one redacted status JSON file, rewritten in place."""

    def __init__(self, directory: Path = HANDOFF_DIR, max_events: int = HANDOFF_MAX_EVENTS):
        self.directory = directory
        self.max_events = max(1, max_events)
        self.events: List[Dict[str, Any]] = []
        self.counts: Dict[str, int] = {}
        self.directory.mkdir(parents=True, exist_ok=True)

    def say(self, evt: HeartEvent) -> None:
        if not should_persist(evt):
            return
        record = {
            "stamp": str(evt.stamp),
            "kind": evt.kind,
            "state": evt.state,
            "cycle": evt.cycle,
            "tick": evt.tick,
            "phase": round(evt.phase, 3),
            "window": evt.window,
            "has_payload": evt.payload is not None,
        }
        self.events.append(record)
        if len(self.events) > self.max_events:
            del self.events[:len(self.events) - self.max_events]
        self.counts[evt.kind] = self.counts.get(evt.kind, 0) + 1
        payload = {
            "schema": "glyph_voice_handoff_status_v1",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "latest_event": record,
            "persisted_event_kinds": sorted(PERSISTED_EVENT_KINDS),
            "log_all_events": LOG_ALL_EVENTS,
            "event_counts": self.counts,
            "events_kept": len(self.events),
            "events": self.events,
            "source_mutation_allowed": False,
            "raw_payload_exported": False,
            "full_raw_archive_export": False,
        }
        target = self.directory / "glyph_voice_status.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(target)


# ---------------------------------------------------------------------------
# Voice 2 — macOS notifications
# ---------------------------------------------------------------------------
class NotifyVoice:
    """Uses osascript to show a macOS notification. Key events only."""
    KEY_KINDS = {"silent_cycle", "cycle_close_input", "reflection", "intake"}

    def say(self, evt: HeartEvent) -> None:
        if evt.kind not in self.KEY_KINDS:
            return
        title = f"Glyph: {evt.kind}"
        message = f"cycle {evt.cycle} · tick {evt.tick} · window {evt.window}"
        # osascript runs independent of Terminal; the mechanism's own process invokes it
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}"'],
                check=False, timeout=2,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Voice 3 — localhost HTTP view
# ---------------------------------------------------------------------------
_EVENT_BUFFER: List[Dict[str, Any]] = []
_BUFFER_LOCK = threading.Lock()
_MAX_BUFFER = 500
_SERVER_REF: Optional[Any] = None
_CHAT_BUFFER: List[Dict[str, Any]] = []
_CHAT_LOCK = threading.Lock()
_MAX_CHAT = 100
_LAST_ATTACHMENTS: List[Dict[str, Any]] = []
_MAX_ATTACHMENT_TEXT = 12000
TEXT_PREVIEW_EXTENSIONS = {
    ".css", ".csv", ".html", ".js", ".json", ".jsx", ".md", ".py",
    ".txt", ".ts", ".tsx", ".xml", ".yaml", ".yml",
}


STOP_WORDS = {
    "about", "after", "again", "also", "and", "because", "been", "before",
    "from", "have", "into", "that", "the", "their", "there", "this", "with",
    "what", "when", "where", "which", "will", "would", "your",
}


def load_automation_config() -> Dict[str, Any]:
    config_path = REPO_ROOT / "automation" / "config.json"
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def service_registry() -> List[Dict[str, str]]:
    config = load_automation_config()
    brand = config.get("brand") if isinstance(config.get("brand"), dict) else {}
    primary_domain = str(brand.get("primary_domain") or "heyerlivin.com")
    render_heartbeat = str(brand.get("render_heartbeat") or "https://eightglyphs27.onrender.com")
    return [
        {"name": "local_voice", "kind": "localhost", "url": f"http://localhost:{PORT}/"},
        {"name": "local_events", "kind": "localhost_api", "url": f"http://localhost:{PORT}/events.json"},
        {"name": "local_chat", "kind": "localhost_api", "url": f"http://localhost:{PORT}/chat.json"},
        {"name": "handoff_status", "kind": "ssd_report", "url": str(HANDOFF_DIR / "glyph_voice_status.json")},
        {"name": "render_authority", "kind": "render_health", "url": render_heartbeat},
        {"name": "public_website", "kind": "website", "url": f"https://{primary_domain}"},
        {"name": "enterprise_runtime", "kind": "ssd_runtime", "url": str(ENTERPRISE_ROOT)},
    ]


def run_command(args: list[str], *, cwd: Path, timeout: int = 30,
                env_extra: dict[str, str] | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "timeout": True,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "error": f"timed out after {timeout}s",
        }
    except OSError as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}", "stdout": "", "stderr": ""}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def wants_disc_intake(message: str, records: list[dict[str, Any]]) -> bool:
    if not records:
        return False
    text = message.lower()
    if wants(text, DISC_KEYWORDS):
        return True
    # File uploads are bounded enough to record immediately. Directories can be
    # huge, so they require an explicit scan/ingest/route request. Browser file
    # uploads do not expose a source path, so they stay as bounded chat intake.
    return any(item.get("kind") == "file" and item.get("path") for item in records)


def run_disc_intake(records: list[dict[str, Any]], message: str) -> dict[str, Any]:
    if not wants_disc_intake(message, records):
        return {"ran": False, "reason": "no_disc_request"}
    script = REPO_ROOT / "automation" / "disc_workflow.py"
    if not script.exists():
        return {"ran": False, "reason": "missing_disc_workflow", "path": str(script)}

    results: list[dict[str, Any]] = []
    for item in records[:MAX_DISC_SOURCES]:
        source_path = str(item.get("path") or "").strip()
        if not source_path:
            results.append({
                "path": str(item.get("name") or "browser upload"),
                "ok": False,
                "error": "browser upload has no SSD source path; preview/hash intake is available, DISC path scan needs a local path",
            })
            continue
        path = Path(source_path).expanduser()
        if not path.exists():
            results.append({"path": str(path), "ok": False, "error": "source path missing"})
            continue
        result = run_command(
            [sys.executable, "-B", str(script), str(path)],
            cwd=REPO_ROOT,
            timeout=60,
        )
        report_path = None
        report = None
        for part in str(result.get("stdout") or "").split():
            if part.startswith("report="):
                report_path = REPO_ROOT / part.split("=", 1)[1]
                break
        if report_path and report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                report = None
        results.append({
            "path": str(path),
            "ok": result.get("ok", False),
            "report_path": str(report_path) if report_path else None,
            "report": report,
            "stdout": compact_text(result.get("stdout") or "", 500),
            "stderr": compact_text(result.get("stderr") or result.get("error") or "", 500),
        })
    return {"ran": True, "results": results, "source_mutation_allowed": False}


def disc_intake_text(result: dict[str, Any]) -> str:
    if not result.get("ran"):
        if result.get("reason") == "no_disc_request":
            return ""
        return f"DISC did not run: {result.get('reason')}."
    lines: list[str] = []
    for item in result.get("results", []):
        report = item.get("report") or {}
        if item.get("ok"):
            counts = report.get("counts") if isinstance(report, dict) else {}
            count_text = ", ".join(f"{key}: {value}" for key, value in list((counts or {}).items())[:4])
            report_path = item.get("report_path") or "report not found"
            lines.append(
                f"DISC recorded {report.get('record_count', 'the')} records for {Path(item['path']).name}; "
                f"{count_text or 'report created'}; report: {report_path}."
            )
        else:
            lines.append(f"DISC could not record {Path(item['path']).name}: {item.get('stderr') or item.get('error')}.")
    if len(result.get("results", [])) >= MAX_DISC_SOURCES:
        lines.append(f"I capped this pass at {MAX_DISC_SOURCES} sources.")
    return " ".join(lines) + " Source files were not moved, renamed, deleted, or overwritten."


def controller_summary_text() -> str:
    if not (REPO_ROOT / "controller" / "main.py").exists():
        return "Controller is not present in this runtime."
    result = run_command(
        [sys.executable, "-B", "-m", "controller.main", "--repo-root", str(REPO_ROOT), "--audit-summary"],
        cwd=REPO_ROOT,
        timeout=30,
        env_extra={
            "PYTHONPATH": str(REPO_ROOT),
            "GLYPH_ENTRYPOINT_APPROVED": "1",
            "GLYPH_ENTRYPOINT_NAME": "glyph_voice_bridge",
        },
    )
    if not result.get("ok"):
        return f"Controller was reached, but summary failed: {compact_text(result.get('stderr') or result.get('error'), 500)}"
    try:
        data = json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        return f"Controller responded: {compact_text(result.get('stdout'), 700)}"
    return (
        "Controller is reachable. "
        f"Runs: {data.get('run_count', 0)}. "
        f"Unresolved issues: {data.get('unresolved_issue_count', 0)}. "
        f"Audit root: {data.get('audit_storage_root')}."
    )


def enterprise_status_text() -> str:
    if not ENTERPRISE_ROOT.exists():
        return f"Enterprise runtime is not present at {ENTERPRISE_ROOT}."
    queue_new = ENTERPRISE_ROOT / "queue" / "new"
    queue_active = ENTERPRISE_ROOT / "queue" / "active"
    queue_completed = ENTERPRISE_ROOT / "queue" / "completed"
    counts = {}
    for label, path in (("new", queue_new), ("active", queue_active), ("completed", queue_completed)):
        try:
            counts[label] = len([item for item in path.iterdir() if item.is_file()])
        except OSError:
            counts[label] = "unreadable"
    workspace = ENTERPRISE_ROOT / "reports" / "CEO_WORKSPACE.json"
    workspace_state = "present" if workspace.exists() else "missing"
    return (
        "Enterprise runtime is visible on the SSD. "
        f"Queue files: new {counts['new']}, active {counts['active']}, completed {counts['completed']}. "
        f"CEO workspace report is {workspace_state}. This status read did not run the CEO process."
    )


def bridge_status_text() -> str:
    return (
        "Bridge status: chat is connected to Heart; uploads now route into DISC when they are files or when you ask to scan; "
        "controller summary is callable; enterprise status is readable; Render remains a separate web service until its server imports this bridge."
    )


def jsonl_record_count(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return str(sum(1 for line in handle if line.strip()))
    except OSError:
        return "unreadable"


def active_source_layers_text() -> str:
    layers = [
        ("canonical SSD repo", REPO_ROOT),
        ("operator contract", REPO_ROOT / "glyph_operator_contract.md"),
        ("workspace policy", REPO_ROOT / "GLYPH_WORKSPACE_POLICY.json"),
        ("heart", REPO_ROOT / "python_engine" / "glyph_heart.py"),
        ("voice", REPO_ROOT / "python_engine" / "glyph_voice.py"),
        ("terminal bridge", REPO_ROOT / "python_engine" / "glyph_terminal.py"),
        ("DISC workflow", REPO_ROOT / "automation" / "disc_workflow.py"),
        ("controller", REPO_ROOT / "controller" / "main.py"),
        ("handoff status", HANDOFF_DIR / "glyph_voice_status.json"),
        ("Heyer Livin site bundle", REPO_ROOT / "heyer-livin-site" / "index.html"),
        ("deploy server", REPO_ROOT / "server.py"),
        ("Render blueprint", REPO_ROOT / "render.yaml"),
        ("enterprise runtime", ENTERPRISE_ROOT),
        ("AI book ledger", REPO_ROOT / "docs" / "ai_book" / "ledger_event.json"),
    ]
    active = [name for name, path in layers if path.exists()]
    missing = [name for name, path in layers if not path.exists()]
    raw_count = jsonl_record_count(RAW_LEDGER)
    segment_count = jsonl_record_count(SEGMENT_LEDGER)
    absence_count = jsonl_record_count(EVENTS_RAW_DIR / "absence_records.jsonl")
    return (
        "Active SSD source layers: "
        + ", ".join(active)
        + f". Raw ledger records: {raw_count}; derived segment records: {segment_count}; absence records: {absence_count}. "
        + "Render and the public website are output surfaces. The SSD repo, raw ledgers, heart, voice, DISC, controller, "
        + "handoff, and enterprise runtime are the local operating body."
        + (f" Missing or not mounted: {', '.join(missing)}." if missing else "")
    )


def local_status() -> Dict[str, Any]:
    if _SERVER_REF is None:
        return {"status": "starting"}
    heart = _SERVER_REF.heart
    return {
        "status": "online",
        "cycle": heart.cycle(),
        "window": heart.window(),
        "event_count": len(heart.log()),
        "reflection_count": len(heart.reflections()),
        "handoff": str(HANDOFF_DIR / "glyph_voice_status.json"),
    }


def compact_text(value: Any, limit: int = 700) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit] + ("..." if len(text) > limit else "")


def wants(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def attachment_records(attachments: Any) -> list[dict[str, Any]]:
    if not isinstance(attachments, list) or not attachments:
        return []
    cleaned: list[dict[str, Any]] = []
    for item in attachments[:10]:
        if not isinstance(item, dict):
            continue
        text_preview = str(item.get("text_preview") or "")[:_MAX_ATTACHMENT_TEXT]
        cleaned.append({
            "name": str(item.get("name") or "untitled"),
            "path": str(item.get("path") or ""),
            "kind": str(item.get("kind") or "file"),
            "size": item.get("size"),
            "sha256": str(item.get("sha256") or ""),
            "mime": item.get("mime"),
            "text_preview": text_preview,
            "preview_error": item.get("preview_error") or item.get("error"),
            "children_preview": item.get("children_preview") if isinstance(item.get("children_preview"), list) else [],
            "preview_chars": len(text_preview),
        })
    return cleaned


def preview_text_for_path(path: Path) -> tuple[str, Optional[str]]:
    if path.suffix.lower() not in TEXT_PREVIEW_EXTENSIONS:
        return "", "binary preview skipped for path intake"
    try:
        with path.open("rb") as handle:
            data = handle.read(_MAX_ATTACHMENT_TEXT)
        return data.decode("utf-8", errors="replace"), None
    except OSError as exc:
        return "", f"{exc.__class__.__name__}: {exc}"


def source_record_from_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "name": path.name or str(path),
            "path": str(path),
            "kind": "missing",
            "size": None,
            "sha256": "",
            "mime": None,
            "text_preview": "",
            "preview_error": "source path missing",
            "children_preview": [],
            "preview_chars": 0,
        }
    if path.is_dir():
        children = []
        try:
            for child in list(path.iterdir())[:20]:
                children.append({
                    "name": child.name,
                    "kind": "directory" if child.is_dir() else "file" if child.is_file() else "other",
                    "path": str(child),
                })
        except OSError:
            children = []
        return {
            "name": path.name or str(path),
            "path": str(path),
            "kind": "directory",
            "size": None,
            "sha256": "",
            "mime": None,
            "text_preview": "",
            "preview_error": None,
            "children_preview": children,
            "preview_chars": 0,
        }
    preview, preview_error = preview_text_for_path(path)
    try:
        size = path.stat().st_size
    except OSError:
        size = None
    return {
        "name": path.name or str(path),
        "path": str(path),
        "kind": "file",
        "size": size,
        "sha256": "",
        "mime": None,
        "text_preview": preview,
        "preview_error": preview_error,
        "children_preview": [],
        "preview_chars": len(preview),
    }


def path_records_from_message(message: str) -> list[dict[str, Any]]:
    candidates: list[str] = []
    for quoted in re.findall(r"['\"](/(?:Volumes|Users)/[^'\"]+)['\"]", message):
        candidates.append(quoted)
    for root in ("/Volumes/", "/Users/"):
        start = message.find(root)
        while start != -1 and len(candidates) < MAX_DISC_SOURCES:
            tail = message[start:].strip()
            found = None
            for end in range(len(tail), 0, -1):
                candidate = tail[:end].strip().rstrip(".,;:")
                if candidate and Path(candidate).exists():
                    found = candidate
                    break
            if found:
                candidates.append(found)
                start = message.find(root, start + len(found))
            else:
                token = re.split(r"\s+", tail, maxsplit=1)[0].rstrip(".,;:")
                if token:
                    candidates.append(token)
                start = message.find(root, start + max(1, len(token)))
    records = []
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        records.append(source_record_from_path(Path(candidate).expanduser()))
        if len(records) >= MAX_DISC_SOURCES:
            break
    return records


def public_attachment_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "path": item["path"],
            "kind": item["kind"],
            "size": item["size"],
            "sha256": str(item["sha256"])[:16],
            "preview_chars": item["preview_chars"],
        }
        for item in records
    ]


def remember_attachments(records: list[dict[str, Any]]) -> None:
    global _LAST_ATTACHMENTS
    if records:
        _LAST_ATTACHMENTS = records


def attachment_summary(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    names = ", ".join(item["name"] for item in records)
    total_preview = sum(int(item["preview_chars"] or 0) for item in records)
    return (
        f"I received {len(records)} attachment"
        f"{'' if len(records) == 1 else 's'}: {names}. "
        "I kept the source files in place and brought in bounded metadata"
        f"{' plus a text preview' if total_preview else ''}."
    )


def summarize_json_source(source: Any) -> str:
    if not isinstance(source, dict):
        return ""
    parts: list[str] = []
    brand = source.get("brand")
    if isinstance(brand, dict):
        product = brand.get("product") or "the product"
        company = brand.get("company") or "the company"
        framework = brand.get("framework")
        domain = brand.get("primary_domain")
        sentence = f"It identifies {product} under {company}"
        if framework:
            sentence += f" with {framework} as the framework"
        if domain:
            sentence += f" and {domain} as the public domain"
        parts.append(sentence + ".")
    numbers = source.get("numbers")
    if isinstance(numbers, dict) and numbers:
        shown = ", ".join(f"{key}: {value}" for key, value in list(numbers.items())[:5])
        parts.append(f"The number layer includes {shown}.")
    offers = source.get("offers")
    if isinstance(offers, list) and offers:
        names = []
        for offer in offers[:5]:
            if isinstance(offer, dict):
                name = offer.get("name")
                price = offer.get("price")
                names.append(f"{name} ({price})" if name and price else str(name or price or "unnamed offer"))
        if names:
            parts.append("The offer layer lists " + ", ".join(names) + ".")
    guardrails = source.get("guardrails")
    if isinstance(guardrails, dict):
        mode = guardrails.get("mode")
        policy = guardrails.get("send_policy")
        if mode or policy:
            parts.append(f"The guardrail layer says mode is {mode or 'unspecified'} and policy is: {policy or 'not listed'}.")
    if not parts:
        keys = ", ".join(list(source.keys())[:8])
        parts.append(f"It is JSON with these top-level sections: {keys}.")
    return " ".join(parts)


def summarize_attachment(record: dict[str, Any]) -> str:
    name = record["name"]
    if record["kind"] == "missing":
        return f"{name} is missing at the provided path."
    if record["kind"] == "directory":
        children = record.get("children_preview") or []
        names = ", ".join(str(item.get("name")) for item in children[:10] if isinstance(item, dict))
        return f"{name} is a directory. I can see {len(children)} previewed entries" + (f": {names}." if names else ".")
    preview = record.get("text_preview") or ""
    if record.get("preview_error") and not preview:
        return f"{name} is present, but I only have metadata right now: {record['preview_error']}."
    if preview:
        try:
            parsed = json.loads(preview)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            summary = summarize_json_source(parsed)
            if summary:
                return f"{name}: {summary}"
        line_count = preview.count("\n") + 1
        words = [part for part in preview.replace("_", " ").split() if part.strip()]
        first = compact_text(preview, 420)
        return f"{name}: text preview has about {line_count} lines and {len(words)} words. Opening read: {first}"
    return f"{name}: I have metadata only, size {record.get('size')} bytes."


def summarize_attachments(records: list[dict[str, Any]]) -> str:
    if not records:
        return "I do not have an uploaded source in memory yet. Use /upload with a file path first."
    summaries = [summarize_attachment(record) for record in records[:3]]
    return " ".join(summaries)


def attachment_patterns(records: list[dict[str, Any]]) -> str:
    if not records:
        return "I need a source file first. Use /upload, then ask me to extract patterns."
    combined = "\n".join(str(item.get("text_preview") or "") for item in records)
    if not combined.strip():
        return "The current source has no text preview, so I can only compare metadata until it is hydrated or converted to text."
    tokens: list[str] = []
    for raw in combined.lower().replace("_", " ").split():
        word = "".join(ch for ch in raw if ch.isalnum())
        if len(word) >= 4 and word not in STOP_WORDS:
            tokens.append(word)
    counts: dict[str, int] = {}
    for word in tokens:
        counts[word] = counts.get(word, 0) + 1
    top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    if not top:
        return "I can read the source, but there are not enough repeated text units to call out a pattern yet."
    pattern_text = ", ".join(f"{word} x{count}" for word, count in top)
    return f"The strongest repeated terms in the current source are: {pattern_text}. That gives me a first pattern layer to test against later files."


def compare_attachments(records: list[dict[str, Any]]) -> str:
    if len(records) < 2:
        if records:
            return f"I only have one current source, {records[0]['name']}. Upload at least one more file before comparison."
        return "I need at least two uploaded sources before I can compare them."
    lines = []
    for item in records[:5]:
        lines.append(
            f"{item['name']}: {item['kind']}, {item.get('size')} bytes, sha {str(item.get('sha256') or '')[:12] or 'not available'}"
        )
    return "Here is the comparison surface: " + " | ".join(lines)


def capabilities() -> str:
    return (
        "I can talk in this terminal, accept /upload file paths, record file sources through DISC, summarize a source, "
        "extract repeated patterns, compare uploaded sources, show local service status, read controller status, "
        "read enterprise status, and prepare handoff language for Render or the website. "
        "Every plain-English message is preserved in the raw ledger before I answer. "
        "I will not move, delete, post, email, or publish anything unless a separate adapter is explicitly added."
    )


def purpose_text() -> str:
    return (
        "Glyph is the local-to-cloud operating system for your archive. Heart receives cycles and intake. "
        "Voice lets you talk to it. DISC records files and folders without moving them. Raw ledgers preserve the source first. "
        "Render and the website are output surfaces, not the source authority."
    )


def model_text() -> str:
    return (
        "This local bot is not a trained model by itself. It is the Glyph runtime: Python heart, voice, DISC intake, ledgers, "
        "controller checks, and handoff records on the SSD. A hosted language model can be added later as an adapter, "
        "but the source memory belongs to the SSD ledgers and files."
    )


def raw_status_text(raw_record: Dict[str, Any]) -> str:
    if raw_record.get("status") == "observed":
        return f"I recorded your message as raw source before answering: {raw_record['record_id']}."
    return (
        "I received your message, but the raw-ledger write is blocked in this process: "
        f"{raw_record.get('write_error', 'unknown write error')}."
    )


def context_text(raw_record: Dict[str, Any]) -> str:
    return (
        raw_status_text(raw_record) + " "
        "The active context is the SSD repo, the operator contract, raw-first ledger law, heart, voice, DISC, controller, "
        "enterprise runtime, Render handoff, and public website surface."
    )


def learning_text() -> str:
    return (
        "Learning here means building a preserved source graph: raw chat records, DISC file observations, hashes, metadata, "
        "Unicode records, summaries, and handoff reports. It does not require you to re-explain everything linearly, and it does not train weights on the SSD."
    )


def chat_reply(message: str, evt: HeartEvent, attachments: Any = None, speaker: str = "glyph_chat") -> Dict[str, Any]:
    text = message.lower()
    raw_record = capture_chat_raw(message, speaker=speaker, event_stamp=str(evt.stamp))
    status = local_status()
    services = service_registry()
    incoming_records = attachment_records(attachments) + path_records_from_message(message)
    if incoming_records:
        remember_attachments(incoming_records)
    active_records = incoming_records or _LAST_ATTACHMENTS
    source_context_requested = bool(
        incoming_records
        or wants(text, ("summarize", "summary", "explain it", "what is in it", "read it"))
        or wants(text, ("pattern", "extract", "recurring", "repeat"))
        or wants(text, ("compare", "difference", "different"))
    )
    attachment_text = attachment_summary(incoming_records)
    disc_result = run_disc_intake(incoming_records, message) if incoming_records else {"ran": False}
    disc_text = disc_intake_text(disc_result)
    if incoming_records and wants(text, ("compare", "difference", "different")):
        reply = f"{attachment_text} {disc_text} {compare_attachments(active_records)}"
    elif incoming_records and wants(text, ("pattern", "extract", "recurring", "repeat")):
        reply = f"{attachment_text} {disc_text} {attachment_patterns(active_records)}"
    elif incoming_records:
        reply = f"{attachment_text} {disc_text} {summarize_attachments(incoming_records)}"
    elif wants(text, ("what can you do", "help", "commands", "how do i use")):
        reply = capabilities()
    elif wants(text, ("ssd operating map", "operating map", "source layers", "active layers", "ssd map")):
        reply = active_source_layers_text()
    elif wants(text, ("purpose", "what are you", "what is this", "operate", "operating")):
        reply = purpose_text()
    elif wants(text, ("model", "outside source", "external source", "foundation model", "trained")):
        reply = model_text()
    elif wants(text, ("context", "transcript", "remember", "authority", "read everything")):
        reply = context_text(raw_record)
    elif wants(text, ("learn", "learning", "knowledge", "database", "databases", "archive")):
        reply = learning_text()
    elif wants(text, ("bridge", "linked", "connected", "connect", "why not")):
        reply = bridge_status_text()
    elif wants(text, CONTROLLER_KEYWORDS):
        reply = controller_summary_text()
    elif wants(text, ENTERPRISE_KEYWORDS):
        reply = enterprise_status_text()
    elif wants(text, ("summarize", "summary", "explain it", "what is in it", "read it")):
        reply = summarize_attachments(active_records)
    elif wants(text, ("pattern", "extract", "recurring", "repeat")):
        reply = attachment_patterns(active_records)
    elif wants(text, ("compare", "difference", "different")):
        reply = compare_attachments(active_records)
    elif wants(text, ("disc", "scan", "ingest", "route it")):
        reply = (
            "I can route the current source into the DISC lane as a read-only intake: discover, ingest, separate, "
            "then report. Upload a file and I will append the source observation to the raw/DISC ledgers without "
            "moving or deleting the file."
        )
    elif any(word in text for word in ("website", "site", "public")):
        reply = (
            "Website bridge is the next adapter: local chat -> Heart intake -> bounded handoff "
            "-> Render/website service route. The public target is "
            f"{next(item['url'] for item in services if item['name'] == 'public_website')}."
        )
    elif any(word in text for word in ("service", "render", "external", "link")):
        names = ", ".join(item["name"] for item in services)
        reply = f"Service registry is loaded: {names}. External actions stay adapter-gated."
    elif any(word in text for word in ("status", "state", "heartbeat", "alive")):
        reply = (
            f"Local bot is {status['status']}; cycle {status.get('cycle')}, "
            f"window {status.get('window')}, events {status.get('event_count')}, "
            f"reflections {status.get('reflection_count')}."
        )
    else:
        reply = (
            raw_status_text(raw_record) + " "
            "I can now route it as chat context, compare it with uploaded sources, scan a path through DISC, "
            "or answer against the SSD operating map."
        )
    return {
        "reply": reply,
        "event_stamp": str(evt.stamp),
        "raw_record_id": raw_record["record_id"],
        "raw_record_status": raw_record.get("status"),
        "raw_record_error": raw_record.get("write_error"),
        "status": status,
        "services": services,
        "attachments": public_attachment_records(active_records if source_context_requested else []),
    }


def remember_chat(message: str, response: Dict[str, Any]) -> None:
    with _CHAT_LOCK:
        _CHAT_BUFFER.append({
            "at": time.time(),
            "message": message,
            "reply": response["reply"],
            "event_stamp": response["event_stamp"],
        })
        if len(_CHAT_BUFFER) > _MAX_CHAT:
            del _CHAT_BUFFER[:len(_CHAT_BUFFER) - _MAX_CHAT]


class WebVoice:
    def say(self, evt: HeartEvent) -> None:
        with _BUFFER_LOCK:
            _EVENT_BUFFER.append(event_record(evt))
            if len(_EVENT_BUFFER) > _MAX_BUFFER:
                del _EVENT_BUFFER[:len(_EVENT_BUFFER) - _MAX_BUFFER]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):   # silence request logging
        pass

    def write_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def do_GET(self):
        if self.path == "/events.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with _BUFFER_LOCK:
                self.wfile.write(json.dumps(_EVENT_BUFFER).encode("utf-8"))
            return
        if self.path == "/chat.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with _CHAT_LOCK:
                self.wfile.write(json.dumps(_CHAT_BUFFER, ensure_ascii=False).encode("utf-8"))
            return
        if self.path == "/services.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(service_registry(), ensure_ascii=False).encode("utf-8"))
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_PAGE.encode("utf-8"))

    def do_POST(self):
        if self.path in {"/intake", "/chat"} and _SERVER_REF is not None:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                data = json.loads(body) if body.strip() else {}
            except json.JSONDecodeError:
                data = {"raw": body}
            evt = _SERVER_REF.submit(data)
            if self.path == "/chat":
                message = str(data.get("message") or data.get("raw") or "").strip()
                response = chat_reply(
                    message,
                    evt,
                    data.get("attachments"),
                    str(data.get("from") or "glyph_chat"),
                )
                remember_chat(message, response)
                self.write_json({"accepted": True, **response})
            else:
                self.write_json({"accepted": True})
            return
        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Glyph Voice</title>
<style>
 body{font-family:ui-monospace,Menlo,monospace;background:#0b0b0b;color:#e6e6e6;margin:0;padding:16px}
 h1{font-size:14px;letter-spacing:.2em;color:#8ab4ff;margin:0 0 12px}
 .row{display:grid;grid-template-columns:80px 160px 80px 60px 60px 1fr;gap:8px;padding:4px 6px;border-bottom:1px solid #1a1a1a;font-size:12px}
 .row.header{color:#6b7280;font-weight:600;border-bottom:1px solid #333}
 .kind-intake{color:#34d399}.kind-silent_cycle{color:#fbbf24}
 .kind-reflection{color:#a78bfa}.kind-cycle_close_input{color:#60a5fa}
 .kind-activity_check{color:#f87171}
 .state{color:#9ca3af}
 .pay{color:#c4c4c4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 #speak{display:grid;grid-template-columns:1fr minmax(180px,280px) auto;gap:8px;margin:0 0 6px}
 #msg,#fileInput{background:#1a1a1a;border:1px solid #333;color:#e6e6e6;padding:8px 12px;font-family:inherit;font-size:13px;border-radius:4px;min-width:0}
 #msg:focus,#fileInput:focus{outline:none;border-color:#8ab4ff}
 #speak button{background:#8ab4ff;color:#0b0b0b;border:none;padding:8px 16px;font-family:inherit;font-size:13px;font-weight:600;border-radius:4px;cursor:pointer}
 #speak button:hover{background:#aac8ff}
 #attachStatus{min-height:16px;margin:0 0 10px;color:#9ca3af;font-size:11px}
 #chat{display:grid;gap:8px;margin:0 0 16px;max-height:220px;overflow:auto;border:1px solid #1f2937;padding:8px}
 .chatline{font-size:12px;line-height:1.45;color:#d1d5db}
 .chatline.user{color:#8ab4ff}
 .chatline.bot{color:#d1fae5}
 .services{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 16px}
 .services a{font-size:11px;color:#c4b5fd;text-decoration:none;border:1px solid #312e81;padding:4px 6px;border-radius:4px}
</style></head>
<body>
<h1>glyph voice · localhost:8788</h1>
<form id="speak" onsubmit="return speak()">
  <input id="msg" placeholder="talk to Glyph…" autocomplete="off" autofocus />
  <input id="fileInput" type="file" multiple />
  <button type="submit">send</button>
</form>
<div id="attachStatus"></div>
<div id="chat"></div>
<div id="services" class="services"></div>
<div class="row header"><div>stamp</div><div>kind</div><div>state</div><div>cycle</div><div>phase</div><div>payload</div></div>
<div id="list"></div>
<script>
async function tick(){
  const r = await fetch('/events.json'); const d = await r.json();
  const el = document.getElementById('list');
  el.innerHTML = d.slice(-200).reverse().map(e => `
    <div class="row">
      <div>${e.stamp}</div>
      <div class="kind-${e.kind}">${e.kind}</div>
      <div class="state">${e.state}</div>
      <div>${e.cycle}</div>
      <div>${e.phase}</div>
      <div class="pay">${JSON.stringify(e.payload ?? '')}</div>
    </div>`).join('');
}
setInterval(tick, 500); tick();
async function loadChat(){
  const r = await fetch('/chat.json'); const d = await r.json();
  const el = document.getElementById('chat');
  el.innerHTML = d.slice(-20).map(e => `
    <div class="chatline user">you · ${escapeHtml(e.message)}</div>
    <div class="chatline bot">glyph · ${escapeHtml(e.reply)}</div>`).join('');
  el.scrollTop = el.scrollHeight;
}
async function loadServices(){
  const r = await fetch('/services.json'); const d = await r.json();
  document.getElementById('services').innerHTML = d.map(s => `<a href="${s.url}" target="_blank">${s.name}</a>`).join('');
}
function escapeHtml(v){
  return String(v ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
loadChat(); loadServices(); setInterval(loadChat, 1500);
const MAX_UPLOAD_FILES = 5;
const MAX_PREVIEW_BYTES = 12000;
function hex(buffer){
  return Array.from(new Uint8Array(buffer)).map(b => b.toString(16).padStart(2,'0')).join('');
}
function textLike(file){
  return String(file.type || '').startsWith('text/') || /\\.(csv|css|html|js|json|jsx|md|py|txt|ts|tsx|xml|ya?ml)$/i.test(file.name);
}
async function fileRecord(file){
  const bytes = await file.arrayBuffer();
  const sha256 = hex(await crypto.subtle.digest('SHA-256', bytes));
  let text_preview = '';
  let preview_error = '';
  if (textLike(file)) {
    text_preview = new TextDecoder('utf-8').decode(bytes.slice(0, Math.min(bytes.byteLength, MAX_PREVIEW_BYTES)));
  } else {
    preview_error = 'binary preview skipped in browser intake';
  }
  return {
    kind: 'browser_file',
    name: file.name,
    path: '',
    size: file.size,
    sha256,
    mime: file.type || '',
    text_preview,
    preview_error
  };
}
async function collectAttachments(){
  const input = document.getElementById('fileInput');
  const files = Array.from(input.files || []).slice(0, MAX_UPLOAD_FILES);
  const status = document.getElementById('attachStatus');
  if (!files.length) { status.textContent = ''; return []; }
  status.textContent = `reading ${files.length} file${files.length === 1 ? '' : 's'}...`;
  const records = [];
  for (const file of files) records.push(await fileRecord(file));
  status.textContent = `attached ${records.map(r => r.name).join(', ')}`;
  return records;
}
async function speak(){
  const el=document.getElementById('msg');
  const fileInput=document.getElementById('fileInput');
  const attachments = await collectAttachments();
  const v=el.value.trim() || (attachments.length ? 'Read the uploaded source.' : '');
  if(!v) return false;
  await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:v,from:'web_chat',at:Date.now(),attachments})});
  el.value=''; fileInput.value=''; await loadChat(); return false;
}
</script>
</body></html>
"""


def start_web_server(port: int = PORT) -> ThreadingHTTPServer:
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


# ---------------------------------------------------------------------------
# Fan-out: one event, three voices
# ---------------------------------------------------------------------------
class MultiVoice:
    def __init__(self, voices: List[Any]):
        self.voices = voices

    def say(self, evt: HeartEvent) -> None:
        for v in self.voices:
            try:
                v.say(evt)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run(period_seconds: float = 0.5, base_window: int = 10,
        with_file: bool = True, with_notify: bool = True, with_web: bool = True):
    voices: List[Any] = []
    if with_file:
        voices.append(FileVoice())
    voices.append(HandoffVoice())
    if with_notify:
        voices.append(NotifyVoice())
    if with_web:
        voices.append(WebVoice())
        start_web_server(PORT)
        # macOS notification that the web view is ready
        subprocess.run(
            ["osascript", "-e",
             'display notification "Open http://localhost:8788 in your browser" '
             'with title "Glyph voice online"'],
            check=False, timeout=2,
        )

    global _SERVER_REF
    multi = MultiVoice(voices)

    heart = Heart(period_seconds=period_seconds, base_window=base_window,
                  on_event=multi.say)
    server = Server(heart)
    _SERVER_REF = server
    heart.start()

    print(f"Glyph voice running.")
    print(f"  file   : {LOG_PATH}")
    print(f"  handoff: {HANDOFF_DIR / 'glyph_voice_status.json'}")
    print(f"  web    : http://localhost:{PORT}")
    print(f"  notify : macOS notifications enabled")
    print(f"Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        heart.stop()
        print("stopped.")


if __name__ == "__main__":
    run()
