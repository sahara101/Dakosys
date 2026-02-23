# DAKOSYS - Docker App Kometa Overlay System

DAKOSYS is a tool for Plex users that creates and manages Trakt.tv lists and Kometa overlays. It categorizes anime episodes by type, tracks TV show statuses, and displays media file sizes — all running in Docker with automatic scheduling.

A built-in web dashboard lets you manage configuration, monitor services, browse logs, and handle anime mappings without touching the command line.

---

## Features

### Anime Episode Type Tracker

Trakt VIP required.

Creates Trakt lists and Kometa overlays categorizing anime episodes by type: filler, manga canon, anime canon, and mixed. Supports automatic scheduling and custom title mappings for episodes that differ between AnimeFillerList and Trakt.

![Anime Episode Type overlay](<img width="1426" height="331" alt="image" src="https://github.com/user-attachments/assets/28b631c0-1255-4642-9ed6-99a909e7949c" />)

### TV / Anime Status Tracker

No Trakt VIP required (uses one list).

Creates overlays showing the airing status of TV shows and anime: currently airing, ended, cancelled, returning, season finale, mid-season finale, final episode, and season premiere. Displays upcoming air dates. Generates a Trakt list of shows with upcoming episodes.

![TV Status overlay](<img width="1402" height="862" alt="image" src="https://github.com/user-attachments/assets/46c38565-5f89-40a4-bb2d-0fa7c0eb653b" />)

### Size Overlay

No Trakt required.

Creates overlays showing file sizes for movies and TV shows. Tracks size changes over time and optionally displays episode counts.

![Size overlay](<img width="1388" height="381" alt="image" src="https://github.com/user-attachments/assets/d2cb682b-8942-4f6b-bcf1-04451ba169c8" />)

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
- Trakt.tv account and API application
- TMDB API for UI posters
- Docker
- Kometa / Plex Meta Manager

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
docker compose run --rm dakosys create-list "Naruto-Shippuden" FILLER
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
