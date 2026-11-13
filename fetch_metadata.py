#!/usr/bin/env python3
"""Cache YouTube descriptions and runtimes using one watch-page request per video."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

DATA_DIR = Path.home() / '.local/share/ai-talk-picker'


def ensure_metadata(db):
    db.execute('CREATE TABLE IF NOT EXISTS video_metadata (id TEXT PRIMARY KEY, data TEXT NOT NULL, fetched_at TEXT NOT NULL)')


def cached_metadata(database, vid=None):
    with sqlite3.connect(database, timeout=10) as db:
        if vid is not None:
            row = db.execute('SELECT data FROM video_metadata WHERE id=?', (vid,)).fetchone()
            return json.loads(row[0]) if row else {}
        return {key: json.loads(value) for key, value in db.execute('SELECT id,data FROM video_metadata')}


def parse_page(page, vid):
    match = re.search(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*', page)
    if not match:
        raise ValueError('YouTube player metadata is missing (page format or availability changed)')
    player, _ = json.JSONDecoder().raw_decode(page[match.end():])
    details = player.get('videoDetails', {})
    if details.get('videoId') != vid:
        raise ValueError('Video unavailable or returned a different video ID')
    result = {'description': details.get('shortDescription') or ''}
    length = details.get('lengthSeconds')
    if length and str(length).isdigit():
        result['duration_seconds'] = int(length)
    published = player.get('microformat', {}).get('playerMicroformatRenderer', {}).get('publishDate')
    if published:
        result['published_date'] = datetime.fromisoformat(published.replace('Z', '+00:00')).date().isoformat()
    return result


def fetch_one(vid, timeout=10):
    if not re.fullmatch(r'[\w-]{11}', vid):
        raise ValueError('Invalid video ID')
    request = Request(f'https://www.youtube.com/watch?v={vid}', headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'})
    with urlopen(request, timeout=timeout) as response:
        page = response.read(4_000_000).decode('utf-8')
    return parse_page(page, vid)


class RequestGate:
    """Space request starts and share server-requested cooldowns across workers."""
    def __init__(self, delay, initial_delay=0):
        self.delay = delay
        self.next_request = time.monotonic() + initial_delay
        self.lock = threading.Lock()

    def wait(self):
        while True:
            with self.lock:
                remaining = self.next_request - time.monotonic()
                if remaining <= 0:
                    self.next_request = time.monotonic() + self.delay
                    return
            time.sleep(min(remaining, 1))

    def cooldown(self, seconds):
        with self.lock:
            self.next_request = max(self.next_request, time.monotonic() + seconds)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    default_source = DATA_DIR / 'catalog.json'
    parser.add_argument('--source', type=Path, default=default_source if default_source.exists() else Path(__file__).parent / 'catalog.example.json')
    parser.add_argument('--extra-source', type=Path, default=DATA_DIR / 'history-videos.json')
    parser.add_argument('--database', type=Path, default=DATA_DIR / 'decisions.sqlite3')
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=1)
    parser.add_argument('--delay', type=float, default=2, help='Seconds between request starts (minimum 0.5)')
    parser.add_argument('--initial-delay', type=float, default=0, help='Cooldown before beginning requests')
    args = parser.parse_args()
    if args.delay < .5 or args.initial_delay < 0:
        parser.error('Delay must be at least 0.5 seconds; initial delay must be nonnegative')
    videos = json.loads(args.source.read_text())['videos']
    if args.extra_source.exists():
        videos += json.loads(args.extra_source.read_text())['videos']
    ids = list(dict.fromkeys(v['id'] for v in videos))
    args.database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.database, timeout=10) as db:
        ensure_metadata(db)
    existing = cached_metadata(args.database)
    pending = [vid for vid in ids if vid not in existing]
    progress_path = args.database.parent / 'metadata-progress.json'
    start = time.monotonic()
    gate = RequestGate(args.delay, args.initial_delay)
    done = 0
    failures = []

    def progress():
        payload = {'total': len(ids), 'cached': len(ids) - len(pending) + done, 'failed': failures, 'remaining': len(pending) - done - len(failures), 'elapsed_seconds': round(time.monotonic() - start, 1)}
        temp = progress_path.with_suffix('.tmp')
        temp.write_text(json.dumps(payload, indent=2) + '\n')
        temp.chmod(0o600)
        temp.replace(progress_path)
        print(json.dumps({k: v for k, v in payload.items() if k != 'failed'}, ensure_ascii=False), flush=True)

    def fetch(vid):
        for attempt in range(4):
            gate.wait()
            try:
                data = fetch_one(vid)
                with sqlite3.connect(args.database, timeout=10) as db:
                    db.execute('INSERT OR REPLACE INTO video_metadata VALUES (?,?,?)', (vid, json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
                return None
            except HTTPError as exc:
                if exc.code in (429, 503):
                    try:
                        retry_after = float(exc.headers.get('Retry-After', '0'))
                    except (ValueError, TypeError, AttributeError):
                        retry_after = 0
                    pause = max(120 * (2 ** attempt), retry_after)
                    gate.cooldown(pause)
                    exc.close()
                    print(f'HTTP {exc.code}: pausing requests for at least {pause:g} seconds.', flush=True)
                    if attempt < 3:
                        continue
                return {'id': vid, 'error': str(exc)}
            except Exception as exc:
                return {'id': vid, 'error': str(exc)}

    progress()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(fetch, vid) for vid in pending]
        for future in as_completed(futures):
            failure = future.result()
            if failure:
                failures.append(failure)
            else:
                done += 1
            progress()
    if failures:
        print(f'{len(failures)} unavailable/failed videos. Re-run to retry; successful entries remain cached.', flush=True)


if __name__ == '__main__':
    main()
