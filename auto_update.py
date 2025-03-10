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

# Import our authentication module
import trakt_auth

# Setup logging
DATA_DIR = "data"
if os.environ.get('RUNNING_IN_DOCKER') == 'true':
    DATA_DIR = "/app/data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Setup logger with rotation
if os.environ.get('RUNNING_IN_DOCKER') == 'true':
    data_dir = "/app/data"
else:
    data_dir = DATA_DIR

log_file = os.path.join(data_dir, "anime_trakt_manager.log")
logger = setup_rotating_logger("anime_trakt_manager", log_file)

# Global configuration
CONFIG = None
def load_config():
    """Load configuration from YAML file."""
    global CONFIG
    CONFIG = trakt_auth.load_config()

    # Load mappings from mappings.yaml and add them to CONFIG
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

# Initialize CONFIG when module is loaded
load_config()

def normalize_episode_title(title):
    """Normalize episode title for better matching."""
    # Remove punctuation and convert to lowercase
    title = re.sub(r'[^\w\s]', ' ', title).lower()

    # Replace "part X" with "(X)" and vice versa
    title = re.sub(r'part\s+(\d+)', r'\1', title)
    title = re.sub(r'\((\d+)\)', r'\1', title)

    # Remove episode numbers like "1x22" or "(22)"
    title = re.sub(r'\d+x\d+\s*', '', title)
    title = re.sub(r'\(\d+\)\s*', '', title)

    # Handle other common replacements
    replacements = {
        'episode': '',
        'ep': '',
        'the': '',
        'and': '',
    }

    for orig, repl in replacements.items():
        title = re.sub(r'\b' + orig + r'\b', repl, title)

    # Remove extra spaces
    title = re.sub(r'\s+', ' ', title).strip()

    return title

def get_all_trakt_lists(access_token=None):
    """Get all Trakt lists for the user."""
    # Use the trakt_auth module's helper
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

    # Get scheduled anime list from config
    scheduled_anime = config.get('scheduler', {}).get('scheduled_anime', [])
    logger.info(f"Scheduled anime: {scheduled_anime}")

    for trakt_list in trakt_lists:
        name = trakt_list['name']
        # Our lists follow the format: anime_name_type
        if '_' in name and any(name.endswith(f"_{suffix}") for suffix in ['filler', 'manga canon', 'anime canon', 'mixed canon/filler']):
            anime_name, episode_type = name.rsplit('_', 1)

            # Only include if this anime is in the scheduled list
            if scheduled_anime and anime_name not in scheduled_anime:
                # Skip without logging each one
                continue

            anime_lists.append({
                'list_id': trakt_list['ids']['trakt'],
                'name': name,
                'anime_name': anime_name,
                'episode_type': episode_type.upper()
            })

    # Add a summary log for skipped lists
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

    # Get config for the mappings
    config = trakt_auth.load_config()

    # Get from mappings if available
    plex_name = config.get('mappings', {}).get(afl_name, None)
    
    # If not found in config, try mappings_manager
    if plex_name is None:
        try:
            mappings_data = mappings_manager.load_mappings()
            plex_name = mappings_data.get('mappings', {}).get(afl_name, afl_name)
        except Exception as e:
            logger.warning(f"Error loading from mappings_manager: {str(e)}")
            plex_name = afl_name

    # If still in AFL format, convert to display format
    if '-' in plex_name:
        plex_name = plex_name.replace('-', ' ').title()

    return plex_name

def get_anime_episodes(anime_name, episode_type_filter=None, silent=False):
    """Get episodes from AnimeFillerList website."""
    # Handle the case where CONFIG might be None in scheduler mode
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

        # Safe configuration access - work even when CONFIG is None
        config_data = CONFIG
        if config_data is None:
            try:
                # Try to reload configuration
                config_data = trakt_auth.load_config() or {}
            except Exception as e:
                logger.warning(f"Failed to load config in get_anime_episodes: {str(e)}")
                config_data = {}
        
        # Safe nested access
        title_mappings = config_data.get('title_mappings', {}) or {}
        anime_mapping = title_mappings.get(anime_name, {}) or {}

        for row in soup.find_all('tr'):
            columns = row.find_all('td')
            if len(columns) >= 3:
                episode_number = columns[0].text.strip()
                episode_name = columns[1].text.strip()
                episode_type = columns[2].text.strip()

                # Apply title mappings if configured
                if anime_mapping:
                    # Apply remove patterns
                    remove_patterns = anime_mapping.get('remove_patterns', []) or []
                    for pattern in remove_patterns:
                        if isinstance(pattern, str):
                            episode_name = episode_name.replace(pattern, '').strip()

                    # Remove specific numbers
                    remove_numbers = anime_mapping.get('remove_numbers', []) or []
                    for number in remove_numbers:
                        try:
                            if isinstance(number, int):
                                episode_name = episode_name.replace(f'{number:02d}', '').strip()
                        except:
                            pass

                    # Remove dashes if configured
                    if anime_mapping.get('remove_dashes', False):
                        episode_name = episode_name.replace('-', '').strip()

                    # Apply special matches
                    special_matches = anime_mapping.get('special_matches', {}) or {}
                    special_match = special_matches.get(episode_name)
                    if special_match:
                        episode_name = special_match

                # Filter by episode type if specified
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
        # Include traceback for better debugging
        import traceback
        logger.error(traceback.format_exc())
        return []

def get_tmdb_id_from_plex(plex, anime_name, silent=False):
    """Get TMDB ID for a show from Plex."""
    try:
        config = trakt_auth.load_config()

        # Get the anime library
        anime_library = plex.library.section(config['plex']['library'])

        # Get the mapped Plex show name - try config first
        mapped_anime_name = config.get('mappings', {}).get(anime_name.lower(), None)
        
        # If not found in config, try mappings_manager
        if mapped_anime_name is None:
            try:
                mappings_data = mappings_manager.load_mappings()
                mapped_anime_name = mappings_data.get('mappings', {}).get(anime_name.lower(), anime_name)
            except Exception as e:
                logger.warning(f"Error loading from mappings_manager: {str(e)}")
                mapped_anime_name = anime_name

        if not silent:
            logger.info(f"Looking for '{mapped_anime_name}' in Plex library")

        # Search for the show in Plex
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

    # Map episode type
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
    # Get TMDB ID
    tmdb_id = get_tmdb_id_from_plex(plex, anime_list['anime_name'])
    if not tmdb_id:
        logger.error(f"Could not find TMDB ID for {anime_list['anime_name']}")
        return False

    # Define Trakt API URL
    trakt_api_url = 'https://api.trakt.tv'

    # Get Trakt show ID
    headers = trakt_auth.get_trakt_headers(access_token)
    search_api_url = f'{trakt_api_url}/search/tmdb/{tmdb_id}?type=show'
    response = requests.get(search_api_url, headers=headers)

    if response.status_code != 200 or not response.json():
        logger.error(f"Failed to get Trakt show ID for {anime_list['anime_name']}")
        return False

    trakt_show_id = response.json()[0]['show']['ids']['trakt']

    # Get all episodes from AnimeFillerList
    anime_episodes = get_anime_episodes(anime_list['anime_name'], episode_type_filter)
    if not anime_episodes:
        logger.error(f"No episodes found on AnimeFillerList for {anime_list['anime_name']}")
        return False

    # Get existing episodes in Trakt list
    list_items_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists/{anime_list['list_id']}/items"
    response = requests.get(list_items_url, headers=headers)
    if response.status_code != 200:
        logger.error("Failed to get existing episodes")
        return False

    existing_episodes = response.json()
    existing_count = len([i for i in existing_episodes if i.get('type') == 'episode'])

    # Compare counts to see if there are new episodes
    if len(anime_episodes) <= existing_count:
        logger.info(f"No new episodes found for {anime_list['name']}")
        return False

    logger.info(f"Found {len(anime_episodes)} episodes on AnimeFillerList")
    logger.info(f"Found {existing_count} episodes in existing list")
    logger.info(f"Found {len(anime_episodes) - existing_count} new episodes to add")

    # Extract existing trakt_ids for the add_episodes_to_trakt_list function
    existing_trakt_ids = set()
    for item in existing_episodes:
        if item.get('type') == 'episode' and 'episode' in item:
            trakt_id = item['episode'].get('ids', {}).get('trakt')
            if trakt_id:
                existing_trakt_ids.add(trakt_id)
    
    # IMPORTANT: Use the working function from anime_trakt_manager to add episodes
    from anime_trakt_manager import add_episodes_to_trakt_list
    
    # Normalize the episode type to match the manual run format ('manga' instead of 'manga canon')
    normalized_type = anime_list['episode_type'].lower()
    if "manga canon" in normalized_type:
        normalized_type = "manga"
    elif "anime canon" in normalized_type:
        normalized_type = "anime"
    elif "mixed canon/filler" in normalized_type:
        normalized_type = "mixed"
    elif normalized_type == "filler":
        normalized_type = "filler"
    
    # Call the function with update_mode=False to get proper notifications
    success, has_failures, failure_info = add_episodes_to_trakt_list(
        anime_list['list_id'],
        anime_episodes,
        access_token,
        trakt_show_id,
        match_by,
        anime_name,
        normalized_type,  # Use normalized type that matches manual run
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
    
    from anime_trakt_manager import clear_error_log, add_episodes_to_trakt_list, create_or_get_trakt_list, get_list_name_format
    clear_error_log()
    
    # Get Trakt access token
    access_token = trakt_auth.ensure_trakt_auth(quiet=True)
    if not access_token:
        logger.error("No Trakt access token found")
        return False
    
    # Connect to Plex
    plex = connect_to_plex()
    if not plex:
        logger.error("Failed to connect to Plex server")
        return False
    
    # Get all anime from the scheduler config
    scheduled_anime = CONFIG.get('scheduler', {}).get('scheduled_anime', [])
    if not scheduled_anime:
        logger.info("No anime scheduled for updates")
        return False
    
    # Get all existing Trakt lists
    trakt_lists = get_all_trakt_lists(access_token)
    if not trakt_lists:
        logger.error("Failed to get Trakt lists")
        return False
    
    # Track any changes to trigger collection sync
    created_new_lists = False
    updated_existing_lists = False
    
    # For each scheduled anime, check all episode types
    for anime_name in scheduled_anime:
        logger.info(f"Checking {anime_name} for updates")
        plex_name = get_plex_name(anime_name)
        
        # Get TMDB ID and Trakt show ID
        tmdb_id = get_tmdb_id_from_plex(plex, anime_name, silent=True)
        if not tmdb_id:
            logger.error(f"Could not find TMDB ID for {anime_name} (Plex: {plex_name})")
            continue
        
        # Get Trakt show ID
        headers = trakt_auth.get_trakt_headers(access_token)
        search_api_url = f'https://api.trakt.tv/search/tmdb/{tmdb_id}?type=show'
        response = requests.get(search_api_url, headers=headers)
        
        if response.status_code != 200 or not response.json():
            logger.error(f"Failed to get Trakt show ID for {anime_name} (Plex: {plex_name})")
            continue
        
        trakt_show_id = response.json()[0]['show']['ids']['trakt']
        
        # Check each episode type
        episode_types = [
            {'name': 'filler', 'filter': 'FILLER', 'collection': 'Fillers', 'trakt_type': 'FILLER'},
            {'name': 'manga canon', 'filter': 'MANGA CANON', 'collection': 'Manga Canon', 'trakt_type': 'MANGA'},
            {'name': 'anime canon', 'filter': 'ANIME CANON', 'collection': 'Anime Canon', 'trakt_type': 'ANIME'},
            {'name': 'mixed canon/filler', 'filter': 'MIXED CANON/FILLER', 'collection': 'Mixed Canon/Filler', 'trakt_type': 'MIXED'}
        ]
        
        # Get existing lists for this anime
        existing_anime_lists = {}
        for trakt_list in trakt_lists:
            list_name = trakt_list.get('name', '')
            if list_name.startswith(f"{anime_name}_"):
                parts = list_name.split('_', 1)
                if len(parts) == 2:
                    existing_anime_lists[parts[1]] = trakt_list['ids']['trakt']
        
        for episode_type in episode_types:
            # Check if episodes of this type exist
            anime_episodes = get_anime_episodes(anime_name, episode_type['filter'], silent=True)
            
            if anime_episodes and len(anime_episodes) > 0:
                # Check if we already have a list for this type
                if episode_type['name'] in existing_anime_lists:
                    # List exists, just update it
                    list_id = existing_anime_lists[episode_type['name']]
                    logger.info(f"Updating existing {episode_type['name']} list for {anime_name}")
                    
                    # Get existing episodes
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
                    
                    # Add episodes to the list
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
                    # List doesn't exist, create it
                    logger.info(f"Creating new {episode_type['name']} list for {anime_name}")
                    
                    # Create the list using the proper list name format
                    trakt_list_name = get_list_name_format(anime_name, episode_type['trakt_type'])
                    
                    # Use create_or_get_trakt_list function
                    list_id, list_exists = create_or_get_trakt_list(trakt_list_name, access_token)
                    
                    if list_id:
                        # Add episodes to the new list
                        success, has_failures, failure_info = add_episodes_to_trakt_list(
                            list_id,
                            anime_episodes,
                            access_token,
                            trakt_show_id,
                            match_by,
                            anime_name,
                            episode_type['trakt_type'],
                            set(),  # No existing episodes
                            update_mode=True
                        )
                        
                        # Mark that we created a new list
                        if not list_exists:  # Only if we actually created a new list
                            logger.info(f"Created new list: {trakt_list_name}")
                            created_new_lists = True
    
    # Sync the collections file if we created any new lists or had significant updates
    if created_new_lists or updated_existing_lists:
        logger.info("Lists were created or updated, synchronizing the collections file")
        # Import here to avoid circular imports
        from asset_manager import sync_anime_episode_collections
        sync_anime_episode_collections(CONFIG, force_update=True)
    
    return True

def check_for_new_episodes(anime_list, access_token, plex, silent=False):
    """Check if there are new episodes for this anime list without detailed logging."""
    try:
        # Map episode type
        episode_type_mapping = {
            'FILLER': 'FILLER',
            'MANGA CANON': 'MANGA CANON',
            'ANIME CANON': 'ANIME CANON',
            'MIXED CANON/FILLER': 'MIXED CANON/FILLER',
        }

        episode_type_filter = episode_type_mapping.get(anime_list['episode_type'])
        if not episode_type_filter:
            return False

        # Quick check of episode counts
        tmdb_id = get_tmdb_id_from_plex(plex, anime_list['anime_name'], silent=True)
        if not tmdb_id:
            return False

        headers = trakt_auth.get_trakt_headers(access_token)
        if not headers:
            return False

        trakt_api_url = 'https://api.trakt.tv'

        # Get show ID
        search_api_url = f'{trakt_api_url}/search/tmdb/{tmdb_id}?type=show'
        response = requests.get(search_api_url, headers=headers)
        if response.status_code != 200 or not response.json():
            return False

        trakt_show_id = response.json()[0]['show']['ids']['trakt']

        # Get list episodes
        list_items_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists/{anime_list['list_id']}/items"
        response = requests.get(list_items_url, headers=headers)
        if response.status_code != 200:
            return False

        existing_count = len([i for i in response.json() if i.get('type') == 'episode'])

        # Get AFL episodes
        anime_episodes = get_anime_episodes(anime_list['anime_name'], episode_type_filter, silent=True)
        if not anime_episodes:
            return False

        # Return True if there are new episodes
        return len(anime_episodes) > existing_count

    except Exception:
        # On any error, return False - we'll catch it in the main update
        return False

def run_tv_status_update():
    """Run the TV/Anime Status Tracker service updates."""
    logger.info("Starting TV/Anime Status Tracker service updates")

    try:
        # Import the TV Status Tracker module
        from tv_status_tracker import run_tv_status_tracker

        # Run the TV Status Tracker
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

    # If specific services are requested, validate them
    valid_services = ['anime_episode_type', 'tv_status_tracker', 'size_overlay']
    if services:
        if not all(service in valid_services for service in services):
            invalid_services = [s for s in services if s not in valid_services]
            logger.error(f"Invalid service(s) specified: {', '.join(invalid_services)}")
            logger.error(f"Valid services: {', '.join(valid_services)}")
            return
    else:
        # If no specific services requested, run all enabled services
        services = []
        if CONFIG.get('services', {}).get('anime_episode_type', {}).get('enabled', True):
            services.append('anime_episode_type')
        if CONFIG.get('services', {}).get('tv_status_tracker', {}).get('enabled', False):
            services.append('tv_status_tracker')

    # Track successful updates
    successful_updates = []

    # Run Anime Episode Type service if requested
    if 'anime_episode_type' in services:
        if CONFIG.get('services', {}).get('anime_episode_type', {}).get('enabled', True):
            logger.info("Running Anime Episode Type service")
            # Use hybrid matching by default
            match_by = CONFIG.get('services', {}).get('anime_episode_type', {}).get('match_by', 'hybrid')
            if run_anime_episode_update(match_by=match_by):
                successful_updates.append('anime_episode_type')
        else:
            logger.warning("Anime Episode Type service is disabled in config")

    # Run TV/Anime Status Tracker service if requested
    if 'tv_status_tracker' in services:
        if CONFIG.get('services', {}).get('tv_status_tracker', {}).get('enabled', False):
            logger.info("Running TV/Anime Status Tracker service")
            if run_tv_status_update():
                successful_updates.append('tv_status_tracker')
        else:
            logger.warning("TV/Anime Status Tracker service is disabled in config")

    # Run Size Overlay service if requested
    if 'size_overlay' in services:
        if CONFIG.get('services', {}).get('size_overlay', {}).get('enabled', False):
            logger.info("Running Size Overlay service")
            if run_size_overlay_update():
                successful_updates.append('size_overlay')
        else:
            logger.warning("Size Overlay service is disabled in config")

    # Save the last update time
    with open(os.path.join(DATA_DIR, "last_update.txt"), "w") as f:
        f.write(datetime.now().isoformat())

    # Provide a summary
    if successful_updates:
        logger.info(f"Update process complete. Successfully updated: {', '.join(successful_updates)}")
    else:
        logger.info("Update process complete. No updates were successful.")

    return len(successful_updates) > 0

# For manual runs, offer to fix mapping issues
def handle_mapping_failures():
    """Handle mapping failures for manual runs."""
    # Only run this for manual invocations, not from the scheduler
    if os.environ.get('SCHEDULER_MODE') == 'true':
        return

    # Check if we have a failed episodes log
    failed_log = os.path.join(DATA_DIR, "failed_episodes.log")
    if not os.path.exists(failed_log):
        return

    # Check if the log has any failures
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
                    # If we can't parse, assume there are failures
                    has_failures = True
                    break

    if has_failures:
        # Import necessary modules here to avoid circular imports
        try:
            import click
            from rich.console import Console
            console = Console()

            console.print(f"[bold yellow]Found mapping failures in the error log[/bold yellow]")
            console.print("[yellow]Use 'docker compose run --rm dakosys fix-mappings' to resolve these issues[/yellow]")

            # If click is available, offer to run fix-mappings now
            if click.confirm("Would you like to fix these mapping issues now?", default=True):
                # Import and run fix_mappings
                from anime_trakt_manager import fix_mappings
                fix_mappings()
        except Exception as e:
            logger.error(f"Error offering fix-mappings: {str(e)}")

def run_size_overlay_update():
    """Run the Size Overlay service updates."""
    logger.info("Starting Size Overlay service updates")

    try:
        # Import the Size Overlay module
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
        # Check if specific services were requested
        if len(sys.argv) > 1:
            services = sys.argv[1:]
            run_update(services)
        else:
            run_update()

        # Handle mapping failures for manual runs
        handle_mapping_failures()
    except KeyboardInterrupt:
        logger.info("Update process interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error in update process: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
