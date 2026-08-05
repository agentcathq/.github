# Org-wide Dependabot with SOC 2 Type II Compliance — Design

**Date:** 2026-08-05
**Org:** agentcathq
**Status:** Approved by user (all four sections), pending implementation plan

## Goal

Roll out Dependabot across the agentcathq organization so that:

- Critical-severity vulnerabilities are flagged for human attention in real time.
- Minor/patch dependency updates (both security and version updates) are auto-merged behind CI.
- The entire configuration satisfies SOC 2 Type II expectations (CC6.8, CC7.1, CC7.2, CC8.1), with Vanta as the compliance platform.

## Decisions log

| Decision | Choice |
|---|---|
| Compliance platform | Vanta (GitHub integration handles SLA tracking + evidence) |
| Critical-alert flagging | Buy GitHub Code Security ($30/active-committer/mo, metered) for enforced org auto-triage rules + security overview; plus Slack routing workflow |
| Update scope | Security updates + scheduled version updates on all active repos |
| Repo scope | 11 active repos with CI; 6 repos excluded (documented in policy) |
| Remediation SLAs | Critical 3d / High 14d / Medium 60d / Low 90d |
| Architecture | Central reusable workflow in `.github` repo + thin per-repo callers |
| Merge method | Squash, via `gh pr merge --auto` (merges only when required checks pass) |

## Repo scope

**In scope (11):** agentcat-ui, agentcat-server, agentcat-mcp, agentcat-go-sdk, agentcat-python-sdk, agentcat-typescript-sdk, webmcp-react, webmcp-gallery, mcpcat-go-sdk, reddit-monitor, lemlist-attio-sync, and any future repo created with the org security configuration as default.

**Excluded (6, documented in the vulnerability management policy):** skills, mcp-event-tracker, mcp-audit, mcpcat-go-api, agentcat-go-api, .github. Rationale: no CI (auto-merge would land untested changes) and little/no dependency surface. `mcpcat` is an empty repo and out of scope entirely. Exclusions must appear in the policy — silent exclusions become audit findings.

## Section 1 — Org-level settings (GitHub UI/API, no files)

1. **Purchase GitHub Code Security** (metered billing, $30/active-committer/month).
2. **Org security configuration:** enable dependency graph, Dependabot alerts, and grouped security updates; apply to the 11 in-scope repos; set as default for new repos.
3. **Enforced org-level auto-triage rules** (Code Security feature): GitHub's "dismiss low impact" preset for low-severity development-scope noise only. No rule may auto-dismiss critical/high or production-scope alerts. Rules set to *enforced* (repo admins cannot opt out) — the stronger Type II control.
4. **Security-manager team:** assign a team the org `security manager` role — documented triage ownership (CC7.2 evidence) without org admin.
5. **Org ruleset** (available on Team plan) on default branches of the 11 repos: require a pull request before merging; block force pushes. Required *status checks* are configured per-repo (CI job names differ across repos).
6. **Vanta configuration:** set SLA windows Critical 3d / High 14d / Medium 60d / Low 90d; verify the GitHub integration ingests all 11 repos' Dependabot data. SLA clock starts at first-detection timestamp.
7. **Policy artifacts (stored in Vanta):**
   - Vulnerability management policy: severity tiers, the SLA windows above, triage ownership (security-manager team), Dependabot as the scanning tool, dismissal process (documented reason + comment required on every dismissal), and the 6-repo exclusion list with rationale.
   - Change management "pre-authorized standard changes" clause: Dependabot PRs limited to semver-patch/semver-minor that pass all required CI checks are pre-authorized to merge automatically; semver-major and critical-severity security PRs require human review (CC8.1 carve-out).

## Section 2 — Central logic in this `.github` repo

### `.github/workflows/dependabot-auto-merge.yml` (reusable, `workflow_call`)

All security-sensitive logic lives here, once:

- **Identity gate:** `github.event.pull_request.user.login == 'dependabot[bot]'` — never `github.actor`, which is spoofable via the "@dependabot recreate" confused-deputy attack on forked content. `dependabot/fetch-metadata` provides secondary verification (outputs populate only for Dependabot-authored, Dependabot-only-commit PRs).
- **Metadata:** `dependabot/fetch-metadata` pinned to a full commit SHA, with `alert-lookup: true` to expose `alert-state`, `ghsa-id`, and `cvss` for security PRs.
- **Auto-merge condition:** update-type is `version-update:semver-patch` or `version-update:semver-minor` AND the PR is not a critical-severity security update (CVSS >= 9.0).
- **On match:** `gh pr review --approve` (github-actions[bot] approval satisfies Vanta's "approved by non-author" test), then `gh pr merge --auto --squash` — merge completes only after all required status checks pass.
- **On no match:** label and leave open for human review — `security-critical` for critical security PRs, `major-update` for semver-major.
- **Trigger:** callers use `pull_request` only. Never `pull_request_target`.
- **Permissions:** `contents: write`, `pull-requests: write` (Dependabot-triggered runs get a read-only GITHUB_TOKEN by default; this elevates it).

### `.github/workflows/critical-alert-router.yml` (scheduled)

- Runs every 6 hours (adequate headroom inside the 3-day critical SLA).
- Polls `GET /orgs/agentcathq/dependabot/alerts?severity=critical&state=open`.
- Posts each open critical alert to Slack with its age against the 3-day SLA and a link to the alert.
- Fails loudly: a workflow-failure notification also goes to Slack, so a broken router cannot fail silently for weeks.
- Secrets (Actions secrets on this repo; the router is schedule-triggered, so the Dependabot-secrets caveat does not apply): a read-only fine-grained PAT with org Dependabot-alerts read scope, and a Slack incoming-webhook URL.

## Section 3 — Per-repo rollout (11 repos)

Each in-scope repo receives one PR adding two files:

### `.github/dependabot.yml`

- **Ecosystems:** per language — `npm` (TypeScript repos), `pip` or `uv` (Python repos; pick the key matching each repo's actual package manager during implementation), `gomod` (Go repos) — plus `github-actions` in every repo so action pins stay current.
- **Schedule:** weekly.
- **Cooldown:** `default-days: 7`, `semver-major-days: 30`. Cooldown applies only to version updates — security PRs arrive immediately, which is the intended split (security fast, freshness lazy).
- **Grouping:** one minor+patch group per ecosystem so version noise arrives as a single weekly PR; majors ungrouped (individual review). Security updates grouped via `applies-to: security-updates`.
- No `reviewers` field (removed by GitHub Aug 2025); no `target-branch` (would silently detach security-PR features).

### Caller workflow (~10 lines)

`.github/workflows/dependabot-auto-merge.yml` triggering on `pull_request`, calling `agentcathq/.github/.github/workflows/dependabot-auto-merge.yml@main`. Referencing `@main` is deliberate: fixes to the central logic propagate instantly, and `main` of the `.github` repo is protected by the org ruleset.

### Scripted repo settings (API)

- Enable **Allow auto-merge** on each repo.
- Register each repo's existing CI jobs as **required status checks** on the default branch.
- Verify no CODEOWNERS rule covers dependency manifests (package.json, go.mod/go.sum, requirements/pyproject/lock files) — code-owner-gated manifests make bot approvals insufficient and stall auto-merge silently.

## Section 4 — Hardening, failure modes, verification

**Hardening**

- Third-party actions pinned to full commit SHAs (Dependabot-triggered runs bypass the org Actions allowlist).
- `pull_request` trigger only; no `pull_request_target` anywhere in the auto-merge path.
- Identity gating per Section 2; no interpolation of PR-controlled strings (e.g. head ref) into shell commands.
- Auto-merge uses the workflow GITHUB_TOKEN; no long-lived PATs in the merge path. (Known limitation: GITHUB_TOKEN cannot enqueue into a merge queue — acceptable, no merge queues in use.)

**Failure modes**

- CI fails on an auto-merge candidate → PR stays open; Vanta SLA aging is the backstop for unnoticed security PRs.
- Merge conflicts → Dependabot rebases its own PRs automatically.
- Router workflow failure → Slack failure notification (no silent gaps in the Type II observation window).
- A repo added without the caller workflow → security updates still open PRs (org config), they just require manual merge; Vanta still tracks them.

**Verification (post-rollout)**

1. A patch-level Dependabot PR auto-approves and auto-merges only after CI passes.
2. A semver-major PR stays open with the `major-update` label.
3. A critical security PR (when one occurs, or simulated via a test repo with a known-vulnerable pin) stays open with `security-critical` and appears in Slack within 6 hours.
4. Slack router dry-run: temporarily widen the severity filter to confirm end-to-end delivery, then restore.
5. Vanta shows Dependabot findings from all 11 repos and applies the 3/14/60/90 SLAs.
6. Sample one auto-merged PR's timeline and confirm the full evidence chain: Dependabot author → bot approval → passing required checks → auto-merge event.

## Evidence model (Type II observation window)

- Vanta continuously ingests alerts, PR approvals, and SLA adherence — primary evidence stream.
- GitHub retains per-PR timelines (author, approval, checks, merge) and per-alert timelines (detection → closure, dismissal reason + comment) — sampled by auditors.
- Branch protection / ruleset settings exportable as configuration evidence.
- Every manual dismissal requires a documented reason + comment; auto-triage dismissals are labeled `resolution:auto-dismiss` and auto-reopen if alert scope changes.

## Key sources

- [GitHub: Automating Dependabot with GitHub Actions](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/automating-dependabot-with-github-actions)
- [GitHub: About Dependabot auto-triage rules](https://docs.github.com/en/code-security/dependabot/dependabot-auto-triage-rules/about-dependabot-auto-triage-rules)
- [GitHub changelog: Secret Protection & Code Security products](https://github.blog/changelog/2025-03-04-introducing-github-secret-protection-and-github-code-security/)
- [GitHub changelog: Org rulesets on Team plans](https://github.blog/changelog/2025-06-16-organization-rulesets-now-available-for-github-team-plans/)
- [dependabot/fetch-metadata](https://github.com/dependabot/fetch-metadata)
- [BoostSecurity: Weaponizing Dependabot (confused-deputy attack)](https://labs.boostsecurity.io/articles/weaponizing-dependabot-pwn-request-at-its-finest)
- [GitHub Security Lab: Preventing pwn requests](https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/)
- [Vanta: GitHub integration guide](https://help.vanta.com/en/articles/14845240-github-integration-guide)
- [Vanta: How Vanta calculates vulnerability SLAs](https://help.vanta.com/en/articles/11951321-how-vanta-calculates-vulnerability-slas)
- [Iurii Okhmat: Dependabot in 2026 — configuration deep dive](https://www.iuriio.com/blog/posts/2026/05/dependabot-recent-updates)
