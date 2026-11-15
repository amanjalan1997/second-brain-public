---
name: network
description: Keep Aman's network tracker (lists/network.md) up to date. Reads new Granola meeting notes, Apple Notes about people, Outlook emails about internship/full-time opportunities, and coffee-chat requests Aman sent; matches each person to an existing entry or proposes a new one; shows the changes for approval, then saves, rebuilds the Excel copy and pushes. Also handles quick edits ("met X", "add contact: ...", "X is at Y now"). Use when Aman types /network, asks to update his network or contacts, mentions a call he just had, or when /today runs its network step.
---

# /network: the network tracker

Aman is not technical. Keep messages short and plain. **Never save changes he hasn't approved.**

Settings live in `config/settings.yaml` under `network`. Read them first; if they disagree with this file, settings.yaml wins.

Files:
- `lists/network.md`: **the master.** Summary table at the top, one profile per person below.
- **Web app, Network tab** (https://your-app.vercel.app; web app only since D-036): read-only view of the tracker (search, status filters, tap for a profile). Its database holds `people/<slug>` (one per person) and `meta/network`. Rebuilt from network.md by `python3 scripts/network_to_app.py <out_dir>`. Never edit it by hand.
- `lists/network.xlsx`: Excel copy for sorting/filtering. Rebuilt by `python3 scripts/network_xlsx.py`. Never edit it by hand.
- `lists/network-state.json`: memory of what was already read (`last_sync`, `seen`), so nothing is processed twice.

## What Aman might say

| He says | Do |
|---|---|
| `/network`, "update my network", "I just had a call with X" | **Sync** (section A) |
| "met X", "X: <fact>", "add contact: X at Y", "X moved to Y" | **Quick edit** (section B) |
| "who do I need to follow up with?" | List open follow-ups and keep-warm nudges (section C) |

---

## A. Sync

### A1. Get ready
1. `git pull`. Read `config/settings.yaml` (`network`) and `lists/network-state.json`. Follow the **Network** heading of `config/preferences.md` (rules Aman approved from his comments in the app).
2. Window = since `last_sync` (minus a day of overlap). If there's no `last_sync`, look back `network.first_sync_days`.
3. Time zones: Outlook returns India Standard Time. Boston = IST − 9h30 until Nov 1, 2026, then IST − 10h30. Granola returns Eastern already. Always write Boston time.

### A2. Gather (skip anything whose id is already in `seen`)
1. **Granola.** `list_meetings` (custom range = the window), then `get_meetings` for new ids. Each meeting with a person other than Aman is an interaction. Use the attendees list for names and emails; the summary for facts and next steps. Meetings with no other attendee (e.g. "CDO PM advisor meeting") still count if the title or summary names who it was with.
2. **Apple Notes.** `python3 scripts/notes.py since <hours>`. A note is about people when its title is a name, a company, or `MM/DD <name or company>`, or when it lists people to "reach out" to / "connect with". Skip `sources.notes_app.skip_notes`, the "To do" note (but do read names under its *Follow-ups* / *Outreach* headings), and anything coursework. Key: note title + modified time.
3. **Outlook: opportunity emails.** `outlook_email_search` with `query` for each of `network.email_keywords`, plus `afterDateTime`. Keep only emails **written by a real person** (to or from Aman) about an internship, full-time role, interview, or referral. Throw out newsletters, mailing lists (`sloangroups`, `campusgroups`, `12twenty` notifications, `*-announce`), Canvas, and course emails. Key: conversation id.
4. **Outlook: coffee chats Aman requested.** Search with `sender` = Aman's email and `query` for each of `network.coffee_chat_phrases`. Every person he asked for time is a contact (status at least *Reached out*). Read the thread to see if they replied or a time was set.
5. **Calendar (support only).** `outlook_calendar_search` over the window and the next 14 days for 1:1s with the people found above, to fill in *Scheduled* dates and confirm meetings happened. Don't add people from the calendar alone; ask instead.

Open (`read_resource`) only what you need to get names, roles, dates and the gist.

### A3. Match each person
1. **Email address** match → same person.
2. Else **full name** match (ignore case, accents, nicknames: Chris = Christopher, Alex = Alexander, Sam = Samuel) → same person.
3. Else **first name + company** match → probably the same: say so in the draft with a `?`.
4. Otherwise → new person.

If two entries look like the same person, or a source gives a different spelling or company than the list, ask. Never merge or rename silently.

### A4. Build the changes
For an **existing** person, propose only what's new:
- a **log** line: `- YYYY-MM-DD · <channel> · <gist> (<source>)` (newest first),
- new **What I learned** bullets (short facts, never raw transcript or email text),
- new **follow-ups** (`- [ ] ...`), and tick off ones that are clearly done,
- updates to **Last contact**, **Next step**, **Status**, contact email, role.

For a **new** person, propose a full entry (table row + profile) with what's known. Leave unknown fields blank.

Status moves forward only: To reach out → Reached out → Scheduled → Met → Keep warm. (A person stays *Met* while follow-ups are open; *Keep warm* once there's nothing pending.)

**Keep-warm nudge:** anyone whose Last contact is older than `network.keep_warm_after_weeks` and has status Met / Keep warm gets a suggested next step "Check in (last spoke <date>)".

### A5. Show the draft and get approval
Show a compact summary in chat, not the whole file:

> Network update: 2 new · 4 updated · 3 follow-ups · 1 question
>
> **New:** Dana Park (Acme, Growth Strategist) · call Oct 2 · follow-up: email to stay in touch
> **Updated:** Alex Morgan · call Oct 5 · +3 learnings · follow-up: send transcript
> **Questions:** "Sam Archer" in your list vs "Sami Archer" in email: same person?

Wait for his reply and apply his edits. Save only after a clear OK.

### A6. Save and push
1. Edit `lists/network.md`: table rows (sorted: Met / Reached out first by most recent contact, then Scheduled, Keep warm, To reach out), profiles (same order as the table), and the count + date line at the top.
2. Run `python3 scripts/network_xlsx.py`.
2b. **Refresh the app** (every save, never skip): `python3 scripts/network_to_app.py <scratchpad>/net | python3 scripts/webdb.py push - --replace`. `--replace` deletes any `people` doc whose id isn't in the new writes (renamed or removed people). If the save fails, say so plainly.
3. Update `lists/network-state.json`: set `last_sync` to now (Boston, ISO); append every processed source id to `seen` (`{"source": "granola|note|email|calendar", "id": "...", "person": "...", "status": "added|updated|ignored"}`).
4. `git add lists && git commit -m "Network: <what changed>" && git push` (with the Co-Authored-By line used in this repo).
5. Tell Aman in one line: how many added/updated, and that it's on GitHub.

---

## B. Quick edits

1. `git pull`, open `lists/network.md`.
2. Apply the change to the table and the profile (add a log line dated today for "met X"). For a new person, ask for anything essential that's missing (company at least).
3. Rebuild the Excel copy, refresh the app (A6 step 2b), commit `Network update: <what>`, push.
4. Reply in one line.

Aman's message *is* the instruction here; no separate approval step.

---

## C. Follow-ups (also used by /today)

Collect every unticked `- [ ]` follow-up in `lists/network.md`, plus keep-warm nudges (A4), plus *Scheduled* meetings in the next 2 days (as prep). `/today` puts these under **Networking / Professional**, tagged `👥 network`.

---

## Rules
- Short extracted facts only. Never paste transcripts, email bodies or note text into the repo.
- Never copy secrets (API keys, passwords, meeting passcodes, phone numbers from signatures unless Aman asks).
- Coursework, classmates in project teams, and admin staff (IT, parking) are not network contacts unless Aman says so.
- When unsure whether someone belongs, ask rather than add.
