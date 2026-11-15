"""Turn a day's to-do file (lists/todo/YYYY-MM-DD.md) into documents for the phone app's database.

  python3 scripts/todo_to_app.py lists/todo/2026-10-05.md <out_dir>

Writes <out_dir>/days/<date>.json and <out_dir>/tasks/<id>.json, then prints a JSON list of
writes ({op, collection, doc_id, file_path}). The markdown file stays the GitHub backup; the app's database is
where ticks, edits and deletes live. To save a list to the web app, use scripts/todo_sync.py merge (it calls
parse() below and never overwrites Aman's ticks, edits or deletes); this script's own output is for tests.

Every task gets a `key`: a fingerprint of its wording, so a later rebuild or refresh can tell it's already
on the list (or was deleted) and skip it (D-037).
"""
import hashlib
import json
import re
import sys
from pathlib import Path

SECTIONS = {"Networking / Professional": "net", "Clubs & interests": "clubs", "Personal": "personal"}


def to24(t):
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", t.strip(), re.I)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), m.group(2), (m.group(3) or "").upper()
    if ap == "PM" and h != 12:
        h += 12
    elif ap == "AM" and h == 12:
        h = 0
    elif not ap and 1 <= h <= 6:  # bare "2:30" in a daytime schedule means afternoon
        h += 12
    return f"{h:02d}:{mi}"


def parse_source(tag):
    tag = tag.strip()
    if tag.startswith("📝"):
        return {"kind": "note", "label": tag[1:].strip()}
    if tag.startswith("📅"):
        return {"kind": "cal", "label": tag[1:].strip()}
    if tag.startswith("✉️"):
        rest = tag[2:].strip()
        return {"kind": "email", "label": "" if rest == "email" else rest}
    if tag.startswith("↩️"):
        return {"kind": "carried", "label": tag[2:].strip().replace("carried ", "")}
    if tag.startswith("👥"):
        return {"kind": "network", "label": tag[1:].strip().replace("network", "").strip()}
    if tag.startswith("📞"):
        return {"kind": "call", "label": "Call · " + tag[1:].strip()}
    if tag.startswith("📰"):
        return {"kind": "news", "label": tag[1:].strip().replace("news", "").strip()}
    if tag.startswith("➕"):
        return {"kind": "added", "label": ""}
    return {"kind": "", "label": tag}


def task_key(text):
    """Fingerprint of a task's wording: same words (ignoring case, punctuation and a leading '? ') → same key."""
    norm = " ".join(re.sub(r"[^a-z0-9]+", " ", re.sub(r"^\?\s+", "", text or "").lower()).split())
    return "t" + hashlib.sha1(norm.encode()).hexdigest()[:10]


def parse(md_path):
    """Read a day's file → (day doc, list of tasks with ids)."""
    md = Path(md_path)
    date = md.stem
    lines = md.read_text(encoding="utf-8").splitlines()
    day = {"date": date, "schedule": [], "due": [], "emails": [], "emailsNote": "", "hidden": []}
    tasks, section, counters, part = [], None, {}, None
    for line in lines:
        if line.startswith("## "):
            title = line[3:].strip()
            part, section = title, SECTIONS.get(title)
            continue
        if part == "At a glance":
            cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("|") else None
            if cells and len(cells) == 3 and to24(cells[0]):
                what = cells[1]
                is_class = what.startswith("*") and what.endswith("*")
                day["schedule"].append({"start": to24(cells[0]), "what": what.strip("*"), "where": cells[2],
                                        "kind": "class" if is_class else "event"})
            if line.startswith("**Due today:**"):
                day["due"] = [s.strip() for s in line.split("**", 2)[2].split("·") if s.strip()]
        elif section and re.match(r"- \[( |x)\] ", line):
            done = line[3] == "x"
            body = line[6:]
            m = re.match(r"(.*?)\s·\s`([^`]*)`\s*$", body)
            text, src = (m.group(1), parse_source(m.group(2))) if m else (body, {"kind": "", "label": ""})
            unsure = text.startswith("? ")
            text = text[2:] if unsure else text
            counters[section] = counters.get(section, 0) + 1
            tasks.append({"id": f"{date}-{section}-{counters[section]:02d}", "day": date, "section": section,
                          "text": text, "source": src, "done": done, "order": counters[section], "unsure": unsure,
                          "key": task_key(text)})
        elif part == "Hidden by your rules" and line.startswith("- "):
            m = re.match(r"- (.*?)(?:\s·\s`([^`]*)`)?\s*$", line)
            if m and m.group(1).strip() != "Nothing hidden":  # "- (Clubs) Validate Sam in Club · `rule`"
                sm = re.match(r"\((Networking|Clubs|Personal)[^)]*\)\s+(.*)", m.group(1).strip())
                sec = {"Networking": "net", "Clubs": "clubs", "Personal": "personal"}[sm.group(1)] if sm else "personal"
                day["hidden"].append({"text": (sm.group(2) if sm else m.group(1)).strip(), "rule": (m.group(2) or "").strip(), "section": sec})
        elif part == "Emails to read":
            if line.startswith("*Top"):
                day["emailsNote"] = line.strip("*").strip()
            m = re.match(r"\d+\.\s+\*\*([^*]+)\*\*\s+·\s+(.*?):\s+(.*?)(?:\s+\[Open\]\((.*?)\))?\s*$", line)
            if m:
                day["emails"].append({"tag": m.group(1), "from": m.group(2), "summary": m.group(3), "link": m.group(4) or ""})
    return day, tasks


def main(md_path, out_dir):
    day, tasks = parse(md_path)
    date, out = day["date"], Path(out_dir)
    writes = []
    (out / "days").mkdir(parents=True, exist_ok=True)
    (out / "tasks").mkdir(parents=True, exist_ok=True)
    p = out / "days" / f"{date}.json"
    p.write_text(json.dumps(day, ensure_ascii=False, indent=1))
    writes.append({"op": "set", "collection": "days", "doc_id": date, "file_path": str(p.resolve())})
    for t in tasks:
        tid = t.pop("id")
        p = out / "tasks" / f"{tid}.json"
        p.write_text(json.dumps(t, ensure_ascii=False, indent=1))
        writes.append({"op": "set", "collection": "tasks", "doc_id": tid, "file_path": str(p.resolve())})
    print(json.dumps(writes, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
