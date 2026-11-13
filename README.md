# Triage Swiper

A small, mobile-first app for quickly sorting videos. Currently supports YouTube
catalogs and Google Takeout watch history. The interface is called **Dovie's
Triage Swiper**.

Plain HTML, CSS, and JavaScript with a Python standard-library server. No build
step, Python packages, API keys, or account setup.

## Run

Requires Python 3.10 or newer.

```sh
git clone https://github.com/DovieW/triage-swiper.git
cd triage-swiper
python3 server.py
```

Open **http://127.0.0.1:8789**. On a fresh installation, the app loads the three
public videos in `catalog.example.json`.

- Swipe right to **Keep**, left to **Toss**.
- Buttons are **Toss**, **Tag**, and **Keep**. Tag opens a compact menu for
  **Maybe 1** (strongest interest), **Maybe 2** (undecided), or **Maybe 3**
  (long shot). Choose a level to save and advance; dismiss to leave the card unchanged.
- Keyboard: ← / →, 1 / 2 / 3, and Z to undo.
- Undo applies to choices made in the current tab session. Other decisions can
  be edited from Shortlist, Tagged, and Tossed.
- The card reserves single-finger gestures for swiping; pinch zoom remains
  available. Use the Shortlist link or scroll outside the card for filters.
- Preview videos in an overlay, or open them on YouTube if embedding is disabled.
- Export the full Keep shortlist as JSON or one video URL per line. Filters only
  affect the displayed list.
- Card space shows a YouTube description when supplied in the catalog, otherwise
  a clearly labeled selection note. Generic history placeholders are hidden;
  the text area scrolls independently. A **Description** button beside **YouTube**
  opens the complete text in a larger modal. The server reads cached descriptions and
  never requests YouTube while you swipe.

Tag names can be changed using **Edit tags** below the swipe area. The three
slots default to Maybe 1 / Maybe 2 / Maybe 3; renaming them preserves existing
choices and syncs across devices. Reset defaults changes the editor fields;
press Save to apply. The menu is centered on desktop and a compact bottom sheet
on phones.

## Your catalog and saved choices

Private data defaults to **`~/.local/share/ai-talk-picker/`**. The directory name
is retained for compatibility with the original app:

| File | Purpose |
| --- | --- |
| `catalog.json` | Your base catalog; overrides the bundled example when present |
| `history-videos.json` | Additional videos imported from Takeout |
| `decisions.sqlite3` | Shared choices, tag names, and cached YouTube metadata |
| `history-import-report.json` | Summary of the latest history import |

These files stay outside the repo. Takeout archives, local JSON files, databases,
and environment files are also ignored by Git. The public example contains no
watch history or personal choices.

Use `catalog.example.json` as the catalog format. Each video needs a unique
YouTube `id`, `url`, `title`, `channel`, `category`, and `duration_seconds` (or
`null` when unknown). Channel IDs, handles, and URLs are needed for history
imports; selection notes use `reason`, optional YouTube descriptions use `description`,
and publication dates use `published_date`.
Channels are derived from the catalog. Original entries take precedence over
imported duplicates.

```sh
python3 server.py --source /path/to/catalog.json --database /path/to/decisions.sqlite3
```

Other options: `--host`, `--port`, and `--extra-source`. Run with `--help` for
details. Back up SQLite while the server is stopped. Existing legacy `later`
choices migrate once to `maybe2`. Toss keeps the original internal `pass` value,
so existing decisions need no migration.

## Phone / Tailscale

```sh
python3 server.py --host YOUR_TAILSCALE_IP
```

On your phone, connect to the same tailnet and open
`http://YOUR_TAILSCALE_IP:8789`. The host computer must remain awake and connected.
The app has one shared shortlist and no sign-in: anyone allowed to reach the
server can read and edit it. Keep it on localhost or a trusted tailnet.

An optional Linux user service is included. It assumes `~/repos/triage-swiper`;
edit the command if your checkout differs, and set `--host` for tailnet access.

```sh
mkdir -p ~/.local/share/ai-talk-picker ~/.config/systemd/user
cp triage-swiper.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now triage-swiper
```

Use `systemctl --user restart triage-swiper` to restart, or
`journalctl --user -u triage-swiper` for logs. It starts with the user session.

## Import YouTube watch history

The importer reads the English HTML `history/watch-history.html` inside a
Takeout ZIP. It supports EST, EDT, and UTC timestamps, filters by **watch date**
and the channel IDs in your base catalog, then deduplicates repeated views using
the latest timestamp. It reads only watch history, without extracting the entire
archive or making network requests.

```sh
python3 import_history.py /path/to/takeout.zip \
  --source /path/to/catalog.json \
  --start 2026-01-01T00:00:00+00:00 \
  --end 2026-07-01T00:00:00+00:00
```

The start is inclusive and the end exclusive; both require timezone offsets.
Output goes to the private data directory, or `--output-directory PATH`. Each
import replaces the previous imported catalog and report; it does not delete
saved choices. Restart the server and reload the page after changing catalogs.

Takeout does not provide duration or publication date. Imported values remain
unknown; totals report unknown runtimes separately, and the duration filter has
an explicit unknown option. The app does not download videos.

## Cached descriptions and runtimes

```sh
python3 fetch_metadata.py
```

This optional batch tool uses one YouTube watch-page HTML request per video,
with one worker and two seconds between request starts by default. Optional
`--workers 1` through `4` share the same request pacing (`--delay`). It extracts the
creator's description and, when available, runtime and publication date. No
video or audio files are downloaded. It uses the same `--source`,
`--extra-source`, and `--database` options as the server.

Successful results are cached in the `video_metadata` SQLite table. Re-running
skips cached videos and retries failures. Progress is recorded privately in
`metadata-progress.json` beside the database. YouTube page-format changes,
consent pages, and unavailable videos can prevent extraction; failed entries
are reported and selection notes remain available as a fallback. HTTP 429/503
responses pause all requests with increasing cooldowns and respect numeric
Retry-After values. Use `--initial-delay SECONDS` to wait before resuming a batch.
A single page fetch can be quick; a full library can take minutes or longer when
YouTube throttles requests. None of this waiting affects the app.

The app preloads cached descriptions for the current and next cards. Description
text is fetched separately from the compact catalog; swipes never wait for
YouTube. A running batch becomes visible as entries arrive, without restarting
the server. Reload to refresh all catalog runtimes, or let current/next card
metadata load normally. New cache tables require one server restart when
upgrading from a version without this feature.

## Tests

Python tests use temporary databases and the public example catalog. Node.js
18+ is only needed for the swipe tests; it is not required to run the app.

```sh
python3 -m unittest -v
node --test test_swipe.cjs
```
