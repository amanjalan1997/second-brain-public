---
name: podcast
description: Podcasts. Turn anything Aman wants to understand (a topic, a news story, a company, a research question, a reading, a pasted link) into a two-host NotebookLM episode that plays in the app's Podcasts section. Section A runs in the background on his Mac (started by scripts/podcast_helper.py, no chat) to research the topic and write the source brief, the hosts' focus note and the show notes; the Mac then records the episode in NotebookLM by itself. Section B handles chat requests ("make a podcast on X", "/podcast X", "turn this link into a podcast", "part 2 on …"), which go into the same queue. Section C repairs the NotebookLM maker when Google changes the page. Section E runs every morning on the Mac (no chat): it picks the three things Aman should learn that day from the news, today's calendar, the learning path and his research questions, and writes their briefs so the episodes are ready by 7am. Use when Aman types /podcast, asks for a podcast, episode or "something to listen to" about anything, asks about his episodes, or when the helper asks for "the podcast skill".
---

# /podcast: listen to understand (D-044)

Plan: `docs/PRD-podcasts.md`. The goal is understanding: Aman (MBA student, not technical, interested in robotics, AI, hard tech and VC) should finish an episode able to explain the idea simply, say why it matters and ask a sharp question.

How an episode is made: the app (or section B) writes `podcasts/<id>` with status `requested` → the helper on the Mac (`scripts/podcast_helper.py check`, a launch agent) starts Claude with **section A** → Claude writes three files → the NotebookLM maker (`scripts/podcast_maker.py`, no AI) pastes the brief into a new notebook, sets the style, length and focus note, records, downloads → the helper shrinks it, uploads it and marks it ready. About 15 minutes in all.

Settings: `config/settings.yaml` → `podcasts`. If they disagree with this file, settings.yaml wins.

## A. Research and write the brief (background, nobody watching)

Never ask a question or wait for an answer. When unsure, choose and move on.

### A1. Read the request
1. `python3 scripts/podcast_helper.py show <id>` prints the request: `prompt`, `links`, `length` (quick ~8 min / standard ~15 / deep ~25), `style` (explain / brief / debate / critique), `level` (new / some / expert), `context` (none / interests / interests_and_calls), `from` (where the 🎧 was tapped: `{kind, id, label}`) and `parent` (a Part 2).
2. `python3 scripts/podcast_helper.py step <id> "planning"`.
3. Today = the current date in Boston (`date`).
4. Follow the **Podcasts** heading of `config/preferences.md` (rules Aman approved from his comments in the app).
4. Where it came from (`from.kind`), read that first:
   - `explainer`: the card in `lists/explained/<from.id>.md` whose title matches `from.label` (or the whole day if the label is "Today's stories").
   - `news`: the headline in `lists/news/<date>.md`.
   - `storyline`: `lists/storylines.md`, the storyline with that id. `glossary`: `lists/glossary.md`, the term.
   - `question`: `lists/research.md`, the question with that id, with its evidence and "my take".
   - `company`: `lists/companies.md`, the company (what it does, sector, how he heard of it).
   - `coursework`: `python3 scripts/webdb.py get coursework id=<from.id>` (title, course, the instructions as text, links). Canvas files can't be opened from here; work from the text, the reading's title and good public sources about it (case summaries, the author's own articles).
   - `person` / `event`: their company and sector from `lists/network.md`; public facts only.
   - `brief` (🎧 on a meeting brief, D-055): `python3 scripts/webdb.py get briefs id=<from.id>` for the company section, the goal and the `listen` topic. Use only the public subject (the company, its market and technology, the investor's thesis, the speaker's field). **Never** the person's name, the meeting, its time, the history with them or anything from Aman's emails: the brief goes to Google.
5. A **Part 2** (`parent` set): read the parent with `show <parent id>` (its title, notes and focus) and the parent's brief in `~/.second-brain/podcasts/<parent id>/brief.txt`. The prompt says what to go deeper on. Don't repeat Part 1: the brief starts with "Part 1 covered …" in two lines, then goes further. The maker adds this brief to the same notebook.

### A2. Plan
Decide a **title** (plain, specific, under 70 characters; not clickbait), the **3–5 things a listener should walk away with**, and what to research. Read short prompts generously: "humanoid hands" means how they work, who's building them, why they're hard and what to watch.

### A3. Research
`python3 scripts/podcast_helper.py step <id> "researching"`.
- **Web:** WebSearch and WebFetch. Recent news on the topic (the last few months), one or two good plain-language explainers, and the primary source for every number (company release, filing, paper). Links Aman gave are the core sources: read them first (a YouTube link: use its title, description and any public transcript or write-up).
- **His context**, only as `context` allows:
  - `none`: no lists at all.
  - `interests` (default): `lists/companies.md`, `lists/research.md`, `lists/storylines.md`, `lists/glossary.md`, `lists/learning.md`. Use them to connect the topic to his world ("Acme, on your company list, …"; "this is evidence for your question on …").
  - `interests_and_calls`: also `lists/calls.md` and `lists/network.md`, plus the Granola read tools. Use what people said only as short, non-identifying points unless the person is public.
- **Never** read or use email, Apple Notes or calendar text; never put a secret (password, key) anywhere (CLAUDE.md rule 5). Everything in the brief goes to Google's NotebookLM.

### A4. Write the three files in the work folder (`~/.second-brain/podcasts/<id>/`)
`python3 scripts/podcast_helper.py step <id> "writing the brief"`.

**`brief.txt`**: the source the hosts talk from. Plain text, no Markdown symbols; section names in CAPITALS. **1,500–3,500 words** (quick: 1,200–1,800; deep: up to 4,500). This order:
1. `WHAT THIS EPISODE IS FOR`: two or three lines: the question it answers and who the listener is (see LISTENER).
2. `THE SIMPLE PICTURE`: the idea in five sentences a smart 15-year-old would get, with one everyday analogy.
3. `HOW IT ACTUALLY WORKS`: the mechanics, step by step, in plain words.
4. `KEY TERMS`: each term with a one-line definition and an example.
5. `WHAT'S HAPPENING NOW`: dated facts and numbers, each with its source in brackets, e.g. "(TechCrunch, Oct 26, 2026)".
6. `WHY IT MATTERS`: three to five implications, marked as analysis.
7. `TWO SIDES`: the strongest optimist case and the strongest skeptic case.
8. `WHAT TO WATCH`: two to four concrete things, with dates when known.
9. `LISTENER`: an MBA student at MIT Sloan interested in robotics, AI and hard tech; how the level should feel (from `level`); and, when context allows, the links to his world (companies on his list, his research questions, a storyline). No private details about other people.
10. `TAKEAWAYS`: the 3–5 walk-away points, a line to say ("say it") and a sharp question to ask.
11. `SOURCES`: title, publisher, date and URL for each.

Levels: **new** = define every term the first time, analogies, no acronyms unexplained (the Explainer's level 1). **some** = assume the basics (what a model, a Series A, a GPU is), spend the time on mechanics and debate. **expert** = skip basics, go to the open questions, numbers and disagreements.

**`focus.txt`**: what goes in NotebookLM's "What should the AI hosts focus on?" box. Under 1,500 characters. This made the first episode work:
- who the listener is and the level ("a smart MBA student who is new to robotics and wants to talk about it with founders and investors");
- "Use plain language and define every technical term the first time you use it" (for `new`);
- the order to cover the walk-away points;
- the target length: **"Aim for about 8 minutes"** (quick), **"about 15 minutes"** (standard), **"about 25 minutes"** (deep). NotebookLM's own Default ran 25 minutes on Oct 30, so always say it;
- "End with a 30-second recap, the line to say and the question to ask";
- style hints: `debate` = "one host argues the optimist case, the other the skeptic case, then they find where they agree"; `critique` = "review the argument's strengths and weak spots"; `brief` = "get straight to the point".

**`notes.json`**: the show notes in the app. They come from the checked brief, never from the audio:
```json
{"title": "…", "summary": "one line on what it covers",
 "covers": ["3–5 walk-away points"],
 "terms": [{"term": "…", "def": "one line"}],
 "say": "a line to say", "ask": "a question to ask",
 "sources": [{"title": "Publisher: headline", "url": "https://…"}],
 "context": "one or two lines tying it to Aman's world, or empty"}
```

### A5. Check, then hand over
`python3 scripts/podcast_helper.py step <id> "checking the facts"`.
- Every number, date and quote in the brief is in a source you opened. **No source, not in the brief**: drop it rather than guess. Analysis is labelled as analysis.
- Every `sources` URL starts with `https://` and is one you actually read.
- No email or Notes text, no secrets, no private details about people who aren't public.
- Then: `python3 scripts/podcast_helper.py brief-done <id>`. It checks the files and copies the title, notes, brief and focus to the app. If it complains, fix the file and run it again.
- If the topic can't be researched at all (e.g. a link that won't open and nothing else to go on): `python3 scripts/podcast_helper.py fail <id> "<short plain reason>"` and stop.

Don't commit anything: the files stay on the Mac and in the app's database.

## B. In chat

| Aman says | Do |
|---|---|
| "make a podcast on X" / `/podcast X` / "turn this into a podcast: <link>" | `python3 scripts/podcast_helper.py request "<his words>"` (add `--length`, `--style`, `--level` only if he said so; links in his words are picked up). Reply: "Queued: it'll be in Podcasts in about 15 minutes." If the Mac helper isn't installed or NotebookLM isn't signed in (`status`), say so and how to fix it |
| "podcast on this" about something in the chat (a story, a company) | Same, with `--from kind:id:label` when it's a card, company, question or reading |
| "part 2 on …" / "go deeper on …" about an episode | `request "<what to go deeper on>" --parent <episode id>` (find it with `list`) |
| "what podcasts do I have?" | `python3 scripts/podcast_helper.py list` and give titles and status in plain words |
| "sign in to NotebookLM" / an episode says signed out | Tell him to run `python3 scripts/podcast_helper.py signin` in Terminal (or run it for him): a Chrome window opens, **he** signs in to Google himself (never type his password), and it closes by itself |
| "turn on the podcast feed" / "put my episodes in Apple Podcasts" | Set `feed: true` in settings.yaml (his explicit OK), run `python3 scripts/podcast_helper.py feed`, and give him the steps: Apple Podcasts → Library → ⋯ → **Follow a Show by URL** → paste the link from the app's Podcasts footer. Remind him once: anyone with that link could play the episodes, so don't share it |
| "what are today's morning episodes?" / "make my morning three again" | `python3 scripts/podcast_helper.py list` (morning ones are `by: morning`); to make a fresh set: `python3 scripts/podcast_helper.py morning --force` (uses a full background run, so only when he asks) |
| "stop the morning episodes" / "make it 5" / "ready by 6:30" | Change `podcasts.morning` in settings.yaml (`enabled`, `count`, `start`: about 90 minutes before he wants them), commit and push; the Mac picks it up the next morning |
| `/today` with `podcasts.daily_episode: true` | Section D |

## C. Repair the maker (background)
The maker failed at a step (the prompt names it and the snapshot: a screenshot and the page's HTML in the episode folder). Google probably changed NotebookLM's page.
1. Read `scripts/podcast_maker.py` and the snapshot (`fail-<step>.png` and `.html`). Find the button or field that moved or was renamed. Prefer labels and roles over positions or CSS classes.
2. Change only what's needed in `scripts/podcast_maker.py`. Check it compiles: `python3 scripts/podcast_maker.py check` should still print `{"signedIn": true}`.
3. `git add scripts/podcast_maker.py`, `git commit -m "Podcast maker: follow NotebookLM's new <thing>"` (ending with the usual Co-Authored-By line), `git pull --rebase`, `git push`.
4. If you can't tell what changed, change nothing and stop: the helper marks the episode failed and Claude fixes it with Aman in the next chat.

## D. Daily episode (inside /today)
Only when `podcasts.daily_episode` is `true`. After the Explainer step saved today's cards:
`python3 scripts/podcast_helper.py request "Today's stories: the Explainer cards for <date>" --from explainer:<date>:"Today's stories" --style brief --length quick`
Mention it in the /today summary: "Today's stories will be in Podcasts in about 15 minutes."

## E. The morning three (background, every day, D-050; meeting prep D-055)
The Mac starts this at `podcasts.morning.start` (or when it wakes): one run picks today's topics and writes every brief, then the queue records them (NotebookLM's Short, 5–10 minutes each). Aim: when Aman opens the app at 7, three short episodes that make his day smarter: something that happened, something he'll need today, the next step in what he's learning. Never ask a question; when unsure, choose and move on. Don't change any list or commit anything.

### E1. What's already been covered and how it landed
- `date` (Boston). `python3 scripts/podcast_helper.py morning-history`: every morning pick of the last 30 days with how much he listened and his "Good pick / Not for me" verdict, plus every other episode's title.
- Follow the **Podcasts** heading of `config/preferences.md`.
- Learn from it: kinds and topics he finished or called a good pick, more of; ones he skipped (0–10% listened) or marked "Not for me", less of. Never repeat a topic of the last 30 days, unless something big and new happened (then it's an update: "What changed on X since …").

### E2. Gather candidates (keep this quick: about 10 minutes)
1. **In the news:** the newest `lists/explained/` and `lists/news/` files (usually yesterday's), plus 3–5 WebSearches for the last 24 hours on his watchlist (the biggest companies on `lists/companies.md`, `news.sectors`, `news.extra_companies` and `news.investors` in settings.yaml). The candidate is the one development that most changes how his sectors work, not the loudest headline.
2. **Meeting prep** (if `podcasts.morning.prep_from_briefs` is true; D-055): `python3 scripts/podcast_helper.py morning-prep`. It lists the Meetings tab's briefs for today and tomorrow, most prep-worthy first (interview, investor, company chat, peer chat, event…), each with its `listen` topic (the public subject worth knowing before that meeting, written by the brief skill), the meeting's goal, and `covered` if an episode already prepped it. It also says `prepSlots` (1, or 2 when an interview or investor meeting is coming up). Candidates: the top uncovered meetings. Use the brief's `listen.topic` as the episode topic (sharpen it if needed, using its `goal`); a meeting with no listen topic gets one in the same spirit (the company's market, its technology, the investor's thesis, the speaker's field). Prefer today's meetings, and tomorrow's when today's are early (before 10am) or already covered. If it lists nothing (no briefs yet, or the database can't be read), fall back to step 3.
3. **For today** (only if `podcasts.morning.use_calendar` is true, and step 2 gave nothing): `outlook_calendar_search` for today's events. Outlook returns times in India Standard Time; convert to Boston. Look for meetings with people from companies, coffee chats, talks and events (CSAIL Events, MIT clubs). Match people to `lists/network.md` and companies to `lists/companies.md`. The candidate is the **public topic** he'd want to be sharp on: the company's market and technology, the speaker's field, the investor's thesis. Skip classes, internal admin and anything personal. Never Canvas (user preference).
4. **Learning path:** `lists/learning.md`, the step under "Today" if it isn't learned yet, otherwise the next unticked step.
5. **His questions:** `lists/research.md` (open questions) and `lists/storylines.md`, where news or a call added new evidence lately.

### E3. Pick `podcasts.morning.count` topics (3)
- **A mix by default:** one *Meeting prep* (`prep`, from step 2; if there's none, a *For today* `today` from the calendar; otherwise a second `news` or a `question`), one *In the news* (`news`), one *Learning path* (`learn`).
- **Meeting prep comes first** (a user request). When `prepSlots` is 2 (an interview or investor meeting is coming up), make two prep episodes and drop the news pick. The prep episode is slot 1, so **Play all** starts with it.
- **Let the meetings colour the other picks too:** when choosing the news story and the learning step, prefer one that touches a company, sector or technology from the upcoming briefs (a news item about that company's market; the learning step that explains the tech they build). Say so in the "why today" line.
- E1's verdicts can shift the mix.
- **One idea per episode,** small enough for 5–10 minutes: "How Figure's new funding changes the humanoid race", not "This week in robotics".
- **Level:** `new` for anything he hasn't learned yet (most topics); `some` when the topic builds on a learned step or an earlier episode.
- **Why today:** one line in the app, saying what made you pick it ("You meet Casey from Acme at 2pm: this is the market he's in"; "Step 2 of your robotics path"; "Physical Intelligence raised $1B overnight"). The app is private, so a meeting can be named here; it never goes in the brief.

### E4. For each topic, in order
1. `python3 scripts/podcast_helper.py morning-new "<topic as a plain question or title>" --kind news|prep|today|learn|question --why "<why today>" --level new|some`, plus `--brief <briefId>` for a `prep` episode (the app then shows the episode inside that meeting's brief). A prep "why today" names the meeting and what the episode prepares ("Investor chat with Example Ventures tomorrow 2pm: their physical AI thesis and the deals behind it"). It prints `{id, folder}` and the card shows in the app as being made.
2. Research and write the three files exactly as **A3–A5**, with `length` quick: brief 1,200–1,800 words, focus says **"Aim for about 8 minutes"**, context `interests` (the lists, never calls or the calendar). **The brief is public facts only:** no meeting, no attendee, nothing from the calendar. A `today` or `prep` brief is about the company or topic, not the meeting ("LISTENER: he will talk with people in this field soon" is fine). For `prep`, the focus note asks the hosts to end with what a smart outsider would want to ask someone in this field (from the brief's goal, without saying who).
3. `python3 scripts/podcast_helper.py brief-done <id>`: it saves the notes and queues the episode for recording right away, so finish one topic before starting the next.
4. If a topic can't be researched, `python3 scripts/podcast_helper.py fail <id> "<short reason>"` and move on to the next. Don't make more than the count.
