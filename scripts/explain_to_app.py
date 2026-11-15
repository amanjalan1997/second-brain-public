"""Turn The Explainer's lists into documents for the app (top of the News tab; storylines and glossary on the laptop).

  python3 scripts/explain_to_app.py <out_dir> [YYYY-MM-DD ...]

Reads lists/explained/<date>.md for each date given (default: the newest one), lists/storylines.md and
lists/glossary.md. Writes <out_dir>/explained/<date>.json, <out_dir>/meta/storylines.json and
<out_dir>/meta/glossary.json, then prints a JSON list of writes ({op, collection, doc_id, file_path}) for the
web app (web app only since D-036): pipe it into `python3 scripts/webdb.py push -` (never --replace, which would
delete the other days' cards). The markdown files stay the master; the app only shows them.

Document shapes:
  explained/<date>: {date, title, intro, cards: [{id, title, storyline, robotics, simply, why: [..], idea: {term, text},
                     optimist, skeptic, watch: [..], confidence, forYou, say, ask, sources: [{label, url}],
                     deeper: {label, url, why}}], week: {moved: [{title, text, links}], surprise, read} | null, updatedAt}
  meta/storylines:  {items: [{id, title, status, stand, players, question, start: [{label, url, why}],
                     timeline: [{date, text, links}]}], updatedAt}
  meta/glossary:    {terms: [{term, means, like, first, storyline, path, link: {label, url}}], updatedAt}
"""
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

LISTS = Path(__file__).resolve().parent.parent / "lists"
FIELD = re.compile(r"^- \*\*(.+?):\*\*\s*(.*)$")
SUB = re.compile(r"^\s+- (.*)$")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def clean(s):
    """Plain text: drop links and markdown emphasis."""
    s = LINK.sub("", s).replace("**", "").replace("`", "")
    s = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", s)
    s = re.sub(r"\s*·\s*(?=·|$)", "", s)
    return re.sub(r"\s{2,}", " ", s).strip(" ·—-")


def links(s):
    return [{"label": l, "url": u} for l, u in LINK.findall(s) if u.startswith("https://")]


def read_link(s):
    """'[Title](url) — why' → {label, url, why}."""
    m = LINK.search(s)
    if not m or not m.group(2).startswith("https://"):
        return None
    return {"label": m.group(1), "url": m.group(2), "why": clean(s[m.end():])}


def fields(lines):
    """`- **Name:** value` lines with indented `  - ` sub-bullets → {name: (value, [subs])}."""
    out, cur = {}, None
    for line in lines:
        m = FIELD.match(line)
        if m:
            cur = m.group(1)
            out[cur] = (m.group(2).strip(), [])
            continue
        s = SUB.match(line)
        if s and cur:
            out[cur][1].append(s.group(1).strip())
        elif cur and line.strip() and line.startswith("  "):  # wrapped continuation of the value
            v, subs = out[cur]
            if subs:
                subs[-1] += " " + line.strip()
            else:
                out[cur] = ((v + " " + line.strip()).strip(), subs)
    return out


def sections(text, prefix):
    """Split markdown into (heading, lines) blocks at headings starting with `prefix`."""
    blocks, head, body = [], None, []
    for line in text.splitlines():
        if line.startswith(prefix) and not line.startswith(prefix + "#"):
            if head is not None:
                blocks.append((head, body))
            head, body = line[len(prefix):].strip(), []
        elif head is not None:
            body.append(line)
    if head is not None:
        blocks.append((head, body))
    return blocks


def card(title, f):
    get = lambda k: f.get(k, ("", []))
    idea = get("The idea underneath")[0]
    m = re.match(r"(.+?)(?<!\bvs)(?<!\be\.g)(?<!\bi\.e)\.\s+(?=[A-Z\"“])(.*)", idea)  # "Term. Definition…" (not "vs.")
    term, rest = (m.group(1), m.group(2)) if m else ("", "")
    return {
        "id": slug(title)[:60], "title": clean(title), "storyline": get("Storyline")[0].strip("` "),
        "robotics": get("Robotics")[0].lower().startswith("y"),
        "simply": clean(get("What happened, simply")[0]),
        "why": [clean(x) for x in get("Why it matters")[1]] or ([clean(get("Why it matters")[0])] if get("Why it matters")[0] else []),
        "idea": {"term": clean(term), "text": clean(rest)} if rest else {"term": "", "text": clean(idea)},
        "optimist": clean(get("Optimist")[0]), "skeptic": clean(get("Skeptic")[0]),
        "watch": [clean(x) for x in get("What to watch")[1]] or ([clean(get("What to watch")[0])] if get("What to watch")[0] else []),
        "confidence": clean(get("Confidence")[0]), "forYou": clean(get("For you")[0]),
        "say": clean(get("Say it")[0]).strip('"“”'), "ask": clean(get("Ask")[0]).strip('"“”'),
        "sources": links(get("Sources")[0]) + [l for s in get("Sources")[1] for l in links(s)],
        "deeper": read_link(get("Go deeper")[0]),
    }


def week(f):
    moved = []
    for s in f.get("Moved this week", ("", []))[1]:
        m = re.match(r"\*\*(.+?):?\*\*:?\s*(.*)", s)
        title, text = (m.group(1).rstrip(":"), m.group(2)) if m else ("", s)
        moved.append({"title": clean(title), "text": clean(text), "links": links(s)})
    surprise = f.get("Surprise of the week", ("", []))[0]
    return {"moved": moved, "surprise": {"text": clean(surprise), "links": links(surprise)},
            "read": read_link(f.get("Read this weekend", ("", []))[0])}


def day(path, out, writes):
    text = path.read_text(encoding="utf-8")
    title = re.search(r"^# (.+)$", text, re.M)
    intro = re.search(r"^\*(.+)\*$", text, re.M)
    doc = {"date": path.stem, "title": title.group(1).strip() if title else "", "intro": clean(intro.group(1)) if intro else "",
           "cards": [], "week": None}
    for head, body in sections(text, "## "):
        f = fields(body)
        if head.lower().startswith("the week"):
            doc["week"] = week(f)
        elif f:
            c = card(head, f)
            if c["sources"]:  # no link, no card
                doc["cards"].append(c)
    doc["updatedAt"] = datetime.now().astimezone().isoformat(timespec="minutes")
    p = out / "explained" / f"{path.stem}.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    writes.append({"op": "set", "collection": "explained", "doc_id": path.stem, "file_path": str(p.resolve())})
    return len(doc["cards"])


def storylines(out, writes):
    path = LISTS / "storylines.md"
    items = []
    if path.exists():
        for head, body in sections(path.read_text(encoding="utf-8"), "### "):
            sid, _, title = head.partition(" · ")
            f = fields(body)
            get = lambda k: f.get(k, ("", []))
            timeline = []
            for t in get("Timeline")[1]:
                m = re.match(r"(\d{4}-\d{2}-\d{2})\s*·\s*(.*)", t)
                if m:
                    timeline.append({"date": m.group(1), "text": clean(m.group(2)), "links": links(m.group(2))})
            items.append({"id": sid.strip(), "title": clean(title or sid), "status": get("Status")[0] or "Active",
                          "stand": clean(get("Where things stand")[0]), "players": clean(get("Key players")[0]),
                          "question": clean(get("The open question")[0]),
                          "start": [r for r in (read_link(s) for s in [get("Start here")[0], *get("Start here")[1]]) if r],
                          "timeline": sorted(timeline, key=lambda t: t["date"], reverse=True)})
    doc = {"items": items, "updatedAt": datetime.now().astimezone().isoformat(timespec="minutes")}
    p = out / "meta" / "storylines.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    writes.append({"op": "set", "collection": "meta", "doc_id": "storylines", "file_path": str(p.resolve())})
    return len(items)


def glossary(out, writes):
    path = LISTS / "glossary.md"
    terms = []
    if path.exists():
        for head, body in sections(path.read_text(encoding="utf-8"), "### "):
            f = fields(body)
            get = lambda k: f.get(k, ("", []))[0]
            more = read_link(get("Learn more"))
            terms.append({"term": clean(head), "means": clean(get("Means")), "like": clean(get("Like")),
                          "first": clean(get("First met")), "storyline": get("Storyline").strip("` "),
                          "path": clean(get("Learning path")), "link": {"label": more["label"], "url": more["url"]} if more else None})
    terms.sort(key=lambda t: t["term"].lower())
    doc = {"terms": terms, "updatedAt": datetime.now().astimezone().isoformat(timespec="minutes")}
    p = out / "meta" / "glossary.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    writes.append({"op": "set", "collection": "meta", "doc_id": "glossary", "file_path": str(p.resolve())})
    return len(terms)


def main(out_dir, dates):
    out = Path(out_dir)
    for d in ("explained", "meta"):
        (out / d).mkdir(parents=True, exist_ok=True)
    files = sorted((LISTS / "explained").glob("*.md"))
    if dates:
        files = [LISTS / "explained" / f"{d}.md" for d in dates]
    elif files:
        files = files[-1:]
    writes = []
    for f in files:
        if not f.exists():
            sys.exit(f"No such file: {f}")
        day(f, out, writes)
    storylines(out, writes)
    glossary(out, writes)
    print(json.dumps(writes, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
