#!/usr/bin/env python3
"""Import matching Takeout history into the private picker catalog, without network requests."""
import argparse
from datetime import datetime, timedelta, timezone
import html
import json
from pathlib import Path
import re
import zipfile
from server import DEFAULT_SOURCE

PRIVATE = Path.home() / '.local/share/ai-talk-picker'


def select_history(markup, templates, start, end):
    selected = {}
    count = 0
    errors = 0
    for match in re.finditer(r'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">(.*?)</div>', markup, re.S):
        fragment = match[1]
        links = re.findall(r'<a href="([^"]+)">(.*?)</a>', fragment, re.S)
        if len(links) < 2:
            continue
        vid = re.search(r'^https://www.youtube.com/watch\?v=([\w-]{11})(?:&|$)', html.unescape(links[0][0]))
        cid = links[1][0].rsplit('/', 1)[-1]
        if not vid or cid not in templates:
            continue
        date = re.search(r'<br>([^<]+(?:EST|EDT|UTC))<br>', fragment)
        if not date:
            errors += 1
            continue
        try:
            value = html.unescape(date[1]).replace('\u202f', ' ').replace('\xa0', ' ')
            wall, zone = value.rsplit(' ', 1)
            dt = datetime.strptime(wall, '%b %d, %Y, %I:%M:%S %p').replace(tzinfo=timezone(timedelta(hours={'EST': -5, 'EDT': -4, 'UTC': 0}[zone])))
        except (KeyError, ValueError):
            errors += 1
            continue
        if not start <= dt < end:
            continue
        count += 1
        key = vid[1]
        if key in selected and dt <= datetime.fromisoformat(selected[key]['watched_at']):
            continue
        t = templates[cid]
        selected[key] = {
            'id': key, 'url': f'https://www.youtube.com/watch?v={key}',
            'title': html.unescape(re.sub('<[^>]+>', '', links[0][1])),
            'channel': t['channel'], 'channel_id': cid,
            'channel_handle': t['channel_handle'], 'channel_url': t['channel_url'],
            'category': t['category'], 'watched_at': dt.isoformat(),
            'published_date': None, 'published_at': None, 'duration_seconds': None,
            'reason': 'From your YouTube watch history.', 'older_standout': False,
            'starter_rank': None, 'source': 'takeout_watch_history'
        }
    return selected, count, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE, help='Catalog containing allowed channel IDs')
    parser.add_argument('--output-directory', type=Path, default=PRIVATE, help='Private import destination')
    parser.add_argument('--start', required=True, help='Inclusive ISO date/time with timezone')
    parser.add_argument('--end', required=True, help='Exclusive ISO date/time with timezone')
    args = parser.parse_args()
    start, end = datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        parser.error('Use an increasing date range with timezone offsets')
    original = json.loads(args.source.read_text())
    templates = {v['channel_id']: v for v in original['videos']}
    with zipfile.ZipFile(args.archive) as z:
        members = [i for i in z.namelist() if i.endswith('/history/watch-history.html')]
        if len(members) != 1:
            raise ValueError('Expected one watch-history.html member')
        selected, records, errors = select_history(z.read(members[0]).decode('utf-8'), templates, start, end)
    if errors:
        raise ValueError(f'{errors} matching channel records could not be parsed; refusing partial import')
    existing = {v['id'] for v in original['videos']}
    extras = sorted((v for k, v in selected.items() if k not in existing), key=lambda v: v['watched_at'], reverse=True)
    report = {
        'archive': args.archive.name, 'start_inclusive': start.isoformat(), 'end_exclusive': end.isoformat(),
        'matching_watch_records': records, 'unique_history_videos': len(selected),
        'already_in_original': len(set(selected) & existing), 'added': len(extras),
        'combined_video_count': len(existing) + len(extras),
        'unique_by_channel': {name: sum(v['channel'] == name for v in selected.values()) for name in sorted({v['channel'] for v in templates.values()})},
        'unknown_durations_added': len(extras)
    }
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for name, data in [('history-videos.json', {'videos': extras}), ('history-import-report.json', report)]:
        tmp = args.output_directory / (name + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        tmp.chmod(0o600)
        tmp.replace(args.output_directory / name)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
