import json
import os
import tempfile
from unittest import mock

from django.test import SimpleTestCase

from issues import views
from issues.models import CriticalIssue, Issue, LowPriorityIssue, Reporter, build_issue


class ModelTests(SimpleTestCase):
    def test_reporter_validation(self):
        Reporter(1, 'Asha', 'asha@x.io', 'backend').validate()
        with self.assertRaisesMessage(ValueError, 'Invalid email'):
            Reporter(1, 'Asha', 'no-at-sign', 'backend').validate()
        with self.assertRaisesMessage(ValueError, 'Name cannot be empty'):
            Reporter(1, '', 'a@x.io', 'backend').validate()

    def test_issue_validation(self):
        with self.assertRaisesMessage(ValueError, 'Title cannot be empty'):
            Issue(1, '', 'd', 'open', 'low', 1).validate()
        with self.assertRaises(ValueError):
            Issue(1, 't', 'd', 'wip', 'low', 1).validate()
        with self.assertRaises(ValueError):
            Issue(1, 't', 'd', 'open', 'urgent', 1).validate()

    def test_factory_picks_subclass_and_describe_is_overridden(self):
        base = dict(id=1, title='Bug', description='', status='open', reporter_id=1)
        self.assertIsInstance(build_issue(priority='critical', **base), CriticalIssue)
        self.assertIsInstance(build_issue(priority='low', **base), LowPriorityIssue)
        medium = build_issue(priority='medium', **base)
        self.assertIs(type(medium), Issue)
        self.assertEqual(medium.describe(), 'Bug [medium]')
        self.assertTrue(build_issue(priority='critical', **base).describe().startswith('[URGENT]'))


class ApiTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        issues_path = os.path.join(self.tmp.name, 'issues.json')
        reporters_path = os.path.join(self.tmp.name, 'reporters.json')
        self.patches = [
            mock.patch.object(views, 'ISSUES_FILE', issues_path),
            mock.patch.object(views, 'REPORTERS_FILE', reporters_path),
        ]
        for p in self.patches:
            p.start()
        self.post('/api/reporters/', {'id': 1, 'name': 'Asha Rao',
                                      'email': 'asha@devtrack.io', 'team': 'backend'})

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def post(self, url, body):
        return self.client.post(url, data=json.dumps(body), content_type='application/json')

    def test_sample_request_from_brief(self):
        res = self.post('/api/issues/', {
            'id': 1, 'title': 'Login button not working on mobile',
            'description': 'Users on iOS 17 cannot tap the login button',
            'status': 'open', 'priority': 'critical', 'reporter_id': 1,
        })
        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            res.json()['message'],
            '[URGENT] Login button not working on mobile — needs immediate attention',
        )

    def test_empty_title_returns_400(self):
        res = self.post('/api/issues/', {'title': '', 'status': 'open',
                                         'priority': 'low', 'reporter_id': 1})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {'error': 'Title cannot be empty'})

    def test_unknown_reporter_returns_400(self):
        res = self.post('/api/issues/', {'title': 't', 'status': 'open',
                                         'priority': 'low', 'reporter_id': 99})
        self.assertEqual(res.status_code, 400)

    def test_get_by_id_and_404(self):
        self.post('/api/issues/', {'id': 5, 'title': 't', 'status': 'open',
                                   'priority': 'high', 'reporter_id': 1})
        self.assertEqual(self.client.get('/api/issues/?id=5').json()['id'], 5)
        res = self.client.get('/api/issues/?id=6')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json(), {'error': 'Issue not found'})
        self.assertEqual(self.client.get('/api/reporters/?id=2').status_code, 404)

    def test_filter_by_status(self):
        self.post('/api/issues/', {'title': 'a', 'status': 'open', 'priority': 'low', 'reporter_id': 1})
        self.post('/api/issues/', {'title': 'b', 'status': 'closed', 'priority': 'low', 'reporter_id': 1})
        res = self.client.get('/api/issues/?status=open')
        self.assertEqual([i['title'] for i in res.json()], ['a'])

    def test_list_reporters(self):
        res = self.client.get('/api/reporters/')
        self.assertEqual(len(res.json()), 1)
