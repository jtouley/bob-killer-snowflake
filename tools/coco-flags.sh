# Flags for every CoCo build call. Sourced by tools/coco-phase, coco-probe, smoke-test.
# Source of truth: .context/evidence/coco_cli_*.txt (`cortex exec --help`, CoCo v1.2.14).
# Changes to this file are gate changes: human review only (SPEC §1.2 control 5).
COCO_CONNECTION="bob_killer"
_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COCO_CLONE="${COCO_CLONE:-$(cd "$_repo_root/.." && pwd)/bob-killer-snowflake-coco}"
COCO_TIMEOUT_S="${COCO_TIMEOUT_S:-6600}"   # below the 2 h ceiling of a Claude Code background command
COCO_BIN="${COCO_BIN:-cortex}"            # tests set an explicit stub path; never fall back silently
COCO_FLAGS=(
  --format json            # machine-readable log
  --no-mcp                 # do not load Claude Code's MCP servers from ~/.claude.json
  --private                # no conversation history kept server-side
  --max-turns 200          # safety ceiling per call
  # exec rejects every tool that needs a prompt, and `--blocked` alone does NOT allow the rest
  # (coco-probe, 2026-10-16). So: an explicit allowlist of CoCo's tool names (from the exec init
  # event), plus `--blocked` patterns that override it (probe: "permanently blocked by session policy").
  # Left out on purpose: ask_user_question, cron_*, team_*/spawn_teammate/send_message, plan mode.
  --allowed "read,write,edit,bash,bash_output,kill_shell,grep,glob,tgrep,sql_execute,web_fetch,task,agent_output,kill_agent,monitor,tool_search,notebook_actions,data_diff"
  --blocked "Bash(git push*),Bash(git remote*),Bash(git reset*),Bash(git rebase*),Bash(git commit --amend*),Bash(git worktree*),Bash(git checkout*),Bash(git switch*),Bash(git branch*),Bash(git tag*),Bash(git update-ref*),Bash(git config*),Bash(git stash*),Bash(git clean*),Bash(git filter-branch*),Bash(git gc*),Bash(rm -rf*),Bash(rm -fr*),Bash(rm -r *)"
)
