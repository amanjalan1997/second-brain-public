"""Meeting briefs (docs/PRD-meeting-briefs.md, D-054): Claude's side of the app's Meetings tab.

  python3 scripts/briefs.py diff <events.json | ->          which calendar items are new / changed / unchanged / gone
  python3 scripts/briefs.py check <briefs.json>             validate briefs before saving (sources, identity, daily cap)
  python3 scripts/briefs.py save <briefs.json> [--no-push]  merge into lists/briefs/<date>.json, rebuild the day's .md,
                                                            update lists/briefs-state.json, load into the app (keeps Aman's taps)
  python3 scripts/briefs.py profile "<email | name | company>"  the latest saved research on a person or company, with its date
  python3 scripts/briefs.py requests                        Brief me taps waiting for the Mac
  python3 scripts/briefs.py working <id> [<id> ...]         mark requests as being worked on (the app shows "Preparing…")
  python3 scripts/briefs.py fail <id> "<plain reason>"      a request that couldn't be done (the app shows the reason)
  python3 scripts/briefs.py sync                            copy Aman's ratings, kind changes and person picks into the state file
  python3 scripts/briefs.py report [--days 7]               numbers for the Sunday review
  python3 scripts/briefs.py cleanup                         remove app briefs older than briefs.keep_in_app_days
  python3 scripts/briefs.py show <YYYY-MM-DD>               print a day's briefs as Markdown

events.json is a list of calendar items in Boston time, one per event (classes and deadlines included):
  {"eventId", "date": "YYYY-MM-DD", "start": "HH:MM", "end": "HH:MM", "title", "where", "attendees": [emails], "cancelled": false}

briefs.json is a list of briefs in the shape the app reads (see the brief skill, section D). One brief per calendar
item, including "none" ones (classes etc.), so the Meetings tab can show the whole day. The app owns a few fields
(APP_FIELDS); save never overwrites them. Brief text lives in the owner-only database and in lists/briefs/ in the
private repo: short extracted facts and links, never email or note text (CLAUDE.md rule 5).
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parent.parent
DIR = REPO / "lists" / "briefs"
STATE = REPO / "lists" / "briefs-state.json"
BOSTON = ZoneInfo("America/New_York")
KINDS = {"interview": "Interview", "company": "Company chat", "investor": "Investor", "peer": "Peer chat",
         "professor": "Professor", "advisor": "Advisor", "event": "Event", "none": "No brief"}
DEPTHS = ("full", "light", "event", "none")
STATUSES = ("ready", "updated", "moved", "cancelled", "unsure", "none", "preparing")
# Fields only the app writes (Aman's taps). save keeps them; the Mac only clears a request once it's answered.
APP_FIELDS = ("rating", "ratedAt", "kindSet", "kindSetAt", "picks", "request", "requestedAt", "requestState",
              "requestNote", "requestDoneAt", "seenAt")
SIXTY = ("who", "why", "goal", "open", "ask")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def settings():
    try:
        import yaml
        return (yaml.safe_load((REPO / "config/settings.yaml").read_text()) or {}).get("briefs", {}) or {}
    except Exception:
        return {}


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"events": {}, "people": {}, "companies": {}, "overrides": {}, "ratings": [], "reviews": []}


def save_state(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1) + "\n")


def read_json(arg):
    return json.load(sys.stdin if arg in (None, "-") else open(arg))


def brief_id(ev):
    return f"{ev['date']}-{hashlib.sha1(str(ev.get('eventId') or ev.get('title')).encode()).hexdigest()[:8]}"


def fingerprint(ev):
    key = [ev.get("date"), ev.get("start"), ev.get("end"), (ev.get("title") or "").strip(),
           sorted(a.lower() for a in (ev.get("attendees") or []) if a), bool(ev.get("cancelled"))]
    return hashlib.sha1(json.dumps(key).encode()).hexdigest()[:12]


def key_of(x):
    return re.sub(r"[^a-z0-9@.]+", " ", str(x or "").lower()).strip()


# ---------------------------------------------------------------- diff

def diff(events):
    st = load_state()["events"]
    out = {"new": [], "changed": [], "same": [], "gone": []}
    seen = set()
    for ev in events:
        bid = brief_id(ev)
        seen.add(bid)
        old = st.get(bid)
        row = {"id": bid, **ev}
        if not old:
            out["new"].append(row)
        elif old.get("fp") != fingerprint(ev):
            what = []
            if (old.get("start"), old.get("end"), old.get("date")) != (ev.get("start"), ev.get("end"), ev.get("date")):
                what.append("time")
            if sorted(old.get("attendees") or []) != sorted(a.lower() for a in ev.get("attendees") or []):
                what.append("attendees")
            if ev.get("cancelled"):
                what.append("cancelled")
            out["changed"].append({**row, "what": what or ["details"], "was": {k: old.get(k) for k in ("start", "end", "title")}})
        else:
            out["same"].append({"id": bid, "title": ev.get("title"), "depth": old.get("depth")})
    dates = {ev["date"] for ev in events}
    out["gone"] = [{"id": k, "title": v.get("title"), "date": v.get("date")} for k, v in st.items()
                   if v.get("date") in dates and k not in seen and v.get("status") != "cancelled"]
    return out


# ---------------------------------------------------------------- check

def refs(x):
    """Every source number cited anywhere inside a section."""
    found = set()
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "src":
                found |= {int(n) for n in (v if isinstance(v, list) else [v])}
            else:
                found |= refs(v)
    elif isinstance(x, list):
        for v in x:
            found |= refs(v)
    return found


def check(briefs):
    errs, warns = [], []
    cap = int(settings().get("max_full_per_day", 5))
    per_day = {}
    for b in briefs:
        name = f"{b.get('date')} {b.get('start')} {b.get('title')!r}"
        for f in ("date", "start", "title", "kind", "depth", "eventId"):
            if not b.get(f):
                errs.append(f"{name}: missing {f}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(b.get("date", ""))):
            errs.append(f"{name}: date must be YYYY-MM-DD")
        if not re.fullmatch(r"\d{2}:\d{2}", str(b.get("start", ""))):
            errs.append(f"{name}: start must be HH:MM (Boston, 24h)")
        if b.get("kind") not in KINDS:
            errs.append(f"{name}: kind must be one of {', '.join(KINDS)}")
        if b.get("depth") not in DEPTHS:
            errs.append(f"{name}: depth must be one of {', '.join(DEPTHS)}")
        if b.get("status") and b["status"] not in STATUSES:
            errs.append(f"{name}: status must be one of {', '.join(STATUSES)}")
        if b.get("depth") == "full":
            per_day[b.get("date")] = per_day.get(b.get("date"), 0) + 1
        if b.get("depth") == "none":
            if b.get("sections"):
                errs.append(f"{name}: a 'none' brief has no sections")
            continue
        if b.get("status") in ("preparing",):
            continue
        sixty = b.get("sixty") or {}
        for k in ("who", "goal"):
            if not sixty.get(k) and b.get("depth") != "event":
                errs.append(f"{name}: the 60-second version needs '{k}'")
        for k, v in sixty.items():
            if k not in SIXTY:
                errs.append(f"{name}: unknown 60-second line '{k}' (use {', '.join(SIXTY)})")
            elif len(str(v)) > 260:
                warns.append(f"{name}: 60-second '{k}' is {len(str(v))} characters; keep it to one line")
        nums = {int(s.get("n")) for s in b.get("sources") or [] if s.get("n") is not None}
        for s in b.get("sources") or []:
            if s.get("url") and not str(s["url"]).startswith("http"):
                errs.append(f"{name}: source {s.get('n')} needs a full http(s) link")
            if not s.get("url") and not s.get("mine"):
                errs.append(f"{name}: source {s.get('n')} has no link (mark your own data with \"mine\": true)")
        missing = refs(b.get("sections") or []) | refs(b.get("sixty") or {})
        missing -= nums
        if missing:
            errs.append(f"{name}: cites source(s) {sorted(missing)} that aren't in sources")
        people = b.get("people") or []
        if people and all(p.get("match") == "unsure" for p in people) and any(s.get("key") == "person" for s in b.get("sections") or []):
            errs.append(f"{name}: nobody is matched, so there can't be a person section (7d)")
        for p in people:
            if p.get("match") == "matched" and not p.get("matchedBy"):
                errs.append(f"{name}: {p.get('name')} is matched but 'matchedBy' doesn't say how (two signals, 7d)")
        keys = [s.get("key") for s in b.get("sections") or []]
        if b.get("depth") in ("full", "light") and "questions" not in keys:
            errs.append(f"{name}: a {b['depth']} brief needs questions")
        intro = next((s for s in b.get("sections") or [] if s.get("key") == "intro"), None)
        if intro and re.search(r"—|–| - ", intro.get("text", "")):
            errs.append(f"{name}: the intro is in Aman's voice: no dashes (config/email-voice.md)")
        listen = b.get("listen")
        if b.get("depth") == "full" and not (listen or {}).get("topic"):
            warns.append(f"{name}: no listen topic, so the morning podcasts can't prep Aman for this one (D-055)")
        if listen:
            topic = str(listen.get("topic") or "")
            if not topic:
                errs.append(f"{name}: 'listen' needs a 'topic'")
            # the topic goes to NotebookLM (Google): public subject only, never the person (D-055)
            names = {w for p in people for w in re.split(r"[\s.,]+", str(p.get("name") or "")) if len(w) > 2}
            hit = [w for w in names if re.search(rf"\b{re.escape(w)}\b", topic, re.I)]
            if hit:
                errs.append(f"{name}: the listen topic names {', '.join(hit)}; it goes to NotebookLM, so keep it to the public subject")
            if len(topic) > 140:
                warns.append(f"{name}: listen topic is {len(topic)} characters; one plain question is enough")
    for d, n in per_day.items():
        if n > cap:
            errs.append(f"{d}: {n} full briefs, more than the cap of {cap} (make the rest light)")
    return errs, warns


# ---------------------------------------------------------------- save

def md_day(day, briefs):
    n = sum(1 for b in briefs if b.get("depth") != "none")
    lines = [f"# Meeting briefs · {day}", "", f"*{n} brief{'' if n == 1 else 's'} · built by the brief skill · "
             "sources are numbered under each brief*", ""]
    for b in sorted(briefs, key=lambda x: x.get("start") or ""):
        head = f"## {b.get('start')}–{b.get('end') or '?'} · {b.get('title')}"
        lines += [head, f"*{KINDS.get(b.get('kind'), b.get('kind'))} · {b.get('depth')} · {b.get('where') or ''}*"]
        if b.get("depth") == "none":
            lines += ["", "No brief needed.", ""]
            continue
        for k in ("alert", "clash", "cameAbout"):
            if b.get(k):
                lines.append(f"> {b[k]}")
        for p in b.get("people") or []:
            lines.append(f"- **{p.get('name')}** · {p.get('title') or ''} {p.get('org') or ''} · "
                         + (f"matched ({p.get('matchedBy')})" if p.get("match") == "matched" else "not sure who this is"))
        s = b.get("sixty") or {}
        if (b.get("listen") or {}).get("topic"):
            lines.append(f"- 🎧 Prep listen: {b['listen']['topic']}")
        if s:
            lines += ["", "**The 60-second version**"] + [f"{i + 1}. **{k.title()}:** {s[k]}" for i, k in enumerate([k for k in SIXTY if s.get(k)])]
        for sec in b.get("sections") or []:
            lines += ["", f"**{sec.get('title') or sec.get('key')}**"]
            if sec.get("text"):
                lines.append(sec["text"])
            for r in sec.get("rows") or []:
                lines.append(f"- **{r.get('label')}:** {r.get('text')}" + cite(r))
            for it in sec.get("items") or []:
                lines.append(f"- {'★ ' if it.get('star') else ''}{it.get('text')}" + (f" *({it['why']})*" if it.get("why") else "") + cite(it))
        if b.get("sources"):
            lines += ["", "**Sources**"] + [f"[{s.get('n')}] {s.get('title')}" + (f" · {s['date']}" if s.get("date") else "")
                                            + (f" · {s['url']}" if s.get("url") else " · your data") for s in b["sources"]]
        lines.append("")
    return "\n".join(lines) + "\n"


def cite(x):
    src = x.get("src")
    if not src:
        return ""
    return " " + "".join(f"[{n}]" for n in (src if isinstance(src, list) else [src]))


def save(briefs, push=True):
    errs, warns = check(briefs)
    if errs:
        sys.exit("Not saved. Fix these first:\n  " + "\n  ".join(errs))
    DIR.mkdir(parents=True, exist_ok=True)
    st = load_state()
    stamp = now()
    by_day = {}
    for b in briefs:
        b = dict(b)
        b["id"] = b.get("id") or brief_id(b)
        b["kindLabel"] = KINDS.get(b["kind"], b["kind"])
        b["status"] = b.get("status") or ("none" if b["depth"] == "none" else "ready")
        b["updatedAt"] = stamp
        if b["depth"] != "none":
            b["researchedAt"] = b.get("researchedAt") or stamp
        b["fp"] = fingerprint(b)
        by_day.setdefault(b["date"], []).append(b)
    saved = []
    for day, items in by_day.items():
        path = DIR / f"{day}.json"
        cur = {x["id"]: x for x in json.loads(path.read_text())} if path.exists() else {}
        for b in items:
            b["createdAt"] = (cur.get(b["id"]) or {}).get("createdAt") or stamp
            cur[b["id"]] = b
            saved.append(b)
        allb = sorted(cur.values(), key=lambda x: x.get("start") or "")
        path.write_text(json.dumps(allb, ensure_ascii=False, indent=1) + "\n")
        (DIR / f"{day}.md").write_text(md_day(day, allb))
    for b in saved:
        st["events"][b["id"]] = {"fp": b["fp"], "date": b["date"], "start": b.get("start"), "end": b.get("end"), "title": b.get("title"),
                                 "attendees": sorted(a.lower() for a in b.get("attendees") or []), "kind": b["kind"],
                                 "depth": b["depth"], "status": b["status"], "researchedAt": b.get("researchedAt")}
        sec = {s.get("key"): s for s in b.get("sections") or []}
        if b["depth"] == "none":
            continue
        for p in b.get("people") or []:
            if p.get("match") != "matched" or "person" not in sec:
                continue
            k = key_of(p.get("email") or p.get("name"))
            st["people"][k] = {"name": p.get("name"), "email": p.get("email"), "org": p.get("org"), "title": p.get("title"),
                               "rows": sec["person"].get("rows") or [], "researchedAt": b["researchedAt"], "briefId": b["id"],
                               "sources": b.get("sources") or []}
        if b.get("company") and "company" in sec:
            st["companies"][key_of(b["company"])] = {"name": b["company"], "rows": sec["company"].get("rows") or [],
                                                     "researchedAt": b["researchedAt"], "briefId": b["id"], "sources": b.get("sources") or []}
    save_state(st)
    if push:
        load_to_app(saved)
    for w in warns:
        print("note:", w)
    print(f"Saved {len(saved)} brief(s) for {', '.join(sorted(by_day))}" + (" and loaded them into the app." if push else " (not loaded into the app)."))


def load_to_app(saved):
    import webdb
    writes = []
    for b in saved:
        old = app_brief(b["id"]) or {}
        keep = {k: old[k] for k in APP_FIELDS if k in old}
        if keep.get("requestState") in ("asked", "working"):
            keep.update(requestState="done", requestDoneAt=now())
        data = {k: v for k, v in b.items() if k != "id"}
        data.update(keep)
        writes.append({"op": "set", "collection": "briefs", "doc_id": b["id"], "data": data})
    if writes:
        webdb.push(writes)


# ---------------------------------------------------------------- profiles, requests, learning

def profile(q):
    st, k = load_state(), key_of(q)
    days = int(settings().get("reuse_profile_days", 30))
    hits = []
    for kind in ("people", "companies"):
        for key, v in st[kind].items():
            if k and (k == key or k in key or k in key_of(v.get("name")) or k == key_of(v.get("org"))):
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(v["researchedAt"].replace("Z", "+00:00"))).days
                hits.append({"kind": "person" if kind == "people" else "company", "ageDays": age, "reuse": age < days, **v})
    return hits


def requests():
    import webdb
    return [{k: r.get(k) for k in ("id", "date", "start", "title", "eventId", "request", "requestedAt", "requestNote", "depth", "kind")}
            for r in webdb.get("briefs", ["requestState=asked"])]


def app_brief(i):
    import webdb
    rows = webdb.call("GET", f"/rest/v1/docs?select=id,data&collection=eq.briefs&id=eq.{webdb.q(i)}") or []
    return rows[0]["data"] if rows else None


def set_request(ids, **fields):
    import webdb
    for i in ids:
        cur = app_brief(i)
        if cur is None:
            print(f"no brief {i}")
            continue
        webdb.push([{"op": "set", "collection": "briefs", "doc_id": i, "data": {**cur, **fields}}])


def sync():
    """Aman's taps in the app → lists/briefs-state.json (ratings, kind changes, person picks)."""
    import webdb
    st = load_state()
    rows = webdb.call("GET", "/rest/v1/docs?select=id,data&collection=eq.briefs") or []
    seen = {(r["id"], r["at"]) for r in st["ratings"]}
    n_r = n_k = 0
    for r in rows:
        d = r["data"]
        if d.get("rating") and (r["id"], d.get("ratedAt")) not in seen:
            st["ratings"].append({"id": r["id"], "at": d.get("ratedAt"), "rating": d["rating"], "kind": d.get("kindSet") or d.get("kind"),
                                  "depth": d.get("depth"), "title": d.get("title")})
            n_r += 1
        if d.get("kindSet") and d.get("kindSet") != d.get("kind"):
            for p in d.get("people") or []:
                for k in filter(None, (p.get("email"), )):
                    if st["overrides"].get(key_of(k)) != d["kindSet"]:
                        st["overrides"][key_of(k)] = d["kindSet"]
                        n_k += 1
            tkey = "title:" + key_of(re.sub(r"\d+", "", d.get("title") or ""))
            if st["overrides"].get(tkey) != d["kindSet"]:
                st["overrides"][tkey] = d["kindSet"]
                n_k += 1
        for idx, pick in (d.get("picks") or {}).items():
            st.setdefault("picks", {})[f"{r['id']}:{idx}"] = pick
    save_state(st)
    print(f"Synced {n_r} new rating(s), {n_k} kind change(s). Overrides: {len(st['overrides'])}.")


def report(days):
    st = load_state()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    evs = [v for v in st["events"].values() if (v.get("researchedAt") or "") >= since and v.get("depth") != "none"]
    rts = [r for r in st["ratings"] if (r.get("at") or "") >= since]
    by = {}
    for r in rts:
        by.setdefault(r["rating"], 0)
        by[r["rating"]] += 1
    kinds = {}
    for r in rts:
        kinds.setdefault(r.get("kind"), {}).setdefault(r["rating"], 0)
        kinds[r.get("kind")][r["rating"]] += 1
    return {"days": days, "briefs": len(evs), "byDepth": {d: sum(1 for v in evs if v.get("depth") == d) for d in DEPTHS if d != "none"},
            "rated": len(rts), "ratings": by, "ratingsByKind": kinds, "useful%": round(100 * by.get("useful", 0) / len(rts)) if rts else None,
            "overrides": len(st["overrides"])}


def cleanup():
    import webdb
    keep = int(settings().get("keep_in_app_days", 90))
    cut = (datetime.now(BOSTON).date() - timedelta(days=keep)).isoformat()
    rows = webdb.call("GET", "/rest/v1/docs?select=id,data&collection=eq.briefs") or []
    old = [{"op": "delete", "collection": "briefs", "doc_id": r["id"]} for r in rows if (r["data"].get("date") or "9") < cut]
    if old:
        webdb.push(old)
    print(f"Removed {len(old)} brief(s) older than {cut} from the app (kept in lists/briefs/).")


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd, rest = argv[1], argv[2:]
    if cmd == "diff":
        print(json.dumps(diff(read_json(rest[0] if rest else None)), ensure_ascii=False, indent=1))
    elif cmd == "check":
        errs, warns = check(read_json(rest[0] if rest else None))
        for w in warns:
            print("note:", w)
        if errs:
            sys.exit("✗ " + "\n✗ ".join(errs))
        print("✓ briefs look right")
    elif cmd == "save":
        save(read_json(rest[0] if rest and rest[0] != "--no-push" else None), push="--no-push" not in rest)
    elif cmd == "profile":
        print(json.dumps(profile(" ".join(rest)), ensure_ascii=False, indent=1))
    elif cmd == "requests":
        print(json.dumps(requests(), ensure_ascii=False, indent=1))
    elif cmd == "working":
        set_request(rest, requestState="working")
    elif cmd == "fail":
        set_request(rest[:1], requestState="failed", requestNote=rest[1] if len(rest) > 1 else "Couldn't make this brief")
    elif cmd == "sync":
        sync()
    elif cmd == "report":
        print(json.dumps(report(int(rest[rest.index("--days") + 1]) if "--days" in rest else 7), indent=1))
    elif cmd == "cleanup":
        cleanup()
    elif cmd == "show":
        p = DIR / f"{rest[0]}.json"
        print(md_day(rest[0], json.loads(p.read_text())) if p.exists() else f"No briefs for {rest[0]}.")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
