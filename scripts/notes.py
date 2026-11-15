"""Read Aman's Apple Notes (on this Mac) for /today. Prints JSON to the screen; saves nothing.

  python3 scripts/notes.py since <hours>   notes changed in the last <hours> hours (unlocked only)
  python3 scripts/notes.py get "<title>"   one note by exact title

The first run asks macOS for permission to control Notes; click OK.
"""
import json
import subprocess
import sys

RS, US = "\x1e", "\x1f"  # record / field separators that never appear in notes

FIELDS = '''(name of n) & US & (id of n) & US & my iso(modification date of n) & US & (plaintext of n) & RS'''

HELPERS = '''
on pad(x)
  if x < 10 then return "0" & x
  return x as string
end pad
on iso(d)
  set t to time of d
  return (year of d as string) & "-" & my pad(month of d as integer) & "-" & my pad(day of d) & "T" & my pad(t div 3600) & ":" & my pad((t mod 3600) div 60)
end iso
'''


def run(body):
    script = f'''{HELPERS}
set RS to (ASCII character 30)
set US to (ASCII character 31)
tell application "Notes"
  set out to ""
  {body}
  return out
end tell'''
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        sys.exit(f"Could not read Notes: {r.stderr.strip()}")
    notes = []
    for rec in r.stdout.rstrip("\n").split(RS):
        parts = rec.strip("\n").split(US)
        if len(parts) == 4:
            title, nid, modified, text = parts
            notes.append({"title": title, "id": nid, "modified": modified, "text": text})
    return notes


def since(hours):
    secs = int(float(hours) * 3600)
    return run(f'''set cutoff to (current date) - {secs}
  repeat with n in (every note whose modification date > cutoff)
    if not (password protected of n) then set out to out & {FIELDS}
  end repeat''')


def get(title):
    safe = title.replace('"', '\\"')
    return run(f'''repeat with n in (every note whose name is "{safe}")
    if not (password protected of n) then set out to out & {FIELDS}
  end repeat''')


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("since", "get"):
        sys.exit(__doc__)
    notes = since(sys.argv[2]) if sys.argv[1] == "since" else get(sys.argv[2])
    print(json.dumps(notes, ensure_ascii=False, indent=1))
