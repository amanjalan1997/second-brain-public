---
name: insights
description: Keep Aman's "thinking" lists up to date. These are the calls list (lists/calls.md, every Granola call with its insights pulled out by theme), his research questions (lists/research.md, the big things he's figuring out, with evidence from calls, news and notes) and his learning path (lists/learning.md, one robotics topic a day for "Learn today"). It files new calls, attaches new evidence to questions, picks today's topic, shows the changes for approval, then saves, refreshes the app's laptop views (Dashboard, Calls & notes, Research & learning) and pushes. Also handles quick edits ("add question: …", "learned X", "move question X to Digging in", "my take on X: …"). Use when Aman types /insights, asks about his calls, insights, research questions or what to learn, or when /today runs its insights step.
---

# /insights: calls, research questions and learning

Aman is not technical. Keep messages short and plain. **Never save a change to these lists he hasn't approved** (CLAUDE.md rule 2), except ticking "learned", which he does himself in the app.

Settings live in `config/settings.yaml` under `insights`. Read them first; if they disagree with this file, settings.yaml wins.

Files (each is the master; the app only shows it):
- `lists/calls.md`: one `### YYYY-MM-DD · <person or meeting> · <org>` block per Granola call, newest first. Fields: Type, When, People, In one line, Insights, Follow-ups, Questions, Mentioned, Filed, Granola.
- `lists/research.md`: one `### <q-id> · <question>` block per question. Fields: Status (Open | Digging in | Answered for now), Added, My take so far, Evidence (`YYYY-MM-DD · call|news|note · <short text>`).
- `lists/learning.md`: the numbered path (`N. [ ] **Title** · subtitle · q-id`), a `## Today` block and a `## Learned` log.
- `scripts/thinking_to_app.py`: turns all three into app documents.

**Privacy (CLAUDE.md rule 5):** short extracted points in your own words only. Never paste transcript text, quotes longer than about 12 words, emails, phone numbers or secrets.

## A. Sync (inside /today step A4f, or on its own as /insights)

### A1. Read what's new
- **Your preferences:** the **Calls and insights**, **Research questions** and **Learn today** headings of `config/preferences.md` (rules Aman approved from his comments in the app).
- **Granola calls since the newest date in calls.md.** Reuse the calls already read in /today A4b2; don't fetch twice. Skip pure lectures and classes. Keep class-project calls (Type `Class project`).
- **Today's news brief** (lists/news/<date>.md) and **Apple Notes** changed since the last run (already read by /today), only for evidence on research questions.
- **The app:** read `meta/learning` from the web app (`python3 scripts/webdb.py get meta`, the `learning` doc; web app only since D-036) and copy any `done: true` steps back into learning.md as `[x]`, adding them to `## Learned` as `- YYYY-MM-DD · <title>` (date = `doneAt` in Boston time). Aman ticks these in the app, so the app wins.

### A2. File each new call
Write a block in the calls.md format:
- **Type:** exactly one of Recruiting, Advice, Learning, Club, Class project.
- **In one line:** the single most useful takeaway.
- **Insights:** 1–5 bullets, each `**Short lead.** One sentence. #theme`. Themes, from `insights.themes` in settings only: ai-science-recruiting, physical-ai, startup-stage, outreach, ai-consulting, career-strategy, clubs, coursework. If an insight fits none, ask Aman whether to add a theme. Don't invent one silently.
- **Follow-ups:** the same ones /today and /network propose for this call (keep them in sync; ticks live in network.md and the app).
- **Questions:** ids of the research questions the call is evidence for.
- **Filed:** `yes`. If you only had time to list the call, add it with `Filed: no` and one line. It shows as "to file" in the app.

### A3. Research questions
- For each question, look for new evidence in the new calls, today's news brief and changed Notes. Add it as an Evidence line (newest first), max 2–3 per question per day. Prefer things that move the answer.
- **Never rewrite "My take so far" yourself.** If the evidence shifts it, suggest a new take and wait for Aman to approve it.
- Suggest a status change (e.g. Open → Digging in once there are 3+ pieces of evidence and a take) but don't apply it without approval.
- If something keeps coming up that isn't a question yet, suggest it as a new question.

### A4. Learn today
Pick today's topic and fill the `## Today` block (Date, Step, Title, What it is, Why for you, Ask at your next robotics chat, Read more):
- Default: the first unticked step on the path.
- Jump ahead to another step if yesterday's calls, today's meetings or today's news make it clearly more useful, and say why in "Why for you".
- **What it is:** 2–3 plain sentences. Define every technical term. Name 1–2 real examples.
- **Why for you:** tie it to a real call, person, company or research question from the lists. Never make up a connection.
- **Read more:** one https link to a good explainer (an official blog, a well-known article or a paper's landing page). Check that it loads (`curl -sIL`). If none checks out, leave the line out.
- If yesterday's topic wasn't ticked, keep it for today unless Aman says to move on.

### A5. Show the changes and get approval
Show an **Insights** block (inside /today it goes under the News block, and the same approval reply covers everything):
> Insights: 2 calls filed (Alex, Sam: 9 insights) · 3 new pieces of evidence (foundation models +2, MBA roles +1) · learn today: Sim-to-real
Then list any suggested take changes, status changes and new questions as questions. Apply Aman's edits.

### A6. Save
1. Write the three files. Update the header lines (counts, "updated <Day, Mon D>").
2. Refresh the app: `python3 scripts/thinking_to_app.py <scratchpad>/thk | python3 scripts/webdb.py push - --replace`. `--replace` deletes any `calls` or `questions` doc whose id isn't in this run. Do this every run, even if nothing changed. If the save fails, say so plainly.
3. Commit `Insights: <summary>` and push (inside /today it's part of the A8 commit).

## B. Quick edits (no approval step: Aman's message is the instruction)
- **"add question: <text>"** → new block in research.md with a short `q-<slug>` id, Status Open, Added today. Ask for his starting take only if he gave one.
- **"my take on <question>: <text>"** → replace My take so far.
- **"move <question> to <status>"** → change Status.
- **"learned <topic>" / "skip <topic>"** → tick it, or move it to the end of the path. Update the app's `meta/learning` too.
- **"add to learning path: <topic>"** → add a step at the right place.
- **"file my call with <person>"** → do A1–A2 for that one call and show it before saving.
Then run A6 steps 2–3 (`Insights update: <what changed>`).
