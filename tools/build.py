#!/usr/bin/env python3
"""Build dist/library.json — the single file the PelRos app downloads.

    python tools/build.py                 # writes dist/library.json (only when the entries changed)
    python tools/build.py --out x.json    # somewhere else
    python tools/build.py --root DIR      # build another checkout (used by PelRos' scripts/sync_library.py)

Format: {"format": 1, "version": "YYYY.MM.DD[.N]", "generated": ISO time, "count": n, "sha256": hash of the
entries, "license": "CC BY 4.0", "entries": [...sorted by id]}. The version is the build date; a second build with
other content on the same day gets ".2", ".3", …; unchanged content keeps the existing file (and version) untouched.
Entries with validation errors stop the build.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import validate as V  # noqa: E402

REPO = "https://github.com/barkinbayraam/PelRos-library"
FORMAT = 1


def entries_hash(entries: list[dict]) -> str:
    blob = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def next_version(today: str, previous: str | None) -> str:
    base = today.replace("-", ".")
    if not previous or not previous.startswith(base):
        return base
    rest = previous[len(base):].lstrip(".")
    n = int(rest) if rest.isdigit() else 1
    return f"{base}.{n + 1}"


def assemble(entries: list[dict], prev: dict | None = None, today: str | None = None, force: bool = False) -> dict | None:
    """The library.json object for these entries; None when `prev` already holds exactly these entries."""
    entries = sorted(entries, key=lambda e: e["id"])
    sha = entries_hash(entries)
    if prev and prev.get("sha256") == sha and not force:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    version = next_version(today or now.date().isoformat(), (prev or {}).get("version"))
    by_tech: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for e in entries:
        by_tech[e["technique"]] = by_tech.get(e["technique"], 0) + 1
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
    return {
        "format": FORMAT,
        "name": "PelRos reference library",
        "version": version,
        "generated": now.replace(microsecond=0).isoformat(),
        "count": len(entries),
        "by_technique": by_tech,
        "by_status": by_status,
        "sha256": sha,
        "license": "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)",
        "source": REPO,
        "entries": entries,
    }


def build(root: Path | None = None, out: Path | None = None, today: str | None = None, force: bool = False) -> dict:
    if root is not None:
        V.ROOT = Path(root).resolve()
        V.ENTRIES = V.ROOT / "entries"
    out = out or (V.ROOT / "dist" / "library.json")
    items, rep = V.validate()
    if rep.errors:
        rep.print()
        raise SystemExit(f"{len(rep.errors)} validation error(s): fix them before building")
    entries = [e for _, e in items]
    prev = None
    if out.exists():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = None
    lib = assemble(entries, prev, today, force)
    if lib is None:
        return {"changed": False, "version": prev.get("version"), "count": len(entries), "path": str(out)}
    version = lib["version"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lib, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"changed": True, "version": version, "count": len(entries), "path": str(out)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--root", type=Path, help="library checkout to build (default: this one)")
    ap.add_argument("--force", action="store_true", help="write a new version even if nothing changed")
    a = ap.parse_args(argv)
    r = build(a.root, a.out, force=a.force)
    print(("built" if r["changed"] else "unchanged") + f": {r['path']} version {r['version']}, {r['count']} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
