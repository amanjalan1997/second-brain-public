"""One-time setup of the web app's Supabase database (D-029). Run by Claude; safe to run again.

  python3 scripts/supabase_setup.py

Needs SUPABASE_ACCESS_TOKEN in .env (a personal access token Aman makes at supabase.com → Account → Access Tokens).
Steps: find the project (or create "second-brain" in East US), run supabase/schema.sql, turn sign-ups off
(sign-in is email + password; WEB_APP_URL in .env, once known, becomes where sign-in links land), then write the Project URL + service key into .env and the URL +
public anon key into app/config.js. Secret values are never printed. Afterwards: webdb.py add-owner and load-all,
then Aman deletes the access token (it can do anything in his Supabase account).
"""
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENV = REPO / ".env"
API = "https://api.supabase.com/v1"
NAME, REGION = "second-brain", "us-east-1"


def read_env():
    vals = {}
    for line in ENV.read_text().splitlines() if ENV.exists() else []:
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def set_env(key, value):
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines) + "\n")


TOKEN = read_env().get("SUPABASE_ACCESS_TOKEN", "")


def api(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=None if body is None else json.dumps(body).encode())
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "second-brain-setup")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        sys.exit(f"Supabase said {e.code} on {method} {path.split('?')[0]}: {e.read().decode()[:300]}")


def step(msg):
    print("•", msg, flush=True)


def main():
    if not TOKEN:
        sys.exit("Add SUPABASE_ACCESS_TOKEN to .env first (supabase.com → Account → Access Tokens).")
    projects = api("GET", "/projects")
    proj = next((p for p in projects if p["name"] == NAME), None) or (projects[0] if len(projects) == 1 else None)
    if not proj and projects:
        sys.exit("Several projects and none called 'second-brain': " + ", ".join(p["name"] for p in projects) + ". Tell Claude which one.")
    if not proj:
        orgs = api("GET", "/organizations")
        if not orgs:
            sys.exit("No Supabase organization found. Create one at supabase.com first.")
        pw = secrets.token_urlsafe(24)
        set_env("SUPABASE_DB_PASSWORD", pw)  # kept only so it isn't lost; nothing needs it day to day
        proj = api("POST", "/projects", {"name": NAME, "organization_id": orgs[0]["id"], "region": REGION, "db_pass": pw})
        step(f"Created project '{NAME}' in East US (free plan). Waiting for it to start (2–3 min)…")
    ref = proj.get("id") or proj.get("ref")
    for _ in range(60):
        status = api("GET", f"/projects/{ref}").get("status", "")
        if status == "ACTIVE_HEALTHY":
            break
        time.sleep(10)
    else:
        sys.exit(f"Project is still starting (status {status}). Run this again in a few minutes.")
    step(f"Using project '{proj['name']}' ({ref}).")

    api("POST", f"/projects/{ref}/database/query", {"query": (REPO / "supabase/schema.sql").read_text()})
    step("Database table and owner-only rule set up (supabase/schema.sql).")

    # The free plan can't change the email text, so sign-in is email + password; the standard sign-in-link email
    # is only used once, to set the password (and if it's forgotten).
    auth = {"disable_signup": True, "external_email_enabled": True, "password_min_length": 10}
    site = read_env().get("WEB_APP_URL", "")
    if site:
        auth["site_url"] = site
        auth["uri_allow_list"] = site.rstrip("/") + "/**"
    api("PATCH", f"/projects/{ref}/config/auth", auth)
    step("Sign-ups turned off; sign-in is email + password" + (f"; sign-in links go to {site}." if site else " (web address added once Vercel is set up)."))

    keys = api("GET", f"/projects/{ref}/api-keys?reveal=true")
    by = {k.get("name"): k.get("api_key") for k in keys}
    anon, service = by.get("anon"), by.get("service_role")
    if not anon or not service:
        sys.exit("Couldn't find the anon and service_role keys on the project.")
    url = f"https://{ref}.supabase.co"
    set_env("SUPABASE_URL", url)
    set_env("SUPABASE_SERVICE_KEY", service)
    cfg = REPO / "app/config.js"
    text = cfg.read_text()
    text = re.sub(r'supabaseUrl: "[^"]*"', f'supabaseUrl: "{url}"', text)
    text = re.sub(r'supabaseAnonKey: "[^"]*"', f'supabaseAnonKey: "{anon}"', text)
    cfg.write_text(text)
    step("Saved the Project URL and secret key to .env, and the URL + public key to app/config.js.")
    print("Done. Next: python3 scripts/webdb.py check && python3 scripts/webdb.py add-owner && python3 scripts/webdb.py load-all")


if __name__ == "__main__":
    main()
