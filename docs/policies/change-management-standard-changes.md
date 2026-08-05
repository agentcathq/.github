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
