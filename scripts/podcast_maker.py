"""The NotebookLM maker for Podcasts (docs/PRD-podcasts.md section 8, D-044). No AI: it clicks through NotebookLM
(now "Gemini Notebook") the same way every time, in its own Chrome profile on this Mac, and downloads the episode.

  python3 scripts/podcast_maker.py signin                 open a normal Chrome window on the maker's profile; Aman signs
                                                          in to Google himself (Claude never sees the password). The
                                                          window closes by itself once NotebookLM opens
  python3 scripts/podcast_maker.py check [--show]         is the profile signed in? prints {"signedIn": true|false}
  python3 scripts/podcast_maker.py make <job.json> [--show]   make one episode (job fields below); prints the result JSON
  python3 scripts/podcast_maker.py download <notebook url> <out.m4a> [--show]   download a notebook's newest episode

A job is {"brief_file", "links": [], "style": explain|brief|debate|critique, "length": quick|standard|deep,
"focus", "notebook_url" (only for a Part 2: reuse that notebook), "out_dir"}. The result is
{"ok": true, "notebook_url", "audio_file", "nlm_title", "duration_s", "usage"} or
{"ok": false, "kind": signin|quota|ui|timeout|busy, "step", "message", "snapshot"}.

The profile lives in ~/.second-brain/notebooklm-profile. Chrome runs without a window (headless) unless --show is
given or PODCAST_MAKER_SHOW=1. Buttons are found by their labels ("Create notebook", "Copied text", "Generate now"),
not by position, so small redesigns don't break it; when a step still fails it saves a screenshot and the page's
HTML next to the episode so the repair step (podcast skill section C) can see what changed.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOME = Path.home() / ".second-brain"
PROFILE = HOME / "notebooklm-profile"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SITE = "https://notebook.google.com/"
STYLES = {"explain": "Deep Dive", "brief": "Brief", "critique": "Critique", "debate": "Debate"}
LENGTHS = {"quick": "Short", "standard": "Default", "deep": "Long"}
RECORD_TIMEOUT_MIN = 35
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/{v} Safari/537.36")


class MakerError(Exception):
    def __init__(self, kind, step, message):
        super().__init__(message)
        self.kind, self.step, self.message = kind, step, message


def show_window(argv):
    return "--show" in argv or os.environ.get("PODCAST_MAKER_SHOW") == "1"


def profile_busy():
    """Chrome leaves a SingletonLock link while a window uses the profile (e.g. the sign-in window is still open)."""
    lock = PROFILE / "SingletonLock"
    if not lock.is_symlink():
        return False
    pid = os.readlink(lock).rsplit("-", 1)[-1]
    try:
        os.kill(int(pid), 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


# ---------- sign-in: a plain Chrome window, no automation, so Google's sign-in page works normally ----------

def signin(timeout_min=15):
    PROFILE.mkdir(parents=True, exist_ok=True)
    if profile_busy():
        sys.exit("The NotebookLM window is already open. Finish signing in there, or close it and run this again.")
    port = 9337
    proc = subprocess.Popen([CHROME, f"--user-data-dir={PROFILE}", f"--remote-debugging-port={port}", "--no-first-run",
                             "--no-default-browser-check", "--new-window", SITE],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("A Chrome window opened. Sign in to Google there (the account with NotebookLM PLUS).", flush=True)
    end = time.time() + timeout_min * 60
    ok, streak = False, 0
    while time.time() < end and proc.poll() is None:
        time.sleep(3)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as r:
                tabs = json.loads(r.read().decode())
        except Exception:
            continue
        # signed out, NotebookLM shows its home page for a moment and then jumps to /trynow, so wait until the
        # signed-in page has stayed up for about 10 seconds
        here = any(t.get("type") == "page" and t.get("url", "").startswith(SITE) and "/trynow" not in t.get("url", "")
                   and "accounts.google" not in t.get("url", "") and "Notebook" in t.get("title", "") for t in tabs)
        streak = streak + 1 if here else 0
        if streak >= 4:
            ok = True
            break
    if ok:
        print("Signed in. Saving and closing the window…", flush=True)
        time.sleep(6)  # let Chrome write the sign-in cookies
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)  # a normal quit: Chrome saves cookies on the way out
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
    if ok:  # double-check the way the maker will see it
        time.sleep(2)
        ok = bool(check().get("signedIn"))
    return ok


# ---------- the automated browser ----------

class Browser:
    def __init__(self, show=False):
        from playwright.sync_api import sync_playwright
        if profile_busy():
            raise MakerError("busy", "opening", "The NotebookLM sign-in window is still open on the Mac.")
        self.pw = sync_playwright().start()
        version = subprocess.run([CHROME, "--version"], capture_output=True, text=True).stdout.split()[-1]
        self.ctx = self.pw.chromium.launch_persistent_context(
            str(PROFILE), channel="chrome", headless=not show, accept_downloads=True,
            viewport={"width": 1440, "height": 1000}, user_agent=UA.format(v=version),
            # the sign-in window used Chrome's real keychain, so this run must too (Playwright's default mock keychain
            # can't read those cookies); and no "controlled by automated software" bar or flag
            ignore_default_args=["--enable-automation", "--use-mock-keychain"],
            args=["--disable-blink-features=AutomationControlled", "--no-first-run", "--no-default-browser-check"])
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.page.set_default_timeout(30000)

    def close(self):
        try:
            self.ctx.close()
        finally:
            self.pw.stop()

    def snapshot(self, out_dir, step):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        try:
            self.page.screenshot(path=str(out / f"fail-{step}.png"), full_page=False)
            (out / f"fail-{step}.html").write_text(self.page.content())
        except Exception:
            pass
        return str(out / f"fail-{step}.png")


def signed_in(page):
    """Signed out, NotebookLM sends you to /trynow (a "Sign in" page) or to accounts.google.com."""
    page.goto(SITE, wait_until="domcontentloaded")
    for _ in range(40):
        url = page.url
        if "accounts.google." in url or "/trynow" in url or "ServiceLogin" in url:
            return False
        if page.get_by_role("button", name=re.compile(r"(New|Create)( new)? notebook|Create new", re.I)).count():
            return True
        time.sleep(1)
    return False


def body_text(page):
    try:
        return page.inner_text("body")
    except Exception:
        return ""


def click_text_button(scope, pattern, step, timeout=20000):
    loc = scope.get_by_role("button", name=re.compile(pattern, re.I))
    try:
        loc.first.wait_for(state="visible", timeout=timeout)
    except Exception:
        raise MakerError("ui", step, f"Couldn't find the '{pattern}' button")
    loc.first.click()


def new_notebook(page):
    page.goto(SITE, wait_until="domcontentloaded")
    for pattern in (r"^\s*(add_2\s*)?New notebook\s*$", r"New notebook", r"Create( new)? notebook", r"Create new"):
        loc = page.get_by_role("button", name=re.compile(pattern, re.I))
        try:
            loc.first.wait_for(state="visible", timeout=8000)
            loc.first.click()
            break
        except Exception:
            continue
    else:
        raise MakerError("ui", "creating the notebook", "Couldn't find the New notebook button")
    page.wait_for_url(re.compile(r"/notebook/[0-9a-f-]{20,}"), timeout=30000)
    return page.url.split("?")[0]


def open_add_sources(page):
    dialog = page.locator("mat-dialog-container")
    if dialog.count() and dialog.first.get_by_text(re.compile("Copied text", re.I)).count():
        return dialog.first
    click_text_button(page, r"Add sources?", "opening Add sources")
    dialog.first.wait_for(state="visible", timeout=15000)
    return dialog.first


def source_count(page):
    m = re.search(r"(\d+) sources?\b", body_text(page))
    return int(m.group(1)) if m else 0


def add_text_source(page, text):
    before = source_count(page)
    dialog = open_add_sources(page)
    click_text_button(dialog, r"Copied text", "adding the brief")
    box = page.locator("mat-dialog-container textarea").last
    box.wait_for(state="visible", timeout=15000)
    box.fill(text)
    click_text_button(page.locator("mat-dialog-container").last, r"^\s*Insert\s*$", "adding the brief")
    wait_sources(page, before + 1, "adding the brief")


def add_link_sources(page, links):
    before = source_count(page)
    dialog = open_add_sources(page)
    click_text_button(dialog, r"Websites?|Website|YouTube", "adding your links")
    box = page.locator("mat-dialog-container textarea, mat-dialog-container input[type=text], mat-dialog-container input[type=url]").last
    box.wait_for(state="visible", timeout=15000)
    box.fill("\n".join(links))
    click_text_button(page.locator("mat-dialog-container").last, r"^\s*Insert\s*$", "adding your links")
    wait_sources(page, before + 1, "adding your links")


def wait_sources(page, want, step, secs=120):
    end = time.time() + secs
    while time.time() < end:
        if source_count(page) >= want and not page.locator("mat-dialog-container").count():
            return
        time.sleep(2)
    raise MakerError("ui", step, "NotebookLM didn't take the source")


AUDIO_ROW = ".artifact-item-button"


def audio_rows(page):
    rows = page.locator(AUDIO_ROW).filter(has_text="audio_spark")
    out = []
    for i in range(rows.count()):
        t = rows.nth(i).inner_text().replace("\n", " ")
        out.append(t)
    return out


def customize_and_generate(page, style, length, focus):
    tile = page.locator('div[aria-label="Audio Overview"]').first
    try:
        tile.wait_for(state="visible", timeout=20000)
    except Exception:
        raise MakerError("ui", "opening Customize", "Couldn't find the Audio Overview tile")
    # the arrow opens Customize; clicking the tile itself would start a default episode
    arrow = tile.locator("mat-icon", has_text="chevron_forward")
    if arrow.count():
        arrow.first.click()
    else:
        tile.locator("button").last.click()
    dialog = page.locator("mat-dialog-container").filter(has_text=re.compile("Customize", re.I)).first
    try:
        dialog.wait_for(state="visible", timeout=15000)
    except Exception:
        raise MakerError("ui", "opening Customize", "The Customize window didn't open")
    usage = ""
    m = re.search(r"AI Usage(.{0,120})", dialog.inner_text().replace("\n", " "))
    if m:
        usage = re.sub(r"\s+", " ", m.group(1)).strip()[:120]
    # formats are radio inputs in the order Deep Dive, Brief, Critique, Debate; lengths are toggle buttons with role "radio"
    style_label = STYLES.get(style, "Deep Dive")
    radios = dialog.locator("input[type=radio]")
    order = ["Deep Dive", "Brief", "Critique", "Debate"]
    if radios.count() >= 4:
        radios.nth(order.index(style_label)).check(force=True)
    else:
        dialog.get_by_text(style_label, exact=True).first.click()
    len_label = LENGTHS.get(length, "Default")
    btn = dialog.get_by_role("radio", name=re.compile(rf"^\s*{len_label}\s*$"))
    if not btn.count():
        btn = dialog.get_by_role("button", name=re.compile(rf"^\s*{len_label}\s*$"))
    if btn.count():
        btn.last.click()
    else:
        dialog.get_by_text(len_label, exact=True).first.click()
    box = dialog.locator("textarea").first
    box.fill(focus)
    gen = dialog.get_by_role("button", name=re.compile(r"Generate( now)?", re.I))
    if not gen.count() or gen.first.is_disabled():
        raise MakerError("quota" if re.search(r"limit|quota|upgrade", dialog.inner_text(), re.I) else "ui",
                         "starting the recording", "The Generate button isn't available")
    gen.first.click()
    time.sleep(4)
    text = body_text(page)
    if re.search(r"(daily|usage) limit|reached (your|the) limit|limit reached|try again tomorrow|out of (credits|usage)", text, re.I):
        raise MakerError("quota", "starting the recording", "NotebookLM's daily limit is used up")
    return usage


def wait_for_episode(page, before, step_cb=None, cancelled=None):
    """Wait until a new audio row appears and nothing is generating. Reloads now and then: the page doesn't always update."""
    start = time.time()
    last_reload = start
    while time.time() - start < RECORD_TIMEOUT_MIN * 60:
        if cancelled and cancelled():
            raise MakerError("cancelled", "recording", "Cancelled")
        text = body_text(page)
        rows = audio_rows(page)
        generating = "Generating" in text
        if len(rows) > before and not generating:
            return rows[0] if rows else ""
        if re.search(r"(couldn't|could not|failed to) (generate|create)", text, re.I):
            raise MakerError("ui", "recording", "NotebookLM said the episode couldn't be made")
        if step_cb:
            step_cb(int((time.time() - start) // 60))
        if time.time() - last_reload > 180:
            page.reload(wait_until="domcontentloaded")
            last_reload = time.time()
            time.sleep(5)
        time.sleep(15)
    raise MakerError("timeout", "recording", f"NotebookLM took longer than {RECORD_TIMEOUT_MIN} minutes")


def parse_row(row):
    """'audio_spark Unread Why Retrofitted … Robots 25:14 · Deep Dive · 1 source · 1m ago …' → (title, seconds)."""
    t = re.sub(r"^(audio_spark\s*)?(Unread\s*)?", "", row.strip())
    m = re.search(r"\s(\d{1,2}):(\d{2})(?::(\d{2}))?\s*·", t)
    if not m:
        return t[:120], 0
    title = t[:m.start()].strip()
    a, b, c = m.group(1), m.group(2), m.group(3)
    secs = int(a) * 3600 + int(b) * 60 + int(c) if c else int(a) * 60 + int(b)
    return title, secs


def download_newest(page, out_file):
    """⋮ → Download opens a googleusercontent link that needs the sign-in cookies; fetch it with them."""
    rows = page.locator(AUDIO_ROW).filter(has_text="audio_spark")
    try:
        rows.first.wait_for(state="visible", timeout=30000)
    except Exception:
        raise MakerError("ui", "downloading", "Couldn't find the episode in the notebook")
    page.evaluate("""() => { window.__sbOpened = []; window.open = (u) => { window.__sbOpened.push(String(u)); return null; }; }""")
    more = rows.first.locator("xpath=ancestor::*[.//button[@aria-label='More']][1]").locator("button[aria-label='More']")
    if not more.count():
        raise MakerError("ui", "downloading", "Couldn't find the episode's ⋮ menu")
    more.last.click()
    item = page.get_by_role("menuitem", name=re.compile("Download", re.I))
    try:
        item.first.wait_for(state="visible", timeout=10000)
    except Exception:
        raise MakerError("ui", "downloading", "The ⋮ menu has no Download")
    url = None
    try:
        with page.expect_download(timeout=8000) as dl:
            item.first.click()
        dl.value.save_as(str(out_file))
        return str(out_file)
    except Exception:
        pass
    for _ in range(20):
        opened = page.evaluate("() => window.__sbOpened || []")
        if opened:
            url = opened[-1]
            break
        time.sleep(0.5)
    if not url:
        raise MakerError("ui", "downloading", "Download didn't give a link")
    res = page.context.request.get(url, timeout=180000)
    ctype = res.headers.get("content-type", "")
    if not res.ok or "html" in ctype:
        raise MakerError("signin" if "html" in ctype else "ui", "downloading", f"The download link answered {res.status} {ctype}")
    Path(out_file).write_bytes(res.body())
    return str(out_file)


def make(job, show=False, step_cb=None, cancelled=None, notebook_cb=None):
    out_dir = Path(job["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    step = "opening NotebookLM"
    b, nb = None, job.get("notebook_url")
    try:
        b = Browser(show)
        page = b.page
        say = step_cb or (lambda s: None)
        say("opening NotebookLM")
        if not signed_in(page):
            raise MakerError("signin", step, "NotebookLM on the Mac is signed out")
        if job.get("notebook_url"):
            step = "opening the notebook"
            page.goto(nb, wait_until="domcontentloaded")
            time.sleep(4)
        else:
            step = "creating the notebook"
            say(step)
            nb = new_notebook(page)
            if notebook_cb:
                notebook_cb(nb)
        step = "adding the brief"
        say(step)
        add_text_source(page, Path(job["brief_file"]).read_text())
        if job.get("links"):
            step = "adding your links"
            say(step)
            try:
                add_link_sources(page, job["links"])
            except MakerError:
                page.keyboard.press("Escape")  # links are extra; the brief alone still makes a good episode
        before = len(audio_rows(page))
        step = "starting the recording"
        say(step)
        usage = customize_and_generate(page, job.get("style", "explain"), job.get("length", "standard"), job["focus"])
        step = "recording"
        row = wait_for_episode(page, before, (lambda m: say(f"recording in NotebookLM · {m} min")) if step_cb else None, cancelled)
        title, secs = parse_row(row)
        step = "downloading"
        say(step)
        audio = download_newest(page, out_dir / "original.m4a")
        return {"ok": True, "notebook_url": nb, "audio_file": audio, "nlm_title": title, "duration_s": secs, "usage": usage}
    except MakerError as e:
        snap = b.snapshot(out_dir, re.sub(r"\W+", "-", e.step)) if b and e.kind == "ui" else ""
        return {"ok": False, "kind": e.kind, "step": e.step, "message": e.message, "snapshot": snap, "notebook_url": nb}
    except Exception as e:  # anything unexpected is treated as a page change, so the repair step can look
        snap = b.snapshot(out_dir, re.sub(r"\W+", "-", step)) if b else ""
        return {"ok": False, "kind": "ui", "step": step, "message": f"{type(e).__name__}: {str(e)[:300]}", "snapshot": snap, "notebook_url": nb}
    finally:
        if b:
            b.close()


def download(notebook_url, out_file, show=False):
    b = Browser(show)
    try:
        if not signed_in(b.page):
            raise MakerError("signin", "opening NotebookLM", "NotebookLM on the Mac is signed out")
        b.page.goto(notebook_url, wait_until="domcontentloaded")
        time.sleep(5)
        rows = audio_rows(b.page)
        path = download_newest(b.page, out_file)
        title, secs = parse_row(rows[0]) if rows else ("", 0)
        return {"ok": True, "audio_file": path, "nlm_title": title, "duration_s": secs}
    except MakerError as e:
        return {"ok": False, "kind": e.kind, "step": e.step, "message": e.message, "snapshot": b.snapshot(Path(out_file).parent, "download")}
    finally:
        b.close()


def check(show=False):
    try:
        b = Browser(show)
    except MakerError as e:
        return {"signedIn": None, "message": e.message}
    try:
        return {"signedIn": signed_in(b.page)}
    finally:
        b.close()


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    show = show_window(rest)
    rest = [a for a in rest if a != "--show"]
    if cmd == "signin":
        ok = signin()
        print("Done: NotebookLM is signed in on this Mac." if ok else "Not signed in (the window closed or timed out). Run it again when ready.")
        sys.exit(0 if ok else 1)
    elif cmd == "check":
        print(json.dumps(check(show)))
    elif cmd == "make":
        print(json.dumps(make(json.loads(Path(rest[0]).read_text()), show, step_cb=lambda s: print("·", s, flush=True)), indent=1))
    elif cmd == "download":
        print(json.dumps(download(rest[0], rest[1], show), indent=1))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
