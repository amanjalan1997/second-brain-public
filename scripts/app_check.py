"""Layout check for the web app: run before pushing any change to app/ (CLAUDE.md rule 9). When a new view or
collection is added to the app, add it to the lists below.

  python3 scripts/app_check.py            check every view at phone (390px) and laptop (1440px) width
  python3 scripts/app_check.py --show     same, then open the screenshots

It builds a stand-in copy of app/index.html filled with the live data (read only; tests/app_mock.js plays the
database), opens each view in headless Chrome, and reports:
  - the page scrolling sideways (something wider than the screen)
  - text spilling out of its box (an element whose content is taller or wider than the element itself)
Screenshots of every view go to .context/app-check/ (git-ignored), so a person can look too.
Exits 1 if anything is flagged. Needs Google Chrome and the database key in .env (~/.second-brain/repo/.env).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / ".context" / "app-check"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PHONE = ["meetings", "meetings+brief", "today", "today+cmdrawer", "today+cm", "emails", "emails+iv", "emails+ivpanel", "emails+ivconfirm", "emails+ivconfirmed", "news", "podcasts", "podcasts+podsheet", "github", "github+gssheet", "github+gsskip", "network", "companies", "coursework", "coursework+sheet"]
LAPTOP = ["meetings", "dash", "dash+cm", "dash+iv", "today", "emails", "emails+ivpanel", "emails+ivother", "news", "podcasts", "podcasts+podsheet", "github", "github+gsplan", "network", "companies", "coursework", "coursework+sheet", "calls", "research"]
COLLS = ["days", "tasks", "people", "companies", "news", "explained", "calls", "questions", "coursework", "announcements", "suggestions", "podcasts", "podprogress", "comments", "scout", "briefs"]
METAS = ["canvas", "refresh", "learning", "thinking", "storylines", "glossary", "companies", "network", "podcasts", "scout"]

# Runs inside the app page: finds overflow, then reports to the parent frame (phone) or the page itself (laptop).
PROBE = r"""<script>
// "+iv…" views: sample Ghostwriter drafts with invites (made up; the stand-in has no drafts), then open the sheet / panel
function ivSetup() {
  const h = location.hash;
  if (!h.includes("+iv")) return;
  sb = sb || {};
  state.courier = { lastSeen: new Date().toISOString(), sending: true, invites: true };
  state.drafts = window.__DATA.sampleDrafts;
  goView(h.slice(1).split("+")[0]);
  const open = (id) => { state.draftOpen = id; state.sheet = { mode: "view" }; renderSheet(); };
  const click = (sel) => { const b = document.querySelector(sel); if (b) b.click(); };
  if (h.includes("+ivconfirmed")) { open("sample-confirmed"); click("[data-act=dinvite]"); }
  else if (/\+iv(panel|confirm|other)/.test(h)) {
    open("sample-offer"); click("[data-act=dinvite]");
    if (h.includes("+ivother")) { click("[data-act=ivteams][data-v='0']"); click("[data-act=ivopt][data-v=other]"); click("[data-act=ivedit]"); }
    if (h.includes("+ivconfirm")) click("[data-act=ivnext]");
  }
}
const click0 = (sel) => { const b = document.querySelector(sel); if (b) b.click(); };
setTimeout(() => {
  // Podcasts only show in the web app (they need its sign-in), so pretend to be it for those views
  if (/^#(podcasts|dash|github)\b/.test(location.hash)) {
    sb = sb || {};
    const D = window.__DATA;
    state.pods = Object.entries(D.podcasts || {}).map(([id, d]) => ({ id, ...d }));
    state.podProg = D.podprogress || {}; state.podMeta = { ...(D.meta.podcasts || {}), lastSeen: new Date().toISOString() };
    state.scout = Object.entries(D.scout || {}).map(([id, d]) => ({ id, ...d })); state.scoutMeta = { ...(D.meta.scout || {}), lastSeen: new Date().toISOString() };
    goView(location.hash.slice(1).split("+")[0]); }
  if (location.hash.includes("+podsheet")) { const b = document.querySelector(".pm-list [data-act=podopen]") || document.querySelector("[data-act=podopen][data-id]"); if (b) b.click(); }
  ivSetup();
  if (location.hash.includes("+brief")) { const b = document.querySelector(".mb-card"); if (b) b.click(); }
  setTimeout(() => { // after the GitHub cards have drawn
    if (location.hash.includes("+gssheet")) click0("[data-act=gsfork]");
    if (location.hash.includes("+gsskip")) click0("[data-act=gsskip]");
    if (location.hash.includes("+gsplan")) click0("[data-act=gsplanopen]");
  }, 2500);
  if (location.hash.includes("+sheet")) { const b = document.querySelector("[data-act=cwopen]"); if (b) b.click(); }
  if (location.hash.includes("+cmdrawer")) { const b = document.querySelector("[data-act=drawer][data-key=comments]"); if (b) b.click(); }
  else if (location.hash.includes("+cm")) { const b = document.querySelector(".cm-btn.cm-has") || document.querySelector(".cm-btn"); if (b) b.click(); }
  setTimeout(() => {
    const W = innerWidth, out = [];
    if (document.documentElement.scrollWidth > W + 1) out.push(`page is ${document.documentElement.scrollWidth}px wide on a ${W}px screen`);
    const roots = ["main", "desk", "cwroot", "sheetroot", "cmroot", "podroot", "gsroot", "mbroot", "top"].map((id) => document.getElementById(id)).filter(Boolean);
    for (const r of roots) for (const el of r.querySelectorAll("*")) {
      const cs = getComputedStyle(el), rect = el.getBoundingClientRect();
      if (!rect.width || cs.display === "inline" || cs.display === "contents" || el.closest("svg")) continue;
      const hid = (v) => v !== "visible";
      // 10px slack: decorations (a timeline line, a shadow) may poke out a little; spilled text is a full line or more
      const tall = !hid(cs.overflowY) && el.scrollHeight > el.clientHeight + 10 && el.clientHeight > 0;
      const wide = !hid(cs.overflowX) && el.scrollWidth > el.clientWidth + 10 && el.clientWidth > 0;
      const offscreen = rect.right > W + 1 && !el.closest(".chips") && cs.position !== "fixed";
      if (tall || wide || offscreen) {
        const name = el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (typeof el.className === "string" && el.className ? "." + el.className.trim().split(/\s+/).join(".") : "");
        out.push(`${name}: ${tall ? `content ${el.scrollHeight}px tall in a ${el.clientHeight}px box` : wide ? `content ${el.scrollWidth}px wide in a ${el.clientWidth}px box` : `runs off the screen (right edge ${Math.round(rect.right)}px)`} · "${(el.textContent || "").trim().slice(0, 50)}"`);
      }
    }
    const res = JSON.stringify([...new Set(out)].slice(0, 40));
    if (window.parent !== window) window.parent.postMessage(res, "*"); else document.body.setAttribute("data-check", res);
  }, /\+gs/.test(location.hash) ? 3800 : 1200);
}, 2500);
</script>"""


def env():
    for path in (REPO / ".env", Path.home() / ".second-brain" / "repo" / ".env"):
        if path.exists():
            for line in path.read_text().splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    sys.path.insert(0, str(REPO / "scripts"))
    import webdb
    return webdb


def data():
    wd = env()
    d = {c: {r["id"]: r["data"] for r in wd.call("GET", f"/rest/v1/docs?select=id,data&collection=eq.{c}") or []} for c in COLLS}
    for k in ("days", "news", "explained"):
        d[k] = dict(sorted(d[k].items())[-3:])
    day = max(d["days"]) if d["days"] else ""
    d["tasks"] = {k: v for k, v in d["tasks"].items() if v.get("day") == day}
    d["meta"] = {r["id"]: r["data"] for r in wd.call("GET", "/rest/v1/docs?select=id,data&collection=eq.meta") or [] if r["id"] in METAS}
    if not d["comments"]:
        d["comments"] = sample_comments(d)
    if not d["briefs"]:  # not loaded into the app yet: use the saved briefs on this Mac
        for f in sorted((REPO / "lists" / "briefs").glob("*.json")):
            d["briefs"].update({b["id"]: {k: v for k, v in b.items() if k != "id"} for b in json.loads(f.read_text())})
    d["sampleDrafts"] = sample_drafts()
    sample_morning(d)
    sample_scout(d)
    return d


def sample_morning(d):
    """Stand-in only: when today has no morning episodes yet, dress up ready ones (plus one still recording) as the morning three."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    if any(v.get("by") == "morning" and (v.get("morning") or {}).get("date") == today for v in d["podcasts"].values()):
        return
    why = ["Physical Intelligence raised $1B overnight: the biggest robotics round this year, and a VLA bet",
           "You meet Casey from Acme at 2pm: this is the construction-autonomy market he's in",
           "Step 2 of your robotics path: where robot training data comes from"]
    ready = [k for k, v in d["podcasts"].items() if v.get("status") == "ready"][:2]
    for n, k in enumerate(ready):
        d["podcasts"][k] = {**d["podcasts"][k], "by": "morning", "morning": {"date": today, "slot": n + 1, "kind": "news", "why": why[n]}}
    d["podcasts"]["pod-sample-morning"] = {
        "status": "recording", "step": "recording in NotebookLM · 4 min", "by": "morning", "title": "Where robot training data comes from",
        "createdAt": f"{today}T10:00:00Z", "morning": {"date": today, "slot": 3, "kind": "learn", "why": why[2]},
        "request": {"prompt": "Where robot training data comes from", "length": "quick", "style": "explain",
                    "from": {"kind": "morning", "id": today, "label": "Learning path"}, "requestedAt": f"{today}T10:00:00Z"}}
    d["meta"].setdefault("podcasts", {})["morning"] = {"date": today, "status": "queued", "made": 3}


def sample_scout(d):
    """Stand-in only: make sure one pick has a ready plan and one a long name, so the plan sheet and wrapping get checked."""
    d.setdefault("scout", {})
    d["scout"]["sample-plan"] = {
        "repo": "a-very-long-organisation-name/an-even-longer-repository-name-for-wrapping", "url": "https://github.com/x/y", "owner": "x",
        "stars": 12345, "gained": 2100, "gainedPeriod": "this week", "language": "Python", "license": None, "created": "2026-09-01T00:00:00Z",
        "pushed": "2026-10-31T00:00:00Z", "isNew": True, "lens": "sectors", "effort": "fork-adapt", "score": 8, "status": "new", "foundAt": "2026-11-01T12:00:00Z",
        "what": "Sample pick for the layout check.", "why": "Checks that long names and three cautions wrap inside the card on a phone.",
        "how": "Ask Claude to read it with you.", "betterThan": None, "cautions": ["no license: fine to read, but reusing the code isn't clearly allowed"],
        "plan": {"status": "ready", "path": "notes/github/x.md", "text": "## What it would do for you\nA **sample** plan.\n## Steps\n1. Ask Claude to clone it\n2. Try it\n- a bullet"}}
    d["meta"].setdefault("scout", {"status": "done", "lastScanAt": "2026-11-01T12:00:00Z", "summary": {"checked": 616, "picks": 1}, "forkModes": ["fork", "private-copy"]})


def sample_drafts():
    """Made-up drafts (stand-in only) covering "Set up invite": offered times, a confirmed time, a taken time, sent ones."""
    who = [{"name": "Alex Rivera", "email": "alex.rivera@example.com", "source": "thread"}]
    sched = {"kind": "offer", "minutes": 30, "teams": True, "place": "", "title": "Alex <> Aman (Sloan MBA'28)",
             "note": "Coffee chat on Acme's edge AI work and the a robotics club.", "attendees": who, "theirTz": "America/Los_Angeles",
             "options": [{"start": "2026-11-05T12:30", "text": "Thurs 11/5, 12:30pm", "free": True, "their": "9:30am PT"},
                         {"start": "2026-11-06T10:00", "text": "Fri 11/6, 10am", "free": True, "their": "7am PT"},
                         {"start": "2026-11-09T14:00", "text": "Mon 11/9, 2pm", "free": False, "their": "11am PT"}],
             "inviteBody": "Hi Alex,\n\nThanks so much for reaching out! Just sent you an invite for **{{time}}** {{where}}. "
                           "Happy to move it as needed!\n\nI look forward to our conversation.\n\nBest,\nAman"}
    base = {"to": who, "cc": [], "bcc": [], "outlookDraftId": "x", "created": "2026-10-31T14:00:00Z", "version": 1}
    return [
        {**base, "id": "sample-offer", "kind": "reply", "status": "ready", "priority": 1, "person": "Alex Rivera", "company": "Acme",
         "why": "Asked for your times for a coffee chat", "subject": "Re: Coffee chat with a Sloan MBA",
         "replyTo": {"from": "Alex Rivera", "when": "Fri 10/30, 4:12pm", "gist": "Happy to chat, what times work for you next week?"},
         "body": "Hi Alex,\n\nThanks so much for reaching out! Would any of these work for a 30 min chat on Teams?\n\n"
                 "Thurs 11/5, 12:30-2pm; Fri 11/6, 10am-12pm; or Mon 11/9, 2-4pm ET\n\nBest,\nAman", "schedule": sched},
        {**base, "id": "sample-confirmed", "kind": "invite", "status": "ready", "priority": 2, "person": "Riley Chen",
         "company": "Acme Robotics", "why": "Confirmed Thurs 11/5, 3pm · no invite on your calendar yet", "subject": "Re: Quick call?",
         "body": "Sounds like a plan! Just sent you an invite.\n\nBest,\nAman",
         "to": [{"name": "Riley Chen", "email": "riley.chen@example.com", "source": "network"}],
         "schedule": {**sched, "kind": "confirmed", "title": "Riley <> Aman (Sloan MBA'28)", "theirTz": None, "inviteBody": "",
                      "attendees": [{"name": "Riley Chen", "email": "riley.chen@example.com", "source": "network"}],
                      "options": [{"start": "2026-11-05T15:00", "text": "Thurs 11/5, 3pm", "free": True}]}},
        {**base, "id": "sample-taken", "kind": "reply", "status": "failed", "priority": 3, "person": "John Doe", "company": "2L",
         "why": "Proposed Wed 1:30 or Thurs 2pm", "subject": "Re: Follow-up", "body": "Hi John,\n\nWed 1:30 works great!\n\nBest,\nAman",
         "note": "Wed 11/4, 1:30-2pm is no longer free on your calendar, so nothing was sent. Pick another time.", "schedule": sched},
        {**base, "id": "sample-invited", "kind": "invite", "status": "invited", "person": "Dana Lee", "sentAt": "2026-10-31T15:00:00Z",
         "inviteSent": {"text": "Tues 11/3, 11am-11:30am", "teams": True, "link": "https://outlook.office365.com/x"}, "subject": "Re: chat"},
    ]


def sample_comments(d):
    """Made-up comments (stand-in only) so the check covers the bubble counts, the thread, the card and the drawer."""
    task = next(iter(sorted(d["tasks"].items(), key=lambda kv: kv[1].get("order") or 0)), None)
    person = next(iter(d["people"].items()), None)
    out, n = {}, 0

    def add(kind, iid, title, where, text, chips=(), reply=None, sugg=None):
        nonlocal n
        n += 1
        c = {"target": {"kind": kind, "id": iid, "title": title, "where": where}, "chips": list(chips), "text": text,
             "createdAt": f"2026-10-31T1{n}:00:00Z", "status": "read" if reply else "new"}
        if reply:
            c.update({"reply": {"text": reply, "at": f"2026-10-31T1{n}:30:00Z"}, "outcome": "rule" if sugg else "noted", "suggestionTitles": [sugg] if sugg else []})
        out[f"c-sample{n}"] = c
    if task:
        add("task", task[0], task[1].get("text", ""), "Today", "This kind of club admin task never matters to me, it's always optional", ["Not for me"],
            "Got it: optional club admin isn't a task. Rule proposed in Suggestions.", "New rule: never make optional club admin a task")
        add("task", task[0], task[1].get("text", ""), "Today", "", ["Wrong section"])
    if person:
        add("person", person[0], person[1].get("name", ""), "Network", "She moved to Acme Robotics last month")
    add("section", "dash-news", "Top news", "Dashboard", "Always lead with a robotics story, even a small one", ["More like this"],
        "Noted. One more like this and I'll propose a rule.")
    return out


def chrome(url, width, height, shot):
    for attempt in range(2):  # headless Chrome now and then hangs on one view: try it once more
        try:
            res = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={width},{height}",
                                  "--virtual-time-budget=8000", f"--screenshot={shot}", "--dump-dom", url],
                                 capture_output=True, text=True, timeout=90)
            break
        except subprocess.TimeoutExpired:
            if attempt:
                return None
    m = re.search(r'data-check="([^"]*)"', res.stdout)
    return json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")) if m else None


def main():
    if not Path(CHROME).exists():
        sys.exit("Google Chrome isn't installed, so the layout check can't run.")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mock.js").write_text((REPO / "tests" / "app_mock.js").read_text())
    html = Path(os.environ.get("APP_CHECK_HTML", REPO / "app" / "index.html")).read_text()  # APP_CHECK_HTML: check another copy
    stand_in = html.replace('<script src="config.js"></script>',
                            '<meta charset="utf-8"><script>window.__DATA=' + json.dumps(data()) + ';</script><script src="mock.js"></script>' + PROBE)
    (OUT / "index.html").write_text(stand_in)
    problems = 0
    for size, views in (("phone", PHONE), ("laptop", LAPTOP)):
        for v in views:
            shot = OUT / f"{size}-{v.replace('+', '-')}.png"
            if size == "phone":
                # headless Chrome won't go narrower than 500px, so the phone view runs in a 390px frame
                frame = OUT / f"frame-{v.replace('+', '-')}.html"
                frame.write_text(f"""<body style="margin:0"><iframe src="index.html#{v}" style="border:0;width:390px;height:2400px"></iframe>
<script>addEventListener("message", (e) => document.body.setAttribute("data-check", e.data));</script>""")
                found = chrome(f"file://{frame}", 500, 2400, shot)
            else:
                found = chrome(f"file://{OUT / 'index.html'}#{v}", 1440, 1400, shot)
            if found is None:
                print(f"✗ {size} {v}: the page didn't finish loading (check the screenshot)")
                problems += 1
            elif found:
                problems += 1
                print(f"✗ {size} {v}:")
                for f in found:
                    print(f"    {f}")
            else:
                print(f"✓ {size} {v}")
    print(f"\nScreenshots: {OUT}")
    if "--show" in sys.argv:
        subprocess.run(["open", *sorted(str(p) for p in OUT.glob("*.png"))])
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
