"""Turn the calls list, research questions and learning path into documents for the app's laptop views.

  python3 scripts/thinking_to_app.py <out_dir>

Reads lists/calls.md, lists/research.md and lists/learning.md. Writes <out_dir>/calls/<id>.json,
<out_dir>/questions/<id>.json, <out_dir>/meta/learning.json and <out_dir>/meta/calls.json, then prints a JSON
list of writes ({op, collection, doc_id, file_path}) for the web app (web app only since D-036):
  python3 scripts/thinking_to_app.py <out_dir> | python3 scripts/webdb.py push - --replace
The markdown files stay the master; the app only shows them. `--replace` deletes any `calls` or `questions` doc
whose id isn't in this run. Learning progress is ticked in the app (meta/learning `done`), so /today reads it back
(`python3 scripts/webdb.py get meta`) into learning.md before running this.
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
THEMES = {
    "ai-science-recruiting": "Breaking into AI-for-science startups",
    "physical-ai": "Physical AI: where it's going",
    "startup-stage": "Startup stage & role choice",
    "outreach": "Outreach & networking tactics",
    "ai-consulting": "AI inside consulting",
    "career-strategy": "Career strategy",
    "clubs": "Running clubs & events",
    "coursework": "Class projects",
}


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def blocks(text, level="### "):
    """Split a file into (heading, field dict) blocks. Fields with sub-bullets become lists."""
    out, head, fields, key = [], None, {}, None
    for line in text.splitlines():
        if line.startswith(level):
            if head:
                out.append((head, fields))
            head, fields, key = line[len(level):].strip(), {}, None
        elif line.startswith("## "):
            if head:
                out.append((head, fields))
            head, fields, key = None, {}, None
        elif head:
            m, s = FIELD.match(line), SUB.match(line)
            if m:
                key = m.group(1)
                fields[key] = m.group(2).strip() or []
            elif s and key is not None:
                if not isinstance(fields[key], list):
                    fields[key] = [fields[key]] if fields[key] else []
                fields[key].append(s.group(1).strip())
    if head:
        out.append((head, fields))
    return out


def as_list(v):
    return v if isinstance(v, list) else [v] if v else []


def csv(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()] if isinstance(v, str) else []


def insight(s):
    theme = ""
    m = re.search(r"\s+#([a-z0-9-]+)\s*$", s)
    if m:
        theme, s = m.group(1), s[: m.start()]
    lead, text = "", s
    m = re.match(r"\*\*(.+?)\*\*\s*(.*)$", s)
    if m:
        lead, text = m.group(1).strip(), m.group(2).strip()
    return {"lead": lead, "text": text, "theme": theme}


def followup(s):
    m = re.match(r"\[([ xX])\]\s*(.*)$", s)
    return {"text": m.group(2), "done": m.group(1) != " "} if m else {"text": s, "done": False}


def calls(out, writes):
    path = LISTS / "calls.md"
    if not path.exists():
        return 0
    n = 0
    for order, (head, f) in enumerate(blocks(path.read_text(encoding="utf-8"))):
        parts = [p.strip() for p in head.split(" · ")]
        date, who, org = (parts + ["", "", ""])[:3]
        doc = {
            "date": date, "who": who, "org": "" if org in ("—", "-") else org,
            "type": f.get("Type", ""), "when": f.get("When", ""), "people": csv(f.get("People")),
            "line": f.get("In one line", ""),
            "insights": [insight(x) for x in as_list(f.get("Insights"))],
            "followups": [followup(x) for x in as_list(f.get("Follow-ups"))],
            "questions": csv(f.get("Questions")), "mentioned": csv(f.get("Mentioned")),
            "filed": f.get("Filed", "yes").lower().startswith("y"),
            "granola": f.get("Granola", "") if str(f.get("Granola", "")).startswith("https://") else "",
            "order": order,
        }
        doc_id = slug(f"{date}-{who}")
        p = out / "calls" / f"{doc_id}.json"
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        writes.append({"op": "set", "collection": "calls", "doc_id": doc_id, "file_path": str(p.resolve())})
        n += 1
    return n


def questions(out, writes):
    path = LISTS / "research.md"
    if not path.exists():
        return 0
    n = 0
    for order, (head, f) in enumerate(blocks(path.read_text(encoding="utf-8"))):
        qid, _, title = head.partition(" · ")
        evidence = []
        for e in as_list(f.get("Evidence")):
            d, kind, text = (e.split(" · ", 2) + ["", "", ""])[:3]
            evidence.append({"date": d.strip(), "kind": kind.strip(), "text": text.strip()})
        doc = {"id": qid.strip(), "title": title.strip(), "status": f.get("Status", "Open"), "added": f.get("Added", ""),
               "take": f.get("My take so far", ""), "evidence": evidence, "order": order}
        p = out / "questions" / f"{qid.strip()}.json"
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        writes.append({"op": "set", "collection": "questions", "doc_id": qid.strip(), "file_path": str(p.resolve())})
        n += 1
    return n


def learning(out, writes):
    path = LISTS / "learning.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    title = re.search(r"^# Learning path:\s*(.+)$", text, re.M)
    steps = []
    for m in re.finditer(r"^(\d+)\. \[([ xX])\] \*\*(.+?)\*\*(.*)$", text, re.M):
        rest = [x.strip() for x in m.group(4).split(" · ") if x.strip()]
        qs = [x for x in rest if x.startswith("q-")]
        steps.append({"n": int(m.group(1)), "title": m.group(3), "sub": " · ".join(x for x in rest if x not in qs),
                      "question": qs[0] if qs else "", "done": m.group(2) != " "})
    today = {}
    sect = re.search(r"^## Today\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if sect:
        for line in sect.group(1).splitlines():
            m = FIELD.match(line)
            if m:
                today[m.group(1)] = m.group(2).strip()
    doc = {
        "track": title.group(1).strip() if title else "Robotics", "steps": steps,
        "today": {"date": today.get("Date", ""), "step": int(today.get("Step", "0") or 0), "title": today.get("Title", ""),
                  "what": today.get("What it is", ""), "why": today.get("Why for you", ""),
                  "ask": today.get("Ask at your next robotics chat", ""),
                  "link": today.get("Read more", "") if today.get("Read more", "").startswith("https://") else ""},
        "updatedAt": datetime.now().astimezone().isoformat(timespec="minutes"),
    }
    p = out / "meta" / "learning.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    writes.append({"op": "set", "collection": "meta", "doc_id": "learning", "file_path": str(p.resolve())})


def main(out_dir):
    out = Path(out_dir)
    for d in ("calls", "questions", "meta"):
        (out / d).mkdir(parents=True, exist_ok=True)
    writes = []
    n_calls = calls(out, writes)
    n_q = questions(out, writes)
    learning(out, writes)
    meta = {"calls": n_calls, "questions": n_q, "themes": THEMES, "updatedAt": datetime.now().astimezone().isoformat(timespec="minutes")}
    p = out / "meta" / "thinking.json"
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    writes.append({"op": "set", "collection": "meta", "doc_id": "thinking", "file_path": str(p.resolve())})
    print(json.dumps(writes, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
