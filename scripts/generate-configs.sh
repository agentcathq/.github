#!/usr/bin/env bash
# Generates build/<repo>/dependabot.yml and build/<repo>/dependabot-auto-merge.yml
# for every repo in scripts/repos.json. Idempotent; overwrites build/.
set -euo pipefail
cd "$(dirname "$0")/.."

jq -c '.repos[]' scripts/repos.json | while read -r repo; do
  name=$(jq -r .name <<<"$repo")
  checks=$(jq -c '.required_checks' <<<"$repo")
  mkdir -p "build/$name"

  {
    echo "version: 2"
    echo "updates:"
    jq -c '.ecosystems[]' <<<"$repo" | while read -r eco; do
      ecosystem=$(jq -r .ecosystem <<<"$eco")
      directory=$(jq -r .directory <<<"$eco")
      cat <<EOF
  - package-ecosystem: "$ecosystem"
    directory: "$directory"
    schedule:
      interval: "weekly"
      day: "monday"
    cooldown:
      default-days: 7
      semver-major-days: 30
    groups:
      ${ecosystem}-minor-patch:
        applies-to: version-updates
        patterns: ["*"]
        update-types: ["minor", "patch"]
      ${ecosystem}-security:
        applies-to: security-updates
        patterns: ["*"]
EOF
    done
  } > "build/$name/dependabot.yml"

  if [ "$checks" != "[]" ]; then
    cat > "build/$name/dependabot-auto-merge.yml" <<'EOF'
name: Dependabot auto-merge

on: pull_request

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    if: github.event.pull_request.user.login == 'dependabot[bot]'
    uses: agentcathq/.github/.github/workflows/dependabot-auto-merge.yml@main
EOF
    echo "generated: $name"
  else
    echo "generated: $name (no caller — no required checks)"
  fi
done
