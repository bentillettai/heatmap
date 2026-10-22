#!/usr/bin/env python3
"""Project log helper: meetings with Henry, the work in between, action items.
Standard library only. See log/README.md for the routine.

  python3 tools/projectlog.py check     validate log/log.json
  python3 tools/projectlog.py build     write log/index.html (runs come from data/runs.jsonl)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "log" / "log.json"
RUNS = ROOT / "data" / "runs.jsonl"
TEMPLATE = ROOT / "log" / "template.html"
PAGE = ROOT / "log" / "index.html"

KINDS = {"meeting", "work"}
OWNERS = {"ben", "Henry", "Claude"}
STATUSES = {"open", "done", "dropped"}


def read_runs():
    if not RUNS.exists():
        return []
    return [json.loads(line) for line in RUNS.read_text().splitlines() if line.strip()]


def problems(log, runs):
    out = []
    run_ids = {r["id"] for r in runs}
    ids, claimed = set(), set()
    for e in log["entries"]:
        where = e.get("id", "?")
        if e.get("id") in ids:
            out.append(f"{where}: duplicate id")
        ids.add(e.get("id"))
        if e.get("kind") not in KINDS:
            out.append(f"{where}: kind must be one of {sorted(KINDS)}")
        for field in ("title", "start", "summary"):
            if not e.get(field):
                out.append(f"{where}: missing {field}")
        for r in e.get("runs", []):
            if r not in run_ids:
                out.append(f"{where}: unknown run {r}")
            if r in claimed:
                out.append(f"{where}: run {r} is already shown under another entry")
            claimed.add(r)
    action_ids = set()
    for a in log["actions"]:
        where = a.get("id", "?")
        if a.get("id") in action_ids:
            out.append(f"{where}: duplicate id")
        action_ids.add(a.get("id"))
        if a.get("owner") not in OWNERS:
            out.append(f"{where}: owner must be one of {sorted(OWNERS)}")
        if a.get("status") not in STATUSES:
            out.append(f"{where}: status must be one of {sorted(STATUSES)}")
        if a.get("from") not in ids:
            out.append(f"{where}: from {a.get('from')} is not an entry")
        if a.get("status") == "done" and not a.get("done"):
            out.append(f"{where}: done actions need a done date")
        if not a.get("text"):
            out.append(f"{where}: missing text")
    return out


def run_entry(r):
    """A run as the page shows it. Runs not claimed by an entry stand alone."""
    return {"id": r["id"], "kind": r.get("kind", "daily"), "time": r.get("time"),
            "items_read": r.get("items_read"), "passed_gate": r.get("passed_gate"),
            "cards": r.get("cards"), "new": len(r.get("new_cards", [])),
            "updated": len(r.get("updated_cards", [])),
            "feedback": (r.get("feedback_synced") or 0) + (r.get("run_feedback_synced") or 0)
                        + (r.get("notes_synced") or 0),
            "summary": r.get("summary", "")}


def check():
    log, runs = json.loads(LOG.read_text()), read_runs()
    found = problems(log, runs)
    for p in found:
        print(p)
    open_count = sum(1 for a in log["actions"] if a["status"] == "open")
    print(f"{len(log['entries'])} entries, {len(runs)} runs, {open_count} open actions, "
          f"{len(found)} problems")
    return not found


def build():
    if not check():
        sys.exit(1)
    log = json.loads(LOG.read_text())
    payload = {**log, "runs": [run_entry(r) for r in read_runs()]}
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    PAGE.write_text(TEMPLATE.read_text().replace("__LOG_DATA__", blob))
    print(f"wrote {PAGE.relative_to(ROOT)} ({PAGE.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check":
        sys.exit(0 if check() else 1)
    elif cmd == "build":
        build()
    else:
        print(__doc__)
        sys.exit(2)
