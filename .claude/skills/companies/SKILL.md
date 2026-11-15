---
name: companies
description: Keep Aman's company list (lists/companies.md) up to date, a learning list of every company he has come across that fits his interests, grouped by sector, with what each one does and how/where he heard of it. Reads Granola calls, Apple Notes, Outlook email and calendar (incl. CSAIL Events), and the network tracker; shows new companies and new mentions for approval, then saves, refreshes the phone app's Companies tab and pushes. Also handles quick edits ("add company: X", "move X to Robotics", "drop X"). Use when Aman types /companies, asks about companies he has heard of or a sector, or when /today runs its companies step.
---

# /companies: the company list

Aman is not technical. Keep messages short and plain. **Never save changes he hasn't approved.**

**Purpose:** help Aman learn the sectors he cares about. It's a learning list, not a target list: include any company that could matter to him, whether or not he'd apply there.

Settings live in `config/settings.yaml` under `companies`. Read them first; if they disagree with this file, settings.yaml wins.

Files:
- `lists/companies.md`: **the master.** One section per sector, one table row per company.
- **Web app, Companies tab** (https://your-app.vercel.app; web app only since D-036): read-only view (search, sector filter). Its database holds `companies/<slug>` and `meta/companies`. Rebuilt from companies.md by `python3 scripts/companies_to_app.py <out_dir>`. Never edit it by hand.
- `lists/companies-state.json`: memory of what was already read (`last_sync`, `seen`), so nothing is processed twice.

## What Aman might say

| He says | Do |
|---|---|
| `/companies`, "update my companies" | **Sync** (section A) |
| "add company: X", "move X to Robotics", "drop X", "X does Y" | **Quick edit** (section B) |
| "what robotics companies have I heard of?" | Answer from `lists/companies.md` |

---

## A. Sync

### A1. Get ready
1. `git pull`. Read `config/settings.yaml` (`companies`) and `lists/companies-state.json`. Follow the **Companies** heading of `config/preferences.md` (rules Aman approved from his comments in the app).
2. Window = since `last_sync` (minus a day of overlap). If there's no `last_sync`, look back `companies.first_sync_days`.
3. Time zones: Outlook returns India Standard Time. Boston = IST − 9h30 until Nov 1, 2026, then IST − 10h30. Write dates in Boston time.

When run inside `/today`, reuse everything `/today` and the network step already read. Don't fetch the same email, note or call twice.

### A2. Gather company mentions (skip ids already in `seen`)
1. **Network tracker** (`lists/network.md`): every company in the *Company · role* column. How heard = the person and how Aman met them.
2. **Granola.** Each call: the other person's company, plus companies discussed (competitors, customers, portfolio companies, "you should look at X").
3. **Apple Notes** (`python3 scripts/notes.py since <hours>`): company names in meeting notes, event notes, career-fair notes, "check out X" lines. Skip `sources.notes_app.skip_notes`.
4. **Outlook email.** Real-person emails, and also event invites, club emails and newsletters **in Aman's areas** (Energy Club, Robotics, AI, CSAIL, Sloan recruiting): companies that are hosting, speaking, sponsoring, hiring or featured. A newsletter that lists 20 companies → keep only the ones the email actually describes and that fit his sectors.
5. **Calendar** (default + `CSAIL Events`): company names in event titles and descriptions (info sessions, speaker talks, treks, career fairs).

Open (`read_resource`) only what you need to get the company name and the gist.

### A3. Keep or skip
Keep a company when it fits one of `companies.sectors`, or Aman met someone from it, or a source recommends it to him.
Skip (settings `companies.skip`): MIT/Sloan/universities themselves, everyday tools mentioned in passing (Zoom, Canvas, Google Docs), course case-study companies outside his sectors, and big companies mentioned only as a passing example. When unsure, list it under **Questions** in the draft rather than adding it.

### A4. Build the changes
For each company:
- **Match** by name (ignore case, "Inc.", "AI", "Labs" suffixes; Acme = Acme Sciences). If unsure whether two names are the same company, ask.
- **New company:** propose a row: name, sector, **what they do** (one plain sentence), **how I heard** (first mention).
- **Existing company:** add the new mention to *How I heard*, and update *Last seen*. Don't repeat a mention that's already there.

**What they do:** write it from the sources plus your own knowledge, in one plain sentence (what they make, for whom). If you're not confident, end it with `(?)`. No web research unless Aman asks.

**How I heard** entries look like `Oct 6 · Sloan Networking Night (met Jamie Rivera)` or `Sep 26 · Fall Career Fair` or `Oct 2 · CSAIL talk` or `Oct 7 · email from Jordan Lee`. Several are joined with `; `, oldest first. Keep at most 4 (drop the oldest, except the first).

**Sector:** use the names in `companies.sectors`. If a company fits two, pick the one Aman would look for it under and mention the other in *What they do*. If nothing fits, use *Other* and suggest a new sector in the draft.

### A5. Show the draft and get approval
Show a compact summary in chat, grouped by sector:

> Companies: 5 new · 3 new mentions · 1 question
>
> **Robotics** · Acme Robotics (new): AI software that lets warehouse robot arms pick any item · Oct 6 Networking Night
> **AI for science** · Acme Sciences: +mention Oct 7 call with Jordan
> **Questions:** "Periodic" in a CSAIL email: Periodic Labs (AI for materials)?

On the first sync, show every company (it's the whole list). Wait for his reply and apply his edits. Save only after a clear OK.

### A6. Save and push
1. Edit `lists/companies.md` (format below): add rows, update mentions, keep sectors in the order of `companies.sectors` and rows A–Z within each sector, and update the count + date line at the top.
2. **Refresh the app** (every save, never skip): `python3 scripts/companies_to_app.py <scratchpad>/co | python3 scripts/webdb.py push - --replace`. `--replace` deletes any `companies` doc whose id isn't in the new writes. If the save fails, say so plainly.
3. Update `lists/companies-state.json`: `last_sync` = now (Boston, ISO); append each processed source id to `seen` (`{"source": "granola|note|email|calendar|network", "id": "...", "companies": ["..."]}`).
4. `git add lists && git commit -m "Companies: <what changed>" && git push` (with the Co-Authored-By line used in this repo). Inside `/today`, this goes in the same commit as the to-do list.
5. Tell Aman in one line: how many added/updated, and that it's on GitHub and in the app.

---

## B. Quick edits

1. `git pull`, open `lists/companies.md`.
2. Apply the change. For a new company, write *What they do* yourself and set *How I heard* to what Aman said (or `<today> · added by Aman`).
3. Refresh the app (A6 step 2), commit `Companies update: <what>`, push.
4. Reply in one line.

Aman's message *is* the instruction here; no separate approval step.

---

## File format: `lists/companies.md`

```markdown
# Companies

*32 companies · 8 sectors · updated Thu, Oct 8 · built by `/companies`*

A learning list: every company I've come across that fits my interests, by sector.

## Robotics

| Company | What they do | How I heard | Last seen |
|---|---|---|---|
| Acme Robotics | AI software that lets warehouse robot arms pick and pack any item | Oct 6 · Sloan Networking Night (met Jamie Rivera, Pat Kim) | 2026-10-06 |

## AI for science
...
```

Rules:
- Every sector in `companies.sectors` gets a heading, even if empty (`*None yet.*`).
- Short facts in your own words only. Never paste email, note or transcript text.
- No pipes (`|`) inside cells.
