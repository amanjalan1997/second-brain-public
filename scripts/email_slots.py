"""Find Aman's free meeting times (Boston time) from his Outlook calendar, for Ghostwriter scheduling replies.

  python3 scripts/email_slots.py offer <events_file> [--from YYYY-MM-DD] [--minutes 30] [--count 3]
                                  [--in-person] [--their-tz America/Los_Angeles]
  python3 scripts/email_slots.py check <events_file> 2026-11-05T12:30 [--minutes 30] [--in-person]
  python3 scripts/email_slots.py times <events_file> 2026-11-05T12:30 [2026-11-06T14:00 ...] [--minutes 30] [--in-person]
                                  [--their-tz America/Los_Angeles]

<events_file> holds the raw output of outlook_calendar_search (one or more pages pasted together; JSON objects
back to back or a JSON array both work). Outlook returns wall-clock times in the mailbox zone (India Standard
Time for Aman), so every time is converted to Boston here, never by hand.

offer: prints JSON {slots: [{day, start, end, text}], text, skipped, options} where text is in Aman's style
       ("Thurs 11/5, 12-1pm"). One window per day, earliest days first, up to --count days. options are the same
       slots as exact meeting times for the app's "Set up invite" panel (docs/PRD-invites.md):
       [{start: "YYYY-MM-DDTHH:MM" Boston, text: "Thurs 11/5, 12:30pm", free: true, their: "9:30am PT" or absent}].
check: prints JSON {free: bool, clashes: [{subject, start, end}]} for one proposed time (Boston time),
       counting the buffer around other events.
times: the invite panel's options for times they proposed: [{start, text, free, their}], free ones first, in the
       order given (a taken time is kept with free: false so Aman can see why it wasn't picked).

Rules come from config/settings.yaml -> email_writer.meetings (hours, days, buffers, look-ahead).
Busy = any event that isn't cancelled, all-day, or matched by not_busy_if_subject_has.
"""
import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
BOSTON = ZoneInfo("America/New_York")
# Windows zone names Outlook uses -> IANA
WINDOWS_TZ = {
    "India Standard Time": "Asia/Kolkata",
    "UTC": "UTC",
    "Coordinated Universal Time": "UTC",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "Pacific Standard Time": "America/Los_Angeles",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Singapore Standard Time": "Asia/Singapore",
}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
AMAN_DAY = {"Tue": "Tues", "Thu": "Thurs"}  # how Aman abbreviates them
TZ_LABEL = {"America/Los_Angeles": "PT", "America/Denver": "MT", "America/Chicago": "CT",
            "America/New_York": "ET", "Europe/London": "UK", "Asia/Kolkata": "IST"}


def settings():
    return yaml.safe_load((ROOT / "config/settings.yaml").read_text())["email_writer"]["meetings"]


def load_events(path):
    """Parse back-to-back JSON objects or an array; keep calendar events only."""
    raw = Path(path).read_text().strip()
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(raw):
        while i < len(raw) and raw[i] in " \r\n\t,":
            i += 1
        if i >= len(raw):
            break
        obj, i = dec.raw_decode(raw, i)
        out.extend(obj if isinstance(obj, list) else [obj])
    return [e for e in out if isinstance(e, dict) and "start" in e]


def to_boston(dt_obj):
    tz = dt_obj.get("timeZone") or "UTC"
    zone = ZoneInfo(WINDOWS_TZ.get(tz, tz))
    naive = datetime.fromisoformat(dt_obj["dateTime"][:19])
    return naive.replace(tzinfo=zone).astimezone(BOSTON)


def busy_blocks(events, cfg, in_person):
    skip = [s.lower() for s in cfg.get("not_busy_if_subject_has", [])]
    pad = timedelta(minutes=cfg["travel_buffer_minutes"] if in_person else cfg["buffer_minutes"])
    blocks = []
    for e in events:
        subj = e.get("subject") or ""
        if e.get("isCancelled") or e.get("isAllDay") or any(s in subj.lower() for s in skip):
            continue
        s, t = to_boston(e["start"]), to_boston(e["end"])
        blocks.append((s - pad, t + pad, subj, s, t))
    return sorted(blocks)


def clock(t, with_suffix=True):
    h = t.hour % 12 or 12
    s = f"{h}" if t.minute == 0 else f"{h}:{t.minute:02d}"
    return s + (("am" if t.hour < 12 else "pm") if with_suffix else "")


def span(a, b):
    """Aman's style: '12-1pm', '9:30-11am', '11am-12:30pm'."""
    same = (a.hour < 12) == (b.hour < 12)
    return f"{clock(a, not same)}-{clock(b)}"


def day_label(d):
    name = DAY_NAMES[d.weekday()]
    return f"{AMAN_DAY.get(name, name)} {d.month}/{d.day}"


def working_days(start, n, days):
    d, out = start, []
    while len(out) < n:
        if DAY_NAMES[d.weekday()] in days:
            out.append(d)
        d += timedelta(days=1)
    return out


def free_windows(day, blocks, cfg, minutes):
    lo = datetime.combine(day, time.fromisoformat(cfg["hours"][0]), BOSTON)
    hi = datetime.combine(day, time.fromisoformat(cfg["hours"][1]), BOSTON)
    cur, out = lo, []
    for b0, b1, *_ in blocks:
        if b1 <= cur or b0 >= hi:
            continue
        if b0 > cur:
            out.append((cur, min(b0, hi)))
        cur = max(cur, b1)
    if cur < hi:
        out.append((cur, hi))
    # round starts up to :00/:30, ends down to :00/:30
    rounded = []
    for a, b in out:
        a = a + timedelta(minutes=(-a.minute) % 30, seconds=-a.second, microseconds=-a.microsecond)
        b = b - timedelta(minutes=b.minute % 30, seconds=b.second, microseconds=b.microsecond)
        if (b - a) >= timedelta(minutes=minutes):
            rounded.append((a, b))
    return rounded


def offer(args, cfg):
    events = load_events(args.events)
    blocks = busy_blocks(events, cfg, args.in_person)
    minutes = args.minutes or cfg["default_minutes"]
    start = date.fromisoformat(args.from_date) if args.from_date else datetime.now(BOSTON).date()
    if not args.from_date and cfg.get("start_tomorrow", True):
        start += timedelta(days=1)
    slots, skipped, options = [], [], []
    for d in working_days(start, cfg["look_ahead_working_days"], cfg["days"]):
        wins = free_windows(d, blocks, cfg, minutes)
        if not wins:
            skipped.append(f"{day_label(d)}: no free {minutes} min between {cfg['hours'][0]} and {cfg['hours'][1]}")
            continue
        # prefer the longest window, capped at 2 hours so the offer stays specific
        a, b = max(wins, key=lambda w: (w[1] - w[0], -w[0].timestamp()))
        b = min(b, a + timedelta(hours=2))
        text = f"{day_label(d)}, {span(a, b)}"
        if args.their_tz and args.their_tz != "America/New_York":
            z = ZoneInfo(args.their_tz)
            text += f" ET ({span(a.astimezone(z), b.astimezone(z))} {TZ_LABEL.get(args.their_tz, args.their_tz)})"
        slots.append({"day": d.isoformat(), "start": a.isoformat(), "end": b.isoformat(), "text": text})
        options.append(invite_option(a, args.their_tz))
        if len(slots) == (args.count or cfg["slots_to_offer"]):
            break
    texts = [s["text"] for s in slots]
    joined = "; ".join(texts[:-1]) + ("; or " if len(texts) > 1 else "") + (texts[-1] if texts else "")
    if not events:
        skipped.insert(0, "WARNING: no calendar events were read; check the events file")
    print(json.dumps({"slots": slots, "text": joined, "skipped": skipped, "options": options}, indent=1))


def invite_option(a, their_tz=None, free=True):
    """One exact time for the app's invite panel: {start, text, free, their}."""
    o = {"start": a.strftime("%Y-%m-%dT%H:%M"), "text": f"{day_label(a.date())}, {clock(a)}", "free": free}
    if their_tz and their_tz != "America/New_York":
        o["their"] = f"{clock(a.astimezone(ZoneInfo(their_tz)))} {TZ_LABEL.get(their_tz, their_tz)}"
    return o


def check_time(events, cfg, when, minutes, in_person):
    """{when, free, outside_usual_hours, clashes} for one start time (Boston). Also used by the courier."""
    s = datetime.fromisoformat(when)
    s = s.replace(tzinfo=BOSTON) if s.tzinfo is None else s.astimezone(BOSTON)
    t = s + timedelta(minutes=minutes)
    clashes = [{"subject": subj, "start": a.strftime("%a %m/%d %H:%M"), "end": b.strftime("%H:%M")}
               for b0, b1, subj, a, b in busy_blocks(events, cfg, in_person) if b0 < t and b1 > s]
    lo, hi = (time.fromisoformat(h) for h in cfg["hours"])
    outside = not (lo <= s.time() and t.time() <= hi and DAY_NAMES[s.weekday()] in cfg["days"])
    return {"when": f"{day_label(s.date())}, {span(s, t)} (Boston)", "free": not clashes,
            "outside_usual_hours": outside, "clashes": clashes, "start": s}


def check(args, cfg):
    r = check_time(load_events(args.events), cfg, args.when, args.minutes or cfg["default_minutes"], args.in_person)
    r.pop("start")
    print(json.dumps(r, indent=1))


def times(args, cfg):
    events = load_events(args.events)
    out = []
    for w in args.when:
        r = check_time(events, cfg, w, args.minutes or cfg["default_minutes"], args.in_person)
        out.append(invite_option(r["start"], args.their_tz, r["free"]))
    out.sort(key=lambda o: not o["free"])
    if not events:
        print("WARNING: no calendar events were read; check the events file", file=sys.stderr)
    print(json.dumps({"options": out}, indent=1))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("offer", "check", "times"):
        q = sub.add_parser(name)
        q.add_argument("events")
        if name == "check":
            q.add_argument("when", help="Boston time, e.g. 2026-11-05T12:30")
        elif name == "times":
            q.add_argument("when", nargs="+", help="Boston times, e.g. 2026-11-05T12:30")
            q.add_argument("--their-tz")
        else:
            q.add_argument("--from", dest="from_date")
            q.add_argument("--count", type=int)
            q.add_argument("--their-tz")
        q.add_argument("--minutes", type=int)
        q.add_argument("--in-person", action="store_true")
    args = p.parse_args()
    {"offer": offer, "check": check, "times": times}[args.cmd](args, settings())


if __name__ == "__main__":
    sys.exit(main())
