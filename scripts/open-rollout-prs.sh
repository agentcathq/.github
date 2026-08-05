#!/usr/bin/env bash
# Opens one rollout PR per repo in scripts/repos.json, adding
# .github/dependabot.yml and .github/workflows/dependabot-auto-merge.yml
# from build/<repo>/. Requires: generate-configs.sh already run.
set -euo pipefail
cd "$(dirname "$0")/.."
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

rollout_repo() {
  local name="$1"

  # Skip if rollout PR already open
  if [ -n "$(gh pr list --repo "agentcathq/$name" --head chore/dependabot-rollout --state open --json number --jq '.[].number')" ]; then
    echo "skip: $name (rollout PR already open)"
    return 0
  fi

  # Clone and work in temp directory (use subshell to avoid cd back)
  (
    set -e
    git clone --depth 1 "https://github.com/agentcathq/$name.git" "$WORK/$name"
    cd "$WORK/$name"
    git checkout -b chore/dependabot-rollout
    mkdir -p .github/workflows
    cp "$OLDPWD/build/$name/dependabot.yml" .github/dependabot.yml
    cp "$OLDPWD/build/$name/dependabot-auto-merge.yml" .github/workflows/dependabot-auto-merge.yml
    git add .github
    git commit -m "chore: enable Dependabot with org auto-merge policy

Weekly grouped version updates (7d cooldown), security updates via org config.
Patch/minor auto-merge behind CI per the org standard-changes policy;
majors and critical security updates require human review."
    git push -u origin chore/dependabot-rollout
    gh pr create --repo "agentcathq/$name" \
      --title "chore: enable Dependabot with org auto-merge policy" \
      --body "Rollout per agentcathq/.github docs/superpowers/specs/2026-08-05-dependabot-soc2-design.md.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
  ) || return 1
}

FAILED=""
while read -r name; do
  echo "=== $name ==="
  if rollout_repo "$name"; then
    echo "ok: $name"
  else
    echo "FAIL: $name"
    FAILED="$FAILED $name"
  fi
done < <(jq -r '.repos[].name' scripts/repos.json)

if [ -z "$FAILED" ]; then
  echo "All rollout PRs opened."
else
  echo "Failed repos:$FAILED"
  exit 1
fi
