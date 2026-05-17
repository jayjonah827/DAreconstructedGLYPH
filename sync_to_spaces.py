#!/usr/bin/env python3
"""
sync_to_spaces.py — Sync repo files to DigitalOcean Spaces.

Walks --root, skips noise, computes SHA-256, compares to remote
x-amz-meta-sha256, uploads only on diff. public-read ACL for keys
under public/, private otherwise. JSON logs to stdout. Idempotent.

Env: DO_SPACES_KEY, DO_SPACES_SECRET, DO_SPACES_REGION, DO_SPACES_BUCKET
Usage: python sync_to_spaces.py [--root .] [--dry-run]

All rights reserved, Heyer Livin LLC.
"""
import argparse, hashlib, json, mimetypes, os, sys, fnmatch
from pathlib import Path

def log(event, **kw):
    print(json.dumps({"event": event, **kw}), flush=True)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             ".next", "dist", "build", ".DS_Store", ".idea", ".vscode"}
SKIP_FILES = {".DS_Store", ".env", ".env.local"}

def load_gitignore(root):
    patterns = []
    gi = Path(root) / ".gitignore"
    if gi.exists():
        for line in gi.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line.rstrip("/"))
    return patterns

def is_ignored(rel_path, patterns):
    parts = rel_path.split("/")
    for pat in patterns:
        for part in parts:
            if fnmatch.fnmatch(part, pat):
                return True
        if fnmatch.fnmatch(rel_path, pat):
            return True
    return False

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for k in ("DO_SPACES_KEY", "DO_SPACES_SECRET", "DO_SPACES_REGION", "DO_SPACES_BUCKET"):
        if not os.environ.get(k):
            log("error", reason=f"missing_env:{k}")
            sys.exit(2)

    region = os.environ["DO_SPACES_REGION"]
    bucket = os.environ["DO_SPACES_BUCKET"]
    endpoint = f"https://{region}.digitaloceanspaces.com"

    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError
    except ImportError:
        log("error", reason="boto3_not_installed", fix="pip install boto3")
        sys.exit(2)

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=os.environ["DO_SPACES_KEY"],
        aws_secret_access_key=os.environ["DO_SPACES_SECRET"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 4, "mode": "standard"}),
    )

    root = Path(args.root).resolve()
    log("start", root=str(root), bucket=bucket, region=region, dry_run=args.dry_run)
    gitignore = load_gitignore(root)

    counts = {"uploaded": 0, "skip_unchanged": 0, "would_upload": 0, "errors": 0}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname in SKIP_FILES:
                continue
            fp = Path(dirpath) / fname
            rel = fp.relative_to(root).as_posix()
            if is_ignored(rel, gitignore):
                continue
            try:
                sha = sha256_file(fp)
            except OSError as e:
                log("error", path=rel, reason=str(e)); counts["errors"] += 1; continue

            acl = "public-read" if rel.startswith("public/") else "private"
            ctype = mimetypes.guess_type(rel)[0] or "application/octet-stream"

            try:
                head = client.head_object(Bucket=bucket, Key=rel)
                if head.get("Metadata", {}).get("sha256") == sha:
                    log("skip_unchanged", key=rel); counts["skip_unchanged"] += 1; continue
            except ClientError as e:
                if e.response["Error"]["Code"] not in ("404", "NoSuchKey", "NotFound"):
                    log("error", key=rel, reason=str(e)); counts["errors"] += 1; continue

            if args.dry_run:
                log("would_upload", key=rel, acl=acl); counts["would_upload"] += 1; continue

            try:
                client.upload_file(
                    str(fp), bucket, rel,
                    ExtraArgs={"ACL": acl, "ContentType": ctype, "Metadata": {"sha256": sha}},
                )
                log("uploaded", key=rel, acl=acl, bytes=fp.stat().st_size)
                counts["uploaded"] += 1
            except ClientError as e:
                log("error", key=rel, reason=str(e)); counts["errors"] += 1

    log("done", **counts)
    sys.exit(1 if counts["errors"] else 0)

if __name__ == "__main__":
    main()
