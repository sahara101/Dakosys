#!/usr/bin/env python3
"""
Auto-update functionality for DAKOSYS
Handles updates for all services based on configuration
"""

import os
import sys
import time
import yaml
import json
import requests
import re
import difflib
from datetime import datetime
import logging
from plexapi.server import PlexServer
import mappings_manager
from shared_utils import setup_rotating_logger
from size_overlay import run_size_overlay_service

import trakt_auth

DATA_DIR = "data"
if os.environ.get('RUNNING_IN_DOCKER') == 'true':
    DATA_DIR = "/app/data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

if os.environ.get('RUNNING_IN_DOCKER') == 'true':
    data_dir = "/app/data"
else:
    data_dir = DATA_DIR

log_file = os.path.join(data_dir, "anime_trakt_manager.log")
logger = setup_rotating_logger("anime_trakt_manager", log_file)

CONFIG = None
def load_config():
    """Load configuration from YAML file."""
    global CONFIG
    CONFIG = trakt_auth.load_config()

    try:
        mappings_data = mappings_manager.load_mappings()
        if 'mappings' in mappings_data:
            CONFIG['mappings'] = mappings_data['mappings']
        if 'trakt_mappings' in mappings_data:
            CONFIG['trakt_mappings'] = mappings_data['trakt_mappings']
        if 'title_mappings' in mappings_data:
            CONFIG['title_mappings'] = mappings_data['title_mappings']
    except Exception as e:
        logger.warning(f"Could not load mappings from mappings.yaml: {str(e)}")

    return CONFIG

load_config()

def normalize_episode_title(title):
    """Normalize episode title for better matching."""
    title = re.sub(r'[^\w\s]', ' ', title).lower()

    title = re.sub(r'part\s+(\d+)', r'\1', title)
    title = re.sub(r'\((\d+)\)', r'\1', title)

    title = re.sub(r'\d+x\d+\s*', '', title)
    title = re.sub(r'\(\d+\)\s*', '', title)

    replacements = {
        'episode': '',
        'ep': '',
        'the': '',
        'and': '',
    }

    for orig, repl in replacements.items():
        title = re.sub(r'\b' + orig + r'\b', repl, title)

    title = re.sub(r'\s+', ' ', title).strip()

    return title

def get_all_trakt_lists(access_token=None):
    """Get all Trakt lists for the user."""
    if not access_token:
        access_token = trakt_auth.ensure_trakt_auth(quiet=True)
        if not access_token:
            logger.error("Failed to get Trakt access token")
            return []

    config = trakt_auth.load_config()
    result = trakt_auth.make_trakt_request(f"users/{config['trakt']['username']}/lists")
    if result:
        return result
    return []

def get_anime_lists(trakt_lists):
    """Filter lists to only include anime lists created by this tool."""
    anime_lists = []
    config = trakt_auth.load_config()

    scheduled_anime = config.get('scheduler', {}).get('scheduled_anime', [])
    logger.info(f"Scheduled anime: {scheduled_anime}")

    for trakt_list in trakt_lists:
        name = trakt_list['name']
        if '_' in name and any(name.endswith(f"_{suffix}") for suffix in ['filler', 'manga canon', 'anime canon', 'mixed canon/filler']):
            anime_name, episode_type = name.rsplit('_', 1)

            if scheduled_anime and anime_name not in scheduled_anime:
                continue

            anime_lists.append({
                'list_id': trakt_list['ids']['trakt'],
                'name': name,
                'anime_name': anime_name,
                'episode_type': episode_type.upper()
            })

    if len(scheduled_anime) > 0:
        valid_lists = [l for l in trakt_lists if '_' in l['name'] and
                      any(l['name'].endswith(f"_{suffix}") for suffix in ['filler', 'manga canon', 'anime canon', 'mixed canon/filler'])]
        skipped_count = len(valid_lists) - len(anime_lists)
        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} unscheduled anime lists")

    return anime_lists

def get_plex_name(afl_name):
    """Convert AnimeFillerList name to user-friendly Plex name."""
    if not afl_name or afl_name == "unknown":
        return "Unknown Anime"

    config = trakt_auth.load_config()

    plex_name = config.get('mappings', {}).get(afl_name, None)

    if plex_name is None:
        try:
            mappings_data = mappings_manager.load_mappings()
            plex_name = mappings_data.get('mappings', {}).get(afl_name, afl_name)
        except Exception as e:
            logger.warning(f"Error loading from mappings_manager: {str(e)}")
            plex_name = afl_name

    if '-' in plex_name:
        plex_name = plex_name.replace('-', ' ').title()

    return plex_name

def get_anime_episodes(anime_name, episode_type_filter=None, silent=False):
    """Get episodes from AnimeFillerList website."""
    global CONFIG

    try:
        base_url = 'https://www.animefillerlist.com/shows/'
        anime_url = f'{base_url}{anime_name}'

        if not silent:
            logger.info(f"Fetching episode data from {anime_url}")

        response = requests.get(anime_url)
        if response.status_code != 200:
            logger.error(f"Failed to fetch data from AnimeFillerList. Status Code: {response.status_code}")
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        filtered_episodes = []

        config_data = CONFIG
        if config_data is None:
            try:
                config_data = trakt_auth.load_config() or {}
            except Exception as e:
                logger.warning(f"Failed to load config in get_anime_episodes: {str(e)}")
                config_data = {}

        title_mappings = config_data.get('title_mappings', {}) or {}
        anime_mapping = title_mappings.get(anime_name, {}) or {}

        for row in soup.find_all('tr'):
            columns = row.find_all('td')
            if len(columns) >= 3:
                episode_number = columns[0].text.strip()
                episode_name = columns[1].text.strip()
                episode_type = columns[2].text.strip()

                if anime_mapping:
                    remove_patterns = anime_mapping.get('remove_patterns', []) or []
                    for pattern in remove_patterns:
                        if isinstance(pattern, str):
                            episode_name = episode_name.replace(pattern, '').strip()

                    remove_numbers = anime_mapping.get('remove_numbers', []) or []
                    for number in remove_numbers:
                        try:
                            if isinstance(number, int):
                                episode_name = episode_name.replace(f'{number:02d}', '').strip()
                        except:
                            pass

                    if anime_mapping.get('remove_dashes', False):
                        episode_name = episode_name.replace('-', '').strip()

                    special_matches = anime_mapping.get('special_matches', {}) or {}
                    special_match = special_matches.get(episode_name)
                    if special_match:
                        episode_name = special_match

                if not episode_type_filter or episode_type.lower() == episode_type_filter.lower():
                    filtered_episodes.append({
                        'number': episode_number,
                        'name': episode_name,
                        'type': episode_type
                    })

        if not silent:
            logger.info(f"Found {len(filtered_episodes)} episodes matching filter: {episode_type_filter}")
        return filtered_episodes
    except Exception as e:
        logger.error(f"Error fetching episodes: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []

def get_tmdb_id_from_plex(plex, anime_name, silent=False):
    """Get TMDB ID for a show from Plex."""
    try:
        config = trakt_auth.load_config()

        anime_lib_names = config.get('plex', {}).get('libraries', {}).get('anime', [])
        if not anime_lib_names:
            return None
        anime_library = plex.library.section(anime_lib_names[0])

        mapped_anime_name = config.get('mappings', {}).get(anime_name.lower(), None)

        if mapped_anime_name is None:
            try:
                mappings_data = mappings_manager.load_mappings()
                mapped_anime_name = mappings_data.get('mappings', {}).get(anime_name.lower(), anime_name)
            except Exception as e:
                logger.warning(f"Error loading from mappings_manager: {str(e)}")
                mapped_anime_name = anime_name

        if not silent:
            logger.info(f"Looking for '{mapped_anime_name}' in Plex library")

        for show in anime_library.all():
            if show.title.lower() == mapped_anime_name.lower():
                for guid in show.guids:
                    if 'tmdb://' in guid.id:
                        tmdb_id = guid.id.split('//')[1]
                        if not silent:
                            logger.info(f"Found TMDB ID: {tmdb_id}")
                        return tmdb_id

        logger.warning(f"Could not find TMDB ID for '{mapped_anime_name}' in Plex")
        return None
    except Exception as e:
        logger.error(f"Error getting TMDB ID: {str(e)}")
        return None

def connect_to_plex():
    """Connect to Plex server."""
    try:
        config = trakt_auth.load_config()
        logger.info("Connecting to Plex server...")
        plex = PlexServer(config['plex']['url'], config['plex']['token'])
        logger.info("Connected to Plex server successfully!")
        return plex
    except Exception as e:
        logger.error(f"Failed to connect to Plex server: {str(e)}")
        return None

def update_anime_list(anime_list, access_token, plex, match_by="hybrid"):
    """Update a single anime list with new episodes."""
    global CONFIG
    anime_name = anime_list['anime_name']
    plex_name = get_plex_name(anime_name)

    episode_type_mapping = {
        'FILLER': 'FILLER',
        'MANGA CANON': 'MANGA CANON',
        'ANIME CANON': 'ANIME CANON',
        'MIXED CANON/FILLER': 'MIXED CANON/FILLER',
    }

    episode_type_filter = episode_type_mapping.get(anime_list['episode_type'])
    if not episode_type_filter:
        logger.error(f"Unknown episode type: {anime_list['episode_type']}")
        return False

    logger.info(f"Looking for '{plex_name}' in Plex library")
    tmdb_id = get_tmdb_id_from_plex(plex, anime_list['anime_name'])
    if not tmdb_id:
        logger.error(f"Could not find TMDB ID for {anime_list['anime_name']}")
        return False

    trakt_api_url = 'https://api.trakt.tv'

    headers = trakt_auth.get_trakt_headers(access_token)
    search_api_url = f'{trakt_api_url}/search/tmdb/{tmdb_id}?type=show'
    response = requests.get(search_api_url, headers=headers)

    if response.status_code != 200 or not response.json():
        logger.error(f"Failed to get Trakt show ID for {anime_list['anime_name']}")
        return False

    trakt_show_id = response.json()[0]['show']['ids']['trakt']

    anime_episodes = get_anime_episodes(anime_list['anime_name'], episode_type_filter)
    if not anime_episodes:
        logger.error(f"No episodes found on AnimeFillerList for {anime_list['anime_name']}")
        return False

    list_items_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists/{anime_list['list_id']}/items"
    response = requests.get(list_items_url, headers=headers)
    if response.status_code != 200:
        logger.error("Failed to get existing episodes")
        return False

    existing_episodes = response.json()
    existing_count = len([i for i in existing_episodes if i.get('type') == 'episode'])

    if len(anime_episodes) <= existing_count:
        logger.info(f"No new episodes found for {anime_list['name']}")
        return False

    logger.info(f"Found {len(anime_episodes)} episodes on AnimeFillerList")
    logger.info(f"Found {existing_count} episodes in existing list")
    logger.info(f"Found {len(anime_episodes) - existing_count} new episodes to add")

    existing_trakt_ids = set()
    for item in existing_episodes:
        if item.get('type') == 'episode' and 'episode' in item:
            trakt_id = item['episode'].get('ids', {}).get('trakt')
            if trakt_id:
                existing_trakt_ids.add(trakt_id)
    
    from anime_trakt_manager import add_episodes_to_trakt_list

    normalized_type = anime_list['episode_type'].lower()
    if "manga canon" in normalized_type:
        normalized_type = "manga"
    elif "anime canon" in normalized_type:
        normalized_type = "anime"
    elif "mixed canon/filler" in normalized_type:
        normalized_type = "mixed"
    elif normalized_type == "filler":
        normalized_type = "filler"
    
    success, has_failures, failure_info = add_episodes_to_trakt_list(
        anime_list['list_id'],
        anime_episodes,
        access_token,
        trakt_show_id,
        match_by,
        anime_name,
        normalized_type,
        existing_trakt_ids,
        update_mode=False
    )
    
    return success

def run_anime_episode_update(match_by="hybrid"):
    """Run the anime episode type service updates with enhanced list creation.
    
    This improved function:
    1. Checks for all episode types, not just existing lists
    2. Creates new lists when finding episodes of a new type
    3. Syncs the collections file after any changes
    """
    logger.info("Starting Anime Episode Type service updates")

    import anime_trakt_manager as _atm
    _atm.load_config()

    from anime_trakt_manager import clear_error_log_for_anime, add_episodes_to_trakt_list, create_or_get_trakt_list, get_list_name_format
    
    access_token = trakt_auth.ensure_trakt_auth(quiet=True)
    if not access_token:
        logger.error("No Trakt access token found")
        return False
    
    plex = connect_to_plex()
    if not plex:
        logger.error("Failed to connect to Plex server")
        return False

    scheduled_anime = CONFIG.get('scheduler', {}).get('scheduled_anime', [])
    if not scheduled_anime:
        logger.info("No anime scheduled for updates")
        return False

    trakt_lists = get_all_trakt_lists(access_token)
    if not trakt_lists:
        logger.error("Failed to get Trakt lists")
        return False

    created_new_lists = False
    updated_existing_lists = False

    for anime_name in scheduled_anime:
        logger.info(f"Checking {anime_name} for updates")
        clear_error_log_for_anime(anime_name)
        plex_name = get_plex_name(anime_name)
        
        tmdb_id = get_tmdb_id_from_plex(plex, anime_name, silent=True)
        if not tmdb_id:
            logger.error(f"Could not find TMDB ID for {anime_name} (Plex: {plex_name})")
            continue
        
        headers = trakt_auth.get_trakt_headers(access_token)
        search_api_url = f'https://api.trakt.tv/search/tmdb/{tmdb_id}?type=show'
        response = requests.get(search_api_url, headers=headers)
        
        if response.status_code != 200 or not response.json():
            logger.error(f"Failed to get Trakt show ID for {anime_name} (Plex: {plex_name})")
            continue
        
        trakt_show_id = response.json()[0]['show']['ids']['trakt']
        
        episode_types = [
            {'name': 'filler', 'filter': 'FILLER', 'collection': 'Fillers', 'trakt_type': 'FILLER'},
            {'name': 'manga canon', 'filter': 'MANGA CANON', 'collection': 'Manga Canon', 'trakt_type': 'MANGA'},
            {'name': 'anime canon', 'filter': 'ANIME CANON', 'collection': 'Anime Canon', 'trakt_type': 'ANIME'},
            {'name': 'mixed canon/filler', 'filter': 'MIXED CANON/FILLER', 'collection': 'Mixed Canon/Filler', 'trakt_type': 'MIXED'}
        ]
        
        existing_anime_lists = {}
        for trakt_list in trakt_lists:
            list_name = trakt_list.get('name', '')
            if list_name.startswith(f"{anime_name}_"):
                parts = list_name.split('_', 1)
                if len(parts) == 2:
                    existing_anime_lists[parts[1]] = trakt_list['ids']['trakt']
        
        for episode_type in episode_types:
            anime_episodes = get_anime_episodes(anime_name, episode_type['filter'], silent=True)
            
            if anime_episodes and len(anime_episodes) > 0:
                if episode_type['name'] in existing_anime_lists:
                    list_id = existing_anime_lists[episode_type['name']]
                    logger.info(f"Updating existing {episode_type['name']} list for {anime_name}")

                    list_items_url = f"https://api.trakt.tv/users/{CONFIG['trakt']['username']}/lists/{list_id}/items"
                    response = requests.get(list_items_url, headers=headers)
                    existing_episodes = []
                    existing_trakt_ids = set()
                    
                    if response.status_code == 200:
                        existing_episodes = response.json()
                        for item in existing_episodes:
                            if item.get('type') == 'episode' and 'episode' in item:
                                trakt_id = item['episode'].get('ids', {}).get('trakt')
                                if trakt_id:
                                    existing_trakt_ids.add(trakt_id)
                    
                    success, has_failures, failure_info = add_episodes_to_trakt_list(
                        list_id,
                        anime_episodes,
                        access_token,
                        trakt_show_id,
                        match_by,
                        anime_name,
                        episode_type['trakt_type'],
                        existing_trakt_ids,
                        update_mode=True
                    )
                    
                    if success and not has_failures:
                        updated_existing_lists = True
                else:
                    logger.info(f"Creating new {episode_type['name']} list for {anime_name}")

                    trakt_list_name = get_list_name_format(anime_name, episode_type['trakt_type'])

                    list_id, list_exists = create_or_get_trakt_list(trakt_list_name, access_token)

                    if list_id:
                        success, has_failures, failure_info = add_episodes_to_trakt_list(
                            list_id,
                            anime_episodes,
                            access_token,
                            trakt_show_id,
                            match_by,
                            anime_name,
                            episode_type['trakt_type'],
                            set(),
                            update_mode=True
                        )
                        
                        if not list_exists:
                            logger.info(f"Created new list: {trakt_list_name}")
                            created_new_lists = True
    
    if created_new_lists or updated_existing_lists:
        logger.info("Lists were created or updated, synchronizing the collections file")
        from asset_manager import sync_anime_episode_collections
        sync_anime_episode_collections(CONFIG, force_update=True)
    
    return True

def check_for_new_episodes(anime_list, access_token, plex, silent=False):
    """Check if there are new episodes for this anime list without detailed logging."""
    try:
        episode_type_mapping = {
            'FILLER': 'FILLER',
            'MANGA CANON': 'MANGA CANON',
            'ANIME CANON': 'ANIME CANON',
            'MIXED CANON/FILLER': 'MIXED CANON/FILLER',
        }

        episode_type_filter = episode_type_mapping.get(anime_list['episode_type'])
        if not episode_type_filter:
            return False

        tmdb_id = get_tmdb_id_from_plex(plex, anime_list['anime_name'], silent=True)
        if not tmdb_id:
            return False

        headers = trakt_auth.get_trakt_headers(access_token)
        if not headers:
            return False

        trakt_api_url = 'https://api.trakt.tv'

        search_api_url = f'{trakt_api_url}/search/tmdb/{tmdb_id}?type=show'
        response = requests.get(search_api_url, headers=headers)
        if response.status_code != 200 or not response.json():
            return False

        trakt_show_id = response.json()[0]['show']['ids']['trakt']

        list_items_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists/{anime_list['list_id']}/items"
        response = requests.get(list_items_url, headers=headers)
        if response.status_code != 200:
            return False

        existing_count = len([i for i in response.json() if i.get('type') == 'episode'])

        anime_episodes = get_anime_episodes(anime_list['anime_name'], episode_type_filter, silent=True)
        if not anime_episodes:
            return False

        return len(anime_episodes) > existing_count

    except Exception:
        return False

def run_tv_status_update():
    """Run the TV/Anime Status Tracker service updates."""
    logger.info("Starting TV/Anime Status Tracker service updates")

    try:
        from tv_status_tracker import run_tv_status_tracker

        success = run_tv_status_tracker()

        if success:
            logger.info("TV/Anime Status Tracker update completed successfully")
        else:
            logger.error("TV/Anime Status Tracker update failed")

        return success
    except Exception as e:
        logger.error(f"Error running TV/Anime Status Tracker: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def run_update(services=None):
    """Main function to run the update process.

    Args:
        services (list, optional): List of service names to run.
                                   If None, runs all enabled services.
    """
    global CONFIG
    logger.info("Starting automatic update process")

    if not CONFIG:
        load_config()

    valid_services = ['anime_episode_type', 'tv_status_tracker', 'size_overlay']
    if services:
        if not all(service in valid_services for service in services):
            invalid_services = [s for s in services if s not in valid_services]
            logger.error(f"Invalid service(s) specified: {', '.join(invalid_services)}")
            logger.error(f"Valid services: {', '.join(valid_services)}")
            return
    else:
        services = []
        if CONFIG.get('services', {}).get('anime_episode_type', {}).get('enabled', True):
            services.append('anime_episode_type')
        if CONFIG.get('services', {}).get('tv_status_tracker', {}).get('enabled', False):
            services.append('tv_status_tracker')

    successful_updates = []

    if 'anime_episode_type' in services:
        if CONFIG.get('services', {}).get('anime_episode_type', {}).get('enabled', True):
            logger.info("Running Anime Episode Type service")
            match_by = CONFIG.get('services', {}).get('anime_episode_type', {}).get('match_by', 'hybrid')
            if run_anime_episode_update(match_by=match_by):
                successful_updates.append('anime_episode_type')
        else:
            logger.warning("Anime Episode Type service is disabled in config")

    if 'tv_status_tracker' in services:
        if CONFIG.get('services', {}).get('tv_status_tracker', {}).get('enabled', False):
            logger.info("Running TV/Anime Status Tracker service")
            if run_tv_status_update():
                successful_updates.append('tv_status_tracker')
        else:
            logger.warning("TV/Anime Status Tracker service is disabled in config")

    if 'size_overlay' in services:
        if CONFIG.get('services', {}).get('size_overlay', {}).get('enabled', False):
            logger.info("Running Size Overlay service")
            if run_size_overlay_update():
                successful_updates.append('size_overlay')
        else:
            logger.warning("Size Overlay service is disabled in config")

    with open(os.path.join(DATA_DIR, "last_update.txt"), "w") as f:
        f.write(datetime.now().isoformat())

    if successful_updates:
        logger.info(f"Update process complete. Successfully updated: {', '.join(successful_updates)}")
    else:
        logger.info("Update process complete. No updates were successful.")

    return len(successful_updates) > 0

def handle_mapping_failures():
    """Handle mapping failures for manual runs."""
    if os.environ.get('SCHEDULER_MODE') == 'true':
        return

    failed_log = os.path.join(DATA_DIR, "failed_episodes.log")
    if not os.path.exists(failed_log):
        return

    has_failures = False
    with open(failed_log, "r") as f:
        for line in f:
            if "Failed Episodes:" in line:
                try:
                    count = int(line.split(":", 1)[1].strip())
                    if count > 0:
                        has_failures = True
                        break
                except:
                    has_failures = True
                    break

    if has_failures:
        try:
            import click
            from rich.console import Console
            console = Console()

            console.print(f"[bold yellow]Found mapping failures in the error log[/bold yellow]")
            console.print("[yellow]Use 'docker compose run --rm dakosys fix-mappings' to resolve these issues[/yellow]")

            if click.confirm("Would you like to fix these mapping issues now?", default=True):
                from anime_trakt_manager import fix_mappings
                fix_mappings()
        except Exception as e:
            logger.error(f"Error offering fix-mappings: {str(e)}")

def run_size_overlay_update():
    """Run the Size Overlay service updates."""
    logger.info("Starting Size Overlay service updates")

    try:
        success = run_size_overlay_service()

        if success:
            logger.info("Size Overlay update completed successfully")
        else:
            logger.error("Size Overlay update failed")

        return success
    except Exception as e:
        logger.error(f"Error running Size Overlay service: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            services = sys.argv[1:]
            run_update(services)
        else:
            run_update()

        handle_mapping_failures()
    except KeyboardInterrupt:
        logger.info("Update process interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error in update process: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
