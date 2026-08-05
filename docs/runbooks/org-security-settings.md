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
    ROLE_ID=$(gh api orgs/agentcathq/organization-roles \
      --jq '.roles[] | select(.name=="security_manager") | .id')
    gh api -X PUT "orgs/agentcathq/organization-roles/teams/security/$ROLE_ID"
[HUMAN] Add the people responsible for triage to the `security` team.

## 5. Org ruleset (require PR, block force pushes, 11 repos)
    gh api -X POST orgs/agentcathq/rulesets --input scripts/org-ruleset.json

## 6. [HUMAN] Delegated alert dismissal (optional hardening, Code Security)
Org Settings → Advanced Security → Global settings → Dependabot →
enable "Delegated alert dismissal" so dismissals require a reviewer.
Skip if the team is too small for two-person dismissal today; revisit at audit prep.

## 7. [HUMAN] Secrets for the alert router (on agentcathq/.github)
- Fine-grained PAT: Settings → Developer settings → Personal access tokens →
  Fine-grained tokens → New: Resource owner agentcathq; Repository access:
  All repositories; Repository permissions → "Dependabot alerts: Read-only"
  (Metadata: Read-only is added automatically); no Organization permissions;
  366-day expiry. The token owner must be an org owner or security manager
  (see section 4). Add as Actions secret `DEPENDABOT_ALERTS_READ_TOKEN` on
  agentcathq/.github.
- Slack: create an Incoming Webhook for the security channel; add as Actions
  secret `SECURITY_SLACK_WEBHOOK_URL` on agentcathq/.github.
  Set a calendar reminder for PAT rotation.

## 8. [HUMAN] Vanta
- Vulnerability SLAs: Critical 3 / High 14 / Medium 60 / Low 90 days.
- Confirm the GitHub integration lists all 11 in-scope repos and is ingesting
  Dependabot alerts (Vanta → Integrations → GitHub → resources).
- Upload the two policy documents from docs/policies/ (see Task 6).
