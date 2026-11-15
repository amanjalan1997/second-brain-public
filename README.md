# Second Brain

A personal AI system that runs my day as an MBA student recruiting in venture capital and technology. I designed it and built it with Claude Code as my engineering partner, and I have used it daily since October 2026.

## The problem

The information I need to act on is scattered across Outlook email and calendar, Apple Notes, Granola call notes and Canvas. Keeping track of people, companies and follow-ups by hand meant that things slipped, and preparing for meetings took time I did not have.

## What it does

Each morning, one command reads those sources and updates a web app on my phone and laptop:

| Section | What it holds |
|---|---|
| **Today** | A ranked to-do list built from email, calendar, notes and calls, with unfinished items carried over |
| **Meetings** | A researched brief for every meeting that matters: the 60-second version, questions to ask, the person, the company, our history and sources for every fact |
| **Emails** | Drafts written in my voice for the emails that need me, plus the threads I am waiting on |
| **Network** | Everyone I have met: how we met, what I learned and the next step |
| **Companies** | Every company I come across, grouped by sector, with what it does and where I heard of it |
| **News** | A daily brief on my companies, investors and sectors, with a few stories explained simply |
| **Calls & research** | Insights from every call filed by theme, and open research questions with the evidence behind my current view |
| **Podcasts** | Anything I want to understand, turned into a short two-host episode |

A **Refresh** button in the app reruns the update during the day.

## Design principles

1. **Claude suggests, I approve.** Nothing is sent from my account until I tap Send on that exact draft. A separate process sends only what I approved, checks the text word for word against what I saw, and refuses anything that changed.
2. **Human checkpoints only where a mistake is costly.** Low-risk work (the to-do list, the news, briefs) runs to completion; I correct it afterwards with comments in the app. Sending email and creating calendar invites always need my explicit approval.
3. **It learns from corrections.** When I edit or delete a task, rewrite a draft or leave a comment, the change is logged and turned into a proposed rule. A rule takes effect only once I accept it.
4. **Measure cost.** Each run is measured. Moving email reading to a smaller model that returns a short digest was expected to cut the cost of a morning update by roughly a third.
5. **Private by default.** The database has an owner-only rule, secrets stay in `.env`, and raw email and note text never enters the repository.

## How it fits together

- **Workflows** are Claude Code skills in `.claude/skills/` (for example `today`, `brief`, `email`, `network`, `companies`, `news`). Each one is a written procedure that Claude follows.
- **Scripts** in `scripts/` do the deterministic work: reading Apple Notes and Canvas, saving to the database, computing free meeting times, checking and sending approved emails, and testing the app layout.
- **The app** (`app/index.html`) is a single-file web app hosted on Vercel, with Supabase as the database. It installs on a phone's home screen.
- **Background helpers** on my Mac (macOS launch agents) pick up Refresh requests, send approved emails and record podcasts.

## What is not included

My lists, settings, notes and drafts are personal and are not in this repository, so it will not run as is. The names in examples have been changed. To adapt it, copy `app/config.example.js` to `app/config.js`, create a Supabase project from `supabase/schema.sql`, and put your keys in `.env`.

## Built with

Claude Code, Python, a single-file JavaScript web app, Vercel, Supabase, the Microsoft 365 (Outlook) and Granola connectors, AppleScript for Apple Notes, the Canvas API, Playwright and NotebookLM.
