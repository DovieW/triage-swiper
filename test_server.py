"""Check persistence, conflict handling and export on temporary data."""
from pathlib import Path
import json
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
from server import make_handler, ROOT


class PickerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'state.sqlite3'
        self.source = ROOT / 'catalog.example.json'
        self.start()
        self.vid = self.request('/api/talks')[1]['videos'][0]['id']

    def start(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.source, self.db, getattr(self, 'extra', None)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def tearDown(self):
        self.stop()
        self.temp.cleanup()

    def request(self, path, data=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        req = Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            res = urlopen(req)
        except HTTPError as e:
            res = e
        body = res.read().decode()
        return res.status, json.loads(body) if 'application/json' in res.headers.get('Content-Type', '') else body

    def choose(self, status, revision):
        return self.request('/api/decision', {'id': self.vid, 'status': status, 'revision': revision})

    def test_dataset(self):
        videos = self.request('/api/talks')[1]['videos']
        self.assertEqual(len({v['id'] for v in videos}), 3)
        self.assertEqual(len({v['channel'] for v in videos}), 1)

    def test_shared_persistence_and_export(self):
        self.assertEqual(self.choose('keep', 0)[0], 200)
        self.stop()
        self.start()
        self.assertEqual(self.request('/api/decisions')[1][self.vid]['status'], 'keep')
        self.assertEqual(self.request('/api/export.json')[1]['video_count'], 1)
        self.assertIn(self.vid, self.request('/api/export.txt')[1])

    def test_conflict_and_undo(self):
        self.assertEqual(self.choose('keep', 0)[0], 200)
        self.assertEqual(self.choose('pass', 0)[0], 409)
        self.assertEqual(self.request('/api/decisions')[1][self.vid]['status'], 'keep')
        self.assertEqual(self.choose('pending', 1)[0], 200)
        self.assertEqual(self.request('/api/export.json')[1]['video_count'], 0)

    def test_expanded_catalog_keeps_originals_and_exports_unknown_runtimes(self):
        original = self.request('/api/talks')[1]['videos'][0]
        extra = dict(original, id='newvideo001', duration_seconds=None, published_date=None)
        self.extra = Path(self.temp.name) / 'extra.json'
        self.extra.write_text(json.dumps({'videos': [extra, dict(original, title='Must not replace original')]}))
        self.stop()
        self.start()
        videos = self.request('/api/talks')[1]['videos']
        self.assertEqual(len(videos), 4)
        self.assertEqual(videos[0]['title'], original['title'])
        self.vid = extra['id']
        self.assertEqual(self.choose('keep', 0)[0], 200)
        exported = self.request('/api/export.json')[1]
        self.assertEqual(exported['unknown_duration_count'], 1)
        self.assertEqual(exported['duration_seconds'], 0)
        self.assertIsNone(exported['videos'][0]['duration_seconds'])

    def test_three_maybe_levels_persist_and_can_be_reclassified(self):
        for revision, status in enumerate(('maybe1', 'maybe2', 'maybe3')):
            response, state = self.choose(status, revision)
            self.assertEqual(response, 200)
            self.assertEqual(state['status'], status)
        self.stop()
        self.start()
        self.assertEqual(self.request('/api/decisions')[1][self.vid]['status'], 'maybe3')
        self.assertEqual(self.request('/api/export.json')[1]['video_count'], 0)
        self.assertEqual(self.choose('keep', 3)[0], 200)
        self.assertEqual(self.request('/api/export.json')[1]['video_count'], 1)

    def test_legacy_later_migrates_once_without_changing_keep_or_pass(self):
        ids = [v['id'] for v in self.request('/api/talks')[1]['videos'][:3]]
        with sqlite3.connect(self.db) as db:
            db.executemany('INSERT INTO decisions VALUES (?,?,?)', [(ids[0], 'later', 4), (ids[1], 'keep', 2), (ids[2], 'pass', 3)])
        self.stop()
        self.start()
        expected = {ids[0]: {'status': 'maybe2', 'revision': 5}, ids[1]: {'status': 'keep', 'revision': 2}, ids[2]: {'status': 'pass', 'revision': 3}}
        self.assertEqual(self.request('/api/decisions')[1], expected)
        self.stop()
        self.start()
        self.assertEqual(self.request('/api/decisions')[1], expected)
        self.assertEqual(self.choose('maybe1', 4)[0], 409)
        self.assertEqual(self.choose('later', 5)[1]['status'], 'maybe2')

    def test_tag_names_persist_and_choices_keep_their_original_ids(self):
        self.assertEqual(self.choose('maybe1', 0)[0], 200)
        names = {'maybe1': 'Consider', 'maybe2': 'Review', 'maybe3': 'Backup'}
        self.assertEqual(self.request('/api/settings')[1]['revision'], 0)
        status, settings = self.request('/api/settings', {'tags': names, 'revision': 0})
        self.assertEqual(status, 200)
        self.assertEqual(settings, {'tags': names, 'revision': 1})
        self.stop()
        self.start()
        self.assertEqual(self.request('/api/settings')[1], settings)
        self.assertEqual(self.request('/api/decisions')[1][self.vid]['status'], 'maybe1')
        self.assertEqual(self.request('/api/settings', {'tags': names, 'revision': 0})[0], 409)

    def test_tag_names_validate_and_reject_cross_origin_writes(self):
        for names in ({'maybe1': 'One'}, {'maybe1': '', 'maybe2': 'Two', 'maybe3': 'Three'}, {'maybe1': 'Same', 'maybe2': 'same', 'maybe3': 'Three'}, {'maybe1': 'X'*33, 'maybe2': 'Two', 'maybe3': 'Three'}):
            self.assertEqual(self.request('/api/settings', {'tags': names, 'revision': 0})[0], 400)
        names = {'maybe1': 'One', 'maybe2': 'Two', 'maybe3': 'Three'}
        self.assertEqual(self.request('/api/settings', {'tags': names, 'revision': 0}, 'https://example.com')[0], 403)

    def test_metadata_is_cached_and_catalog_payload_stays_small(self):
        self.assertEqual(self.request('/api/metadata?id=' + self.vid)[1], {})
        cached = {'description': 'Description '*1000, 'duration_seconds': 321, 'published_date': '2026-01-02'}
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO video_metadata VALUES (?,?,?)', (self.vid, json.dumps(cached), '2026-01-03'))
        self.assertEqual(self.request('/api/metadata?id=' + self.vid)[1], cached)
        video = next(v for v in self.request('/api/talks')[1]['videos'] if v['id'] == self.vid)
        self.assertEqual(video['duration_seconds'], 321)
        self.assertNotIn('description', video)
        self.assertEqual(self.request('/api/metadata?id=unknown')[0], 404)
        self.assertEqual(self.choose('keep', 0)[0], 200)
        self.assertEqual(self.request('/api/export.json')[1]['duration_seconds'], 321)

    def test_validation_and_origin(self):
        self.assertEqual(self.choose('bogus', 0)[0], 400)
        self.assertEqual(self.request('/api/decision', {'id': 'missing', 'status': 'keep', 'revision': 0})[0], 400)
        self.assertEqual(self.request('/api/decision', {'id': self.vid, 'status': 'keep', 'revision': 0}, 'https://example.com')[0], 403)

    def test_only_app_assets_served(self):
        for path in ('/server.py', '/../catalog.json', '/decisions.sqlite3'):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request('/')[0], 200)


if __name__ == '__main__':
    unittest.main()
