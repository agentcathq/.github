import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from typing import Any

import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/critical-alert-router.yml'
STEPS = yaml.safe_load(WORKFLOW.read_text())['jobs']['route']['steps']


def alert(name: str, fork: bool | None, severity: str = 'high') -> dict[str, Any]:
    repository: dict[str, Any] = {'full_name': f'example/{name}'}
    if fork is not None:
        repository['fork'] = fork
    return {
        'repository': repository,
        'dependency': {'package': {'name': 'test-package'}},
        'security_advisory': {'severity': severity, 'cvss': {'score': 7.5}},
        'created_at': '2026-09-18T00:00:00Z',
        'html_url': f'https://github.com/example/{name}/security/dependabot/1',
    }


class AlertRouterTest(unittest.TestCase):
    def route(self, pages: list[list[dict[str, Any]]]) -> tuple[list[Any], str, str | None]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'pages.json').write_text('\n'.join(json.dumps(page) for page in pages))
            for name, script in {
                'gh': '#!/bin/sh\ncat pages.json\n',
                'curl': '#!/bin/sh\ncp payload.json posted.json\n',
            }.items():
                executable = root / name
                executable.write_text(script)
                executable.chmod(0o755)
            env = {
                **os.environ,
                'PATH': f'{root}{os.pathsep}{os.environ["PATH"]}',
                'GITHUB_OUTPUT': str(root / 'output'),
                'SEVERITY': 'critical,high',
                'SLACK_WEBHOOK_URL': 'https://example.invalid/webhook',
            }
            subprocess.run(['bash', '-eo', 'pipefail', '-c', STEPS[0]['run']],
                           cwd=root, env=env, check=True, capture_output=True)
            count = (root / 'output').read_text().strip()
            self.assertEqual(STEPS[1]['if'], "steps.fetch.outputs.count != '0'")
            if count != 'count=0':
                subprocess.run(['bash', '-eo', 'pipefail', '-c', STEPS[1]['run']],
                               cwd=root, env=env, check=True, capture_output=True)
            posted = root / 'posted.json'
            text = json.loads(posted.read_text())['text'] if posted.exists() else None
            return json.loads((root / 'alerts.json').read_text()), count, text

    def test_mixed_pages_exclude_forks_before_count_and_post(self) -> None:
        kept = [alert('service', False), alert('another-service', False, 'critical')]
        result, count, text = self.route([
            [alert('upstream-copy', True), kept[0]],
            [kept[1], alert('another-copy', True, 'critical')],
        ])
        self.assertEqual(result, kept)
        self.assertEqual(count, 'count=2')
        assert text is not None
        self.assertIn('*2 open Dependabot alert(s)*', text)
        self.assertNotIn('upstream-copy', text)
        self.assertNotIn('another-copy', text)
        self.assertIn('example/service: test-package', text)
        self.assertIn('high (CVSS 7.5)', text)
        self.assertIn(' — SLA 7d', text)
        self.assertIn(' — SLA 3d', text)
        self.assertLess(text.index('critical (CVSS'), text.index('high (CVSS'))

    def test_only_forks_do_not_post(self) -> None:
        self.assertEqual(self.route([[alert('copy', True)]]), ([], 'count=0', None))

    def test_empty_page_does_not_post(self) -> None:
        self.assertEqual(self.route([[]]), ([], 'count=0', None))

    def test_no_pages_do_not_post(self) -> None:
        self.assertEqual(self.route([]), ([], 'count=0', None))

    def test_non_forks_unchanged(self) -> None:
        alerts = [alert('service', False), alert('another-service', False)]
        result, count, text = self.route([alerts])
        self.assertEqual(result, alerts)
        self.assertEqual(count, 'count=2')
        assert text is not None
        self.assertIn('example/service: test-package', text)
        self.assertIn('example/another-service: test-package', text)

    def test_missing_fork_metadata_does_not_hide_alert(self) -> None:
        alerts = [alert('service', None)]
        result, count, text = self.route([alerts])
        self.assertEqual(result, alerts)
        self.assertEqual(count, 'count=1')
        self.assertIsNotNone(text)


if __name__ == '__main__':
    unittest.main()
