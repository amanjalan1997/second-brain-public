"""Turn the network tracker (lists/network.md) into documents for the phone app's Network tab.

  python3 scripts/network_to_app.py <out_dir>

Writes <out_dir>/people/<id>.json (one per person) and <out_dir>/meta/network.json, then prints a
JSON list of writes ({op, collection, doc_id, file_path}) for the web app (web app only since D-036):
  python3 scripts/network_to_app.py <out_dir> | python3 scripts/webdb.py push - --replace
network.md stays the master; the app only shows it. `--replace` deletes any `people` doc whose id isn't in this run.
"""
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

MD = Path(__file__).resolve().parent.parent / "lists" / "network.md"
BULLET = re.compile(r"- \*\*(.+?):\*\*\s*(.*)$")


def slug(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse_table(lines):
    rows, header = [], None
    for line in lines:
        if not line.startswith("|"):
            if header:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
        elif not set(cells[0]) <= set("-: "):
            rows.append(dict(zip(header, cells)))
    return rows


def parse_profiles(lines):
    people, cur, field = {}, None, None
    for line in lines:
        if line.startswith("### "):
            cur = people.setdefault(line[4:].strip(), {})
            field = None
            continue
        if cur is None or not line.strip():
            continue
        m = BULLET.match(line)
        if m:
            field = m.group(1).strip()
            cur[field] = {"text": m.group(2).strip(), "items": []}
        elif field and re.match(r"\s{2,}- ", line):
            cur[field]["items"].append(line.strip()[2:].strip())
    return people


def items(p, key):
    f = p.get(key)
    if not f:
        return []
    return ([f["text"]] if f["text"] else []) + f["items"]


def main(out_dir):
    lines = MD.read_text(encoding="utf-8").splitlines()
    rows = parse_table(lines)
    profiles = parse_profiles(lines)
    out = Path(out_dir)
    (out / "people").mkdir(parents=True, exist_ok=True)
    (out / "meta").mkdir(parents=True, exist_ok=True)
    writes = []
    for order, r in enumerate(rows, 1):
        name = r["Name"]
        p = profiles.get(name, {})
        follow = []
        for it in items(p, "Follow-ups"):
            m = re.match(r"\[( |x)\]\s*(.*)", it)
            follow.append({"text": m.group(2) if m else it, "done": bool(m and m.group(1) == "x")})
        last = r.get("Last contact", "")
        doc = {
            "name": name,
            "company": r.get("Company · role", ""),
            "area": r.get("Area", ""),
            "relationship": r.get("Relationship", ""),
            "lastContact": last,
            "lastDate": (re.search(r"\d{4}-\d{2}-\d{2}", last) or [""])[0],
            "nextStep": r.get("Next step", ""),
            "status": r.get("Status", ""),
            "order": order,
            "role": " ".join(items(p, "Company / role")),
            "contact": " ".join(items(p, "Contact")),
            "howMet": " ".join(items(p, "How we met")),
            "learned": items(p, "What I learned"),
            "followups": follow,
            "log": items(p, "Log"),
        }
        doc_id = slug(name)
        path = out / "people" / f"{doc_id}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        writes.append({"op": "set", "collection": "people", "doc_id": doc_id, "file_path": str(path.resolve())})
    meta = {"count": len(rows), "updatedAt": datetime.now().astimezone().isoformat(timespec="minutes")}
    path = out / "meta" / "network.json"
    path.write_text(json.dumps(meta, indent=1))
    writes.append({"op": "set", "collection": "meta", "doc_id": "network", "file_path": str(path.resolve())})
    print(json.dumps(writes, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
