# 🧛‍♂️ DAKOSYS - Docker App Kometa Overlay System

DAKOSYS is a powerful tool for Plex users that creates and manages Trakt.tv lists and Kometa/PMM overlays. It helps you categorize anime episodes by type, track TV show statuses, display media file sizes, all running in Docker with automatic scheduling.

## ✨ Features

### 🗃️ Anime Episode Type Tracker

![Image](https://zipline.rlvd.eu/u/sm6SDX.png)


!! Trakt VIP needed !!

- Create overlays of Trakt.tv lists of anime episodes filtered by type (filler, manga canon, anime canon, mixed)

- Automate list updates with customizable scheduling

- Match episodes automatically

- Handle special title mappings between different sources

### 📺 TV/Anime Status Tracker

!! No Trakt VIP needed as long as you still have 1 list to use !!

![Image2](https://zipline.rlvd.eu/u/X6lWUS.png)

- Create overlays showing show status (airing, ended, cancelled, returning, mid-season finale, season finale, last episode, season premiere)

- Display air dates for upcoming episodes

- Highlight special episodes (season finales, season premieres)

- Generate Trakt lists of shows with upcoming episodes

### 📊 Size Overlay Service

!! Trakt not needed at all !!

![image3](https://zipline.rlvd.eu/u/3CKGBe.png)

- Create overlays showing file sizes for movies and TV shows

- Track size changes over time

- Display episode counts for TV series

- Customizable overlay appearance and positioning

### 🔔 Notifications System

- Discord webhook integration

- Notifications for errors, updates, and changes

### 📋 Requirements

- Plex Media Server

- Trakt.tv account

- Trakt.tv API application

- Docker and Docker Compose

- Kometa/PMM (Plex Meta Manager)
  
## 🐳 Quick Start
1. Create directories for config and data

```
mkdir -p dakosys/{config,data}
cd dakosys
```
2. Download the docker-compose.yml file

```
curl -O https://raw.githubusercontent.com/sahara101/dakosys/main/docker-compose.yml
```
3. Run the setup command
   
```
docker compose run --rm dakosys setup
```
This will guide you through creating a configuration file with options for all services.

4. Start the auto-updater daemon
```
docker compose up -d dakosys-updater
```
This starts the background service that automatically runs updates according to your schedule.

## 🧩 Service Configuration

During setup, you can enable three main services:

1. Anime Episode Type Tracker
Categorizes anime episodes by type (filler, manga canon, etc.), creates Trakt lists and Kometa overlays.

<div align="center">
  <h2>⚠️ TRAKT VIP REQUIRED ⚠️</h2>
  <p>Trakt free accounts are limited to 2-10 lists.<br>
  This app creates multiple lists (1 per episode type per anime).<br></p>
</div>

Since this cannot be fully automated because of differences in Anime Filler List and Trakt names I have added several commands for this service, see below. 

The other two services are set and forget :)

2. TV/Anime Status Tracker
Creates overlays showing airing status, next episode dates, and special episodes.

3. Size Overlay Service
Creates overlays displaying file sizes and episode counts.

Each service can be configured separately with different libraries and schedules.
## 📝 Usage Examples

You can always run ```docker compose run --rm dakosys --help``` to see possible commands, and then ```--help``` on each command to check how it is used. 

### Anime Episode Type Tracker

Create all list types for an anime at once

You can type either the Plex anime name or the Anime Filler List (AFL) name (from URL). For Example https://www.animefillerlist.com/shows/boruto-naruto-next-generations whereas ```boruto-naruto-next-generations``` is the name you need. 

The command below will first try to find the name in Plex. If it is a direct copy from Plex it will match it directly, if not it will try to find it. Then, it tries to match the Plex name to AFL. It uses a matching logic and asks if the found anime is the correct one. Please read the outputs. See an example at the end of README. 

```
docker compose run --rm dakosys create-all "One-Piece"
```

Create a list of filler episodes
```
docker compose run --rm dakosys create-list "Naruto-Shiuden" FILLER
```

Fix mapping errors for episodes
```
docker compose run --rm dakosys fix-mappings
```

List all available anime on Anime Filler List
```
docker compose run --rm dakosys list-anime
```

Show all episodes with their types
```
docker compose run --rm dakosys show-episodes "Demon Slayer Kimetsu No Yaiba"
```

Delete a list
```
docker compose run --rm dakosys delete-list bleach FILLER
```

Delere more lists at once
```
docker compose run --rm dakosys list-lists --format plain --anime "One Punch Man" | xargs -n2 docker compose run --rm --no-TTY dakosys delete-piped --force
```

### Managing Scheduled Updates

Add an anime to automatic updates
```
docker compose run --rm dakosys schedule add "Jujutsu Kaisen"
```

Remove an anime from automatic updates
```
docker compose run --rm dakosys schedule remove "Dragon Ball"
```

List all automatically updated anime
```
docker compose run --rm dakosys schedule list
```

Run an immediate update of all services
```
docker compose run --rm dakosys run-update all
```

Run an immediate update of a specific service
```
docker compose run --rm dakosys run-update tv_status_tracker
```
### List Management
List all Trakt lists created by DAKOSYS
```
docker compose run --rm dakosys list-lists
```

List all Trakt lists for a specific anime
```
docker compose run --rm dakosys list-lists --anime "Attack on Titan"
```

Manually synchronize collections file
This command will sync the Kometa collections file with all generated trakt lists. Useful in case the file gets deleted/altered.
```
docker compose run --rm dakosys sync-collections
```

## ⚙️ Scheduler Configuration
You can configure when updates run by editing the scheduler section in your config.yaml file. Each service can have its own schedule:
```
  anime_episode_type:
    type: "daily"
    times: ["03:00"]
  
  tv_status_tracker:
    type: "hourly"
    minute: 30
  
  size_overlay:
    type: "weekly"
    days: ["sunday"]
    time: "04:00"
```
Available schedule types:

hourly: Run every hour at the specified minute

daily: Run every day at specified times

weekly: Run on specified days of the week at a set time

monthly: Run on specified dates of the month at a set time

## 🔔 Notifications

DAKOSYS can send notifications to Discord about:

- New episodes added to lists

- Mapping errors that need attention

- List deletions

### Notification examples

```
New Episodes Added: The Seven Deadly Sins: Four Knights of the Apocalypse
Successfully added 22 new manga episodes for The Seven Deadly Sins: Four Knights of the Apocalypse.
Added Episodes
The Four Knights of the Apocalypse
The Demon of Echo Gorge
A Resolve Further Honed
Sistana Shaken
The Name of the Magic
Young Heroes
Master and Pupil
Roar of Destruction
A Real Holy Knight
A Sinister Endeavor

... and 12 more episodes
```

```
Mapping Errors: Seven Deadly Sins Four Knights Apocalypse
Failed to map 2 manga episodes for Seven Deadly Sins Four Knights Apocalypse.
Failed Episodes
The Boy Sets Out on Adventure
Unknown Power
Error Details
Failed to find match for the boy sets out on adventure
Failed to find match for unknown power
Run 'docker compose run --rm dakosys fix-mappings' to resolve these issues
```

```
Detected 0 new items and 2 changes. Total change: +23.30 GB
Media Libraries
• Filme: 11.79 TB - 386 movies
• Anime: 3.30 TB - 29 shows (3226 episodes)
• Seriale: 14.66 TB - 107 shows (4772 episodes)
Total Media Size
29.75 TB across 386 movies and 136 shows with 7998 episodes.
Changes Detected
Filme
• The Hunger Games: 53.96 GB → 77.36 GB (+23.40 GB)

Seriale
• Power Rangers (971 episodes): 439.47 GB → 439.37 GB (-0.10 GB)
```

```
TV/Anime Status Updates
Processed 136 shows. Found changes for 3 shows.
Date Changes (3)
• Dr. STONE - New date: 13/03
• Ghosts (US) - New date: 14/03
• Severance - New date: 14/03
```

TV show status changes

Media size changes

To enable notifications, provide a Discord webhook URL during setup.

## 📊 Monitoring and Logs

You can monitor the DAKOSYS services through various logs:

View logs from the updater service
```
docker compose logs -f dakosys-updater
```

Service-specific logs in the data directory:
- data/anime_trakt_manager.log
- data/tv_status_tracker.log
- data/size_overlay.log
- data/notifications.log
- data/auto_update.log
- data/scheduler.log

Mapping errors log
```
cat data/failed_episodes.log
```
## 🔧 Troubleshooting

### Missing Episodes in Lists

If episodes are missing, use the mapping fix tool:

```
docker compose run --rm dakosys fix-mappings
```
This interactive tool helps you create custom mappings for problematic episodes.

### Test Commands

Test your scheduler configuration
```
docker compose run --rm dakosys test-scheduler
```

### Test Discord notifications
```
docker compose run --rm dakosys test-notification
```

## 📚 Advanced Configuration

For advanced users, the full configuration is stored in config/config.yaml. You can also use service-specific setup:

Run setup for just one service
```
docker compose run --rm dakosys setup anime_episode_type
docker compose run --rm dakosys setup tv_status_tracker
docker compose run --rm dakosys setup size_overlay
```

## Example create-all

```
docker compose run --rm dakosys create-all "Bleach"
Connecting to Plex server...
Connected to Plex server successfully!
Found direct match in Plex: Bleach
Fetching anime list from AnimeFillerList...
Looking for AnimeFillerList match for: Bleach
Trying variations: bleach
Found exact match on full title: bleach
Found match: bleach
Use this match? [Y/n]: y
2025-03-10 23:16:01,031 - mappings_manager - INFO - Saved mappings to /app/config/mappings.yaml
Added mapping: bleach → Bleach
Using mapping: bleach → Bleach
Looking for 'Bleach' in Plex libraries...
Found TMDB ID: 30984
Found Trakt show ID: 30850

Checking for MANGA episodes...

Found 162 MANGA episodes:
1. Episode 1: The Day I Became a Shinigami (Manga Canon)
2. Episode 2: The Shinigami's Work (Manga Canon)
3. Episode 3: The Older Brother's Wish, the Younger Sister's Wish (Manga Canon)
4. Episode 4: Cursed Parakeet (Manga Canon)
5. Episode 5: Beat the Invisible Enemy! (Manga Canon)
... and 157 more episodes
Trakt list 'bleach_manga canon' created successfully with ID 30876171.
Processing episodes... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

Adding 162 episodes in batches...
Rate limit hit, retrying batch 17 in 1s... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

Summary:
Successfully added: 162 episodes
Already in list (skipped): 0 episodes
Failed to add: 0 episodes
List created: https://trakt.tv/users/sahara/lists/bleach_manga-canon

Checking for FILLER episodes...

Found 163 FILLER episodes:
1. Episode 33: Miracle! The Mysterious New Hero (Filler)
2. Episode 50: The Reviving Lion (Filler)
3. Episode 64: New School Term, Renji Has Come to the Material World?! (Filler)
4. Episode 65: Creeping Terror, the Second Victim (Filler)
5. Episode 66: Breakthrough! The Trap Hidden in the Labyrinth (Filler)
... and 158 more episodes
Trakt list 'bleach_filler' created successfully with ID 30876173.
Processing episodes... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

Adding 163 episodes in batches...
Rate limit hit, retrying batch 17 in 1s... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

Summary:
Successfully added: 163 episodes
Already in list (skipped): 0 episodes
Failed to add: 0 episodes
List created: https://trakt.tv/users/sahara/lists/bleach_filler

Checking for ANIME episodes...
No ANIME episodes found for bleach

Checking for MIXED episodes...

Found 41 MIXED episodes:
1. Episode 8: June 17, Memories in the Rain (Mixed Canon/Filler)
2. Episode 27: Release the Death Blow! (Mixed Canon/Filler)
3. Episode 32: Stars and the Stray (Mixed Canon/Filler)
4. Episode 46: Authentic Records! School of Shinigami (Mixed Canon/Filler)
5. Episode 109: Ichigo and Rukia, Thoughts in the Revolving Around Heaven (Mixed Canon/Filler)
... and 36 more episodes
Trakt list 'bleach_mixed canon/filler' created successfully with ID 30876176.
Processing episodes... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

Adding 41 episodes in batches...
Rate limit hit, retrying batch 5 in 1s... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

Summary:
Successfully added: 41 episodes
Already in list (skipped): 0 episodes
Failed to add: 0 episodes
List created: https://trakt.tv/users/sahara/lists/bleach_mixed-canon-filler

🎉 List creation complete! 🎉

Created lists:
✓ MANGA: 162 episodes - https://trakt.tv/users/sahara/lists/bleach_manga-canon
✓ FILLER: 163 episodes - https://trakt.tv/users/sahara/lists/bleach_filler
✓ MIXED: 41 episodes - https://trakt.tv/users/sahara/lists/bleach_mixed-canon-filler

Would you like to add 'Bleach' to the automatic update schedule? [Y/n]: n
'Bleach' will not be automatically updated.

Episode types with no episodes:
✗ ANIME: No episodes found
Synchronizing collections file with Trakt lists...
Collections synchronized successfully!
Updated file: /kometa/config/collections/anime_episode_type.yml
```


