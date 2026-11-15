#!/bin/bash
# PermissionRequest hook for background refreshes (D-039). The Microsoft 365 connector asks for approval before
# every Outlook call ("Your organization requires approval for this tool"), and a background run has nobody to
# ask. So Aman answers in the app when he taps Refresh, and refresh_helper.py passes his answer in
# SECOND_BRAIN_OUTLOOK ("allowed" or "skipped") for that one run. This hook gives that answer:
#   - Outlook *read* tools: allowed only if he tapped Allow for this refresh.
#   - any other Microsoft 365 tool (send, draft, calendar changes, delete): always refused.
#   - everything else: no answer (the helper's --allowedTools list decides).
# Every Outlook answer is logged in ~/.second-brain/logs/outlook-access.log.

in=$(cat)
tool=$(printf '%s' "$in" | /usr/bin/jq -r '.tool_name // empty')
answer() {
  mkdir -p "$HOME/.second-brain/logs"
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1 $tool" >> "$HOME/.second-brain/logs/outlook-access.log"
  if [ "$1" = allow ]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}'
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"deny","message":"%s"}}}\n' "$2"
  fi
  exit 0
}
case "$tool" in
  mcp__claude_ai_Microsoft_365__outlook_email_search|mcp__claude_ai_Microsoft_365__outlook_calendar_search|\
  mcp__claude_ai_Microsoft_365__read_resource|mcp__claude_ai_Microsoft_365__search_people)
    [ "$SECOND_BRAIN_OUTLOOK" = "allowed" ] && answer allow
    answer deny "Aman chose to refresh without Outlook this time. Skip email and calendar." ;;
  mcp__claude_ai_Microsoft_365__*)
    answer deny "Background refreshes only read Outlook. Never send, draft or change anything." ;;
esac
exit 0
