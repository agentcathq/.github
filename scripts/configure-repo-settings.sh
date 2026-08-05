#!/usr/bin/env bash
# Applies per-repo settings for the Dependabot rollout:
#   1. allow_auto_merge on the repo
#   2. labels security-critical / major-update
#   3. branch protection: required status checks on the default branch
#   4. CODEOWNERS audit: flags rules covering dependency manifests
# Usage: scripts/configure-repo-settings.sh [--dry-run]
set -euo pipefail
cd "$(dirname "$0")/.."
DRY=${1:-}
if [ -n "$DRY" ] && [ "$DRY" != "--dry-run" ]; then
  echo "usage: $0 [--dry-run]" >&2
  exit 2
fi

run() { if [ "$DRY" = "--dry-run" ]; then echo "DRY: $*"; else "$@"; fi; }

jq -c '.repos[]' scripts/repos.json | while read -r repo; do
  name=$(jq -r .name <<<"$repo")
  branch=$(jq -r .default_branch <<<"$repo")
  checks=$(jq -c '.required_checks' <<<"$repo")
  echo "=== $name ==="

  if [ "$checks" != "[]" ]; then
    run gh api -X PATCH "repos/agentcathq/$name" -F allow_auto_merge=true --silent
  fi

  run gh label create security-critical --repo "agentcathq/$name" \
    --color B60205 --description "Critical-severity security update - human review required" --force
  run gh label create major-update --repo "agentcathq/$name" \
    --color FBCA04 --description "Semver-major update - human review required" --force

  if [ "$checks" != "[]" ]; then
    body=$(jq -n --argjson c "$checks" '{
      required_status_checks: {strict: false, contexts: $c},
      enforce_admins: false,
      required_pull_request_reviews: null,
      restrictions: null,
      allow_force_pushes: false,
      allow_deletions: false
    }')
    if [ "$DRY" = "--dry-run" ]; then
      echo "DRY: PUT repos/agentcathq/$name/branches/$branch/protection <<< $body"
    else
      gh api -X PUT "repos/agentcathq/$name/branches/$branch/protection" --input - <<<"$body" --silent
    fi
  else
    echo "WARN: $name has no required_checks - auto-merge would be ungated. Fix repos.json first. Auto-merge was NOT enabled, pending CI."
  fi

  for path in CODEOWNERS .github/CODEOWNERS docs/CODEOWNERS; do
    content=$(gh api "repos/agentcathq/$name/contents/$path" --jq .content 2>/dev/null | base64 -d 2>/dev/null) || continue
    hits=$(grep -nE 'package\.json|package-lock|go\.(mod|sum)|requirements|pyproject|poetry\.lock|uv\.lock|\*' <<<"$content" || true)
    [ -n "$hits" ] && printf 'WARN: %s %s may gate manifests (bot approval cannot satisfy code-owner review):\n%s\n' "$name" "$path" "$hits"
  done
done
