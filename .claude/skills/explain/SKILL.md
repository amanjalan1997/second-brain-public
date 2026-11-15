---
name: explain
description: The Explainer. Turn the morning news brief into 3–5 stories explained simply (ELI5), focused on implications: what happened in plain words, why it matters, the idea underneath, two sides, what to watch, a line to say and a question to ask, with linked sources and one "Go deeper" read on every card. Keeps two living lists that build Aman's big picture, the storylines (lists/storylines.md) and a glossary of concepts (lists/glossary.md), whose changes he approves. Saves lists/explained/YYYY-MM-DD.md, loads it into the top of the app's News tab (storylines and glossary in Research & learning) and pushes. Sundays add "The week in 5 minutes". Use when Aman types /explain, asks to explain the news or a story ("explain X", "what does X mean", "ELI5 X"), asks about a storyline or term, or when /today runs its explain step.
---

# /explain: the news, explained simply

Aman is not technical, and this exists to make him **conversant** in AI and robotics: able to say what happened without jargon, why it matters, give a take, and ask a sharp question. Keep chat messages short and plain. The spec is `docs/PRD-explainer.md` (D-028).

Settings live in `config/settings.yaml` under `explain`. Read them first; if they disagree with this file, settings.yaml wins.

Files (each is the master; the app only shows it):
- `lists/explained/YYYY-MM-DD.md`: one file per day, the cards. Saves without approval, like the news brief (D-024). The first one (2026-10-27) is the model for format and tone.
- `lists/storylines.md`: the 6–12 ongoing narratives. Changes are **approved first** (CLAUDE.md rule 2).
- `lists/glossary.md`: every concept a card has explained. New terms are **approved first** (they're shown with the storyline changes; one reply covers both).
- `scripts/explain_to_app.py`: turns all three into app documents.

## What Aman might say

| He says | Do |
|---|---|
| `/explain`, "explain today's news" | **Build** today's cards (section A) |
| "explain X", "ELI5 X", "what does X mean?" | One-off explainer (section B); don't save a day file |
| "what's the story on humanoids?", "catch me up on X" | Read the storyline back in plain words (section B) |
| "too basic", "go deeper", "level 2" | Change `explain.level` in settings, commit, one-line reply |
| "add storyline: X", "archive X" | Edit `lists/storylines.md` (his message is the approval), refresh the app, push |

---

## A. Build today's cards

### A1. Get ready
1. `git pull`. Read `config/settings.yaml` (`explain`, `news`), `lists/storylines.md`, `lists/glossary.md`, and the last 3 days of `lists/explained/` (so a story isn't explained twice; a follow-up is fine if something new happened, and it says what's new). Follow the **Explainer** heading of `config/preferences.md` (rules Aman approved from his comments in the app).
2. **Input = today's news brief** `lists/news/<date>.md`. If there isn't one yet, run `/news` first (inside `/today` it already exists by now). The brief is the breadth; don't redo its searches.
3. Also read `lists/research.md`, `lists/learning.md`, today's meetings (inside `/today`, from step A3) and the companies and people in `lists/companies.md` / `lists/network.md`, for the **For you** line.
4. If today's file already exists, ask: refresh it, or leave it.

### A2. Pick 3–5 stories
Score every brief item, then pick `stories_min`–`stories_max` (3 on a quiet day, 5 on a big one). Weigh:
- **Importance:** does it change how the industry works, or who wins? (A rule change, a new price point, a big company's direction, a first.)
- **Teaching value:** does it reveal an idea worth knowing (inference, sim-to-real, take-or-pay, open weights)?
- **Relevance to Aman:** his companies, contacts, research questions, this week's meetings, Energy Club, recruiting.
- **Storyline progress:** does it move one of the storylines forward?

Rules:
- **At least `robotics_min` (1) robotics story every run.** If nothing big happened in robotics, take the most useful smaller robotics item, or write a **catch-up card** on a robotics storyline (where it stands and why, from the storyline's timeline).
- **Group** related headlines into one story (Anthropic's S-1 + an inference-chip round + a nuclear loan → "the AI compute bill"). A card's title says what's going on, not just the event.
- Plain fundraises only make it in when they show a pattern ("robot money is going to jobs that pay now").
- Cover the `/news` sectors broadly over a week; don't make every card about frontier labs.

### A3. Read deeper
For each picked story, open 1–3 of its original sources (the filing, the company post, the best article) to get the details right. Web search budget: about **25 searches + page reads** in total, because `/news` already used most of the run's ~200.
- Find the **Go deeper** read: one explainer, analysis or long interview that gives the full picture, free where possible (official blogs, Stratechery free posts, SemiAnalysis free posts, MIT Tech Review, IEEE Spectrum, The Robot Report, Epoch AI, a16z/Sequoia essays, podcast episode pages). It can be older than today if it's the best explainer. Check it loads: `curl -sIL -o /dev/null -w "%{http_code}" --max-time 15 -A "Mozilla/5.0" <url>` → 200 (a 403 from a big publisher that blocks bots is OK). **Never a URL from memory.** If none checks out, use the storyline's "Start here" read.
- Inside `/today`, give this to one background agent (`researcher`, the cheaper model, D-052) as soon as the brief is written, with the picked stories, the source URLs, the budget and these rules; write the cards while it reads.

### A4. Write the cards
`lists/explained/<date>.md`:

```markdown
# Explained: Tue, Oct 27, 2026

*4 stories from today's news brief, explained simply. Facts link to their sources; "Why it matters" and "Two sides" are analysis. Level 1 (ELI5).*

---

## The AI compute bill is coming due
- **Storyline:** compute-power
- **Robotics:** no
- **What happened, simply:** 2–4 sentences. An everyday analogy, the key numbers, no jargon (define any term you must use in the same sentence).
- **Why it matters:**
  - What it changes for the industry.
  - A second-order effect (what happens next because of it).
  - Who wins, who's exposed.
- **The idea underneath:** Training vs. inference. 2–3 sentences defining the concept simply.
- **Optimist:** one line.
- **Skeptic:** one line.
- **What to watch:**
  - The next event or number that shows which side is right (with a date if known).
- **Confidence:** High | Medium | Low, and a few words on why (how solid are the facts, how speculative is the take).
- **For you:** 1–2 lines tying it to his companies, contacts, research questions or this week's meetings. Leave the field out if nothing real fits. Never invent a connection.
- **Say it:** "One sentence he could say in a conversation."
- **Ask:** "One sharp question for someone in the field."
- **Sources:** [Fortune](https://…) · [RuntimeWire](https://…)
- **Go deeper:** [Title](https://…) — one line on why it's worth his time.
```

Rules:
- **No link, no card.** Every fact in "What happened" comes from a linked source (copy the links from the brief, plus anything opened in A3). Mark single-source facts `(unconfirmed)`, as the brief does.
- "Why it matters", "Two sides" and "What to watch" are analysis: reason from the facts, and keep it honest with **Confidence**. Don't state a forecast as fact.
- Analogies explain the *idea*, never replace the numbers.
- **Level** (`explain.level`): 1 = true ELI5, every term defined; 2 = define only new terms (not in the glossary), use real vocabulary; 3 = industry-newsletter density. Terms already in the glossary can be used with a short reminder instead of a full definition.
- Order: the robotics card is never last; otherwise by importance.
- Length: each card a 2–3 minute read; the day 10–15 minutes.
- Copy no article text. At most one quote under 15 words per card.

**Sundays** (`weekly_recap_day`) add this after the cards:

```markdown
## The week in 5 minutes
- **Moved this week:**
  - **Storyline title:** what changed, in one or two sentences. [Source](https://…)
  - (3 storylines)
- **Surprise of the week:** one thing that surprised the experts, or a debate that heated up. [Source](https://…)
- **Read this weekend:** [Title](https://…) — why.
```
Reading only: no quizzes (`practice_questions: false`).

### A5. Update storylines and glossary (suggest, then wait)
**Storylines** (`lists/storylines.md`):
- File each card under one storyline (`Storyline:` field). Add a **Timeline** line for it: `- YYYY-MM-DD · one line with the key number [Source](url)`, newest first, max 12 lines (drop the oldest).
- Rewrite **Where things stand** if the story changes it (3–4 sentences).
- If a card fits no storyline and the theme is likely to keep coming back, suggest a **new storyline** (id, title, where things stand, key players, open question, Start here reads). Otherwise file it under `other` (no new storyline).
- Suggest **archiving** a storyline with no timeline entry for `archive_storyline_after_days` (30).
- Keep **Start here** current: 1–2 checked reads. Replace one only when there's a clearly better one.

**Glossary** (`lists/glossary.md`):
- Each card's "idea underneath" becomes a term if it isn't there yet: **Means** (two plain sentences), **Like** (an analogy), **First met** (`YYYY-MM-DD · card title`), **Storyline**, **Learn more** (a checked link, often the card's Go deeper). Alphabetical.
- If the robotics learning path (`lists/learning.md`) has a step on the same idea, add `- **Learning path:** step N` instead of explaining it twice.

**Show** an **Explained** block (inside `/today` it goes under the News block, and the same approval reply covers everything):
> Explained: 4 stories (compute bill · robots that dig · open models and China · $10B megafunds) · storylines: 4 updated · glossary: +3 (inference, open weights, megafund)

List each card title with its one-line "Say it", then the storyline and glossary changes as questions ("Add 3 glossary terms and update 4 storylines?"). The cards save regardless; only the storyline and glossary changes wait for his OK.

### A6. Save, load into the app, push
1. Write the day file (cards save without approval). After Aman's OK, write the approved storyline and glossary changes, and update each file's header line (counts, "updated <Day, Mon D>").
2. **App** (web app only since D-036): `python3 scripts/explain_to_app.py <scratchpad>/explain <date> | python3 scripts/webdb.py push -`. It writes `explained/<date>`, `meta/storylines` and `meta/glossary`. Never `--replace` here: it would delete the other days' cards. If the save fails, say so plainly. This works from Conductor too.
3. `git add lists/explained lists/storylines.md lists/glossary.md && git commit -m "Explained: <Day, Mon D> (<n> stories)" && git push` (with the Co-Authored-By line used in this repo). Inside `/today` this goes in the same commit as the to-do list.
4. Tell Aman in one line: how many stories, the robotics one, and that it's at the top of the News tab and on GitHub.

### A7. Suggest, don't change
If a card is evidence for one of his research questions, say so in the **For you** line and pass it to the insights step (inside `/today`, A4f adds the Evidence line with approval). Never edit `lists/research.md`, `lists/companies.md` or `lists/network.md` from here.

---

## B. One-off questions (chat only)

- **"explain X" / "ELI5 X":** write one card in the A4 format in chat (search up to ~10 times; same link rules). Offer to add the term to the glossary or the story to a storyline; save only if he says yes.
- **"what does X mean?":** if X is in the glossary, answer from it (Means + Like + Learn more). If not, explain it in 2–3 sentences with an analogy and one checked link, and offer to add it.
- **"catch me up on <storyline>":** read `lists/storylines.md` back in plain words: where things stand, the last 3–5 timeline events with links, the open question, and the Start here read.
