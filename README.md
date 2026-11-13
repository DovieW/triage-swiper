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
  be edited from Shortlist, Maybe, and Tossed.
- The card reserves single-finger gestures for swiping; pinch zoom remains
  available. Use the Shortlist link or scroll outside the card for filters.
- Preview videos in an overlay, or open them on YouTube if embedding is disabled.
- Export the full Keep shortlist as JSON or one video URL per line. Filters only
  affect the displayed list.

## Your catalog and saved choices

Private data defaults to **`~/.local/share/ai-talk-picker/`**. The directory name
is retained for compatibility with the original app:

| File | Purpose |
| --- | --- |
| `catalog.json` | Your base catalog; overrides the bundled example when present |
| `history-videos.json` | Additional videos imported from Takeout |
| `decisions.sqlite3` | Shared Keep, Toss, and Maybe choices |
| `history-import-report.json` | Summary of the latest history import |

These files stay outside the repo. Takeout archives, local JSON files, databases,
and environment files are also ignored by Git. The public example contains no
watch history or personal choices.

Use `catalog.example.json` as the catalog format. Each video needs a unique
YouTube `id`, `url`, `title`, `channel`, `category`, and `duration_seconds` (or
`null` when unknown). Channel IDs, handles, and URLs are needed for history
imports; notes use `reason`, and publication dates use `published_date`.
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

## Tests

Python tests use temporary databases and the public example catalog. Node.js
18+ is only needed for the swipe tests; it is not required to run the app.

```sh
python3 -m unittest -v
node --test test_swipe.cjs
```
