#!/usr/bin/env python3
"""Heatmap pipeline helper. Standard library only.

Claude does the reading and judging (see CLAUDE.md); this script keeps the
data files tidy and builds the page.

  python3 tools/heatmap.py merge-items NEW.json     add items, skip known URLs
  python3 tools/heatmap.py check                    validate cards, recompute scores
  python3 tools/heatmap.py build                    write site/index.html
  python3 tools/heatmap.py ingest-feedback DIR_OR_JSON   (ArtifactData out_dir)
  python3 tools/heatmap.py ingest-notes DIR_OR_JSON
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
NOTES = DATA / "notes.jsonl"
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


def build():
    doc = load_cards()
    items = {i["id"]: i for i in read_jsonl(ITEMS)}
    for c in doc["cards"]:
        for src in c["sources"]:
            it = items.get(src.get("item"))
            if it:
                src.setdefault("url", it["url"])
                src.setdefault("title", it.get("title"))
                src.setdefault("publisher", it.get("publisher"))
                src.setdefault("date", it.get("date"))
    payload = {
        "meta": doc["meta"],
        "cards": doc["cards"],
        "organisations": organisations(doc["cards"]),
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


def ingest_feedback(dump_path):
    """Feedback docs live at feedback/<card>~<viewer id>; keep every revision."""
    rows = read_jsonl(FEEDBACK)
    seen = {(r.get("doc_id"), r.get("updated")) for r in rows}
    added = 0
    for d in _docs(dump_path):
        card = d.get("card") or (d.get("doc_id") or "").split("~")[0]
        key = (d.get("doc_id"), d.get("updated"))
        if key in seen:
            continue
        rows.append({"doc_id": d.get("doc_id"), "card": card, "vote": d.get("vote"),
                     "why": d.get("why", ""), "by": d.get("by"), "updated": d.get("updated"),
                     "synced": dt.date.today().isoformat(), "actioned": False})
        seen.add(key)
        added += 1
    write_jsonl(FEEDBACK, rows)
    print(f"feedback: {added} new, {len(rows)} total")


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
    print(f"feedback rows: {len(read_jsonl(FEEDBACK))}, notes: {len(read_jsonl(NOTES))}")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["stats"]
    {
        "merge-items": lambda: merge_items(*args),
        "check": check,
        "build": build,
        "ingest-feedback": lambda: ingest_feedback(*args),
        "ingest-notes": lambda: ingest_notes(*args),
        "new-urls": lambda: new_urls(args),
        "stats": stats,
    }[cmd]()
