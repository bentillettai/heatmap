#!/usr/bin/env python3
"""Heatmap pipeline helper. Standard library only.

Claude does the reading and judging (see CLAUDE.md); this script keeps the
data files tidy and builds the page.

  python3 tools/heatmap.py merge-items NEW.json     add items, skip known URLs
  python3 tools/heatmap.py check                    validate cards, recompute scores
  python3 tools/heatmap.py build                    write site/index.html
  python3 tools/heatmap.py ingest-feedback DIR_OR_JSON   (ArtifactData out_dir)
  python3 tools/heatmap.py ingest-run-feedback DIR_OR_JSON
  python3 tools/heatmap.py ingest-comments DIR_OR_JSON
  python3 tools/heatmap.py ingest-notes DIR_OR_JSON
  python3 tools/heatmap.py learn NEW.json           add facts people taught it to knowledge.jsonl
  python3 tools/heatmap.py knowledge [CARD|k-ID ...]  facts that apply to cards, or cards a fact applies to
  python3 tools/heatmap.py record-run RUN.json      log the run and freeze its report
  python3 tools/heatmap.py new-urls URL [URL ...]       print the ones not yet read
  python3 tools/heatmap.py api-search PLAN.json OUT.json  search research and funding APIs (tools/apis.py)
  python3 tools/heatmap.py api-orgs [--since DATE] [ORG ...]  recent grants for card organisations
  python3 tools/heatmap.py stats
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import apis

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ITEMS = DATA / "items.jsonl"
CARDS = DATA / "cards.json"
FEEDBACK = DATA / "feedback.jsonl"
RUN_FEEDBACK = DATA / "run_feedback.jsonl"
COMMENTS = DATA / "comments.jsonl"
NOTES = DATA / "notes.jsonl"
RUNS = DATA / "runs.jsonl"
KNOWLEDGE = DATA / "knowledge.jsonl"   # facts and constraints people taught it
FUNDING = DATA / "funding.json"   # recent grants per organisation, from api-orgs
SNAPSHOTS = DATA / "runs"   # one frozen report per run, published as runs/<id>.json
VENN = ROOT / "config" / "venn.json"   # what the page means by problems, technologies, capabilities
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
# Optional card fields: next_step (one line), added (date first shown),
# knowledge (ids of learned facts that shaped the card).
FACT_KINDS = {"constraint", "context", "correction", "lead"}
FACT_TAGS = ("cards", "orgs", "areas", "capabilities", "technology")
FACT_SOURCES = {"comment", "feedback", "run-feedback", "note", "item"}


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
        item.pop("abstract", None)   # api-search candidates carry it; the summary replaces it
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
    facts = {f["id"]: f for f in read_jsonl(KNOWLEDGE)}
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
        for k in c.get("knowledge", []):
            f = facts.get(k)
            if not f:
                problems.append(f"{c['id']}: knowledge {k} not in knowledge.jsonl")
            elif f["status"] != "active":
                problems.append(f"{c['id']}: knowledge {k} is {f['status']}"
                                + (f"; cite {f['superseded_by']} instead" if f.get("superseded_by") else ""))
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
    # Facts aimed at a card or one of its organisations that the card doesn't cite yet.
    active = [f for f in facts.values() if f["status"] == "active"]
    for c in doc["cards"]:
        todo = [f["id"] for f in active if f["id"] not in c.get("knowledge", [])
                and fact_match(f, c) in ("card", "organisation")]
        if todo:
            print(f"to review: {c['id']} may need {', '.join(todo)}")


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
            "trl", "barriers", "next_step", "scores", "knowledge"]
    sig = {k: c.get(k) for k in keep}
    sig["orgs"] = sorted([o["name"], o.get("role")] for o in c["orgs"])
    sig["sources"] = sorted(s["item"] for s in c["sources"])
    return json.dumps(sig, sort_keys=True, ensure_ascii=False)


def learn(new_path):
    """Add facts distilled from comments, feedback and notes to knowledge.jsonl.

    NEW.json is a list. Each entry is a new fact:
      {"fact": one or two plain sentences, "kind": constraint|context|correction|lead,
       "tags": {"cards": [...], "orgs": [...], "areas": [...], "capabilities": [...],
                "technology": [...]},
       "source": {"kind": comment|feedback|run-feedback|note|item, "doc_id", "by",
                  "owner", "date", "target"},
       "supersedes": "k-004" (optional, when it replaces an older fact)}
    or {"retire": "k-007", "why": "..."} for a fact that turned out wrong.
    Nothing is deleted: replaced and retired facts stay, marked as such.
    Facts from notes are kept off the page.
    """
    rows = read_jsonl(KNOWLEDGE)
    by_id = {r["id"]: r for r in rows}
    cards = {c["id"] for c in load_cards()["cards"]}
    today = dt.date.today().isoformat()
    n = max((int(r["id"][2:]) for r in rows), default=0)
    problems, added, retired = [], 0, 0
    for i, e in enumerate(json.loads(Path(new_path).read_text()), 1):
        old = e.get("retire") or e.get("supersedes")
        if old and by_id.get(old, {}).get("status") != "active":
            problems.append(f"entry {i}: {old} is not an active fact")
            continue
        if "retire" in e:
            by_id[old].update(status="retired", retired=today, retired_why=e.get("why", ""))
            retired += 1
            continue
        fact, tags, src = (e.get("fact") or "").strip(), e.get("tags") or {}, e.get("source") or {}
        if not fact or len(fact) > 400:
            problems.append(f"entry {i}: fact must be 1 to 400 characters")
        if e.get("kind") not in FACT_KINDS:
            problems.append(f"entry {i}: kind must be one of {sorted(FACT_KINDS)}")
        if set(tags) - set(FACT_TAGS) or not any(tags.get(k) for k in FACT_TAGS):
            problems.append(f"entry {i}: tags need at least one of {FACT_TAGS}, and nothing else")
        problems += [f"entry {i}: unknown area {a}" for a in tags.get("areas", []) if a not in AREAS]
        problems += [f"entry {i}: unknown card {c}" for c in tags.get("cards", []) if c not in cards]
        if src.get("kind") not in FACT_SOURCES:
            problems.append(f"entry {i}: source.kind must be one of {sorted(FACT_SOURCES)}")
        n += 1
        row = {"id": f"k-{n:03d}", "fact": fact, "kind": e.get("kind"),
               "tags": {k: tags[k] for k in FACT_TAGS if tags.get(k)},
               "source": src, "added": today, "status": "active"}
        if src.get("kind") == "note" or e.get("show") is False:
            row["show"] = False
        if old:
            row["supersedes"] = old
            by_id[old].update(status="superseded", superseded_by=row["id"])
        rows.append(row)
        by_id[row["id"]] = row
        added += 1
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    write_jsonl(KNOWLEDGE, rows)
    active = sum(1 for r in rows if r["status"] == "active")
    print(f"knowledge: {added} added, {retired} retired, {active} active")


def fact_match(fact, card):
    """Why a fact applies to a card, most specific first, or None."""
    t = fact["tags"]
    if card["id"] in t.get("cards", []):
        return "card"
    if {o["name"].lower() for o in card["orgs"]} & {o.lower() for o in t.get("orgs", [])}:
        return "organisation"
    text = f"{card['technology']} {card['headline']}".lower()
    if any(w.lower() in text for w in t.get("technology", [])):
        return "technology"
    if set(card.get("capabilities", [])) & set(t.get("capabilities", [])):
        return "capability"
    if card["area"] in t.get("areas", []):
        return "area"
    return None


def knowledge(args):
    """With card ids, print the active facts that apply to each card; with
    k- ids, the cards each fact applies to; with nothing, every active fact."""
    facts = [f for f in read_jsonl(KNOWLEDGE) if f["status"] == "active"]
    cards = load_cards()["cards"]
    if not args:
        for f in facts:
            tags = "; ".join(f"{k}: {', '.join(v)}" for k, v in f["tags"].items())
            print(f"{f['id']} [{f['kind']}] {f['fact']}  ({tags})")
        print(f"{len(facts)} active facts")
        return
    for a in args:
        if a.startswith("k-"):
            f = next((f for f in facts if f["id"] == a), None)
            hits = [(c["id"], fact_match(f, c)) for c in cards] if f else []
            print(f"{a}: " + (", ".join(f"{cid} ({why})" for cid, why in hits if why) or "no cards"))
        else:
            c = next((c for c in cards if c["id"] == a), None)
            if not c:
                print(f"{a}: no such card")
                continue
            hits = [(f, fact_match(f, c)) for f in facts]
            print(f"{a}:")
            for f, why in hits:
                if why:
                    cited = " (cited)" if f["id"] in c.get("knowledge", []) else ""
                    print(f"  {f['id']} [{f['kind']}, by {why}]{cited} {f['fact']}")


def public_facts(rows):
    """Active facts the page may show, newest first. Facts from notes stay off it."""
    keep = ("id", "fact", "kind", "tags", "added", "run", "supersedes")
    out = []
    for f in reversed(rows):
        if f["status"] == "active" and f.get("show", True):
            src = {k: f["source"].get(k) for k in ("kind", "target", "by", "owner", "date", "doc_id")}
            out.append({**{k: f[k] for k in keep if k in f}, "source": src})
    return out


def _when(ts):
    if not ts:
        return None
    t = dt.datetime.fromisoformat(ts)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def ratings(runs):
    """Votes on each run's work: on the run itself, and on the cards it added
    or changed. A card vote counts for the latest run that touched the card
    before the vote, using each person's latest vote."""
    out = {r["id"]: {"run": {"up": 0, "down": 0}, "cards": {"up": 0, "down": 0}} for r in runs}
    for path, key in ((RUN_FEEDBACK, "run"), (FEEDBACK, "card")):
        latest = {}
        for row in read_jsonl(path):
            latest[row["doc_id"]] = row
        for row in latest.values():
            if row.get("vote") not in ("up", "down"):
                continue
            if key == "run":
                if row["run"] in out:
                    out[row["run"]]["run"][row["vote"]] += 1
                continue
            t = _when(row.get("updated"))
            touched = [r for r in runs if row["card"] in r.get("new_cards", []) + r.get("updated_cards", [])
                       and (t is None or _when(r["time"]) <= t)]
            if touched:
                out[touched[-1]["id"]]["cards"][row["vote"]] += 1
    return out


def snapshot_path(run_id):
    return SNAPSHOTS / f"{run_id}.json"


def record_run(run_path):
    """Log a run in runs.jsonl and freeze its report as data/runs/<id>.json.

    RUN.json holds what Claude knows about the run: kind (daily, sweep or
    manual), items_read, passed_gate, feedback_synced, notes_synced,
    run_feedback_synced, summary, and feedback_review ({summary, applied,
    proposed, facts_used: [{id, effect}]}). This adds the id, time, card
    count, which cards are new or changed since the previous run and which
    facts were learned, and copies the summary into cards.json.
    """
    run = json.loads(Path(run_path).read_text())
    if not KNOWLEDGE.exists():
        KNOWLEDGE.touch()
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
            "learned": [],
            "facts_used": review.get("facts_used", []),
        },
    }
    facts = read_jsonl(KNOWLEDGE)
    known = {f["id"] for f in facts}
    for f in facts:
        if "run" not in f:
            f["run"] = run_id
            record["feedback_review"]["learned"].append(f["id"])
    for u in record["feedback_review"]["facts_used"]:
        if u.get("id") not in known:
            sys.exit(f"facts_used: {u.get('id')} not in knowledge.jsonl")
    write_jsonl(KNOWLEDGE, facts)
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
    runs = [r for r in read_jsonl(RUNS) if "id" in r]
    votes = ratings(runs)
    facts = {f["id"]: f for f in read_jsonl(KNOWLEDGE)}
    for r in reversed(runs):
        p = snapshot_path(r["id"])
        names = {c["id"]: c["headline"] for c in cards}
        if p.exists():
            names = {c["id"]: c["headline"] for c in json.loads(p.read_text())["cards"]}
        review = dict(r.get("feedback_review") or {})
        review["learned"] = [{"id": k, "kind": facts[k]["kind"], "fact": facts[k]["fact"],
                              "status": facts[k]["status"]}
                             if facts[k].get("show", True) else {"id": k, "hidden": True}
                             for k in review.get("learned", []) if k in facts]
        out.append({**r,
                    "feedback_review": review,
                    "ratings": votes[r["id"]],
                    "snapshot": f"runs/{r['id']}.json" if p.exists() else None,
                    "new_cards": [{"id": i, "headline": names.get(i, i)} for i in r.get("new_cards", [])],
                    "updated_cards": [{"id": i, "headline": names.get(i, i)} for i in r.get("updated_cards", [])]})
    return out


def venn(cards):
    """The three circles as the page explains them (config/venn.json), each
    entry with the ids of the cards it covers, best first."""
    conf = json.loads(VENN.read_text())
    ranked = sorted(cards, key=lambda c: c.get("rank", 999))

    def text(c):
        return " ".join([c.get("headline", ""), c.get("problem", ""), c.get("technology", "")])

    def hits(entry, pool):
        pats = [re.compile(r"\b" + re.escape(m), re.I) for m in entry.get("match", [])]
        return [c["id"] for c in pool if any(p.search(text(c)) for p in pats)]

    out = {"problems": [], "technologies": [], "capabilities": []}
    for p in conf["problems"]:
        pool = [c for c in ranked if p["area"] == "other" or c["area"] == p["area"]]
        out["problems"].append({**p, "cards": hits(p, pool)})
    for t in conf["technologies"]:
        out["technologies"].append({**t, "cards": hits(t, ranked)})
    for k in conf["capabilities"]:
        ids = [c["id"] for c in ranked if any(x.split(" (")[0] == k["id"] for x in c.get("capabilities", []))]
        out["capabilities"].append({**k, "cards": ids})
    for group in out.values():
        for e in group:
            e.pop("match", None)
    return out


def payload():
    """Everything the page shows, as one JSON object. The Claude page embeds it;
    the website reads it from Convex (tools/convex_sync.py)."""
    doc = load_cards()
    items = {i["id"]: i for i in read_jsonl(ITEMS)}
    with_sources(doc["cards"], items)
    return {
        "meta": doc["meta"],
        "cards": doc["cards"],
        "organisations": organisations(doc["cards"]),
        "runs": runs_index(doc["cards"]),
        "knowledge": public_facts(read_jsonl(KNOWLEDGE)),
        "item_count": len(items),
        "passed_gate": sum(1 for i in items.values() if i.get("gate") == "pass"),
        "weights": WEIGHTS,
        "venn": venn(doc["cards"]),
    }


def build():
    data = payload()
    html = TEMPLATE.read_text()
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    PAGE.write_text(html.replace("__HEATMAP_DATA__", blob))
    print(f"wrote {PAGE.relative_to(ROOT)} ({PAGE.stat().st_size // 1024} KB, {len(data['cards'])} cards)")


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


def ingest_comments(dump_path):
    """Comment docs live at comments/<id>: {kind card|run, target, text,
    created, by, owner, who, run}. Keep every comment, and a new row if one
    is edited."""
    rows = read_jsonl(COMMENTS)
    seen = {(r["doc_id"], r.get("text")) for r in rows}
    added = 0
    for d in _docs(dump_path):
        if (d["doc_id"], d.get("text")) in seen:
            continue
        rows.append({"doc_id": d["doc_id"], "kind": d.get("kind"), "target": d.get("target"),
                     "text": d.get("text", ""), "run": d.get("run"), "by": d.get("by"),
                     "owner": d.get("owner"), "created": d.get("created"),
                     "synced": dt.date.today().isoformat(), "actioned": False})
        seen.add((d["doc_id"], d.get("text")))
        added += 1
    write_jsonl(COMMENTS, rows)
    print(f"comments: {added} new, {len(rows)} total")


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


def api_search(plan_path, out_path):
    """Run the day's API searches and write new candidate items for Claude to gate.

    PLAN.json: {"since": "2025-01-01", "per_source": 3,
                "searches": [{"area": "datacentre", "query": "\"immersion cooling\"",
                              "sources": ["gtr", "cordis"], "country": "gb"}]}
    sources defaults to all five; country only affects OpenAlex.
    """
    plan = json.loads(Path(plan_path).read_text())
    since = plan.get("since") or (dt.date.today() - dt.timedelta(days=365)).isoformat()
    per_source = plan.get("per_source", 3)
    known = {canonical_url(i["url"]) for i in read_jsonl(ITEMS)}
    card_orgs = {apis.org_key(o["name"]): o["name"] for c in load_cards()["cards"] for o in c["orgs"]}
    out, tally = [], {}
    for s in plan["searches"]:
        for src in s.get("sources") or apis.SOURCES:
            t = tally.setdefault(src, {"new": 0, "known": 0, "errors": []})
            try:
                kwargs = {"country": s["country"]} if src == "openalex" and s.get("country") else {}
                found = apis.SEARCH[src](s["query"], s["area"], since, per_source, **kwargs)
            except Exception as e:   # one source failing must not stop the others
                t["errors"].append(f"{s['query']}: {type(e).__name__}: {e}"[:200])
                continue
            for item in found:
                key = canonical_url(item["url"])
                if key in known:
                    t["known"] += 1
                    continue
                known.add(key)
                for o in item["orgs"]:
                    name = card_orgs.get(apis.org_key(o["name"]))
                    if name:
                        o["name"], o["on_cards"] = name, True
                item["id"] = slug(f"{src}-{item['title']}")
                out.append(item)
                t["new"] += 1
    Path(out_path).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    for src, t in tally.items():
        print(f"{src}: {t['new']} new, {t['known']} already read" + (f", {len(t['errors'])} errors" if t["errors"] else ""))
        for e in t["errors"]:
            print(f"  error: {e}")
    print(f"wrote {len(out)} candidates to {out_path}")


def api_orgs(args):
    """Record recent GtR and CORDIS projects for organisations on cards (UK ones by default)."""
    since = "2022-01-01"
    if args[:1] == ["--since"]:
        since, args = args[1], args[2:]
    cards = load_cards()["cards"]
    names = args or sorted({o["name"] for c in cards for o in c["orgs"] if o.get("country") == "UK"})
    doc = json.loads(FUNDING.read_text()) if FUNDING.exists() else {"orgs": {}}
    for name in names:
        entry = {"checked": dt.date.today().isoformat(), "since": since}
        for src, fn in (("gtr", apis.gtr_org_projects), ("cordis", apis.cordis_org_projects)):
            try:
                entry[src] = fn(name, since)
            except Exception as e:
                entry[src] = {"error": f"{type(e).__name__}: {e}"[:200]}
        doc["orgs"][name] = entry
        found = sum(len(entry[s].get("projects", [])) for s in ("gtr", "cordis"))
        skipped = entry["gtr"].get("skipped")
        print(f"{name}: {found} projects since {since}" + (f" (GtR: {skipped})" if skipped else ""))
    doc["updated"] = dt.date.today().isoformat()
    FUNDING.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


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
          f"comments: {len(read_jsonl(COMMENTS))}, notes: {len(read_jsonl(NOTES))}, runs: {len(read_jsonl(RUNS))}")
    facts = read_jsonl(KNOWLEDGE)
    print(f"knowledge: {sum(1 for f in facts if f['status'] == 'active')} active facts, {len(facts)} ever")
    runs = [r for r in read_jsonl(RUNS) if "id" in r]
    for rid, v in ratings(runs).items():
        up, down = v["run"]["up"] + v["cards"]["up"], v["run"]["down"] + v["cards"]["down"]
        share = f"{round(100 * up / (up + down))}% up" if up + down else "no votes yet"
        print(f"  run {rid}: {up} up, {down} down ({share})")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["stats"]
    {
        "merge-items": lambda: merge_items(*args),
        "check": check,
        "build": build,
        "record-run": lambda: record_run(*args),
        "learn": lambda: learn(*args),
        "knowledge": lambda: knowledge(args),
        "ingest-feedback": lambda: ingest_feedback(*args),
        "ingest-run-feedback": lambda: ingest_feedback(*args, path=RUN_FEEDBACK, key="run"),
        "ingest-comments": lambda: ingest_comments(*args),
        "ingest-notes": lambda: ingest_notes(*args),
        "new-urls": lambda: new_urls(args),
        "api-search": lambda: api_search(*args),
        "api-orgs": lambda: api_orgs(args),
        "stats": stats,
    }[cmd]()
