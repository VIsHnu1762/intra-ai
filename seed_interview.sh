#!/usr/bin/env bash
# seed_interview.sh — Quick seed script to create an interview session for testing
# Usage: ./seed_interview.sh [interview_id] [agents]
# Examples:
#   ./seed_interview.sh                           → creates a default Alex-only session
#   ./seed_interview.sh my-interview-id alex      → Alex only
#   ./seed_interview.sh my-interview-id jordan    → Jordan only
#   ./seed_interview.sh my-interview-id alex,jordan → Both agents
#
# After running, open: http://localhost:3000/interview/{interview_id}/prep

set -e

API_URL="${API_URL:-http://localhost:8000}"
INTERVIEW_ID="${1:-demo-interview-001}"
AGENTS_RAW="${2:-alex}"

# Build agent_ids JSON array
IFS=',' read -ra AGENT_LIST <<< "$AGENTS_RAW"
AGENTS_JSON="["
for i in "${!AGENT_LIST[@]}"; do
  agent=$(echo "${AGENT_LIST[$i]}" | tr -d ' ')
  [ $i -gt 0 ] && AGENTS_JSON+=","
  AGENTS_JSON+="\"$agent\""
done
AGENTS_JSON+="]"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     Intra AI Interview Session Seed           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Interview ID : $INTERVIEW_ID"
echo "  Agents       : $AGENTS_JSON"
echo "  API          : $API_URL"
echo ""

RESPONSE=$(curl -s -X POST "$API_URL/api/v1/sessions" \
  -H "Content-Type: application/json" \
  -d "{
    \"interview_id\": \"$INTERVIEW_ID\",
    \"candidate_id\": \"cand-${INTERVIEW_ID}\",
    \"agent_ids\": $AGENTS_JSON,
    \"duration_minutes\": 60,
    \"job_title\": \"Senior Software Engineer\",
    \"company\": \"Intra AI\"
  }")

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

CHANNEL=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('channel_name',''))" 2>/dev/null || echo "")

echo ""
echo "══════════════════════════════════════════════"
echo "✅ Session created!"
echo ""
echo "  Candidate link:"
echo "  → http://localhost:3000/interview/$INTERVIEW_ID/prep"
echo ""
if [ -n "$CHANNEL" ]; then
  echo "  Agora channel: $CHANNEL"
fi
echo "══════════════════════════════════════════════"
echo ""
