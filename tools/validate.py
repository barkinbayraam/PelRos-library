#!/usr/bin/env python3
"""Validate the PelRos reference library.

    python tools/validate.py                      # schema + consistency checks of every entry
    python tools/validate.py --check-doi          # … and look every DOI up on Crossref (title + year must match)
    python tools/validate.py --check-doi --write-status   # … and set status doi_verified / checked in the files
    python tools/validate.py entries/raman/x.yaml # only some files

Exit code 1 when an entry has an error (schema, duplicate id, implausible value, DOI not found or not matching
its citation). Network trouble with Crossref is only a warning, so an outage does not block contributions.
Needs pyyaml + jsonschema (tools/requirements.txt).
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import html
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ENTRIES = ROOT / "entries"
SCHEMA = ROOT / "schema" / "entry.schema.json"
TECHNIQUES = ("raman", "ftir", "xrd", "uvvis", "pl")
MAILTO = "barkinbayraam@gmail.com"
USER_AGENT = f"PelRos-library-validator/1.0 (https://github.com/barkinbayraam/PelRos-library; mailto:{MAILTO})"
CROSSREF = "https://api.crossref.org/works/"
TITLE_MIN_RATIO = 0.85

# plausible position ranges per technique (outside → error: usually a unit or typing mistake)
POSITION_RANGE = {"raman": (5.0, 4500.0), "ftir": (100.0, 8000.0), "xrd": (1.0, 170.0)}
D_RANGE = (0.3, 60.0)  # Å
VALUE_RANGE = {"eV": (0.05, 12.0), "nm": (150.0, 5000.0)}


# ----------------------------------------------------------------------------------------------- loading
def _plain(o):
    """YAML gives dates as datetime.date: turn them (recursively) into ISO strings like the JSON the app reads."""
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()[:10]
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_plain(v) for v in o]
    return o


def entry_files(paths: list[str] | None = None) -> list[Path]:
    if paths:
        return [Path(p).resolve() for p in paths]
    return sorted(ENTRIES.glob("*/*.yaml")) + sorted(ENTRIES.glob("*/*.yml"))


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("the file is not a YAML mapping (key: value lines)")
    return _plain(data)


# ----------------------------------------------------------------------------------------------- checks
class Report:
    def __init__(self):
        self.errors: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []

    def error(self, where: str, msg: str):
        self.errors.append((where, msg))

    def warn(self, where: str, msg: str):
        self.warnings.append((where, msg))

    def print(self):
        gh = bool(os.environ.get("GITHUB_ACTIONS"))
        for kind, items in (("error", self.errors), ("warning", self.warnings)):
            for where, msg in items:
                if gh:
                    print(f"::{kind} file={where}::{msg}")
                else:
                    print(f"{kind.upper():8s} {where}: {msg}")


def two_theta(d: float, wavelength: float) -> float | None:
    s = wavelength / (2.0 * d)
    return None if not (0 < s <= 1) else math.degrees(2.0 * math.asin(s))


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def check_entry(path: Path, e: dict, validator, rep: Report) -> None:
    where = _rel(path)
    for err in sorted(validator.iter_errors(e), key=lambda x: list(x.path)):
        loc = "/".join(str(p) for p in err.path) or "(top)"
        rep.error(where, f"schema: {loc}: {err.message}")
    tech = e.get("technique")
    # id must equal <technique folder>/<file name>
    folder, stem = path.parent.name, path.stem
    if folder not in TECHNIQUES:
        rep.error(where, f"entries must be in entries/<technique>/, not '{folder}'")
    if tech and folder != tech:
        rep.error(where, f"technique '{tech}' but the file is in entries/{folder}/")
    if e.get("id") != f"{folder}/{stem}":
        rep.error(where, f"id must be '{folder}/{stem}' (folder/file name), found '{e.get('id')}'")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", stem):
        rep.error(where, "file name: lowercase letters, digits and '-' only")
    peaks = e.get("peaks") or []
    lo, hi = POSITION_RANGE.get(tech, (-math.inf, math.inf))
    wl = (e.get("conditions") or {}).get("wavelength_A")
    for i, p in enumerate(peaks):
        if not isinstance(p, dict):
            continue
        pos = p.get("position")
        if isinstance(pos, (int, float)) and not (lo <= pos <= hi):
            rep.error(where, f"peaks[{i}].position {pos} is outside the plausible {tech} range {lo:g}–{hi:g}")
        if tech == "xrd":
            d = p.get("d")
            if d is None:
                rep.error(where, f"peaks[{i}]: XRD peaks need the d-spacing 'd' (Å)")
            elif isinstance(d, (int, float)):
                if not (D_RANGE[0] <= d <= D_RANGE[1]):
                    rep.error(where, f"peaks[{i}].d {d} Å is outside {D_RANGE[0]}–{D_RANGE[1]} Å")
                elif isinstance(wl, (int, float)) and isinstance(pos, (int, float)):
                    tt = two_theta(d, wl)
                    if tt is None or abs(tt - pos) > 0.15:
                        rep.warn(where, f"peaks[{i}]: d = {d} Å gives 2θ = {tt and round(tt, 3)}° at λ = {wl} Å, "
                                        f"but position is {pos}° (check radiation / wavelength_A)")
            if isinstance(p.get("hkl"), (int, float)):
                rep.error(where, f"peaks[{i}].hkl must be quoted (e.g. \"002\"), YAML read it as the number {p['hkl']}")
        elif p.get("d") is not None:
            rep.warn(where, f"peaks[{i}]: 'd' is only used for XRD")
    if tech == "xrd" and peaks and not isinstance(wl, (int, float)):
        rep.warn(where, "XRD: give conditions.wavelength_A (the 2θ positions refer to it)")
    for i, v in enumerate(e.get("values") or []):
        if not isinstance(v, dict):
            continue
        val, unit = v.get("value"), v.get("unit")
        if isinstance(val, (int, float)) and unit in VALUE_RANGE:
            a, b = VALUE_RANGE[unit]
            if not (a <= val <= b):
                rep.error(where, f"values[{i}].value {val} {unit} is outside the plausible range {a:g}–{b:g} {unit}")
    st = e.get("status")
    if st in ("doi_verified", "values_verified") and not e.get("checked"):
        rep.error(where, f"status {st} needs the date of the check in 'checked'")
    src = e.get("source") or {}
    doi = str(src.get("doi") or "")
    if doi.lower().startswith(("http", "doi:")):
        rep.error(where, "source.doi must be the bare DOI (10.xxxx/…), without https://doi.org/ or doi:")


# ----------------------------------------------------------------------------------------------- Crossref
def normalise_title(s: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))  # Crossref titles may carry <sub>, <i>, MathML
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def title_ratio(a: str, b: str) -> float:
    na, nb = normalise_title(a), normalise_title(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def citation_year(citation: str) -> int | None:
    """Year of a citation like 'Author, Phys. Rev. B 58, 14256 (1998)': the last 4-digit 18xx–20xx number."""
    ys = re.findall(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)", citation or "")
    return int(ys[-1]) if ys else None


def crossref_years(msg: dict) -> set[int]:
    out = set()
    for k in ("issued", "published-print", "published-online", "published", "created"):
        parts = ((msg.get(k) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            out.add(int(parts[0]))
    return out


class Crossref:
    """Polite Crossref client: identifying User-Agent with mailto, retries with back-off, ≤ ~4 requests/s."""

    def __init__(self, min_interval: float = 0.25, retries: int = 4, timeout: float = 20.0, opener=None):
        self.min_interval, self.retries, self.timeout = min_interval, retries, timeout
        self._last = 0.0
        self._cache: dict[str, dict | None] = {}
        self._open = opener or urllib.request.urlopen

    def work(self, doi: str) -> dict | None:
        """Crossref 'message' for the DOI, None when Crossref does not know it (404). Raises OSError on network trouble."""
        key = doi.lower()
        if key in self._cache:
            return self._cache[key]
        url = CROSSREF + urllib.parse.quote(doi, safe="") + "?mailto=" + urllib.parse.quote(MAILTO)
        delay = 1.0
        for attempt in range(self.retries):
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            try:
                with self._open(req, timeout=self.timeout) as r:
                    msg = json.loads(r.read().decode("utf-8"))["message"]
                self._cache[key] = msg
                return msg
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self._cache[key] = None
                    return None
                if e.code in (429, 500, 502, 503, 504) and attempt < self.retries - 1:
                    ra = e.headers.get("Retry-After") if e.headers else None
                    time.sleep(float(ra) if ra and ra.isdigit() else delay)
                    delay *= 2
                    continue
                raise OSError(f"Crossref answered HTTP {e.code}") from e
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as e:
                if attempt < self.retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise OSError(f"cannot reach Crossref ({getattr(e, 'reason', e)})") from e
        raise OSError("Crossref: no answer")


def compare(entry: dict, msg: dict) -> list[str]:
    """Problems between an entry's citation/title and the Crossref record (empty list = match)."""
    src = entry.get("source") or {}
    problems = []
    cr_title = " ".join(msg.get("title") or []) or ""
    if msg.get("subtitle"):
        cr_full = f"{cr_title} {' '.join(msg['subtitle'])}"
    else:
        cr_full = cr_title
    title = src.get("title")
    if not title:
        problems.append(f"source.title is missing; Crossref title: \"{cr_title}\"")
    else:
        r = max(title_ratio(title, cr_title), title_ratio(title, cr_full))
        if r < TITLE_MIN_RATIO:
            problems.append(f"title does not match Crossref (similarity {r:.2f} < {TITLE_MIN_RATIO}): "
                            f"Crossref has \"{cr_title}\"")
    y = citation_year(src.get("citation", ""))
    years = crossref_years(msg)
    if y is None:
        problems.append("no year found in source.citation")
    elif years and y not in years:
        problems.append(f"year {y} in the citation, Crossref has {sorted(years)}")
    return problems


def set_status(path: Path, status: str, checked: str) -> None:
    """Rewrite the top-level 'status:' and 'checked:' lines in place (keeps comments and formatting)."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out, seen_status, seen_checked = [], False, False
    for ln in lines:
        if re.match(r"^status\s*:", ln):
            out.append(f"status: {status}\n")
            seen_status = True
            continue
        if re.match(r"^checked\s*:", ln):
            out.append(f"checked: {checked}\n")
            seen_checked = True
            continue
        out.append(ln)
    if out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    if not seen_status:
        out.append(f"status: {status}\n")
    if not seen_checked:
        i = next((k for k, ln in enumerate(out) if ln.startswith("status:")), len(out) - 1)
        out.insert(i + 1, f"checked: {checked}\n")
    path.write_text("".join(out), encoding="utf-8")


def check_dois(items: list[tuple[Path, dict]], rep: Report, write: bool, client: Crossref | None = None,
               today: str | None = None) -> dict:
    client = client or Crossref()
    today = today or dt.date.today().isoformat()
    stats = {"ok": 0, "mismatch": 0, "not_found": 0, "network": 0, "updated": 0}
    for path, e in items:
        where = _rel(path)
        doi = str((e.get("source") or {}).get("doi") or "").strip()
        if not doi:
            continue
        try:
            msg = client.work(doi)
        except OSError as err:
            stats["network"] += 1
            rep.warn(where, f"DOI {doi} not checked: {err}")
            continue
        status = e.get("status")
        if msg is None:
            stats["not_found"] += 1
            rep.error(where, f"DOI {doi} is not registered at Crossref (check it, or the source is not citable)")
            problems = ["not found"]
        else:
            problems = compare(e, msg)
            for pr in problems:
                rep.error(where, f"DOI {doi}: {pr}")
            stats["ok" if not problems else "mismatch"] += 1
        if not write:
            continue
        if problems and status == "doi_verified":
            set_status(path, "unverified", today)  # a verified entry that no longer matches loses the badge
            stats["updated"] += 1
        elif not problems and status == "unverified" and "recalled" not in str((e.get("source") or {}).get("where") or "").lower():
            # an entry whose numbers were recalled rather than read in the paper stays "unverified" even though its
            # DOI is fine: the badge must not suggest that the values come from that paper
            set_status(path, "doi_verified", today)
            stats["updated"] += 1
    return stats


# ----------------------------------------------------------------------------------------------- main
def validator():
    import jsonschema

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


def validate(paths: list[str] | None = None, rep: Report | None = None) -> tuple[list[tuple[Path, dict]], Report]:
    rep = rep or Report()
    v = validator()
    items: list[tuple[Path, dict]] = []
    ids: dict[str, Path] = {}
    for path in entry_files(paths):
        try:
            e = load(path)
        except (yaml.YAMLError, ValueError, OSError) as err:
            rep.error(_rel(path), f"cannot read: {err}")
            continue
        check_entry(path, e, v, rep)
        eid = e.get("id")
        if isinstance(eid, str):
            if eid in ids:
                rep.error(_rel(path), f"duplicate id '{eid}' (also in {_rel(ids[eid])})")
            ids[eid] = path
        items.append((path, e))
    return items, rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="entry files (default: all of entries/)")
    ap.add_argument("--check-doi", action="store_true", help="look the DOIs up on Crossref")
    ap.add_argument("--write-status", action="store_true", help="with --check-doi: set doi_verified + checked date")
    ap.add_argument("--json", action="store_true", help="print a JSON summary")
    a = ap.parse_args(argv)
    items, rep = validate(a.files or None)
    stats = None
    if a.check_doi:
        stats = check_dois(items, rep, a.write_status)
    rep.print()
    summary = {"entries": len(items), "errors": len(rep.errors), "warnings": len(rep.warnings), "doi": stats}
    if a.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"{len(items)} entries, {len(rep.errors)} errors, {len(rep.warnings)} warnings"
              + (f"; DOIs: {stats}" if stats else ""))
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
