"""Ghostwriter's "waiting on" tracker: who owes Aman a reply, and when to suggest a follow-up.

The master is lists/email-state.json; lists/waiting-on.md is rendered from it (don't edit the .md by hand).

  python3 scripts/email_tracker.py add <file.json>          add threads (JSON array, see below); skips known ones
  python3 scripts/email_tracker.py due [--today YYYY-MM-DD] threads needing Aman: replies in, nudges due
  python3 scripts/email_tracker.py nudged <id> [--date D]   a follow-up was sent: count it, set the next date
  python3 scripts/email_tracker.py replied <id> [--note T]  they replied (a draft answer is being prepared)
  python3 scripts/email_tracker.py waiting <id> [--date D] [--kind K]  Aman replied/asked again: wait for them
  python3 scripts/email_tracker.py close <id> [done|gone-quiet]
  python3 scripts/email_tracker.py untrack <id>             stop tracking and never suggest this thread again
  python3 scripts/email_tracker.py skip <conversationId>    Aman said no to tracking a thread: never suggest it again
  python3 scripts/email_tracker.py set <id> key=value ...   edit a field (e.g. draftId=..., note=...)
  python3 scripts/email_tracker.py log --to a@x,b@y --subject S [--conversation C] [--thread ID] [--kind K]
                                                           record an email Claude sent (after Aman's "send")
  python3 scripts/email_tracker.py nudge-date YYYY-MM-DD <kind> [<nudges already sent>]
  python3 scripts/email_tracker.py render                   rewrite lists/waiting-on.md

Thread fields: id, person, company, email, subject, ask (<=12 words), kind (scheduling|networking|favour|logistics),
sent (date of Aman's last email, Boston), conversationId, lastMessageId, status (waiting|replied|done|gone-quiet),
nudges, next_nudge, draftId, note, updated, asked_on (start of the current ask; used for reply-time stats).
Each reply or "gone quiet" also adds an anonymous row to "outcomes" (kind, dates, nudges) so
scripts/email_learn.py report can show how fast people reply and whether nudges work.
Dates are Boston dates. Timing rules: config/settings.yaml -> email_writer.follow_ups.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "lists/email-state.json"
OUT = ROOT / "lists/waiting-on.md"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
KINDS = ("scheduling", "networking", "favour", "logistics")


def cfg():
    return yaml.safe_load((ROOT / "config/settings.yaml").read_text())["email_writer"]["follow_ups"]


def today():
    return datetime.now(ZoneInfo("America/New_York")).date()


def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"last_check": None, "threads": [], "sent_log": [], "dont_track": []}


def save(st):
    STATE.write_text(json.dumps(st, indent=1, ensure_ascii=False) + "\n")
    render(st)


def nudge_date(sent, kind, nudges=0):
    """Working days after `sent` per the schedule, moved forward to an allowed nudge day."""
    c = cfg()
    sched = c[kind]
    n = sched[min(nudges, len(sched) - 1)]
    d = sent
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    while DAYS[d.weekday()] not in c["nudge_days"]:
        d += timedelta(days=1)
    return d


def working_days_between(a, b):
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        n += d.weekday() < 5
    return n


def outcome(st, t, replied_on=None):
    asked = date.fromisoformat(t.get("asked_on") or t["sent"])
    row = {"kind": t["kind"], "asked_on": asked.isoformat(), "nudges": t["nudges"]}
    if replied_on:
        row.update(replied_on=replied_on.isoformat(), working_days=working_days_between(asked, replied_on))
    else:
        row["gone_quiet"] = True
    st.setdefault("outcomes", []).append(row)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:24]


def find(st, tid):
    for t in st["threads"]:
        if t["id"] == tid:
            return t
    sys.exit(f"no thread with id {tid}")


def touch(t):
    t["updated"] = today().isoformat()


def add(st, path):
    known = {t.get("conversationId") for t in st["threads"]} | set(st["dont_track"])
    added = []
    for r in json.loads(Path(path).read_text()):
        if r.get("conversationId") in known:
            continue
        kind = r.get("kind", "networking")
        assert kind in KINDS, kind
        sent = date.fromisoformat(r["sent"])
        base = slug(f"{r['person'].split()[0]}-{r.get('company') or ''}") + sent.strftime("-%m%d")
        tid, i = base, 2
        while any(t["id"] == tid for t in st["threads"]):
            tid, i = f"{base}-{i}", i + 1
        t = {"id": tid, "person": r["person"], "company": r.get("company", ""), "email": r.get("email", ""),
             "subject": r.get("subject", ""), "ask": r.get("ask", ""), "kind": kind, "sent": sent.isoformat(),
             "conversationId": r.get("conversationId"), "lastMessageId": r.get("lastMessageId"),
             "status": r.get("status", "waiting"), "nudges": int(r.get("nudges", 0)),
             "next_nudge": None, "draftId": None, "note": r.get("note", ""), "asked_on": r.get("asked_on", sent.isoformat())}
        t["next_nudge"] = nudge_date(sent, kind, t["nudges"]).isoformat()
        touch(t)
        st["threads"].append(t)
        added.append(tid)
    print(json.dumps({"added": added}, indent=1))


def due(st, on):
    c = cfg()
    out = {"replies": [], "nudges": [], "let_go": []}
    for t in st["threads"]:
        if t["status"] == "replied":
            out["replies"].append(t)
        elif t["status"] == "waiting" and t["next_nudge"] and t["next_nudge"] <= on.isoformat():
            (out["let_go"] if t["nudges"] >= min(c["max_nudges"], len(c[t["kind"]])) else out["nudges"]).append(t)
    print(json.dumps({k: [{"id": t["id"], "person": t["person"], "company": t["company"], "subject": t["subject"],
                           "ask": t["ask"], "sent": t["sent"], "nudges": t["nudges"],
                           "conversationId": t["conversationId"], "lastMessageId": t["lastMessageId"]}
                          for t in v] for k, v in out.items()}, indent=1))


def render(st):
    c, on = cfg(), today()
    th = st["threads"]
    key = lambda t: t["sent"]
    replies = sorted([t for t in th if t["status"] == "replied"], key=key, reverse=True)
    waiting = [t for t in th if t["status"] == "waiting"]
    due_now = sorted([t for t in waiting if t["next_nudge"] and t["next_nudge"] <= on.isoformat()], key=key)
    later = sorted([t for t in waiting if t not in due_now], key=lambda t: t["next_nudge"] or "")
    quiet = sorted([t for t in th if t["status"] == "gone-quiet"], key=key, reverse=True)
    cutoff = (on - timedelta(days=c.get("done_shown_days", 14))).isoformat()
    done = sorted([t for t in th if t["status"] == "done" and t.get("updated", "") >= cutoff], key=key, reverse=True)

    def who(t):
        return f"{t['person']} ({t['company']})" if t["company"] else t["person"]

    def nice(d):
        d = date.fromisoformat(d)
        return f"{DAYS[d.weekday()]} {d.strftime('%b')} {d.day}"

    def table(rows, cols):
        if not rows:
            return "*Nothing here.*\n"
        head = "| " + " | ".join(h for h, _ in cols) + " |\n|" + "---|" * len(cols) + "\n"
        return head + "".join("| " + " | ".join(str(f(t)).replace("|", "/") for _, f in cols) + " |\n" for t in rows)

    base = [("Person", who), ("Subject", lambda t: t["subject"]), ("Asked", lambda t: t["ask"]),
            ("Last email", lambda t: nice(t["sent"]))]
    md = ["# Waiting on\n",
          "*People Aman is waiting to hear back from. Kept by Ghostwriter (`/email`, `/inbox`, `/today`); made from "
          "`lists/email-state.json` by `scripts/email_tracker.py render`, so don't edit this file by hand. "
          "Every reply or follow-up is only sent after Aman says \"send\".*\n",
          f"*Updated {nice(on.isoformat())}. Waiting on {len(waiting)}, follow-ups due {len(due_now)}, "
          f"replies in {len(replies)}.*\n",
          "## Replied: answer to draft\n", table(replies, base + [("Note", lambda t: t.get("note", ""))]),
          "## Follow-up due\n", table(due_now, base + [("Nudges sent", lambda t: t["nudges"])]),
          "## Waiting\n", table(later, base + [("Kind", lambda t: t["kind"]),
                                              ("Follow up on", lambda t: nice(t["next_nudge"]) if t["next_nudge"] else "")]),
          "## Gone quiet\n", table(quiet, base + [("Nudges sent", lambda t: t["nudges"])]),
          f"## Done (last {c.get('done_shown_days', 14)} days)\n", table(done, base)]
    OUT.write_text("\n".join(md))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("add").add_argument("file")
    sub.add_parser("due").add_argument("--today")
    for name in ("nudged", "waiting"):
        q = sub.add_parser(name)
        q.add_argument("id")
        q.add_argument("--date")
        if name == "waiting":
            q.add_argument("--kind", choices=KINDS)
    q = sub.add_parser("replied"); q.add_argument("id"); q.add_argument("--note", default="")
    q.add_argument("--date")
    q = sub.add_parser("close"); q.add_argument("id"); q.add_argument("how", nargs="?", default="done",
                                                                       choices=["done", "gone-quiet"])
    sub.add_parser("untrack").add_argument("id")
    sub.add_parser("skip").add_argument("conversation")
    q = sub.add_parser("set"); q.add_argument("id"); q.add_argument("pairs", nargs="+")
    q = sub.add_parser("log")
    for a in ("--to", "--subject", "--conversation", "--thread", "--kind"):
        q.add_argument(a, required=a in ("--to", "--subject"))
    q = sub.add_parser("nudge-date"); q.add_argument("sent"); q.add_argument("kind", choices=KINDS)
    q.add_argument("nudges", nargs="?", type=int, default=0)
    sub.add_parser("render")
    a = p.parse_args()

    if a.cmd == "nudge-date":
        print(nudge_date(date.fromisoformat(a.sent), a.kind, a.nudges).isoformat())
        return
    st = load()
    on = date.fromisoformat(a.today) if getattr(a, "today", None) else today()
    if a.cmd == "add":
        add(st, a.file)
    elif a.cmd == "due":
        due(st, on)
        return
    elif a.cmd == "render":
        pass
    elif a.cmd == "untrack":
        t = find(st, a.id)
        st["threads"].remove(t)
        if t.get("conversationId"):
            st["dont_track"].append(t["conversationId"])
    elif a.cmd == "skip":
        if a.conversation not in st["dont_track"]:
            st["dont_track"].append(a.conversation)
    elif a.cmd == "log":
        st["sent_log"].append({"date": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="minutes"),
                               "to": a.to.split(","), "subject": a.subject, "conversationId": a.conversation,
                               "thread": a.thread, "kind": a.kind})
    else:
        t = find(st, a.id)
        d = date.fromisoformat(a.date) if getattr(a, "date", None) else today()  # Boston date
        if a.cmd == "nudged":
            t["nudges"] += 1
            t["sent"], t["status"] = d.isoformat(), "waiting"
            t["next_nudge"] = nudge_date(d, t["kind"], t["nudges"]).isoformat()
        elif a.cmd == "waiting":
            t["kind"] = a.kind or t["kind"]
            t["sent"], t["status"], t["nudges"], t["asked_on"] = d.isoformat(), "waiting", 0, d.isoformat()
            t["next_nudge"], t["draftId"] = nudge_date(d, t["kind"]).isoformat(), None
        elif a.cmd == "replied":
            if t["status"] == "waiting":
                outcome(st, t, d)
            t["status"], t["note"] = "replied", a.note or t.get("note", "")
        elif a.cmd == "close":
            if a.how == "gone-quiet" and t["status"] == "waiting":
                outcome(st, t)
            t["status"], t["next_nudge"], t["draftId"] = a.how, None, None
        elif a.cmd == "set":
            for pair in a.pairs:
                k, v = pair.split("=", 1)
                t[k] = int(v) if k == "nudges" else (None if v in ("", "null") else v)
        touch(t)
    save(st)


if __name__ == "__main__":
    sys.exit(main())
