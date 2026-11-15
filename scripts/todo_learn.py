"""Learn what matters to Aman from what he does with his to-do list in the app (D-037).

  python3 scripts/todo_learn.py sync
      Pull new signals from the web app into lists/todo-learning.json: deletes (with his reason and the
      "don't suggest" tick), rewordings, section moves, ticks (hours to tick), tasks he brought back or added
      himself. Also moves tasks he deleted as "Not now" to lists/parked.md. Prints what's new.
  python3 scripts/todo_learn.py nomore
      "Don't suggest things like this" deletes that haven't become a rule suggestion yet (then marks them seen).
  python3 scripts/todo_learn.py report [--days 7]
      Numbers for the weekly review: suggested, done, edited, moved, deleted by reason, hidden by rules,
      brought back, added by him; by source; the deletes and edits themselves.
  python3 scripts/todo_learn.py log-review '<json>'
      Record a finished weekly review ({"accepted": [...], "rejected": [...]}).

The log holds only short task lines (already in lists/todo/), never email or note text (CLAUDE.md rule 5).
"""
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import webdb  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "lists/todo-learning.json"
PARKED = REPO / "lists/parked.md"
REASONS = {"not-for-me": "Not for me", "done": "Already done", "later": "Not now", "duplicate": "Duplicate",
           "none": "Just delete", "undo-refresh": "Undid a refresh"}


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
    return {"events": [], "rules_seen": [], "reviews": [], "last_sync": None}


def save(log):
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n")


def src_kind(t):
    return (t.get("source") or {}).get("kind", "")


def events_for(t):
    tid, day, text, kind = t["id"], t.get("day"), t.get("originalText") or t.get("text", ""), src_kind(t)
    label = (t.get("source") or {}).get("label", "")
    base = {"day": day, "text": text, "source": kind, "label": label}
    out = []
    if t.get("deleted"):
        out.append({**base, "id": f"{tid}:deleted", "type": "deleted", "at": t.get("deletedAt"),
                    "reason": t.get("deleteReason") or "none", "noMore": bool(t.get("noMore"))})
    for e in t.get("edits") or []:
        if e.get("from") != e.get("to"):
            out.append({**base, "id": f"{tid}:edit:{e.get('at')}", "type": "edited", "at": e.get("at"), "from": e.get("from"), "to": e.get("to")})
        if e.get("fromSection") != e.get("toSection"):
            out.append({**base, "id": f"{tid}:move:{e.get('at')}", "type": "moved", "at": e.get("at"),
                        "fromSection": e.get("fromSection"), "toSection": e.get("toSection")})
    if t.get("done") and t.get("doneAt") and kind != "added":
        start = parse_iso(t.get("addedAt")) or parse_iso(f"{day}T11:00:00+00:00")  # list day ≈ 7 AM Boston
        end = parse_iso(t["doneAt"])
        hours = round((end - start).total_seconds() / 3600, 1) if start and end else None
        out.append({**base, "id": f"{tid}:ticked", "type": "ticked", "at": t["doneAt"], "hours": hours})
    if t.get("restoredAt"):
        out.append({**base, "id": f"{tid}:restored", "type": "restored", "at": t["restoredAt"]})
    if t.get("broughtBack"):
        out.append({**base, "id": f"{tid}:brought_back", "type": "brought_back", "at": t.get("addedAt"), "rule": t.get("rule", "")})
    elif kind == "added" and label == "in app":
        out.append({**base, "id": f"{tid}:added", "type": "added", "at": t.get("addedAt")})
    return out


def park(tasks):
    """Tasks deleted as "Not now" go to lists/parked.md once, then get parked=true in the app."""
    todo = [t for t in tasks if t.get("deleted") and t.get("deleteReason") == "later" and not t.get("parked")]
    if not todo:
        return []
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%a, %b %-d")
    block = f"\n## Parked {today} (from the app, \"Not now\")\n\n" + "".join(f"- {t['text']}\n" for t in todo)
    PARKED.write_text(PARKED.read_text().rstrip("\n") + "\n" + block)
    writes = []
    for t in todo:
        data = {k: v for k, v in t.items() if k != "id"}
        writes.append({"op": "set", "collection": "tasks", "doc_id": t["id"], "data": {**data, "parked": True}})
    webdb.push(writes)
    return [t["text"] for t in todo]


def sync():
    log = load()
    seen = {e["id"] for e in log["events"]}
    tasks = webdb.get("tasks", [])
    new = [e for t in tasks for e in events_for(t) if e["id"] not in seen]
    log["events"] += new
    log["last_sync"] = now()
    parked = park(tasks)
    save(log)
    c = Counter(e["type"] for e in new)
    print(json.dumps({"new_signals": dict(c), "parked": parked}, ensure_ascii=False))


def nomore():
    log = load()
    done = set(log.get("rules_seen", []))
    hits = [e for e in log["events"] if e["type"] == "deleted" and e.get("noMore") and e["id"] not in done]
    log["rules_seen"] = sorted(done | {e["id"] for e in hits})
    save(log)
    print(json.dumps([{k: e.get(k) for k in ("day", "text", "source", "label", "reason")} for e in hits], ensure_ascii=False, indent=1))


def report(days):
    log = load()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    tasks = [t for t in webdb.get("tasks", []) if (t.get("day") or "") >= since]
    claude = [t for t in tasks if src_kind(t) != "added"]
    keys = {t.get("key") or t.get("text") for t in claude}
    ev = [e for e in log["events"] if (e.get("day") or "") >= since]
    by = lambda typ: [e for e in ev if e["type"] == typ]  # noqa: E731
    hidden = sum(len(d.get("hidden") or []) for d in webdb.get("days", []) if (d.get("date") or "") >= since)
    ticked = [e["hours"] for e in by("ticked") if e.get("hours") is not None]
    per_source = {}
    for t in claude:
        s = per_source.setdefault(src_kind(t) or "other", {"suggested": 0, "done": 0, "deleted": 0, "edited": 0})
        s["suggested"] += 1
        s["done"] += bool(t.get("done"))
        s["deleted"] += bool(t.get("deleted")) and t.get("deleteReason") != "undo-refresh"
        s["edited"] += bool(t.get("edits"))
    out = {
        "days": days, "since": since,
        "tasks_suggested_unique": len(keys), "task_rows": len(claude),
        "done": sum(bool(t.get("done")) for t in claude),
        "deleted_by_reason": dict(Counter(REASONS.get(e["reason"], e["reason"]) for e in by("deleted"))),
        "dont_suggest": len([e for e in by("deleted") if e.get("noMore")]),
        "edited": len(by("edited")), "moved": len(by("moved")),
        "added_by_aman": len(by("added")), "brought_back": len(by("brought_back")), "restored": len(by("restored")),
        "hidden_by_rules": hidden,
        "median_hours_to_tick": sorted(ticked)[len(ticked) // 2] if ticked else None,
        "by_source": per_source,
        "deletes": [{k: e.get(k) for k in ("day", "text", "source", "label", "reason", "noMore")} for e in by("deleted")],
        "edits": [{k: e.get(k) for k in ("day", "from", "to")} for e in by("edited")],
        "moves": [{k: e.get(k) for k in ("day", "text", "fromSection", "toSection")} for e in by("moved")],
        "added": [e["text"] for e in by("added")],
        "brought_back_items": [{k: e.get(k) for k in ("text", "rule")} for e in by("brought_back")],
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == "sync":
        sync()
    elif cmd == "nomore":
        nomore()
    elif cmd == "report":
        report(int(argv[argv.index("--days") + 1]) if "--days" in argv else 7)
    elif cmd == "log-review":
        log = load()
        log["reviews"].append({"at": now(), **json.loads(argv[1])})
        save(log)
        print("Logged.")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
