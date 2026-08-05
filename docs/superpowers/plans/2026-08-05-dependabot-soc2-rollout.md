# Org-wide Dependabot with SOC 2 Compliance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Roll out Dependabot across 11 agentcathq repos with critical alerts routed to humans via Slack and patch/minor updates auto-merged behind CI, satisfying SOC 2 Type II (Vanta).

**Architecture:** All security-sensitive automation lives once in the public `agentcathq/.github` repo — a reusable `workflow_call` auto-merge workflow and a scheduled critical-alert → Slack router. Each target repo receives two small generated files (a `dependabot.yml` and a ~10-line caller workflow) via scripted PRs, plus API-applied repo settings. Org-level GitHub settings and Vanta policy artifacts are documented as a runbook with the human-only steps marked.

**Tech Stack:** GitHub Actions, `gh` CLI, bash + `jq`, `actionlint`, Dependabot, Vanta.

**Spec:** `docs/superpowers/specs/2026-08-05-dependabot-soc2-design.md` (approved 2026-08-05).

## Global Constraints

- Org: `agentcathq`. Work in this repo happens on branch `dependabot-soc2-design`.
- In-scope repos (11): agentcat-ui, agentcat-server, agentcat-mcp, agentcat-go-sdk, agentcat-python-sdk, agentcat-typescript-sdk, webmcp-react, webmcp-gallery, mcpcat-go-sdk, reddit-monitor, lemlist-attio-sync — plus future repos via org default config. Excluded (documented in policy, never touched by rollout): skills, mcp-event-tracker, mcp-audit, mcpcat-go-api, agentcat-go-api, .github, mcpcat.
- Auto-merge ONLY when: update-type is `version-update:semver-patch` or `version-update:semver-minor` AND NOT (security PR with CVSS >= 9.0). Critical security PRs get label `security-critical`; majors get `major-update`; both stay open.
- Identity gate on `github.event.pull_request.user.login == 'dependabot[bot]'` — never `github.actor`. Trigger on `pull_request` only — never `pull_request_target`.
- Third-party actions pinned to full commit SHAs.
- Merge method: `gh pr merge --auto --squash`.
- Dependabot config: weekly schedule (Monday), cooldown `default-days: 7` / `semver-major-days: 30`, minor+patch grouped per ecosystem, `github-actions` ecosystem in every repo.
- SLAs (Vanta + policy): Critical 3d / High 14d / Medium 60d / Low 90d.
- Secrets on this repo (Actions secrets): `DEPENDABOT_ALERTS_READ_TOKEN` (fine-grained PAT, org Dependabot alerts: read), `SECURITY_SLACK_WEBHOOK_URL` (Slack incoming webhook).
- Steps marked **[HUMAN]** need org-owner/billing/Vanta access — pause and hand to the user.

---

### Task 1: Reusable auto-merge workflow

**Files:**
- Create: `.github/workflows/dependabot-auto-merge.yml`

**Interfaces:**
- Produces: reusable workflow callable as `agentcathq/.github/.github/workflows/dependabot-auto-merge.yml@main` with no inputs/secrets beyond the implicit `GITHUB_TOKEN` (Task 3's caller template and Task 7's rollout depend on this exact path). Labels used: `security-critical`, `major-update` (Task 4 creates them in each repo).

- [ ] **Step 1: Resolve the current fetch-metadata release SHA**

```bash
TAG=$(gh release view --repo dependabot/fetch-metadata --json tagName --jq .tagName)
SHA=$(gh api repos/dependabot/fetch-metadata/commits/$TAG --jq .sha)
echo "$TAG $SHA"
```

Expected: a tag (v2.x or v3.x) and a 40-char SHA. Use both in Step 2 (`uses: dependabot/fetch-metadata@<SHA> # <TAG>`).

- [ ] **Step 2: Write the workflow**

Create `.github/workflows/dependabot-auto-merge.yml` (substitute `<SHA>`/`<TAG>` from Step 1):

```yaml
name: Dependabot auto-merge (reusable)

on:
  workflow_call: {}

permissions:
  contents: write
  pull-requests: write

jobs:
  dependabot-auto-merge:
    runs-on: ubuntu-latest
    # Identity gate: pull_request.user.login, never github.actor —
    # actor is spoofable on attacker content via "@dependabot recreate".
    if: >-
      github.repository_owner == 'agentcathq' &&
      github.event_name == 'pull_request' &&
      github.event.pull_request.user.login == 'dependabot[bot]'
    steps:
      - name: Fetch Dependabot metadata
        id: metadata
        uses: dependabot/fetch-metadata@<SHA> # <TAG>
        with:
          alert-lookup: true
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Label critical security update for human review
        if: steps.metadata.outputs.alert-state != '' && steps.metadata.outputs.cvss >= 9.0
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: gh pr edit "$PR_URL" --add-label security-critical

      - name: Label major update for human review
        if: steps.metadata.outputs.update-type == 'version-update:semver-major'
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: gh pr edit "$PR_URL" --add-label major-update

      - name: Approve and enable auto-merge (patch/minor, non-critical only)
        if: >-
          (steps.metadata.outputs.update-type == 'version-update:semver-patch' ||
           steps.metadata.outputs.update-type == 'version-update:semver-minor') &&
          !(steps.metadata.outputs.alert-state != '' && steps.metadata.outputs.cvss >= 9.0)
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh pr review --approve "$PR_URL"
          gh pr merge --auto --squash "$PR_URL"
```

Notes: `cvss` is a numeric string (`0` when no alert); GitHub expressions coerce it for `>=`. The approve step is what satisfies Vanta's approved-by-non-author test. `--auto` merges only after all required status checks pass.

- [ ] **Step 3: Validate with actionlint**

```bash
which actionlint || brew install actionlint
actionlint .github/workflows/dependabot-auto-merge.yml
```

Expected: no output (clean).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/dependabot-auto-merge.yml
git commit -m "feat: reusable Dependabot auto-merge workflow (patch/minor, non-critical)"
```

---

### Task 2: Critical-alert Slack router

**Files:**
- Create: `.github/workflows/critical-alert-router.yml`

**Interfaces:**
- Consumes: repo Actions secrets `DEPENDABOT_ALERTS_READ_TOKEN`, `SECURITY_SLACK_WEBHOOK_URL` (created in Task 7 Step 2).
- Produces: 6-hourly Slack posts of open critical alerts; `workflow_dispatch` with a `severity` input used by Task 8's dry-run.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/critical-alert-router.yml`:

```yaml
name: Critical Dependabot alert router

on:
  schedule:
    - cron: '17 1,7,13,19 * * *'
  workflow_dispatch:
    inputs:
      severity:
        description: 'Severity filter (widen to "high" for verification dry-runs)'
        required: false
        default: 'critical'

permissions: {}

jobs:
  route:
    runs-on: ubuntu-latest
    steps:
      - name: Fetch open alerts
        id: fetch
        env:
          GH_TOKEN: ${{ secrets.DEPENDABOT_ALERTS_READ_TOKEN }}
          SEVERITY: ${{ inputs.severity || 'critical' }}
        run: |
          gh api --paginate \
            "/orgs/agentcathq/dependabot/alerts?severity=${SEVERITY}&state=open&per_page=100" \
            --jq '.' | jq -s 'add // []' > alerts.json
          echo "count=$(jq length alerts.json)" >> "$GITHUB_OUTPUT"

      - name: Post alerts to Slack
        if: steps.fetch.outputs.count != '0'
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SECURITY_SLACK_WEBHOOK_URL }}
          SLA_DAYS: '3'
        run: |
          jq --arg sla "$SLA_DAYS" -r '
            "🚨 *\(length) open critical Dependabot alert(s)* (SLA: \($sla) days)\n" +
            (map(
              "• <\(.html_url)|\(.repository.full_name): \(.dependency.package.name)> — " +
              "\(.security_advisory.severity) (CVSS \(.security_advisory.cvss.score // "n/a")) — " +
              "open \(((now - (.created_at | fromdateiso8601)) / 86400 | floor)) day(s)"
            ) | join("\n"))
          ' alerts.json > message.txt
          jq -n --rawfile text message.txt '{text: $text}' > payload.json
          curl -fsS -X POST -H 'Content-type: application/json' \
            --data @payload.json "$SLACK_WEBHOOK_URL"

  notify-failure:
    runs-on: ubuntu-latest
    needs: route
    if: failure()
    steps:
      - name: Report router failure to Slack
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SECURITY_SLACK_WEBHOOK_URL }}
        run: |
          curl -fsS -X POST -H 'Content-type: application/json' \
            --data '{"text":"⚠️ critical-alert-router FAILED — https://github.com/agentcathq/.github/actions"}' \
            "$SLACK_WEBHOOK_URL"
```

Notes: off-peak cron minute (`:17`) avoids the top-of-hour Actions rush. The `notify-failure` job is the "fails loudly" requirement — a broken router pings Slack instead of rotting silently. If the webhook itself is dead, GitHub's default workflow-failure email to the security-manager team is the last-resort signal.

- [ ] **Step 2: Validate with actionlint**

```bash
actionlint .github/workflows/critical-alert-router.yml
```

Expected: no output.

- [ ] **Step 3: Test the jq message template locally with fixture data**

```bash
mkdir -p /tmp/router-test && cd /tmp/router-test
cat > alerts.json <<'EOF'
[{"html_url":"https://github.com/agentcathq/agentcat-server/security/dependabot/1",
  "repository":{"full_name":"agentcathq/agentcat-server"},
  "dependency":{"package":{"name":"example-pkg"}},
  "security_advisory":{"severity":"critical","cvss":{"score":9.8}},
  "created_at":"2026-08-01T12:00:00Z"}]
EOF
jq --arg sla 3 -r '
  "🚨 *\(length) open critical Dependabot alert(s)* (SLA: \($sla) days)\n" +
  (map(
    "• <\(.html_url)|\(.repository.full_name): \(.dependency.package.name)> — " +
    "\(.security_advisory.severity) (CVSS \(.security_advisory.cvss.score // "n/a")) — " +
    "open \(((now - (.created_at | fromdateiso8601)) / 86400 | floor)) day(s)"
  ) | join("\n"))
' alerts.json
```

Expected: a formatted message line naming agentcat-server/example-pkg, CVSS 9.8, and a plausible day count. Fix the template in the workflow if jq errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/naseemalnaji/Projects/mcpcat/.github
git add .github/workflows/critical-alert-router.yml
git commit -m "feat: 6-hourly critical Dependabot alert router to Slack"
```

---

### Task 3: Repo inventory + config generator

**Files:**
- Create: `scripts/repos.json`
- Create: `scripts/generate-configs.sh`
- Output (gitignored): `build/<repo>/dependabot.yml`, `build/<repo>/dependabot-auto-merge.yml`
- Create: `.gitignore` (add `build/`)

**Interfaces:**
- Produces: `scripts/repos.json` — schema `{"repos":[{"name":str,"default_branch":str,"ecosystems":[{"ecosystem":str,"directory":str}],"required_checks":[str]}]}` — consumed by Tasks 4 and 7. `scripts/generate-configs.sh` writes both stamped files per repo into `build/`.

- [ ] **Step 1: Detect each repo's manifests, default branch, and CI check names**

```bash
for r in agentcat-ui agentcat-server agentcat-mcp agentcat-go-sdk agentcat-python-sdk \
         agentcat-typescript-sdk webmcp-react webmcp-gallery mcpcat-go-sdk \
         reddit-monitor lemlist-attio-sync; do
  echo "=== $r ==="
  gh api repos/agentcathq/$r --jq .default_branch
  gh api repos/agentcathq/$r/contents --jq '.[].name' | \
    grep -E '^(package\.json|go\.mod|pyproject\.toml|requirements.*\.txt|uv\.lock|poetry\.lock|Gemfile|Dockerfile)$' || echo "(no root manifests)"
  BRANCH=$(gh api repos/agentcathq/$r --jq .default_branch)
  gh api "repos/agentcathq/$r/commits/$BRANCH/check-runs" --jq '.check_runs[].name' | sort -u
done
```

Record per repo: default branch, ecosystems (`npm` for package.json, `gomod` for go.mod, `uv` if uv.lock else `pip` for Python manifests, `docker` if Dockerfile — plus `github-actions` for every repo), and CI check names. If a repo's manifests are not at the root (workspace/monorepo), list the subdirectory in `directory`. Also open each repo's CI workflow and check `on:` for `paths:` filters — a required check that skips on dependency-only PRs blocks auto-merge forever; note any such repo and drop that check from `required_checks` (or note it for a trigger fix).

- [ ] **Step 2: Write `scripts/repos.json` from the detection output**

Template (fill every repo from Step 1's real output — expected ecosystems shown; verify rather than trust):

```json
{
  "repos": [
    {"name": "agentcat-ui", "default_branch": "main",
     "ecosystems": [{"ecosystem": "npm", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []},
    {"name": "agentcat-server", "default_branch": "main",
     "ecosystems": [{"ecosystem": "uv", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []},
    {"name": "agentcat-mcp", "default_branch": "main",
     "ecosystems": [{"ecosystem": "npm", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []},
    {"name": "agentcat-go-sdk", "default_branch": "main",
     "ecosystems": [{"ecosystem": "gomod", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []},
    {"name": "agentcat-python-sdk", "default_branch": "main",
     "ecosystems": [{"ecosystem": "pip", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []},
    {"name": "agentcat-typescript-sdk", "default_branch": "main",
     "ecosystems": [{"ecosystem": "npm", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []},
    {"name": "webmcp-react", "default_branch": "main",
     "ecosystems": [{"ecosystem": "npm", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []},
    {"name": "webmcp-gallery", "default_branch": "main",
     "ecosystems": [{"ecosystem": "npm", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []},
    {"name": "mcpcat-go-sdk", "default_branch": "main",
     "ecosystems": [{"ecosystem": "gomod", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []},
    {"name": "reddit-monitor", "default_branch": "main",
     "ecosystems": [{"ecosystem": "pip", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []},
    {"name": "lemlist-attio-sync", "default_branch": "main",
     "ecosystems": [{"ecosystem": "pip", "directory": "/"}, {"ecosystem": "github-actions", "directory": "/"}],
     "required_checks": []}
  ]
}
```

Fill each `required_checks` array with the check names observed in Step 1 (empty array only if a repo truly reports none — then flag it to the user, since it was scoped in *because* it has CI).

- [ ] **Step 3: Write `scripts/generate-configs.sh`**

```bash
#!/usr/bin/env bash
# Generates build/<repo>/dependabot.yml and build/<repo>/dependabot-auto-merge.yml
# for every repo in scripts/repos.json. Idempotent; overwrites build/.
set -euo pipefail
cd "$(dirname "$0")/.."

jq -c '.repos[]' scripts/repos.json | while read -r repo; do
  name=$(jq -r .name <<<"$repo")
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
done
```

- [ ] **Step 4: Run the generator and validate every output file parses**

```bash
chmod +x scripts/generate-configs.sh
./scripts/generate-configs.sh
for f in build/*/*.yml; do ruby -ryaml -e 'YAML.load_file(ARGV[0])' "$f" || echo "INVALID: $f"; done
actionlint build/*/dependabot-auto-merge.yml || true   # caller has no repo context; expect only "workflow_call target not found"-class notes, no syntax errors
cat build/agentcat-ui/dependabot.yml
```

Expected: 11 `generated:` lines, no `INVALID:` lines, and the printed sample shows npm + github-actions entries with cooldown and both groups.

- [ ] **Step 5: Commit**

```bash
echo "build/" >> .gitignore
git add scripts/repos.json scripts/generate-configs.sh .gitignore
git commit -m "feat: repo inventory and Dependabot config generator"
```

---

### Task 4: Repo settings script (auto-merge, labels, protection, CODEOWNERS audit)

**Files:**
- Create: `scripts/configure-repo-settings.sh`

**Interfaces:**
- Consumes: `scripts/repos.json` (`name`, `default_branch`, `required_checks`).
- Produces: per-repo settings applied via API. Run with `--dry-run` to print without applying. Task 7 executes it for real.

- [ ] **Step 1: Write `scripts/configure-repo-settings.sh`**

```bash
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

run() { if [ "$DRY" = "--dry-run" ]; then echo "DRY: $*"; else "$@"; fi; }

jq -c '.repos[]' scripts/repos.json | while read -r repo; do
  name=$(jq -r .name <<<"$repo")
  branch=$(jq -r .default_branch <<<"$repo")
  checks=$(jq -c '.required_checks' <<<"$repo")
  echo "=== $name ==="

  run gh api -X PATCH "repos/agentcathq/$name" -F allow_auto_merge=true --silent

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
    echo "WARN: $name has no required_checks - auto-merge would be ungated. Fix repos.json first."
  fi

  for path in CODEOWNERS .github/CODEOWNERS docs/CODEOWNERS; do
    content=$(gh api "repos/agentcathq/$name/contents/$path" --jq .content 2>/dev/null | base64 -d 2>/dev/null) || continue
    hits=$(grep -nE 'package\.json|package-lock|go\.(mod|sum)|requirements|pyproject|poetry\.lock|uv\.lock|\*' <<<"$content" || true)
    [ -n "$hits" ] && printf 'WARN: %s %s may gate manifests (bot approval cannot satisfy code-owner review):\n%s\n' "$name" "$path" "$hits"
  done
done
```

Note: `strict: false` (branches need not be up to date) — grouped weekly PRs would otherwise queue rebases; Dependabot rebases on demand anyway.

- [ ] **Step 2: Dry-run against the full inventory**

```bash
chmod +x scripts/configure-repo-settings.sh
./scripts/configure-repo-settings.sh --dry-run
```

Expected: per-repo `DRY:` lines for PATCH/labels/protection, zero `WARN:` lines (investigate any WARN before Task 7; a `*`-owner CODEOWNERS hit needs a human decision on scoping).

- [ ] **Step 3: Commit**

```bash
git add scripts/configure-repo-settings.sh
git commit -m "feat: repo settings script for Dependabot rollout"
```

---

### Task 5: Org-settings runbook + org ruleset

**Files:**
- Create: `docs/runbooks/org-security-settings.md`
- Create: `scripts/org-ruleset.json`

**Interfaces:**
- Produces: the runbook the user executes for all **[HUMAN]** org steps; `scripts/org-ruleset.json` consumed by the runbook's ruleset command.

- [ ] **Step 1: Write `scripts/org-ruleset.json`**

```json
{
  "name": "default-branch-pr-required",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []},
    "repository_name": {
      "include": ["agentcat-ui", "agentcat-server", "agentcat-mcp", "agentcat-go-sdk",
                  "agentcat-python-sdk", "agentcat-typescript-sdk", "webmcp-react",
                  "webmcp-gallery", "mcpcat-go-sdk", "reddit-monitor", "lemlist-attio-sync"],
      "exclude": []
    }
  },
  "rules": [
    {"type": "pull_request",
     "parameters": {"required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": false,
                    "require_code_owner_review": false,
                    "require_last_push_approval": false,
                    "required_review_thread_resolution": false}},
    {"type": "non_fast_forward"},
    {"type": "deletion"}
  ]
}
```

Note: `required_approving_review_count: 0` — the ruleset requires *a PR*, not an approval; the auto-merge workflow's bot approval covers Vanta's per-PR approval test, and human PRs keep normal review culture. Required status checks are per-repo (Task 4) because check names differ.

- [ ] **Step 2: Write `docs/runbooks/org-security-settings.md`**

```markdown
# Org security settings runbook — Dependabot SOC 2 rollout

Execute top to bottom. Steps marked [HUMAN] need org-owner/billing/Vanta/Slack access.
CLI steps assume `gh auth status` shows an org-owner login.

## 1. [HUMAN] Buy GitHub Code Security
Org Settings → Billing and licensing → Licensing → GitHub Advanced Security →
enable **Code Security** (metered, $30/active-committer/month). No repo assignment yet.

## 2. [HUMAN] Org security configuration
Org Settings → Advanced Security → Configurations → New configuration:
- Name: `agentcat-default`
- Dependency graph: Enabled; Dependabot alerts: Enabled;
  Dependabot security updates: Enabled (grouped); Code Security features: Include
- Policy: apply to the 11 in-scope repos (select by name), and set
  "Automatically apply to newly created repositories: All repositories".
The 7 excluded repos (skills, mcp-event-tracker, mcp-audit, mcpcat-go-api,
agentcat-go-api, .github, mcpcat) get NO configuration — they are documented
as out-of-scope in the vulnerability management policy.

## 3. [HUMAN] Enforced auto-triage rules
Org Settings → Advanced Security → Global settings → Dependabot →
Auto-triage rules → enable the GitHub preset "Dismiss low impact issues" →
set to **Enforced**. Create no custom rules; nothing may auto-dismiss
critical/high or production-scope alerts.

## 4. Security-manager team
    gh api orgs/agentcathq/teams/security --silent 2>/dev/null || \
      gh api -X POST orgs/agentcathq/teams -f name=security -f privacy=closed
    gh api -X PUT orgs/agentcathq/security-managers/teams/security
[HUMAN] Add the people responsible for triage to the `security` team.

## 5. Org ruleset (require PR, block force pushes, 11 repos)
    gh api -X POST orgs/agentcathq/rulesets --input scripts/org-ruleset.json

## 6. [HUMAN] Delegated alert dismissal (optional hardening, Code Security)
Org Settings → Advanced Security → Global settings → Dependabot →
enable "Delegated alert dismissal" so dismissals require a reviewer.
Skip if the team is too small for two-person dismissal today; revisit at audit prep.

## 7. [HUMAN] Secrets for the alert router (on agentcathq/.github)
- Fine-grained PAT: Settings → Developer settings → PATs → New:
  Resource owner agentcathq, Organization permissions → "Dependabot alerts: Read-only",
  no repo permissions, 366-day expiry. Add as Actions secret
  `DEPENDABOT_ALERTS_READ_TOKEN` on agentcathq/.github.
- Slack: create an Incoming Webhook for the security channel; add as Actions
  secret `SECURITY_SLACK_WEBHOOK_URL` on agentcathq/.github.
  Set a calendar reminder for PAT rotation.

## 8. [HUMAN] Vanta
- Vulnerability SLAs: Critical 3 / High 14 / Medium 60 / Low 90 days.
- Confirm the GitHub integration lists all 11 in-scope repos and is ingesting
  Dependabot alerts (Vanta → Integrations → GitHub → resources).
- Upload the two policy documents from docs/policies/ (see Task 6).
```

- [ ] **Step 3: Validate the ruleset JSON parses and matches the API schema shape**

```bash
jq . scripts/org-ruleset.json >/dev/null && echo OK
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add docs/runbooks/org-security-settings.md scripts/org-ruleset.json
git commit -m "docs: org security settings runbook + org ruleset definition"
```

---

### Task 6: Vanta policy documents

**Files:**
- Create: `docs/policies/vulnerability-management-policy.md`
- Create: `docs/policies/change-management-standard-changes.md`

**Interfaces:**
- Produces: the two policy artifacts the runbook's Vanta step uploads. Auditors test adherence to exactly these values — they must match the Global Constraints verbatim.

- [ ] **Step 1: Write `docs/policies/vulnerability-management-policy.md`**

```markdown
# Vulnerability Management Policy

**Owner:** security team (GitHub org security managers) · **Effective:** 2026-08-05 · **Review:** annually

## Scope
All actively maintained agentcathq source repositories: agentcat-ui, agentcat-server,
agentcat-mcp, agentcat-go-sdk, agentcat-python-sdk, agentcat-typescript-sdk,
webmcp-react, webmcp-gallery, mcpcat-go-sdk, reddit-monitor, lemlist-attio-sync,
and all newly created repositories (auto-enrolled via the org security configuration).

**Excluded** (no production code or dependency surface; no CI): skills,
mcp-event-tracker, mcp-audit, mcpcat-go-api, agentcat-go-api, .github, mcpcat (empty).
Exclusions are reviewed at each policy review.

## Detection
GitHub Dependabot (dependency graph + alerts + security updates) is the
vulnerability scanner for third-party dependencies, enabled org-wide via an
enforced organization security configuration. Severity is assigned by the
GitHub Advisory Database (CVSS).

## Remediation SLAs (from first detection)
| Severity | SLA |
|---|---|
| Critical | 3 days |
| High | 14 days |
| Medium | 60 days |
| Low | 90 days |

SLA adherence is tracked continuously in Vanta from the first-detection timestamp.

## Triage & response
- Critical alerts are routed to the security Slack channel within 6 hours of
  detection (scheduled router workflow) and require human remediation; the fixing
  PR is reviewed and merged by a human.
- Patch/minor security updates below critical are remediated automatically by
  Dependabot PRs that auto-merge after all required CI checks pass (see the
  change management standard-changes clause).
- An alert may be dismissed only with a documented dismissal reason and
  explanatory comment in GitHub (retained on the alert timeline). Dismissals
  are the documented risk-acceptance record.
- An SLA miss requires a written remediation plan or risk acceptance recorded
  against the alert before the SLA expires.
```

- [ ] **Step 2: Write `docs/policies/change-management-standard-changes.md`**

```markdown
# Change Management — Pre-authorized Standard Changes

**Owner:** security team · **Effective:** 2026-08-05 · **Review:** annually

The following change class is pre-authorized and requires no per-instance
human approval (SOC 2 CC8.1 standard-change carve-out):

**Automated dependency updates**, when ALL of the following hold:
1. The pull request is authored by GitHub Dependabot (verified by workflow
   identity gating on the PR author).
2. The update is semver-patch or semver-minor. Semver-major updates and
   critical-severity (CVSS >= 9.0) security updates are explicitly excluded
   and require human review.
3. All required CI status checks on the target branch pass. CI is the
   documented testing and approval gate for this change class.
4. The merge is performed via GitHub auto-merge (squash) with the automation's
   approval recorded on the PR.

Evidence per change (retained by GitHub on the PR): Dependabot authorship,
bot approval, passing required checks, auto-merge enablement, merge event.
Any merge outside these conditions is an ordinary change requiring standard
review, and any deviation is treated as an incident for CC8.1 purposes.
```

- [ ] **Step 3: Commit**

```bash
git add docs/policies/
git commit -m "docs: vulnerability management policy + standard-changes clause for Vanta"
```

---

### Task 7: Execute — merge central PR, apply org settings, roll out to 11 repos

**Files:**
- Create: `scripts/open-rollout-prs.sh`

**Interfaces:**
- Consumes: everything above — merged `@main` reusable workflow (Task 1), `build/` outputs (Task 3), settings script (Task 4), executed runbook (Task 5).

- [ ] **Step 1: Open and merge the .github repo PR**

```bash
git push -u origin dependabot-soc2-design
gh pr create --title "Dependabot SOC 2 rollout: central workflows, tooling, runbook, policies" \
  --body "Implements docs/superpowers/specs/2026-08-05-dependabot-soc2-design.md.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

**[HUMAN]** Review and merge this PR. The reusable workflow must be on `main` before any caller lands (callers reference `@main`).

- [ ] **Step 2: [HUMAN] Execute the org runbook**

Work through `docs/runbooks/org-security-settings.md` top to bottom (Code Security purchase, security configuration, auto-triage, security team, org ruleset, secrets, Vanta SLAs, policy uploads). Gate: do not proceed to Step 3 until sections 1–5 and 7 are done.

- [ ] **Step 3: Apply per-repo settings**

```bash
git checkout main && git pull
./scripts/configure-repo-settings.sh --dry-run   # final inspection
./scripts/configure-repo-settings.sh             # apply
```

Expected: no `WARN:` lines. Spot-check one repo: `gh api repos/agentcathq/agentcat-ui --jq .allow_auto_merge` → `true`.

- [ ] **Step 4: Write `scripts/open-rollout-prs.sh`**

```bash
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
```

- [ ] **Step 5: Regenerate configs and open the 11 rollout PRs**

```bash
./scripts/generate-configs.sh
chmod +x scripts/open-rollout-prs.sh
./scripts/open-rollout-prs.sh
gh search prs --owner agentcathq --author "@me" --state open "dependabot rollout"
```

Expected: 11 open PRs (one per repo).

- [ ] **Step 6: [HUMAN] Merge the rollout PRs as CI passes**

Each PR must show its required checks passing before merge (this is the first live test of the branch-protection wiring).

- [ ] **Step 7: Commit the rollout script (in this repo)**

```bash
git checkout -b chore/rollout-script && git add scripts/open-rollout-prs.sh
git commit -m "feat: rollout PR opener script"
git push -u origin chore/rollout-script && gh pr create --fill
```

---

### Task 8: Post-rollout verification

**Files:** none (verification checklist; record results as a comment on the rollout PR in this repo).

- [ ] **Step 1: Verify Dependabot ran and a patch/minor PR auto-merged correctly**

After the first weekly run (or trigger manually: repo → Insights → Dependency graph → Dependabot → "Check for updates"):

```bash
gh pr list --repo agentcathq/agentcat-ui --author "app/dependabot" --state all --limit 10
```

Pick one merged patch/minor PR and verify the evidence chain:

```bash
gh pr view <N> --repo agentcathq/agentcat-ui --json author,reviews,statusCheckRollup,mergedBy,labels
```

Expected: author dependabot, an APPROVED review by github-actions, all checks SUCCESS, merged. This is the CC8.1 evidence chain — one sampled PR must show all of it.

- [ ] **Step 2: Verify a semver-major PR stayed open with its label**

```bash
gh search prs --owner agentcathq --author "app/dependabot" --state open --label major-update
```

Expected: any major PRs are open (not merged) and labeled. If none exist yet, re-check after the first weekly cycle that produces one.

- [ ] **Step 3: Dry-run the Slack router end-to-end**

```bash
gh workflow run critical-alert-router.yml --repo agentcathq/.github -f severity=high
gh run list --repo agentcathq/.github --workflow critical-alert-router.yml --limit 1
```

Expected: run succeeds and (if any open high alerts exist) a Slack message arrives. **[HUMAN]** confirm the Slack message renders with repo, package, CVSS, and age. If zero high alerts exist org-wide, the empty-result path (no Slack post, green run) is itself the pass condition.

- [ ] **Step 4: Verify org auto-triage + Vanta ingestion**

**[HUMAN]** In Vanta: GitHub integration shows all 11 repos; vulnerability SLAs display 3/14/60/90; at least one Dependabot finding (if any alerts exist) appears with a due date. In GitHub org → Security: the auto-triage preset shows Enforced.

- [ ] **Step 5: Record verification results**

Comment the outcomes of Steps 1–4 (commands + outputs) on the merged rollout PR in this repo — the first evidence artifact of the observation window.
