#!/usr/bin/env python3
"""Move data between the pipeline and the Heatmap website's Convex backend.
Standard library only. The pipeline doesn't depend on the website: it builds
the report as before, pushes it here, and pulls what people wrote.

  python3 tools/convex_sync.py push [--all]        latest report, plus run reports not yet there
  python3 tools/convex_sync.py pull OUT_DIR         votes, comments and notes from the website,
                                                    as OUT_DIR/<collection>/<doc id>.json (the
                                                    ArtifactData out_dir layout, so ingest-* read it)
  python3 tools/convex_sync.py mirror DIR           copy documents pulled from the Claude page
                                                    (ArtifactData out_dir) to the website
  python3 tools/convex_sync.py invite EMAIL NAME [--owner] [--by ID]
                                                    let someone log in (--by keeps their Claude page id)
  python3 tools/convex_sync.py people               who can log in, and who has (no emails shown)

Needs CONVEX_DEPLOY_KEY (production deploy key from the Convex dashboard), or
CONVEX_URL and CONVEX_ADMIN_KEY for a local backend. Never print either.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heatmap  # noqa: E402

COLLECTIONS = ("feedback", "runfeedback", "comments", "notes")


def deployment():
    url, key = os.environ.get("CONVEX_URL"), os.environ.get("CONVEX_ADMIN_KEY")
    if url and key:
        return url.rstrip("/"), key
    key = os.environ.get("CONVEX_DEPLOY_KEY")
    if not key or "|" not in key:
        sys.exit("CONVEX_DEPLOY_KEY is not set (or CONVEX_URL and CONVEX_ADMIN_KEY).")
    name = key.split("|", 1)[0].split(":", 1)[-1]
    return f"https://{name}.convex.cloud", key


def call(kind, path, args=None):
    """Run a Convex function as admin: kind is query or mutation, path like sync:putReport."""
    url, key = deployment()
    body = json.dumps({"path": path, "args": args or {}, "format": "json"}).encode()
    req = urllib.request.Request(f"{url}/api/{kind}", data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Convex {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            out = json.loads(res.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"{path}: HTTP {e.code} {e.read()[:300].decode(errors='replace')}")
    if out.get("status") != "success":
        sys.exit(f"{path}: {out.get('errorMessage') or out}")
    return out.get("value")


def push(everything=False):
    data = heatmap.payload()
    run_id = data["meta"].get("run_id") or "latest"
    call("mutation", "sync:putReport", {"runId": run_id, "json": json.dumps(data, ensure_ascii=False)})
    have = set() if everything else set(call("query", "sync:snapshotIds"))
    sent = 0
    for r in data["runs"]:
        p = heatmap.snapshot_path(r["id"])
        if r["id"] in have or not p.exists():
            continue
        call("mutation", "sync:putSnapshot", {"runId": r["id"], "json": p.read_text().strip()})
        sent += 1
    print(f"website: report for run {run_id} ({len(data['cards'])} cards), {sent} run reports sent")


def file_name(doc_id):
    # ArtifactData spells "~" as "@" in file names; keep the same ids here so a
    # document seen in both places is recognised as one.
    return doc_id.replace("~", "@") + ".json"


def pull(out_dir):
    out = Path(out_dir)
    for c in COLLECTIONS:
        docs = call("query", "sync:listEntries", {"collection": c})
        (out / c).mkdir(parents=True, exist_ok=True)
        for d in docs:
            (out / c / file_name(d["id"])).write_text(json.dumps(d["data"], indent=2, ensure_ascii=False) + "\n")
        print(f"{c}: {len(docs)} on the website")


def mirror(src_dir):
    src = Path(src_dir)
    for c in COLLECTIONS:
        files = sorted((src / c).glob("*.json")) if (src / c).is_dir() else []
        docs = []
        for f in files:
            raw = json.loads(f.read_text())
            data = raw["data"] if isinstance(raw.get("data"), dict) and "id" in raw else raw
            doc_id = f.stem.replace("@", "~") if c in ("feedback", "runfeedback") else f.stem
            docs.append({"id": doc_id, "data": data})
        added = call("mutation", "sync:upsertEntries", {"collection": c, "docs": docs}) if docs else 0
        print(f"{c}: {len(docs)} from the Claude page, {int(added)} new on the website")


def invite(args):
    if len(args) < 2:
        sys.exit("usage: invite EMAIL NAME [--owner] [--by ID]")
    email, name = args[0], args[1]
    owner = "--owner" in args
    by = args[args.index("--by") + 1] if "--by" in args else None
    who = call("mutation", "sync:putPerson", {"email": email, "name": name, "owner": owner,
                                              **({"by": by} if by else {})})
    print(f"invited {name} (id {who})")


def people():
    for p in call("query", "sync:listPeople"):
        print(f"{p['name']}{' (owner)' if p['owner'] else ''}: {'signed up' if p['signedUp'] else 'not signed up yet'}")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "push":
        push("--all" in rest)
    elif cmd == "pull" and rest:
        pull(rest[0])
    elif cmd == "mirror" and rest:
        mirror(rest[0])
    elif cmd == "invite":
        invite(rest)
    elif cmd == "people":
        people()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
