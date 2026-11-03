import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import compat_alert_router as router  # noqa: E402

NOW = datetime(2026, 11, 3, 12, 41, tzinfo=UTC)
REPO = 'agentcat-python-sdk'
WORKFLOW = 'mcp-compatibility.yml'


def run(run_id: int, conclusion: str, created: datetime, event: str = 'schedule',
        finished: datetime | None = None) -> dict[str, Any]:
    return {
        'id': run_id, 'run_number': run_id, 'name': 'MCP Version Compatibility Testing',
        'event': event, 'conclusion': conclusion, 'head_sha': f'{run_id:07d}abcdef',
        'created_at': created.isoformat().replace('+00:00', 'Z'),
        'updated_at': (finished or created + timedelta(minutes=20)).isoformat().replace('+00:00', 'Z'),
        'html_url': f'https://github.com/agentcathq/{REPO}/actions/runs/{run_id}',
    }


class FakeApi:
    def __init__(self, runs: list[dict[str, Any]], jobs: list[dict[str, Any]] | None = None,
                 router_runs: list[dict[str, Any]] | None = None) -> None:
        self.runs = runs
        self.jobs = jobs or []
        self.router_runs = router_runs or []
        self.paths: list[str] = []

    def __call__(self, path: str) -> Any:
        self.paths.append(path)
        if '/.github/actions/workflows/' in path:
            return {'workflow_runs': self.router_runs}
        if f'/actions/workflows/{WORKFLOW}/runs' in path:
            return {'workflow_runs': self.runs}
        if '/workflows/' in path:
            return {'workflow_runs': []}
        if '/jobs' in path:
            return {'jobs': self.jobs}
        raise AssertionError(path)


def collect(api: FakeApi, since: datetime = NOW - timedelta(hours=1)) -> list[str]:
    return router.collect(api, since, NOW, NOW, watched=[(REPO, WORKFLOW)])


class CompatAlertRouterTest(unittest.TestCase):
    def test_new_failure_names_versions_run_and_duration(self) -> None:
        api = FakeApi(
            runs=[
                run(5, 'failure', NOW - timedelta(minutes=50)),
                run(4, 'cancelled', NOW - timedelta(hours=10)),
                run(3, 'failure', NOW - timedelta(days=1, hours=1)),
                run(2, 'failure', NOW - timedelta(days=2, hours=3), event='push'),
                run(1, 'success', NOW - timedelta(days=3)),
            ],
            jobs=[
                {'name': 'test-with-fastmcp (1.31.0)', 'conclusion': 'failure'},
                {'name': 'test-with-fastmcp (1.30.0)', 'conclusion': 'success'},
                {'name': 'test-without-fastmcp (1.31.0)', 'conclusion': 'timed_out'},
            ],
        )
        [text] = collect(api)
        self.assertIn('`agentcat-python-sdk` · MCP Version Compatibility Testing', text)
        self.assertIn('`test-with-fastmcp (1.31.0)`, `test-without-fastmcp (1.31.0)`', text)
        self.assertNotIn('1.30.0', text)
        self.assertIn('<https://github.com/agentcathq/agentcat-python-sdk/actions/runs/5|', text)
        self.assertIn('*Failing for:* 2 days 3 hours (3 failed runs in a row since 2026-11-01 09:41 UTC)', text)
        self.assertIn('Last green: <https://github.com/agentcathq/agentcat-python-sdk/actions/runs/1|#1>', text)

    def test_first_failure_says_one_run(self) -> None:
        api = FakeApi(runs=[run(2, 'failure', NOW - timedelta(minutes=30)), run(1, 'success', NOW - timedelta(days=1))])
        [text] = collect(api)
        self.assertIn('*Failing for:* 30 minutes (1 failed run since', text)
        self.assertIn('*Failed jobs:* none reported', text)

    def test_failure_outside_window_is_not_posted_again(self) -> None:
        api = FakeApi(runs=[run(2, 'failure', NOW - timedelta(hours=3)), run(1, 'success', NOW - timedelta(days=1))])
        self.assertEqual(collect(api), [])

    def test_green_latest_run_posts_nothing(self) -> None:
        api = FakeApi(runs=[run(2, 'success', NOW - timedelta(minutes=30)), run(1, 'failure', NOW - timedelta(days=1))])
        self.assertEqual(collect(api), [])

    def test_pull_request_runs_are_ignored(self) -> None:
        api = FakeApi(runs=[
            run(2, 'failure', NOW - timedelta(minutes=30), event='pull_request'),
            run(1, 'success', NOW - timedelta(days=1)),
        ])
        self.assertEqual(collect(api), [])

    def test_no_green_run_in_history(self) -> None:
        api = FakeApi(runs=[run(2, 'failure', NOW - timedelta(minutes=30)), run(1, 'failure', NOW - timedelta(hours=5))])
        [text] = collect(api)
        self.assertIn('at least 5 hours (2 failed runs in a row', text)
        self.assertIn('No green run', text)

    def test_long_job_lists_are_cut(self) -> None:
        jobs = [{'name': f'job ({n}.0.0)', 'conclusion': 'failure'} for n in range(20)]
        api = FakeApi(runs=[run(2, 'failure', NOW - timedelta(minutes=30))], jobs=jobs)
        [text] = collect(api)
        self.assertIn('and 5 more', text)
        self.assertNotIn('job (15.0.0)', text)

    def test_window_starts_at_previous_successful_router_run(self) -> None:
        previous = NOW - timedelta(hours=1, minutes=3)
        api = FakeApi(runs=[], router_runs=[
            {'id': 99, 'run_started_at': NOW.isoformat(), 'created_at': NOW.isoformat()},
            {'id': 98, 'run_started_at': previous.isoformat(), 'created_at': previous.isoformat()},
        ])
        self.assertEqual(
            router.window_start(api, 'agentcathq/.github', 'compat-alert-router.yml', '99', NOW), previous)

    def test_window_is_bounded_after_an_outage(self) -> None:
        old = NOW - timedelta(days=9)
        api = FakeApi(runs=[], router_runs=[{'id': 1, 'run_started_at': old.isoformat(), 'created_at': old.isoformat()}])
        self.assertEqual(
            router.window_start(api, 'agentcathq/.github', 'compat-alert-router.yml', '99', NOW),
            NOW - router.MAX_LOOKBACK)

    def test_first_router_run_uses_default_lookback(self) -> None:
        self.assertEqual(
            router.window_start(FakeApi(runs=[]), 'agentcathq/.github', 'compat-alert-router.yml', '99', NOW),
            NOW - router.DEFAULT_LOOKBACK)

    def test_duration_text(self) -> None:
        self.assertEqual(router.duration(timedelta(days=1)), '1 day')
        self.assertEqual(router.duration(timedelta(hours=1, minutes=59)), '1 hour')
        self.assertEqual(router.duration(timedelta(minutes=1)), '1 minute')

    def test_workflow_runs_router_on_a_schedule_with_read_only_token(self) -> None:
        workflow = yaml.safe_load((ROOT / '.github/workflows/compat-alert-router.yml').read_text())
        self.assertEqual(workflow['permissions'], {'actions': 'read', 'contents': 'read'})
        self.assertIn('schedule', workflow[True])
        step = workflow['jobs']['route']['steps'][-1]
        self.assertEqual(step['run'], 'python scripts/compat_alert_router.py')



if __name__ == '__main__':
    unittest.main()
