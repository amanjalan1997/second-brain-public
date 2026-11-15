"""Ghostwriter's learning loop: compare what Claude drafted with what Aman actually sent, and sum it up.

  python3 scripts/email_learn.py draft <id> <file> --type T --audience A [--to NAME] [--draft-id D]
        save Claude's first version of an email (HTML or text) before Aman sees it
  python3 scripts/email_learn.py sent <id> <file> [--how claude|outlook|app]
        save what actually went out (HTML or text, quoted history is cut off) and score the edits
  python3 scripts/email_learn.py feedback <id|general> "<what Aman said, <=12 words>"
  python3 scripts/email_learn.py discarded <id>      the draft was dropped (deleted, or Aman wrote his own)
  python3 scripts/email_learn.py blind <s1,s2,...> [--note T]   log a blind-test round ("sounds like me" 1-5 each)
  python3 scripts/email_learn.py lint <file>        check a draft (HTML or text) for AI tells before Aman sees it
  python3 scripts/email_learn.py report [--days 30]  numbers for the weekly review (JSON)
  python3 scripts/email_learn.py pairs [--since YYYY-MM-DD]     list local draft/sent files to read in the review
  python3 scripts/email_learn.py reviewed [--version N] [--note T]  mark a weekly review as done

<id> is any short key for the email, normally the tracker thread id plus a date ("casey-acme-1026-1103").
Types: outreach, thank-you, scheduling, follow-up, intro-ask, intro-reply, apology, admin, club, quick.
Audiences: professor, founder-investor, alumni-recruiter, peer, admin, company.

Privacy (CLAUDE.md rule 5): email text is stored only on this Mac, in email_writer.learning.private_dir
(default ~/.second-brain/ghostwriter). The repo file lists/email-learning.json gets numbers, flags and
Aman's short feedback lines only.
"""
import argparse
import difflib
import html
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "lists/email-learning.json"
TRACKER = ROOT / "lists/email-state.json"
BOSTON = ZoneInfo("America/New_York")
TYPES = ("outreach", "thank-you", "scheduling", "follow-up", "intro-ask", "intro-reply", "apology", "admin",
         "club", "quick")
AUDIENCES = ("professor", "founder-investor", "alumni-recruiter", "peer", "admin", "company")
# Where quoted history or app signatures start in a sent email
CUT = re.compile(r"^(From: |-----Original Message|_{10,}|Get Outlook for|Sent from my|On .+ wrote:$)", re.M)
LONG_DASH = "—"
# Things Aman never writes (config/email-voice.md, "Never write"); lint blocks these in drafts
BANNED = ["—", "–", "--", " - ", "hope this email finds you", "i wanted to reach out", "delve", "leverage",
          "furthermore", "additionally", "moreover", "i'd be thrilled", "excited to connect", "touch base",
          "circle back", "circling back", "synergy", "at your earliest convenience", "don't hesitate to",
          "thanks in advance", "great question", "bumping this", "in case it got buried", "gentle reminder",
          "looking forward to hearing from you", "best regards", "kind regards", "warm regards", "hi there"]


def settings():
    s = yaml.safe_load((ROOT / "config/settings.yaml").read_text())["email_writer"]
    return s.get("learning", {})


def private_dir():
    d = Path(settings().get("private_dir", "~/.second-brain/ghostwriter")).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def now():
    return datetime.now(BOSTON).isoformat(timespec="minutes")


def load():
    if LOG.exists():
        return json.loads(LOG.read_text())
    return {"emails": {}, "feedback": [], "blind_tests": [], "reviews": []}


def save(log):
    LOG.write_text(json.dumps(log, indent=1, ensure_ascii=False) + "\n")


def to_text(raw):
    """HTML or text -> Aman's own words: tags stripped, quoted history and app signatures cut off."""
    if "<" in raw and ">" in raw:
        raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
        raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", raw)
        raw = re.sub(r"(?i)<hr[^>]*>", "\n__________\n", raw)
        raw = html.unescape(re.sub(r"<[^>]+>", "", raw))
    raw = raw.replace("\r", "").replace("\xa0", " ")
    m = CUT.search(raw)
    if m:
        raw = raw[:m.start()]
    lines = [l.strip() for l in raw.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def words(t):
    return re.findall(r"[\w'’]+|[^\w\s]", t)


def lines_of(t):
    return [l for l in t.split("\n") if l.strip()]


def first_line(t):
    ls = lines_of(t)
    return ls[0] if ls else ""


def signoff(t):
    ls = lines_of(t)
    for i in range(len(ls) - 1, -1, -1):
        if re.match(r"^(Best|Thanks|Thank you|Regards|Cheers)\b", ls[i]):
            return ls[i]
    return ""


def sentences(t):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", t) if len(s.strip()) > 2]


def compare(a, b):
    """Edit numbers between Claude's draft a and the sent text b (no text is returned)."""
    wa, wb = words(a), words(b)
    sm = difflib.SequenceMatcher(a=[w.lower() for w in wa], b=[w.lower() for w in wb], autojunk=False)
    changed = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    ratio = round(min(changed / max(len(wa), len(wb), 1), 1.0), 3)  # share of words changed, 0-1
    sa, sb = set(sentences(a)), set(sentences(b))
    count = lambda t: len(re.findall(r"[\w'’]+", t))
    flags = []
    if first_line(a) != first_line(b):
        flags.append("opening changed")
    if signoff(a) != signoff(b):
        flags.append("sign-off changed")
    if count(b) < count(a) * 0.8:
        flags.append("made shorter")
    if count(b) > count(a) * 1.2:
        flags.append("made longer")
    if a.count("!") != b.count("!"):
        flags.append("exclamations " + ("added" if b.count("!") > a.count("!") else "removed"))
    if LONG_DASH in a:
        flags.append("draft had a long dash")
    return {"words_draft": count(a), "words_sent": count(b), "edit_ratio": ratio,
            "light_edit": ratio < settings().get("light_edit_below", 0.10), "unchanged": ratio == 0,
            "sentences_removed": len(sa - sb), "sentences_added": len(sb - sa), "flags": flags}


def cmd_draft(log, a):
    assert a.type in TYPES, f"type must be one of {TYPES}"
    assert a.audience in AUDIENCES, f"audience must be one of {AUDIENCES}"
    text = to_text(Path(a.file).read_text())
    d = private_dir() / a.id
    d.mkdir(exist_ok=True)
    (d / "draft.txt").write_text(text + "\n")
    e = log["emails"].setdefault(a.id, {})
    e.update({"type": a.type, "audience": a.audience, "to": a.to or "", "draftId": a.draft_id,
              "drafted": now(), "status": "drafted"})
    print(json.dumps({"saved": str(d / "draft.txt"), "words": e.get("words_draft") or len(text.split())}))


def cmd_sent(log, a):
    e = log["emails"].get(a.id)
    if not e:
        sys.exit(f"no draft recorded for {a.id}")
    d = private_dir() / a.id
    sent = to_text(Path(a.file).read_text())
    (d / "sent.txt").write_text(sent + "\n")
    draft = (d / "draft.txt").read_text().strip()
    e.update(compare(draft, sent))
    e.update({"sent": now(), "status": "sent", "sent_by": a.how})
    diff = "\n".join(difflib.unified_diff(draft.split("\n"), sent.split("\n"), "claude", "aman", lineterm=""))
    (d / "diff.txt").write_text(diff + "\n")
    print(json.dumps({k: e[k] for k in ("edit_ratio", "light_edit", "words_draft", "words_sent", "flags")}))


def summarise(rows):
    if not rows:
        return {"count": 0}
    r = [e["edit_ratio"] for e in rows]
    return {"count": len(rows), "light_or_no_edits": f"{sum(e['light_edit'] for e in rows)}/{len(rows)}",
            "unchanged": sum(e["unchanged"] for e in rows), "median_edit": round(median(r), 3),
            "avg_edit": round(mean(r), 3)}


def cmd_report(log, a):
    since = (date.today() - timedelta(days=a.days)).isoformat()
    emails = [dict(e, id=k) for k, e in log["emails"].items() if (e.get("sent") or e.get("drafted", "")) >= since]
    sent = [e for e in emails if e.get("status") == "sent"]
    by = lambda key: {v: summarise([e for e in sent if e[key] == v]) for v in sorted({e[key] for e in sent})}
    flags = {}
    for e in sent:
        for f in e.get("flags", []):
            flags[f] = flags.get(f, 0) + 1
    out = {"window_days": a.days, "overall": summarise(sent), "by_type": by("type"), "by_audience": by("audience"),
           "edit_patterns": dict(sorted(flags.items(), key=lambda x: -x[1])),
           "most_edited": [{"id": e["id"], "type": e["type"], "edit_ratio": e["edit_ratio"]}
                           for e in sorted(sent, key=lambda e: -e["edit_ratio"])[:5]],
           "discarded": [e["id"] for e in emails if e.get("status") == "discarded"],
           "waiting_to_compare": [e["id"] for e in emails if e.get("status") == "drafted"],
           "feedback": [f for f in log["feedback"] if f["date"] >= since],
           "blind_tests": log["blind_tests"][-3:],
           "last_review": log["reviews"][-1] if log["reviews"] else None}
    # monthly trend of the main metric
    months = {}
    for e in [x for x in log["emails"].values() if x.get("status") == "sent"]:
        months.setdefault(e["sent"][:7], []).append(e)
    out["trend_by_month"] = {m: summarise(v)["light_or_no_edits"] for m, v in sorted(months.items())}
    # follow-up timing from the tracker
    if TRACKER.exists():
        oc = json.loads(TRACKER.read_text()).get("outcomes", [])
        timing = {}
        for k in sorted({o["kind"] for o in oc}):
            got = [o for o in oc if o["kind"] == k and o.get("replied_on")]
            timing[k] = {"asked": len([o for o in oc if o["kind"] == k]), "replied": len(got),
                         "median_working_days_to_reply": median([o["working_days"] for o in got]) if got else None,
                         "replied_without_nudge": sum(o["nudges"] == 0 for o in got),
                         "replied_after_nudge": sum(o["nudges"] > 0 for o in got),
                         "gone_quiet": sum(bool(o.get("gone_quiet")) for o in oc if o["kind"] == k)}
        out["follow_up_timing"] = timing
    print(json.dumps(out, indent=1, ensure_ascii=False))


def cmd_pairs(log, a):
    base = private_dir()
    rows = []
    for k, e in sorted(log["emails"].items(), key=lambda x: x[1].get("sent", "")):
        if e.get("status") == "sent" and e["sent"][:10] >= (a.since or "0000"):
            rows.append({"id": k, "type": e["type"], "audience": e["audience"], "edit_ratio": e["edit_ratio"],
                         "draft": str(base / k / "draft.txt"), "sent": str(base / k / "sent.txt"),
                         "diff": str(base / k / "diff.txt")})
    print(json.dumps(rows, indent=1))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("draft"); q.add_argument("id"); q.add_argument("file")
    q.add_argument("--type", required=True); q.add_argument("--audience", required=True)
    q.add_argument("--to"); q.add_argument("--draft-id")
    q = sub.add_parser("sent"); q.add_argument("id"); q.add_argument("file")
    q.add_argument("--how", choices=["claude", "outlook", "app"], default="claude")
    q = sub.add_parser("feedback"); q.add_argument("id"); q.add_argument("text")
    sub.add_parser("discarded").add_argument("id")
    q = sub.add_parser("blind"); q.add_argument("scores"); q.add_argument("--note", default="")
    sub.add_parser("report").add_argument("--days", type=int, default=30)
    sub.add_parser("pairs").add_argument("--since")
    sub.add_parser("lint").add_argument("file")
    q = sub.add_parser("reviewed"); q.add_argument("--version"); q.add_argument("--note", default="")
    a = p.parse_args()
    log = load()
    if a.cmd == "draft":
        cmd_draft(log, a)
    elif a.cmd == "sent":
        cmd_sent(log, a)
    elif a.cmd == "feedback":
        log["feedback"].append({"date": now()[:10], "email": a.id, "text": a.text[:120]})
        if a.id in log["emails"]:
            log["emails"][a.id].setdefault("feedback", []).append(a.text[:120])
    elif a.cmd == "discarded":
        log["emails"][a.id]["status"] = "discarded"
    elif a.cmd == "blind":
        s = [float(x) if "." in x else int(x) for x in a.scores.split(",")]
        log["blind_tests"].append({"date": now()[:10], "scores": s, "average": round(mean(s), 2), "note": a.note})
        print(json.dumps(log["blind_tests"][-1]))
    elif a.cmd == "lint":
        t = to_text(Path(a.file).read_text())
        hits = [b for b in BANNED if b in t.lower().replace("’", "'")]
        print(json.dumps({"ok": not hits, "found": hits, "words": len(re.findall(r"[\w'’]+", t)),
                          "exclamations": t.count("!"), "questions": t.count("?")}, ensure_ascii=False))
        sys.exit(1 if hits else 0)
    elif a.cmd == "report":
        cmd_report(log, a)
        return
    elif a.cmd == "pairs":
        cmd_pairs(log, a)
        return
    elif a.cmd == "reviewed":
        log["reviews"].append({"date": now()[:10], "guide_version": a.version, "note": a.note})
    save(log)


if __name__ == "__main__":
    sys.exit(main())
