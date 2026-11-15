---
name: news
description: Build Aman's morning news brief (lists/news/YYYY-MM-DD.md) from a web search of the last 24 hours on his watchlist, which is every company in his company list plus key investors, people and sector themes in robotics, AI for science, frontier AI, AI apps, energy/hard tech and VC. It covers fundraises across those sectors, investor news and interview/podcast/X insights, with a source link on every headline. Saves it, loads it into the phone app's News tab and pushes. Use when Aman types /news, asks for his news brief or "what happened in <sector>", or when /today runs its news step.
---

# /news: the morning news brief

Aman is not technical. Keep messages short and plain.

Settings live in `config/settings.yaml` under `news`. Read them first; if they disagree with this file, settings.yaml wins.

Files:
- `lists/news/YYYY-MM-DD.md`: **the master**, one brief per day. The first one (2026-10-20) was a 7-day catch-up and is the model for format and tone.
- **Web app, News tab** (https://your-app.vercel.app; web app only since D-036): read-only view. One database doc per day, `news/<date>`, built by `python3 scripts/news_to_app.py lists/news/<date>.md <out_dir>`. Never edit it by hand.
- `lists/news-state.json`: `last_run` (Boston ISO time) and `seen` (headline keys + URLs from the last 14 days), so a story isn't repeated tomorrow.

## What Aman might say

| He says | Do |
|---|---|
| `/news`, "news brief", "what's new" | **Build** today's brief (section A) |
| "news on X", "what's happening with Acme?" | One-off search on X (section B); don't save a brief |
| "explain X", "why does X matter?" | Use the explain skill (section B there) |
| "add X to my news", "stop following X" | Edit `news` in `config/settings.yaml`, commit, push, one-line reply |

---

## A. Build the brief

### A1. Get ready
1. `git pull`. Read `config/settings.yaml` (`news`, `companies.sectors`), `lists/news-state.json`, and the company list (`lists/companies.md`; every company there is on the watchlist). Follow the **News** heading of `config/preferences.md` (rules Aman approved from his comments in the app).
2. **Window** = since `last_run`, normally the last 24 hours. On Monday (or after a gap), cover everything since the last brief, up to 7 days. Today = the Boston date.
3. If today's brief already exists, ask: refresh it, or leave it.

### A2. Search (in parallel)
The brief is the costliest part of `/today`, so it runs on a budget (D-052; numbers in `news` in settings.yaml). Launch **`news.agents` (3) background agents** (Agent tool, `researcher`, which runs on the cheaper model; never `general-purpose`, which runs on the main one) in one message so they run at the same time. Each gets **at most `news.searches_per_agent` searches** (15; Saturday and Sunday `weekend_searches_per_agent`, 8) and **at most `page_reads_per_agent` page reads** (8):

| Agent | Covers |
|---|---|
| Robotics, physical AI & AI for science | humanoids, robot models, warehouse, AVs; autonomous labs, AI drug and materials discovery; the Robotics, AI for science and Biotech sectors. **Acme Sciences always.** |
| Frontier AI & AI apps | labs, models, chips, data centers and their power; agents, coding tools, enterprise AI, GTM/FDE news; the Foundation models & AI infrastructure and AI applications sectors |
| Energy, hard tech, VC & ideas | fusion, fission, geothermal, grid, batteries, space, quantum, defense (Energy + Hard tech sectors); `news.investors` (new funds, partner moves, theses, deals led); the week's biggest rounds; interviews, podcasts and X posts by `news.people` |

Keep each prompt short: the agent reads the long lists itself. Each agent's prompt must say:
- the exact window (dates and times in Boston time) and today's date;
- its search and page-read caps: **search for several names at once** (`"Skild AI" OR "Field AI" OR "1X" funding`), one or two searches per theme, and open a page only when the search result doesn't show the date, amount or source;
- the companies: "read your sectors' rows in `lists/companies.md` and `news.extra_companies`, `news.investors` and `news.people` in `config/settings.yaml`". Don't paste the lists into the prompt;
- **also search beyond the names**: new fundraises by *any* startup in the sector, big deals/partnerships/launches, and interviews with a real insight (`news.also_cover`);
- skip anything already in `seen`: "read `lists/news-state.json` and skip its URLs and headlines" (don't paste it);
- the **rules**: only items with a real URL it actually saw; never invent URLs, dates, amounts or quotes; mark single-source or uncertain facts `(unconfirmed)`; summarise in its own words, at most one quote under 15 words; X is only reachable through web search and news coverage;
- the **return format**: one bullet per item, `- **Headline** (Company · YYYY-MM-DD). 1–2 sentences with the numbers. *Why it matters:* one line. [Source](URL)`, then a `Fundraises` table (Company | What | Amount | Stage | Lead | Date | Link), then one line listing names with no news.

While the agents run, read nothing else that needs the web. Inside `/today`, launch them first and do the Outlook/Notes/Granola steps while they work.

### A3. Write the brief
Combine the agents' results. Drop duplicates (same story from two agents → keep one, merge links). Drop anything outside the window unless it's major and new to Aman. Then write `lists/news/<date>.md`:

```markdown
# News brief: Wed, Oct 21, 2026

*Last 24 hours (Oct 20, 7 AM – Oct 21, 7 AM). Every headline links to its source. "(unconfirmed)" = one secondary source or a detail I couldn't verify.*

---

## ⭐ Top 5 today

1. **Headline.** One or two plain sentences. [Source](url)

## ☕ For today

- Talking points for today's meetings, tied to news (e.g. a coffee with someone at Acme Sciences → Acme Sciences and competitor news). Skip the section if nothing relates.

## 🤖 Robotics & physical AI

- **Headline** (Oct 21). What happened, with numbers. *Why it matters:* one line. [Source](url)

## 🧪 AI for science & bio
## 🧠 Frontier AI & infrastructure
## 💻 AI apps & software
## ⚡ Energy, climate & hard tech
## 💰 VC & investors

## 💸 Fundraises

| Company | What | Amount | Stage | Lead | Date | Link |
|---|---|---|---|---|---|---|

## 🎙️ Interviews & ideas

- **Person (role): format** (date). The insight. *Why it matters:* one line. [Source](url)

---

## About this brief

- **Coverage:** which watchlist names had no news (one line), and anything the search cap cut short.
```

Rules:
- **Every headline has at least one link.** No link → leave it out.
- Leave out empty sector sections. Keep `Top 5` and `Fundraises` (write `- Nothing new today` if empty).
- Order inside a section: Aman's own companies and contacts first, then size and importance.
- Tie news to Aman where it fits: a company on his list, a person in `lists/network.md`, a meeting today, Energy Club, recruiting. Say so in *Why it matters*.
- Indented sub-bullets (`  - `) are fine for lists inside an item; the app shows them as bullets.
- Plain language; define a term the first time (e.g. "pro-rata rights: an early investor's right to keep its share in later rounds").
- Copy no article text. Short facts in your own words.
- Length: a 5-minute read, `news.items` (about 20–30 items on a normal day, 12–20 on a weekend). Fewer, better items beat a long list.

### A4. Save, load into the app, push
This is information, not one of Aman's lists, so it saves without an approval step (decision D-024). Show the Top 5 in chat after saving.
1. Write the file. Update `lists/news-state.json`: `last_run` = now (Boston ISO); add each item's URL and a short headline key to `seen` with today's date; drop `seen` entries older than 14 days.
2. **App:** `python3 scripts/news_to_app.py lists/news/<date>.md <scratchpad>/news-<date> | python3 scripts/webdb.py push -`. Re-running it for the same day overwrites `news/<date>`. If the save fails, say so plainly.
3. `git add lists/news lists/news-state.json && git commit -m "News: <Day, Mon D>" && git push` (with the Co-Authored-By line used in this repo). Inside `/today` this goes in the same commit as the to-do list.
4. Tell Aman in one line: how many items, the single biggest story, and that it's in the app and on GitHub.

### A5. Suggest, don't change
If a story shows a company should be on his company list (a new company in his sectors, a rename like Orbital Materials → Orbital Industries), list it at the end of the chat reply as a suggestion for `/companies`. Never edit `lists/companies.md` or `lists/network.md` from here.

---

### A6. Then explain
The brief is the breadth. Right after it's saved, run `/explain` (`.claude/skills/explain/SKILL.md`) to turn it into 3–5 stories explained simply (inside `/today` this is step A4e2). On its own, `/news` ends by offering it: "Want today's stories explained? Say /explain."

---

## B. One-off questions

For "news on X": run up to ~15 searches yourself (no agents), answer in chat with 3–8 linked bullets, newest first. Don't write a brief or touch the app unless Aman asks to save it.
