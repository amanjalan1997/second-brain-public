---
name: today
description: Build Aman's daily to-do list from his Outlook calendar and email, his Apple Notes (the 'To do' note plus next steps in meeting notes), carry over unfinished personal items, rank the top emails to read, and also run the network and company-list updates, the morning news brief, the explainer (3–5 stories explained simply) and the insights step (file new calls, add evidence to research questions, pick today's topic to learn); get his approval, then save everything, refresh the app (Today, Emails, News, Network and Companies tabs, plus the laptop Dashboard, Calls & notes and Research & learning views) and push to GitHub. Also handles quick updates during the day ("done: ...", "add personal: ..."). Use when Aman types /today, asks for his to-do list or morning update, or ticks off or adds an item.
---

# /today: the daily to-do list

Aman is not technical. Keep messages short and plain. **Never wait for his input (D-053):** run every step, pick sensible defaults for open questions, save, update the app and push, then report in one short message. His feedback comes as comments in the app (A4i on the next run).

**The app** (https://your-app.vercel.app, web app only since D-036) is where Aman reads, ticks, **edits and deletes** his tasks. Its database (Supabase, via `scripts/webdb.py`) is the **source of truth for tasks**: `days/<YYYY-MM-DD>` holds the schedule, emails and hidden items, and `tasks/<id>` holds one task each (`day`, `section` net|clubs|personal, `text`, `source` {kind, label}, `done`, `order`, `unsure`, `key` = fingerprint of the wording; plus, once he's touched it, `originalText`, `edits`, `deleted`, `deleteReason`, `noMore`). Deleted tasks stay in the database, hidden, so Claude can learn from them and never re-adds them. The markdown file in `lists/todo/` is the GitHub backup; `scripts/todo_sync.py` keeps the two in step (D-037). **Never save tasks any other way**: `todo_sync.py merge` only adds, so Aman's ticks, edits and deletes survive.

The rules live in `config/settings.yaml` (sections `todo`, `emails`, `sources`) and **`config/todo-rules.md`** (what Aman has taught Claude matters and doesn't, from his deletes and edits). Read both first and follow them. If settings.yaml disagrees with this file, settings.yaml wins.

The app's **Refresh** button runs the `refresh` skill on the Mac: this list's steps without the news, adding new tasks straight away and turning master-list changes into suggestions (D-037).

**Keep the run lean (D-052).** Every step of this chat re-reads everything said so far, so a long run with raw dumps in it is what makes `/today` expensive. So:
- Outlook is read by the **`outlook-digest` agent** (cheaper model), never in this chat; it returns a short digest. If one detail is missing, open just that message (`read_resource` with its id).
- The news is searched by **3 `researcher` agents** with caps (news skill A2).
- **One script to get ready** (`scripts/today_prep.py`, A1) and **one to save** (`scripts/today_save.py`, A8).
- In between: chain shell commands into one call, don't re-read a file you already printed, and don't look up a script's `--help` when the command is written in this file or the skill you're following.

## What Aman might say

| He says | Do |
|---|---|
| `/today`, "morning update", "build my list" | **Build** (section A) |
| "done: X", "finished X" | **Tick off** (section B) |
| "add <section>: X", e.g. "add personal: book flight" | **Add** (section B) |
| "drop X", "move X to Clubs" | **Edit** (section B) |

---

## A. Build today's list

### A1. Get ready
1. `python3 scripts/today_prep.py`: one command that pulls the repo and prints everything this run needs from the Mac. That covers today's Boston date and the Outlook offset, the last list, what Aman did in the app (`todo_learn sync`: deletes, rewordings, moves, ticks; "Not now" deletes go to `lists/parked.md`), the carry-over (A6), "don't suggest" deletes (A4h), the Apple Notes "To do" note and changed notes (A4b), new comments (A4i), the Canvas sync (A4g2), due email follow-ups and the last-run times. Use its output; don't run those scripts again.
2. Read `config/settings.yaml`, `config/todo-rules.md` and `config/preferences.md` (Schedule and prep, Emails to read; the other skills read their own headings) in the **same** shell call as step 1.
3. **Start the helpers now, in one message, in the background**, so they work while you do A4b–A4b2:
   - the **3 news agents** (A4e, `.claude/skills/news/SKILL.md` A2);
   - the **`outlook-digest` agent** (A3–A4). Prompt: "Outlook digest for /today. Today is <Day, Mon D YYYY> (Boston); the last list is <date>." Add a wider email window only after a gap of more than a day.

### A2. Time zones (important)
The digest is already in Boston time. If you ever call an Outlook tool yourself: Aman's mailbox is set to **India Standard Time**, so the tools return IST wall-clock times. Convert every time to Boston before showing it:
- Until **Sun Nov 1, 2026**: Boston = IST − 9h30 (EDT)
- From **Nov 1, 2026**: Boston = IST − 10h30 (EST)

When searching, use a wide window (from the day before to 2 days after), then convert and keep only what falls in the right Boston days. If an event arrives with a different `timeZone`, convert from that one.

### A3. Calendar → "At a glance" + meeting prep
From the digest's **Calendar** section (CSAIL talks come through the default calendar; there is no separate CSAIL Events calendar).
- **At a glance:** every event today, in time order: Boston time, title, location (shortened).
  - Classes (subjects starting with a course number like `15.xxx`) and anything with category `Class` or `Exam` are shown but marked as context. Never turn them into tasks.
  - Events starting with `DUE:` or all-day deadlines go on one **Due today** line under the schedule. They are not tasks.
  - CSAIL talks: list only those about AI or robotics. They go in **Clubs & interests** as "consider attending", not in the schedule.
- **Prep tasks:** for each *non-class* meeting today, and tomorrow's (look-ahead days from settings), consider one prep task, e.g. "3 questions for Alex (12:00)". Skip prep for big events where you just show up (webinars, happy hours, festivals) unless an RSVP or registration is pending.

### A3b. Meeting briefs (Meetings tab, D-054)
Right after A3, run section A of `.claude/skills/brief/SKILL.md` on today and the next `briefs.look_ahead_days`, reusing the calendar items A3 just read (don't search again). Hand the web research to background agents so it runs while you do A4 onwards; save the briefs with `briefs.py save` before A7 (they need no approval, like the news brief). Prep tasks for briefed meetings become "Read <first name>'s brief (<N> min)" (brief skill A10), and the draft gets a short **Meetings** block. Off when `briefs.enabled` is false.

### A4. Email → tasks + "Emails to read"
From the digest's **Emails to read** section. The agent already skipped `emails.skip` and coursework (Canvas, `15.xxx`, TAs, professors: coursework never becomes a task or a "to read"), ranked by `emails.rank_by` and wrote the one-line gists.
1. Check the ranking against `config/todo-rules.md` and the Emails to read heading of `config/preferences.md`; reorder if needed.
2. Keep the top `emails.max_per_day` (10).
   - If an email **asks Aman to do something** (the digest's "Ask") (reply, confirm, RSVP, send something), *also* add a task to the matching section, tagged `✉️ email`.
   - Each email gets a reason tag: **Reply**, **Meeting**, **RSVP**, **Deadline**, **Energy Club**, **Robotics**, **AI**, **Event** or **FYI**.
3. Use the digest's "Skipped" count for "N others skipped".

### A4b. Apple Notes → tasks
Notes are read on this Mac with `scripts/notes.py`. It prints JSON and saves nothing. The first run may trigger a macOS "allow access to Notes" popup; tell Aman to click OK. Memory between runs lives in `lists/notes-state.json` (`last_scan`, `todo_note`, `handled`). Settings are in `sources.notes_app`.

**1. The "To do" note** (`python3 scripts/notes.py get "To do"`). It has dated sections ("10/05", "9/29"…), newest at the top. **Only the newest dated section counts.** Older sections are history.
- Read it with judgment. Lines like "Clubs", "Recruiting", "Follow-ups", "Outreach", "Personal", "Professional" and "Coursework" are headings. A short line under a heading (e.g. "Energy Club" then "KPIs") belongs to it ("Energy Club: KPIs").
- Headings map to sections: Clubs → Clubs & interests · Recruiting / Follow-ups / Outreach / Professional → Networking / Professional · Personal → Personal · **Coursework → skip**.
- Compare with `todo_note.items` in the state file:
  - **Line added** (or a newer dated section with new lines) → propose as a new task, tagged `📝 To do`.
  - **Line removed** → that item is probably done. Propose ticking off the matching task.
  - **Unchanged line** → do nothing. It's already on the list, or Aman ticked it off. Never re-add it.

**2. Other notes changed since `last_scan`** (`python3 scripts/notes.py since <hours since last_scan, rounded up>`). Skip the "To do" note here, since step 1 covers it.
- Look for next steps: lines starting with or containing the trigger words in settings ("check out", "email", "connect with", "reach out", "follow up", "stay in touch", "look into", "read", "send", "call", "remind", "sign up", "book"…), explicit "To do:" blocks, and clear asks like "hiring!!!" next to a company.
- Skip coursework, workout logs, drafts of class assignments, and anything already in `handled` (same note plus the same action).
- Each becomes a proposed task tagged `📝 <note title>`, sorted with A5.
- **Never** copy secrets into the list or the repo (API keys, passwords, codes). If a note contains one, warn Aman once.

**3. Approval.** Notes items appear in the draft like everything else. After Aman approves, update `lists/notes-state.json`:
- set `last_scan` to now (Boston time, ISO),
- replace `todo_note` with the newest section's interpreted items,
- append each new action to `handled` with status `added`, `done` or `ignored` (as Aman decided).

The state file holds short task lines only. Never put full note text in it or in the repo.

### A4b2. Granola calls → tasks
Every call since the last list gets its own tasks, whether or not the person goes in the network tracker. Settings: `sources.granola`.
1. `list_meetings` (custom range: day of the last list → now), then `get_meetings` for each meeting. Skip ids already in `lists/network-state.json` `seen` **that were turned into tasks** (status `added`/`updated`, or `tasks` noted). When two notes exist for the same meeting, read both and merge.
2. For each call with at least one other person, propose:
   - **Thank-you:** "Thank <first name> for <topic>", one per call (group calls: one to the host/external guest). Skip if Aman already sent one (the digest's sent-mail sections).
   - **New people mentioned:** "Reach out to <names> (<company>, from <person>)". These also go to the Network block as *To reach out*.
   - **Next steps** from the summary's "Next steps" section and Aman's private notes, written as short tasks.
3. **Coursework calls count here** (exception to the no-coursework rule): next steps from calls for class projects (e.g. an OP client kickoff) become tasks, tagged with the call. Put them in **Personal** unless they fit better elsewhere. Thank-yous for class-project calls are optional: propose with `?`.
4. Tag every task `📞 <call title, shortened>`. Don't duplicate a task already coming from Notes, email or the network step: keep one, with the Granola tag.

### A4c. Network → updates + follow-ups
Run the **network sync** from `.claude/skills/network/SKILL.md` (section A2–A4) over the same window, reusing what you already read in A3–A4b2. Its Outlook steps (opportunity emails, coffee chats Aman asked for, calendar) come from the digest's matching sections: don't search Outlook again. Then:
- Show its proposed network changes as a short **Network** block under the to-do draft (applied without asking, D-053).
- Add network follow-ups due now (section C of that skill) to **Networking / Professional**, tagged `👥 network`. Don't duplicate a task that's already there from email or Notes.

### A4d. Companies → new companies + mentions
Run the **companies sync** from `.claude/skills/companies/SKILL.md` (sections A2–A4) over the same window, reusing everything already read in A3–A4c (the digest's calendar, emails and **Companies mentioned**; Notes, Granola, the network changes). Don't fetch anything twice.
- Show its proposed changes as a short **Companies** block under the Network block (applied without asking, D-053).
- Companies don't create tasks.

### A4e. News → the morning brief
The agents started in A1 step 3. When they're back, write the brief as in the news skill A3, with one addition: the **For today** section uses today's real meetings from A3 (e.g. a coffee with someone at Acme Sciences → Acme Sciences and competitor news, plus 2–3 questions).
- Show a short **News** block under the Companies block: the Top 5 headlines with links, and one line like "38 items · 11 fundraises · full brief saves with the list".
- News doesn't create tasks on its own. If a story clearly calls for one (a deadline, an application opening at a company Aman is recruiting with), propose it in the right section tagged `📰 news`.
- The brief needs no approval of its own (D-024), but it saves together with the list in A8.

### A4e2. Explained → 3–5 stories explained simply
As soon as the brief is written, run the **explainer** from `.claude/skills/explain/SKILL.md` (sections A1–A5) on it: pick 3–5 stories (at least one robotics), hand the deeper reading and "Go deeper" links to one background agent, and write the cards while it reads. Reuse the brief, today's meetings (A3), the research questions and the learning path; don't re-run the news searches.
- Show its **Explained** block under the News block: each card's title and "Say it" line, then the storyline and glossary changes as questions.
- The cards save with the list in A8 without their own approval (D-028); storyline and glossary changes need the same OK as everything else.
- If a card is evidence for a research question, pass it to A4f.

### A4e3. Podcast of today's stories (only if turned on)
If `podcasts.daily_episode` is `true` in settings.yaml, run section D of `.claude/skills/podcast/SKILL.md` once the Explainer cards are saved: it queues "Today's stories" (a quick brief) for the Mac to make. Add one line to the summary: "Today's stories will be in Podcasts in about 15 minutes." Off by default (D-044).

### A4f. Insights → calls, research questions, learn today
Run the **insights sync** from `.claude/skills/insights/SKILL.md` (sections A1–A4), reusing the Granola calls from A4b2, the Notes from A4b, the news brief from A4e and the explained cards from A4e2. Don't fetch anything twice.
- File each new call in `lists/calls.md`. Its follow-ups are the same tasks A4b2 proposes; don't add them twice.
- Show its **Insights** block under the Explained block (applied without asking, D-053).
- Insights don't create tasks.

### A4g. Email → replies, follow-ups (Ghostwriter)
Run the **inbox check** from `.claude/skills/email/SKILL.md` section D (which runs C), using the digest's **Replies on threads he's waiting on** (C1), **Coffee chats and asks Aman sent** and **Other email Aman sent** (C2) instead of searching again. Open (`read_resource`) only the replies you're drafting an answer to. It checks the threads in `lists/email-state.json` for replies, drafts answers (with free times for scheduling), lists due follow-ups and suggests new threads to track.
- Tasks go under Networking / Professional: "Reply to Sam (2L): draft ready", "Follow up with Casey (Acme), 7 days: draft ready".
- Show an **Email** block under the Insights block (2–4 lines).
- **Learning:** if `lists/email-learning.json` shows no review in the last 7 days and it's on or after the review day (`email_writer.learning.weekly_review`), or 5+ sent drafts since the last review, add a task "Ghostwriter weekly review" and run section G3 of the email skill after the list is saved. Same for the monthly blind test (G5) when 30 days have passed.
- After the list is saved, show each draft's preview one at a time. **Approving the list never sends anything:** each email is sent only after Aman says "send" for that exact draft (CLAUDE.md rule 4).

### A4g2. Coursework → Quick review summaries
`today_prep.py` already ran `canvas.py sync`; if it says summaries are missing, write the ones `canvas.py pending` lists (`.claude/skills/coursework/SKILL.md` section A). In the draft, one line under the Email block: "Coursework: N due in the next 48 hours, M new announcements" (names only if something is due within 48 hours). No coursework tasks: the app's Coursework section and Today's "due in 48 hours" block cover it.

### A4h. Rules → hide, sort, word
Apply `config/todo-rules.md` to every task, as in the refresh skill A8: **Never** → into the day file's `## Hidden by your rules` section (`- (<Networking|Clubs|Personal>) <task> · \`<rule>\``), **Rarely matters** → hidden unless the list is short, **Usually matters** → top of its section, **Write tasks like this** → wording. Then, from the prep's `todo_learn nomore` output: for each "Don't suggest things like this" delete, propose a narrow rule in the draft's questions ("New rule: never make SloanGroups member-validation emails a task?"). Only rules Aman OKs go into the file (with "· added <date>" and a Changelog line).

### A4i. Comments → replies and rules (docs/PRD-comments.md)
Answer the comments Aman left in the app since the last run (listed by `today_prep.py`), exactly as the refresh skill A8c (`.claude/skills/refresh/SKILL.md`): decide preference / fix / question / noted, write the replies and the suggestions. In the draft, a **Comments** block: one line per comment ("On '<title>': <his comment> → <your reply>"), then "N suggestions go to the app's Suggestions card". If he says "accept the comment rules" (or names some), apply those straight away as refresh section B and mark them accepted. Saved in A8.

### A5. Sort into sections
Sections, in this order (from `todo.categories`):
1. **Networking / Professional:** meeting prep, follow-ups, replies to people, recruiting, coffee chats
2. **Clubs & interests:** the Energy Club, Robotics, AI (see `keywords`)
3. **Personal:** personal research and errands

If you're not sure which section an item belongs in, put it in your best guess, add a `?`, and ask Aman.

### A6. Carry over
`today_prep.py` printed `todo_sync.py carry <last date>`. It reads the last list from the app (where Aman ticks, edits, deletes and adds) and prints every unfinished task that he hasn't deleted, with its edited wording, its section and a `carried since` tag (kept from earlier, or set to that list's date). Carry all of them (settings `carry_over_unfinished`), including ones he added in the app.
- Carried longer than `flag_stale_after_days` (5) → ask: **do it, drop it, or park it** (Open Threads, later).
- Drop items that are clearly finished (e.g. a meeting-prep task whose meeting has already happened), and say that you dropped them.

### A7. Decide, don't ask (D-053)
Aman doesn't approve in chat any more: he reviews in the app and leaves comments. So, without stopping:
- Unsure section → best guess with a `?`. Stale carried tasks (5+ days) → keep tasks about people (follow-ups, connects, replies); move "look into / learn about" tasks to `lists/parked.md` under a dated heading. Clearly finished items → tick them (`todo_sync.py set <id> done=true` on the last list).
- Network and company changes → apply the ones a real source backs; leave out people known only from a calendar invite. Storyline and glossary changes → apply.
- New rules for `config/todo-rules.md` / `preferences.md` → only as suggestions in the app (via the comment answers), never written straight into the files.
Then save (A8) and report in **one short message**: counts per block, what you decided on his behalf (parked, ticked, skipped), and anything he must do himself today.

### A8. Save and push
1. Write `lists/todo/YYYY-MM-DD.md` in the format below (with the `## Hidden by your rules` section if anything was hidden).
2. If Notes were read, update `lists/notes-state.json` (see A4b step 3).
3. Save the approved network changes (network skill A6 steps 1–3; the xlsx rebuild is in step 4) and company changes (companies skill A6 steps 1 and 3), the news brief (news skill A4 step 1), the explained cards plus the approved storyline and glossary changes (explain skill A6 step 1), and the approved insights changes (insights skill A6 step 1).
4. **Update the app and GitHub: every run, every view, never skip** (standing rule), in **one** command:
   `python3 scripts/today_save.py <date> [--comments <answers.json>] --commit "To-do: <Day, Mon D> (+ network: …, companies: +3, news: 38, explained: 4, calls: +2)<blank line>Co-Authored-By: …"`
   It does, in order (D-052):
   - rebuilds `network.xlsx`;
   - Today + Emails: `todo_sync.py merge`, then `export`, then `refresh_helper.py morning`. Merge only adds, so Aman's ticks, edits, deletes and his own tasks survive, and a second `/today` the same day is safe;
   - Network, Companies, and Calls/research/learn today, with `--replace`;
   - News and Explained, never with `--replace`;
   - the waiting-on list (`email_tracker render` and `email_app waiting`);
   - comments (`comments.py answer`, A4i; pass the answers file even if Aman changed nothing);
   - with `--commit`: commits `lists/` and the rule files, then pulls and pushes. Use the Co-Authored-By line used in this repo. If this branch holds unrelated work, leave out `--commit` and commit from a temporary worktree on `origin/main` instead.
   It prints one ✓/✗ line per step. If anything shows ✗, say so plainly, and don't report the app as updated.
5. Tell Aman in one line: saved, how many tasks, network and company changes, news items, explained stories, app updated, on GitHub.

---

## B. Quick updates during the day

1. `git pull`. Open today's file and get today's tasks from the app (`python3 scripts/todo_sync.py list <date>`). If there's no list, say so and offer to build it.
2. Apply the change:
   - **Tick off:** `- [ ]` → `- [x]`. Match loosely ("alex" matches "3 questions for Alex"). If more than one item matches, ask which.
   - **Add:** append to the named section, tagged `➕ added`. If he names no section, guess and say which one you used.
   - **Drop / move:** delete the item or move it to another section.
3. Make the change in the app, then run `python3 scripts/todo_sync.py export <date>` (it rewrites the file's task sections and counts). Commit `To-do update: <what changed>` and push.
   - Tick: `python3 scripts/todo_sync.py set <id> done=true`.
   - Add: `python3 scripts/todo_sync.py add <date> <net|clubs|personal> "<text>"`.
   - Drop: `python3 scripts/todo_sync.py set <id> deleted=true deleteReason=none` (soft delete, like the app's). If he says why ("not relevant", "never show me these"), use `not-for-me` and add `noMore=true` for "never".
   - Move or reword: `python3 scripts/todo_sync.py edit <id> [--text "<new>"] [--section <key>]` (records the original wording, like the app).
4. Reply in one line, e.g. "Ticked off. 6 left."

No approval step is needed here: Aman's message *is* the instruction.

---

## C. Weekly to-do review (learning what matters)

Once a week (Sundays, or the first `/today` after 7 days since the last review in `lists/todo-learning.json` `reviews`), add a task "To-do weekly review" and, after the list is saved, write the review:
1. `python3 scripts/todo_learn.py sync`, then `python3 scripts/todo_learn.py report --days 7`.
2. Write `drafts/<date>-todo-review.md` (it opens in Roughdraft; see the draft-review skill):
   - **The numbers**, in one short table: tasks suggested, done, edited, moved, deleted (by reason), hidden by rules, brought back, added by Aman; and done / deleted rates by source (email, notes, calls, calendar, network, carried).
   - **Patterns with evidence**, 3–6 of them, each with the real examples: "You deleted 4 of 5 'Consider attending CSAIL talk' tasks, but kept both about robot learning". Include rewordings ("you rename 'Respond to email about…' to '<person>: <action>'"), section moves, things he added that Claude missed, and anything hidden that he brought back (a rule that's too broad).
   - **Your comments** (`python3 scripts/comments.py report --days 7`): how many, what each led to (rule accepted / skipped / waiting, fix, answer, noted), and comments that point the same way ("3 comments say the Explainer is too long").
   - **Proposed changes**, each as an exact before → after for `config/todo-rules.md`, `config/preferences.md` (or `config/settings.yaml`), numbered so he can say "yes to 1 and 3".
3. Wait for his Approve, apply only what he accepted (rules get "· added <date>" and a Changelog line), log it with `python3 scripts/todo_learn.py log-review '{"accepted": [...], "rejected": [...]}'` (and `comments.py log-review` for comment-based changes) (rejected ideas aren't proposed again), commit and push.
Never change the rules without his OK.

---

## File format: `lists/todo/YYYY-MM-DD.md`

Keep it exactly like this. It has to read well in the GitHub phone app, and the future app will parse it.

```markdown
# Mon, Oct 5

*7 tasks · 10 emails · built 7:42 AM*

## At a glance

| Time | What | Where |
|---|---|---|
| 10:00 | *15.xxx Course* | Room 100 |
| 12:00 | Aman / Alex | Cafe |
| 7:00 PM | Partnerships exec meeting | Zoom |

**Due today:** 15.xxx Deliverable 3

## Networking / Professional

- [ ] 3 questions for Alex · `📅 12:00`
- [ ] Confirm Wed call with Jordan · `✉️ email`

## Clubs & interests

- [ ] Agenda for Partnerships exec · `📅 7:00 PM`
- [ ] Consider: CSAIL talk on robot learning, Tue 4 PM · `📅 CSAIL`

## Personal

- [ ] Read up on robotics startups · `↩️ carried since 2026-10-04`

## Hidden by your rules

- (Clubs) Validate Sam in the Robotics Club group · `SloanGroups member validation`

## Emails to read

*Top 10 of 57 · 47 skipped*

1. **Reply** · Jordan Lee (Acme Sciences): asks you to confirm Wednesday's time. [Open](<outlook webLink>)
2. **Meeting** · ...
```

Rules for the file:
- Times: Boston, 12-hour, with `AM`/`PM` only when it isn't obvious (classes in the morning can omit it).
- Classes go in *italics* in the table.
- Every task ends with a source tag: `📅 <time or source>`, `✉️ email`, `📝 <note title>`, `↩️ carried since YYYY-MM-DD`, `👥 network`, `📞 <call>`, `📰 news`, or `➕ added`.
- Keep empty sections with the line `- Nothing today`.
- `## Hidden by your rules` only appears when a rule hid something. Each line starts with the section it would have gone in. A refresh adds `· refreshed <time>` to the header line.
- **Privacy:** never paste email bodies. Save only the sender's name, a one-line summary in your own words, and the Outlook link.
