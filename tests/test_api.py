import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.events import Candidate
from app.store import Store


@unittest.skipUnless(importlib.util.find_spec('httpx'), 'Install requirements-dev.txt for HTTP tests')
class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from app.main import app
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'api.sqlite3')
        worker = MagicMock()
        worker.status.return_value = {'id':'test', 'name':'Test', 'status':'offline'}
        worker.frame.return_value = None
        cfg = {'retention_days':7, 'cameras':[{'id':'test', 'name':'Test'}]}
        self.patches = [patch('app.main.load_config', return_value=cfg),
                        patch('app.main.Store', return_value=self.store),
                        patch('app.main.CameraWorker', return_value=worker),
                        patch.dict(os.environ, {'MONITOR_USERNAME':'admin', 'MONITOR_PASSWORD':'test-only-password-123'})]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)
        self.client.__enter__()
        self.auth = ('admin', 'test-only-password-123')

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_all_sensitive_endpoints_require_auth(self):
        for url in ['/', '/assets/app.js', '/api/cameras', '/api/events', '/api/export.csv', '/api/cameras/test/stream']:
            self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get('/api/events', auth=('admin','wrong')).status_code, 401)

    def test_dashboard_and_status(self):
        response = self.client.get('/', auth=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertIn('CCTV Phone Monitor', response.text)
        self.assertEqual(self.client.get('/assets/app.js', auth=self.auth).status_code, 200)
        data = self.client.get('/api/cameras', auth=self.auth).json()
        self.assertEqual(data[0]['status'], 'offline')
        self.assertNotIn('source', data[0])

    def test_event_review_validation(self):
        event_id = self.store.start('test', 1, Candidate(0,10,'A'))
        response = self.client.patch(f'/api/events/{event_id}/review', auth=self.auth,
                                     json={'value':'false_positive'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/events', auth=self.auth).json()[0]['review'], 'false_positive')
        self.assertEqual(self.client.patch(f'/api/events/{event_id}/review', auth=self.auth,
                                          json={'value':'not_working'}).status_code, 422)
        self.assertEqual(self.client.patch('/api/events/999/review', auth=self.auth,
                                          json={'value':'uncertain'}).status_code, 404)

    def test_export_and_bad_parameters(self):
        self.store.start('test', 1, Candidate(0,10,'=malicious'))
        response = self.client.get('/api/export.csv', auth=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=malicious", response.text)
        self.assertEqual(self.client.get('/api/events?limit=0', auth=self.auth).status_code, 422)
        self.assertEqual(self.client.get('/api/cameras/unknown/stream', auth=self.auth).status_code, 404)
        self.assertEqual(self.client.get('/api/snapshots/bad.jpg', auth=self.auth).status_code, 404)


if __name__ == '__main__':
    unittest.main()
