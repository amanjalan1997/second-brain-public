---
name: draft-review
description: Open a draft Claude wrote (email, note, prep doc, plan, post) in Roughdraft inside the app's right-hand browser panel so Aman can comment and suggest edits, wait for him to click Approve, then apply his feedback. Use whenever Claude writes a draft longer than a few lines for Aman to review, or when Aman says "open it in Roughdraft", "rd", "let me review this" or /draft-review.
---

# Draft review in Roughdraft

Roughdraft is a local Markdown review app (https://github.com/Lex-Inc/roughdraft). It runs only on this Mac at http://localhost:7373: no account, no cloud. Aman leaves comments and suggested edits, then clicks **Approve** at the top right. Its ▾ menu has an overall-comment box and **Submit with comment**. Roughdraft's docs call this "Done Reviewing", but version 0.1.10 has no button with that name, so always tell Aman to click **Approve**.

Aman is not technical. Keep messages short and plain.

## Setup facts

- Node.js lives in `~/.local/node` and is **not** on the shell PATH. Start **every** Roughdraft command with `export PATH="$HOME/.local/node/bin:$PATH";`. The full path alone is not enough, because Roughdraft runs `env node` and fails with exit code 127 when Node isn't on the PATH. The commands below write `roughdraft` for short.
- If it's missing or broken, run `roughdraft doctor` and tell Aman. Version 0.1.10 shipped without its `yaml` dependency; the fix was `npm i --no-save --omit=dev yaml@^2.9.0` inside `~/.local/node/lib/node_modules/roughdraft`. Reinstalls or updates may need it again.

## When to use it

- Any draft longer than a few lines that Aman should review before it's used: emails, cover letters, coffee-chat notes, prep docs, plans, posts.
- Not for list drafts from `/today`, `/network`, `/companies` (those keep their own approve-in-chat flow), unless Aman asks.

## Steps

1. **Write the draft** as Markdown to `drafts/<YYYY-MM-DD>-<short-slug>.md` in this repo. `drafts/` is git-ignored: drafts often quote email text and never get committed (CLAUDE.md rule 5).
2. **Open it.** A hook (`.claude/hooks/open-in-roughdraft.sh`, D-026) handles this for every Markdown file Claude writes or edits outside CLAUDE.md, `docs/`, `.claude/` and `lists/`, once per session. In Conductor it opens the file in Aman's default browser by itself; don't open it again. In the Claude desktop app it can't reach the panel, so it reminds you to do the panel step below. Use these steps by hand only when the hook didn't fire (or Aman closed the tab):
   - **Claude desktop app** (the `mcp__Claude_Browser__*` tools exist): run `roughdraft open "<absolute path>" --no-watch --print-url`. This starts the server if needed and prints a URL. Open that URL with `mcp__Claude_Browser__preview_start` (`url` param) so it shows in the right-hand panel. If the panel is already open, `mcp__Claude_Browser__navigate` to it instead. Then **always** call `mcp__ccd_view__show_pane` with `pane: "preview"`, because the panel can be open but hidden.
   - **Conductor, or anywhere else without those tools:** run `roughdraft open "<absolute path>" --no-watch`. This opens the draft in Aman's default browser. Also give him the URL (from `roughdraft open ... --no-watch --print-url`) in case he'd rather paste it into Conductor's in-app browser (⌘⇧B). In a Conductor workspace, the absolute path is inside that workspace's own `drafts/` folder.
3. **Wait for Approve.** `roughdraft watch` crashes with `UND_ERR_HEADERS_TIMEOUT` after 5 minutes without a click (Node's fetch timeout), so wrap it in a retry loop. Run this with Bash `run_in_background: true`. It gives up after 2 hours:
   `F="<absolute path>"; for i in $(seq 1 24); do out=$(roughdraft watch "$F" --json 2>&1) && { echo "$out"; exit 0; }; echo "$out" | grep -q UND_ERR_HEADERS_TIMEOUT || { echo "$out"; exit 1; }; done; exit 2`
   Tell Aman in one line: "Draft is open on the right (in Conductor: in your browser). Select text to comment or suggest edits, then click Approve (top right)." End the turn; the background command finishing wakes you up. If Aman says he's done in chat instead, carry on without waiting.
4. **Apply the feedback.** Re-read the file. Feedback is CriticMarkup:
   - `{>>comment<<}` comment, `{++text++}` insert, `{--text--}` delete, `{~~old~>new~~}` replace, `{==text==}` highlight.
   - Overall comments and comment metadata are in YAML endmatter at the end of the file.
   - Accept suggested edits unless they clash with something else he asked for; act on comments. Ignore markup inside code blocks.
   - Rewrite the file as a clean draft with all markup removed. If a comment needs his answer, leave a reply as `{>>…<<}{#cN}` with `by: Claude` and `re: <id>` in the endmatter (see `roughdraft help criticmarkup`).
5. **Show the new version.** Reload the panel (navigate to the same URL); in Conductor the browser page picks up the rewritten file by itself (if not, run `roughdraft open` again). Start step 3 again. Repeat until Aman says it's final.
6. **Finish.** Give him the final text in chat, ready to copy, or do what he asked with it (e.g. save an Outlook draft only if he asked for that specific action, CLAUDE.md rule 4).
