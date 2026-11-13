#!/usr/bin/env python3
"""Cache small channel avatars locally; never fetch images during swiping."""
import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from server import DEFAULT_SOURCE, DATA_DIR


class AvatarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.avatar = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('property') == 'og:image':
            self.avatar = attrs.get('content')


def avatar_url(page):
    parser = AvatarParser()
    parser.feed(page)
    url = parser.avatar or ''
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('yt3.googleusercontent.com', 'yt3.ggpht.com'):
        raise ValueError('No trusted YouTube channel avatar found')
    return re.sub(r'=s\d+', '=s64', url)


def cache_avatar(cid, directory):
    if not re.fullmatch(r'UC[\w-]{22}', cid):
        raise ValueError('Invalid channel ID')
    if any((directory / (cid + ext)).exists() for ext in ('.jpg', '.png', '.webp')):
        return
    request = Request(f'https://www.youtube.com/channel/{cid}', headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'})
    with urlopen(request, timeout=12) as response:
        url = avatar_url(response.read(4_000_000).decode())
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=12) as response:
        mime = response.headers.get_content_type()
        if mime not in ('image/jpeg', 'image/png', 'image/webp'):
            raise ValueError('Unexpected avatar image format')
        data = response.read(500_001)
    if not data or len(data) > 500_000:
        raise ValueError('Avatar image is empty or too large')
    ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}[mime]
    temp = directory / (cid + '.tmp')
    temp.write_bytes(data)
    temp.replace(directory / (cid + ext))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output-directory', type=Path, default=DATA_DIR / 'channel-avatars')
    args = parser.parse_args()
    videos = json.loads(args.source.read_text())['videos']
    channels = {v['channel_id']: v['channel'] for v in videos if v.get('channel_id')}
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for cid, name in channels.items():
        try:
            cache_avatar(cid, args.output_directory)
            print(f'Cached: {name}', flush=True)
        except HTTPError as exc:
            print(f'HTTP {exc.code}: {name}', flush=True)
            if exc.code in (429, 503):
                print('Stopping on rate limit. Re-run later to resume.', flush=True)
                break
        except Exception as exc:
            print(f'Unavailable: {name}: {exc}', flush=True)
        time.sleep(.5)


if __name__ == '__main__':
    main()
