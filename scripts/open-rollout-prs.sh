#!/usr/bin/env bash
# Opens one rollout PR per repo in scripts/repos.json, adding
# .github/dependabot.yml and .github/workflows/dependabot-auto-merge.yml
# from build/<repo>/. Requires: generate-configs.sh already run.
set -euo pipefail
cd "$(dirname "$0")/.."
WORK=$(mktemp -d)

jq -r '.repos[].name' scripts/repos.json | while read -r name; do
  echo "=== $name ==="
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
  cd "$OLDPWD"
done
echo "All rollout PRs opened."
