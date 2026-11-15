"""The Mac side of Podcasts (docs/PRD-podcasts.md, D-044). A launch agent runs `check` every minute.

  python3 scripts/podcast_helper.py check                     look once for work: an episode Aman asked for in the app
                                                              (podcasts/<id> status "requested") → Claude researches and
                                                              writes the brief (podcast skill, section A) → the NotebookLM
                                                              maker records it → shrink, upload, "ready". Also renews play
                                                              links, removes deleted episodes, archives old played ones and
                                                              keeps the Apple Podcasts feed current. Uses no Claude when idle.
  python3 scripts/podcast_helper.py request "<prompt>" [--length quick|standard|deep] [--style explain|brief|debate|critique]
        [--level new|some|expert] [--context none|interests|interests_and_calls] [--from kind:id[:label]] [--link URL ...]
        [--parent <id>]                                       ask for an episode (chat, /today); prints its id
  python3 scripts/podcast_helper.py show <id>                 print one episode (what section A reads first)
  python3 scripts/podcast_helper.py list [status]             list episodes, newest first
  python3 scripts/podcast_helper.py step <id> "<step>"        show a step in the app ("researching")
  python3 scripts/podcast_helper.py brief-done <id>           section A finished: check brief.txt, focus.txt, notes.json
                                                              in the episode's folder and copy them to the app
  python3 scripts/podcast_helper.py fail <id> "<reason>"      give up on an episode with a plain reason
  python3 scripts/podcast_helper.py signin [--wait MIN]       sign NotebookLM in on this Mac (Aman types his own password),
                                                              then retry episodes that were waiting for it
  python3 scripts/podcast_helper.py add-file <audio> --title "…" [--notes notes.json] [--prompt "…"] [--notebook URL]
                                                              put an episode made elsewhere into the app
  python3 scripts/podcast_helper.py import <notebook url> [--title "…"] [--notes notes.json]   download a notebook's newest
                                                              episode with the maker and put it in the app
  python3 scripts/podcast_helper.py morning [--force]          make today's "morning three" now (the check starts it by itself
                                                              at podcasts.morning.start; --force runs again on the same day)
  python3 scripts/podcast_helper.py morning-history           past morning picks with Aman's ratings, and every topic of the
                                                              last 30 days (section E reads it so nothing repeats)
  python3 scripts/podcast_helper.py morning-new "<topic>" --kind news|prep|today|learn|question --why "<one line>" [--level new|some] [--brief <brief id>]
  python3 scripts/podcast_helper.py morning-prep [--days 2]   upcoming meetings from the Meetings tab, most prep-worthy first, with their listen topics (D-055)
                                                              section E: start one morning episode; prints its id and folder
  python3 scripts/podcast_helper.py feed                      rebuild the private Apple Podcasts feed now
  python3 scripts/podcast_helper.py status                    Mac, sign-in, today's count, storage
  python3 scripts/podcast_helper.py install | uninstall       set up / remove the launch agent

Every morning (podcasts.morning in settings.yaml, D-050) the check also starts one Claude run (podcast skill, section E)
that picks three topics for the day from the news, today's calendar, the learning path and research questions, and
writes their briefs; the same queue then records them, so they're ready by about 7am. If the Mac sleeps through the
start time, it runs when the Mac wakes (until 9pm).

Episodes live in the `podcasts` collection; listening progress in `podprogress` (so a playing episode doesn't redraw
the app every few seconds); `meta/podcasts` holds the Mac's status. Audio goes to the private Supabase Storage bucket
`podcasts` as AAC at 64 kbps (`afconvert`, built into macOS); the app plays it through a long-lived signed link kept
in the owner-only episode doc. Every episode's files (original download, brief, notes) stay on the Mac in
~/.second-brain/podcasts/<id>/. The launch agent runs from its own repo copy, ~/.second-brain/podcast-repo.
"""
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import webdb  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home() / ".second-brain"
EPISODES = HOME / "podcasts"
LOGS = HOME / "logs"
LABEL = "com.secondbrain.podcasts"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
BUCKET = "podcasts"
LINK_DAYS = 400            # play links last 400 days and are renewed when under 30 days are left
RESEARCH_TIMEOUT_MIN = 25
MORNING_TIMEOUT_MIN = 50
MORNING_LAST_HOUR = 21     # a Mac that sleeps all day skips that day's morning episodes
RUNNING = ("planning", "researching", "writing", "recording", "saving")
BOSTON = None
try:
    from zoneinfo import ZoneInfo
    BOSTON = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    pass

ALLOWED = ["Read", "Write", "Edit", "Glob", "Grep", "Skill", "TodoWrite", "WebSearch", "WebFetch",
           "Bash(python3 scripts/podcast_helper.py *)", "Bash(python3 scripts/webdb.py get *)",
           "Bash(date*)", "Bash(ls *)", "Bash(cat *)", "Bash(mkdir *)", "Bash(wc *)"]
GRANOLA = ["mcp__claude_ai_Granola__list_meetings", "mcp__claude_ai_Granola__get_meetings", "mcp__claude_ai_Granola__search_meetings",
           "mcp__claude_ai_Granola__query_granola_meetings", "mcp__claude_ai_Granola__search_transcripts"]
BLOCKED = ["mcp__claude_ai_Microsoft_365", "mcp__claude_ai_Gmail", "mcp__claude_ai_Google_Calendar", "mcp__claude_ai_Google_Drive",
           "Bash(git push*)", "Bash(curl *)"]
# The morning run may also read today's calendar (to pick topics), never email: anything else in Outlook is blocked.
CALENDAR = ["mcp__claude_ai_Microsoft_365__outlook_calendar_search"]
MORNING_BLOCKED = [b for b in BLOCKED if b != "mcp__claude_ai_Microsoft_365"] + [f"mcp__claude_ai_Microsoft_365__{t}" for t in (
    "outlook_email_search", "read_resource", "chat_message_search", "search_people", "outlook_send_mail", "outlook_send_draft",
    "outlook_create_draft", "outlook_create_reply_draft", "outlook_create_reply_all_draft", "outlook_update_draft", "outlook_forward_mail",
    "outlook_create_event", "outlook_update_event", "outlook_delete_event", "outlook_respond_to_event", "outlook_trash_thread",
    "outlook_batch_delete_messages", "teams_list_chats", "teams_list_channel_messages", "teams_send_chat_message",
    "teams_send_channel_message", "sharepoint_search", "sharepoint_folder_search")]
REPAIR_ALLOWED = ["Read", "Edit", "Glob", "Grep", "Bash(python3 scripts/podcast_maker.py *)", "Bash(git add scripts/podcast_maker.py)",
                  "Bash(git commit *)", "Bash(git pull*)", "Bash(git push*)", "Bash(git diff*)", "Bash(ls *)"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse(iso):
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")) if iso else None


def boston_day(dt=None):
    return (dt or datetime.now(timezone.utc)).astimezone(BOSTON).strftime("%Y-%m-%d") if BOSTON else (dt or datetime.now()).strftime("%Y-%m-%d")


def settings():
    s = {"enabled": True, "maker": "notebooklm", "defaults": {"length": "standard", "style": "explain", "level": "new"},
         "use_my_context": "interests", "daily_episode": False, "max_per_day": 5, "keep_in_cloud_days": 60, "feed": False}
    try:
        import yaml
        s.update(yaml.safe_load((REPO / "config/settings.yaml").read_text()).get("podcasts") or {})
    except Exception:
        pass
    s["morning"] = {"enabled": False, "count": 3, "start": "05:30", "length": "quick", "use_calendar": True, **(s.get("morning") or {})}
    return s


# ---------- database ----------

def get_doc(coll, did):
    rows = webdb.call("GET", f"/rest/v1/docs?select=data&collection=eq.{webdb.q(coll)}&id=eq.{webdb.q(did)}")
    return rows[0]["data"] if rows else None


def put_doc(coll, did, data):
    webdb.push([{"op": "set", "collection": coll, "doc_id": did, "data": data}])


def patch(eid, **fields):
    d = get_doc("podcasts", eid) or {}
    d.update(fields)
    put_doc("podcasts", eid, d)
    return d


def all_episodes():
    return [{**r["data"], "id": r["id"]} for r in webdb.call("GET", "/rest/v1/docs?select=id,data&collection=eq.podcasts")]


def meta(**fields):
    m = get_doc("meta", "podcasts") or {}
    if fields:
        m.update(fields)
        put_doc("meta", "podcasts", m)
    return m


def set_step(eid, step, status=None):
    d = get_doc("podcasts", eid) or {}
    steps = (d.get("steps") or [])[-20:]
    if not steps or steps[-1].get("step") != step:
        steps.append({"step": step, "at": now()})
    d.update(step=step, steps=steps, heartbeat=now(), **({"status": status} if status else {}))
    put_doc("podcasts", eid, d)
    meta(lastSeen=now())


# ---------- storage (Supabase Storage, private bucket) ----------

def storage(method, path, body=None, ctype="application/json", headers=None):
    url, key = webdb.env()
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    req = urllib.request.Request(url + "/storage/v1" + path, method=method, data=data)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("apikey", key)
    req.add_header("Content-Type", ctype)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip().startswith(("{", "[")) else raw
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Storage error {e.code} on {method} {path.split('?')[0]}: {e.read().decode()[:200]}")


def upload(obj, data, ctype, cache="31536000"):
    storage("POST", f"/object/{BUCKET}/{obj}", data, ctype, {"x-upsert": "true", "cache-control": f"max-age={cache}"})


def sign(obj, days):
    url, _ = webdb.env()
    res = storage("POST", f"/object/sign/{BUCKET}/{obj}", {"expiresIn": int(days * 86400)})
    return url + "/storage/v1" + res["signedURL"], (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")


def remove(objs):
    if objs:
        storage("DELETE", f"/object/{BUCKET}", {"prefixes": list(objs)})


def storage_bytes():
    rows = storage("POST", f"/object/list/{BUCKET}", {"prefix": "episodes/", "limit": 1000, "offset": 0})
    return sum(((r.get("metadata") or {}).get("size") or 0) for r in rows if isinstance(r, dict))


# ---------- files ----------

def shrink(src, dst):
    """AAC, 64 kbps, 44.1 kHz stereo (mono downmix fails in afconvert): about 0.5 MB a minute."""
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "64000", str(src), str(dst)], check=True, capture_output=True)
    out = subprocess.run(["afinfo", str(dst)], capture_output=True, text=True).stdout
    m = re.search(r"estimated duration: ([\d.]+)", out)
    return round(float(m.group(1))) if m else 0


def publish_audio(eid, src):
    """Shrink, upload and sign an episode file; returns the audio fields for the doc."""
    folder = EPISODES / eid
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "episode.m4a"
    secs = shrink(src, out)
    obj = f"episodes/{eid}.m4a"
    upload(obj, out.read_bytes(), "audio/mp4")
    link, exp = sign(obj, LINK_DAYS)
    return {"path": obj, "url": link, "urlExpires": exp, "durationS": secs, "bytes": out.stat().st_size, "mime": "audio/mp4"}


def new_id(prompt):
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")[:28].strip("-") or "episode"
    t = datetime.now(timezone.utc).astimezone(BOSTON) if BOSTON else datetime.now()
    return f"pod-{t.strftime('%Y%m%d-%H%M')}-{slug}-{secrets.token_hex(2)}"


# ---------- Claude runs ----------

def claude_bin():
    for p in (os.environ.get("CLAUDE_BIN"), shutil.which("claude"),
              str(Path.home() / "Library/Application Support/com.conductor.app/bin/claude"),
              str(Path.home() / ".local/bin/claude"), "/usr/local/bin/claude", "/opt/homebrew/bin/claude"):
        if p and Path(p).exists():
            return p
    sys.exit("Can't find the claude command.")


def run_claude(prompt, tag, allowed, timeout_min=RESEARCH_TIMEOUT_MIN, blocked=BLOCKED):
    LOGS.mkdir(parents=True, exist_ok=True)
    EPISODES.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"{datetime.now().strftime('%Y-%m-%d-%H%M')}-{tag}.log"
    env = {**os.environ, "SECOND_BRAIN_HEADLESS": "1"}
    cmd = [claude_bin(), "-p", prompt, "--add-dir", str(EPISODES), "--allowedTools", *allowed, "--disallowedTools", *blocked]
    with open(log, "w") as f:
        try:
            code = subprocess.run(cmd, cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                                  timeout=timeout_min * 60).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    return code, log


# ---------- one episode, start to finish ----------

def cancelled(eid):
    return bool((get_doc("podcasts", eid) or {}).get("cancelRequested"))


def research(ep):
    eid = ep["id"]
    folder = EPISODES / eid
    folder.mkdir(parents=True, exist_ok=True)
    for f in ("brief.txt", "focus.txt", "notes.json"):
        (folder / f).unlink(missing_ok=True)
    set_step(eid, "planning", "planning")
    ctx = (ep.get("request") or {}).get("context", "interests")
    allowed = ALLOWED + (GRANOLA if ctx == "interests_and_calls" else [])
    code, log = run_claude(f"Use the podcast skill (.claude/skills/podcast/SKILL.md), section A: episode {eid}. "
                           f"Work folder: {folder}. Nobody is watching: never ask questions.", f"podcast-{eid[4:17]}", allowed)
    d = get_doc("podcasts", eid) or {}
    if d.get("cancelRequested"):
        return None
    if not all((folder / f).exists() for f in ("brief.txt", "focus.txt", "notes.json")) or not d.get("briefDone"):
        reason = "the research took too long" if code == "timeout" else "Claude stopped before the brief was ready"
        return {"ok": False, "kind": "research", "message": reason, "log": str(log)}
    return {"ok": True}


def record(ep, s):
    import podcast_maker
    eid = ep["id"]
    req = ep.get("request") or {}
    folder = EPISODES / eid
    parent = get_doc("podcasts", req["parent"]) if req.get("parent") else None
    job = {"brief_file": str(folder / "brief.txt"), "links": req.get("links") or [], "style": req.get("style") or s["defaults"]["style"],
           "length": req.get("length") or s["defaults"]["length"], "focus": (folder / "focus.txt").read_text().strip(),
           "notebook_url": (parent or {}).get("notebookUrl"), "out_dir": str(folder)}
    last = {"t": 0}

    def say(step):
        if datetime.now().timestamp() - last["t"] > 50 or not step.startswith("recording"):
            last["t"] = datetime.now().timestamp()
            set_step(eid, step, "recording")

    check_every = {"t": 0, "v": False}

    def stop():
        if datetime.now().timestamp() - check_every["t"] > 30:
            check_every.update(t=datetime.now().timestamp(), v=cancelled(eid))
        return check_every["v"]

    patch(eid, recordStartedAt=now())
    return podcast_maker.make(job, show=os.environ.get("PODCAST_MAKER_SHOW") == "1", step_cb=say, cancelled=stop,
                              notebook_cb=lambda url: patch(eid, notebookUrl=url))


def repair(ep, res):
    code, log = run_claude(
        f"Use the podcast skill (.claude/skills/podcast/SKILL.md), section C: the NotebookLM maker failed on episode {ep['id']} "
        f"at step '{res.get('step')}' ({res.get('message')}). Snapshot: {res.get('snapshot') or 'none'}. Fix scripts/podcast_maker.py.",
        f"podcast-repair-{ep['id'][4:17]}", REPAIR_ALLOWED, timeout_min=20)
    return code == 0


def finish(ep, res, s):
    eid = ep["id"]
    set_step(eid, "saving", "saving")
    audio = publish_audio(eid, res["audio_file"])
    d = get_doc("podcasts", eid) or {}
    title = d.get("title") or res.get("nlm_title") or "Episode"
    d.update(status="ready", step="", readyAt=now(), audio=audio, notebookUrl=res.get("notebook_url") or d.get("notebookUrl"),
             nlmTitle=res.get("nlm_title") or "", error=None, recoverUrl=None, title=title)
    put_doc("podcasts", eid, d)
    m = meta()
    today = boston_day()
    count = (m.get("today") or {}).get("count", 0) if (m.get("today") or {}).get("date") == today else 0
    meta(lastSeen=now(), signedIn=True, today={"date": today, "count": count + 1}, usage=res.get("usage") or m.get("usage"),
         storageBytes=storage_bytes())
    if s.get("feed") or m.get("feedUrl"):
        build_feed()


def fail(eid, kind, message, **extra):
    patch(eid, status="failed", step="", error={"kind": kind, "message": message, "at": now()}, heartbeat=now(), **extra)


def run_episode(ep, s):
    eid = ep["id"]
    d = get_doc("podcasts", eid) or {}
    # Try again after a failure while recording: the notebook may already hold the finished episode
    if d.get("recoverUrl"):
        import podcast_maker
        set_step(eid, "checking the earlier recording", "recording")
        folder = EPISODES / eid
        res = podcast_maker.download(d["recoverUrl"], folder / "original.m4a")
        if res.get("ok") and (folder / "brief.txt").exists():
            finish(ep, {**res, "notebook_url": d["recoverUrl"]}, s)
            return
    if not (d.get("briefDone") and (EPISODES / eid / "focus.txt").exists()):
        r = research(ep)
        if r is None:
            patch(eid, status="cancelled", step="")
            return
        if not r["ok"]:
            fail(eid, r["kind"], r["message"])
            return
    if cancelled(eid):
        patch(eid, status="cancelled", step="")
        return
    res = record(ep, s)
    if not res["ok"] and res["kind"] == "ui" and not d.get("repaired"):
        set_step(eid, "NotebookLM changed its page: fixing", "recording")
        patch(eid, repaired=True)
        if repair(ep, res):
            subprocess.run(["git", "pull", "--rebase", "--autostash", "-q"], cwd=REPO, capture_output=True)
            import importlib
            import podcast_maker
            importlib.reload(podcast_maker)
            res = record(ep, s)
    if res["ok"]:
        finish(ep, res, s)
        return
    kind = res["kind"]
    if kind == "cancelled":
        patch(eid, status="cancelled", step="")
    elif kind == "signin":
        meta(signedIn=False, signedInCheckedAt=now())
        patch(eid, status="blocked", step="", error={"kind": "signin", "message": "NotebookLM is signed out on your Mac", "at": now()})
    elif kind == "quota":
        tomorrow = (datetime.now(timezone.utc).astimezone(BOSTON) + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0) if BOSTON \
            else datetime.now(timezone.utc) + timedelta(hours=24)
        patch(eid, status="waiting", step="", waitUntil=tomorrow.astimezone(timezone.utc).isoformat(timespec="seconds"),
              error={"kind": "quota", "message": "NotebookLM's daily limit is used up: it tries again after midnight", "at": now()})
    elif kind == "busy":
        patch(eid, status="requested", step="", error={"kind": "busy", "message": res["message"], "at": now()})
    else:
        fail(eid, kind, f"{res.get('message')} (at: {res.get('step')})", recoverUrl=res.get("notebook_url") if res.get("step") in ("recording", "downloading") else None)


# ---------- housekeeping (no browser, no Claude) ----------

def housekeeping(eps, s):
    progress = {r["id"]: r["data"] for r in webdb.call("GET", "/rest/v1/docs?select=id,data&collection=eq.podprogress")}
    changed = False
    keep_days = int(s.get("keep_in_cloud_days") or 60)
    for e in eps:
        st, audio = e.get("status"), e.get("audio") or {}
        if st == "deleted":
            try:
                remove([audio["path"]] if audio.get("path") else [])
            except RuntimeError:
                continue
            src = EPISODES / e["id"]
            if src.exists():
                (EPISODES / "deleted").mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(EPISODES / "deleted" / e["id"]))
            for coll in ("podcasts", "podprogress"):
                webdb.call("DELETE", f"/rest/v1/docs?collection=eq.{coll}&id=eq.{webdb.q(e['id'])}", headers={"Prefer": "return=minimal"})
            changed = True
            continue
        if st == "ready" and audio.get("path"):
            exp = parse(audio.get("urlExpires"))
            if not exp or exp - datetime.now(timezone.utc) < timedelta(days=30):
                link, when = sign(audio["path"], LINK_DAYS)
                patch(e["id"], audio={**audio, "url": link, "urlExpires": when})
            p = progress.get(e["id"]) or {}
            ready = parse(e.get("readyAt"))
            if p.get("played") and not e.get("starred") and ready and datetime.now(timezone.utc) - ready > timedelta(days=keep_days):
                remove([audio["path"]])
                patch(e["id"], status="archived", audio={**audio, "url": None, "path": None}, archivedAt=now())
                changed = True
        if st in RUNNING:
            beat = parse(e.get("heartbeat") or e.get("request", {}).get("requestedAt"))
            # we hold the lock, so nothing is running: a card still in a running step was left behind by a crash
            if beat and datetime.now(timezone.utc) - beat > timedelta(minutes=10):
                fail(e["id"], "stopped", "The Mac stopped partway", recoverUrl=e.get("notebookUrl") or None)
        if st == "waiting" and parse(e.get("waitUntil")) and parse(e["waitUntil"]) <= datetime.now(timezone.utc):
            patch(e["id"], status="requested", waitUntil=None, error=None)
        if st in ("failed", "cancelled") and e.get("retryRequested"):
            patch(e["id"], status="requested", retryRequested=False, error=None, cancelRequested=False, step="")
    m = meta()
    if (s.get("feed") or m.get("feedRequested")) and (changed or not m.get("feedUrl") or m.get("feedFor") != feed_key(eps)):
        build_feed()


def feed_key(eps):
    return hashlib.sha256(json.dumps(sorted(e["id"] for e in eps if e.get("status") == "ready")).encode()).hexdigest()[:16]


def build_feed():
    """A private podcast feed for Apple Podcasts / Overcast (PRD 6e): a secret link anyone with it could play."""
    m = meta()
    eps = sorted([e for e in all_episodes() if e.get("status") == "ready" and (e.get("audio") or {}).get("url")],
                 key=lambda e: e.get("readyAt") or "", reverse=True)
    obj = m.get("feedObject") or f"feed/{secrets.token_urlsafe(18)}.xml"
    app = os.environ.get("WEB_APP_URL") or webdb_env("WEB_APP_URL") or "https://your-app.vercel.app"
    items = []
    for e in eps:
        n, a = e.get("notes") or {}, e["audio"]
        desc = "\n".join([e.get("summary") or ""] + [f"• {c}" for c in n.get("covers") or []]
                         + ([f"Line to say: {n['say']}"] if n.get("say") else []) + ([f"Question to ask: {n['ask']}"] if n.get("ask") else []))
        pub = parse(e.get("readyAt")) or datetime.now(timezone.utc)
        items.append(f"""<item><title>{escape(e.get('title') or 'Episode')}</title><guid isPermaLink="false">{escape(e['id'])}</guid>
<pubDate>{pub.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate><description>{escape(desc)}</description>
<enclosure url="{escape(a['url'])}" length="{a.get('bytes') or 0}" type="audio/mp4"/><itunes:duration>{a.get('durationS') or 0}</itunes:duration></item>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>
<title>Second Brain Podcasts</title><link>{escape(app)}</link><language>en-us</language>
<description>Aman's private episodes, made from his questions. Not public.</description>
<itunes:author>Second Brain</itunes:author><itunes:block>Yes</itunes:block><itunes:explicit>false</itunes:explicit>
<itunes:image href="{escape(app.rstrip('/'))}/icons/icon-512.png"/>
{''.join(items)}
</channel></rss>"""
    upload(obj, xml.encode(), "application/rss+xml", cache="300")
    fields = {"feedObject": obj, "feedFor": feed_key(eps), "feedBuiltAt": now()}
    if not m.get("feedUrl"):
        fields["feedUrl"], _ = sign(obj, 3650)
    meta(**fields)
    return fields.get("feedUrl") or m.get("feedUrl")


def webdb_env(name):
    path = REPO / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ---------- the morning three (D-050) ----------

def boston_now():
    return datetime.now(timezone.utc).astimezone(BOSTON) if BOSTON else datetime.now()


def morning_due(s, m):
    mo, last = s["morning"], m.get("morning") or {}
    if not mo.get("enabled"):
        return False
    if last.get("date") == boston_day():
        # a run that was killed partway (Mac shut down, process stopped) and queued nothing gets one more try
        started = parse(last.get("startedAt"))
        stale = last.get("status") == "picking" and started and datetime.now(timezone.utc) - started > timedelta(minutes=MORNING_TIMEOUT_MIN + 15)
        if not stale or last.get("retried") or morning_eps():
            return False
    h, mi = (int(x) for x in str(mo.get("start") or "05:30").split(":"))
    t = boston_now()
    return (t.hour, t.minute) >= (h, mi) and t.hour < MORNING_LAST_HOUR


def morning_eps(day=None):
    day = day or boston_day()
    return sorted([e for e in all_episodes() if e.get("by") == "morning" and (e.get("morning") or {}).get("date") == day],
                  key=lambda e: (e.get("morning") or {}).get("slot") or 0)


def morning(s):
    """One Claude run picks today's topics and writes every brief (podcast skill, section E); the queue records them."""
    day, mo = boston_day(), s["morning"]
    prev = meta().get("morning") or {}
    meta(morning={"date": day, "status": "picking", "startedAt": now(), "count": int(mo.get("count") or 3), "retried": prev.get("date") == day})
    print(f"{now()} morning {day}: picking", flush=True)
    allowed = ALLOWED + (CALENDAR if mo.get("use_calendar") else [])
    code, log = run_claude(
        f"Use the podcast skill (.claude/skills/podcast/SKILL.md), section E: today's morning episodes for {day}, "
        f"{int(mo.get('count') or 3)} of them. Nobody is watching: never ask questions.",
        "podcast-morning", allowed, timeout_min=MORNING_TIMEOUT_MIN, blocked=MORNING_BLOCKED)
    eps = morning_eps(day)
    for e in eps:  # a brief Claude didn't finish: say so rather than leave the card spinning
        if not e.get("briefDone") and e.get("status") in RUNNING:
            fail(e["id"], "research", "the research took too long" if code == "timeout" else "Claude stopped before the brief was ready")
    made = sum(1 for e in morning_eps(day) if e.get("briefDone"))
    meta(morning={"date": day, "status": "queued" if made else "failed", "finishedAt": now(), "made": made,
                  "count": int(mo.get("count") or 3), "log": str(log)})
    print(f"{now()} morning {day}: {made} queued", flush=True)


def morning_new(topic, opts):
    s = settings()
    day, kind = boston_day(), opts.get("kind") or "news"
    slot = len(morning_eps(day)) + 1
    eid = new_id(topic)
    (EPISODES / eid).mkdir(parents=True, exist_ok=True)
    put_doc("podcasts", eid, {
        "status": "writing", "step": "researching", "createdAt": now(), "heartbeat": now(), "by": "morning",
        "morning": {"date": day, "slot": slot, "kind": kind, "why": opts.get("why") or "", "briefId": opts.get("brief") or None},
        "request": {"prompt": topic, "links": [], "length": s["morning"].get("length") or "quick", "style": "explain",
                    "level": opts.get("level") or "new", "context": s.get("use_my_context", "interests"),
                    "from": {"kind": "morning", "id": day, "label": MORNING_KINDS.get(kind, kind)}, "parent": None,
                    "requestedAt": now()}})
    return eid


MORNING_KINDS = {"news": "In the news", "prep": "Meeting prep", "today": "For today", "learn": "Learning path", "question": "Your question"}
PREP_ORDER = {"interview": 0, "investor": 1, "company": 2, "peer": 3, "event": 4, "professor": 5, "advisor": 6}


def morning_prep(days=None):
    """What the morning run reads to pick meeting-prep episodes (D-055): the Meetings tab's briefs for today and the
    next days, most important first, each with its public 'listen' topic and whether an episode already covers it."""
    s = settings()
    days = int(days or (s["morning"].get("prep_days") or 2))
    start = boston_now().date()
    dates = {(start + timedelta(days=i)).isoformat() for i in range(days)}
    covered = {}
    for e in all_episodes():
        if e.get("status") in ("deleted", "cancelled", "failed"):
            continue
        f, mo = (e.get("request") or {}).get("from") or {}, e.get("morning") or {}
        bid = mo.get("briefId") or (f.get("id") if f.get("kind") == "brief" else None)
        if bid:
            covered[bid] = {"episode": e.get("id"), "title": e.get("title") or (e.get("request") or {}).get("prompt"), "status": e.get("status")}
    rows = webdb.call("GET", "/rest/v1/docs?select=id,data&collection=eq.briefs") or []
    out = []
    for r in rows:
        b = r["data"]
        if b.get("date") not in dates or b.get("depth") == "none" or b.get("status") == "cancelled" or b.get("kind") == "none":
            continue
        people = b.get("people") or []
        out.append({"briefId": r["id"], "date": b.get("date"), "start": b.get("start"), "kind": b.get("kind"), "depth": b.get("depth"),
                    "title": b.get("title"), "company": b.get("company"), "who": ", ".join(p.get("name", "") for p in people[:2]),
                    "goal": (b.get("sixty") or {}).get("goal"), "listen": b.get("listen"), "covered": covered.get(r["id"])})
    out.sort(key=lambda x: (x["covered"] is not None, PREP_ORDER.get(x["kind"], 9), x["date"], x["start"] or ""))
    busy = any(x["kind"] in ("interview", "investor") and not x["covered"] for x in out)
    return {"days": sorted(dates), "busy": busy, "prepSlots": int(s["morning"].get("prep_slots_busy" if busy else "prep_slots") or 1),
            "meetings": out}


def morning_history():
    """What section E reads before picking: past picks with Aman's verdicts, and every topic of the last 30 days."""
    progress = {r["id"]: r["data"] for r in webdb.call("GET", "/rest/v1/docs?select=id,data&collection=eq.podprogress")}
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    out = {"morningPicks": [], "otherEpisodes": []}
    for e in sorted(all_episodes(), key=lambda e: e.get("createdAt") or "", reverse=True):
        if (e.get("createdAt") or "") < since or e.get("status") == "deleted":
            continue
        p, dur = progress.get(e["id"]) or {}, (e.get("audio") or {}).get("durationS") or 0
        row = {"title": e.get("title") or (e.get("request") or {}).get("prompt", ""), "status": e.get("status"),
               "listened": "all" if p.get("played") else f"{round(100 * (p.get('positionS') or 0) / dur)}%" if dur else "0%",
               "rating": {k: v for k, v in (e.get("rating") or {}).items() if k != "at"}}
        if e.get("by") == "morning":
            mo = e.get("morning") or {}
            out["morningPicks"].append({"date": mo.get("date"), "kind": mo.get("kind"), "why": mo.get("why"), **row})
        else:
            out["otherEpisodes"].append(row)
    return out


# ---------- the launch agent's check ----------

def check():
    HOME.mkdir(parents=True, exist_ok=True)
    lock = open(HOME / "podcasts.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # an episode is still being made
    s = settings()
    meta(lastSeen=now())
    eps = all_episodes()
    housekeeping(eps, s)
    if not s.get("enabled", True):
        return
    eps = all_episodes()
    queue = sorted([e for e in eps if e.get("status") == "requested"], key=lambda e: (e.get("request") or {}).get("requestedAt") or "")
    due = morning_due(s, meta())
    if not queue and not due:
        return
    if os.environ.get("SECOND_BRAIN_UPDATED") != "1":
        # get the latest code first, then restart so this run uses it
        head = lambda: subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout  # noqa: E731
        before = head()
        subprocess.run(["git", "pull", "--rebase", "--autostash", "-q"], cwd=REPO, capture_output=True)
        if head() != before:
            lock.close()
            os.environ["SECOND_BRAIN_UPDATED"] = "1"
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), "check"])
    if due:
        morning(s)
        queue = sorted([e for e in all_episodes() if e.get("status") == "requested"], key=lambda e: (e.get("request") or {}).get("requestedAt") or "")
        if not queue:
            return
    m = meta()
    today = boston_day()
    count = (m.get("today") or {}).get("count", 0) if (m.get("today") or {}).get("date") == today else 0
    ep = queue[0]
    if count >= int(s.get("max_per_day") or 5):
        tomorrow = (datetime.now(timezone.utc).astimezone(BOSTON) + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        for e in queue:
            patch(e["id"], status="waiting", waitUntil=tomorrow.astimezone(timezone.utc).isoformat(timespec="seconds"),
                  error={"kind": "cap", "message": f"Today's limit of {s.get('max_per_day')} episodes is reached: it starts after midnight"})
        return
    if m.get("signedIn") is False:
        for e in queue:
            patch(e["id"], status="blocked", error={"kind": "signin", "message": "NotebookLM is signed out on your Mac", "at": now()})
        return
    print(f"{now()} episode {ep['id']}: starting", flush=True)
    try:
        run_episode(ep, s)
    except Exception as ex:  # never leave a card spinning
        fail(ep["id"], "error", f"Something went wrong on the Mac: {type(ex).__name__}: {str(ex)[:200]}")
        raise
    print(f"{now()} episode {ep['id']}: {(get_doc('podcasts', ep['id']) or {}).get('status')}", flush=True)


# ---------- commands ----------

def request(prompt, opts):
    s = settings()
    dfl = s["defaults"]
    frm = None
    if opts.get("from"):
        parts = opts["from"].split(":", 2)
        frm = {"kind": parts[0], "id": parts[1] if len(parts) > 1 else "", "label": parts[2] if len(parts) > 2 else ""}
    eid = new_id(prompt)
    put_doc("podcasts", eid, {
        "status": "requested", "createdAt": now(), "by": opts.get("by", "chat"),
        "request": {"prompt": prompt, "links": opts.get("links") or re.findall(r"https?://\S+", prompt),
                    "length": opts.get("length") or dfl["length"], "style": opts.get("style") or dfl["style"],
                    "level": opts.get("level") or dfl["level"], "context": opts.get("context") or s.get("use_my_context", "interests"),
                    "from": frm, "parent": opts.get("parent"), "requestedAt": now()}})
    return eid


def brief_done(eid):
    folder = EPISODES / eid
    missing = [f for f in ("brief.txt", "focus.txt", "notes.json") if not (folder / f).exists()]
    if missing:
        sys.exit(f"Missing in {folder}: {', '.join(missing)}")
    notes = json.loads((folder / "notes.json").read_text())
    brief = (folder / "brief.txt").read_text()
    focus = (folder / "focus.txt").read_text().strip()
    words = len(brief.split())
    if words < 400:
        sys.exit(f"The brief is only {words} words; aim for 1,500-3,500.")
    if len(focus) > 4000:
        sys.exit("The focus note is too long; keep it under 4,000 characters.")
    for k in ("title", "summary", "covers", "say", "ask", "sources"):
        if not notes.get(k):
            sys.exit(f"notes.json needs '{k}'.")
    # a morning episode written by section E goes straight into the queue to be recorded
    picking = (get_doc("podcasts", eid) or {}).get("by") == "morning" and (meta().get("morning") or {}).get("status") == "picking"
    queued = {"status": "requested", "step": ""} if picking else {}
    patch(eid, title=notes["title"], summary=notes["summary"], brief=brief, focus=focus, briefDone=True, heartbeat=now(),
          notes={k: notes.get(k) for k in ("covers", "terms", "say", "ask", "sources", "context")}, **queued)
    print(f"Saved the brief ({words} words) and show notes for {eid}.")


def add_file(src, opts):
    eid = opts.get("id") or new_id(opts.get("title") or "episode")
    folder = EPISODES / eid
    folder.mkdir(parents=True, exist_ok=True)
    orig = folder / ("original" + Path(src).suffix)
    if Path(src).resolve() != orig.resolve():
        shutil.copy(src, orig)
    notes = json.loads(Path(opts["notes"]).read_text()) if opts.get("notes") else {}
    audio = publish_audio(eid, orig)
    put_doc("podcasts", eid, {
        "status": "ready", "createdAt": opts.get("created") or now(), "readyAt": now(), "by": "import",
        "title": opts.get("title") or notes.get("title") or "Episode", "summary": notes.get("summary") or "",
        "notes": {k: notes.get(k) for k in ("covers", "terms", "say", "ask", "sources", "context")} if notes else None,
        "brief": notes.get("brief") or "", "notebookUrl": opts.get("notebook") or "", "nlmTitle": opts.get("title") or "",
        "request": {"prompt": opts.get("prompt") or "", "style": opts.get("style") or "explain", "length": opts.get("length") or "standard",
                    "level": "new", "from": json.loads(opts["from"]) if opts.get("from") else None, "requestedAt": opts.get("created") or now()},
        "audio": audio})
    meta(storageBytes=storage_bytes())
    return eid, audio


def install():
    home_repo = HOME / "podcast-repo"
    if not (home_repo / ".git").exists():
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=REPO, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "clone", "-q", url, str(home_repo)], check=True)
    # only the database keys: the Canvas token must stay in one place (~/.second-brain/repo/.env), since renewing it kills old copies
    keep = ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "WEB_APP_URL")
    lines = [ln for ln in (REPO / ".env").read_text().splitlines() if ln.split("=", 1)[0].strip() in keep]
    (home_repo / ".env").write_text("\n".join(lines) + "\n")
    os.chmod(home_repo / ".env", 0o600)
    LOGS.mkdir(parents=True, exist_ok=True)
    py = shutil.which("python3") or "/usr/bin/python3"
    path = ":".join([str(Path(py).parent), str(Path(claude_bin()).parent), str(Path.home() / ".local/node/bin"), "/usr/local/bin",
                     "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
    PLIST.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key><array><string>{py}</string><string>{home_repo}/scripts/podcast_helper.py</string><string>check</string></array>
  <key>WorkingDirectory</key><string>{home_repo}</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>{path}</string><key>CLAUDE_BIN</key><string>{claude_bin()}</string></dict>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{LOGS}/podcasts.log</string>
  <key>StandardErrorPath</key><string>{LOGS}/podcasts.log</string>
</dict></plist>
""")
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], check=True)
    meta(lastSeen=now())
    print(f"Installed: {PLIST} (checks every minute, repo copy {home_repo}, logs {LOGS}/podcasts.log).")


def opts_from(rest, multi=("link",)):
    opts, args, i = {}, [], 0
    while i < len(rest):
        a = rest[i]
        if a.startswith("--"):
            k = a[2:]
            v = rest[i + 1] if i + 1 < len(rest) else ""
            if k in multi:
                opts.setdefault(k + "s", []).append(v)
            else:
                opts[k] = v
            i += 2
        else:
            args.append(a)
            i += 1
    return args, opts


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "check":
        check()
    elif cmd == "request":
        args, opts = opts_from(rest)
        print(request(" ".join(args), opts))
    elif cmd == "show":
        d = get_doc("podcasts", rest[0])
        if not d:
            sys.exit("No such episode.")
        print(json.dumps({"id": rest[0], "folder": str(EPISODES / rest[0]), **{k: v for k, v in d.items() if k not in ("brief",)}},
                         ensure_ascii=False, indent=1))
    elif cmd == "list":
        eps = sorted(all_episodes(), key=lambda e: e.get("createdAt") or "", reverse=True)
        for e in eps:
            if not rest or e.get("status") == rest[0]:
                print(f"{e['id']:52} {e.get('status', ''):10} {e.get('title') or (e.get('request') or {}).get('prompt', '')[:60]}")
    elif cmd == "step":
        set_step(rest[0], rest[1], "writing" if re.search(r"writ|check|notes", rest[1], re.I) else "planning" if rest[1] == "planning" else "researching")
    elif cmd == "brief-done":
        brief_done(rest[0])
    elif cmd == "fail":
        fail(rest[0], "research", rest[1] if len(rest) > 1 else "Claude couldn't research this")
    elif cmd == "signin":
        import podcast_maker
        _, opts = opts_from(rest)
        ok = podcast_maker.signin(int(opts.get("wait") or 15))
        if ok:
            meta(signedIn=True, signedInCheckedAt=now())
            n = 0
            for e in all_episodes():
                if e.get("status") == "blocked":
                    patch(e["id"], status="requested", error=None)
                    n += 1
            print(f"NotebookLM is signed in on this Mac.{f' Retrying {n} waiting episode(s).' if n else ''}")
        else:
            print("Not signed in yet. Run this again when you're ready.")
    elif cmd == "add-file":
        args, opts = opts_from(rest)
        eid, audio = add_file(args[0], opts)
        print(f"Added {eid}: {audio['durationS'] // 60} min, {audio['bytes'] // 1024} KB.")
    elif cmd == "import":
        import podcast_maker
        args, opts = opts_from(rest)
        eid = opts.get("id") or new_id(opts.get("title") or "episode")
        (EPISODES / eid).mkdir(parents=True, exist_ok=True)
        res = podcast_maker.download(args[0], EPISODES / eid / "original.m4a")
        if not res["ok"]:
            sys.exit(f"Couldn't download: {res['message']}")
        eid, audio = add_file(res["audio_file"], {**opts, "id": eid, "notebook": args[0], "title": opts.get("title") or res["nlm_title"]})
        print(f"Imported {eid}: {audio['durationS'] // 60} min.")
    elif cmd == "morning":
        s = settings()
        if "--force" not in rest and (meta().get("morning") or {}).get("date") == boston_day():
            sys.exit("Today's morning episodes were already made. Add --force to make another set.")
        lock = open(HOME / "podcasts.lock", "w")
        fcntl.flock(lock, fcntl.LOCK_EX)  # waits for an episode being recorded
        morning(s)
        lock.close()
        print("Queued: the Mac records them in the next few minutes.")
    elif cmd == "morning-history":
        print(json.dumps(morning_history(), ensure_ascii=False, indent=1))
    elif cmd == "morning-prep":
        args, opts = opts_from(rest)
        print(json.dumps(morning_prep(opts.get("days")), ensure_ascii=False, indent=1))
    elif cmd == "morning-new":
        args, opts = opts_from(rest)
        eid = morning_new(" ".join(args), opts)
        print(json.dumps({"id": eid, "folder": str(EPISODES / eid)}))
    elif cmd == "feed":
        print(build_feed())
    elif cmd == "status":
        m = meta()
        print(json.dumps({k: m.get(k) for k in ("lastSeen", "signedIn", "today", "usage", "storageBytes", "feedBuiltAt")}, indent=1))
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
