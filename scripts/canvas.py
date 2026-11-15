"""Talk to Canvas (canvas.mit.edu) for the Coursework section (docs/PRD-canvas.md, D-042).

  python3 scripts/canvas.py check            test the connection: who you are, active courses, assignment counts
  python3 scripts/canvas.py renew [--force]  renew the token if it expires within 10 days (--force: renew now)
  python3 scripts/canvas.py adopt            swap a hand-made CANVAS_TOKEN for a self-renewing one (first setup, or recovery)
  python3 scripts/canvas.py sync             fetch courses, assignments and announcements and load them into the app
  python3 scripts/canvas.py tick             what the Mac's helper runs every minute: renew if due, sync hourly
                                             (or right after Aman taps Refresh). No network use when nothing is due
  python3 scripts/canvas.py pending [N]      items still missing a Quick review summary, as JSON for Claude (default 40)
  python3 scripts/canvas.py summaries <file.json | ->   save Claude's Quick review summaries, then sync

MIT caps Canvas tokens at 30 days. The script keeps its own token alive: `renew` asks Canvas for a fresh
key with a new 30-day expiry and saves it, and the old key stops working at once. `tick` runs it daily.

What goes where (PRD section 12): the app's database gets `coursework` (one doc per assignment: dates, status,
format, rubric, the instructions as plain text, the Quick review summary), `announcements` (last 30 days) and
`meta/canvas` (last sync, token expiry, courses). Summaries and the "what changed" state live on the Mac in
~/.second-brain/canvas/, never in the repo. Only 15.xxx courses are synced (orientation courses are skipped).

Needs CANVAS_TOKEN and CANVAS_TOKEN_ID in ~/.second-brain/repo/.env, the one copy every job reads, because a
renewal kills the old key and copies would go stale. The token is secret: it can do anything Aman can do in
Canvas, so it must never be printed, committed, pasted into chat or put in the app.
"""
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV = Path(os.environ.get("CANVAS_ENV", Path.home() / ".second-brain" / "repo" / ".env"))
BASE = "https://canvas.mit.edu"
RENEW_WITHIN_DAYS = 10
DATA = Path.home() / ".second-brain" / "canvas"
SYNC_EVERY_MIN = 60
ANNOUNCE_DAYS = 30
DELIVER = {"online_upload", "online_text_entry", "online_url", "media_recording", "student_annotation"}
QUIZ = {"online_quiz", "external_tool", "discussion_topic"}


def env():
    vals = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    if not vals.get("CANVAS_TOKEN"):
        sys.exit(f"Missing CANVAS_TOKEN in {ENV} (see docs/PRD-canvas.md section 5a).")
    return vals


def save_env(updates):
    """Replace or add KEY=value lines in .env, writing a temp file first so a crash never leaves it half-written."""
    lines = ENV.read_text().splitlines()
    done = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip()
        if k in updates:
            lines[i] = f"{k}={updates[k]}"
            done.add(k)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in done]
    tmp = ENV.with_name(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV)


def call(method, path, data=None, token=None):
    token = token or env()["CANVAS_TOKEN"]
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(BASE + path, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        hint = " (token expired or deleted: make a new one, see docs/PRD-canvas.md section 5a)" if e.code == 401 else ""
        sys.exit(f"Canvas error {e.code} on {method} {path.split('?')[0]}{hint}: {e.read().decode()[:200]}")


def days_left(vals):
    exp = vals.get("CANVAS_TOKEN_EXPIRES")
    if not exp:
        return None
    return (dt.datetime.fromisoformat(exp.replace("Z", "+00:00")) - dt.datetime.now(dt.timezone.utc)).days


def check():
    me = call("GET", "/api/v1/users/self")
    courses = call("GET", "/api/v1/courses?enrollment_state=active&per_page=100")
    print(f"Connected as {me['name']}. {len(courses)} active courses:")
    for c in courses:
        n = len(call("GET", f"/api/v1/courses/{c['id']}/assignments?per_page=100"))
        print(f"  {c.get('course_code', '?'):<14} {n:>3} assignments  {c.get('name', '')[:60]}")
    left = days_left(env())
    print(f"Token renews itself; current key expires in {left} days." if left is not None else "Token expiry unknown: run `renew --force`.")


def renew(force=False):
    vals = env()
    left = days_left(vals)
    if not force and left is not None and left > RENEW_WITHIN_DAYS:
        print(f"Token fine: {left} days left.")
        return
    if not vals.get("CANVAS_TOKEN_ID"):
        sys.exit("Missing CANVAS_TOKEN_ID: this token wasn't made by the script, so it can't be renewed.")
    expires = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t = call("PUT", f"/api/v1/users/self/tokens/{vals['CANVAS_TOKEN_ID']}",
             {"token[regenerate]": "true", "token[expires_at]": expires})
    if not t.get("visible_token"):
        sys.exit("Canvas renewed the token but didn't return the new key; make a new one by hand (section 5a).")
    save_env({"CANVAS_TOKEN": t["visible_token"], "CANVAS_TOKEN_EXPIRES": t.get("expires_at") or expires})
    call("GET", "/api/v1/users/self")  # the saved key works
    print(f"Token renewed: expires {t.get('expires_at')}.")


def adopt():
    expires = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t = call("POST", "/api/v1/users/self/tokens",
             {"token[purpose]": "Second brain (renews itself)", "token[expires_at]": expires})
    save_env({"CANVAS_TOKEN": t["visible_token"], "CANVAS_TOKEN_ID": t["id"],
              "CANVAS_TOKEN_EXPIRES": t.get("expires_at") or expires})
    call("GET", "/api/v1/users/self")  # the saved key works
    print(f"Now using a self-renewing token (expires {t.get('expires_at')}). Delete the hand-made one in "
          "Canvas: Account > Settings > Approved Integrations.")


# ---------- sync: Canvas → the app's database ----------

def get_all(path):
    """GET every page of a Canvas list (it pages with a Link header)."""
    token, out, url = env()["CANVAS_TOKEN"], [], BASE + path
    while url:
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out += json.loads(r.read().decode() or "[]")
                m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
                url = m.group(1) if m else None
        except urllib.error.HTTPError as e:
            sys.exit(f"Canvas error {e.code} on GET {path.split('?')[0]}: {e.read().decode()[:200]}")
    return out


def plain(markup, limit=None):
    """Canvas HTML → readable plain text (paragraphs and bullets kept)."""
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", markup or "")
    t = re.sub(r"(?i)<li(\s[^>]*)?>", "\n• ", t)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|h\d|li|tr|ul|ol)>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ")
    t = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in t.splitlines())
    t = re.sub(r"•\s*\n+\s*", "• ", t)
    t = re.sub(r"\n\n+(?=• )", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t if not limit or len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + " …"


def links(markup):
    out = []
    for href, text in re.findall(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', markup or ""):
        href = html.unescape(href)
        href = BASE + href if href.startswith("/") else href
        name = plain(text) or href
        if href.startswith("http") and all(x["url"] != href for x in out):
            out.append({"name": name[:90], "url": href.split("?verifier")[0] if "/files/" not in href else href})
    return out[:12]


def digest(*parts):
    return hashlib.sha1("\x1f".join(str(p or "") for p in parts).encode()).hexdigest()[:12]


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text()) if p.exists() else default


def store(name, data):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = DATA / (name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    os.replace(tmp, DATA / name)


def kind_of(types):
    t = set(types or [])
    if t & DELIVER:
        return "deliverable"
    if t & QUIZ:
        return "quiz"
    if "not_graded" in t:
        return "prep"
    return "inclass"  # none / on_paper: done in class, nothing to hand in


def status_of(a):
    s = a.get("submission") or {}
    if s.get("excused"):
        return "excused"
    if s.get("workflow_state") == "graded" and s.get("score") is not None:
        return "graded"
    if s.get("submitted_at") or s.get("workflow_state") in ("submitted", "pending_review"):
        return "submitted"
    if s.get("missing"):
        return "missing"
    return "todo"


def webdb_mod():
    # the database key lives in the same .env as the Canvas token (this script may run from a Conductor workspace)
    vals = env()
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
        if vals.get(k):
            os.environ.setdefault(k, vals[k])
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import webdb
    return webdb


def sync(quiet=False):
    started = dt.datetime.now(dt.timezone.utc)
    courses = [c for c in call("GET", "/api/v1/courses?enrollment_state=active&per_page=100")
               if str(c.get("course_code", "")).startswith("15.")]
    seen_due = load("due.json", {})       # assignment id -> due date last time (to flag moved deadlines)
    moved = load("moved.json", {})        # assignment id -> {from, at}
    sums = load("summaries.json", {})     # item id -> {hash, ...summary}
    writes, cmeta = [], []
    for c in courses:
        code = c["course_code"].split("_")[0]
        cmeta.append({"id": c["id"], "code": code, "name": re.sub(r"^\S+\s+", "", c.get("name", "")).split(":")[0].strip(),
                      "url": f"{BASE}/courses/{c['id']}"})
        for a in get_all(f"/api/v1/courses/{c['id']}/assignments?include[]=submission&per_page=100"):
            if not a.get("published", True):
                continue
            aid, due = str(a["id"]), a.get("due_at")
            if aid in seen_due and seen_due[aid] != due and seen_due[aid] and due:
                moved[aid] = {"from": seen_due[aid], "at": started.isoformat(timespec="seconds")}
            seen_due[aid] = due
            sub = a.get("submission") or {}
            h = digest(a.get("name"), a.get("description"), due)
            doc_id = f"{c['id']}-{aid}"
            summ = sums.get(doc_id) if (sums.get(doc_id) or {}).get("hash") == h else None
            mv = moved.get(aid)
            if mv and (started - dt.datetime.fromisoformat(mv["at"])).days > 7:
                mv = None
            writes.append({"op": "set", "collection": "coursework", "doc_id": doc_id, "data": {
                "course": code, "courseId": c["id"], "title": (a.get("name") or "").strip(), "due": due,
                "unlockAt": a.get("unlock_at"), "lockAt": a.get("lock_at"), "locked": bool(a.get("locked_for_user")),
                "kind": kind_of(a.get("submission_types")), "types": a.get("submission_types") or [],
                "exts": a.get("allowed_extensions") or [], "points": a.get("points_possible"),
                "team": bool(a.get("group_category_id")), "attempts": a.get("allowed_attempts"),
                "status": status_of(a), "submittedAt": sub.get("submitted_at"), "late": bool(sub.get("late")),
                "score": sub.get("score"), "grade": sub.get("grade"), "attempt": sub.get("attempt"),
                "rubric": [{"what": r.get("description", ""), "points": r.get("points")} for r in (a.get("rubric") or [])][:12],
                "text": plain(a.get("description"), 3000), "links": links(a.get("description")),
                "url": a.get("html_url"), "moved": mv, "hash": h, "summary": summ}})
    since = (started - dt.timedelta(days=ANNOUNCE_DAYS)).strftime("%Y-%m-%d")
    ctx = "&".join(f"context_codes[]=course_{c['id']}" for c in courses)
    codes = {f"course_{c['id']}": c["course_code"].split("_")[0] for c in courses}
    for n in get_all(f"/api/v1/announcements?{ctx}&start_date={since}&end_date={(started + dt.timedelta(days=1)).strftime('%Y-%m-%d')}&per_page=100"):
        doc_id = f"{n['context_code'].split('_')[-1]}-{n['id']}"
        h = digest(n.get("title"), n.get("message"))
        summ = sums.get(doc_id) if (sums.get(doc_id) or {}).get("hash") == h else None
        writes.append({"op": "set", "collection": "announcements", "doc_id": doc_id, "data": {
            "course": codes.get(n["context_code"], ""), "title": (n.get("title") or "").strip(), "posted": n.get("posted_at"),
            "author": (n.get("author") or {}).get("display_name") or n.get("user_name") or "",
            "unread": n.get("read_state") == "unread", "text": plain(n.get("message"), 4000), "links": links(n.get("message")),
            "files": [{"name": f.get("display_name", ""), "url": f.get("url", "")} for f in (n.get("attachments") or [])][:8],
            "url": n.get("html_url"), "hash": h, "summary": summ}})
    meta = {"lastSync": started.isoformat(timespec="seconds"), "ok": True, "error": "", "courses": cmeta,
            "tokenExpires": env().get("CANVAS_TOKEN_EXPIRES", ""),
            "counts": {"coursework": sum(w["collection"] == "coursework" for w in writes),
                       "announcements": sum(w["collection"] == "announcements" for w in writes)}}
    writes.append({"op": "set", "collection": "meta", "doc_id": "canvas", "data": meta})
    n, gone = webdb_mod().push(writes, replace=True)
    store("due.json", seen_due)
    store("moved.json", {k: v for k, v in moved.items() if (started - dt.datetime.fromisoformat(v["at"])).days <= 7})
    store("last.json", {"lastSync": meta["lastSync"], "items": {w["doc_id"]: w["data"] for w in writes if w["collection"] != "meta"}})
    if not quiet:
        print(f"Synced {meta['counts']['coursework']} assignments and {meta['counts']['announcements']} announcements "
              f"from {len(courses)} courses ({gone} removed). {len(pending_items(10 ** 6))} still need a Quick review summary.")


def sync_failed(reason):
    try:
        wd = webdb_mod()
        rows = wd.call("GET", "/rest/v1/docs?select=data&collection=eq.meta&id=eq.canvas") or []
        meta = rows[0]["data"] if rows else {}
        meta.update({"ok": False, "error": reason[:200], "failedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
        wd.push([{"op": "set", "collection": "meta", "doc_id": "canvas", "data": meta}])
    except SystemExit:
        pass


def tick():
    """Run by the Mac's helper every minute. Cheap when nothing is due."""
    vals = env()
    left = days_left(vals)
    t = load("tick.json", {})
    now = dt.datetime.now(dt.timezone.utc)
    if left is not None and left <= RENEW_WITHIN_DAYS and t.get("renewTried", "") < now.strftime("%Y-%m-%d"):
        t["renewTried"] = now.strftime("%Y-%m-%d")
        store("tick.json", t)
        renew()
    last = load("last.json", {}).get("lastSync")
    asked = (t.get("refreshAsked") or "")
    try:
        rows = webdb_mod().call("GET", "/rest/v1/docs?select=data&collection=eq.meta&id=eq.refresh") or []
        req = (rows[0]["data"].get("requestedAt") if rows else "") or ""
    except SystemExit:
        req = ""
    tried = t.get("lastAttempt")
    due = (not last or (now - dt.datetime.fromisoformat(last)).total_seconds() > SYNC_EVERY_MIN * 60) and \
        (not tried or (now - dt.datetime.fromisoformat(tried)).total_seconds() > 15 * 60)  # a failing sync retries every 15 min
    if req and req != asked and (not last or req > last):
        due = True
        t["refreshAsked"] = req
    if due:
        t["lastAttempt"] = now.isoformat(timespec="seconds")
        store("tick.json", t)
        try:
            sync(quiet=True)
        except SystemExit as e:
            sync_failed(str(e))
            raise


def pending_items(limit=40):
    items = load("last.json", {}).get("items", {})
    utc = dt.datetime.now(dt.timezone.utc)
    now, soon, recent = utc.isoformat(), (utc + dt.timedelta(days=21)).isoformat(), (utc - dt.timedelta(days=14)).isoformat()
    out = []
    for doc_id, d in items.items():
        if d.get("summary"):
            continue
        if "posted" in d and (d.get("posted") or "") >= recent:
            out.append({"id": doc_id, "type": "announcement", "course": d["course"], "title": d["title"], "posted": d["posted"],
                        "text": d["text"], "links": [x["name"] for x in d.get("links", [])], "files": [x["name"] for x in d.get("files", [])], "hash": d["hash"]})
        elif d.get("kind") in ("deliverable", "quiz") and d.get("status") in ("todo", "missing") and d.get("due") and now[:10] <= d["due"] <= soon:
            out.append({"id": doc_id, "type": "assignment", "course": d["course"], "title": d["title"], "due": d["due"], "kind": d["kind"],
                        "format": d["types"], "exts": d["exts"], "points": d["points"], "team": d["team"], "rubric": d["rubric"],
                        "text": d["text"], "links": [x["name"] for x in d.get("links", [])], "hash": d["hash"]})
    out.sort(key=lambda x: x.get("due") or x.get("posted") or "", reverse=False)
    return out[:limit]


def save_summaries(items):
    """items: [{id, hash, ...}] — assignments: what, asks[], deliverable, uses[], effort; announcements: gist, action, deadline."""
    sums = load("summaries.json", {})
    keep = ("what", "asks", "deliverable", "uses", "effort", "gist", "action", "deadline")
    for it in items:
        if it.get("id") and it.get("hash"):
            sums[it["id"]] = {"hash": it["hash"], **{k: it[k] for k in keep if it.get(k)}}
    store("summaries.json", sums)
    print(f"Saved {len(items)} summaries.")
    sync()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check":
        check()
    elif cmd == "renew":
        renew("--force" in sys.argv)
    elif cmd == "adopt":
        adopt()
    elif cmd == "sync":
        sync()
    elif cmd == "tick":
        tick()
    elif cmd == "pending":
        print(json.dumps(pending_items(int(sys.argv[2]) if len(sys.argv) > 2 else 40), indent=1))
    elif cmd == "summaries":
        src = sys.argv[2] if len(sys.argv) > 2 else "-"
        save_summaries(json.load(sys.stdin if src == "-" else open(src)))
    else:
        sys.exit(__doc__)
