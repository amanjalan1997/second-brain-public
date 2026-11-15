"""Turn the company list (lists/companies.md) into documents for the phone app's Companies tab.

  python3 scripts/companies_to_app.py <out_dir>

Writes <out_dir>/companies/<id>.json (one per company) and <out_dir>/meta/companies.json, then prints a
JSON list of writes ({op, collection, doc_id, file_path}) for the web app (web app only since D-036):
  python3 scripts/companies_to_app.py <out_dir> | python3 scripts/webdb.py push - --replace
companies.md stays the master; the app only shows it. `--replace` deletes any `companies` doc whose id isn't in this run.
"""
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

MD = Path(__file__).resolve().parent.parent / "lists" / "companies.md"


def slug(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main(out_dir):
    out = Path(out_dir)
    (out / "companies").mkdir(parents=True, exist_ok=True)
    (out / "meta").mkdir(parents=True, exist_ok=True)
    writes, sectors, sector, header = [], [], None, None
    for line in MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            sector, header = line[3:].strip(), None
            sectors.append(sector)
            continue
        if not sector or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set(cells[0]) <= set("-: "):
            continue
        r = dict(zip(header, cells))
        doc = {
            "name": r.get("Company", ""),
            "sector": sector,
            "sectorOrder": len(sectors),
            "what": r.get("What they do", ""),
            "heard": [h.strip() for h in r.get("How I heard", "").split(";") if h.strip()],
            "lastSeen": r.get("Last seen", ""),
        }
        doc_id = slug(doc["name"])
        path = out / "companies" / f"{doc_id}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        writes.append({"op": "set", "collection": "companies", "doc_id": doc_id, "file_path": str(path.resolve())})
    meta = {"count": len(writes), "sectors": sectors, "updatedAt": datetime.now().astimezone().isoformat(timespec="minutes")}
    path = out / "meta" / "companies.json"
    path.write_text(json.dumps(meta, indent=1))
    writes.append({"op": "set", "collection": "meta", "doc_id": "companies", "file_path": str(path.resolve())})
    print(json.dumps(writes, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
