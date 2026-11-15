"""Aman's comments on items in the app, and Claude's replies (docs/PRD-comments.md).

  python3 scripts/comments.py list [new|all] [--days N]
      Comments as JSON, oldest first, each with `thread` (the other comments on the same item). Default: new
      (not yet answered). `all` covers the last N days (default 30). Deleted comments are left out.
  python3 scripts/comments.py answer <file.json | ->
      Save Claude's answers in one go (the refresh and /today save steps). A list of
        {"id": "<comment id>", "reply": "<one or two lines>", "outcome": "rule|fix|answer|noted",
         "suggestions": [<suggestion objects, as for refresh_helper.py suggest>]}
      Suggestions are added to the app's Suggestions card (stamped with the comment id), the reply shows under
      the comment, the comment is marked read and logged in lists/comments-log.json. Prints what it did.
  python3 scripts/comments.py report [--days 7]
      Numbers for the weekly review: comments by kind and outcome, what their suggestions became (accepted,
      skipped, waiting), and the "noted" ones (look for comments that point the same way).
  python3 scripts/comments.py log-review '<json>'
      Record a finished weekly review ({"accepted": [...], "rejected": [...]}).

The log keeps Aman's comment, the item's short title and the outcome; never email or note text (CLAUDE.md rule 5).
"""
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import refresh_helper  # noqa: E402
import webdb  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "lists/comments-log.json"
OUTCOMES = ("rule", "fix", "answer", "noted")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(s):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def load():
    if LOG.exists():
        return json.loads(LOG.read_text())
    return {"comments": [], "reviews": []}


def save(log):
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n")


def target_key(c):
    t = c.get("target") or {}
    return f"{t.get('kind')}|{t.get('id')}"


def all_comments():
    return [c for c in webdb.get("comments", []) if not c.get("deleted")]


def short(c):
    """What Claude needs to read one comment (and what goes in a thread)."""
    out = {k: c.get(k) for k in ("id", "createdAt", "chips", "text", "status") if c.get(k) not in (None, "", [])}
    if c.get("reply"):
        out["reply"] = c["reply"].get("text")
    return out


def list_comments(which, days):
    rows = sorted(all_comments(), key=lambda c: c.get("createdAt") or "")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    by_target = {}
    for c in rows:
        by_target.setdefault(target_key(c), []).append(c)
    pick = [c for c in rows if c.get("status") != "read"] if which == "new" else [c for c in rows if (parse_iso(c.get("createdAt")) or since) >= since]
    return [{**short(c), "target": c.get("target"), "thread": [short(x) for x in by_target[target_key(c)] if x["id"] != c["id"]]} for c in pick]


def answer(items):
    by_id = {c["id"]: c for c in all_comments()}
    log, stamp, done, n_sugg = load(), now(), [], 0
    for a in items:
        c = by_id.get(a.get("id"))
        if not c:
            print(f"skipped {a.get('id')}: no such comment (deleted?)")
            continue
        outcome = a.get("outcome") if a.get("outcome") in OUTCOMES else "noted"
        suggs = [{**s, "comment": c["id"]} for s in a.get("suggestions") or []]
        if suggs:
            n_sugg += refresh_helper.suggest(suggs)
        reply = (a.get("reply") or "").strip()
        data = {k: v for k, v in c.items() if k != "id"}
        data.update({"status": "read", "readAt": stamp, "outcome": outcome})
        if reply:
            data["reply"] = {"text": reply, "at": stamp}
        if suggs:
            data["suggestionTitles"] = [s.get("title") for s in suggs]
        webdb.push([{"op": "set", "collection": "comments", "doc_id": c["id"], "data": data}])
        t = c.get("target") or {}
        log["comments"] = [x for x in log["comments"] if x.get("id") != c["id"]] + [{
            "id": c["id"], "at": c.get("createdAt"), "kind": t.get("kind"), "title": t.get("title"), "where": t.get("where"),
            "chips": c.get("chips") or [], "text": c.get("text") or "", "outcome": outcome, "reply": reply,
            "suggestions": [s.get("title") for s in suggs], "answeredAt": stamp}]
        done.append(c["id"])
    save(log)
    print(f"answered {len(done)} comment(s), {n_sugg} new suggestion(s)")


def report(days):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    log = load()
    recent = [x for x in log["comments"] if (parse_iso(x.get("answeredAt")) or since) >= since]
    status = {}
    for s in webdb.get("suggestions", []):
        if s.get("comment"):
            status[(s.get("title") or "").strip().lower()] = s.get("status")
    fate = Counter(status.get((t or "").strip().lower(), "unknown") for x in recent for t in x.get("suggestions") or [])
    waiting = [short(c) | {"target": c.get("target")} for c in all_comments() if c.get("status") != "read"]
    print(json.dumps({
        "days": days,
        "answered": len(recent),
        "by_kind": Counter(x.get("kind") for x in recent),
        "by_outcome": Counter(x.get("outcome") for x in recent),
        "suggestions": dict(fate),
        "noted": [{k: x.get(k) for k in ("at", "kind", "title", "chips", "text")} for x in log["comments"] if x.get("outcome") == "noted"],
        "rules": [{"comment": x.get("text") or ", ".join(x.get("chips") or []), "on": x.get("title"), "suggestions": x.get("suggestions")}
                  for x in recent if x.get("suggestions")],
        "waiting": waiting,
    }, ensure_ascii=False, indent=1))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "list"
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else None
    if cmd == "list":
        which = argv[2] if len(argv) > 2 and argv[2] in ("new", "all") else "new"
        print(json.dumps(list_comments(which, days or 30), ensure_ascii=False, indent=1))
    elif cmd == "answer":
        src = argv[2] if len(argv) > 2 else "-"
        answer(json.loads(sys.stdin.read() if src == "-" else Path(src).read_text()))
    elif cmd == "report":
        report(days or 7)
    elif cmd == "log-review":
        log = load()
        log["reviews"].append({"at": now(), **json.loads(argv[2])})
        save(log)
        print("review logged")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
