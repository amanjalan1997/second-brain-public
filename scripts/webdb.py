"""Read and write the web app's database (Supabase). Claude's side of the web app (D-029).

  python3 scripts/webdb.py push <writes.json | ->  [--replace]   load writes printed by a *_to_app.py script
  python3 scripts/webdb.py get <collection> [field=value ...]       print matching docs as JSON
  python3 scripts/webdb.py delete <collection> <id> [<id> ...]      delete docs
  python3 scripts/webdb.py load-all [--days N]                       rebuild everything from the lists (first load)
  python3 scripts/webdb.py add-owner                                 create Aman's login (once, after setup)
  python3 scripts/webdb.py check                                     test the connection

Writes are the {op, collection, doc_id, file_path} lists the *_to_app.py scripts print (a write may carry
`data` instead of `file_path`). The web app is the only app since D-036. To-do tasks are saved with
scripts/todo_sync.py, never pushed directly, so Aman's ticks, edits and deletes survive (D-037). `--replace` deletes docs in the pushed collections whose id wasn't in this
push (use it for people, companies, calls, questions; never for tasks, which hold Aman's ticks).

Needs SUPABASE_URL and SUPABASE_SERVICE_KEY in .env (git-ignored). The service key is secret: it bypasses the
owner-only rule, so it must never be committed, pasted into chat or put in the app.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SETTINGS_EMAIL = "you@example.edu"


def env():
    vals = {}
    path = REPO / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    url = os.environ.get("SUPABASE_URL") or vals.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or vals.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env (see docs/WEB-APP.md).")
    return url.rstrip("/"), key


def call(method, path, body=None, headers=None):
    url, key = env()
    req = urllib.request.Request(url + path, method=method, data=None if body is None else json.dumps(body).encode())
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        sys.exit(f"Database error {e.code} on {method} {path.split('?')[0]}: {e.read().decode()[:300]}")


def q(s):
    return urllib.parse.quote(s, safe="")


def ids_in(collection):
    out, start = [], 0
    while True:
        rows = call("GET", f"/rest/v1/docs?select=id&collection=eq.{q(collection)}", headers={"Range": f"{start}-{start + 999}"})
        out += [r["id"] for r in rows]
        if len(rows) < 1000:
            return out
        start += 1000


def push(writes, replace=False):
    rows, deletes = [], []
    for w in writes:
        if w.get("op", "set") == "delete":
            deletes.append((w["collection"], w["doc_id"]))
            continue
        data = w.get("data")
        if data is None:
            data = json.loads(Path(w["file_path"]).read_text())
        rows.append({"collection": w["collection"], "id": w["doc_id"], "data": data})
    for i in range(0, len(rows), 200):
        call("POST", "/rest/v1/docs?on_conflict=collection,id", rows[i:i + 200],
             {"Prefer": "resolution=merge-duplicates,return=minimal"})
    if replace:
        keep = {}
        for r in rows:
            keep.setdefault(r["collection"], set()).add(r["id"])
        for coll, ids in keep.items():
            if coll in ("tasks", "days", "meta"):
                continue  # never wipe ticks, days or meta docs
            deletes += [(coll, i) for i in ids_in(coll) if i not in ids]
    for coll, i in deletes:
        call("DELETE", f"/rest/v1/docs?collection=eq.{q(coll)}&id=eq.{q(i)}", headers={"Prefer": "return=minimal"})
    return len(rows), len(deletes)


def get(collection, filters):
    path = f"/rest/v1/docs?select=id,data&collection=eq.{q(collection)}"
    for f in filters:
        field, _, value = f.partition("=")
        path += f"&id=eq.{q(value)}" if field == "id" else f"&data->>{q(field)}=eq.{q(value)}"  # id = the doc's own id
    return [{"id": r["id"], **r["data"]} for r in call("GET", path)]


def run_script(args):
    out = subprocess.run(["python3", *args], cwd=REPO, capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"{args[0]} failed: {out.stderr.strip()[:300]}")
    return json.loads(out.stdout)


def load_all(days):
    tmp = Path(tempfile.mkdtemp(prefix="webdb-"))
    todo = sorted((REPO / "lists/todo").glob("*.md"))[-days:]
    news = sorted((REPO / "lists/news").glob("*.md"))[-days:]
    writes = []
    for f in todo:
        writes += run_script(["scripts/todo_to_app.py", str(f), str(tmp / f"app-{f.stem}")])
    for f in news:
        writes += run_script(["scripts/news_to_app.py", str(f), str(tmp / f"news-{f.stem}")])
    explained = sorted((REPO / "lists/explained").glob("*.md"))[-days:]
    if explained:  # cards per day, plus meta/storylines and meta/glossary
        writes += run_script(["scripts/explain_to_app.py", str(tmp / "explain"), *[f.stem for f in explained]])
    replaceable = []
    replaceable += run_script(["scripts/network_to_app.py", str(tmp / "net")])
    replaceable += run_script(["scripts/companies_to_app.py", str(tmp / "co")])
    replaceable += run_script(["scripts/thinking_to_app.py", str(tmp / "thk")])
    n1, _ = push(writes)
    n2, d = push(replaceable, replace=True)
    print(f"Loaded {n1 + n2} docs ({len(todo)} days of lists, {len(news)} news briefs, {len(explained)} explained days, network, companies, calls, "
          f"questions, learning); removed {d} stale docs.")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "push":
        src = rest[0] if rest and rest[0] != "--replace" else "-"
        writes = json.load(sys.stdin if src == "-" else open(src))
        n, d = push(writes, replace="--replace" in rest)
        print(f"Saved {n} docs, deleted {d}.")
    elif cmd == "get":
        print(json.dumps(get(rest[0], rest[1:]), ensure_ascii=False, indent=1))
    elif cmd == "delete":
        for i in rest[1:]:
            call("DELETE", f"/rest/v1/docs?collection=eq.{q(rest[0])}&id=eq.{q(i)}", headers={"Prefer": "return=minimal"})
        print(f"Deleted {len(rest) - 1}.")
    elif cmd == "load-all":
        days = int(rest[rest.index("--days") + 1]) if "--days" in rest else 30
        load_all(days)
    elif cmd == "add-owner":
        call("POST", "/auth/v1/admin/users", {"email": SETTINGS_EMAIL, "email_confirm": True})
        print(f"Login created for {SETTINGS_EMAIL}.")
    elif cmd == "check":
        call("GET", "/rest/v1/docs?select=id&limit=1")
        print("Connected: the docs table is there.")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
