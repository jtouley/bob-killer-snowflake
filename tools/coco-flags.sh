# Flags for every CoCo build call. Sourced by tools/coco-phase.
# Source of truth: .context/evidence/coco_cli_*.txt (`cortex exec --help`, CoCo v1.2.14).
# Changes to this file are gate changes: human review only (SPEC §1.2 control 5).
COCO_CONNECTION="bob_killer"
COCO_WORKTREE="${COCO_WORKTREE:-$(cd "$(git rev-parse --show-toplevel)/.." && pwd)/bob-killer-snowflake-coco}"
COCO_FLAGS=(
  --format json            # machine-readable log
  --no-mcp                 # do not load Claude Code's MCP servers from ~/.claude.json
  --private                # no conversation history kept server-side
  --max-turns 200          # safety ceiling per phase call
  # --blocked = these tools are blocked, all others allowed (exec rejects interactive prompts).
  # The post-call checks in SPEC §1.8 stay the real guard.
  --blocked "Bash(git push *),Bash(git reset *),Bash(git rebase *),Bash(git commit --amend *),Bash(git worktree *),Bash(git checkout *),Bash(git switch *),Bash(git branch -D *),Bash(git tag *),Bash(rm -rf *)"
)
