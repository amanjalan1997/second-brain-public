#!/bin/bash
# Runs after Claude writes or edits a file (PostToolUse hook, see .claude/settings.json).
# Opens Markdown files in Roughdraft so Aman can read and comment without asking (D-026).
# Each file opens once per session. In Conductor it opens in the default browser; in the Claude
# desktop app a hook can't reach the right-hand panel, so it tells Claude to open it there.
# Skipped: Claude's bookkeeping (CLAUDE.md, docs/, .claude/) and the lists, which are approved in chat.

input=$(cat)
# background runs from the app's Refresh button (D-037) have nobody to show it to
[ -n "$SECOND_BRAIN_HEADLESS" ] && exit 0
file=$(printf '%s' "$input" | /usr/bin/jq -r '.tool_input.file_path // empty')
session=$(printf '%s' "$input" | /usr/bin/jq -r '.session_id // "none"')

case "$file" in *.md|*.markdown) ;; *) exit 0 ;; esac
[ -f "$file" ] || exit 0

repo="${CLAUDE_PROJECT_DIR:-$(pwd)}"
rel="${file#"$repo"/}"
case "$rel" in
  CLAUDE.md|README.md|docs/*|.claude/*|lists/*|*/node_modules/*) exit 0 ;;
esac

seen="${TMPDIR:-/tmp}/roughdraft-opened-$session"
grep -qxF "$file" "$seen" 2>/dev/null && exit 0
echo "$file" >> "$seen"

export PATH="$HOME/.local/node/bin:$PATH"
if [ -n "$CONDUCTOR_WORKSPACE_ID" ]; then
  nohup roughdraft open "$file" --no-watch >/dev/null 2>&1 &
  exit 0
fi
msg="Roughdraft auto-open (D-026): show $file in the right-hand panel now, using the Claude desktop app steps in the draft-review skill (step 2). If the panel tools aren't available, run: roughdraft open \"$file\" --no-watch"
/usr/bin/jq -n --arg m "$msg" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $m}}'
exit 0
