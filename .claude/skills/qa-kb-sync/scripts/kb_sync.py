#!/usr/bin/env python3
"""Deterministic half of the qa-kb-sync skill: config, change detection, decoding, manifest, log.

RUN this script - do not read it into context. Only its output costs tokens.

    kb_sync.py check
    kb_sync.py plan   <folder>
    kb_sync.py save   <folder> <fileId> <result.json>
    kb_sync.py record <folder> <fileId> --status synced|linked|removed|failed
    kb_sync.py log    [--added N --updated N --linked N --removed N --notes "..."]
    kb_sync.py status

State per folder lives in knowledge-base/<folder>/.sync-manifest.json (per machine, git-ignored).
The Drive listing the agent fetches goes in knowledge-base/<folder>/.sync-listing.json.
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
KB = ROOT / "knowledge-base"
CONFIG = KB / "sync-config.json"
LOG = KB / "SYNC_LOG.md"

GOOGLE_NATIVE = "application/vnd.google-apps."
FOLDER_MIME = GOOGLE_NATIVE + "folder"
EXT_BY_MIME = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "text/csv": "csv",
    "text/plain": "txt",
    "text/markdown": "md",
    "application/json": "json",
}
EXPORT_MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
    "csv": "text/csv",
    "txt": "text/plain",
    "md": "text/markdown",
}


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load_config() -> dict:
    if not CONFIG.exists():
        die(f"{CONFIG} not found")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg.setdefault("folders", {})
    cfg.setdefault("max_download_mb", 25)
    cfg.setdefault("never_download_mime_prefixes", ["video/", "audio/"])
    cfg.setdefault("google_export", {})
    cfg.setdefault("exclude_name_patterns", [])
    return cfg


def folder_id(link: str):
    """Accept a full Drive folder URL or a bare id. Returns None if still a placeholder."""
    if not link or link.strip().startswith("<"):
        return None
    m = re.search(r"/folders/([A-Za-z0-9_\-]+)", link) or re.search(r"[?&]id=([A-Za-z0-9_\-]+)", link)
    if m:
        return m.group(1)
    bare = link.strip().rstrip("/")
    return bare if re.fullmatch(r"[A-Za-z0-9_\-]{10,}", bare) else None


def manifest_path(folder: str) -> Path:
    return KB / folder / ".sync-manifest.json"


def load_manifest(folder: str) -> dict:
    p = manifest_path(folder)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"files": {}, "last_sync": None}


def save_manifest(folder: str, data: dict):
    p = manifest_path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _first(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def normalise_listing(raw) -> list:
    """Drive listings come back in several shapes - accept them all."""
    if isinstance(raw, dict):
        for key in ("files", "results", "items", "data", "entries"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
        else:
            raw = [raw] if raw.get("id") else []
    if not isinstance(raw, list):
        die("listing JSON must be a list of files, or an object containing one")

    out = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        # a page wrapper slipped into the array
        inner = _first(it, "files", "results", "items")
        if isinstance(inner, list):
            out.extend(normalise_listing(inner))
            continue
        fid = _first(it, "id", "fileId", "file_id")
        if not fid:
            continue
        size = _first(it, "size", "fileSize", "sizeBytes", default=0)
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = 0
        out.append({
            "id": fid,
            "title": str(_first(it, "title", "name", default=fid)),
            "mimeType": str(_first(it, "mimeType", "mime_type", "mime", default="")),
            "modifiedTime": str(_first(it, "modifiedTime", "modified_time", "updateTime",
                                       "modifiedDate", "version", default="")),
            "size": size,
            "link": _first(it, "viewUrl", "webViewLink", "url", "alternateLink",
                           default=f"https://drive.google.com/file/d/{fid}/view"),
        })
    return out


def read_listing(folder: str) -> list:
    p = KB / folder / ".sync-listing.json"
    if not p.exists():
        die(f"{p} not found - fetch the Drive listing and write it there first")
    return normalise_listing(json.loads(p.read_text(encoding="utf-8")))


def safe_name(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    return (name or "untitled")[:150]


def planned_name(entry: dict, cfg: dict) -> str:
    """The local filename for a Drive file - same rule in plan and save, so they agree."""
    name = safe_name(entry["title"])
    mime = entry["mimeType"]
    if mime.startswith(GOOGLE_NATIVE):
        ext = cfg["google_export"].get(mime)
        if ext and not name.lower().endswith("." + ext):
            name = f"{name}.{ext}"
        return name
    if "." not in name:
        ext = EXT_BY_MIME.get(mime)
        if ext:
            name = f"{name}.{ext}"
    return name


def classify(entry: dict, cfg: dict, known: dict):
    """-> (action, reason). action in: download | link | unchanged | subfolder"""
    mime = entry["mimeType"]
    if mime == FOLDER_MIME:
        return "subfolder", "sub-folders are not synced"

    for pattern in cfg["exclude_name_patterns"]:
        if fnmatch.fnmatch(entry["title"].lower(), pattern.lower()):
            return "excluded", f"matches exclude pattern {pattern}"

    prev = known.get(entry["id"])
    changed = prev is None or prev.get("modifiedTime") != entry["modifiedTime"]
    if not changed and prev.get("status") == "synced":
        return "unchanged", ""
    if not changed and prev.get("status") == "linked":
        return "unchanged", ""

    for prefix in cfg["never_download_mime_prefixes"]:
        if mime.startswith(prefix):
            return "link", f"{mime} - not downloaded by policy"

    cap = int(cfg["max_download_mb"]) * 1024 * 1024
    if entry["size"] and entry["size"] > cap:
        mb = entry["size"] / 1024 / 1024
        return "link", f"{mb:.1f} MB - above the {cfg['max_download_mb']} MB limit"

    if mime.startswith(GOOGLE_NATIVE) and mime not in cfg["google_export"]:
        return "link", f"{mime} - no export format configured"

    return "download", "new" if prev is None else "changed"


# --------------------------------------------------------------------------- commands

def cmd_check(_args):
    cfg = load_config()
    rows, configured = [], 0
    for folder, link in cfg["folders"].items():
        fid = folder_id(link)
        exists = (KB / folder).is_dir()
        if fid:
            configured += 1
        rows.append((folder, fid or "NOT CONFIGURED", "ok" if exists else "MISSING FOLDER"))
    width = max(len(r[0]) for r in rows) if rows else 10
    print(f"config: {CONFIG}")
    print(f"max download: {cfg['max_download_mb']} MB   never download: "
          f"{', '.join(cfg['never_download_mime_prefixes']) or '-'}\n")
    for folder, fid, state in rows:
        print(f"  {folder.ljust(width)}  {fid:<36} {state}")
    print(f"\n{configured} of {len(rows)} folder(s) configured.")
    if configured == 0:
        die("no Drive folder links set - fill them into knowledge-base/sync-config.json", 1)


def cmd_plan(args):
    cfg = load_config()
    folder = args.folder
    if folder not in cfg["folders"]:
        die(f"'{folder}' is not in sync-config.json")
    fid = folder_id(cfg["folders"][folder])
    if not fid:
        die(f"'{folder}' has no Drive link yet")

    listing = read_listing(folder)
    man = load_manifest(folder)
    known = man["files"]

    plan = {"folder": folder, "folder_id": fid, "download": [], "link": [],
            "subfolders": [], "removed": [], "unchanged": 0, "excluded": 0}

    seen = set()
    for e in listing:
        seen.add(e["id"])
        action, reason = classify(e, cfg, known)
        if action == "unchanged":
            plan["unchanged"] += 1
            continue
        if action == "excluded":
            plan["excluded"] += 1
            continue
        if action == "subfolder":
            plan["subfolders"].append({"id": e["id"], "title": e["title"]})
            continue
        item = {"id": e["id"], "title": e["title"], "mimeType": e["mimeType"],
                "modifiedTime": e["modifiedTime"], "link": e["link"],
                "save_as": planned_name(e, cfg), "reason": reason}
        if action == "download":
            if e["mimeType"].startswith(GOOGLE_NATIVE):
                ext = cfg["google_export"][e["mimeType"]]
                item["exportMimeType"] = EXPORT_MIME.get(ext, "text/plain")
            plan["download"].append(item)
        else:
            plan["link"].append(item)

    for fid_known, meta in known.items():
        if fid_known not in seen and meta.get("status") not in ("removed",):
            plan["removed"].append({"id": fid_known, "title": meta.get("title", fid_known),
                                    "local": meta.get("local")})

    print(json.dumps(plan, indent=2, ensure_ascii=False))


def _decode_content(payload) -> bytes:
    if isinstance(payload, str):
        return base64.b64decode(payload)
    if isinstance(payload, dict):
        for key in ("content", "data", "base64", "fileContent", "bytes"):
            if key in payload:
                return _decode_content(payload[key])
        for value in payload.values():
            if isinstance(value, (dict, list)):
                try:
                    return _decode_content(value)
                except Exception:
                    continue
    if isinstance(payload, list):
        for value in payload:
            try:
                return _decode_content(value)
            except Exception:
                continue
    raise ValueError("no base64 content found in the download result")


def cmd_save(args):
    cfg = load_config()
    entry = next((e for e in read_listing(args.folder) if e["id"] == args.file_id), None)
    if entry is None:
        die(f"file id {args.file_id} is not in this folder's listing")

    src = Path(args.result)
    if not src.exists():
        die(f"{src} not found")
    try:
        payload = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = src.read_text(encoding="utf-8").strip()
    try:
        blob = _decode_content(payload)
    except Exception as exc:
        die(f"could not decode the download result: {exc}")

    dest = KB / args.folder / planned_name(entry, cfg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)

    man = load_manifest(args.folder)
    man["files"][entry["id"]] = {
        "title": entry["title"], "local": dest.name, "mimeType": entry["mimeType"],
        "modifiedTime": entry["modifiedTime"], "link": entry["link"],
        "status": "synced", "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_manifest(args.folder, man)
    print(f"saved {dest.relative_to(ROOT)}  ({len(blob):,} bytes)")


def cmd_record(args):
    entry = next((e for e in read_listing(args.folder) if e["id"] == args.file_id), None)
    man = load_manifest(args.folder)
    prev = man["files"].get(args.file_id, {})
    rec = {
        "title": (entry or {}).get("title", prev.get("title", args.file_id)),
        "local": prev.get("local"),
        "mimeType": (entry or {}).get("mimeType", prev.get("mimeType", "")),
        "modifiedTime": (entry or {}).get("modifiedTime", prev.get("modifiedTime", "")),
        "link": (entry or {}).get("link", prev.get("link")),
        "status": args.status,
        "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if args.note:
        rec["note"] = args.note
    man["files"][args.file_id] = rec
    save_manifest(args.folder, man)
    print(f"{args.folder}: {args.file_id} recorded as {args.status}")


def cmd_log(args):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not LOG.exists():
        LOG.write_text(
            "# Knowledge-base sync log\n\n"
            "Written by the `qa-kb-sync` skill. Per machine - not committed.\n\n"
            "| When | Added | Updated | Linked | Removed | Notes |\n"
            "|---|---|---|---|---|---|\n", encoding="utf-8")
    notes = (args.notes or "").replace("|", "/").replace("\n", " ")
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"| {stamp} | {args.added} | {args.updated} | {args.linked} | "
                 f"{args.removed} | {notes} |\n")
    for folder in load_config()["folders"]:
        if manifest_path(folder).exists():
            man = load_manifest(folder)
            man["last_sync"] = stamp
            save_manifest(folder, man)
    print(f"logged to {LOG.relative_to(ROOT)}")


def cmd_status(_args):
    cfg = load_config()
    for folder in cfg["folders"]:
        man = load_manifest(folder)
        files = man["files"]
        if not files and not man.get("last_sync"):
            print(f"  {folder}: never synced")
            continue
        counts = {}
        for meta in files.values():
            counts[meta.get("status", "?")] = counts.get(meta.get("status", "?"), 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        print(f"  {folder}: last sync {man.get('last_sync') or 'unknown'} - {summary or 'no files'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check").set_defaults(func=cmd_check)

    p = sub.add_parser("plan"); p.add_argument("folder"); p.set_defaults(func=cmd_plan)

    p = sub.add_parser("save")
    p.add_argument("folder"); p.add_argument("file_id"); p.add_argument("result")
    p.set_defaults(func=cmd_save)

    p = sub.add_parser("record")
    p.add_argument("folder"); p.add_argument("file_id")
    p.add_argument("--status", required=True, choices=["synced", "linked", "removed", "failed"])
    p.add_argument("--note")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("log")
    for f in ("added", "updated", "linked", "removed"):
        p.add_argument(f"--{f}", type=int, default=0)
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_log)

    sub.add_parser("status").set_defaults(func=cmd_status)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
