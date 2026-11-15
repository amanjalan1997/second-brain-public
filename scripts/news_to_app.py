"""Turn a day's news brief (lists/news/YYYY-MM-DD.md) into one document for the phone app's News tab.

  python3 scripts/news_to_app.py lists/news/<date>.md <out_dir>

Writes <out_dir>/news/<date>.json and prints a JSON list of writes ({op, collection, doc_id, file_path})
for the web app (web app only since D-036): pipe it into `python3 scripts/webdb.py push -` (never --replace).
The markdown file stays the master; the app only shows it.

Document shape: {date, title, intro, sections: [{name, items: [{headline, text, group, links: [{label, url}]}]}],
raises: [{company, what, amount, stage, lead, date, link}], notes: [..], updatedAt}.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
EMOJI = re.compile(r"^[^\w(]+\s*")  # leading emoji on section headings


def clean(s):
    """Plain text: drop links, markdown emphasis and leftover separators."""
    s = LINK.sub("", s)
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", s)  # *italics*
    s = re.sub(r"\s*·\s*(?=·|$)", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" ·—-")


SUB = re.compile(r"^\s+(?:[-*]|\d+\.)\s+")


def make_item(lines, group):
    """First line = the item; indented bullets = points; other indented lines = a closing paragraph."""
    raw = re.sub(r"^(?:[-*]|\d+\.)\s+", "", lines[0].strip())
    points, more = [], []
    for l in lines[1:]:
        if SUB.match(l):
            points.append(SUB.sub("", l).strip())
        elif points and not more and l.startswith("      "):  # wrapped text under a point
            points[-1] += " " + l.strip()
        else:
            more.append(l.strip())
    every = " ".join([raw, *points, *more])
    links = [{"label": l, "url": u} for l, u in LINK.findall(every)]
    m = BOLD.search(raw)
    if m and m.start() == 0:
        headline, rest = clean(m.group(1)), raw[m.end():]
    else:
        headline, rest = "", raw
    item = {"headline": headline, "text": clean(rest), "links": links}
    if points:
        item["points"] = [p for p in (clean(p) for p in points) if p]
    if more and clean(" ".join(more)):
        item["more"] = clean(" ".join(more))
    if group:
        item["group"] = group
    return item


def main(md_path, out_dir):
    md = Path(md_path)
    date = md.stem
    doc = {"date": date, "title": "", "intro": "", "sections": [], "raises": [], "notes": []}
    section, group, item, header = None, None, None, None

    def flush():
        nonlocal item
        if item and section is not None:
            target = doc["notes"] if section.get("_notes") else section["items"]
            it = make_item(item, group)
            target.append(it["text"] if section.get("_notes") and not it["headline"] else it)
        item = None

    for line in md.read_text(encoding="utf-8").splitlines():
        s = line.rstrip()
        if s.startswith("# ") and not doc["title"]:
            doc["title"] = s[2:].strip()
            continue
        if s.startswith("## "):
            flush()
            name = EMOJI.sub("", s[3:].strip())
            group, header = None, None
            section = {"name": name, "items": []}
            if name.lower().startswith("about"):
                section["_notes"] = True
            elif name.lower().startswith("fundraise"):
                section["_raises"] = True
            else:
                doc["sections"].append(section)
            continue
        if section is None:
            if s.startswith("*") and not doc["intro"]:
                doc["intro"] = clean(s)
            continue
        if section.get("_raises"):
            if not s.startswith("|"):
                continue
            cells = [c.strip() for c in s.strip().strip("|").split("|")]
            if header is None:
                header = [c.lower() for c in cells]
                continue
            if set(cells[0]) <= set("-: "):
                continue
            r = dict(zip(header, cells))
            link = LINK.search(r.get("link", ""))
            doc["raises"].append({"company": r.get("company", ""), "what": r.get("what", ""), "amount": r.get("amount", ""),
                                  "stage": r.get("stage", ""), "lead": r.get("lead", ""), "date": r.get("date", ""),
                                  "link": link.group(2) if link else ""})
            continue
        if re.match(r"^\*\*[^*]+\*\*$", s.strip()):  # bold sub-heading, e.g. **Robotics & AVs**
            flush()
            group = s.strip().strip("*")
            continue
        if re.match(r"^(?:[-*]|\d+\.)\s+", s):  # new top-level item
            flush()
            item = [s]
        elif item is not None and s.strip():  # sub-bullet or continuation line
            item.append(s)
        elif not s.strip() and item is not None and section.get("_notes"):
            flush()
    flush()
    doc["sections"] = [sec for sec in doc["sections"] if sec["items"]]
    for sec in doc["sections"]:
        sec.pop("_notes", None)
    doc["updatedAt"] = datetime.now().astimezone().isoformat(timespec="minutes")

    out = Path(out_dir) / "news"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{date}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    print(json.dumps([{"op": "set", "collection": "news", "doc_id": date, "file_path": str(path.resolve())}]))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
