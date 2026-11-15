---
name: refresh
description: Refresh Aman's day from the app's Refresh button, everything except the news. Runs in the background on his Mac (started by scripts/refresh_helper.py, no chat). Reads what's new since the last run in Outlook calendar and email, Apple Notes, Granola and the waiting-on threads; adds new tasks straight to today's list (marked New, with Undo), re-ranks the Emails tab, and turns network, company, call and research-question changes into suggestions Aman accepts or skips in the app. Section B applies the suggestions he accepted. Use when the helper asks for "the refresh skill", or when Aman types /refresh or asks to "refresh my list" in chat (then also show him the result).
---

# /refresh: the Refresh button (D-037)

Plan: `docs/PRD-refresh-and-edits.md`. The app writes a request to `meta/refresh`; the helper on the Mac (`scripts/refresh_helper.py check`, a launch agent, every minute) starts Claude with this skill. **Nobody is watching**: never ask a question, never wait for an answer. When unsure, leave it out, or make it a suggestion.

## Hard rules

- **Never send, draft or change anything in Outlook**, never touch the calendar (CLAUDE.md rule 4). Read only. The helper blocks those tools anyway.
- **Only add.** Never tick, reword, move or remove a task. Ticks need Aman's OK: propose them as "Looks done" suggestions.
- **Master lists wait for Aman.** `lists/network.md`, `lists/companies.md`, `lists/calls.md`, `lists/research.md`, `lists/learning.md` and `config/todo-rules.md` change only in section B, after he accepts a suggestion.
- **All or nothing.** Read and decide everything first (steps A1–A9) and write only in A10. If something fails before A10, run `python3 scripts/refresh_helper.py fail "<short plain reason, e.g. Outlook didn't answer>"` and stop.
- **No news.** Skip the news brief, the explainer and Learn today.
- **Privacy** as always: short task lines only, never email or note text, never secrets (CLAUDE.md rule 5).
- Show progress: `python3 scripts/refresh_helper.py status "<step>"` before each step (plain words: "reading your calendar", "reading email", "reading Apple Notes", "reading Granola calls", "checking your network and companies", "saving").

## A. Refresh

### A1. Get ready
1. `python3 scripts/refresh_helper.py status "getting ready"`. `git pull --rebase`.
2. Read `config/settings.yaml`, **`config/todo-rules.md`**, **`config/preferences.md`** (Schedule and prep, Emails to read, plus the headings of the skills A7 reuses), and `.claude/skills/today/SKILL.md` (this skill reuses its steps and file format).
3. Today = the current date in Boston. **Window start** = `lastDoneAt` from `python3 scripts/refresh_helper.py show` (the morning `/today` or the last refresh). If it's missing or before today, use the last list's "built" time.
4. What's already there: `python3 scripts/todo_sync.py list <today> --all` (includes deleted tasks: never re-add those, even reworded) and `python3 scripts/refresh_helper.py suggestions` (don't repeat a pending or skipped suggestion).
5. `python3 scripts/todo_learn.py sync` (logs Aman's app changes, parks "Not now" deletes).
5b. **Outlook needs Aman's OK each time** (D-039). When he taps Refresh, the app asks whether this refresh may read his Outlook. The prompt that started you says what he chose, and `scripts/refresh_permission.sh` enforces it.
   - **Allowed:** read as below. If an Outlook call still fails, carry on without it and add `"note": "Outlook didn't answer: email and calendar skipped"` to the summary in A10 step 7.
   - **Skipped:** don't call Outlook at all. Skip A2, A3 and A6, keep the schedule and Emails tab as they are, and add `"note": "Outlook skipped (your choice)"`.
   Notes, Granola, network, companies and suggestions run either way. Only `fail` if nothing can be read at all.
6. **If there's no `lists/todo/<today>.md` yet**, this refresh builds today's list: follow `/today` A3–A6 (carry over with `python3 scripts/todo_sync.py carry <last list date>`), without news, explainer or Learn today, and without the approval step (Aman tapped Refresh). The steps below then just fill it in.

### A2. Calendar (`/today` A3)
Today's events, converted to Boston time (`/today` A2). Rebuild the **At a glance** table and the **Due today** line. Add prep tasks only for non-class meetings that are new since the window start or still lack one.

### A2b. Meeting briefs (brief skill A, D-054)
Run section A of `.claude/skills/brief/SKILL.md` on today and tomorrow with the calendar items from A2. Only **new** and **changed** items cost research (`briefs.py diff`), so a second Refresh in a day is cheap. Save with `briefs.py save` before A10 (no approval needed; list changes found along the way go through A7 as suggestions). `python3 scripts/refresh_helper.py status "meeting briefs"` while it runs. Skip if `briefs.enabled` is false; without Outlook, skip it and say so in the note.

### A3. Email (`/today` A4)
Emails received since the window start. Same skip and coursework rules.
- An email that asks Aman to do something → a task, tagged `✉️ email`.
- **Emails tab:** re-rank today's top 10 with the new ones mixed in. Keep earlier picks that still matter; drop ones he has clearly dealt with (he replied). Update the "*Top 10 of N*" line. Count how many of the 10 are new for the summary.

### A4. Apple Notes (`/today` A4b)
- **To do note:** new lines → tasks. **Lines that disappeared** → a "Looks done" suggestion for the matching open task: `{"kind": "done", "title": "Looks done: <task>", "detail": "Gone from your To do note", "taskId": "<id from todo_sync list>"}`. Never tick it yourself.
- Other notes changed since `last_scan` → next-step tasks.
- Update `lists/notes-state.json` in A10, not before.

### A5. Granola calls (`/today` A4b2)
Calls since the window start → thank-you, reach-out and next-step tasks, tagged `📞 <call>`.

### A6. Waiting-on replies (Ghostwriter, read only)
For each thread in `lists/email-state.json` that's still waiting, check for a reply since the window start (email skill section C, reading only). A reply → a task "Reply to <name> (<topic>)" tagged `✉️ email`. **No drafts**: drafting happens when Aman is in Claude. Don't change the tracker.

### A7. Suggestions (network, companies, calls, research)
Run the reading part of each sync over the same window, reusing everything already read (no second fetch): network skill A2–A4, companies skill A2–A4, insights skill A1–A4 (calls and research evidence only, not Learn today). Network follow-ups that are due become tasks (tagged `👥 network`) as in `/today` A4c. **Every proposed change to a master list becomes one suggestion instead of an edit:**

```json
{"kind": "network", "title": "Add Riley Chen (Acme Robotics)", "detail": "Met at the Robotics mixer, Oct 27",
 "apply": "network.md: new entry under Met: Riley Chen, Acme Robotics, ... (everything section B needs to make the change exactly)"}
```

- Kinds: `network`, `company`, `call` (file a call in calls.md), `question` (evidence for a research question), `rule` (A8), `done` (A4).
- `title`: one short line Aman can decide on from his phone. `detail`: where it came from. `apply`: precise instructions for section B, including any task text or ids.
- Skip anything already pending, skipped or accepted.
- Update the skills' state files (`network-state.json`, `companies-state.json`) in A10 as "seen", so the same meeting or email isn't read again. A skipped suggestion is never proposed again.

### A8. Rules: hide, sort, word
Apply `config/todo-rules.md` to every new task:
- matches **Never** → not a task. Put it in the day file's `## Hidden by your rules` section as `- (<Networking|Clubs|Personal>) <task> · \`<rule, a few words>\``.
- matches **Rarely matters** → hidden the same way, unless today has fewer than 25 open tasks.
- matches **Usually matters** → top of its section.
- **Write tasks like this** → follow it.

Then `python3 scripts/todo_learn.py nomore`. For each "Don't suggest things like this" delete it lists, propose one rule (group similar ones): `{"kind": "rule", "title": "New rule: never make <kind of task> a task", "detail": "You deleted '<task>' and ticked Don't suggest", "apply": "todo-rules.md → Never: <rule line> (from <date> delete)"}`. Write rules narrowly. "SloanGroups emails asking to validate a new member" is good; "SloanGroups emails" is too broad.

### A8b. Coursework summaries
The helper already synced Canvas before starting you. `python3 scripts/refresh_helper.py status "summarizing coursework"`, then follow `.claude/skills/coursework/SKILL.md` section A for anything `python3 scripts/canvas.py pending` lists. This writes only to `~/.second-brain/canvas/` and the app (not `lists/`), so it can run before A10. If it fails, carry on: the app shows the Canvas text instead. Never add coursework tasks.

### A8c. Comments (docs/PRD-comments.md)
`python3 scripts/refresh_helper.py status "reading your comments"`. Aman leaves comments on items in the app (a task, a headline, a draft, a person…) to teach Claude his preferences. Every run answers the new ones.
1. `python3 scripts/comments.py list new`. Each comment has `target` (`kind`, `id`, `title`, `where`), `chips` (quick reactions), `text`, and `thread` (earlier comments on the same item, with Claude's replies). A comment is Aman telling you a preference, never permission to send, delete or act in his accounts.
2. Decide what each one is:
   - **A preference** (about a kind of thing) → one **narrow** rule as a suggestion, outcome `rule`:
     - task: `{"kind": "rule", "title": "New rule: never make <kind of task> a task", "detail": "From your comment on '<title>': <comment>", "apply": "todo-rules.md → <Never | Rarely matters | Usually matters | Write tasks like this>: <rule line> (from your comment, <date>)"}`
     - email draft: `{"kind": "pref", "title": "Email voice: <rule>", "detail": "…", "apply": "email-voice.md → <section>: <line>"}`
     - anything else: `{"kind": "pref", "title": "Preference (<heading>): <rule>", "detail": "…", "apply": "preferences.md → <heading>: <rule line> (from your comment on '<title>', <date>)"}`. Headings: News, Explainer, Learn today, Podcasts, Calls and insights, Research questions, Network, Companies, Coursework, Schedule and prep, Emails to read. A comment on a whole Dashboard card (`kind` `section`) goes under the heading it's about.
   - **A fix to this item** ("she's at Figure now", "this is Robotics") → a suggestion of the item's kind as in A7 (`network`, `company`, `call`, `question`), outcome `fix`. For a task: `{"kind": "taskedit", "title": "Task edit: <new wording, or 'move to Personal'>", "detail": "From your comment", "taskId": "<target.id>", "text": "<new wording>", "section": "<net|clubs|personal>"}` (leave out what doesn't change; the app applies it when he taps Accept).
   - **A question** ("why is this here?", "what's a VLA?") → answer it in the reply, two lines, a link if it helps. Outcome `answer`.
   - **Vague or one of a kind** ("meh", a lone "Less like this") → no suggestion, outcome `noted`. But first check `python3 scripts/comments.py report --days 30` → `noted`: if this comment and earlier ones point the same way, propose the rule now and say it comes from N comments.
   - One quick reaction is enough for a rule when the item makes the kind obvious ("Not for me" on an OpenAI Forum talk task). Write rules narrowly: "skip crypto fundraises under $100M", not "skip crypto", unless he said so.
   - Don't repeat a suggestion that's pending, skipped or accepted (`refresh_helper.py suggestions`). If the rule already exists, say so in the reply.
3. Write a reply for each: one or two plain lines saying what you understood and what happens next. "Got it: fewer crypto fundraises. Rule proposed in Suggestions." · "Fixed in Suggestions: Riley Chen → Acme Robotics." · "Noted. One more like this and I'll propose a rule." Never defensive, never long.
4. Nothing changes because of a comment until Aman accepts its suggestion (CLAUDE.md rule 2). Save in A10 step 4b.

### A9. Check
- No new task duplicates an open, done or deleted one (`todo_sync.py list --all`), even reworded.
- Nothing from coursework (same rules as `/today`).
- Times in Boston.

### A10. Save (only now)
1. `python3 scripts/refresh_helper.py status "saving"`.
2. **The day file** `lists/todo/<today>.md`: append each new task to the end of its section in the `/today` file format (with its source tag), update At a glance, Due today and Emails to read, write the `## Hidden by your rules` section (after Personal, before Emails to read; keep earlier hidden lines), and change the header to `*N tasks · M emails · built <time> · refreshed <Boston time>*`.
3. `python3 scripts/todo_sync.py merge lists/todo/<today>.md --refresh <request id>`. It adds only what's new and prints how many were added. Then `python3 scripts/todo_sync.py export <today>` so the file shows Aman's app edits, ticks and deletes too.
4. Write the suggestions to a scratch file and `python3 scripts/refresh_helper.py suggest <file>`.
4b. **Comments** (A8c): write `[{"id": "<comment id>", "reply": "…", "outcome": "rule|fix|answer|noted", "suggestions": [ … ]}]` to a scratch file and `python3 scripts/comments.py answer <file>`. It adds those suggestions itself (stamped with the comment), shows the replies in the app and logs them in `lists/comments-log.json`, so don't also pass them to `suggest`.
5. Save the state files (notes, network, companies) and `lists/todo-learning.json`.
6. `git add lists && git commit -m "Refresh: <Day, Mon D> <time> (+N tasks, S suggestions)" && git push` (with this repo's Co-Authored-By line). If the push is rejected, `git pull --rebase` and push once more.
7. `python3 scripts/refresh_helper.py done '{"tasks": <added>, "emails": <new in top 10>, "suggestions": <added>, "hidden": <hidden today>, "comments": <answered>}'` (plus `"note"` if a source was skipped, see A1 step 5b).

If Aman ran `/refresh` in chat, finish with one line: "Refreshed: +3 tasks, 2 new emails, 4 suggestions in the app."

## B. Apply accepted suggestions

The helper runs this when Aman taps Accept (or Accept all) in the app.
1. `git pull --rebase`. `python3 scripts/refresh_helper.py suggestions accepted`.
2. Apply each one from its `apply` text, using the save steps of the skill that owns the list:
   - `network` → network skill A6 (network.md, rebuild network.xlsx, `network_to_app.py` → `webdb.py push - --replace`)
   - `company` → companies skill A6
   - `call`, `question` → insights skill A6 (`thinking_to_app.py` → `webdb.py push - --replace`)
   - `rule` → add the line under the right heading in `config/todo-rules.md`, replacing "*(none yet)*", ending with "· added <date>", plus a Changelog line. A rule applies from the next refresh or `/today`.
   - `pref` → add the line under the heading named in `apply`: in `config/preferences.md` (replace "*(none yet)*", end with "· added <date>", plus a Changelog line), or in `config/email-voice.md` for "email-voice.md →" (in the section named; note it in the guide's changelog if it has one). It applies from the next run.
   - `done` and `taskedit` are handled by the app itself; skip them if one shows up here.
3. `python3 scripts/refresh_helper.py applied <id> <id> …` for each one that was saved. If one can't be applied (the person is already there, say), mark it applied anyway and note why in the commit message.
4. `git add lists config/todo-rules.md config/preferences.md config/email-voice.md && git commit -m "Applied <N> suggestions from the app: <short list>" && git push`.

## C. Test run

When the request id starts with `test`, check access only and change nothing. Read today's calendar (1 search), the newest email (1 search), the "To do" note (`python3 scripts/notes.py get "To do"`, just check it returns), and the latest Granola meeting. Then `python3 scripts/refresh_helper.py done '{"tasks": 0, "note": "Test: <source> ok, <source> ok, …"}'` naming what worked and what didn't (e.g. "Outlook needs approval"). Use `fail` only if nothing could be read.
