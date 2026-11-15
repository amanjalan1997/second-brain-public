#!/usr/bin/env python3
"""Get /today ready in one step (D-052): everything step A1 needs from this Mac, printed once.

  python3 scripts/today_prep.py

Runs and prints, in order: git pull, the Boston date and the Outlook time offset, the last list, what Aman did
in the app (todo_learn sync), the carried-over tasks (todo_sync carry), "don't suggest" deletes (todo_learn
nomore), the Apple Notes "To do" note and the notes changed since the last scan, new comments, the Canvas sync,
due email follow-ups, and the last-run times of news, network and the inbox check.

Saves nothing itself (todo_learn sync and canvas sync keep their own logs, as always). Output is capped so it
stays short: each run of /today used to spend about 10 separate steps on this.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
BOS, IST = ZoneInfo("America/New_York"), ZoneInfo("Asia/Kolkata")
NOTE_CAP, NOTES_TOTAL_CAP = 1500, 12000


def run(args, cap=4000):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout + (r.stderr if r.returncode else "")).strip()
    if len(out) > cap:
        out = out[:cap] + f"\n… (cut at {cap} characters)"
    return out or "(nothing)", r.returncode


def section(title, body):
    print(f"\n=== {title}\n{body}")


def state(name):
    p = ROOT / "lists" / name
    return json.loads(p.read_text()) if p.exists() else {}


def main():
    out, _ = run(["git", "pull", "--rebase", "--autostash", "-q"], 600)
    now = datetime.now(BOS)
    gap = (now.utcoffset() - now.astimezone(IST).utcoffset()).total_seconds() / 3600
    h, m = divmod(abs(gap) * 60, 60)
    print(f"Today: {now:%a, %b %-d %Y} · now {now:%-I:%M %p} Boston ({now.date().isoformat()})")
    print(f"Outlook (IST) → Boston: {'-' if gap < 0 else '+'}{int(h)}h{int(m):02d}")
    print(f"git pull: {out if out != '(nothing)' else 'up to date'}")

    days = sorted(p.stem for p in (ROOT / "lists/todo").glob("????-??-??.md") if p.stem < now.date().isoformat())
    last = days[-1] if days else None
    has_today = (ROOT / f"lists/todo/{now.date().isoformat()}.md").exists()
    section("Last list", f"{last or 'none'}" + ("   (today's list already exists: second run of the day)" if has_today else ""))

    section("What Aman did in the app (todo_learn sync)", run([sys.executable, "scripts/todo_learn.py", "sync"], 2500)[0])
    if last:
        section(f"Carry over from {last} (todo_sync carry)", run([sys.executable, "scripts/todo_sync.py", "carry", last], 6000)[0])
    section("'Don't suggest things like this' deletes (todo_learn nomore)", run([sys.executable, "scripts/todo_learn.py", "nomore"], 1500)[0])

    ns = state("notes-state.json")
    todo_out, code = run([sys.executable, "scripts/notes.py", "get", "To do"], 60000)
    try:
        got = json.loads(todo_out) if code == 0 else todo_out
        todo_text = (got[0] if got else {}).get("text", "(note not found)") if isinstance(got, list) else str(got)
    except ValueError:
        todo_text = todo_out
    section("Apple Notes: 'To do' note (top; only the newest dated section counts)", todo_text[:2500])
    section("Apple Notes: last 'To do' items already handled", json.dumps(ns.get("todo_note", {}).get("items", ns.get("todo_note")), ensure_ascii=False)[:1500])
    hours = 24
    if ns.get("last_scan"):
        hours = max(1, int((now - datetime.fromisoformat(ns["last_scan"])).total_seconds() // 3600) + 1)
    since_out, code = run([sys.executable, "scripts/notes.py", "since", str(hours)], 200000)
    lines, total = [], 0
    try:
        notes = json.loads(since_out) if code == 0 else []
    except ValueError:
        notes = []
    for n in notes:
        if n.get("title") == "To do":
            continue
        body = (n.get("text") or "")[:NOTE_CAP]
        if total + len(body) > NOTES_TOTAL_CAP:
            lines.append(f"… {len(notes) - len(lines)} more notes left out (cap); read them with notes.py get")
            break
        total += len(body)
        lines.append(f"## {n.get('title')} ({n.get('modified', '')})\n{body}")
    section(f"Apple Notes changed in the last {hours} h (since {ns.get('last_scan', '?')})",
            "\n\n".join(lines) if lines else (since_out[:500] if code else "(none)"))

    section("New comments in the app (comments.py list)", run([sys.executable, "scripts/comments.py", "list"], 4000)[0])
    out, _ = run([sys.executable, "scripts/canvas.py", "sync"], 100000)
    pend, _ = run([sys.executable, "scripts/canvas.py", "pending"], 200000)
    try:
        pcount = len(json.loads(pend))
    except ValueError:
        pcount = "?"
    section("Canvas", "\n".join(out.splitlines()[-4:]) + f"\nQuick review summaries missing: {pcount} (canvas.py pending)")
    section("Email follow-ups due (email_tracker.py due)", run([sys.executable, "scripts/email_tracker.py", "due"], 3000)[0])

    es, nw, nn = state("email-state.json"), state("network-state.json"), state("news-state.json")
    waiting = [t for t in es.get("threads", []) if t.get("status") == "waiting"]
    section("Last runs", "\n".join([
        f"news last_run: {nn.get('last_run')} ({len(nn.get('seen', []))} seen items; news agents read lists/news-state.json themselves)",
        f"network last_sync: {nw.get('last_sync')}",
        f"inbox last_check: {es.get('last_check')} · {len(waiting)} threads waiting on a reply",
        f"notes last_scan: {ns.get('last_scan')}",
    ]))


if __name__ == "__main__":
    main()
