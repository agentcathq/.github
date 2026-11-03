"""Post new SDK compatibility-test failures to Slack (#oncall-alerts).

Each run reads the newest completed main-branch run of every watched workflow.
A failed run that finished inside this router's window gets one Slack
message: the failed jobs (their names hold the MCP SDK version), a link to the
run, and how long the workflow has been red. MeowBot reads that message and
opens a fix pull request.

The window starts where the previous successful router run started, so a
failed router run never drops an alert. A failure that stays red posts again on
each new failed run, with a longer "failing for".

Python standard library only: the workflow runs it with no install step.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

ORG = 'agentcathq'

# (repo, workflow file). Each file runs the SDK against the MCP SDK releases it
# supports. A matrix job name holds the version, for example
# `test-with-fastmcp (1.31.0)` or `rmcp-canary (3.8.0)`.
WATCHED: list[tuple[str, str]] = [
    ('agentcat-csharp-sdk', 'ci.yml'),
    ('agentcat-go-sdk', 'go-sdk-compatibility.yml'),
    ('agentcat-go-sdk', 'go-sdk-prerelease.yml'),
    ('agentcat-go-sdk', 'mcp-go-compatibility.yml'),
    ('agentcat-go-sdk', 'mcp-go-prerelease.yml'),
    ('agentcat-java-sdk', 'ci.yml'),
    ('agentcat-php-sdk', 'nightly.yml'),
    ('agentcat-python-sdk', 'mcp-compatibility.yml'),
    ('agentcat-python-sdk', 'mcp-prerelease-compatibility.yml'),
    ('agentcat-ruby-sdk', 'mcp-compat.yml'),
    ('agentcat-rust-sdk', 'nightly.yml'),
    ('agentcat-typescript-sdk', 'mcp-compatibility.yml'),
]

FAILED = {'failure', 'timed_out', 'startup_failure'}
# A cancelled or skipped run says nothing about compatibility: skip it in the
# streak instead of letting it end or start one.
IGNORED = {'cancelled', 'skipped', 'neutral', 'stale', 'action_required'}
MAX_JOBS_LISTED = 15
# With no earlier successful router run, look back this far.
DEFAULT_LOOKBACK = timedelta(hours=2)
# After a long router outage, do not flood the channel with stale failures.
MAX_LOOKBACK = timedelta(hours=26)

Api = Callable[[str], Any]


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def github_api(token: str) -> Api:
    def get(path: str) -> Any:
        url = path if path.startswith('https://') else f'https://api.github.com{path}'
        request = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'agentcat-compat-alert-router',
        })
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    return get


def window_start(api: Api, router_repo: str, router_workflow: str, this_run_id: str | None,
                 this_start: datetime) -> datetime:
    """Where the previous successful router run started (bounded by MAX_LOOKBACK)."""
    data = api(f'/repos/{router_repo}/actions/workflows/{router_workflow}/runs'
               '?status=success&per_page=5&exclude_pull_requests=true')
    for run in data.get('workflow_runs', []):
        if str(run['id']) == str(this_run_id):
            continue
        started = parse_time(run.get('run_started_at') or run['created_at'])
        if started < this_start:
            return max(started, this_start - MAX_LOOKBACK)
    return this_start - DEFAULT_LOOKBACK


def main_runs(api: Api, repo: str, workflow: str) -> list[dict[str, Any]]:
    """Completed runs on main, newest first, without pull-request or ignored runs."""
    query = urllib.parse.urlencode({
        'branch': 'main', 'status': 'completed', 'per_page': 100, 'exclude_pull_requests': 'true',
    })
    data = api(f'/repos/{ORG}/{repo}/actions/workflows/{workflow}/runs?{query}')
    runs = [
        run for run in data.get('workflow_runs', [])
        if run.get('event') != 'pull_request' and run.get('conclusion') not in IGNORED
    ]
    return sorted(runs, key=lambda run: run['created_at'], reverse=True)


def failed_jobs(api: Api, repo: str, run_id: int) -> list[str]:
    names: list[str] = []
    page = 1
    while True:
        data = api(f'/repos/{ORG}/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100&page={page}')
        jobs = data.get('jobs', [])
        names.extend(job['name'] for job in jobs if job.get('conclusion') in FAILED)
        if len(jobs) < 100:
            return names
        page += 1


def duration(delta: timedelta) -> str:
    minutes = max(int(delta.total_seconds() // 60), 0)
    days, rest = divmod(minutes, 24 * 60)
    hours, minutes = divmod(rest, 60)
    def unit(n: int, word: str) -> str:
        return f'{n} {word}' if n == 1 else f'{n} {word}s'
    if days:
        return unit(days, 'day') + (f' {unit(hours, "hour")}' if hours else '')
    if hours:
        return unit(hours, 'hour')
    return unit(minutes, 'minute')


def stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')


def streak(runs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """The newest run of consecutive failures, and the last green run before it."""
    failing: list[dict[str, Any]] = []
    for run in runs:
        if run.get('conclusion') in FAILED:
            failing.append(run)
            continue
        return failing, run if run.get('conclusion') == 'success' else None
    return failing, None


def alert_message(repo: str, runs: list[dict[str, Any]], jobs: list[str], now: datetime) -> str:
    failing, green = streak(runs)
    latest = failing[0]
    first = failing[-1]
    name = latest.get('name') or latest.get('path', '')
    started = parse_time(first['created_at'])
    lines = [f'🧪 *SDK compatibility failure* · `{repo}` · {name}']
    if jobs:
        shown = ', '.join(f'`{job}`' for job in jobs[:MAX_JOBS_LISTED])
        more = len(jobs) - MAX_JOBS_LISTED
        lines.append(f'*Failed jobs:* {shown}'
                     + (f' and {more} more' if more > 0 else ''))
    else:
        lines.append('*Failed jobs:* none reported. The run failed before or outside its jobs.')
    lines.append(
        f'*Run:* <{latest["html_url"]}|{name} #{latest.get("run_number", latest["id"])}> '
        f'({latest.get("event", "unknown")} on main, {stamp(parse_time(latest["created_at"]))}, '
        f'commit `{str(latest.get("head_sha", ""))[:7]}`)'
    )
    count = len(failing)
    runs_text = '1 failed run' if count == 1 else f'{count} failed runs in a row'
    if green is not None:
        lines.append(
            f'*Failing for:* {duration(now - started)} ({runs_text} since {stamp(started)}). '
            f'Last green: <{green["html_url"]}|#{green.get("run_number", green["id"])}>, '
            f'{stamp(parse_time(green["created_at"]))}.'
        )
    else:
        lines.append(
            f'*Failing for:* at least {duration(now - started)} ({runs_text} since {stamp(started)}). '
            'No green run in the run history that GitHub returned.'
        )
    return '\n'.join(lines)


def collect(api: Api, since: datetime, until: datetime, now: datetime,
            watched: list[tuple[str, str]] = WATCHED) -> list[str]:
    """One Slack message per watched workflow whose newest main run failed inside [since, until)."""
    messages: list[str] = []
    for repo, workflow in watched:
        runs = main_runs(api, repo, workflow)
        if not runs or runs[0].get('conclusion') not in FAILED:
            continue
        finished = parse_time(runs[0].get('updated_at') or runs[0]['created_at'])
        if not since <= finished < until:
            continue
        jobs = failed_jobs(api, repo, runs[0]['id'])
        messages.append(alert_message(repo, runs, jobs, now))
    return messages


def post(webhook: str, text: str) -> None:
    body = json.dumps({'text': text}).encode()
    request = urllib.request.Request(webhook, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def run() -> int:
    api = github_api(os.environ['GH_TOKEN'])
    now = datetime.now(UTC)
    router_repo = os.environ.get('GITHUB_REPOSITORY', f'{ORG}/.github')
    run_id = os.environ.get('GITHUB_RUN_ID')
    this_start = now
    if run_id:
        this_run = api(f'/repos/{router_repo}/actions/runs/{run_id}')
        this_start = parse_time(this_run.get('run_started_at') or this_run['created_at'])
    if os.environ.get('LOOKBACK_HOURS'):
        since = this_start - timedelta(hours=float(os.environ['LOOKBACK_HOURS']))
    else:
        since = window_start(api, router_repo, 'compat-alert-router.yml', run_id, this_start)
    print(f'Window: {stamp(since)} to {stamp(this_start)}')
    messages = collect(api, since, this_start, now)
    print(f'{len(messages)} new failure(s)')
    dry_run = os.environ.get('DRY_RUN') == 'true'
    for text in messages:
        print(text, end='\n\n')
        if not dry_run:
            post(os.environ['SLACK_WEBHOOK_URL'], text)
    return 0


if __name__ == '__main__':
    sys.exit(run())
