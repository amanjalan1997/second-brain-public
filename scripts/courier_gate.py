"""The courier's gate (D-035): answers Claude's tool-approval prompts during a background courier run.

Aman's Microsoft 365 connection requires approval for every Outlook tool call. In a background run nobody is there
to click "allow", so Claude asks this gate instead (claude -p --permission-prompt-tool mcp__gate__approve). It allows
only the tools listed in COURIER_ALLOW for this run (Write only inside the repo's drafts/ folder), and allows outlook_send_draft only for a draft that
`courier.py verify ... after` checked against what Aman approved in the last 10 minutes, and outlook_create_event only
for the exact invite Aman approved, after `courier.py invite-check` found the time free (once per approval,
docs/PRD-invites.md). Everything else is refused.

A minimal MCP server over stdio (newline-delimited JSON-RPC), no dependencies. Started by scripts/courier.py.
"""
import json
import os
import sys
import time
from pathlib import Path

ALLOW = set(json.loads(os.environ.get("COURIER_ALLOW", "[]")))
DRAFTS = (Path(os.environ.get("COURIER_ROOT", ".")) / "drafts").resolve()
OKDIR = Path.home() / ".second-brain/courier-ok"
SEND = "mcp__claude_ai_Microsoft_365__outlook_send_draft"
EVENT = "mcp__claude_ai_Microsoft_365__outlook_create_event"
FRESH = 900  # an invite check is good for 15 minutes
LOG = Path.home() / ".second-brain/courier.log"


def same_event(want, got):
    """True only if `got` (the tool call) is exactly the approved invite `want`, field by field."""
    if set(got) - set(want):
        return False  # nothing added: no other calendar, no extra options
    for k, v in want.items():
        g = got.get(k)
        if k in ("start", "end"):
            if not isinstance(g, dict) or str(g.get("dateTime", ""))[:16] != v["dateTime"][:16] or g.get("timeZone") != v["timeZone"]:
                return False
        elif k == "attendees":
            if sorted(str(a.get("email", "")).strip().lower() for a in g or []) != sorted(a["email"].lower() for a in v):
                return False
            if any(a.get("type", "required") != "required" for a in g or []):
                return False
        elif g != v:
            return False
    return True


def invite_ok(args):
    """The approved, checked invite these arguments match (path of its ok file), or None."""
    for f in sorted(OKDIR.glob("invite-*.json")):
        ok = json.loads(f.read_text())
        if ok.get("checked") and time.time() - ok.get("checkedAt", 0) < FRESH and same_event(ok["event"], args):
            return f
    return None


def decide(tool, args):
    if tool == "Write" and "Write" in ALLOW:  # files only inside the repo's git-ignored drafts/ folder
        if DRAFTS in Path(str(args.get("file_path", "/"))).resolve().parents:
            return {"behavior": "allow", "updatedInput": args}
        return {"behavior": "deny", "message": "The courier may only write inside drafts/."}
    if tool not in ALLOW:
        return {"behavior": "deny", "message": f"The courier doesn't allow {tool} in this run."}
    if tool == SEND:
        ok = OKDIR / str(args.get("messageId", ""))
        if not (ok.exists() and time.time() - json.loads(ok.read_text())["at"] < 600):
            return {"behavior": "deny", "message": "Blocked: this draft wasn't verified against what Aman approved."}
        (OKDIR / f"{args.get('messageId')}.attempt").write_text(str(time.time()))  # so the courier knows a send was tried
    if tool == EVENT:
        f = invite_ok(args)
        if not f:
            return {"behavior": "deny", "message": "Blocked: this isn't the invite Aman approved, or its calendar check is missing or old."}
        f.rename(f.with_suffix(".attempt"))  # used up: a second create_event for the same approval is refused
    return {"behavior": "allow", "updatedInput": args}


def reply(i, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": i, "result": result}) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        method, i = msg.get("method"), msg.get("id")
        if method == "initialize":
            reply(i, {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2024-11-05"),
                      "capabilities": {"tools": {}}, "serverInfo": {"name": "courier-gate", "version": "1"}})
        elif method == "tools/list":
            reply(i, {"tools": [{"name": "approve", "description": "Approves or refuses a tool call for the courier.",
                                 "inputSchema": {"type": "object", "properties": {"tool_name": {"type": "string"},
                                                 "input": {"type": "object"}, "tool_use_id": {"type": "string"}}}}]})
        elif method == "tools/call":
            a = msg.get("params", {}).get("arguments", {})
            d = decide(a.get("tool_name", ""), a.get("input") or {})
            if d["behavior"] == "deny" or a.get("tool_name") in (SEND, EVENT):
                with LOG.open("a") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} gate: {d['behavior']} {a.get('tool_name')}\n")
            reply(i, {"content": [{"type": "text", "text": json.dumps(d)}]})
        elif i is not None:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": i, "error": {"code": -32601, "message": "unknown method"}}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
