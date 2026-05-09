#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shlex
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(os.environ.get("GLYPH_RUNTIME_ROOT", Path(__file__).resolve().parents[1])).resolve()
DEFAULT_URL = os.environ.get("GLYPH_CHAT_URL", "http://127.0.0.1:8788/chat")
MAX_PREVIEW_CHARS = int(os.environ.get("GLYPH_UPLOAD_PREVIEW_CHARS", "12000"))
MAX_UPLOAD_BYTES = int(os.environ.get("GLYPH_UPLOAD_MAX_BYTES", str(2 * 1024 * 1024)))


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        data = response.read().decode("utf-8")
    return json.loads(data)


def get_url(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def ensure_service() -> None:
    if get_url("http://127.0.0.1:8788/services.json"):
        return
    service = REPO_ROOT / "bin" / "glyph-service"
    if service.exists():
        subprocess.run([str(service), "start"], cwd=str(REPO_ROOT), check=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def text_preview(path: Path) -> tuple[str | None, str | None]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"{exc.__class__.__name__}: {exc}"
    if len(raw) > MAX_UPLOAD_BYTES:
        return None, f"file is larger than the upload preview limit ({MAX_UPLOAD_BYTES} bytes)"
    if b"\x00" in raw[:4096]:
        return None, "binary file; preview withheld"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-8", errors="replace")
        except UnicodeError as exc:
            return None, f"{exc.__class__.__name__}: {exc}"
    return text[:MAX_PREVIEW_CHARS], None


def attachment_for(path_text: str) -> dict[str, Any]:
    path = Path(path_text).expanduser().resolve()
    if not path.exists():
        return {
            "kind": "missing",
            "path": str(path),
            "name": path.name or str(path),
            "error": "path does not exist",
        }
    if path.is_dir():
        children = []
        try:
            for child in sorted(path.iterdir(), key=lambda p: p.name.lower())[:50]:
                children.append({
                    "name": child.name,
                    "kind": "directory" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.exists() and child.is_file() else None,
                })
        except OSError as exc:
            children.append({"error": f"{exc.__class__.__name__}: {exc}"})
        return {
            "kind": "directory",
            "path": str(path),
            "name": path.name,
            "children_preview": children,
            "source_mutation_allowed": False,
        }
    stat = path.stat()
    preview, preview_error = text_preview(path)
    return {
        "kind": "file",
        "path": str(path),
        "name": path.name,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "mime": mimetypes.guess_type(path.name)[0],
        "sha256": sha256_file(path),
        "text_preview": preview,
        "preview_error": preview_error,
        "source_mutation_allowed": False,
    }


def print_reply(text: str) -> None:
    print()
    for paragraph in str(text).splitlines() or [""]:
        wrapped = textwrap.fill(
            paragraph,
            width=88,
            initial_indent="Glyph: ",
            subsequent_indent="       ",
        )
        print(wrapped)
    print()


def print_intro(url: str) -> None:
    print("Glyph terminal is connected to the local bot.")
    print("Talk normally. Drop a file path after /upload when you want the bot to intake it.")
    print("Use /scan for folders or any source you explicitly want routed through DISC.")
    print("Examples: /upload ~/Downloads/report.pdf   |   /scan ~/Documents/source-folder   |   /status   |   /quit")
    print(f"Endpoint: {url}")
    print()


def parse_upload(line: str) -> list[str]:
    parts = shlex.split(line)
    if not parts:
        return []
    return parts[1:]


def interactive(url: str) -> int:
    ensure_service()
    print_intro(url)
    while True:
        try:
            line = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        lowered = line.lower()
        if lowered in {"/quit", "quit", "exit", "/exit"}:
            return 0
        if lowered in {"/help", "help"}:
            print_intro(url)
            continue
        if lowered in {"/status", "status"}:
            payload = {"message": "status", "from": "glyph_terminal"}
        elif lowered.startswith("/upload ") or lowered.startswith("upload "):
            paths = parse_upload(line)
            if not paths:
                print_reply("Give me a file path after upload.")
                continue
            attachments = [attachment_for(item) for item in paths]
            names = ", ".join(item.get("name", item.get("path", "source")) for item in attachments)
            payload = {
                "message": f"I uploaded {names}.",
                "from": "glyph_terminal",
                "attachments": attachments,
            }
        elif lowered.startswith("/scan ") or lowered.startswith("scan "):
            paths = parse_upload(line)
            if not paths:
                print_reply("Give me a file or folder path after scan.")
                continue
            attachments = [attachment_for(item) for item in paths]
            names = ", ".join(item.get("name", item.get("path", "source")) for item in attachments)
            payload = {
                "message": f"Scan, ingest, and record {names} through DISC.",
                "from": "glyph_terminal",
                "attachments": attachments,
            }
        else:
            payload = {"message": line, "from": "glyph_terminal"}
        try:
            response = post_json(url, payload)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            print_reply(f"I could not reach the local bot yet: {exc}")
            continue
        print_reply(response.get("reply", "I heard you."))
    return 0


def send_once(url: str, message: str, uploads: list[str]) -> int:
    ensure_service()
    payload: dict[str, Any] = {"message": message, "from": "glyph_terminal"}
    if uploads:
        payload["attachments"] = [attachment_for(item) for item in uploads]
    response = post_json(url, payload)
    print_reply(response.get("reply", "I heard you."))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Plain-English terminal client for the local Glyph bot.")
    parser.add_argument("message", nargs="*", help="Send one message and exit. Omit for interactive mode.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Local Glyph chat endpoint.")
    parser.add_argument("--upload", action="append", default=[], help="Attach a file or folder path.")
    args = parser.parse_args()

    if args.message or args.upload:
        message = " ".join(args.message).strip() or "I uploaded a source file."
        return send_once(args.url, message, args.upload)
    return interactive(args.url)


if __name__ == "__main__":
    raise SystemExit(main())
