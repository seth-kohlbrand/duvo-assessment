#!/usr/bin/env bash
# End-to-end agent demo: connect a real agent (Claude Code headless) to the
# StoreLink buyer MCP server and drive the pilot buyer task through it.
#
# Usage: scripts/agent_demo.sh [idempotency-key]
#
# Requires: docker, claude CLI, jq.
# Artifacts land in demo_artifacts/: the generated MCP config, the raw
# stream-json transcript, the tool calls the agent made, and its final answer.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$REPO_ROOT/demo_artifacts"
IMAGE="storelink-buyer-mcp:exercise"
KEY="${1:-agent-demo-$(date +%Y%m%d-%H%M%S)}"

mkdir -p "$OUT_DIR" "$REPO_ROOT/audit"

echo "==> Building server image ($IMAGE)"
docker build -q -t "$IMAGE" "$REPO_ROOT"

# Generate the MCP config for this checkout; the audit mount must be absolute.
CONFIG="$OUT_DIR/mcp-config.json"
cat > "$CONFIG" <<EOF
{
  "mcpServers": {
    "storelink": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "STORELINK_AUDIT_DIR=/audit",
        "-v", "$REPO_ROOT/audit:/audit",
        "$IMAGE"
      ]
    }
  }
}
EOF

echo "==> Smoke check: agent discovers the tool surface"
claude -p "List the tool names available from the storelink MCP server, one per line, nothing else." \
  --mcp-config "$CONFIG" --strict-mcp-config \
  --allowedTools "mcp__storelink__*" \
  | tee "$OUT_DIR/tool_list.txt"

echo
echo "==> Buyer task driven by the agent (idempotency key: $KEY)"
claude -p "You are a category buyer for Korral using StoreLink via MCP. SKU 8847291 may be running low at stores 47 and 102. Investigate and replenish whichever stores need it, using idempotency key $KEY. Then prove the write is retry-safe by re-issuing the exact same replenishment call with the same idempotency key and reporting what the server does. Finish with a summary of what happened at each store and why." \
  --mcp-config "$CONFIG" --strict-mcp-config \
  --allowedTools "mcp__storelink__*" \
  --output-format stream-json --verbose > "$OUT_DIR/agent_run.jsonl"

echo
echo "==> Tool calls the agent made:"
jq -r 'select(.type == "assistant") | .message.content[]?
       | select(.type == "tool_use") | "\(.name) \(.input | tojson)"' \
  "$OUT_DIR/agent_run.jsonl" | tee "$OUT_DIR/tool_calls.txt"

echo
echo "==> Agent final answer:"
jq -r 'select(.type == "result") | .result' \
  "$OUT_DIR/agent_run.jsonl" | tee "$OUT_DIR/final_answer.md"

echo
echo "==> Last buyer audit records written through the mounted volume:"
tail -n 2 "$REPO_ROOT/audit/buyer.jsonl" | jq -r '.plain_language_summary'

echo
echo "Artifacts: $OUT_DIR (tool_list.txt, agent_run.jsonl, tool_calls.txt, final_answer.md)"
