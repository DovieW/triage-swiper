import json
import unittest
from unittest.mock import patch, MagicMock
from fetch_metadata import parse_page, fetch_one


class MetadataTest(unittest.TestCase):
    def page(self, video='abcdefghijk', length='123'):
        return '<script>var ytInitialPlayerResponse = ' + json.dumps({'videoDetails': {'videoId': video, 'shortDescription': 'Real description\nWith chapters & links', 'lengthSeconds': length}, 'microformat': {'playerMicroformatRenderer': {'publishDate': '2026-01-02T12:00:00-05:00'}}}) + ';</script>'

    def test_parses_real_description_and_metadata(self):
        self.assertEqual(parse_page(self.page(), 'abcdefghijk'), {'description': 'Real description\nWith chapters & links', 'duration_seconds': 123, 'published_date': '2026-01-02'})

    def test_rejects_missing_or_wrong_video(self):
        for page in ('<html>consent or error</html>', self.page('wrongvideo1')):
            with self.assertRaises(ValueError):
                parse_page(page, 'abcdefghijk')

    def test_one_watch_page_request_and_no_video_download(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = self.page().encode()
        with patch('fetch_metadata.urlopen', return_value=response) as request:
            self.assertEqual(fetch_one('abcdefghijk')['duration_seconds'], 123)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[0].full_url, 'https://www.youtube.com/watch?v=abcdefghijk')

    def test_invalid_video_id_never_requests_network(self):
        with patch('fetch_metadata.urlopen') as request:
            with self.assertRaises(ValueError):
                fetch_one('../../private')
            request.assert_not_called()

class RequestGateTest(unittest.TestCase):
    def test_request_spacing_and_shared_cooldown(self):
        from fetch_metadata import RequestGate
        clock = [0.0]
        with patch('fetch_metadata.time.monotonic', side_effect=lambda: clock[0]), patch('fetch_metadata.time.sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            gate = RequestGate(2, initial_delay=5)
            gate.wait()
            self.assertEqual(clock[0], 5)
            gate.wait()
            self.assertEqual(clock[0], 7)
            gate.cooldown(120)
            gate.wait()
            self.assertEqual(clock[0], 127)
