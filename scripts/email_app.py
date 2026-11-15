"""Ghostwriter in the app (docs/PRD-email-app.md, D-035): put drafts in the web app and keep them in step.

  python3 scripts/email_app.py push <draft.json> [--over-cap]   add or update one draft card (fields below)
  python3 scripts/email_app.py list [--all]                      drafts in the app (id, status, person, Outlook id)
  python3 scripts/email_app.py get <id>                          one draft as JSON
  python3 scripts/email_app.py set <id> key=value ...            change fields, e.g. status=stale "note=New reply from X"
  python3 scripts/email_app.py waiting                           copy the waiting-on list to the app (meta/waiting)
  python3 scripts/email_app.py checked --new N [--note T] [--also file.json] [--failed]
                                                                 record how an inbox check went (meta/inbox_check);
                                                                 unless --failed, also sets last_check in lists/email-state.json
  python3 scripts/email_app.py html <id>                         the draft's text as Outlook HTML
  python3 scripts/email_app.py wipe                              clear the text of drafts sent/deleted 14+ days ago

Draft fields (push): kind (reply|follow-up|thank-you|new|heads-up), person, company, why (one line), priority
(1 = most urgent), to/cc/bcc ([{name, email, source}], source = thread|network|people-search), subject, body (plain
text: blank line between paragraphs, **bold** for the ask), replyTo ({from, when, gist <=15 words}), also (list of
"Also on send" lines), flags, sensitive, calendar, meeting ({start: "YYYY-MM-DDTHH:MM" Boston, minutes}), invite
({subject, start, minutes, attendees, teams}), tracker ({action: add|waiting|nudged|close, thread, kind, ask}),
learnKey, threadId, callId, outlookDraftId, replyToMessageId, conversationId, outlookLink, hasAttachments.
Optional: id (else <first-name>-<company>-<MMDD>).

"Set up invite" (docs/PRD-invites.md): a draft about meeting also gets `schedule`:
  {kind: offer | accept | confirmed, options: [{start: "YYYY-MM-DDTHH:MM" Boston, text, free, their}] (from
  email_slots.py offer/times; the first is the suggested one), minutes, teams (bool), place ("" for Teams, else where),
  inPerson (bool, off campus = travel buffer), title, note (one line for the invite), attendees ([{name, email, source}]),
  theirTz, inviteBody (the reply for "invite + email", with {{time}} and {{where}} where those go)}.
Kind `invite` = they confirmed a time and no reply is needed: schedule (kind confirmed) and optionally a short reply
(subject, body, outlookDraftId) Aman can switch on. The app writes inviteChoice ({start, minutes, teams, place, title,
note, attendees, withEmail}), preInvite ({subject, body} before the invite text replaced them) and approved.invite;
the courier writes inviteSent ({start, end, eventId, link, at}) and status invited (invite only) or sends the email next.

Statuses: ready -> (Aman taps Send) approved -> (courier) sending -> sent | failed; ready -> (Aman deletes) delete ->
(courier) deleted; ready -> (Set up invite) approved -> (courier) inviting -> invited (invite only) or approved again
for the email -> sent; stale = something changed (new reply, edited in Outlook), review again; sent-outlook = he sent it
from Outlook himself. The app writes only: body, subject, version, editedByAman, approved, status approved/ready/delete,
deleteReason, comment. Everything else comes from Claude.

Privacy (CLAUDE.md rule 5): draft text lives in the app's owner-only database and in Outlook, never in the repo.
Incoming email is never copied, only a <=15-word gist.
"""
import hashlib
import html
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import webdb  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BOSTON = ZoneInfo("America/New_York")
KINDS = ("reply", "follow-up", "thank-you", "new", "heads-up", "invite")
SCHEDULE_KINDS = ("offer", "accept", "confirmed")
SOURCES = ("thread", "network", "people-search")
ACTIVE = ("ready", "approved", "sending", "inviting", "failed", "stale")
MAX_WAITING = 8
WIPE_DAYS = 14


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slug(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def emails(rs):
    return [str(r.get("email", "")).strip().lower() for r in (rs or [])]


def fingerprint(d):
    """SHA-256 of exactly what Aman saw when he tapped Send. app/index.html computes the same thing (canon())."""
    return hashlib.sha256(canon_json(d).encode("utf-8")).hexdigest()


def invite_canon(c):
    """What Aman approved for an invite. app/index.html computes the same thing (inviteCanon())."""
    return [c.get("start") or "", int(c.get("minutes") or 0), bool(c.get("teams")), c.get("place") or "", c.get("title") or "",
            c.get("note") or "", [str(e).strip().lower() for e in c.get("attendees") or []]]


def invite_fingerprint(d):
    """SHA-256 of the invite choice plus, when the email goes too, the email exactly as approved."""
    c = d.get("inviteChoice") or {}
    mail = json.loads(canon_json(d)) if c.get("withEmail") else None
    raw = json.dumps([invite_canon(c), mail], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canon_json(d):
    return json.dumps([emails(d.get("to")), emails(d.get("cc")), emails(d.get("bcc")), d.get("subject") or "", d.get("body") or "",
                       list(d.get("also") or [])], ensure_ascii=False, separators=(",", ":"))


def body_to_html(body):
    """Plain text with blank-line paragraphs and **bold** -> the HTML Outlook drafts use (allowlisted tags only)."""
    paras = [p.strip("\n") for p in re.split(r"\n\s*\n", (body or "").strip()) if p.strip()]
    out = []
    for p in paras:
        h = html.escape(p, quote=False)
        h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h, flags=re.S)
        out.append("<p>" + h.replace("\n", "<br>") + "</p>")
    return "".join(out)


def norm(s):
    """Compare texts loosely: no markup, curly quotes straightened, all whitespace collapsed."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s).replace("**", "")
    s = s.translate({0x2019: "'", 0x2018: "'", 0x201C: '"', 0x201D: '"', 0xA0: " "})
    return re.sub(r"\s+", " ", s).strip()


def get_doc(i):
    rows = webdb.call("GET", f"/rest/v1/docs?select=id,data&collection=eq.drafts&id=eq.{webdb.q(i)}")
    return {"id": rows[0]["id"], **rows[0]["data"]} if rows else None


def all_docs():
    return webdb.get("drafts", [])


def save(i, data):
    data = {k: v for k, v in data.items() if k != "id"}
    webdb.push([{"op": "set", "collection": "drafts", "doc_id": i, "data": data}])


def update(i, **fields):
    d = get_doc(i)
    if not d:
        sys.exit(f"No draft {i} in the app.")
    d.update(fields)
    d["updated"] = now()
    save(i, d)
    return d


def check_draft(d):
    problems = []
    if d.get("kind") not in KINDS:
        problems.append(f"kind must be one of {', '.join(KINDS)}")
    for k in ("person", "why"):
        if not d.get(k):
            problems.append(f"missing {k}")
    if d.get("kind") == "invite" and not d.get("schedule"):
        problems.append("an invite card needs a schedule")
    if d.get("schedule"):
        problems += check_schedule(d)
    if d.get("kind") not in ("heads-up", "invite") or d.get("outlookDraftId"):
        for k in ("subject", "body", "outlookDraftId"):
            if not d.get(k):
                problems.append(f"missing {k}")
        if not d.get("to"):
            problems.append("no recipients")
    for r in (d.get("to") or []) + (d.get("cc") or []) + (d.get("bcc") or []):
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(r.get("email", ""))):
            problems.append(f"bad address {r.get('email')!r}")
        if r.get("source") not in SOURCES:
            problems.append(f"{r.get('email')}: source must be one of {', '.join(SOURCES)} (never guess an address)")
    if "—" in (d.get("body") or "") or "–" in (d.get("body") or ""):
        problems.append("the text has a long or en dash (run email_learn.py lint first)")
    return problems


def check_schedule(d):
    sc, problems = d["schedule"], []
    if sc.get("kind") not in SCHEDULE_KINDS:
        problems.append(f"schedule.kind must be one of {', '.join(SCHEDULE_KINDS)}")
    opts = sc.get("options") or []
    if not opts:
        problems.append("schedule.options is empty (use email_slots.py offer or times)")
    for o in opts:
        try:
            when = datetime.fromisoformat(o.get("start", "")).replace(tzinfo=BOSTON)
        except ValueError:
            problems.append(f"schedule option start {o.get('start')!r} isn't YYYY-MM-DDTHH:MM")
            continue
        if not o.get("text"):
            problems.append(f"schedule option {o['start']} has no text")
        if when < datetime.now(BOSTON):
            problems.append(f"schedule option {o['start']} is in the past")
    if not isinstance(sc.get("minutes"), int) or not 10 <= sc["minutes"] <= 180:
        problems.append("schedule.minutes must be a whole number of minutes (10 to 180)")
    if not sc.get("title"):
        problems.append("schedule.title is missing")
    if not sc.get("teams") and not sc.get("place"):
        problems.append("schedule needs teams: true or a place")
    if not sc.get("attendees"):
        problems.append("schedule.attendees is empty")
    for r in sc.get("attendees") or []:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(r.get("email", ""))):
            problems.append(f"bad attendee address {r.get('email')!r}")
        if r.get("source") not in SOURCES:
            problems.append(f"attendee {r.get('email')}: source must be one of {', '.join(SOURCES)} (never guess an address)")
    if d.get("kind") != "invite" and "{{time}}" not in (sc.get("inviteBody") or ""):
        problems.append("schedule.inviteBody needs {{time}} where the chosen time goes")
    for k in ("inviteBody", "note", "title"):
        if "—" in (sc.get(k) or "") or "–" in (sc.get(k) or ""):
            problems.append(f"schedule.{k} has a long or en dash")
    return problems


def push(path, over_cap=False):
    d = json.loads(Path(path).read_text())
    problems = check_draft(d)
    if problems:
        sys.exit("Not added: " + "; ".join(problems))
    i = d.pop("id", None) or slug(f"{d['person'].split()[0]}-{d.get('company', '')}-{datetime.now(BOSTON):%m%d}")
    old = get_doc(i)
    if old and (old.get("status") in ("approved", "sending", "inviting", "sent", "sent-outlook", "invited") or old.get("inviteSent")):
        sys.exit(f"Not changed: {i} is {old['status']} in the app.")
    waiting = [x for x in all_docs() if x.get("status") in ACTIVE and x["id"] != i]
    if not old and len(waiting) >= MAX_WAITING and not over_cap:
        print(json.dumps({"added": False, "id": i, "reason": f"{len(waiting)} drafts already waiting (cap {MAX_WAITING}); "
                          "list it under 'Also worth a reply' instead"}))
        sys.exit(3)
    people = set(webdb.ids_in("people"))
    d.setdefault("personId", slug(d["person"]) if slug(d["person"]) in people else None)
    d.update(status="ready", version=1, editedByAman=False, approved=None, note=d.get("note", ""),
             created=(old or {}).get("created") or now(), updated=now(),
             synced={"subject": d.get("subject", ""), "body": d.get("body", "")})
    if old and old.get("editedByAman") and old.get("status") in ("ready", "failed", "stale"):
        # keep Aman's own wording; just say what changed underneath it
        d.update(body=old["body"], subject=old["subject"], version=old.get("version", 1), editedByAman=True,
                 note="Claude updated this draft; your edits are kept.")
    save(i, d)
    print(json.dumps({"added": True, "id": i, "status": "ready", "updated_existing": bool(old)}))


def push_waiting():
    st = json.loads((ROOT / "lists/email-state.json").read_text())
    keep = ("id", "person", "company", "subject", "ask", "kind", "sent", "status", "nudges", "next_nudge", "draftId")
    threads = [{k: t.get(k) for k in keep} for t in st.get("threads", []) if t.get("status") in ("waiting", "replied", "gone-quiet")]
    doc = {"threads": threads, "updated": now(), "lastCheck": st.get("last_check")}
    webdb.push([{"op": "set", "collection": "meta", "doc_id": "waiting", "data": doc}])
    print(f"Waiting-on list in the app: {len(threads)} threads.")


def checked(new, note="", also=None, failed=False):
    rows = webdb.call("GET", "/rest/v1/docs?select=data&collection=eq.meta&id=eq.inbox_check")
    cur = rows[0]["data"] if rows else {}
    cur.update(status="failed" if failed else "done", finished=now(), newDrafts=int(new), note=note)
    if also is not None:
        cur["also"] = json.loads(Path(also).read_text())
    webdb.push([{"op": "set", "collection": "meta", "doc_id": "inbox_check", "data": cur}])
    if not failed:  # the next check reads email from here on (lists/email-state.json last_check, Boston time)
        sp = ROOT / "lists/email-state.json"
        st = json.loads(sp.read_text())
        st["last_check"] = datetime.now(BOSTON).isoformat(timespec="minutes")
        sp.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n")
        subprocess.run([sys.executable, str(ROOT / "scripts/email_tracker.py"), "render"], cwd=ROOT, capture_output=True)
    print(f"Inbox check recorded: {'failed' if failed else 'done'}, {new} new drafts.")


def wipe():
    cut = datetime.now(timezone.utc) - timedelta(days=WIPE_DAYS)
    n = 0
    for d in all_docs():
        when = d.get("sentAt") or d.get("updated") or ""
        if d.get("status") in ("sent", "sent-outlook", "invited", "deleted") and d.get("body") and when and \
                datetime.fromisoformat(when.replace("Z", "+00:00")) < cut:
            d.update(body="", synced=None, outlookBody=None, wiped=now())
            save(d["id"], d)
            n += 1
    print(f"Wiped the text of {n} old drafts.")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "push":
        push(rest[0], over_cap="--over-cap" in rest)
    elif cmd == "list":
        for d in sorted(all_docs(), key=lambda x: (x.get("status") not in ACTIVE, x.get("priority", 9))):
            if "--all" in rest or d.get("status") in ACTIVE + ("delete",):
                print(f"{d['id']:40} {d.get('status', ''):12} {d.get('kind', ''):10} {d.get('person', '')} · "
                      f"outlook {str(d.get('outlookDraftId') or '-')[-12:]}{' · ' + d['note'] if d.get('note') else ''}")
    elif cmd == "get":
        print(json.dumps(get_doc(rest[0]), ensure_ascii=False, indent=1))
    elif cmd == "set":
        fields = {}
        for kv in rest[1:]:
            k, _, v = kv.partition("=")
            fields[k] = None if v == "null" else v
        update(rest[0], **fields)
        print(f"Updated {rest[0]}.")
    elif cmd == "waiting":
        push_waiting()
    elif cmd == "checked":
        opt = lambda f: rest[rest.index(f) + 1] if f in rest else None  # noqa: E731
        checked(opt("--new") or 0, opt("--note") or "", opt("--also"), "--failed" in rest)
    elif cmd == "html":
        print(body_to_html((get_doc(rest[0]) or {}).get("body", "")))
    elif cmd == "wipe":
        wipe()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
