#!/usr/bin/env python3
"""Heatmap pipeline helper. Standard library only.

Claude does the reading and judging (see CLAUDE.md); this script keeps the
data files tidy and builds the page.

  python3 tools/heatmap.py merge-items NEW.json     add items, skip known URLs
  python3 tools/heatmap.py check                    validate cards, recompute scores
  python3 tools/heatmap.py build                    write site/index.html
  python3 tools/heatmap.py ingest-feedback DIR_OR_JSON   (ArtifactData out_dir)
  python3 tools/heatmap.py ingest-run-feedback DIR_OR_JSON
  python3 tools/heatmap.py ingest-notes DIR_OR_JSON
  python3 tools/heatmap.py record-run RUN.json      log the run and freeze its report
  python3 tools/heatmap.py new-urls URL [URL ...]       print the ones not yet read
  python3 tools/heatmap.py stats
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ITEMS = DATA / "items.jsonl"
CARDS = DATA / "cards.json"
FEEDBACK = DATA / "feedback.jsonl"
RUN_FEEDBACK = DATA / "run_feedback.jsonl"
NOTES = DATA / "notes.jsonl"
RUNS = DATA / "runs.jsonl"
SNAPSHOTS = DATA / "runs"   # one frozen report per run, published as runs/<id>.json
TEMPLATE = ROOT / "site" / "template.html"
PAGE = ROOT / "site" / "index.html"

# Weights from config/rubric.md. Keep the two in step.
WEIGHTS = {
    "venn_fit": 30,
    "manufacturing_key": 20,
    "evidence": 15,
    "novelty": 15,
    "uk_relevance": 10,
    "contactable": 10,
}
AREAS = {"datacentre", "aerospace", "motorsport", "other"}
CARD_FIELDS = [
    "id", "area", "headline", "problem", "technology", "capabilities",
    "why", "applicability", "trl", "barriers", "orgs", "sources", "scores",
]
# Optional card fields: next_step (one line), added (date first shown).


def read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def canonical_url(url):
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, "", ""))


def slug(text, n=48):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n].rstrip("-") or "item"


def merge_items(new_path):
    items = read_jsonl(ITEMS)
    known = {canonical_url(i["url"]) for i in items}
    ids = {i["id"] for i in items}
    added = skipped = 0
    for item in json.loads(Path(new_path).read_text()):
        key = canonical_url(item["url"])
        if key in known:
            skipped += 1
            continue
        item.setdefault("found", dt.date.today().isoformat())
        base = item.get("id") or slug(item.get("title") or key)
        uid, n = base, 2
        while uid in ids:
            uid, n = f"{base}-{n}", n + 1
        item["id"] = uid
        items.append(item)
        known.add(key)
        ids.add(uid)
        added += 1
    write_jsonl(ITEMS, items)
    print(f"added {added}, skipped {skipped} already known, total {len(items)}")


def score(card):
    s = card["scores"]
    total = sum(WEIGHTS[k] * s[k] for k in WEIGHTS) / 5
    return round(total)


def load_cards():
    return json.loads(CARDS.read_text())


def check():
    doc = load_cards()
    items = {i["id"] for i in read_jsonl(ITEMS)}
    problems = []
    seen = set()
    for c in doc["cards"]:
        for f in CARD_FIELDS:
            if f not in c:
                problems.append(f"{c.get('id')}: missing {f}")
        if c.get("id") in seen:
            problems.append(f"{c['id']}: duplicate id")
        seen.add(c.get("id"))
        if c.get("area") not in AREAS:
            problems.append(f"{c.get('id')}: unknown area {c.get('area')}")
        for k in WEIGHTS:
            v = c.get("scores", {}).get(k)
            if not isinstance(v, (int, float)) or not 0 <= v <= 5:
                problems.append(f"{c.get('id')}: score {k}={v} not in 0-5")
        for src in c.get("sources", []):
            if src.get("item") and src["item"] not in items:
                problems.append(f"{c['id']}: source item {src['item']} not in items.jsonl")
        if c.get("applicability", {}).get("type") not in ("stated", "inferred"):
            problems.append(f"{c.get('id')}: applicability.type must be stated or inferred")
        c.setdefault("added", dt.date.today().isoformat())
        if not problems:
            c["score"] = score(c)
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    # Rank within each area and overall.
    doc["cards"].sort(key=lambda c: -c["score"])
    for i, c in enumerate(doc["cards"], 1):
        c["rank"] = i
    for area in AREAS:
        for i, c in enumerate([c for c in doc["cards"] if c["area"] == area], 1):
            c["area_rank"] = i
    CARDS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"ok: {len(doc['cards'])} cards")


def organisations(cards):
    orgs = {}
    for c in cards:
        for o in c["orgs"]:
            key = o["name"].lower()
            rec = orgs.setdefault(key, {
                "name": o["name"], "type": o.get("type"), "country": o.get("country"),
                "roles": set(), "cards": [], "areas": set(),
            })
            rec["roles"].add(o.get("role", "mentioned"))
            rec["cards"].append(c["id"])
            rec["areas"].add(c["area"])
            if not rec.get("country") and o.get("country"):
                rec["country"] = o["country"]
    out = []
    for rec in orgs.values():
        rec["roles"] = sorted(rec["roles"])
        rec["areas"] = sorted(rec["areas"])
        out.append(rec)
    out.sort(key=lambda r: (-len(r["cards"]), r["name"].lower()))
    return out


def with_sources(cards, items):
    """Fill each source's url, title, publisher and date from items.jsonl."""
    for c in cards:
        for src in c["sources"]:
            it = items.get(src.get("item"))
            if it:
                src.setdefault("url", it["url"])
                src.setdefault("title", it.get("title"))
                src.setdefault("publisher", it.get("publisher"))
                src.setdefault("date", it.get("date"))
    return cards


def card_signature(c):
    """What counts as a change to a card between runs (not rank, which moves
    whenever another card does, and not organisation country tidying)."""
    keep = ["headline", "problem", "technology", "capabilities", "why", "applicability",
            "trl", "barriers", "next_step", "scores"]
    sig = {k: c.get(k) for k in keep}
    sig["orgs"] = sorted([o["name"], o.get("role")] for o in c["orgs"])
    sig["sources"] = sorted(s["item"] for s in c["sources"])
    return json.dumps(sig, sort_keys=True, ensure_ascii=False)


def snapshot_path(run_id):
    return SNAPSHOTS / f"{run_id}.json"


def record_run(run_path):
    """Log a run in runs.jsonl and freeze its report as data/runs/<id>.json.

    RUN.json holds what Claude knows about the run: kind (daily, sweep or
    manual), items_read, passed_gate, feedback_synced, notes_synced,
    run_feedback_synced, summary, and feedback_review ({summary, applied,
    proposed}). This adds the id, time, card count and which cards are new
    or changed since the previous run, and copies the summary into cards.json.
    """
    run = json.loads(Path(run_path).read_text())
    runs = read_jsonl(RUNS)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    today = now.date().isoformat()
    seq = 1 + sum(1 for r in runs if r.get("date") == today)
    run_id = f"{today}-{seq}"
    doc = load_cards()
    prev = {}
    if runs and snapshot_path(runs[-1]["id"]).exists():
        prev = {c["id"]: c for c in json.loads(snapshot_path(runs[-1]["id"]).read_text())["cards"]}
    review = run.get("feedback_review") or {}
    record = {
        "id": run_id,
        "date": today,
        "time": now.isoformat().replace("+00:00", "Z"),
        "kind": run.get("kind", "daily"),
        "items_read": run.get("items_read", 0),
        "passed_gate": run.get("passed_gate", 0),
        "cards": len(doc["cards"]),
        "new_cards": [c["id"] for c in doc["cards"] if c["id"] not in prev],
        "updated_cards": [c["id"] for c in doc["cards"]
                          if c["id"] in prev and card_signature(c) != card_signature(prev[c["id"]])],
        "feedback_synced": run.get("feedback_synced", 0),
        "notes_synced": run.get("notes_synced", 0),
        "run_feedback_synced": run.get("run_feedback_synced", 0),
        "summary": run.get("summary", ""),
        "feedback_review": {
            "summary": review.get("summary") or "No new feedback since the last run.",
            "applied": review.get("applied", []),
            "proposed": review.get("proposed", []),
        },
    }
    doc["meta"].update(updated=today, run_id=run_id, run_summary=record["summary"])
    CARDS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    items = {i["id"]: i for i in read_jsonl(ITEMS)}
    SNAPSHOTS.mkdir(exist_ok=True)
    snap = {"run": record, "meta": doc["meta"], "cards": with_sources(doc["cards"], items)}
    snapshot_path(run_id).write_text(json.dumps(snap, ensure_ascii=False) + "\n")
    runs.append(record)
    write_jsonl(RUNS, runs)
    print(f"run {run_id}: {len(record['new_cards'])} new, {len(record['updated_cards'])} updated")
    print(f"publish with files: runs/{run_id}.json -> {snapshot_path(run_id).relative_to(ROOT)}")


def runs_index(cards):
    """Runs newest first, with headlines for the cards each one added or changed."""
    out = []
    for r in reversed(read_jsonl(RUNS)):
        if "id" not in r:
            continue
        p = snapshot_path(r["id"])
        names = {c["id"]: c["headline"] for c in cards}
        if p.exists():
            names = {c["id"]: c["headline"] for c in json.loads(p.read_text())["cards"]}
        out.append({**r,
                    "snapshot": f"runs/{r['id']}.json" if p.exists() else None,
                    "new_cards": [{"id": i, "headline": names.get(i, i)} for i in r.get("new_cards", [])],
                    "updated_cards": [{"id": i, "headline": names.get(i, i)} for i in r.get("updated_cards", [])]})
    return out


def build():
    doc = load_cards()
    items = {i["id"]: i for i in read_jsonl(ITEMS)}
    with_sources(doc["cards"], items)
    payload = {
        "meta": doc["meta"],
        "cards": doc["cards"],
        "organisations": organisations(doc["cards"]),
        "runs": runs_index(doc["cards"]),
        "item_count": len(items),
        "passed_gate": sum(1 for i in items.values() if i.get("gate") == "pass"),
        "weights": WEIGHTS,
    }
    html = TEMPLATE.read_text()
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    PAGE.write_text(html.replace("__HEATMAP_DATA__", blob))
    print(f"wrote {PAGE.relative_to(ROOT)} ({PAGE.stat().st_size // 1024} KB, {len(doc['cards'])} cards)")


def _docs(dump_path):
    """Read documents saved by ArtifactData list with out_dir (one JSON file
    per document, named by doc id), or a single JSON dump of a list result."""
    path = Path(dump_path)
    if path.is_dir():
        return [{"doc_id": f.stem, **json.loads(f.read_text())} for f in sorted(path.glob("*.json"))]
    raw = json.loads(path.read_text())
    docs = raw.get("documents") or raw.get("docs") or raw if isinstance(raw, dict) else raw
    if isinstance(docs, dict):
        docs = docs.get("items", [])
    out = []
    for d in docs:
        body = d.get("data", d)
        out.append({"doc_id": d.get("id") or d.get("doc_id"), **body})
    return out


def ingest_feedback(dump_path, path=FEEDBACK, key="card"):
    """Feedback docs live at feedback/<card>~<viewer id> (or
    runfeedback/<run id>~<viewer id>); keep every revision."""
    rows = read_jsonl(path)
    seen = {(r.get("doc_id"), r.get("updated")) for r in rows}
    added = 0
    for d in _docs(dump_path):
        target = d.get(key) or (d.get("doc_id") or "").split("~")[0]
        rev = (d.get("doc_id"), d.get("updated"))
        if rev in seen:
            continue
        rows.append({"doc_id": d.get("doc_id"), key: target, "vote": d.get("vote"),
                     "why": d.get("why", ""), "by": d.get("by"), "owner": d.get("owner"),
                     "updated": d.get("updated"),
                     "synced": dt.date.today().isoformat(), "actioned": False})
        seen.add(rev)
        added += 1
    write_jsonl(path, rows)
    print(f"{path.stem}: {added} new, {len(rows)} total")


def ingest_notes(dump_path):
    rows = read_jsonl(NOTES)
    seen = {r["doc_id"] for r in rows}
    added = 0
    for d in _docs(dump_path):
        if d["doc_id"] in seen:
            continue
        rows.append({"doc_id": d["doc_id"], "text": d.get("text", ""), "area": d.get("area"),
                     "by": d.get("by"), "created": d.get("created"),
                     "synced": dt.date.today().isoformat(),
                     "actioned": False})
        added += 1
    write_jsonl(NOTES, rows)
    print(f"notes: {added} new, {len(rows)} total")


def new_urls(urls):
    """Print the URLs that are not already in items.jsonl."""
    known = {canonical_url(i["url"]) for i in read_jsonl(ITEMS)}
    for u in urls:
        if canonical_url(u) not in known:
            print(u)


def stats():
    items = read_jsonl(ITEMS)
    doc = load_cards()
    by_area = {}
    for c in doc["cards"]:
        by_area[c["area"]] = by_area.get(c["area"], 0) + 1
    passed = sum(1 for i in items if i.get("gate") == "pass")
    print(f"items: {len(items)} ({passed} passed the thermal gate)")
    print(f"cards: {len(doc['cards'])} {by_area}")
    print(f"feedback rows: {len(read_jsonl(FEEDBACK))}, run feedback: {len(read_jsonl(RUN_FEEDBACK))}, "
          f"notes: {len(read_jsonl(NOTES))}, runs: {len(read_jsonl(RUNS))}")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["stats"]
    {
        "merge-items": lambda: merge_items(*args),
        "check": check,
        "build": build,
        "record-run": lambda: record_run(*args),
        "ingest-feedback": lambda: ingest_feedback(*args),
        "ingest-run-feedback": lambda: ingest_feedback(*args, path=RUN_FEEDBACK, key="run"),
        "ingest-notes": lambda: ingest_notes(*args),
        "new-urls": lambda: new_urls(args),
        "stats": stats,
    }[cmd]()
