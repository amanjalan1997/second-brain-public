"""The Mac side of the app's Refresh button (D-037). A launch agent runs `check` every minute.

  python3 scripts/refresh_helper.py check
      Look once for work: a refresh Aman asked for in the app (meta/refresh status "requested") → run the
      /refresh skill with Claude in the background; suggestions he accepted → run /refresh in apply mode.
      Does nothing (and uses no Claude) when there's nothing to do. Each check first runs `canvas.py tick`
      (Canvas token renewal and the hourly sync, no Claude; log ~/.second-brain/logs/canvas.log).
      Also answers **Brief me** taps in the Meetings tab (briefs with requestState "asked", D-054): runs the brief
      skill, section B, with Outlook allowed for that run (tapping Brief me is the ask, PRD decision A6).
  python3 scripts/refresh_helper.py show                      print meta/refresh
  python3 scripts/refresh_helper.py status "<step>"           show a step in the app ("reading email")
  python3 scripts/refresh_helper.py done '<summary json>'     finish: {"tasks", "emails", "suggestions", "hidden"}
  python3 scripts/refresh_helper.py fail "<plain reason>"     finish with an error (nothing was changed)
  python3 scripts/refresh_helper.py morning                   /today saved the morning list ("last refreshed")
  python3 scripts/refresh_helper.py suggest <file.json | ->   add suggestions for the app's Suggestions card
  python3 scripts/refresh_helper.py suggestions [status]      list suggestions (default: all, newest first)
  python3 scripts/refresh_helper.py applied <id> [<id> ...]   mark accepted suggestions as saved
  python3 scripts/refresh_helper.py test [--outlook]          ask for a test run (checks access, changes nothing)
  python3 scripts/refresh_helper.py install | uninstall       set up / remove the launch agent

The launch agent runs from its own copy of the repo (~/.second-brain/repo), so a refresh never trips over
work in progress in a Conductor workspace. Background runs only read Outlook, Granola and Apple Notes and write
Aman's own lists: no emails, drafts or calendar changes (CLAUDE.md rule 4). Logs: ~/.second-brain/logs/.
"""
import fcntl
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import webdb  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home() / ".second-brain"
LOGS = HOME / "logs"
LABEL = "com.secondbrain.refresh"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
EXPIRE_HOURS = 3
RUN_TIMEOUT_MIN = 25
MAX_APPLY_TRIES = 2
BRIEF_EXPIRE_HOURS = 6

# Background Claude may read sources and write Aman's lists, nothing else.
ALLOWED = [
    "Read", "Write", "Edit", "Glob", "Grep", "Skill", "TodoWrite", "WebSearch", "WebFetch", "Agent",
    "Bash(python3 scripts/*)", "Bash(git *)", "Bash(date*)", "Bash(ls *)", "Bash(cat *)", "Bash(mkdir *)",
    "mcp__claude_ai_Microsoft_365__outlook_email_search", "mcp__claude_ai_Microsoft_365__outlook_calendar_search",
    "mcp__claude_ai_Microsoft_365__read_resource", "mcp__claude_ai_Microsoft_365__search_people",
    "mcp__claude_ai_Granola__list_meetings", "mcp__claude_ai_Granola__get_meetings", "mcp__claude_ai_Granola__search_meetings",
    "mcp__claude_ai_Granola__query_granola_meetings", "mcp__claude_ai_Granola__get_meeting_transcript",
]
BLOCKED = [f"mcp__claude_ai_Microsoft_365__{t}" for t in (
    "outlook_send_mail", "outlook_send_draft", "outlook_create_draft", "outlook_create_reply_draft",
    "outlook_create_reply_all_draft", "outlook_update_draft", "outlook_forward_mail", "outlook_create_event",
    "outlook_update_event", "outlook_delete_event", "outlook_respond_to_event", "outlook_trash_thread",
    "outlook_batch_delete_messages", "teams_send_chat_message", "teams_send_channel_message")]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_doc(coll, did):
    rows = webdb.call("GET", f"/rest/v1/docs?select=data&collection=eq.{webdb.q(coll)}&id=eq.{webdb.q(did)}")
    return rows[0]["data"] if rows else None


def put_doc(coll, did, data):
    webdb.push([{"op": "set", "collection": coll, "doc_id": did, "data": data}])


def update_refresh(**fields):
    r = get_doc("meta", "refresh") or {}
    r.update(fields)
    put_doc("meta", "refresh", r)
    return r


def claude_bin():
    for p in (os.environ.get("CLAUDE_BIN"), shutil.which("claude"),
              str(Path.home() / "Library/Application Support/com.conductor.app/bin/claude"),
              str(Path.home() / ".local/bin/claude"), "/usr/local/bin/claude", "/opt/homebrew/bin/claude"):
        if p and Path(p).exists():
            return p
    sys.exit("Can't find the claude command.")


def run_claude(prompt, tag, outlook="skipped"):
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"{datetime.now().strftime('%Y-%m-%d-%H%M')}-{tag}.log"
    subprocess.run(["git", "pull", "--rebase", "--autostash", "-q"], cwd=REPO, capture_output=True)
    # Outlook asks for approval on every call; scripts/refresh_permission.sh answers with Aman's choice from the app (D-039)
    env = {**os.environ, "SECOND_BRAIN_HEADLESS": "1", "SECOND_BRAIN_OUTLOOK": outlook}
    cmd = [claude_bin(), "-p", prompt, "--settings", str(REPO / ".claude/refresh-settings.json"),
           "--allowedTools", *ALLOWED, "--disallowedTools", *BLOCKED]
    with open(log, "w") as f:
        try:
            res = subprocess.run(cmd, cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, timeout=RUN_TIMEOUT_MIN * 60)
            code = res.returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    return code, log


def canvas_tick():
    """Canvas (D-042): renew the token when it's due, sync hourly or right after a Refresh tap. Never stops a refresh."""
    if not (REPO / "scripts/canvas.py").exists():
        return
    LOGS.mkdir(parents=True, exist_ok=True)
    try:
        res = subprocess.run([sys.executable, str(REPO / "scripts/canvas.py"), "tick"], cwd=REPO, capture_output=True, text=True, timeout=180)
        out = (res.stdout + res.stderr).strip()
    except subprocess.TimeoutExpired:
        res, out = None, "timed out"
    if out or (res and res.returncode):
        with open(LOGS / "canvas.log", "a") as f:
            f.write(f"{now()} {out[-500:]}\n")


def scout_tick():
    """GitHub Scout (D-051): its own process with its own lock, so a GitHub scan never holds up a refresh."""
    if not (REPO / "scripts/github_scout.py").exists():
        return
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "scout.log", "a") as f:
        subprocess.Popen([sys.executable, str(REPO / "scripts/github_scout.py"), "tick"], cwd=REPO, stdin=subprocess.DEVNULL,
                         stdout=f, stderr=subprocess.STDOUT, start_new_session=True)


def check():
    HOME.mkdir(parents=True, exist_ok=True)
    scout_tick()
    lock = open(HOME / "refresh.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # a run is still going
    canvas_tick()
    r = get_doc("meta", "refresh") or {}
    asked = webdb.get("briefs", ["requestState=asked"])
    busy = r.get("status") == "requested" or webdb.get("suggestions", ["status=accepted"]) or asked
    if busy and os.environ.get("SECOND_BRAIN_UPDATED") != "1":
        # get the latest code first, then restart so this run uses it (not the copy already loaded)
        head = lambda: subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout  # noqa: E731
        before = head()
        subprocess.run(["git", "pull", "--rebase", "--autostash", "-q"], cwd=REPO, capture_output=True)
        if head() != before:
            lock.close()
            os.environ["SECOND_BRAIN_UPDATED"] = "1"
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), "check"])
    if r.get("status") == "requested":
        asked = datetime.fromisoformat(r["requestedAt"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - asked > timedelta(hours=EXPIRE_HOURS):
            update_refresh(status="expired")
            return
        update_refresh(status="running", startedAt=now(), step="starting")
        section = "C (test run)" if str(r.get("id", "")).startswith("test") else "A"
        outlook = "allowed" if r.get("outlook") == "allowed" else "skipped"
        say = "Aman allowed Outlook for this refresh" if outlook == "allowed" else "Aman chose to refresh without Outlook this time: skip Outlook"
        code, log = run_claude(f"Use the refresh skill (.claude/skills/refresh/SKILL.md), section {section}: refresh request {r['id']}. {say}.", "refresh", outlook)
        after = get_doc("meta", "refresh") or {}
        if after.get("status") == "running":
            reason = "it took too long" if code == "timeout" else "Claude stopped before finishing"
            update_refresh(status="error", message=reason, finishedAt=now())
        print(f"refresh {r['id']}: exit {code}, log {log}")
        return
    if r.get("status") == "running":
        started = datetime.fromisoformat((r.get("startedAt") or now()).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - started > timedelta(minutes=RUN_TIMEOUT_MIN + 5):
            update_refresh(status="error", message="the Mac stopped partway (asleep?)", finishedAt=now())
        return
    accepted = [s for s in webdb.get("suggestions", ["status=accepted"]) if (s.get("tries") or 0) < MAX_APPLY_TRIES]
    if accepted:
        for s in accepted:
            put_doc("suggestions", s["id"], {**{k: v for k, v in s.items() if k != "id"}, "tries": (s.get("tries") or 0) + 1})
        code, log = run_claude("Use the refresh skill (.claude/skills/refresh/SKILL.md), section B: apply the suggestions Aman accepted in the app.", "apply")
        print(f"apply {len(accepted)}: exit {code}, log {log}")
        return
    if asked:
        briefs(asked)


def briefs(asked):
    """Brief me taps (D-054): one background run for every waiting request. Old taps expire with a plain reason."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=BRIEF_EXPIRE_HOURS)
    fresh = []
    for b in asked:
        when = datetime.fromisoformat((b.get("requestedAt") or now()).replace("Z", "+00:00"))
        if when < cutoff:
            put_doc("briefs", b["id"], {**{k: v for k, v in b.items() if k != "id"}, "requestState": "failed",
                                         "requestNote": "Your Mac was asleep for too long. Tap Brief me again."})
        else:
            fresh.append(b["id"])
    if not fresh:
        return
    for i in fresh:
        b = next(x for x in asked if x["id"] == i)
        put_doc("briefs", i, {**{k: v for k, v in b.items() if k != "id"}, "requestState": "working"})
    code, log = run_claude(f"Use the brief skill (.claude/skills/brief/SKILL.md), section B: Brief me requests {' '.join(fresh)}. "
                           "Aman tapped Brief me, so Outlook (read only) is allowed for this run.", "brief", "allowed")
    for i in fresh:
        b = get_doc("briefs", i) or {}
        if b.get("requestState") == "working":
            put_doc("briefs", i, {**b, "requestState": "failed",
                                  "requestNote": "It took too long. Tap Brief me again." if code == "timeout" else "Claude stopped before finishing. Tap Brief me again."})
    print(f"briefs {len(fresh)}: exit {code}, log {log}")


def suggest(items):
    existing = webdb.get("suggestions", [])
    known = {(s.get("kind"), (s.get("title") or "").strip().lower()) for s in existing}
    stamp, writes = now(), []
    rid = (get_doc("meta", "refresh") or {}).get("id")
    for i, s in enumerate(items):
        k = (s.get("kind"), (s.get("title") or "").strip().lower())
        if not s.get("title") or k in known:
            continue
        known.add(k)
        writes.append({"op": "set", "collection": "suggestions", "doc_id": "s-" + uuid.uuid4().hex[:10],
                       "data": {**s, "status": "pending", "createdAt": stamp, "order": i, "refreshId": rid}})
    if writes:
        webdb.push(writes)
    return len(writes)


def install():
    home_repo = HOME / "repo"
    if not (home_repo / ".git").exists():
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=REPO, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "clone", "-q", url, str(home_repo)], check=True)
    shutil.copy(REPO / ".env", home_repo / ".env")
    LOGS.mkdir(parents=True, exist_ok=True)
    py = shutil.which("python3") or "/usr/bin/python3"
    path = ":".join([str(Path(claude_bin()).parent), str(Path.home() / ".local/node/bin"), "/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
    PLIST.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key><array><string>{py}</string><string>{home_repo}/scripts/refresh_helper.py</string><string>check</string></array>
  <key>WorkingDirectory</key><string>{home_repo}</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>{path}</string><key>CLAUDE_BIN</key><string>{claude_bin()}</string></dict>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{LOGS}/helper.log</string>
  <key>StandardErrorPath</key><string>{LOGS}/helper.log</string>
</dict></plist>
""")
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], check=True)
    if not get_doc("meta", "refresh"):
        put_doc("meta", "refresh", {"status": "idle"})
    print(f"Installed: {PLIST} (checks every minute, repo copy {home_repo}, logs {LOGS}).")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "check":
        check()
    elif cmd == "show":
        print(json.dumps(get_doc("meta", "refresh"), indent=1))
    elif cmd == "status":
        update_refresh(step=rest[0])
    elif cmd == "done":
        t = now()
        update_refresh(status="done", kind="refresh", finishedAt=t, lastDoneAt=t, lastKind="refresh", step="", message="",
                       summary=json.loads(rest[0]) if rest else {})
    elif cmd == "fail":
        update_refresh(status="error", message=rest[0] if rest else "", finishedAt=now())
    elif cmd == "morning":
        t = now()
        r = get_doc("meta", "refresh") or {}
        if r.get("status") in ("requested", "running"):
            update_refresh(lastDoneAt=t, lastKind="morning")
        else:
            update_refresh(status="done", kind="morning", lastDoneAt=t, lastKind="morning")
    elif cmd == "suggest":
        items = json.load(sys.stdin if not rest or rest[0] == "-" else open(rest[0]))
        print(f"Added {suggest(items)} suggestions.")
    elif cmd == "suggestions":
        rows = webdb.get("suggestions", [f"status={rest[0]}"] if rest else [])
        print(json.dumps(sorted(rows, key=lambda s: s.get("createdAt") or "", reverse=True), ensure_ascii=False, indent=1))
    elif cmd == "applied":
        for sid in rest:
            s = get_doc("suggestions", sid)
            if s:
                put_doc("suggestions", sid, {**s, "status": "applied", "appliedAt": now()})
        print(f"Marked {len(rest)} applied.")
    elif cmd == "test":
        update_refresh(status="requested", kind="refresh", id="test-" + uuid.uuid4().hex[:6], requestedAt=now(), step="", message="", summary=None,
                       outlook="allowed" if "--outlook" in rest else "skipped")
        print("Test run requested; the launch agent picks it up within a minute.")
    elif cmd == "install":
        install()
    elif cmd == "uninstall":
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
        PLIST.unlink(missing_ok=True)
        print("Removed the launch agent.")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
