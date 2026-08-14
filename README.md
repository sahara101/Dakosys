# DAKOSYS - Docker App Kometa Overlay System

DAKOSYS is a tool for Plex users that creates and manages Trakt.tv lists and Kometa overlays. It categorizes anime episodes by type, tracks TV show statuses, and displays media file sizes — all running in Docker with automatic scheduling.

A built-in web dashboard lets you manage configuration, monitor services, browse logs, and handle anime mappings without touching the command line.

---

## Features

### Anime Episode Type Tracker

Trakt VIP required.

Creates Trakt lists and Kometa overlays categorizing anime episodes by type: filler, manga canon, anime canon, and mixed. Supports automatic scheduling and custom title mappings for episodes that differ between AnimeFillerList and Trakt.

<img width="1406" height="326" alt="image" src="https://github.com/user-attachments/assets/5d90e452-173c-4665-b020-add2625ed261" />

### TV / Anime Status Tracker

No Trakt account required.

Creates overlays showing the airing status of TV shows and anime: currently airing, ended, cancelled, returning, season finale, mid-season finale, final episode, and season premiere. Displays upcoming air dates, converted to your timezone from the network's real broadcast time. Generates a Next Airing collection of shows with upcoming episodes, ordered by air date — from a local file by default, or from a Trakt list if you prefer.

<img width="1391" height="876" alt="image" src="https://github.com/user-attachments/assets/ce2e31fe-aeee-467f-b498-6ea36ac0139b" />

### Size Overlay

No Trakt required.

Creates overlays showing file sizes for movies and TV shows. Tracks size changes over time and optionally displays episode counts.

<img width="1381" height="371" alt="image" src="https://github.com/user-attachments/assets/829cd5b1-2d67-456b-b41a-4a930b7a2b9a" />


### Web Dashboard

A web UI accessible at `http://your-host:3000`.

Features:
- Dashboard with service status, next scheduled runs, and media stats
- Configuration editor with built-in config reference documenting all options
- Log viewer for all services
- Anime management: add anime, view Trakt lists, resolve mapping errors
- TV status browser and Next Airing list with posters
- Library size browser
- Setup wizard for first-time configuration

<img width="1728" height="993" alt="image" src="https://github.com/user-attachments/assets/03af3c98-39f2-4121-99e2-74390d90f87b" />

### Notifications

Discord webhook integration.

---

## Requirements

- Plex Media Server
- Docker
- Kometa / Plex Meta Manager — **2.3.1 or newer** for the default Next Airing configuration, which uses Kometa's `text_file` builder. Kometa 2.3.1 itself requires Python 3.10+. On an older Kometa, set `next_airing.provider: trakt` instead
- TMDB API key — required by the TV Status Tracker under `metadata_provider: tvdb` (the default) and `tmdb`, where the tracker will not start without one. Optional under `metadata_provider: trakt`, and not needed at all for an Anime Episode Type only install
- TheTVDB v4 API key — **optional**. DAKOSYS reaches TheTVDB through a proxy operated for the project, so there is nothing to register ([details](#about-the-thetvdb-key))
- Trakt.tv account and API application — required by the Anime Episode Type service, and by the TV Status Tracker only if you set `metadata_provider: trakt` or `next_airing.provider: trakt`

> **Note on Trakt:** creating a new Trakt API application now [requires Trakt VIP](https://github.com/trakt/trakt-web/pull/3057). The TV Status Tracker no longer needs Trakt in its default configuration; the Anime Episode Type service still does.

---

## Quick Start

Create the directory structure:

```
mkdir -p dakosys/{config,data}
cd dakosys
```

Download docker-compose.yml:

```
curl -O https://raw.githubusercontent.com/sahara101/dakosys/main/docker-compose.yml
```

Run the setup wizard:

```
docker compose run --rm dakosys setup
```

Start the daemon:

```
docker compose up -d dakosys-updater
```

The web dashboard will be available at `http://your-host:3000`.

Add the generated YAML files to your Kometa config:

```yaml
Seriale:
  collection_files:
    - file: config/collections/seriale-next-airing.yml
  overlay_files:
    - file: config/overlays/size-overlays-seriale.yml
    - file: config/overlays/overlay_tv_status_seriale.yml

Anime:
  collection_files:
    - file: config/collections/anime-next-airing.yml
    - file: config/collections/anime_episode_type.yml
      schedule: weekly(monday)
  overlay_files:
    - file: config/overlays/size-overlays-anime.yml
    - file: config/overlays/fillers.yml
    - file: config/overlays/manga_canon.yml
    - file: config/overlays/anime_canon.yml
    - file: config/overlays/mixed.yml
    - file: config/overlays/overlay_tv_status_anime.yml
```

---

## Service Notes

**Anime Episode Type Tracker** requires Trakt VIP because it creates multiple lists (one per episode type per anime). Episode ordering in Plex must match TMDB ordering — for some shows like One Piece this requires manual adjustment.

**TV / Anime Status Tracker** and **Size Overlay** are set-and-forget once configured.

---

## Manual Commands

You can always run `docker compose run --rm dakosys --help` to list all commands, and `--help` on any command for usage details.

### Anime Episode Type

Create all list types for an anime:
```
docker compose run --rm dakosys create-all "One-Piece"
```

Create a specific list type:
```
docker compose run --rm dakosys create "Naruto-Shippuden" FILLER
```

Fix mapping errors for episodes:
```
docker compose run --rm dakosys fix-mappings
```

List all available anime on AnimeFillerList:
```
docker compose run --rm dakosys list-anime
```

Show all episodes and their types:
```
docker compose run --rm dakosys show-episodes "Demon Slayer Kimetsu No Yaiba"
```

Delete a list:
```
docker compose run --rm dakosys delete-list bleach FILLER
```

Delete multiple lists at once:
```
docker compose run --rm dakosys list-lists --format plain --anime "One Punch Man" | xargs -n2 docker compose run --rm --no-TTY dakosys delete-piped --force
```

### Scheduled Updates

Add an anime to the automatic update schedule:
```
docker compose run --rm dakosys schedule add "Jujutsu Kaisen"
```

Remove an anime from the schedule:
```
docker compose run --rm dakosys schedule remove "Dragon Ball"
```

List all scheduled anime:
```
docker compose run --rm dakosys schedule list
```

Run an immediate update of all services:
```
docker compose run --rm dakosys run-update all
```

Run an immediate update of a specific service:
```
docker compose run --rm dakosys run-update tv_status_tracker
```

### List Management

List all Trakt lists created by DAKOSYS:
```
docker compose run --rm dakosys list-lists
```

List Trakt lists for a specific anime:
```
docker compose run --rm dakosys list-lists --anime "Attack on Titan"
```

Sync the Kometa collections file with current Trakt lists:
```
docker compose run --rm dakosys sync-collections
```

---

## Scheduler Configuration

Each service has its own schedule block under `scheduler:` in `config.yaml`.

```yaml
scheduler:
  anime_episode_type:
    type: daily
    times: ["03:00"]

  tv_status_tracker:
    type: hourly
    minute: 30

  size_overlay:
    type: weekly
    days: ["sunday"]
    time: "04:00"
```

Schedule types:

| Type | Fields |
|------|--------|
| `daily` | `times: ["HH:MM", ...]` |
| `hourly` | `minute: N` |
| `weekly` | `days: ["monday", ...]`, `time: "HH:MM"` |
| `monthly` | `dates: [1, 15]`, `time: "HH:MM"` |
| `cron` | `expression: "0 3 * * *"` |
| `run` | Runs once at startup only |

---

## TV Status Custom Labels

Status text displayed on overlays defaults to English. Override any label in `config.yaml`:

```yaml
services:
  tv_status_tracker:
    labels:
      ended: "T E R M I N E E"
      cancelled: "A N N U L E E"
      returning: "R E V I E N T"
      airing: "EN COURS"
      season_finale: "FIN DE SAISON"
      mid_season_finale: "MI-SAISON"
      final_episode: "EPISODE FINAL"
      season_premiere: "PREMIERE SAISON"
```

All keys are optional. Labels for `airing`, `season_finale`, `mid_season_finale`, `final_episode`, and `season_premiere` have the air date appended automatically.

---

## Next Airing Collection

The Next Airing Kometa collection can be built from a local file (default) or from a Trakt list.

```yaml
services:
  tv_status_tracker:
    next_airing:
      provider: text_file          # text_file | trakt
      text_file_path: ''           # optional, where DAKOSYS writes the file
      kometa_text_file_path: ''    # optional, how Kometa refers to that file
```

> **Upgrading from 2.2.x:** this setting is new, so an install without it takes the `text_file`
> default — the Trakt list stops being updated and each `*-next-airing.yml` is regenerated to use
> the `text_file` builder. Set `provider: trakt` to keep the previous behaviour.

`trakt` keeps the existing behaviour: shows are synced to a Trakt list ordered by air date, and the collection uses a `trakt_list` builder.

`text_file` writes an ordered list of TMDB IDs locally and generates a collection using Kometa's `text_file` builder. Air-date ordering is preserved because `text_file` honours `collection_order: custom`. No Trakt list is created or updated.

**`text_file` requires Kometa 2.3.1 or newer, which in turn requires Python 3.10 or newer.** The builder does not exist in earlier versions — the collection fails to load with `Collection Error: text_file attribute not supported`, and Kometa continues without it, leaving the previous collection in place.

Switching `provider` regenerates the per-library `*-next-airing.yml` files. The previous version of each file is saved alongside it as `.bak`.

### Paths

DAKOSYS and Kometa often see the same directory at different paths — DAKOSYS may write to `/kometa/config/collections` while Kometa itself sees `/config/collections`, or runs from its own install directory. Two settings cover this:

- `text_file_path` — where DAKOSYS **writes** the file. Defaults to `<collections_dir>/next-airing.txt`.
- `kometa_text_file_path` — what gets written into the collection YAML for Kometa to **read**. Defaults to `config/<collections dir name>/next-airing.txt`, matching the relative style already used for `file_poster`.

The relative default works for both Docker installs (where `config/…` resolves under the mounted config volume) and native installs run from the Kometa directory. Override `kometa_text_file_path` only if your Kometa resolves paths differently.

---

## Metadata Provider

Show status and next-episode data come from TheTVDB when `tmdb_api_key` is set, and from Trakt when it is not. `tvdb` is the recommended provider and what `setup.py` configures for new installs:

```yaml
tvdb_api_key: your-key-here      # optional, the shared proxy is used without it

services:
  tv_status_tracker:
    metadata_provider: tvdb    # trakt | tmdb | tvdb
    use_tvmaze: true           # air-time fallback under tmdb and tvdb
```

> **Upgrading from 2.2.x:** this setting is new, so an install without it takes the default above.
> If you already have a `tmdb_api_key` — previously used only for Next Airing poster images — your
> status and air dates now come from TheTVDB instead of Trakt. Set `metadata_provider: trakt` to
> keep the previous source.

Combining `metadata_provider: tvdb` (or `tmdb`) with `next_airing.provider: text_file` runs the TV Status Tracker **without a Trakt account at all**.

The two `trakt` settings do not need the same credentials. `metadata_provider: trakt` reads Trakt's public endpoints and needs only `trakt.client_id` — no OAuth, no token. `next_airing.provider: trakt` writes to a Trakt list and therefore needs the full application plus an authorized token.

Both `tmdb` and `tvdb` require `tmdb_api_key`, and the tracker refuses to start without it — TMDB supplies the show status and which episode airs next, including the `CANCELLED` state that TheTVDB has no equivalent for. `tvdb` then adds the exact air time on top. `tvdb_api_key` is optional: without one, TheTVDB is reached through the shared proxy.

### Choosing the provider during setup

The web setup wizard asks which metadata source to use and writes `metadata_provider` accordingly. `setup.py`, the CLI setup, always writes `metadata_provider: tvdb` — selecting the source there is coming in the next release. Until then, set the key in `config.yaml` directly if you want `trakt` or `tmdb` on a CLI-configured install.

### About the TheTVDB key

You do not need to register anything. Since November 2020 TheTVDB issues [per-project keys, not per-user keys](https://thetvdb.com/api-information), and their terms require the key holder to keep it confidential — so the key is never shipped to clients. DAKOSYS reaches TheTVDB through a small proxy operated for the project, and attribution is displayed in the dashboard footer.

Self-hosting the whole chain is supported: set `DAKOSYS_TVDB_API_KEY` in the container environment, or `tvdb_api_key` in `config.yaml`, and DAKOSYS calls TheTVDB directly with your own project key.

If TheTVDB cannot be reached — no key and an unreachable proxy — the run does not fail. Under `tvdb` the show record already comes from TMDB and TheTVDB only supplies the air time, so an unavailable TheTVDB simply means that upgrade does not happen: TVmaze is tried next when `use_tvmaze` is on, and failing that the TMDB calendar date is shown as-is, unconverted.

If you are an individual user wanting to support TheTVDB, [subscribe](https://thetvdb.com/subscribe) rather than requesting an API key.

### Why tvdb

TheTVDB stores an episode's calendar date separately from the series' broadcast time and country of origin. Combining the three yields a real UTC instant, so the date renders correctly in every timezone, where a bare TMDB date cannot.

Measured end to end against Trakt across 14 airing shows in 5 timezones, `tvdb` rendered the wrong day **20%** of the time versus **31%** for an unconverted TMDB date. Eight of the fourteen shows were exact in every timezone. The residual comes from three causes, none of which the timezone conversion can fix: TheTVDB and TMDB occasionally disagree about which episode airs next, TheTVDB sometimes has not added an upcoming season yet (the date falls back to TMDB's, unconverted), and streaming platforms have no single global release instant, so sources legitimately differ by a few hours.

It also carries `finaleType`, which restores the `FINAL_EPISODE` status that TMDB alone cannot distinguish from a season finale.

### Automatic fallback

Trakt's public metadata endpoints need only a `client_id`, so `metadata_provider: trakt` works without OAuth as long as `next_airing.provider` is `text_file`. Should Trakt reject those requests anyway — an expired or revoked application key, or an endpoint moved behind Trakt VIP — DAKOSYS logs the HTTP status and switches to TMDB for the remainder of the run rather than leaving shows unprocessed. This needs `tmdb_api_key` to be set; without it the run continues but the affected shows get no status.

The fallback is per-run and not persisted: the next run retries Trakt first.

### Air dates and timezones

TMDB only provides a calendar date for an episode, with no time of day, so it cannot be converted to a viewer's timezone. DAKOSYS therefore looks the episode up on TVmaze (free, no API key) to obtain a real UTC timestamp, and converts only that. Where TVmaze has no entry, the TMDB date is displayed as-is rather than converted — converting a bare date would shift it a day for users in negative UTC offsets.

Set `use_tvmaze: false` to skip the lookup entirely and always use TMDB dates as-is.

In practice this matches Trakt closely. On a 14-show library, 13 dates were identical to Trakt's and all statuses matched; the one difference was a show TVmaze had no upcoming episode for.

### Known differences from Trakt

- TMDB does not distinguish a series finale from a season finale ahead of broadcast, so `FINAL_EPISODE` is reported as `SEASON_FINALE`.
- Streaming releases have no real air time. TVmaze substitutes noon UTC, which is stable across timezones; shows sharing a date are ordered by title.
- TVmaze coverage is thinner for anime, which falls back to TMDB dates.

---

## Notifications

Discord webhook notifications.

```yaml
notifications:
  enabled: true
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
```

Test notifications:
```
docker compose run --rm dakosys test-notification
```

---

## Logs

Service logs are written to the `data/` directory:

- `data/anime_trakt_manager.log`
- `data/tv_status_tracker.log`
- `data/size_overlay.log`
- `data/notifications.log`
- `data/auto_update.log`
- `data/scheduler.log`
- `data/failed_episodes.log`

View container logs:
```
docker compose logs -f dakosys-updater
```

---

## Troubleshooting

**Missing episodes in lists** — use the mapping fix tool:
```
docker compose run --rm dakosys fix-mappings
```

**Test scheduler configuration:**
```
docker compose run --rm dakosys test-scheduler
```

**Run setup for a single service:**
```
docker compose run --rm dakosys setup anime_episode_type
docker compose run --rm dakosys setup tv_status_tracker
docker compose run --rm dakosys setup size_overlay
```

---

## Example: create-all output

```
docker compose run --rm dakosys create-all "Bleach"
Connecting to Plex server...
Connected to Plex server successfully!
Found direct match in Plex: Bleach
Fetching anime list from AnimeFillerList...
Found exact match: bleach
Use this match? [Y/n]: y
Added mapping: bleach → Bleach

Checking for MANGA episodes...
Found 162 MANGA episodes
Trakt list 'bleach_manga canon' created successfully.
Successfully added: 162 episodes

Checking for FILLER episodes...
Found 163 FILLER episodes
Trakt list 'bleach_filler' created successfully.
Successfully added: 163 episodes

Checking for MIXED episodes...
Found 41 MIXED episodes
Trakt list 'bleach_mixed canon/filler' created successfully.
Successfully added: 41 episodes

Created lists:
  MANGA: 162 episodes - https://trakt.tv/users/sahara/lists/bleach_manga-canon
  FILLER: 163 episodes - https://trakt.tv/users/sahara/lists/bleach_filler
  MIXED: 41 episodes - https://trakt.tv/users/sahara/lists/bleach_mixed-canon-filler

Would you like to add 'Bleach' to the automatic update schedule? [Y/n]: n
```
