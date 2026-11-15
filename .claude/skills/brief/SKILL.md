---
name: brief
description: Meeting briefs for the app's Meetings tab. For every meeting that matters (company chats, interviews, investors, Sloan peers about their summer employer, professors, advisors, events), research the person and the company and write a brief - the 60-second version, goal and ask, questions to ask, the person, the company, Aman's history with them, a 30-second intro, watch-outs, plus an interview pack or event brief - with a source on every fact and a two-signal identity check. Saves with scripts/briefs.py into the app. Use when /today or the Refresh runs its briefs step, when the Mac helper asks for "the brief skill" (Brief me taps), or when Aman types /brief or says "brief me on my 2 PM", "prep me for Sam", "who am I meeting tomorrow?". Plan: docs/PRD-meeting-briefs.md.
---

# /brief: meeting briefs (D-054)

Plan: `docs/PRD-meeting-briefs.md`. Engine: `scripts/briefs.py` (run with no arguments for its commands). Briefs live in the app's `briefs` collection and in `lists/briefs/<date>.json` + `.md`; `lists/briefs-state.json` remembers which events are briefed, the research on each person and company (reused for 30 days) and what Aman taught it.

## Hard rules
- **Read only.** Never send or draft email, never touch the calendar (CLAUDE.md rule 4). Thank-you drafts are Ghostwriter's job.
- **Right person or nothing.** A person counts as **matched** only on two signals (name plus one of: their email domain, a LinkedIn URL in the invite or a signature, the company in the network tracker, the role in their signature, the school). Otherwise `"match": "unsure"` with 1–3 candidates, no person section, and nothing found about a candidate used anywhere else in the brief.
- **Every fact has a source** (`src` numbers) or comes from Aman's own data (a source with `"mine": true`). No guessed titles, invented quotes, assumed funding or "probably" facts. Unknowns go in a "Couldn't find" line. Aggregator-only numbers (funding lists, CB Insights snippets) are labelled as such or left out.
- **Privacy** (PRD section 8): web searches carry only names, companies, titles and public topics, never email text, notes, call content or Aman's plans. Research people's professional and public lives only: no addresses, family, health, politics or religion, even if found. LinkedIn only through search results and public pages; never log in.
- **No email or note text in briefs**: one-line summaries of touchpoints only (CLAUDE.md rule 5).
- **Briefs save without approval** (like the news brief, D-024). Changes to Aman's lists found along the way (someone changed jobs, a company worth adding) become suggestions, never edits (rule 2).
- **Capacity:** briefs are made only inside `/today`, Refresh, Brief me and chat (D-048). At most `briefs.max_full_per_day` full briefs per day; the rest are light.
- Times always in Boston time (rule 8). Aman's Outlook returns India Standard Time: until Sun Nov 1, 2026 Boston = IST − 9h30; from Nov 1, 2026 Boston = IST − 10h30.

## A. Brief a range of days (from `/today` A3b and the Refresh's A2b)

### A1. Get ready
1. Read `config/settings.yaml` → `briefs`, **`config/about-me.md`** (background, recruiting focus, intro blocks, story bank) and the **"Meeting briefs"** heading of `config/preferences.md`.
2. `python3 scripts/briefs.py sync` (Aman's ratings, kind changes and person picks from the app → state file). Read `lists/briefs-state.json` → `overrides` (kind per email or title) and `picks`.
3. Range: `/today` = today + the next `look_ahead_days` (default: today and tomorrow). Refresh = today and tomorrow.

### A2. Calendar → events.json
Reuse the calendar items `/today` A3 or the Refresh A2 already read (in `/today`, the outlook-digest's `↳ id …` detail lines under today's and tomorrow's items); don't search twice. Only if an item lacks its detail line, look up that one event with `outlook_calendar_search`. Write every item in the range to a scratch `events.json` in the shape `briefs.py` documents (Boston date and 24h times, `attendees` = emails other than you@example.edu, `where` short, `cancelled`). Keep each item's join link (Zoom / Teams / Meet), organiser, and the invite body's useful lines (booking-page LinkedIn links, agendas, "AI notetaker") for later; never save the body.

### A3. What needs doing
`python3 scripts/briefs.py diff events.json` →
- **new** → brief it (A4–A9).
- **changed** → time only: update `start`/`end`, set `status: "updated"` (or `"moved"` if the day changed) and keep the research; attendees changed: research the new people; `cancelled` → save it with `status: "cancelled"` and its old content.
- **gone** (no longer on the calendar) → save with `status: "cancelled"`.
- **same** → nothing, except the **news check**: a full brief researched more than `news_check_before_days` before its meeting, when the meeting is tomorrow → refresh only "What's happened lately" in the company section (3–4 searches) and set `status: "updated"`.

### A4. Sort each item into a kind
Apply in order; the first that fits wins.
1. **Override** for any attendee email or the title in `overrides` (Aman changed it in the app) → that kind.
2. **none:** classes (course number subjects, category Class), `DUE:` / deadlines / all-day items, anything in `briefs.skip_titles`, the core team (his core team), club exec meetings, case practice, Comms Lab, personal items (friends, no professional context), cancelled items.
3. **interview:** recruiting systems (Ashby, Greenhouse, Lever, Gem, GoodTime), a recruiting calendar as organiser, "interview" / "chat with <company>" from a company, or a recruiter thread.
4. **investor:** a VC firm's domain or a network-tracker person in VC.
5. **event:** Luma, Eventbrite, Zoom Events, CSAIL talks, conference agenda items, socials and nights with no single host. Back-to-back sessions of one conference become one event brief on the first item; the others are `none` with `cameAbout: "Part of <conference>: see the <time> brief"`.
6. **professor:** MIT faculty or office-hours booking pages (Calendly / YouCanBook.me from a faculty member).
7. **advisor:** MIT CDO, known mentors, career coaches.
8. **peer:** a Sloan/MIT student (mit.edu, or the network tracker says "Sloan (summer 2026 at X)") whom Aman is meeting about a company.
9. **company:** anyone else at a company.

**Depth:** interview, company, investor → **full**; peer → **full** on the company and light on the person (counts as full); professor, advisor → **light**; event → **event**; none → **none**. Over the daily cap → make the latest-in-the-day non-interview ones **light** and say "Brief me for the full version" in `cameAbout`. Interviews are never cut.

### A5. Who is each person (identity check)
For each external attendee: their email, name from the invite, the network tracker (`lists/network.md` table + entry), the calls list, the email threads with them (`outlook_email_search` by sender/recipient; read only the 2–3 most relevant) and their signatures. Record `matchedBy` in plain words ("name + @example-vc.com + Example's team page"). Personal emails with a first name only → unsure unless the tracker or emails say who they are. If Aman picked a candidate before (`picks`), use it.

### A6. Aman's own data first
Gather before searching the web, so searches are precise:
- **How it came about:** the outreach, intro or booking (one line: "You booked it after the industry summit, Oct 30", "Intro from Jordan Lee").
- **Touchpoints**, newest first: emails (one line each), Granola calls (`lists/calls.md`: "In one line" + link), Apple Notes mentions, events.
- **Promises** both ways and whether they happened (check sent mail).
- **What other people said** about this company (calls list insights, network entries) and the companies list entry, research questions it touches (`lists/research.md`), recent news briefs that mention it (`lists/news/`, last 30 days).
- **Goal:** from the outreach email, the task list and `config/about-me.md` → Recruiting focus.

### A7. Research (web)
1. **Reuse:** `python3 scripts/briefs.py profile "<email or name>"` and `profile "<company>"`. If `reuse` is true, copy those rows (keep their sources) and only search for news since `researchedAt`. "Brief me again" requests skip reuse.
2. **Full briefs:** one `researcher` agent (Sonnet) per brief, all launched in parallel in one message, each with: the person's name, email domain and what A5/A6 already know, the company, the meeting kind, Aman's goal, and the exact list of what to find (sections 5e, 5f and, for interviews, 5j of the PRD), "every fact with a URL and date", "mark anything unconfirmed", "only public professional information", a budget of about 15 searches, and "return a compact structured list, max 600 words". Interviews also ask for: the job posting (careers / Ashby / Greenhouse page), the interview process if public, the last 90 days of company news.
3. **Light briefs:** 3–6 searches yourself or one small agent (professor: research page, recent papers, courses, companies they advise; advisor: usually none needed).
4. **Event briefs:** the agenda page, speakers (one line each), companies present; then match against the network tracker and companies list for "who might be there".

### A8. Write the brief (format: section D)
Write from the findings; never paste raw search results. Plain words, short lines, Aman's level (MBA, ex-McKinsey, technical background). The intro is in his voice (`config/email-voice.md`: no dashes, plain words) built from `config/about-me.md` intro blocks. Questions are specific to this person and this week, never answerable by a search, each with why it's worth asking, top 3 starred. Interview stories come from the about-me story bank; if a theme has no story, say "add your story" rather than inventing one.

**Prep listen** (D-055): every full, interview, investor and event brief gets `"listen": {"topic": "…", "why": "…"}`: the one **public** subject worth an 8-minute listen before this meeting, phrased as a plain question ("How do early-stage funds like Example Ventures pick physical AI deals?", "Why are warehouse robots finally getting bought?"). It comes from the goal and the company section: the company's market or technology, the investor's thesis, the speaker's field, the role's domain for an interview. **Never the person's name, the meeting or anything from Aman's own data**: the topic goes to Google's NotebookLM (`briefs.py check` refuses a topic that names an attendee). `why` is one private line on what it prepares ("so you can ask about their seed thesis"). The morning podcasts use it to make a prep episode (podcast skill E2), and the brief shows **🎧 Prep podcast**.

Spotting problems is part of the job: a join link that doesn't match what they asked for (Zoom vs Teams), a clash with another meeting, a missing RSVP, travel time between rooms, an AI notetaker, a meeting with no agenda. Put the most important one in `alert`. If it needs Aman to act, also propose a task (A10).

### A9. Check and save
`python3 scripts/briefs.py check briefs.json`, fix every ✗, then `python3 scripts/briefs.py save briefs.json` (loads into the app, keeps Aman's taps, writes `lists/briefs/<date>.json` + `.md` and the state). Include the `none` items so the Meetings tab shows the whole day. Commit `lists/briefs/` and `lists/briefs-state.json` with the run's other changes.

### A10. Back to `/today` or the Refresh
- **Prep tasks** (PRD decision A10): instead of "3 questions for X", the task is "Read <first name>'s brief (<N> min) · <time>" tagged `📅 <day time>`, with `"brief": "<brief id>"` in its source so the app links it. Keep a separate task only for a real action (fix the join link, RSVP, send something first, resolve a clash).
- **Suggestions**, never edits: a person's new role, a company worth adding to `lists/companies.md`, a person to add to the network tracker (same JSON as the refresh skill A7, via `refresh_helper.py suggest` in a refresh; in the `/today` draft's Network/Companies blocks otherwise).
- **In the `/today` draft:** a **Meetings** block: one line per brief ("Mon 1:00 PM Taylor Brooks (Acme, peer chat): brief ready, 3 min"), alerts first, then "N meetings need no brief".

## B. Brief me requests (background, started by the Mac helper)
The prompt names the request ids. Nobody is watching: never ask questions.
1. `python3 scripts/briefs.py working <ids>`. Read A1.
2. For each: `python3 scripts/briefs.py requests` gives `request` (`brief` = make one, even for a `none` item; `again` = fresh research, no reuse; `deeper` = full depth plus more on the person and company), the brief id, date, time and title. Find the event in the calendar (Outlook calendar search on that Boston day, matching title and time) when Outlook is allowed; otherwise use the saved brief's details and say "Calendar not checked" in `cameAbout`.
3. Do A4–A9 for that one item (a `none` item asked for becomes at least `light`; the kind follows A4 without the none rules). The daily cap doesn't apply to Brief me.
4. If it can't be done (the event is gone, nothing could be read), `python3 scripts/briefs.py fail <id> "<plain reason>"`. Commit and push what was saved.

## C. Chat requests
"brief me on my 2 PM", "prep me for Sam", `/brief tomorrow`, "who am I meeting this week?":
- A specific meeting → B steps 2–3 for it (Outlook is fine in chat), then show the 60-second version and the top 3 questions in chat, and say it's in the Meetings tab.
- A day or a week → A for that range, then a short list like the `/today` Meetings block.
- "brief me anyway" on a `none` item, "this isn't an interview" → treat as an override: save the brief with the new kind and record it (the next `sync` keeps it).
- After saving: commit and push (rule 1).

## D. The brief format (what `briefs.py save` and the app read)
One JSON object per calendar item:

```json
{
 "eventId": "<Outlook event id>", "date": "2026-11-05", "start": "14:00", "end": "14:30",
 "title": "Sam <> Aman (Sloan MBA'28)", "where": "Online", "join": "https://teams.microsoft.com/…", "joinLabel": "Teams",
 "attendees": ["sam@example-vc.com"],
 "kind": "investor", "depth": "full", "status": "ready", "readMin": 4,
 "cameAbout": "You met at an AI summit last week and asked for 30 minutes.",
 "alert": "She asked for Zoom (she's travelling), but your invite has a Teams link. Send a Zoom link or check Teams works for her.",
 "clash": "",
 "company": "Example Ventures",
 "people": [{"name": "Sam Rivera", "title": "Investing Principal", "org": "Example Ventures", "email": "sam@example-vc.com",
             "match": "matched", "matchedBy": "name + @example-vc.com + Example's team page", "candidates": []}],
 "sixty": {"who": "…", "why": "…", "goal": "…", "open": "…", "ask": "…"},
 "listen": {"topic": "How do early-stage funds pick physical AI deals right now?", "why": "So you can ask where Example lands on humanoids vs vertical robots"},
 "sections": [
  {"key": "questions", "title": "Questions to ask", "items": [{"text": "…", "why": "…", "star": true, "src": [3]}]},
  {"key": "person", "title": "Sam Rivera", "rows": [{"label": "Now", "text": "…", "src": [1]}]},
  {"key": "company", "title": "Example Ventures", "rows": [{"label": "What they do", "text": "…", "src": [2]}]},
  {"key": "history", "title": "You and Sam", "items": [{"text": "Oct 30 · …", "src": [8]}]},
  {"key": "intro", "title": "How to introduce yourself", "text": "…"},
  {"key": "watchouts", "title": "Watch-outs", "items": [{"text": "…"}]},
  {"key": "missing", "title": "Couldn't find", "items": [{"text": "…"}]}
 ],
 "sources": [{"n": 1, "title": "Example Ventures team page", "url": "https://www.example-vc.com/team", "date": "2026"},
             {"n": 8, "title": "Your emails with Sam (Oct 30)", "mine": true}]
}
```

- **Section keys and order:** `questions`, `person`, `company`, `history`, `intro`, `interview` (interview kind: rows Role, This round, How they interview, then items for likely questions with `why` = "Your story: …", and "Your why us"), `event` (event kind: rows Speakers / Companies / Who you know / People worth meeting / Logistics, plus items for Q&A questions), `watchouts`, `missing`. Leave a section out rather than pad it.
- **Light briefs:** `sixty` (who, why, goal, ask), `questions` (3–5), `person` (3–4 rows), `history`, `missing`. **Event briefs:** `sixty` (why, goal, ask), `event`, `questions`. **none:** just the calendar fields with `kind: "none"`, `depth: "none"` and an optional `cameAbout`.
- **Person rows:** Now · Path · In their own words · Common ground · Links · (each with `src`). **Company rows** (5f): What they do · How they make money · Stage and scale · Leadership · Lately (dated items) · Competitors · Where an MBA fits · Why it matters to you. Investors: Fund · Stage and cheque · Thesis · Portfolio · Recent deals · Partners · Students and fellows.
- **Peer kind:** the company section comes before the person, with "How MBAs get in" and "Recruiting timeline" rows.
- `readMin`: words in sixty + sections ÷ 200, rounded up. `**bold**` is allowed inside text; nothing else.
- When a meeting has repeat history, the first `history` item starts with "Since last time:".
- `after` (written by section E): `{"callId", "callLine", "granola", "draftId"}`.

## E. After the meeting, and learning
- In `/today` A4b2 and the Refresh A5, when a Granola call matches a brief (same person or title, same day), add `after: {callId, callLine, granola}` and Ghostwriter's thank-you `draftId` if there is one, and save the brief again (`briefs.py save`; Aman's rating is kept).
- **Sunday review** (`/today` section C): `python3 scripts/briefs.py report --days 7` → one line ("12 briefs, 9 rated: 7 useful, 2 too long (peer chats)"), plus at most two proposed rules for `config/preferences.md` → "Meeting briefs" when a pattern repeats (≥2 same ratings on the same kind). Only rules Aman OKs are added.
- Comments (💬) on a brief or its sections are answered by the comments step like any other item; accepted rules go under "Meeting briefs".
- Monthly: `python3 scripts/briefs.py cleanup` (briefs older than 90 days leave the app; the repo keeps them).
