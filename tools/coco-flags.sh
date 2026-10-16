# Flags for every CoCo build call. Sourced by tools/coco-phase, coco-probe, smoke-test.
# Source of truth: .context/evidence/coco_cli_*.txt (`cortex exec --help`, CoCo v1.2.14).
# Changes to this file are gate changes: human review only (SPEC §1.2 control 5).
COCO_CONNECTION="bob_killer"
_repo_root="$(git rev-parse --show-toplevel)"
COCO_CLONE="${COCO_CLONE:-$(cd "$_repo_root/.." && pwd)/bob-killer-snowflake-coco}"
COCO_TIMEOUT_S="${COCO_TIMEOUT_S:-6600}"   # below the 2 h ceiling of a Claude Code background command
COCO_FLAGS=(
  --format json            # machine-readable log
  --no-mcp                 # do not load Claude Code's MCP servers from ~/.claude.json
  --private                # no conversation history kept server-side
  --max-turns 200          # safety ceiling per call
  # --blocked: "Tools that are blocked (all others allowed)" per `cortex exec --help`.
  # Whether the others then run without --bypass is proven by tools/coco-probe (SPEC §1.5).
  # This list is a speed bump; the real guard is the isolated clone + tools/coco-guard.
  --blocked "Bash(git push*),Bash(git remote*),Bash(git reset*),Bash(git rebase*),Bash(git commit --amend*),Bash(git worktree*),Bash(git checkout*),Bash(git switch*),Bash(git branch*),Bash(git tag*),Bash(git update-ref*),Bash(git config*),Bash(git stash*),Bash(git clean*),Bash(git filter-branch*),Bash(git gc*),Bash(rm -rf*),Bash(rm -fr*),Bash(rm -r *)"
)
