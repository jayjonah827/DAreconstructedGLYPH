"""KairoGLYPH — site routes (additive).

Serves the KairoGLYPH front end. The glassmorphism SPA shell
(web/kairoglyph.html) covers /, /dashboard, /subscribe, /about, /filing.
Jonah's real research documents are served as their own pages:

  /research  -> web/study.html           (The Jonah Study — full paper)
  /system    -> web/system-diagram.html   (full system architecture)
  /glyph     -> web/glyph-system.html     (the Glyph system reference)

The three document pages get a small "KairoGLYPH" back-link injected at
serve time, so the source files are never modified.

server.py mounts this router before the legacy handlers; the /api/*
routes are unaffected.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["kairo-site"])

_WEB = Path(__file__).resolve().parent / "web"

_BACKLINK = (
    '<a href="/" style="position:fixed;top:10px;left:12px;z-index:9999;'
    'font:600 12px Helvetica,Arial,sans-serif;color:#fff;'
    'background:rgba(0,0,0,.62);border:1px solid rgba(255,255,255,.25);'
    'padding:7px 12px;border-radius:10px;text-decoration:none;'
    '-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);">'
    '‹ KairoGLYPH</a>'
)


def _serve(name: str, inject_nav: bool = False) -> HTMLResponse:
    path = _WEB / name
    if not path.exists():
        return HTMLResponse(
            f"<h1>KairoGLYPH</h1><p>web/{name} not found.</p>", status_code=404)
    html = path.read_text(encoding="utf-8", errors="replace")
    if inject_nav:
        html = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + _BACKLINK,
                      html, count=1)
    return HTMLResponse(html)


@router.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return _serve("kairoglyph.html")


@router.get("/filing", response_class=HTMLResponse)
def filing() -> HTMLResponse:
    return _serve("kairoglyph.html")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return _serve("kairoglyph.html")


@router.get("/dashboard/{slug}", response_class=HTMLResponse)
def dashboard_slug(slug: str) -> HTMLResponse:
    return _serve("kairoglyph.html")


@router.get("/subscribe", response_class=HTMLResponse)
def subscribe() -> HTMLResponse:
    return _serve("kairoglyph.html")


@router.get("/about", response_class=HTMLResponse)
def about() -> HTMLResponse:
    return _serve("kairoglyph.html")


@router.get("/research", response_class=HTMLResponse)
def research() -> HTMLResponse:
    return _serve("study.html", inject_nav=True)


@router.get("/system", response_class=HTMLResponse)
def system() -> HTMLResponse:
    return _serve("system-diagram.html", inject_nav=True)


@router.get("/glyph", response_class=HTMLResponse)
def glyph() -> HTMLResponse:
    return _serve("glyph-system.html", inject_nav=True)
