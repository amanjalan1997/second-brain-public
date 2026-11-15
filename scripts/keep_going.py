"""Keep Claude going after a usage limit: every conversation that stopped because of the limit is resumed
once the limit resets. Conversations Aman stopped himself are left alone.

  python3 scripts/keep_going.py install     set it up once: a background job checks every 10 minutes
  python3 scripts/keep_going.py status      what's stopped, when it resumes, what was resumed recently
  python3 scripts/keep_going.py check       one check now (what the background job runs)
  python3 scripts/keep_going.py check --dry-run   show what it would resume, start nothing
  python3 scripts/keep_going.py uninstall   turn the background job off

How it decides: Claude Code saves every conversation (Conductor chats included) under ~/.claude/projects.
A conversation counts as "stopped by the limit" when its last message is Claude's usage-limit error, which
records the exact reset time. If Aman stopped it ("interrupted by user") or wrote anything after the limit
message, the last message is something else, so it is skipped. Only limits hit in the last 24 hours count.
Runs in ~/.second-brain (the app's Refresh button, refresh_helper.py) are skipped too: that job has its own
retry and safety limits, so resuming them here would be double work.

When the reset time has passed (plus 2 minutes), it runs `claude --resume <id> -p "<carry on>"` in that
conversation's folder, in the background, one process per conversation. The resumed work is added to the
same conversation, so the Conductor chat has it in context next time Aman writes there (the chat window
may not show it until reopened). If the resumed run hits the limit again, the next check picks it up again.
Each limit message is retried at most 3 times. The Mac is kept from idle-sleeping while a reset is pending
and while resumed runs work (a closed lid still sleeps it; checks catch up when it wakes).

Permissions: each conversation resumes in the mode it was in (auto, bypassPermissions, ...); "default"
becomes "auto", since no one is there to click "allow". Skill rules still apply (e.g. no email without "send").
Files: the job runs a copy of this script in ~/.second-brain/keep-going/ (so it survives deleted Conductor
workspaces; run install again after changing it); log in ~/.second-brain/logs/keep-going.log, output of
each resumed run in ~/.second-brain/logs/keep-going/.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BOSTON = ZoneInfo("America/New_York")
PROJECTS = Path.home() / ".claude/projects"
HOME = Path.home() / ".second-brain"
INSTALL_DIR = HOME / "keep-going"
STATE = INSTALL_DIR / "state.json"
LOG = HOME / "logs/keep-going.log"
RUN_LOGS = HOME / "logs/keep-going"
LABEL = "com.secondbrain.keep-going"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
CONDUCTOR_CLAUDE = Path.home() / "Library/Application Support/com.conductor.app/bin/claude"

CHECK_EVERY_MIN = 10
LOOKBACK_HOURS = 24
GRACE_SEC = 120
MAX_TRIES = 3
PROMPT = ("Your usage limit has reset, so you've been resumed automatically. Carry on with the task you were "
          "working on when you stopped, from where you left off. If it was already finished, say so in one line.")


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(BOSTON):%Y-%m-%d %H:%M} Boston] {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def boston(ts):
    return datetime.fromtimestamp(ts, BOSTON).strftime("%a %H:%M")


def find_claude():
    return os.environ.get("CLAUDE_BIN") or shutil.which("claude") or str(CONDUCTOR_CLAUDE)


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"tries": {}, "running": {}, "seen": []}


def save_state(state):
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stopped_by_limit(path):
    """If this conversation's last message is a usage-limit error, return its details; else None."""
    last, mode, cwd = None, None, None
    with path.open(errors="ignore") as f:
        for line in f:
            if '"type":"user"' not in line and '"type":"assistant"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("isSidechain") or d.get("type") not in ("user", "assistant"):
                continue  # sidechains are helper agents, not the main chat
            last = d
            mode = d.get("permissionMode") or mode
            cwd = d.get("cwd") or cwd
    if not last or last.get("error") != "rate_limit":
        return None
    info = (last.get("apiErrorParams") or {}).get("rate_limit_info") or last.get("quotaLimits") or {}
    resets = info.get("resetsAt")
    if not resets or not cwd:
        return None
    return {"id": last.get("sessionId") or path.stem, "uuid": last.get("uuid"), "resets": int(resets),
            "cwd": cwd, "mode": mode if mode not in (None, "default", "manual") else "auto", "file": str(path)}


def find_stopped():
    cutoff = time.time() - LOOKBACK_HOURS * 3600
    found = []
    for path in PROJECTS.glob("*/*.jsonl"):
        if path.stat().st_mtime < cutoff:
            continue
        s = stopped_by_limit(path)
        if s and Path(s["cwd"]).is_dir() and not Path(s["cwd"]).resolve().is_relative_to(HOME.resolve()):
            found.append(s)
    return sorted(found, key=lambda s: s["resets"])


def title(s):
    """A short label for the log: the workspace folder name and the start of the first thing Aman asked."""
    first = ""
    with open(s["file"], errors="ignore") as f:
        for line in f:
            if '"type":"user"' in line:
                try:
                    c = json.loads(line)["message"]["content"]
                except (ValueError, KeyError):
                    continue
                text = c if isinstance(c, str) else next((b.get("text", "") for b in c if b.get("type") == "text"), "")
                if text and not text.startswith("<"):
                    first = " ".join(text.split())[:50]
                    break
    return f"{Path(s['cwd']).name}: \"{first}\"" if first else Path(s["cwd"]).name


def notify(msg):
    subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Claude resumed"'],
                   capture_output=True)


def resume(s):
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    out = RUN_LOGS / f"{datetime.now(BOSTON):%Y-%m-%d_%H%M}_{s['id'][:8]}.log"
    cmd = ["caffeinate", "-i", find_claude(), "--resume", s["id"], "-p", PROMPT, "--permission-mode", s["mode"]]
    with out.open("w") as f:
        proc = subprocess.Popen(cmd, cwd=s["cwd"], stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    return proc.pid, out


def check(dry_run=False):
    state = load_state()
    state["running"] = {k: v for k, v in state["running"].items() if alive(v)}
    now = time.time()
    started, waiting = [], []
    for s in find_stopped():
        if s["id"] in state["running"]:
            continue  # already being resumed
        tries = state["tries"].get(s["uuid"], 0)
        if tries >= MAX_TRIES:
            continue
        name = title(s)
        if now < s["resets"] + GRACE_SEC:
            waiting.append(s)
            if dry_run or s["uuid"] not in state.setdefault("seen", []):
                log(f"Waiting: {name} (limit resets {boston(s['resets'])} Boston)")
                state["seen"] = state["seen"][-200:] + [s["uuid"]]
            continue
        if dry_run:
            log(f"Would resume now: {name} [{s['mode']}]")
            continue
        pid, out = resume(s)
        state["running"][s["id"]] = pid
        state["tries"][s["uuid"]] = tries + 1
        started.append(name)
        log(f"Resumed: {name} [{s['mode']}], output in {out}")
    if waiting and not dry_run:
        # Keep the Mac from idle-sleeping until the earliest reset, so the next check can run on time.
        secs = int(min(s["resets"] for s in waiting) + GRACE_SEC - now) + 60
        subprocess.Popen(["caffeinate", "-i", "-t", str(secs)], start_new_session=True)
    if started:
        notify(f"{len(started)} conversation(s) picked up again after the usage limit reset.")
    if not dry_run:
        save_state(state)
    if not started and not waiting and dry_run:
        log("Nothing stopped by the usage limit in the last 24 hours.")


def status():
    state = load_state()
    print("Background job:", "ON (checks every 10 minutes)" if PLIST.exists() else "OFF (run: install)")
    stopped = find_stopped()
    print(f"\nStopped by the usage limit (last {LOOKBACK_HOURS}h): {len(stopped) or 'none'}")
    for s in stopped:
        when = "resumes at next check" if time.time() > s["resets"] + GRACE_SEC else f"resets {boston(s['resets'])}"
        done = state["tries"].get(s["uuid"], 0)
        print(f"  - {title(s)}: {when}" + (f" (tried {done}x)" if done else ""))
    running = [k for k, v in state.get("running", {}).items() if alive(v)]
    print(f"\nResumed and still working: {len(running) or 'none'}")
    if LOG.exists():
        print("\nRecent log:")
        print("".join(LOG.read_text().splitlines(keepends=True)[-8:]), end="")


def install():
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    (HOME / "logs").mkdir(parents=True, exist_ok=True)
    script = INSTALL_DIR / "keep_going.py"
    shutil.copy2(__file__, script)
    claude = find_claude()
    path = f"{Path(claude).parent}:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    PLIST.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key><array><string>{sys.executable}</string><string>{script}</string><string>check</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>{path}</string><key>CLAUDE_BIN</key><string>{claude}</string></dict>
  <key>StartInterval</key><integer>{CHECK_EVERY_MIN * 60}</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{HOME}/logs/keep-going.launchd.log</string>
  <key>StandardErrorPath</key><string>{HOME}/logs/keep-going.launchd.log</string>
</dict></plist>
""")
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    subprocess.run(["launchctl", "load", str(PLIST)], check=True)
    log(f"Installed: checks every {CHECK_EVERY_MIN} minutes, including after a restart.")


def uninstall():
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    PLIST.unlink(missing_ok=True)
    log("Uninstalled: no more automatic resumes.")


def main():
    ap = argparse.ArgumentParser(description="Resume Claude conversations stopped by the usage limit.")
    ap.add_argument("command", choices=["check", "status", "install", "uninstall"])
    ap.add_argument("--dry-run", action="store_true", help="with check: show what it would resume, start nothing")
    args = ap.parse_args()
    {"check": lambda: check(args.dry_run), "status": status, "install": install, "uninstall": uninstall}[args.command]()


if __name__ == "__main__":
    main()
