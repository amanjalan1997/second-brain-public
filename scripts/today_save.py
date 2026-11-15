#!/usr/bin/env python3
"""Save an approved /today to the app and GitHub in one step (D-052): step A8 parts 4–5.

  python3 scripts/today_save.py <YYYY-MM-DD> [--comments <answers.json>] [--commit "<message>"] [--skip news,explain]

Run it after the list and the approved changes are written to their files (lists/todo/<date>.md, network.md,
companies.md, news/<date>.md, explained/<date>.md, calls.md, research.md, learning.md, the state files). In order:
  1. rebuild lists/network.xlsx
  2. Today + Emails: todo_sync.py merge, then export (only adds; Aman's ticks, edits and deletes survive)
  3. refresh_helper.py morning (the app shows "Last refreshed … (morning list)")
  4. Network, Companies, Calls/research/learn today (--replace), News and Explained (never --replace)
  5. the waiting-on list (email_tracker render + email_app waiting)
  6. comments.py answer <file>, if --comments is given
  7. with --commit: git add lists + the rule files, commit with that message, pull --rebase, push
Every step runs even if an earlier one failed; the summary says exactly which failed. Exit code 1 if any did.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
PY = sys.executable
RULE_FILES = ["config/todo-rules.md", "config/preferences.md", "config/email-voice.md"]


def sh(args, stdin=None):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, input=stdin)
    return r.returncode, r.stdout, r.stderr


def push(writes_cmd, replace):
    import webdb
    code, out, err = sh(writes_cmd)
    if code:
        raise RuntimeError(err.strip().splitlines()[-1] if err.strip() else f"exit {code}")
    n, d = webdb.push(json.loads(out), replace=replace)
    return f"{n} saved" + (f", {d} removed" if d else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("date")
    ap.add_argument("--comments")
    ap.add_argument("--commit")
    ap.add_argument("--skip", default="", help="comma list of steps to leave out: xlsx,todo,network,companies,thinking,news,explain,waiting")
    a = ap.parse_args()
    skip = {s.strip() for s in a.skip.split(",") if s.strip()}
    tmp = Path(tempfile.mkdtemp(prefix="today-save-"))
    results = []

    def step(name, fn):
        if name in skip:
            results.append(("–", name, "skipped"))
            return
        try:
            results.append(("✓", name, fn() or "done"))
        except Exception as e:  # keep going: one failed write mustn't stop the others
            results.append(("✗", name, str(e)[:300]))

    def run(args):
        code, out, err = sh(args)
        if code:
            raise RuntimeError((err or out).strip().splitlines()[-1] if (err or out).strip() else f"exit {code}")
        return out.strip().splitlines()[-1][:200] if out.strip() else "done"

    todo = f"lists/todo/{a.date}.md"
    step("xlsx", lambda: run([PY, "scripts/network_xlsx.py"]))

    def todo_step():
        if not (ROOT / todo).exists():
            raise RuntimeError(f"{todo} not found")
        code, out, err = sh([PY, "scripts/todo_sync.py", "merge", todo])
        if code:
            raise RuntimeError((err or out).strip()[-300:])
        run([PY, "scripts/todo_sync.py", "export", a.date])
        run([PY, "scripts/refresh_helper.py", "morning"])
        try:
            s = json.loads(out)
            return ", ".join(f"{k} {v}" for k, v in s.items() if isinstance(v, (int, str)))[:200]
        except ValueError:
            return out.strip()[-200:]
    step("todo", todo_step)
    step("network", lambda: push([PY, "scripts/network_to_app.py", str(tmp / "net")], True))
    step("companies", lambda: push([PY, "scripts/companies_to_app.py", str(tmp / "co")], True))
    step("thinking", lambda: push([PY, "scripts/thinking_to_app.py", str(tmp / "thk")], True))
    news = ROOT / f"lists/news/{a.date}.md"
    if news.exists():
        step("news", lambda: push([PY, "scripts/news_to_app.py", str(news), str(tmp / "news")], False))
    if (ROOT / f"lists/explained/{a.date}.md").exists():
        step("explain", lambda: push([PY, "scripts/explain_to_app.py", str(tmp / "explain"), a.date], False))
    step("waiting", lambda: (run([PY, "scripts/email_tracker.py", "render"]), run([PY, "scripts/email_app.py", "waiting"]))[1])
    if a.comments:
        step("comments", lambda: run([PY, "scripts/comments.py", "answer", a.comments]))

    if a.commit:
        def commit():
            files = ["lists"] + [f for f in RULE_FILES if (ROOT / f).exists()]
            code, _, err = sh(["git", "add", *files])
            if code:
                raise RuntimeError(err.strip()[-200:])
            if not sh(["git", "diff", "--cached", "--quiet"])[0]:
                return "nothing new to commit"
            for args in (["git", "commit", "-q", "-m", a.commit], ["git", "pull", "--rebase", "--autostash", "-q"], ["git", "push", "-q"]):
                code, out, err = sh(args)
                if code:
                    raise RuntimeError(f"{args[1]}: {(err or out).strip()[-200:]}")
            return sh(["git", "log", "--oneline", "-1"])[1].strip()
        step("git", commit)

    for mark, name, msg in results:
        print(f"{mark} {name}: {msg}")
    failed = [n for m, n, _ in results if m == "✗"]
    print("All saved." if not failed else f"FAILED: {', '.join(failed)}. Tell Aman plainly; don't report the app as updated.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
