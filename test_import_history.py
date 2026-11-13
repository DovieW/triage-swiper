from datetime import datetime
import unittest
from import_history import select_history

TEMPLATE = {'channel': 'Example', 'channel_id': 'UCExample', 'channel_handle': 'example', 'channel_url': 'https://www.youtube.com/@example', 'category': 'AI engineering'}


def entry(vid, date, channel='UCExample', title='Example &amp; talk'):
    return f'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">Watched <a href="https://www.youtube.com/watch?v={vid}">{title}</a><br><a href="https://www.youtube.com/channel/{channel}">Example</a><br>{date}<br></div>'


class ImportTest(unittest.TestCase):
    def select(self, markup):
        return select_history(markup, {'UCExample': TEMPLATE}, datetime.fromisoformat('2026-05-13T00:00:00-04:00'), datetime.fromisoformat('2026-11-14T00:00:00-05:00'))

    def test_channel_date_filter_deduplication_and_unknown_metadata(self):
        markup = entry('abcdefghijk', 'May 13, 2026, 12:00:00 AM EDT')
        markup += entry('abcdefghijk', 'Nov 13, 2026, 1:00:00 PM EST')
        markup += entry('oldvideo001', 'May 12, 2026, 11:59:59 PM EDT')
        markup += entry('newvideo001', 'Nov 14, 2026, 12:00:00 AM EST')
        markup += entry('otherchan01', 'Nov 13, 2026, 1:00:00 PM EST', 'UCOther')
        videos, records, errors = self.select(markup)
        self.assertEqual((len(videos), records, errors), (1, 2, 0))
        self.assertEqual(videos['abcdefghijk']['watched_at'], '2026-11-13T13:00:00-05:00')
        self.assertEqual(videos['abcdefghijk']['title'], 'Example & talk')
        self.assertIsNone(videos['abcdefghijk']['duration_seconds'])
        self.assertIsNone(videos['abcdefghijk']['published_date'])

    def test_repeated_hour_compares_instants_and_reports_parse_failures(self):
        markup = entry('abcdefghijk', 'Nov 1, 2026, 1:10:00 AM EST')
        markup += entry('abcdefghijk', 'Nov 1, 2026, 1:50:00 AM EDT')
        markup += entry('badrecord01', 'Invalid date')
        videos, _, errors = self.select(markup)
        self.assertEqual(videos['abcdefghijk']['watched_at'], '2026-11-01T01:10:00-05:00')
        self.assertEqual(errors, 1)
