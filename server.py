#!/usr/bin/env python3
"""Private, dependency-free Triage Swiper server. Run with --help for configuration."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from fetch_metadata import ensure_metadata, cached_metadata

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path.home() / '.local/share/ai-talk-picker'
DEFAULT_TAGS = {'maybe1': 'Maybe 1', 'maybe2': 'Maybe 2', 'maybe3': 'Maybe 3'}
DEFAULT_SOURCE = DATA_DIR / 'catalog.json' if (DATA_DIR / 'catalog.json').exists() else ROOT / 'catalog.example.json'


def make_handler(source, database, extra_source=None):
    videos = json.loads(Path(source).read_text())['videos']
    original_ids = {v['id'] for v in videos}
    if extra_source and Path(extra_source).exists():
        extras = json.loads(Path(extra_source).read_text())['videos']
        videos += [v for v in extras if v['id'] not in original_ids]
    ids = {v['id'] for v in videos}
    if not videos or len(videos) != len(ids):
        raise ValueError('Expected a nonempty catalog with unique video IDs')
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, status TEXT NOT NULL, revision INTEGER NOT NULL)')
        db.execute("UPDATE decisions SET status='maybe2',revision=revision+1 WHERE status='later'")
        db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), tags TEXT NOT NULL, revision INTEGER NOT NULL)')
        ensure_metadata(db)

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, mime='application/json', filename=None):
            if mime == 'application/json':
                body = json.dumps(body, ensure_ascii=False).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' https://i.ytimg.com; frame-src https://www.youtube-nocookie.com; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def state(self):
            with sqlite3.connect(database) as db:
                return {i: {'status': s, 'revision': r} for i, s, r in db.execute('SELECT id,status,revision FROM decisions')}

        def settings(self):
            with sqlite3.connect(database, timeout=10) as db:
                row = db.execute('SELECT tags,revision FROM settings WHERE id=1').fetchone()
            return {'tags': json.loads(row[0]) if row else DEFAULT_TAGS, 'revision': row[1] if row else 0}

        def catalog(self):
            cached = cached_metadata(database)
            return [dict(v, **{key: value for key, value in cached.get(v['id'], {}).items() if key != 'description'}) for v in videos]

        def do_GET(self):
            path = urlparse(self.path).path
            if path == '/api/talks':
                return self.send(200, {'videos': self.catalog()})
            if path == '/api/settings':
                return self.send(200, self.settings())
            if path == '/api/metadata':
                vid = parse_qs(urlparse(self.path).query).get('id', [''])[0]
                if vid not in ids:
                    return self.send(404, {'error': 'Unknown video'})
                return self.send(200, cached_metadata(database, vid))
            if path == '/api/decisions':
                return self.send(200, self.state())
            if path in ('/api/export.json', '/api/export.txt'):
                state = self.state()
                selected = [v for v in self.catalog() if state.get(v['id'], {}).get('status') == 'keep']
                if path.endswith('.txt'):
                    return self.send(200, ''.join(v['url'] + '\n' for v in selected), 'text/plain; charset=utf-8', 'selected-talks.txt')
                return self.send(200, {'video_count': len(selected), 'duration_seconds': sum(v.get('duration_seconds') or 0 for v in selected), 'unknown_duration_count': sum(v.get('duration_seconds') is None for v in selected), 'videos': selected}, filename='selected-talks.json')
            assets = {'/swipe.js': ('swipe.js', 'text/javascript; charset=utf-8'), '/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in assets:
                name, mime = assets[path]
                return self.send(200, (ROOT / name).read_bytes(), mime)
            self.send(404, {'error': 'Not found'})

        def do_POST(self):
            if self.path not in ('/api/decision', '/api/settings'):
                return self.send(404, {'error': 'Not found'})
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                return self.send(403, {'error': 'Origin rejected'})
            if self.headers.get('Content-Type') != 'application/json':
                return self.send(415, {'error': 'JSON required'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096:
                    raise ValueError()
                data = json.loads(self.rfile.read(size))
                if self.path == '/api/settings':
                    return self.save_settings(data)
                vid, status, revision = data['id'], data['status'], data['revision']
                if status == 'later':
                    status = 'maybe2'  # Accept choices from tabs opened before the update.
                if vid not in ids or status not in ('pending', 'keep', 'pass', 'maybe1', 'maybe2', 'maybe3') or type(revision) is not int or revision < 0:
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                return self.send(400, {'error': 'Invalid decision'})
            try:
                with sqlite3.connect(database, timeout=10) as db:
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('SELECT status,revision FROM decisions WHERE id=?', (vid,)).fetchone()
                    actual = row[1] if row else 0
                    if revision != actual:
                        return self.send(409, {'error': 'This talk changed on another device. Refreshed; please choose again.'})
                    db.execute('INSERT INTO decisions VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,revision=excluded.revision', (vid, status, actual + 1))
                self.send(200, {'status': status, 'revision': actual + 1})
            except sqlite3.Error:
                self.send(503, {'error': 'Could not save. Please try again.'})

        def save_settings(self, data):
            try:
                tags, revision = data['tags'], data['revision']
                if not isinstance(tags, dict) or set(tags) != set(DEFAULT_TAGS) or type(revision) is not int or revision < 0:
                    raise ValueError()
                if any(not isinstance(value, str) or not 1 <= len(value.strip()) <= 32 for value in tags.values()):
                    raise ValueError()
                tags = {key: value.strip() for key, value in tags.items()}
                if len({value.casefold() for value in tags.values()}) != 3:
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                return self.send(400, {'error': 'Use three distinct tag names, each 1–32 characters.'})
            try:
                with sqlite3.connect(database, timeout=10) as db:
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('SELECT revision FROM settings WHERE id=1').fetchone()
                    current = row[0] if row else 0
                    if revision != current:
                        return self.send(409, {'error': 'Tag names changed on another device. Close and reopen Edit tags.'})
                    db.execute('INSERT OR REPLACE INTO settings VALUES (1,?,?)', (json.dumps(tags), current + 1))
                self.send(200, {'tags': tags, 'revision': current + 1})
            except sqlite3.Error:
                self.send(503, {'error': 'Could not save tag names. Try again.'})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8789)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--database', type=Path, default=Path.home() / '.local/share/ai-talk-picker/decisions.sqlite3')
    parser.add_argument('--extra-source', type=Path, default=Path.home() / '.local/share/ai-talk-picker/history-videos.json')
    args = parser.parse_args()
    os.umask(0o077)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.source, args.database, args.extra_source))
    print(f'Triage Swiper: http://{args.host}:{server.server_port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
