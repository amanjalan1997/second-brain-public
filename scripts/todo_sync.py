"""Save a day's to-do list to the web app without ever undoing Aman's work, and copy his app changes back (D-037).

  python3 scripts/todo_sync.py merge lists/todo/<date>.md [--refresh <id>] [--dry]
      Add the file's tasks to the web app. Only adds: a task whose fingerprint (`key`) is already on that day,
      or was deleted in the last 14 days, is skipped. Ticks, edits, deletes and tasks Aman added stay as they are.
      Also saves the day's schedule, emails and "hidden by your rules" list. --refresh tags the new tasks with
      the refresh's id (the app marks them New and can undo them). Prints a JSON summary.
  python3 scripts/todo_sync.py export <date>
      Rewrite the task sections of lists/todo/<date>.md from the web app: edited wording, ticks, tasks added in
      the app, deleted tasks left out. Everything else in the file (schedule, emails, notes) is kept.
  python3 scripts/todo_sync.py list <date> [--all]
      Print the day's tasks (open and done; --all adds deleted ones) so Claude can check what's already there.
  python3 scripts/todo_sync.py carry <date>
      Print the day's unfinished, not deleted tasks as to-do lines with a carried tag (for /today step A6).
  python3 scripts/todo_sync.py set <id> field=value [...]     quick change from chat: done=true, deleted=true deleteReason=none
  python3 scripts/todo_sync.py add <date> <net|clubs|personal> "<text>"
  python3 scripts/todo_sync.py edit <id> [--text "<new wording>"] [--section <key>]   records the original, like the app
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import webdb  # noqa: E402
from todo_to_app import SECTIONS, parse, task_key  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SEC_TITLE = {v: k for k, v in SECTIONS.items()}
DELETED_LOOKBACK_DAYS = 14


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def keys_of(t):
    """A task counts as 'already there' under its own key and under the key of its original wording."""
    ks = {t.get("key") or task_key(t.get("text", "")), task_key(t.get("text", ""))}
    if t.get("originalText"):
        ks.add(task_key(t["originalText"]))
    return ks


def recent_deleted():
    cutoff = datetime.now(timezone.utc) - timedelta(days=DELETED_LOOKBACK_DAYS)
    out = []
    for t in webdb.get("tasks", ["deleted=true"]):
        try:
            when = datetime.fromisoformat((t.get("deletedAt") or "").replace("Z", "+00:00"))
        except ValueError:
            when = cutoff
        if when >= cutoff:
            out.append(t)
    return out


def merge(md_path, refresh_id=None, dry=False):
    day, tasks = parse(md_path)
    date = day["date"]
    existing = webdb.get("tasks", [f"day={date}"])
    deleted = recent_deleted()
    on_day, gone = set(), set()
    for t in existing:
        (gone if t.get("deleted") else on_day).update(keys_of(t))
    for t in deleted:
        gone.update(keys_of(t))
    next_order = {}
    for t in existing:
        next_order[t.get("section")] = max(next_order.get(t.get("section"), 0), t.get("order") or 0)
    added, skipped_on_day, skipped_deleted, writes = [], 0, 0, []
    stamp = now_iso()
    for t in tasks:
        t.pop("id")
        if t["key"] in on_day:
            skipped_on_day += 1
            continue
        if t["key"] in gone:
            skipped_deleted += 1
            continue
        on_day.add(t["key"])
        if existing:  # adding to a day that's already in the app: append after what's there
            next_order[t["section"]] = next_order.get(t["section"], 0) + 1
            t["order"] = next_order[t["section"]]
        t["addedAt"] = stamp
        if refresh_id:
            t["refreshId"] = refresh_id
        tid = f"{date}-{t['key']}"
        writes.append({"op": "set", "collection": "tasks", "doc_id": tid, "data": t})
        added.append(t["text"])
    old_day = (webdb.get("days", [f"date={date}"]) or [{}])[0]
    day_doc = {**{k: v for k, v in old_day.items() if k != "id"}, **day, "updatedAt": stamp}
    writes.append({"op": "set", "collection": "days", "doc_id": date, "data": day_doc})
    if not dry:
        webdb.push(writes)
    return {"date": date, "added": len(added), "already_on_list": skipped_on_day, "skipped_deleted": skipped_deleted,
            "hidden_by_rules": len(day.get("hidden", [])), "emails": len(day.get("emails", [])),
            "new_tasks": added, "dry_run": dry}


def source_tag(src):
    kind, label = (src or {}).get("kind", ""), (src or {}).get("label", "")
    if kind == "cal":
        return f"📅 {label}"
    if kind == "email":
        return f"✉️ {label or 'email'}"
    if kind == "note":
        return f"📝 {label}"
    if kind == "carried":
        return f"↩️ carried {label}".rstrip()
    if kind == "network":
        return f"👥 network {label}".rstrip()
    if kind == "call":
        return "📞 " + re.sub(r"^Call · ", "", label)
    if kind == "news":
        return f"📰 news {label}".rstrip()
    if kind == "added":
        return "➕ added"
    return label


def task_line(t):
    tag = source_tag(t.get("source"))
    text = ("? " if t.get("unsure") else "") + t.get("text", "")
    return f"- [{'x' if t.get('done') else ' '}] {text}" + (f" · `{tag}`" if tag else "")


def live_tasks(date):
    ts = [t for t in webdb.get("tasks", [f"day={date}"]) if not t.get("deleted")]
    return sorted(ts, key=lambda t: (t.get("order") or 0, t.get("addedAt") or ""))


def export(date):
    path = REPO / "lists/todo" / f"{date}.md"
    if not path.exists():
        sys.exit(f"No file {path}")
    tasks = live_tasks(date)
    lines = path.read_text(encoding="utf-8").splitlines()
    out, skip = [], False
    for line in lines:
        if line.startswith("## "):
            skip = False
            key = SECTIONS.get(line[3:].strip())
            if key:
                mine = [task_line(t) for t in tasks if t.get("section") == key]
                out += [line, "", *(mine or ["- Nothing today"]), ""]
                skip = True
                continue
        if not skip:
            out.append(line)
    n_emails = len(parse(path)[0]["emails"])
    for i, line in enumerate(out):
        m = re.match(r"\*(\d+) tasks · (\d+) emails(.*)\*$", line)
        if m:
            out[i] = f"*{len(tasks)} tasks · {n_emails} emails{m.group(3)}*"
            break
    path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    return {"date": date, "tasks": len(tasks), "done": sum(1 for t in tasks if t.get("done"))}


def get_task(tid):
    rows = webdb.call("GET", f"/rest/v1/docs?select=id,data&collection=eq.tasks&id=eq.{webdb.q(tid)}")
    if not rows:
        sys.exit(f"No task {tid}")
    return rows[0]["data"]


def put_task(tid, data):
    webdb.push([{"op": "set", "collection": "tasks", "doc_id": tid, "data": data}])


def set_fields(tid, pairs):
    t = get_task(tid)
    for pair in pairs:
        k, _, v = pair.partition("=")
        try:
            t[k] = json.loads(v)
        except json.JSONDecodeError:
            t[k] = v
    if t.get("done") and not t.get("doneAt"):
        t["doneAt"] = now_iso()
    if t.get("deleted") and not t.get("deletedAt"):
        t["deletedAt"] = now_iso()
    put_task(tid, t)
    return t


def edit(tid, text=None, section=None):
    t = get_task(tid)
    text, section = text or t["text"], section or t["section"]
    stamp = now_iso()
    t.setdefault("originalText", t["text"])
    t.setdefault("originalSection", t["section"])
    t["edits"] = (t.get("edits") or []) + [{"at": stamp, "from": t["text"], "to": text, "fromSection": t["section"], "toSection": section}]
    t.update(text=text, section=section, editedAt=stamp)
    put_task(tid, t)
    return t


def add(date, section, text):
    if section not in SEC_TITLE:
        sys.exit("Section must be net, clubs or personal.")
    ts = webdb.get("tasks", [f"day={date}"])
    key = task_key(text)
    order = max([t.get("order") or 0 for t in ts if t.get("section") == section] + [0]) + 1
    t = {"day": date, "section": section, "text": text, "source": {"kind": "added", "label": ""}, "done": False,
         "order": order, "unsure": False, "key": key, "addedAt": now_iso()}
    put_task(f"{date}-{key}", t)
    return f"{date}-{key}"


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "merge":
        rid = rest[rest.index("--refresh") + 1] if "--refresh" in rest else None
        print(json.dumps(merge(rest[0], rid, "--dry" in rest), ensure_ascii=False, indent=1))
    elif cmd == "export":
        print(json.dumps(export(rest[0])))
    elif cmd == "list":
        ts = webdb.get("tasks", [f"day={rest[0]}"])
        if "--all" not in rest:
            ts = [t for t in ts if not t.get("deleted")]
        keep = ("id", "section", "text", "originalText", "done", "deleted", "deleteReason", "source", "key")
        print(json.dumps([{k: t[k] for k in keep if k in t} for t in ts], ensure_ascii=False, indent=1))
    elif cmd == "carry":
        for t in live_tasks(rest[0]):
            if t.get("done"):
                continue
            src = t.get("source") or {}
            since = re.sub(r"^since ", "", src.get("label", "")) if src.get("kind") == "carried" else rest[0]
            print(f"{SEC_TITLE.get(t.get('section'), '?')}\t{task_line({**t, 'done': False, 'source': {'kind': 'carried', 'label': 'since ' + since}})}")
    elif cmd == "set":
        t = set_fields(rest[0], rest[1:])
        print(f"Saved: {t['text']}")
    elif cmd == "add":
        print(add(rest[0], rest[1], rest[2]))
    elif cmd == "edit":
        opt = lambda f: rest[rest.index(f) + 1] if f in rest else None  # noqa: E731
        t = edit(rest[0], opt("--text"), opt("--section"))
        print(f"Saved: {t['text']} ({t['section']})")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
