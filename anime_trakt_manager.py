#!/usr/bin/env python3
"""
Anime Trakt List Manager

A tool for creating and managing Trakt.tv lists of anime episodes
based on episode types (filler, manga, anime, mixed) from AnimeFillerList.
"""

import os
import sys
import time
import re
import yaml
import json
import click
import difflib
import logging
import requests
from bs4 import BeautifulSoup
from plexapi.server import PlexServer
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from shared_utils import setup_rotating_logger

import trakt_auth
console = Console()

CONFIG = {}
DATA_DIR = "data"
CONFIG_FILE = "config/config.yaml"

if os.environ.get('RUNNING_IN_DOCKER') == 'true':
    data_dir = "/app/data"
else:
    data_dir = DATA_DIR

log_file = os.path.join(data_dir, "anime_trakt_manager.log")
logger = setup_rotating_logger("anime_trakt_manager", log_file)

try:
    import notifications
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False
    logger.warning("Notifications module not available")

def load_config():
    """Load configuration from YAML file."""
    global CONFIG

    setup_mode = 'setup' in sys.argv

    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        config_path = "/app/config/config.yaml"
        data_dir = "/app/data"
    else:
        config_path = CONFIG_FILE
        data_dir = DATA_DIR

    try:
        if not os.path.exists(config_path):
            if setup_mode:
                CONFIG = {}
                if not os.path.exists(os.path.dirname(config_path)):
                    os.makedirs(os.path.dirname(config_path))
                if not os.path.exists(data_dir):
                    os.makedirs(data_dir)
                return True
            else:
                console.print(f"[bold red]Configuration file not found at {config_path}[/bold red]")
                console.print(f"[yellow]Please run 'setup' command first to create a configuration file.[/yellow]")
                console.print(f"[yellow]Example: docker compose run --rm dakosys setup[/yellow]")
                return False

        with open(config_path, 'r') as file:
            CONFIG = yaml.safe_load(file)

        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        try:
            import mappings_manager
            all_mappings = mappings_manager.load_mappings()
            
            if 'mappings' in all_mappings:
                CONFIG['mappings'] = all_mappings['mappings']
            if 'trakt_mappings' in all_mappings:
                CONFIG['trakt_mappings'] = all_mappings['trakt_mappings']
            if 'title_mappings' in all_mappings:
                CONFIG['title_mappings'] = all_mappings['title_mappings']
                
        except Exception as e:
            logger.warning(f"Could not load mappings from mappings.yaml: {str(e)}")

        return True
    except Exception as e:
        console.print(f"[bold red]Error loading configuration: {str(e)}[/bold red]")
        return False

def reload_config():
    """Reload configuration from disk to get the latest mappings."""
    global CONFIG
    config_path = "/app/config/config.yaml" if os.environ.get('RUNNING_IN_DOCKER') == 'true' else CONFIG_FILE
    try:
        with open(config_path, 'r') as file:
            CONFIG = yaml.safe_load(file)
            
        try:
            import mappings_manager
            all_mappings = mappings_manager.load_mappings()
            
            if 'mappings' in all_mappings:
                CONFIG['mappings'] = all_mappings['mappings']
            if 'trakt_mappings' in all_mappings:
                CONFIG['trakt_mappings'] = all_mappings['trakt_mappings']
            if 'title_mappings' in all_mappings:
                CONFIG['title_mappings'] = all_mappings['title_mappings']
                
        except Exception as e:
            logger.warning(f"Could not load mappings from mappings.yaml: {str(e)}")
            
        console.print("[green]Reloaded configuration with updated mappings.[/green]")
        return True
    except Exception as e:
        console.print(f"[yellow]Warning: Could not reload config: {str(e)}[/yellow]")
        return False

def connect_to_plex():
    """Connect to Plex server."""
    try:
        console.print("[bold blue]Connecting to Plex server...[/bold blue]")
        plex = PlexServer(CONFIG['plex']['url'], CONFIG['plex']['token'])
        console.print("[bold green]Connected to Plex server successfully![/bold green]")
        return plex
    except Exception as e:
        console.print(f"[bold red]Failed to connect to Plex server: {str(e)}[/bold red]")
        console.print("[yellow]Please check your Plex URL and token in the configuration file.[/yellow]")
        return None

def get_anime_libraries(plex):
    """Get all anime libraries configured in DAKOSYS."""
    libraries = []

    for library_name in CONFIG.get('plex', {}).get('libraries', {}).get('anime', []):
        try:
            libraries.append(plex.library.section(library_name))
        except Exception as e:
            logger.error(f"Error accessing library {library_name}: {str(e)}")


    return libraries

def get_tmdb_id_from_plex(plex, anime_name):
    """Get TMDB ID for a show from Plex."""
    try:
        mapped_anime_name = CONFIG.get('mappings', {}).get(anime_name.lower(), anime_name)

        console.print(f"[blue]Looking for '{mapped_anime_name}' in Plex libraries...[/blue]")

        libraries = get_anime_libraries(plex)
        for anime_library in libraries:
            for show in anime_library.all():
                if show.title.lower() == mapped_anime_name.lower():
                    for guid in show.guids:
                        if 'tmdb://' in guid.id:
                            tmdb_id = guid.id.split('//')[1]
                            console.print(f"[green]Found TMDB ID: {tmdb_id}[/green]")
                            return tmdb_id

        console.print(f"[yellow]Could not find TMDB ID for '{mapped_anime_name}' in any Plex library.[/yellow]")
        return None
    except Exception as e:
        console.print(f"[bold red]Error getting TMDB ID: {str(e)}[/bold red]")
        return None

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
            if trakt_auth:
                config_data = trakt_auth.load_config() or {}
            else:
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
                        episode_name = episode_name.replace(pattern, '').strip()

                    remove_numbers = anime_mapping.get('remove_numbers', []) or []
                    for number in remove_numbers:
                        try:
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
        return []

def get_trakt_show_id(access_token, tmdb_id):
    """Get Trakt show ID using TMDB ID."""
    try:
        headers = trakt_auth.get_trakt_headers(access_token)
        if not headers:
            console.print("[bold red]Failed to get Trakt API headers[/bold red]")
            return None

        trakt_api_url = 'https://api.trakt.tv'
        search_api_url = f'{trakt_api_url}/search/tmdb/{tmdb_id}?type=show'
        response = requests.get(search_api_url, headers=headers)

        if response.status_code == 200:
            show_results = response.json()
            if show_results:
                trakt_show_id = show_results[0]['show']['ids']['trakt']
                console.print(f"[green]Found Trakt show ID: {trakt_show_id}[/green]")
                return trakt_show_id
        else:
            console.print(f"[bold red]Failed to search on Trakt using TMDB ID. Status Code: {response.status_code}[/bold red]")
            console.print(f"[yellow]Response: {response.text}[/yellow]")

        return None
    except Exception as e:
        console.print(f"[bold red]Error getting Trakt show ID: {str(e)}[/bold red]")
        return None

def get_plex_name(afl_name):
    """Convert AnimeFillerList name to user-friendly Plex name.

    Args:
        afl_name: AnimeFillerList name (e.g., 'attack-titan')

    Returns:
        User-friendly Plex name (e.g., 'Attack on Titan')
    """
    if not afl_name or afl_name == "unknown":
        return "Unknown Anime"

    plex_name = CONFIG.get('mappings', {}).get(afl_name, afl_name)

    if '-' in plex_name:
        plex_name = plex_name.replace('-', ' ').title()

    return plex_name

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

def handle_special_anime_titles(anime_name, episode):
    """Apply special handling for specific anime titles that have unique formatting.

    Returns the modified episode dict.
    """
    modified_episode = episode.copy()

    if anime_name and anime_name.lower() in ['code-geass', 'code-geass-lelouch-of-the-rebellion']:
        episode_title = episode['name']

        if (episode_title.startswith('Stage ') or episode_title.startswith('Turn ') or
            episode_title.startswith('Final Turn')) and ' - ' in episode_title:
            pure_title = episode_title.split(' - ', 1)[1].strip()
            modified_episode['name'] = pure_title
            logger.info(f"Code Geass special handling: '{episode_title}' → '{pure_title}'")

    return modified_episode

def get_trakt_season_and_episode_by_number(trakt_show_id, episode_number_abs, access_token):
    """Get Trakt season and episode numbers using absolute episode number."""
    try:
        headers = trakt_auth.get_trakt_headers(access_token)
        if not headers:
            return None, None

        trakt_api_url = 'https://api.trakt.tv'
        trakt_seasons_url = f'{trakt_api_url}/shows/{trakt_show_id}/seasons?extended=episodes,full'
        response = requests.get(trakt_seasons_url, headers=headers)

        if response.status_code == 200:
            seasons_info = response.json()

            for season_info in seasons_info:
                for episode_info in season_info.get('episodes', []):
                    if episode_info.get('number_abs') == int(episode_number_abs):
                        trakt_season = season_info.get('number')
                        trakt_episode = episode_info.get('number')
                        return trakt_season, trakt_episode

            console.print(f"[yellow]Episode number_abs '{episode_number_abs}' not found in any season.[/yellow]")
            return None, None
        else:
            console.print(f"[bold red]Failed to get Trakt seasons information. Status Code: {response.status_code}[/bold red]")
            return None, None
    except Exception as e:
        console.print(f"[bold red]Error getting season info: {str(e)}[/bold red]")
        return None, None

def get_trakt_season_and_episode_by_title(trakt_show_id, episode_title, access_token):
    """Get Trakt season and episode numbers using episode title."""
    try:
        headers = trakt_auth.get_trakt_headers(access_token)
        if not headers:
            return None, None

        trakt_api_url = 'https://api.trakt.tv'
        normalized_title = normalize_episode_title(episode_title)

        logger.info(f"Looking for episode: '{episode_title}' (normalized: '{normalized_title}')")

        trakt_seasons_url = f'{trakt_api_url}/shows/{trakt_show_id}/seasons?extended=episodes'
        response = requests.get(trakt_seasons_url, headers=headers)

        if response.status_code == 200:
            seasons_info = response.json()

            best_match = None
            best_score = 0
            best_season = None
            best_episode = None

            for season_info in seasons_info:
                for episode_info in season_info.get('episodes', []):
                    trakt_title = episode_info.get('title', '')
                    normalized_trakt_title = normalize_episode_title(trakt_title)

                    if normalized_trakt_title == normalized_title:
                        return season_info.get('number'), episode_info.get('number')

                    similarity = difflib.SequenceMatcher(None, normalized_title, normalized_trakt_title).ratio()
                    if similarity > 0.7 and similarity > best_score:
                        best_score = similarity
                        best_match = trakt_title
                        best_season = season_info.get('number')
                        best_episode = episode_info.get('number')

            if best_match and best_score > 0.7:
                logger.info(f"Fuzzy matched '{episode_title}' to '{best_match}' (score: {best_score:.2f})")
                return best_season, best_episode

            logger.warning(f"Episode title '{episode_title}' not found in any season. Closest match: '{best_match}' (score: {best_score:.2f})")
            console.print(f"[yellow]Episode title '{episode_title}' not found. Closest match: '{best_match}' (similarity: {best_score*100:.0f}%)[/yellow]")

            return None, None
        else:
            console.print(f"[bold red]Failed to get Trakt seasons information. Status Code: {response.status_code}[/bold red]")
            return None, None
    except Exception as e:
        console.print(f"[bold red]Error getting season info by title: {str(e)}[/bold red]")
        return None, None

def get_trakt_episode_id(trakt_show_id, trakt_season, trakt_episode, access_token):
    """Get Trakt episode ID."""
    try:
        headers = trakt_auth.get_trakt_headers(access_token)
        if not headers:
            return None

        trakt_api_url = 'https://api.trakt.tv'
        trakt_season_url = f'{trakt_api_url}/shows/{trakt_show_id}/seasons/{trakt_season}?extended=episodes'
        response = requests.get(trakt_season_url, headers=headers)

        if response.status_code == 200:
            season_info = response.json()

            if isinstance(season_info, list):
                episodes_info = season_info
            else:
                episodes_info = season_info.get('episodes', [])

            episode_info = next((ep for ep in episodes_info if ep.get('number') == trakt_episode), None)

            if episode_info:
                trakt_episode_id = episode_info.get('ids', {}).get('trakt')
                return trakt_episode_id
            else:
                console.print(f"[yellow]Episode {trakt_episode} not found in season {trakt_season}.[/yellow]")
                return None
        else:
            console.print(f"[bold red]Failed to get Trakt season information. Status Code: {response.status_code}[/bold red]")
            return None
    except Exception as e:
        console.print(f"[bold red]Error getting episode ID: {str(e)}[/bold red]")
        return None

def create_or_get_trakt_list(list_name, access_token):
    """Create a new Trakt list or get existing one."""
    try:
        headers = trakt_auth.get_trakt_headers(access_token)
        if not headers:
            return None, False

        trakt_api_url = 'https://api.trakt.tv'
        list_search_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists"
        response = requests.get(list_search_url, headers=headers)

        if response.status_code == 200:
            existing_lists = response.json()
            existing_list = next((lst for lst in existing_lists if lst['name'] == list_name), None)

            if existing_list:
                list_id = existing_list['ids']['trakt']
                console.print(f"[blue]Trakt list '{list_name}' already exists with ID {list_id}.[/blue]")
                return list_id, True
            else:
                create_list_payload = {
                    'name': list_name,
                    'description': f'List for {list_name}',
                    'privacy': CONFIG.get('lists', {}).get('default_privacy', 'private'),
                }

                create_list_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists"
                response = requests.post(create_list_url, headers=headers, json=create_list_payload)

                if response.status_code == 201:
                    list_id = response.json().get('ids', {}).get('trakt')
                    console.print(f"[green]Trakt list '{list_name}' created successfully with ID {list_id}.[/green]")
                    return list_id, False
                else:
                    console.print(f"[bold red]Failed to create Trakt list. Status Code: {response.status_code}[/bold red]")
                    console.print(f"[yellow]Response: {response.text}[/yellow]")
                    return None, False
        else:
            console.print(f"[bold red]Failed to search for Trakt lists. Status Code: {response.status_code}[/bold red]")
            return None, False
    except Exception as e:
        console.print(f"[bold red]Error creating/getting list: {str(e)}[/bold red]")
        return None, False

def get_list_name_format(afl_name, episode_type):
    """Get proper list name format matching the original script."""
    episode_type_mapping = {
        'FILLER': 'filler',
        'MANGA': 'manga canon',
        'ANIME': 'anime canon',
        'MIXED': 'mixed canon/filler',
    }

    type_label = episode_type_mapping.get(episode_type.upper(), episode_type.lower())
    return f'{afl_name}_{type_label}'

def get_existing_episodes_in_trakt_list(list_id, access_token):
    """Get existing episodes in a Trakt list."""
    try:
        headers = trakt_auth.get_trakt_headers(access_token)
        if not headers:
            return []

        trakt_api_url = 'https://api.trakt.tv'
        list_items_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists/{list_id}/items"
        response = requests.get(list_items_url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            console.print(f"[bold red]Failed to get existing episodes in Trakt list. Status Code: {response.status_code}[/bold red]")
            return []
    except Exception as e:
        console.print(f"[bold red]Error getting list episodes: {str(e)}[/bold red]")
        return []

def add_episodes_to_trakt_list(list_id, episodes, access_token, trakt_show_id, match_by="hybrid", anime_name=None, episode_type=None, existing_trakt_ids=None, update_mode=False):
    """Add episodes to a Trakt list with optimized API usage.

    This implementation minimizes API calls by:
    1. Getting all seasons/episodes in one API call
    2. Getting all existing list episodes in one API call
    3. Adding episodes in batches
    4. Handling rate limits with proper retries
    """
    import os

    try:
        config_data = None
        trakt_username = None
        notifications_enabled = False

        try:
            if 'CONFIG' in globals() and globals()['CONFIG'] is not None:
                config_data = globals()['CONFIG']

            if (not config_data or not config_data.get('trakt')) and 'trakt_auth' in globals() and hasattr(trakt_auth, 'load_config'):
                config_data = trakt_auth.load_config()

            if not config_data or not config_data.get('trakt'):
                import yaml
                config_path = "/app/config/config.yaml" if os.environ.get('RUNNING_IN_DOCKER') == 'true' else "config/config.yaml"
                if os.path.exists(config_path):
                    with open(config_path, 'r') as file:
                        config_data = yaml.safe_load(file)
                        logger.info(f"Loaded configuration directly from {config_path}")

            if config_data and isinstance(config_data, dict):
                trakt_config = config_data.get('trakt', {})
                if isinstance(trakt_config, dict):
                    trakt_username = trakt_config.get('username')

                notifications_config = config_data.get('notifications', {})
                if isinstance(notifications_config, dict):
                    notifications_enabled = notifications_config.get('enabled', False)

            if trakt_username:
                logger.info(f"Using Trakt username: {trakt_username}")

        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

        if not trakt_username:
            logger.error("Trakt username not found in config - cannot proceed without it")
            console.print("[bold red]ERROR: Trakt username not found in configuration[/bold red]")
            console.print("[yellow]Please ensure your config.yaml has a valid trakt.username setting[/yellow]")
            return False, False, None

        headers = trakt_auth.get_trakt_headers(access_token)
        if not headers:
            return False, False, None

        trakt_api_url = 'https://api.trakt.tv'

        if existing_trakt_ids is None:
            logger.info(f"Getting existing episodes in list {list_id}")
            list_items_url = f"{trakt_api_url}/users/{trakt_username}/lists/{list_id}/items"
            response = requests.get(list_items_url, headers=headers)

            if response.status_code != 200:
                console.print(f"[bold red]Failed to get list items. Status: {response.status_code}[/bold red]")
                return False, False, None

            existing_episodes = response.json()

            existing_trakt_ids = set()
            for item in existing_episodes:
                if item.get('type') == 'episode' and 'episode' in item:
                    trakt_id = item['episode'].get('ids', {}).get('trakt')
                    if trakt_id:
                        existing_trakt_ids.add(trakt_id)

            logger.info(f"Found {len(existing_trakt_ids)} existing episodes in list")

        # Step 2: Get all seasons data for this show (one API call)
        logger.info(f"Getting all seasons data for show {trakt_show_id}")
        trakt_seasons_url = f'{trakt_api_url}/shows/{trakt_show_id}/seasons?extended=episodes,full'
        response = requests.get(trakt_seasons_url, headers=headers)

        if response.status_code != 200:
            console.print(f"[bold red]Failed to get seasons data. Status: {response.status_code}[/bold red]")
            return False, False, None

        all_seasons = response.json()

        special_anime = False
        if anime_name and anime_name.lower() in ['code-geass', 'code-geass-lelouch-of-the-rebellion']:
            special_anime = True
            logger.info(f"Detected {anime_name} - applying special title handling")
        episode_by_title = {}
        episode_by_number = {}

        for season in all_seasons:
            season_num = season.get('number')
            if 'episodes' in season:
                for episode in season.get('episodes', []):
                    title = episode.get('title', '').lower()
                    if title:
                        trakt_id = episode.get('ids', {}).get('trakt')
                        episode_num = episode.get('number')
                        if trakt_id:
                            episode_by_title[title] = {
                                'season': season_num,
                                'episode': episode_num,
                                'trakt_id': trakt_id
                            }

                            normalized = normalize_episode_title(title)
                            if normalized != title:
                                episode_by_title[normalized] = {
                                    'season': season_num,
                                    'episode': episode_num,
                                    'trakt_id': trakt_id
                                }

                    abs_num = episode.get('number_abs')
                    if abs_num:
                        trakt_id = episode.get('ids', {}).get('trakt')
                        if trakt_id:
                            episode_by_number[str(abs_num)] = {
                                'season': season_num,
                                'episode': episode_num,
                                'trakt_id': trakt_id
                            }

        episodes_to_add = []
        failed_episodes = []
        skipped_episodes = []
        failure_details = []

        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn()
        ) as progress:
            task = progress.add_task("[cyan]Processing episodes...", total=len(episodes))

            for episode in episodes:
                matched = False

                if special_anime:
                    episode = handle_special_anime_titles(anime_name, episode)

                if match_by in ["number", "hybrid"]:
                    episode_number = episode['number']

                    trakt_data = None

                    if episode_number in episode_by_number:
                        trakt_data = episode_by_number[episode_number]
                    else:
                        try:
                            clean_number = re.sub(r'\D', '', episode_number)
                            if clean_number in episode_by_number:
                                trakt_data = episode_by_number[clean_number]
                        except:
                            pass

                    if trakt_data:
                        trakt_id = trakt_data['trakt_id']
                        if trakt_id not in existing_trakt_ids:
                            episodes_to_add.append({
                                'ids': {'trakt': trakt_id},
                                'name': episode['name']
                            })
                        else:
                            skipped_episodes.append(episode_number)
                        matched = True

                if not matched and (match_by == "title" or match_by == "hybrid"):
                    episode_title = episode['name'].lower()

                    mapped_title = episode_title
                    title_mappings = config_data.get('title_mappings', {}) or {}
                    anime_mapping = title_mappings.get(anime_name, {}) or {}
                    
                    if anime_mapping and 'special_matches' in anime_mapping:
                        special_matches_lower = {k.lower(): v for k, v in anime_mapping['special_matches'].items()}
                        special_match = special_matches_lower.get(episode_title)
                        if special_match:
                            mapped_title = special_match.lower()
                            if mapped_title.startswith("episode: "):
                                mapped_title = mapped_title[9:]  # Remove "Episode: " prefix
                            logger.info(f"Applied mapping: '{episode_title}' → '{mapped_title}'")

                    matched = False

                    if mapped_title in episode_by_title:
                        trakt_id = episode_by_title[mapped_title]['trakt_id']
                        if trakt_id not in existing_trakt_ids:
                            episodes_to_add.append({
                                'ids': {'trakt': trakt_id},
                                'name': episode['name']
                            })
                        else:
                            skipped_episodes.append(episode_title)
                        matched = True

                    if not matched:
                        normalized_title = normalize_episode_title(mapped_title)
                        if normalized_title in episode_by_title:
                            trakt_id = episode_by_title[normalized_title]['trakt_id']
                            if trakt_id not in existing_trakt_ids:
                                episodes_to_add.append({
                                    'ids': {'trakt': trakt_id},
                                    'name': episode['name']
                                })
                            else:
                                skipped_episodes.append(episode_title)
                            matched = True

                    if not matched and special_anime and anime_name.lower() in ['code-geass', 'code-geass-lelouch-of-the-rebellion']:
                        episode_title = episode['name']

                        stage_match = re.match(r'Stage (\d+)(?:\s*-\s*)?(.+)?', episode_title)
                        turn_match = re.match(r'Turn (\d+)(?:\s*-\s*)?(.+)?', episode_title)
                        final_match = re.match(r'Final Turn(?:\s*-\s*)?(.+)?', episode_title)

                        ep_num = None
                        pure_title = None

                        if stage_match:
                            ep_num = int(stage_match.group(1))
                            pure_title = stage_match.group(2) if stage_match.group(2) else f"Episode {ep_num}"
                            season = 1
                        elif turn_match:
                            ep_num = int(turn_match.group(1))
                            pure_title = turn_match.group(2) if turn_match.group(2) else f"Episode {ep_num}"
                            season = 2
                        elif final_match:
                            ep_num = 25
                            pure_title = final_match.group(1) if final_match.group(1) else "Re;"
                            season = 2

                        if ep_num:
                            for season_data in all_seasons:
                                if season_data.get('number') == season:
                                    for ep_data in season_data.get('episodes', []):
                                        if ep_data.get('number') == ep_num:
                                            trakt_id = ep_data.get('ids', {}).get('trakt')
                                            if trakt_id and trakt_id not in existing_trakt_ids:
                                                episodes_to_add.append({
                                                    'ids': {'trakt': trakt_id},
                                                    'name': episode['name']
                                                })
                                                logger.info(f"Matched Code Geass {episode_title} → S{season}E{ep_num}")
                                                matched = True
                                                break
                                    if matched:
                                        break

                        if not matched and pure_title:
                            normalized_pure = normalize_episode_title(pure_title)
                            for title in episode_by_title.keys():
                                if normalized_pure == title or pure_title.lower() == title:
                                    trakt_id = episode_by_title[title]['trakt_id']
                                    if trakt_id not in existing_trakt_ids:
                                        episodes_to_add.append({
                                            'ids': {'trakt': trakt_id},
                                            'name': episode['name']
                                        })
                                        logger.info(f"Matched Code Geass {episode_title} → {title} by pure title")
                                        matched = True
                                        break

                    if not matched:
                        best_match = None
                        best_score = 0.85

                        for title in episode_by_title.keys():
                            similarity = difflib.SequenceMatcher(None, normalized_title, title).ratio()
                            if similarity > best_score:
                                best_score = similarity
                                best_match = title

                        if best_match:
                            trakt_id = episode_by_title[best_match]['trakt_id']
                            if trakt_id not in existing_trakt_ids:
                                episodes_to_add.append({
                                    'ids': {'trakt': trakt_id},
                                    'name': episode['name']
                                })
                                logger.info(f"Fuzzy matched '{mapped_title}' to '{best_match}' (score: {best_score:.2f})")
                            else:
                                skipped_episodes.append(episode_title)
                            matched = True

                    if not matched:
                        failed_episodes.append(episode)
                        failure_details.append(f"Failed to find match for {episode_title}")

                progress.update(task, advance=1)

        added_episodes = []
        if episodes_to_add:
            add_items_url = f"{trakt_api_url}/users/{trakt_username}/lists/{list_id}/items"

            batch_size = 10
            console.print(f"\n[bold]Adding {len(episodes_to_add)} episodes in batches...[/bold]")

            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn()
            ) as progress:
                batch_task = progress.add_task("[cyan]Adding episodes...", total=len(episodes_to_add))

                for i in range(0, len(episodes_to_add), batch_size):
                    batch = episodes_to_add[i:i+batch_size]

                    episode_payload = {
                        'episodes': [{'ids': {'trakt': ep['ids']['trakt']}} for ep in batch],
                        'type': 'show'
                    }

                    max_retries = 3
                    retry_count = 0
                    retry_delay = 1

                    while retry_count < max_retries:
                        response = requests.post(add_items_url, headers=headers, json=episode_payload)

                        if response.status_code == 201:
                            for ep in batch:
                                added_episodes.append(ep['name'])
                            progress.update(batch_task, advance=len(batch))
                            time.sleep(0.5)
                            break
                        elif response.status_code == 429:
                            retry_count += 1
                            progress.update(batch_task, description=f"Rate limit hit, retrying batch {i//batch_size + 1} in {retry_delay}s...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            failure_details.append(f"Failed to add batch {i//batch_size + 1} - Status {response.status_code}: {response.text}")
                            for ep in batch:
                                failed_episodes.append(ep)
                            progress.update(batch_task, advance=len(batch))
                            break

                    if retry_count == max_retries:
                        failure_details.append(f"Failed to add batch {i//batch_size + 1} - Rate limit retries exhausted")
                        for ep in batch:
                            failed_episodes.append(ep)
                        progress.update(batch_task, advance=len(batch))

        console.print("\n[bold green]Summary:[/bold green]")
        console.print(f"[green]Successfully added: {len(added_episodes)} episodes[/green]")
        console.print(f"[blue]Already in list (skipped): {len(skipped_episodes)} episodes[/blue]")
        console.print(f"[yellow]Failed to add: {len(failed_episodes)} episodes[/yellow]")
        logger.info(f"Summary: Successfully added: {len(added_episodes)}, Skipped: {len(skipped_episodes)}, Failed: {len(failed_episodes)}")

        has_failures = len(failed_episodes) > 0
        failure_info = None

        if added_episodes and len(added_episodes) > 0:
            if notifications_enabled:
                try:
                    plex_name = None
                    if anime_name:
                        mappings = config_data.get('mappings', {}) or {}
                        plex_name = mappings.get(anime_name, anime_name)
                        if '-' in plex_name:
                            plex_name = plex_name.replace('-', ' ').title()

                    import notifications
                    notifications.notify_successful_updates(
                        anime_name if anime_name else "unknown",
                        episode_type if episode_type else "unknown",
                        added_episodes,
                        plex_name,
                        total_added=len(added_episodes)
                    )
                    logger.info(f"Sent notification about {len(added_episodes)} added episodes for {plex_name or anime_name}")
                except Exception as e:
                    logger.error(f"Error sending success notification: {str(e)}")

        if has_failures:
            console.print("\n[bold yellow]Failed Episodes:[/bold yellow]")
            for i, episode in enumerate(failed_episodes[:5], 1):
                episode_name = episode['name'] if isinstance(episode, dict) else str(episode)
                console.print(f"[yellow]{i}. {episode_name}[/yellow]")

            try:
                data_dir = DATA_DIR
                if os.environ.get('RUNNING_IN_DOCKER') == 'true':
                    data_dir = "/app/data"
                os.makedirs(data_dir, exist_ok=True)

                log_file = os.path.join(data_dir, "failed_episodes.log")
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

                afl_name = anime_name if anime_name else "unknown"
                episode_type_value = episode_type if episode_type else "unknown"

                with open(log_file, "a") as f:
                    f.write(f"\n--- {timestamp} ---\n")
                    f.write(f"Anime: {afl_name}\n")
                    f.write(f"Episode Type: {episode_type_value}\n")
                    f.write(f"Failed Episodes: {len(failed_episodes)}\n")

                    for i, episode in enumerate(failed_episodes, 1):
                        if isinstance(episode, dict):
                            ep_num = episode.get('number')
                            ep_name = episode.get('name', str(episode))
                            entry = f"Ep.{ep_num} - {ep_name}" if ep_num is not None else ep_name
                        else:
                            entry = str(episode)
                        f.write(f"{i}. {entry}\n")

                    f.write("---\n")

                console.print(f"[blue]Failures logged to {log_file}[/blue]")

                failure_info = {
                    "log_file": log_file,
                    "count": len(failed_episodes)
                }

                if notifications_enabled:
                    try:
                        import notifications
                        notifications.notify_mapping_errors(
                            afl_name,
                            episode_type_value,
                            [ep['name'] if isinstance(ep, dict) else str(ep) for ep in failed_episodes],
                            failure_details
                        )
                    except Exception as e:
                        logger.error(f"Error sending notification: {str(e)}")

            except Exception as e:
                console.print(f"[bold red]Error during logging: {str(e)}[/bold red]")
                import traceback
                console.print(traceback.format_exc())

        return True, has_failures, failure_info
    except Exception as e:
        console.print(f"[bold red]Error adding episodes to list: {str(e)}[/bold red]")
        logger.error(f"Error adding episodes to list: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False, False, None

def format_trakt_url(username, list_name):
    """Format a valid Trakt URL for a list."""
    url_name = list_name.replace(' ', '-')

    url_name = url_name.replace('/', '-')

    url_name = re.sub(r'[^\w\-]', '', url_name)

    return f"https://trakt.tv/users/{username}/lists/{url_name}"

def format_anime_name(anime_name):
    """Format anime name for API usage."""
    formatted_name = re.sub(r'\s+', '-', anime_name).lower()
    return formatted_name

def log_failed_episodes(anime_name, episode_type, failed_episodes, details=None):
    """Log failed episodes for troubleshooting."""
    try:
        data_dir = DATA_DIR
        if os.environ.get('RUNNING_IN_DOCKER') == 'true':
            data_dir = "/app/data"

        os.makedirs(data_dir, exist_ok=True)

        log_file = os.path.join(data_dir, "failed_episodes.log")

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        with open(log_file, "a") as f:
            f.write(f"\n--- {timestamp} ---\n")
            f.write(f"Anime: {anime_name}\n")
            f.write(f"Episode Type: {episode_type}\n")
            f.write(f"Failed Episodes: {len(failed_episodes)}\n")

            for i, episode in enumerate(failed_episodes, 1):
                if isinstance(episode, dict):
                    ep_num = episode.get('number')
                    ep_name = episode.get('name', str(episode))
                    entry = f"Ep.{ep_num} - {ep_name}" if ep_num is not None else ep_name
                else:
                    entry = str(episode)
                f.write(f"{i}. {entry}\n")

            if details is not None:
                f.write("Details:\n")
                if isinstance(details, list):
                    for detail in details:
                        f.write(f"- {detail}\n")
                else:
                    f.write(f"- {str(details)}\n")

            f.write("---\n")

        logger.info(f"Logged {len(failed_episodes)} failed episodes for {anime_name}")

        return True
    except Exception as e:
        console.print(f"[yellow]Error logging failed episodes: {str(e)}[/yellow]")
        logger.error(f"Error logging failed episodes: {str(e)}")
        import traceback  # Add traceback for better error reporting
        logger.error(traceback.format_exc())
        return False

def find_anime_on_animefillerlist(plex_title, all_afl_shows):
    """Find the best matching anime on AnimeFillerList for a Plex title."""
    plex_title_lower = plex_title.lower()

    variations = [
        plex_title_lower,  # Full title
        plex_title_lower.split(':')[0].strip() if ':' in plex_title_lower else plex_title_lower,
        ' '.join(plex_title_lower.split()[:2]) if len(plex_title_lower.split()) > 2 else plex_title_lower,
    ]

    console.print(f"[dim]Looking for matches to: {plex_title}[/dim]")
    console.print(f"[dim]Checking variations: {', '.join(variations)}[/dim]")

    best_matches = []
    for afl_show in all_afl_shows:
        display_name = afl_show.replace('-', ' ')

        best_variation_score = 0
        for variation in variations:
            similarity = difflib.SequenceMatcher(None, display_name, variation).ratio()
            best_variation_score = max(best_variation_score, similarity)

            if display_name == variation or similarity > 0.9:
                return [(afl_show, 1.0)]

        if best_variation_score > 0.6:
            best_matches.append((afl_show, best_variation_score))

    best_matches.sort(key=lambda x: x[1], reverse=True)

    return best_matches

def generate_variations(title):
    """Generate multiple variations of a title for matching."""
    variations = []

    clean_title = title.lower()
    clean_title = clean_title.replace('ū', 'u').replace('ō', 'o')
    variations.append(clean_title)
    
    sequel_indicators = [
        " shippuden", " shippūden", " shippūden", 
        " boruto", ": boruto", 
        " next generations", " the next generation",
        ": brotherhood", " brotherhood",
        " season 2", " 2nd season", " second season",
        " part 2", " part ii"
    ]
    
    is_sequel = False
    base_anime = clean_title
    
    for indicator in sequel_indicators:
        if indicator in clean_title:
            is_sequel = True
            base_idx = clean_title.find(indicator)
            base_anime = clean_title[:base_idx].strip()
            
            sequel_name = clean_title.replace(':', ' ').replace('  ', ' ').strip()
            if sequel_name != clean_title and sequel_name not in variations:
                variations.insert(1, sequel_name)
            break
    
    if not is_sequel:
        if ':' in clean_title:
            before_colon = clean_title.split(':', 1)[0].strip()
            variations.append(before_colon)

            after_colon = clean_title.split(':', 1)[1].strip()
            variations.append(after_colon)

            no_colon = clean_title.replace(':', ' ').strip()
            variations.append(no_colon)

            variations.append(clean_title.replace(':', '').strip())

        words = clean_title.split()
        if len(words) >= 3:
            variations.append(' '.join(words[:3]))
            
        if len(words) >= 2:
            variations.append(' '.join(words[:2]))
            
        if len(words) >= 1:
            common_bases = ['naruto', 'boruto', 'dragon', 'one', 'my', 'attack', 'demon']
            if words[0] not in common_bases:
                variations.append(words[0])

    simplified = clean_title
    for word in ['the', 'a', 'an', 'of', 'and']:
        simplified = re.sub(r'\b' + word + r'\b', '', simplified)
    simplified = re.sub(r'\s+', ' ', simplified).strip()
    if simplified != clean_title and simplified not in variations:
        variations.append(simplified)

    key_words = [word for word in clean_title.split() if len(word) > 3 and word not in ['with', 'from', 'that', 'this', 'what']]
    if key_words and ' '.join(key_words) != clean_title:
        variations.append(' '.join(key_words))

    unique_variations = []
    for v in variations:
        if v and v not in unique_variations:
            unique_variations.append(v)
            
    if is_sequel and clean_title not in unique_variations[:1]:
        if clean_title in unique_variations:
            unique_variations.remove(clean_title)
        unique_variations.insert(0, clean_title)

    return unique_variations

def find_best_anime_match(plex_title, all_afl_shows):
    """Find best match using similarity ranking across all potential matches."""
    console.print(f"[dim]Looking for AnimeFillerList match for: {plex_title}[/dim]")

    variations = generate_variations(plex_title)
    console.print(f"[dim]Trying variations: {', '.join(variations)}[/dim]")

    afl_display = {name: name.replace('-', ' ') for name in all_afl_shows}

    all_potential_matches = []

    normalized_full_title = plex_title.lower().replace('ū', 'u').replace('ō', 'o')
    for afl_name, display_name in afl_display.items():
        simplified_name = display_name.lower().replace('ū', 'u').replace('ō', 'o')
        if normalized_full_title == simplified_name:
            console.print(f"[green]Found exact match on full title: {afl_name}[/green]")
            return afl_name

    variations_by_length = sorted(variations, key=len, reverse=True)
    for variation in variations_by_length:
        for afl_name, display_name in afl_display.items():
            if variation == display_name:
                potential_longer_match = False
                for other_name in afl_display.values():
                    if display_name != other_name and display_name in other_name:
                        # Check if this longer name is a better match for our plex_title
                        if difflib.SequenceMatcher(None, plex_title.lower(), other_name).ratio() > 0.8:
                            potential_longer_match = True
                            break
                
                if not potential_longer_match:
                    console.print(f"[green]Found exact match: {afl_name}[/green]")
                    return afl_name  # Immediate return for exact matches without longer alternatives

    # 3. Calculate similarity scores for all shows against all variations
    for afl_name, display_name in afl_display.items():
        # Track best score for this show across all variations
        best_score = 0
        best_variation = ""
        match_type = "word"  # Default match type

        # Check different matching methods
        for variation in variations:
            # 3a. Word-subset matching
            afl_words = set(display_name.split())
            title_words = set(variation.split())

            is_subset_match = False
            # Need at least 2 words in common for a valid subset match
            common_words = afl_words.intersection(title_words)

            if len(common_words) >= 2:
                if afl_words.issubset(title_words) or title_words.issubset(afl_words):
                    is_subset_match = True

            # 3b. Sequence similarity score
            similarity = difflib.SequenceMatcher(None, display_name, variation).ratio()

            # Boost score for subset matches
            if is_subset_match and len(common_words) > 1:
                # Words in common provide a bonus
                word_bonus = min(0.3, len(common_words) * 0.1)  # Cap at 0.3
                adjusted_similarity = similarity + word_bonus

                # Extra boost if it's the main part (not small variations)
                if len(variation.split()) >= 2 and len(afl_words) >= 2:
                    adjusted_similarity += 0.1

                # Cap at 0.99 to keep exact matches higher
                adjusted_similarity = min(0.99, adjusted_similarity)

                if adjusted_similarity > best_score:
                    best_score = adjusted_similarity
                    best_variation = variation
                    match_type = "subset"

            # Regular similarity might still be better
            elif similarity > best_score:
                best_score = similarity
                best_variation = variation
                match_type = "similarity"

        # Only consider this show if it has a decent score
        # Use a higher threshold (0.7) for better accuracy
        threshold = 0.7  # Increased minimum reasonable match threshold
        if best_score >= threshold:
            all_potential_matches.append((afl_name, best_score, match_type, best_variation))

    # Sort all matches by score (highest first)
    all_potential_matches.sort(key=lambda x: x[1], reverse=True)

    # If we have matches, return the best one
    if all_potential_matches:
        best_match, score, match_type, variation = all_potential_matches[0]

        # Log more details for understanding the match
        match_detail = f"best variation: '{variation}'"
        console.print(f"[green]Found {match_type} match: {best_match} (similarity: {score*100:.0f}%, {match_detail})[/green]")

        # Debug: show top 3 matches that were considered
        if len(all_potential_matches) > 1:
            console.print("[dim]Top alternative matches:[/dim]")
            for i in range(1, min(3, len(all_potential_matches))):
                alt_name, alt_score, alt_type, alt_var = all_potential_matches[i]
                console.print(f"[dim]{i+1}. {alt_name} ({alt_score*100:.0f}%, {alt_type}, variation: '{alt_var}')[/dim]")

        return best_match

    # No good matches found
    console.print("[yellow]No strong automatic matches found[/yellow]")
    return None

def suggest_matches(plex_title, all_afl_shows, max_suggestions=5):
    """Find and suggest potential matches for manual selection."""
    # Convert AFL shows to display format for comparison
    afl_display = {name: name.replace('-', ' ') for name in all_afl_shows}

    # Generate variations of the Plex title
    variations = generate_variations(plex_title)

    # Calculate similarity scores
    matches = []
    for afl_name, display_name in afl_display.items():
        best_score = 0
        for variation in variations:
            similarity = difflib.SequenceMatcher(None, display_name, variation).ratio()
            best_score = max(best_score, similarity)

        if best_score > 0.4:  # Lower threshold for suggestions
            matches.append((afl_name, best_score))

    # Sort by similarity and return top matches
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:max_suggestions]

def clear_error_log():
    """Clear the error log file at the start of a new run."""
    try:
        data_dir = DATA_DIR
        if os.environ.get('RUNNING_IN_DOCKER') == 'true':
            data_dir = "/app/data"

        log_file = os.path.join(data_dir, "failed_episodes.log")

        # Create directory if it doesn't exist
        os.makedirs(data_dir, exist_ok=True)

        # Create empty log file (overwriting any existing one)
        with open(log_file, 'w') as f:
            f.write(f"# Mapping errors log - Created {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    except Exception as e:
        logger.error(f"Error clearing error log: {str(e)}")

def clear_error_log_for_anime(anime_name):
    """Remove all log entries for a specific anime, leaving other anime's entries intact."""
    try:
        data_dir = DATA_DIR
        if os.environ.get('RUNNING_IN_DOCKER') == 'true':
            data_dir = "/app/data"
        log_file = os.path.join(data_dir, "failed_episodes.log")
        if not os.path.exists(log_file):
            return
        with open(log_file, 'r') as f:
            lines = f.readlines()
        kept = []
        skip_block = False
        for line in lines:
            stripped = line.rstrip("\n")
            if stripped.startswith("--- ") and stripped.endswith(" ---"):
                skip_block = False
                kept.append(line)
            elif stripped.startswith("Anime: "):
                if stripped[7:].strip() == anime_name:
                    skip_block = True
                    kept.pop()  # remove the "--- timestamp ---" line already appended
                else:
                    kept.append(line)
            elif not skip_block:
                kept.append(line)
            elif stripped == "---":
                skip_block = False
        with open(log_file, 'w') as f:
            f.writelines(kept)
    except Exception as e:
        logger.error(f"Error clearing error log for {anime_name}: {str(e)}")

def clean_error_log(anime_name, episode_type, fixed_episodes):
    """Remove fixed episodes from the error log while preserving other entries."""
    try:
        data_dir = DATA_DIR
        if os.environ.get('RUNNING_IN_DOCKER') == 'true':
            data_dir = "/app/data"

        log_file = os.path.join(data_dir, "failed_episodes.log")

        if not os.path.exists(log_file):
            logger.warning(f"Error log file not found: {log_file}")
            return False

        # Create a backup of the original log
        backup_file = os.path.join(data_dir, "failed_episodes.log.bak")
        import shutil
        shutil.copy2(log_file, backup_file)

        # Read the log file
        with open(log_file, 'r') as f:
            lines = f.readlines()

        # Parse the log file into entries
        entries = []
        current_entry = []
        in_entry = False

        for line in lines:
            if line.startswith('---'):
                if in_entry:
                    # End of entry, add it to our list
                    entries.append(current_entry)
                    current_entry = []
                    in_entry = False
                else:
                    # Start of entry
                    in_entry = True

            if in_entry or line.startswith('---'):
                current_entry.append(line)

        # Check if we have a partial entry at the end
        if current_entry:
            entries.append(current_entry)

        # Process entries to remove fixed episodes
        updated_entries = []
        removed_count = 0

        # Normalize input types for comparison
        normalized_anime = anime_name.lower().strip()
        normalized_type = episode_type.lower().strip()
        if "canon" in normalized_type:
            if "manga" in normalized_type:
                normalized_type = "manga"
            elif "anime" in normalized_type:
                normalized_type = "anime"
            elif "mixed" in normalized_type:
                normalized_type = "mixed"

        # Get the list of anime names to check - check both AFL name and Plex name
        anime_names_to_check = [normalized_anime]
        
        # Check if anime_name is a Plex name and get the corresponding AFL name
        for afl_name, plex_name in CONFIG.get('mappings', {}).items():
            if plex_name.lower() == normalized_anime:
                anime_names_to_check.append(afl_name.lower())
                break
                
        # Check if anime_name is an AFL name and get the corresponding Plex name  
        plex_name = CONFIG.get('mappings', {}).get(normalized_anime)
        if plex_name:
            anime_names_to_check.append(plex_name.lower())
            
        logger.info(f"Checking anime names for cleaning: {anime_names_to_check}")

        for entry in entries:
            # Extract anime name and episode type from entry
            entry_anime = None
            entry_type = None
            entry_episodes = []
            found_episodes_list = False
            in_details = False

            for i, line in enumerate(entry):
                if line.startswith('Anime:'):
                    # Extract base anime name without parentheses
                    raw_anime = line.replace('Anime:', '').strip()
                    entry_anime = raw_anime.split(' (')[0].strip().lower()
                elif line.startswith('Episode Type:'):
                    entry_type = line.replace('Episode Type:', '').strip().lower()
                    # Normalize entry type
                    if "canon" in entry_type:
                        if "manga" in entry_type:
                            entry_type = "manga"
                        elif "anime" in entry_type:
                            entry_type = "anime"
                        elif "mixed" in entry_type:
                            entry_type = "mixed"
                elif line.startswith('Failed Episodes:'):
                    found_episodes_list = True
                    entry_episodes.append(line)
                elif line.startswith('Details:'):
                    in_details = True
                elif in_details and not line.startswith('---'):
                    continue  # Skip details
                elif found_episodes_list and not in_details and line[0].isdigit() and '. ' in line:
                    episode_name = line.split('. ', 1)[1].strip()
                    # Strip "Ep.N - " prefix so comparison works against plain names from UI
                    ep_prefix = re.match(r'^Ep\.\d+ - (.+)$', episode_name)
                    compare_name = ep_prefix.group(1) if ep_prefix else episode_name
                    entry_episodes.append((line, compare_name))

            # Compare normalized values for more flexible matching
            # Check if the entry anime name matches any of our anime names to check
            if entry_anime in anime_names_to_check and entry_type == normalized_type:
                # This entry matches, so remove fixed episodes
                updated_episode_lines = []

                for episode_entry in entry_episodes:
                    if isinstance(episode_entry, tuple):
                        line, episode_name = episode_entry
                        if episode_name not in fixed_episodes:
                            updated_episode_lines.append(line)
                        else:
                            removed_count += 1
                    else:
                        updated_episode_lines.append(episode_entry)

                if len(updated_episode_lines) > 1:  # More than just the header line
                    # Update the count in the "Failed Episodes:" line
                    count = len(updated_episode_lines) - 1
                    updated_episode_lines[0] = f"Failed Episodes: {count}\n"

                    # Reconstruct this entry with remaining episodes
                    new_entry = []
                    found_episodes_list = False
                    in_details = False
                    episode_index = 1

                    for line in entry:
                        if line.startswith('Details:'):
                            in_details = True
                            continue  # Skip the Details section entirely
                        elif in_details and not line.startswith('---'):
                            continue  # Skip all detail lines
                        elif line.startswith('Failed Episodes:'):
                            new_entry.append(updated_episode_lines[0])
                            found_episodes_list = True
                        elif found_episodes_list and not in_details and line[0].isdigit() and '. ' in line:
                            if episode_index < len(updated_episode_lines):
                                if isinstance(updated_episode_lines[episode_index], tuple):
                                    new_entry.append(updated_episode_lines[episode_index][0])
                                else:
                                    new_entry.append(updated_episode_lines[episode_index])
                                episode_index += 1
                        else:
                            new_entry.append(line)

                    # Renumber the episodes
                    final_entry = []
                    episode_number = 1
                    for line in new_entry:
                        if found_episodes_list and line[0].isdigit() and '. ' in line:
                            episode_parts = line.split('. ', 1)
                            if len(episode_parts) > 1:
                                episode_name = episode_parts[1]
                                final_entry.append(f"{episode_number}. {episode_name}")
                                episode_number += 1
                        else:
                            final_entry.append(line)

                    updated_entries.append(final_entry)
                else:
                    # All episodes in this entry were fixed, so skip the entire entry
                    removed_count += 1
            else:
                # This entry is for a different anime/type, keep it as-is
                updated_entries.append(entry)

        # Write the updated log
        with open(log_file, 'w') as f:
            # Add a header comment
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"# Mapping errors log - Updated {timestamp}\n")
            f.write(f"# Removed {removed_count} fixed entries for {anime_name} ({episode_type})\n\n")

            # Write all the entries
            for entry in updated_entries:
                for line in entry:
                    f.write(line)

        logger.info(f"Cleaned error log for {anime_name} ({episode_type}): removed {removed_count} entries")
        return True

    except Exception as e:
        logger.error(f"Error cleaning error log: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def _create_list_internal(anime_name, episode_type, match_by="hybrid"):
    """Internal function to create lists without using Click command."""
    # Force reload config to get latest mappings
    reload_config()

    # Map episode type input to the full name used on AnimeFillerList
    episode_type_mapping = {
        'FILLER': 'FILLER',
        'MANGA': 'MANGA CANON',
        'ANIME': 'ANIME CANON',
        'MIXED': 'MIXED CANON/FILLER',
    }

    episode_type_filter = episode_type_mapping.get(episode_type.upper())

    # Format anime name
    formatted_anime_name = format_anime_name(anime_name)

    # Get auth token using our trakt_auth module
    access_token = trakt_auth.ensure_trakt_auth()
    if not access_token:
        return False

    # Connect to Plex
    plex = connect_to_plex()
    if not plex:
        return False

    # Get TMDB ID from Plex
    tmdb_id = get_tmdb_id_from_plex(plex, formatted_anime_name)
    if not tmdb_id:
        return False

    # Get Trakt show ID
    trakt_show_id = get_trakt_show_id(access_token, tmdb_id)
    if not trakt_show_id:
        return False

    # Get episodes from AnimeFillerList
    anime_episodes = get_anime_episodes(formatted_anime_name, episode_type_filter)

    # ADDITIONAL CODE - Apply mappings manually if needed
    title_mappings = CONFIG.get('title_mappings', {}).get(formatted_anime_name, {}).get('special_matches', {})
    if title_mappings:
        # Check if we need to apply mappings manually
        for episode in anime_episodes:
            if episode['name'] in title_mappings:
                # Log that we're applying a mapping
                console.print(f"[green]Applying mapping: '{episode['name']}' → '{title_mappings[episode['name']]}'[/green]")
                episode['name'] = title_mappings[episode['name']]

    if not anime_episodes:
        console.print(f"[bold red]No episodes found for {formatted_anime_name} with type {episode_type_filter}[/bold red]")
        return False

    # Display episodes that will be added
    console.print(f"\n[bold]Episodes to be added to Trakt list:[/bold]")
    for i, episode in enumerate(anime_episodes, 1):
        console.print(f"{i}. Episode {episode['number']}: {episode['name']} ({episode['type']})")

    # Use the correct list name format
    trakt_list_name = get_list_name_format(formatted_anime_name, episode_type)
    list_id, list_exists = create_or_get_trakt_list(trakt_list_name, access_token)
    if not list_id:
        return False

    # Add episodes to Trakt list
    success, has_failures, failure_info = add_episodes_to_trakt_list(
        list_id,
        anime_episodes,
        access_token,
        trakt_show_id,
        match_by,
        formatted_anime_name,
        episode_type.lower()
    )

    console.print(f"\n[bold green]🎉 List creation complete! 🎉[/bold green]")
    trakt_url = format_trakt_url(CONFIG['trakt']['username'], trakt_list_name)
    console.print(f"[blue]You can view your list at: {trakt_url}[/blue]")

    # Display failure message at the end if there were failures
    if has_failures and failure_info:
        console.print("\n[bold yellow]Some episodes could not be mapped:[/bold yellow]")
        console.print(f"[blue]Failures logged to {failure_info['log_file']}[/blue]")
        console.print("[yellow]To fix these mapping issues, run this command:[/yellow]")
        console.print("[green]docker compose run --rm dakosys fix-mappings[/green]")

    return not has_failures

    if not has_failures:
        try:
            from asset_manager import sync_anime_episode_collections
            logger.info("Synchronizing collections file with Trakt lists...")
            return sync_anime_episode_collections(CONFIG, force_update=True)
        except Exception as e:
            logger.error(f"Error synchronizing collections: {str(e)}")
            return not has_failures

@click.group()
def cli():
    """Dakosys: Kometa overlay generator for anime episode type; next airing and size calculation."""
    # Load configuration unless we're running setup
    if 'setup' not in sys.argv:
        if not load_config():
            sys.exit(1)

@cli.command()
@click.argument('service', required=False, type=click.Choice(['anime_episode_type', 'tv_status_tracker', 'size_overlay']))
def setup(service=None):
    """Interactive setup to create or update configuration.
    
    SERVICE: Optional service to configure (anime_episode_type, tv_status_tracker, size_overlay)
    If no service is specified, runs the full setup.
    """
    try:
        from setup import run_setup, setup_service
        
        # If a specific service was requested, run targeted setup
        if service:
            console.print(f"[bold blue]Running setup for {service} service...[/bold blue]")
            setup_service(service)
        else:
            # Run full setup
            console.print("[bold blue]Running full setup...[/bold blue]")
            run_setup()
    except ImportError as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        console.print("[yellow]Make sure setup.py is in the same directory.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Error during setup: {str(e)}[/bold red]")
        import traceback
        console.print(traceback.format_exc())

@cli.command()
def test_notification():
    """Test Discord notification system."""
    try:
        console.print("[bold blue]Testing Discord notification system...[/bold blue]")

        # Import the notifications module
        try:
            import notifications
            console.print("[green]Successfully imported notifications module[/green]")
        except ImportError as e:
            console.print(f"[bold red]Failed to import notifications module: {str(e)}[/bold red]")
            return

        # Create test data
        anime_name = "Test Anime"
        episode_type = "TEST"
        failed_episodes = ["Episode 1: Test Failure", "Episode 2: Another Test"]
        details = ["Error: Test error message", "Debug: This is just a test"]

        # Send test notification
        console.print("[yellow]Sending test notification to Discord...[/yellow]")
        result = notifications.notify_mapping_errors(anime_name, episode_type, failed_episodes, details)

        if result:
            console.print("[bold green]Test notification sent successfully![/bold green]")
            console.print("[blue]Check your Discord channel for the notification[/blue]")
        else:
            console.print("[bold red]Failed to send test notification[/bold red]")
            console.print("[yellow]Check data/notifications.log for error details[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error during notification test: {str(e)}[/bold red]")
        import traceback
        console.print(traceback.format_exc())

@cli.command()
def test_logging():
    """Test logging functionality."""
    try:
        console.print("[bold blue]Testing logging functionality...[/bold blue]")

        # Create some test data
        failed_episodes = ["Test Episode 1", "Test Episode 2"]

        # Print the data type of failed_episodes
        console.print(f"Type of failed_episodes: {type(failed_episodes)}")
        console.print(f"Content of failed_episodes: {failed_episodes}")

        # Make sure data directory exists
        data_dir = DATA_DIR
        if os.environ.get('RUNNING_IN_DOCKER') == 'true':
            data_dir = "/app/data"

        console.print(f"Data directory: {data_dir}")
        os.makedirs(data_dir, exist_ok=True)

        # Create or open log file
        log_file = os.path.join(data_dir, "test_log.txt")
        console.print(f"Writing to log file: {log_file}")

        # Write directly to file
        with open(log_file, "w") as f:
            f.write("Test log file\n")
            f.write(f"Number of episodes: {len(failed_episodes)}\n")

            # Write each episode explicitly
            f.write("Episodes:\n")
            for episode in failed_episodes:
                f.write(f"- {episode}\n")

        console.print(f"[green]Successfully wrote to {log_file}[/green]")

    except Exception as e:
        console.print(f"[bold red]Error in test logging: {str(e)}[/bold red]")
        import traceback
        console.print(traceback.format_exc())

def update_kometa_configs(anime_name, access_token=None):
    """DEPRECATED: Using sync_anime_episode_collections from asset_manager instead.
    
    This function added URLs for all episode types regardless of whether they exist,
    which could cause phantom list URLs in the collections file.
    """
    logger.warning("update_kometa_configs is deprecated, using sync_anime_episode_collections instead")
    from asset_manager import sync_anime_episode_collections
    return sync_anime_episode_collections(CONFIG, force_update=True)

@cli.command()
def list_anime():
    """List all anime shows available on AnimeFillerList."""
    try:
        console.print("[bold blue]Fetching anime list from AnimeFillerList...[/bold blue]")

        base_url = 'https://www.animefillerlist.com/shows'
        response = requests.get(base_url)

        if response.status_code != 200:
            console.print(f"[bold red]Failed to fetch data from AnimeFillerList. Status Code: {response.status_code}[/bold red]")
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        anime_list = []

        # Find all anime links
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('/shows/'):
                anime_name = href.replace('/shows/', '')
                if anime_name and anime_name != '':
                    anime_list.append(anime_name)

        # Sort and display the list
        anime_list = sorted(list(set(anime_list)))

        console.print(f"\n[bold green]Found {len(anime_list)} anime shows on AnimeFillerList:[/bold green]")

        for i, anime in enumerate(anime_list, 1):
            # Check if we have a mapping for this anime
            plex_name = CONFIG.get('mappings', {}).get(anime, "")
            if plex_name:
                console.print(f"{i}. {anime} [green](Mapped to: {plex_name})[/green]")
            else:
                console.print(f"{i}. {anime}")

    except Exception as e:
        console.print(f"[bold red]Error listing anime: {str(e)}[/bold red]")

@cli.command()
@click.argument('anime_name')
def show_episodes(anime_name):
    """Show all episodes for an anime with their types.

    ANIME_NAME: Name of the anime (e.g. 'one-piece', 'attack-titan')
    """
    # Try to find in mappings first (Plex name)
    afl_name = None
    for name, plex_title in CONFIG.get('mappings', {}).items():
        if plex_title.lower() == anime_name.lower():
            afl_name = name
            break

    # If not found, try direct match with AFL name format
    if not afl_name:
        afl_name = format_anime_name(anime_name)

    # Get episodes without filtering
    episodes = get_anime_episodes(afl_name)

    if not episodes:
        console.print(f"[bold red]No episodes found for {afl_name}[/bold red]")
        return

    # Count each type
    type_counts = {}
    for episode in episodes:
        episode_type = episode['type']
        type_counts[episode_type] = type_counts.get(episode_type, 0) + 1

    # Display summary
    display_name = afl_name.replace('-', ' ').title()
    console.print(f"\n[bold]Episodes for {display_name}:[/bold]")
    console.print(f"[bold]Total Episodes:[/bold] {len(episodes)}")
    for ep_type, count in type_counts.items():
        percentage = (count / len(episodes)) * 100
        console.print(f"[bold]{ep_type}:[/bold] {count} episodes ({percentage:.1f}%)")

    # Display episodes grouped by type
    episode_types = sorted(list(type_counts.keys()))

    for ep_type in episode_types:
        console.print(f"\n[bold]{ep_type} Episodes:[/bold]")
        type_episodes = [ep for ep in episodes if ep['type'] == ep_type]
        for episode in type_episodes:
            console.print(f"Episode {episode['number']}: {episode['name']}")

@cli.command()
def test_scheduler():
    """Test the scheduler configuration without actually updating lists."""
    try:
        # Temporarily modify the config to enable dry run
        config = CONFIG
        if not config:
            console.print("[bold red]Failed to load configuration[/bold red]")
            return

        # Check if scheduler config exists
        if 'scheduler' not in config:
            console.print("[bold red]No scheduler configuration found[/bold red]")
            console.print("[yellow]Please add a scheduler section to your config.yaml file[/yellow]")
            return

        # Set dry run mode
        original_dry_run = config['scheduler'].get('dry_run', False)
        config['scheduler']['dry_run'] = True

        # Create a config copy without mappings
        config_to_save = config.copy()
        if 'mappings' in config_to_save:
            del config_to_save['mappings']
        if 'trakt_mappings' in config_to_save:
            del config_to_save['trakt_mappings']
        if 'title_mappings' in config_to_save:
            del config_to_save['title_mappings']

        # Save modified config temporarily
        temp_config_path = os.path.join(DATA_DIR, 'temp_config.yaml')
        with open(temp_config_path, 'w') as f:
            yaml.dump(config_to_save, f)

        # Import and run the scheduler in test mode
        console.print("[bold blue]Testing scheduler configuration...[/bold blue]")
        console.print("[yellow]This will show when your updates would run without actually updating any lists.[/yellow]")

        try:
            from scheduler import setup_scheduler
            success = setup_scheduler()
            if success:
                console.print("[bold green]Scheduler configuration is valid![/bold green]")

                # Print the next scheduled runs
                console.print("\n[bold blue]Next scheduled runs:[/bold blue]")

                import schedule
                jobs = schedule.get_jobs()
                for i, job in enumerate(jobs, 1):
                    next_run = job.next_run
                    if next_run:
                        console.print(f"[green]{i}. Next run at: {next_run.strftime('%Y-%m-%d %H:%M:%S')}[/green]")

                if not jobs:
                    console.print("[yellow]No scheduled jobs found. Check your scheduler configuration.[/yellow]")
            else:
                console.print("[bold red]Scheduler configuration is invalid![/bold red]")
                console.print("[yellow]Please check data/scheduler.log for details.[/yellow]")
        except Exception as e:
            console.print(f"[bold red]Error testing scheduler: {str(e)}[/bold red]")

        # Restore original config
        config['scheduler']['dry_run'] = original_dry_run
        
        # Create a config copy without mappings
        config_to_save = config.copy()
        if 'mappings' in config_to_save:
            del config_to_save['mappings']
        if 'trakt_mappings' in config_to_save:
            del config_to_save['trakt_mappings']
        if 'title_mappings' in config_to_save:
            del config_to_save['title_mappings']
        
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config_to_save, f)

        # Remove temp config
        if os.path.exists(temp_config_path):
            os.remove(temp_config_path)

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")

@cli.command()
@click.argument('anime_name')
@click.argument('episode_type', type=click.Choice(['FILLER', 'MANGA', 'ANIME', 'MIXED'], case_sensitive=False))
@click.option('--match-by', type=click.Choice(['title', 'number', 'hybrid']), default='hybrid',
              help='How to match episodes (by title, number or both)')
@click.option('--force-map', is_flag=True, default=False,
              help='Force mapping creation/update even if one exists')
def create(anime_name, episode_type, match_by, force_map):
    """Create a list for a specific episode type.

    ANIME_NAME: Name of the anime (e.g. 'attack-titan' or 'Attack on Titan')
    EPISODE_TYPE: Type of episodes to include (FILLER, MANGA, ANIME, MIXED)
    """
    # Clear the error log at the start
    clear_error_log()
    # Map episode type input to the full name used on AnimeFillerList
    episode_type_mapping = {
        'FILLER': 'FILLER',
        'MANGA': 'MANGA CANON',
        'ANIME': 'ANIME CANON',
        'MIXED': 'MIXED CANON/FILLER',
    }

    episode_type_filter = episode_type_mapping.get(episode_type.upper())

    # Connect to Plex
    plex = connect_to_plex()
    if not plex:
        return

    try:
        anime_libs = get_anime_libraries(plex)
        if not anime_libs:
            return
        anime_library = anime_libs[0]
    except Exception as e:
        console.print(f"[bold red]Error accessing Plex library: {str(e)}[/bold red]")
        return

    # First check: Is this an AFL name with an existing mapping?
    afl_name = format_anime_name(anime_name)
    plex_name = CONFIG.get('mappings', {}).get(afl_name)

    if not afl_name or not plex_name:
        # Check reverse mapping (Plex title to AFL name)
        for afl_key, mapped_plex_title in CONFIG.get('mappings', {}).items():
            if mapped_plex_title.lower() == anime_name.lower():
                afl_name = afl_key
                plex_name = mapped_plex_title
                console.print(f"[green]Found existing mapping: {afl_name} → {plex_name}[/green]")
                break

    # Second check: Is this a Plex name? (direct match in Plex)
    plex_direct_match = None
    for show in anime_library.all():
        if show.title.lower() == anime_name.lower():
            plex_direct_match = show.title
            break

    # If we have neither an AFL mapping nor a direct Plex match, try fuzzy search in Plex
    if (not plex_name or force_map) and not plex_direct_match:
        console.print("[yellow]No exact mapping found. Searching for matches in Plex...[/yellow]")

        # Collect all Plex show titles
        plex_titles = [show.title for show in anime_library.all()]

        # Try to find matches
        potential_matches = []
        for title in plex_titles:
            # Check for exact match first
            if anime_name.lower() == title.lower():
                potential_matches.append((title, 1.0))
                continue
        
            # Check for match before colon (for titles like "Show Name: Subtitle")
            if ':' in title:
                before_colon = title.split(':', 1)[0].strip().lower()
                if anime_name.lower() == before_colon:
                    potential_matches.append((title, 0.95))  # Almost perfect match
                    continue
            
            # Use simple similarity ratio as a fallback
            similarity = difflib.SequenceMatcher(None, anime_name.lower(), title.lower()).ratio()
            if similarity > 0.6:  # Threshold for potential matches
                potential_matches.append((title, similarity))

        # Sort by similarity
        potential_matches.sort(key=lambda x: x[1], reverse=True)

        if potential_matches:
            console.print("[green]Found potential matches in your Plex library:[/green]")

            # Show options
            for i, (title, score) in enumerate(potential_matches[:5], 1):
                console.print(f"{i}. {title} [dim](similarity: {score*100:.0f}%)[/dim]")

            console.print("0. None of these - enter a different name")

            # Ask user to select
            choice = click.prompt("Select the correct show", type=int, default=1)

            if choice > 0 and choice <= len(potential_matches):
                plex_direct_match = potential_matches[choice-1][0]
            else:
                console.print("[yellow]No show selected. Exiting.[/yellow]")
                return
        else:
            console.print("[bold red]No matches found in your Plex library.[/bold red]")
            return

    # If we found a direct match in Plex but no mapping, create one
    if plex_direct_match and (not plex_name or force_map):
        console.print(f"[green]Found direct match in Plex: {plex_direct_match}[/green]")

        # We need to find the corresponding AnimeFillerList name
        console.print("[bold blue]Fetching anime list from AnimeFillerList...[/bold blue]")
        base_url = 'https://www.animefillerlist.com/shows'
        response = requests.get(base_url)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            all_afl_shows = []

            # Find all anime links
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.startswith('/shows/'):
                    all_afl_shows.append(href.replace('/shows/', ''))

            # First try automatic matching
            afl_name = find_best_anime_match(plex_direct_match, all_afl_shows)

            if afl_name:
                # Automatic match found - confirm with user
                console.print(f"[bold green]Found match: {afl_name.replace('-', ' ')}[/bold green]")

                if click.confirm("Use this match?", default=True):
                    add_mapping(afl_name, plex_direct_match)
                else:
                    # User rejects automatic match - go to manual selection
                    afl_name = None

            if not afl_name:
                # No automatic match or user rejected it - show suggestions
                console.print("[yellow]Please select the correct AnimeFillerList show:[/yellow]")

                # Get suggestions
                suggestions = suggest_matches(plex_direct_match, all_afl_shows)

                if suggestions:
                    console.print("[green]Potential matches:[/green]")

                    # Show options
                    for i, (name, score) in enumerate(suggestions, 1):
                        console.print(f"{i}. {name.replace('-', ' ')} [dim](similarity: {score*100:.0f}%)[/dim]")

                    console.print("0. None of these - enter manually")

                    # Ask user to select
                    choice = click.prompt("Select the correct AnimeFillerList show", type=int, default=1)

                    if choice > 0 and choice <= len(suggestions):
                        afl_name = suggestions[choice-1][0]

                        add_mapping(afl_name, plex_direct_match)
                    else:
                        # Manual entry
                        console.print("\n[yellow]Please enter the correct AnimeFillerList show name.[/yellow]")
                        console.print("[yellow]You can find this by searching on https://www.animefillerlist.com/shows[/yellow]")
                        console.print("[yellow]Format example: 'code-geass' (use hyphens, all lowercase)[/yellow]")

                        afl_name = click.prompt("Enter AnimeFillerList show name")

                        add_mapping(afl_name, plex_direct_match)
                else:
                    # No suggestions
                    console.print("[yellow]No matches found. Please enter the correct AnimeFillerList show name.[/yellow]")
                    console.print("[yellow]You can find this by searching on https://www.animefillerlist.com/shows[/yellow]")
                    console.print("[yellow]Format example: 'code-geass' (use hyphens, all lowercase)[/yellow]")

                    afl_name = click.prompt("Enter AnimeFillerList show name")

                    add_mapping(afl_name, plex_direct_match)
        else:
            console.print("[bold red]Failed to fetch data from AnimeFillerList.[/bold red]")
            return

    # By this point, we should have both afl_name and either plex_name or plex_direct_match
    if not afl_name:
        console.print("[bold red]Failed to determine AnimeFillerList name.[/bold red]")
        return

    plex_show_name = plex_name or plex_direct_match
    if not plex_show_name:
        console.print("[bold red]Failed to determine Plex show name.[/bold red]")
        return

    console.print(f"[bold green]Using mapping: {afl_name} → {plex_show_name}[/bold green]")

    # Now call the original create_list function but with the AFL name
    # Get auth token
    access_token = trakt_auth.ensure_trakt_auth()
    if not access_token:
        return

    # Get TMDB ID from Plex
    tmdb_id = get_tmdb_id_from_plex(plex, afl_name)
    if not tmdb_id:
        return

    # Get Trakt show ID
    trakt_show_id = get_trakt_show_id(access_token, tmdb_id)
    if not trakt_show_id:
        return

    # Get episodes from AnimeFillerList
    anime_episodes = get_anime_episodes(afl_name, episode_type_filter)
    if not anime_episodes:
        console.print(f"[bold red]No episodes found for {afl_name} with type {episode_type_filter}[/bold red]")
        return

    # Display episodes that will be added
    console.print(f"\n[bold]Episodes to be added to Trakt list:[/bold]")
    for i, episode in enumerate(anime_episodes, 1):
        console.print(f"{i}. Episode {episode['number']}: {episode['name']} ({episode['type']})")

    # Create or get Trakt list
    trakt_list_name = get_list_name_format(afl_name, episode_type)
    list_id, list_exists = create_or_get_trakt_list(trakt_list_name, access_token)
    if not list_id:
        return

    # Add episodes to Trakt list
    success, has_failures, failure_info = add_episodes_to_trakt_list(
        list_id,
        anime_episodes,
        access_token,
        trakt_show_id,
        match_by,
        afl_name,
        episode_type.lower()
    )

    # Format URL correctly
    trakt_url = format_trakt_url(CONFIG['trakt']['username'], trakt_list_name)
    console.print(f"\n[bold green]🎉 List creation complete! 🎉[/bold green]")
    console.print(f"[blue]You can view your list at: {trakt_url}[/blue]")

    # Display failure message at the end if there were failures
    if has_failures and failure_info:
        console.print("\n[bold yellow]Some episodes could not be mapped:[/bold yellow]")
        console.print(f"[blue]Failures logged to {failure_info['log_file']}[/blue]")
        console.print("[yellow]To fix these mapping issues, run this command:[/yellow]")
        console.print("[green]docker compose run --rm dakosys fix-mappings[/green]")

    if not has_failures:
        try:
            from asset_manager import sync_anime_episode_collections
            console.print("[blue]Synchronizing collections file with Trakt lists...[/blue]")
            if sync_anime_episode_collections(CONFIG, force_update=True):
                console.print("[green]Collections synchronized successfully![/green]")
            else:
                console.print("[yellow]Failed to synchronize collections[/yellow]")
        except Exception as e:
            console.print(f"[red]Error synchronizing collections: {str(e)}[/red]")
            logger.error(f"Error synchronizing collections: {str(e)}")

def smart_create_all(anime_name):
    """Create lists for all episode types that exist for an anime."""
    # Clear the error log at the start
    clear_error_log()
    # All possible episode types
    episode_types = ['MANGA', 'FILLER', 'ANIME', 'MIXED']

    # Connect to Plex
    plex = connect_to_plex()
    if not plex:
        return

    # First check: Is this an AFL name with an existing mapping?
    afl_name = format_anime_name(anime_name)
    plex_name = CONFIG.get('mappings', {}).get(afl_name)

    if not afl_name or not plex_name:
        # Check reverse mapping (Plex title to AFL name)
        for afl_key, mapped_plex_title in CONFIG.get('mappings', {}).items():
            if mapped_plex_title.lower() == anime_name.lower():
                afl_name = afl_key
                plex_name = mapped_plex_title
                console.print(f"[green]Found existing mapping: {afl_name} → {plex_name}[/green]")
                break

    # Second check: Is this a Plex name? (direct match in Plex)
    plex_direct_match = None
    try:
        _libs = get_anime_libraries(plex)
        anime_library = _libs[0] if _libs else None
        for show in (anime_library.all() if anime_library else []):
            if show.title.lower() == anime_name.lower():
                plex_direct_match = show.title
                break
    except Exception as e:
        console.print(f"[bold red]Error accessing Plex library: {str(e)}[/bold red]")
        return

    # If we have neither an AFL mapping nor a direct Plex match, try fuzzy search in Plex
    if not plex_name and not plex_direct_match:
        console.print("[yellow]No exact mapping found. Searching for matches in Plex...[/yellow]")

        # Collect all Plex show titles
        plex_titles = [show.title for show in anime_library.all()]

        # Try to find matches
        potential_matches = []
        for title in plex_titles:
            # Check for exact match first
            if anime_name.lower() == title.lower():
                potential_matches.append((title, 1.0))
                continue

            # Check for match before colon (for titles like "Show Name: Subtitle")
            if ':' in title:
                before_colon = title.split(':', 1)[0].strip().lower()
                if anime_name.lower() == before_colon:
                    potential_matches.append((title, 0.95))  # Almost perfect match
                    continue

            # Use simple similarity ratio as a fallback
            similarity = difflib.SequenceMatcher(None, anime_name.lower(), title.lower()).ratio()
            if similarity > 0.6:  # Threshold for potential matches
                potential_matches.append((title, similarity))

        # Sort by similarity
        potential_matches.sort(key=lambda x: x[1], reverse=True)

        if potential_matches:
            console.print("[green]Found potential matches in your Plex library:[/green]")

            # Show options
            for i, (title, score) in enumerate(potential_matches[:5], 1):
                console.print(f"{i}. {title} [dim](similarity: {score*100:.0f}%)[/dim]")

            console.print("0. None of these - enter a different name")

            # Ask user to select
            choice = click.prompt("Select the correct show", type=int, default=1)

            if choice > 0 and choice <= len(potential_matches):
                plex_direct_match = potential_matches[choice-1][0]
            else:
                console.print("[yellow]No show selected. Exiting.[/yellow]")
                return
        else:
            console.print("[bold red]No matches found in your Plex library.[/bold red]")
            return

    # If we found a direct match in Plex but no mapping, create one
    if plex_direct_match and not plex_name:
        console.print(f"[green]Found direct match in Plex: {plex_direct_match}[/green]")

        # We need to find the corresponding AnimeFillerList name
        console.print("[bold blue]Fetching anime list from AnimeFillerList...[/bold blue]")
        base_url = 'https://www.animefillerlist.com/shows'
        response = requests.get(base_url)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            all_afl_shows = []

            # Find all anime links
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.startswith('/shows/'):
                    all_afl_shows.append(href.replace('/shows/', ''))

            # First try automatic matching
            afl_name = find_best_anime_match(plex_direct_match, all_afl_shows)

            if afl_name:
                # Automatic match found - confirm with user
                console.print(f"[bold green]Found match: {afl_name.replace('-', ' ')}[/bold green]")

                if click.confirm("Use this match?", default=True):
                    # User confirms, save the mapping
                    add_mapping(afl_name, plex_direct_match)
                else:
                    # User rejects automatic match - go to manual selection
                    afl_name = None

            if not afl_name:
                # No automatic match or user rejected it - show suggestions
                console.print("[yellow]Please select the correct AnimeFillerList show:[/yellow]")

                # Get suggestions
                suggestions = suggest_matches(plex_direct_match, all_afl_shows)

                if suggestions:
                    console.print("[green]Potential matches:[/green]")

                    # Show options
                    for i, (name, score) in enumerate(suggestions, 1):
                        console.print(f"{i}. {name.replace('-', ' ')} [dim](similarity: {score*100:.0f}%)[/dim]")

                    console.print("0. None of these - enter manually")

                    # Ask user to select
                    choice = click.prompt("Select the correct AnimeFillerList show", type=int, default=1)

                    if choice > 0 and choice <= len(suggestions):
                        afl_name = suggestions[choice-1][0]

                        add_mapping(afl_name, plex_direct_match)
                    else:
                        # Manual entry
                        console.print("\n[yellow]Please enter the correct AnimeFillerList show name.[/yellow]")
                        console.print("[yellow]You can find this by searching on https://www.animefillerlist.com/shows[/yellow]")
                        console.print("[yellow]Format example: 'code-geass' (use hyphens, all lowercase)[/yellow]")

                        afl_name = click.prompt("Enter AnimeFillerList show name")

                        add_mapping(afl_name, plex_direct_match)
                else:
                    # No suggestions
                    console.print("[yellow]No matches found. Please enter the correct AnimeFillerList show name.[/yellow]")
                    console.print("[yellow]You can find this by searching on https://www.animefillerlist.com/shows[/yellow]")
                    console.print("[yellow]Format example: 'code-geass' (use hyphens, all lowercase)[/yellow]")

                    afl_name = click.prompt("Enter AnimeFillerList show name")

                    add_mapping(afl_name, plex_direct_match)
        else:
            console.print("[bold red]Failed to fetch data from AnimeFillerList.[/bold red]")
            return

    # By this point, we should have both afl_name and either plex_name or plex_direct_match
    if not afl_name:
        console.print("[bold red]Failed to determine AnimeFillerList name.[/bold red]")
        return

    plex_show_name = plex_name or plex_direct_match
    if not plex_show_name:
        console.print("[bold red]Failed to determine Plex show name.[/bold red]")
        return

    console.print(f"[bold green]Using mapping: {afl_name} → {plex_show_name}[/bold green]")

    # Get auth token
    access_token = trakt_auth.ensure_trakt_auth()
    if not access_token:
        return

    # Get TMDB ID from Plex
    tmdb_id = get_tmdb_id_from_plex(plex, afl_name)
    if not tmdb_id:
        return

    # Get Trakt show ID
    trakt_show_id = get_trakt_show_id(access_token, tmdb_id)
    if not trakt_show_id:
        return

    # Iterate through each episode type and create lists for types that have episodes
    created_lists = []
    empty_types = []
    all_failures = []

    for episode_type in episode_types:
        episode_type_filter = {
            'FILLER': 'FILLER',
            'MANGA': 'MANGA CANON',
            'ANIME': 'ANIME CANON',
            'MIXED': 'MIXED CANON/FILLER',
        }.get(episode_type)

        # Get episodes from AnimeFillerList
        console.print(f"\n[bold blue]Checking for {episode_type} episodes...[/bold blue]")
        anime_episodes = get_anime_episodes(afl_name, episode_type_filter)

        if not anime_episodes or len(anime_episodes) == 0:
            console.print(f"[yellow]No {episode_type} episodes found for {afl_name}[/yellow]")
            empty_types.append(episode_type)
            continue

        # Display episodes that will be added
        console.print(f"\n[bold]Found {len(anime_episodes)} {episode_type} episodes:[/bold]")
        for i, episode in enumerate(anime_episodes[:5], 1):
            console.print(f"{i}. Episode {episode['number']}: {episode['name']} ({episode['type']})")

        if len(anime_episodes) > 5:
            console.print(f"... and {len(anime_episodes) - 5} more episodes")

        # Create or get Trakt list
        trakt_list_name = get_list_name_format(afl_name, episode_type)
        list_id, list_exists = create_or_get_trakt_list(trakt_list_name, access_token)
        if not list_id:
            continue

        # Add episodes to Trakt list
        success, has_failures, failure_info = add_episodes_to_trakt_list(
            list_id,
            anime_episodes,
            access_token,
            trakt_show_id,
            "hybrid",
            afl_name,
            episode_type.lower()
        )

        # Store failure info if there were failures
        if has_failures and failure_info:
            all_failures.append(failure_info)

        # Format URL correctly
        trakt_url = format_trakt_url(CONFIG['trakt']['username'], trakt_list_name)
        console.print(f"[green]List created: {trakt_url}[/green]")

        created_lists.append((episode_type, trakt_url, len(anime_episodes)))

    # Summary
    console.print("\n[bold green]🎉 List creation complete! 🎉[/bold green]")

    if created_lists:
        console.print("\n[bold]Created lists:[/bold]")
        for episode_type, url, count in created_lists:
            console.print(f"[green]✓ {episode_type}: {count} episodes - {url}[/green]")

        # Add to scheduled anime list in config
        config = CONFIG

        if 'scheduler' not in config:
            config['scheduler'] = {}

        if 'scheduled_anime' not in config['scheduler']:
            config['scheduler']['scheduled_anime'] = []

        # Check if already scheduled
        already_scheduled = False
        if 'scheduler' in config and 'scheduled_anime' in config['scheduler']:
            # Make sure scheduled_anime is not None and is iterable
            if config['scheduler']['scheduled_anime'] is not None:
                if afl_name in config['scheduler']['scheduled_anime']:
                    already_scheduled = True
            else:
                # Initialize as empty list if it's None
                config['scheduler']['scheduled_anime'] = []
        else:
            # Initialize scheduler and scheduled_anime if they don't exist
            if 'scheduler' not in config:
                config['scheduler'] = {}
            config['scheduler']['scheduled_anime'] = []

        # Not scheduled yet, ask if they want to add it
        if not already_scheduled:
            # Ask if they want to add it
            if click.confirm(f"\nWould you like to add '{plex_show_name}' to the automatic update schedule?", default=True):
                # Add to scheduled anime list
                config['scheduler']['scheduled_anime'].append(afl_name)

                # Create a config copy without mappings
                config_to_save = config.copy()
                if 'mappings' in config_to_save:
                    del config_to_save['mappings']
                if 'trakt_mappings' in config_to_save:
                    del config_to_save['trakt_mappings']
                if 'title_mappings' in config_to_save:
                    del config_to_save['title_mappings']

                # Save the cleaned config
                config_path = "/app/config/config.yaml" if os.environ.get('RUNNING_IN_DOCKER') == 'true' else "config/config.yaml"
                with open(config_path, 'w') as file:
                    yaml.dump(config_to_save, file)

                console.print(f"[bold green]Added '{plex_show_name}' to automatic update schedule![/bold green]")
            else:
                console.print(f"[yellow]'{plex_show_name}' will not be automatically updated.[/yellow]")

    if empty_types:
        console.print("\n[bold]Episode types with no episodes:[/bold]")
        for episode_type in empty_types:
            console.print(f"[yellow]✗ {episode_type}: No episodes found[/yellow]")

    if created_lists:
        try:
            from asset_manager import sync_anime_episode_collections
            console.print("[blue]Synchronizing collections file with Trakt lists...[/blue]")
            if sync_anime_episode_collections(CONFIG, force_update=True):
                console.print("[green]Collections synchronized successfully![/green]")
                # Show the path to the updated file for the user
                collections_dir = CONFIG.get('services', {}).get('tv_status_tracker', {}).get('collections_dir', '/kometa/config/collections')
                collections_file = os.path.join(collections_dir, 'anime_episode_type.yml')
                console.print(f"[blue]Updated file: {collections_file}[/blue]")
            else:
                console.print("[yellow]Failed to synchronize collections[/yellow]")
        except Exception as e:
            console.print(f"[red]Error synchronizing collections: {str(e)}[/red]")
            logger.error(f"Error synchronizing collections: {str(e)}")

    # Display failure message at the end if there were failures
    if all_failures:
        console.print("\n[bold yellow]Some episodes could not be mapped:[/bold yellow]")
        console.print(f"[blue]Failures logged to {all_failures[0]['log_file']}[/blue]")
        console.print("[yellow]To fix these mapping issues, run this command:[/yellow]")
        console.print("[green]docker compose run --rm dakosys fix-mappings[/green]")

@cli.command(name="create-all")
@click.argument('anime_name')
def create_all_lists(anime_name):
    """Create lists for all episode types (FILLER, MANGA, ANIME, MIXED) with episodes.

    ANIME_NAME: Name of the anime (e.g. 'one-piece' or 'Attack on Titan')
    """
    smart_create_all(anime_name)

@cli.command()
@click.argument('action', type=click.Choice(['list', 'add', 'remove']))
@click.argument('anime_name', required=False)
def schedule(action, anime_name=None):
    """Manage which anime are automatically updated.

    ACTION: list, add, or remove
    ANIME_NAME: Name of anime (required for add/remove)
    """
    config = CONFIG

    # Ensure scheduler and scheduled_anime exist
    if 'scheduler' not in config:
        config['scheduler'] = {}

    if 'scheduled_anime' not in config['scheduler']:
        config['scheduler']['scheduled_anime'] = []

    # List currently scheduled anime
    if action == 'list':
        scheduled = config['scheduler']['scheduled_anime']
        console.print(f"[bold]Currently scheduled anime ({len(scheduled)}):[/bold]")

        table = Table(show_header=True, header_style="bold")
        table.add_column("AnimeFillerList Name")
        table.add_column("Plex Title")

        for afl_name in scheduled:
            plex_name = config.get('mappings', {}).get(afl_name, afl_name)
            # Prettify the AFL name
            display_name = afl_name.replace('-', ' ').title()
            table.add_row(display_name, plex_name)

        console.print(table)

    # Add an anime to schedule
    elif action == 'add':
        if not anime_name:
            console.print("[bold red]Error: Anime name is required for add action[/bold red]")
            return

        # Try to find in mappings first (Plex name)
        afl_name = None
        for name, plex_title in config.get('mappings', {}).items():
            if plex_title.lower() == anime_name.lower():
                afl_name = name
                break

        # If not found, try direct match with AFL name format
        if not afl_name:
            afl_name = format_anime_name(anime_name)

            # Verify this AFL name exists in mappings
            if afl_name not in config.get('mappings', {}):
                console.print(f"[yellow]Warning: '{anime_name}' not found in your mappings.[/yellow]")
                console.print(f"[yellow]Adding anyway as '{afl_name}', but it won't update until mapped.[/yellow]")

        # Add to scheduled list if not already there
        if afl_name not in config['scheduler']['scheduled_anime']:
            config['scheduler']['scheduled_anime'].append(afl_name)

            # Create a config copy without mappings
            config_to_save = config.copy()
            if 'mappings' in config_to_save:
                del config_to_save['mappings']
            if 'trakt_mappings' in config_to_save:
                del config_to_save['trakt_mappings']
            if 'title_mappings' in config_to_save:
                del config_to_save['title_mappings']

            # Save the cleaned config
            config_path = "/app/config/config.yaml" if os.environ.get('RUNNING_IN_DOCKER') == 'true' else CONFIG_FILE
            with open(config_path, 'w') as file:
                yaml.dump(config_to_save, file)

            console.print(f"[bold green]Added '{anime_name}' to automatic update schedule![/bold green]")
        else:
            console.print(f"[blue]'{anime_name}' is already in the automatic update schedule.[/blue]")

    # Remove an anime from schedule
    elif action == 'remove':
        if not anime_name:
            console.print("[bold red]Error: Anime name is required for remove action[/bold red]")
            return

        # Try to find in mappings first (Plex name)
        afl_name = None
        for name, plex_title in config.get('mappings', {}).items():
            if plex_title.lower() == anime_name.lower():
                afl_name = name
                break

        # If not found, try direct match with AFL name format
        if not afl_name:
            afl_name = format_anime_name(anime_name)

        # Remove from scheduled list
        if afl_name in config['scheduler']['scheduled_anime']:
            config['scheduler']['scheduled_anime'].remove(afl_name)

            # Create a config copy without mappings
            config_to_save = config.copy()
            if 'mappings' in config_to_save:
                del config_to_save['mappings']
            if 'trakt_mappings' in config_to_save:
                del config_to_save['trakt_mappings']
            if 'title_mappings' in config_to_save:
                del config_to_save['title_mappings']

            # Save the cleaned config
            config_path = "/app/config/config.yaml" if os.environ.get('RUNNING_IN_DOCKER') == 'true' else CONFIG_FILE
            with open(config_path, 'w') as file:
                yaml.dump(config_to_save, file)

            console.print(f"[bold green]Removed '{anime_name}' from automatic update schedule![/bold green]")
        else:
            console.print(f"[yellow]'{anime_name}' is not in the automatic update schedule.[/yellow]")

@cli.command()
def fix_mappings():
    """Interactive tool to fix mapping errors from previous runs."""
    try:
        console.print("[bold blue]Loading mapping errors from logs...[/bold blue]")

        # Load from failed episodes log
        data_dir = DATA_DIR
        if os.environ.get('RUNNING_IN_DOCKER') == 'true':
            data_dir = "/app/data"

        log_file = os.path.join(data_dir, "failed_episodes.log")

        if not os.path.exists(log_file):
            console.print("[yellow]No mapping errors found in logs.[/yellow]")
            return

        # Parse the log file to extract mapping errors
        current_entry = {}
        entries = []

        with open(log_file, 'r') as f:
            for line in f:
                line = line.strip()

                if line.startswith('---'):
                    if current_entry and 'anime' in current_entry and 'episodes' in current_entry:
                        entries.append(current_entry)
                    current_entry = {'episodes': [], 'details': []}
                elif line.startswith('Anime:'):
                    current_entry['anime'] = line.replace('Anime:', '').strip()
                elif line.startswith('Episode Type:'):
                    current_entry['type'] = line.replace('Episode Type:', '').strip()

                    # Extract the real episode type from various formats
                    if current_entry['type'] == 'unknown' or current_entry['type'] == 'UNKNOWN':
                        # Try to find the type in the list of episodes - this might give clues
                        # Don't do anything here - we'll try to determine it later
                        pass
                    elif 'anime' in current_entry['type'].lower():
                        current_entry['trakt_type'] = 'ANIME'
                    elif 'manga' in current_entry['type'].lower():
                        current_entry['trakt_type'] = 'MANGA'
                    elif 'filler' in current_entry['type'].lower():
                        current_entry['trakt_type'] = 'FILLER'
                    elif 'mixed' in current_entry['type'].lower():
                        current_entry['trakt_type'] = 'MIXED'

                elif line.startswith('Failed Episodes:'):
                    continue  # Skip the count line
                elif line.startswith('Details:'):
                    in_details = True
                elif line.startswith('-') and 'details' in current_entry:
                    current_entry['details'].append(line[2:].strip())
                elif line and line[0].isdigit() and '.' in line and 'episodes' in current_entry:
                    episode = line.split('.', 1)[1].strip()
                    current_entry['episodes'].append(episode)

        # Add the last entry if it exists
        if current_entry and 'anime' in current_entry and 'episodes' in current_entry:
            entries.append(current_entry)

        if not entries:
            console.print("[yellow]No valid mapping errors found in logs.[/yellow]")
            return

        # Display the entries
        console.print(f"[bold green]Found {len(entries)} sets of mapping errors[/bold green]")

        # Group by anime
        anime_groups = {}
        for entry in entries:
            anime_name = entry['anime']
            if anime_name not in anime_groups:
                anime_groups[anime_name] = []
            anime_groups[anime_name].append(entry)

        # Track if anything was fixed
        fixed_any = False

        # Display and prompt for each anime
        for anime_name, group in anime_groups.items():
            console.print(f"\n[bold]Mapping errors for: {anime_name}[/bold]")

            # Show reference URLs to help with mapping
            afl_url = f"https://www.animefillerlist.com/shows/{anime_name}"
            console.print(f"[blue]AnimeFillerList URL: {afl_url}[/blue]")

            # Get the mapped Plex name for this anime
            plex_name = None
            try:
                # Try to get from mappings_manager first
                import mappings_manager
                mappings = mappings_manager.load_mappings()
                plex_name = mappings.get('mappings', {}).get(anime_name)
            except Exception as e:
                # Fall back to CONFIG if mappings_manager fails
                plex_name = CONFIG.get('mappings', {}).get(anime_name)

            if not plex_name:
                # If still no mapping, use the anime_name directly
                plex_name = anime_name

            # Try to get the Trakt URL for this anime
            trakt_url = None
            try:
                # Get Trakt slug from Plex & Trakt
                access_token = trakt_auth.ensure_trakt_auth(quiet=True)
                if access_token:
                    plex = connect_to_plex()
                    if plex:
                        # Use the Plex name to look up the TMDB ID
                        logger.info(f"Looking for '{plex_name}' in Plex libraries...")
                        tmdb_id = None

                        try:
                            _libs = get_anime_libraries(plex)
                            anime_library = _libs[0] if _libs else None
                            for show in (anime_library.all() if anime_library else []):
                                if show.title.lower() == plex_name.lower():
                                    for guid in show.guids:
                                        if 'tmdb://' in guid.id:
                                            tmdb_id = guid.id.split('//')[1]
                                            logger.info(f"Found TMDB ID: {tmdb_id}")
                                            break
                                    if tmdb_id:
                                        break
                        except Exception as e:
                            logger.error(f"Error searching Plex: {str(e)}")

                        if tmdb_id:
                            trakt_show_id = get_trakt_show_id(access_token, tmdb_id)
                            if trakt_show_id:
                                # Get show info to get the slug
                                headers = trakt_auth.get_trakt_headers(access_token)
                                trakt_api_url = 'https://api.trakt.tv'
                                show_url = f"{trakt_api_url}/shows/{trakt_show_id}?extended=full"
                                response = requests.get(show_url, headers=headers)

                                if response.status_code == 200:
                                    show_data = response.json()
                                    trakt_slug = show_data.get('ids', {}).get('slug')
                                    if trakt_slug:
                                        trakt_url = f"https://trakt.tv/shows/{trakt_slug}/seasons/all"
                        else:
                            console.print(f"[yellow]Could not find TMDB ID for '{plex_name}' in any Plex library.[/yellow]")
            except Exception as e:
                # Ignore errors in getting URLs
                pass

            if trakt_url:
                console.print(f"[blue]Trakt Seasons URL: {trakt_url}[/blue]")

            # Count total failed episodes
            total_episodes = sum(len(entry['episodes']) for entry in group)
            console.print(f"Total failed episodes: {total_episodes}")

            # Display sample episodes
            sample_episodes = []
            for entry in group[:2]:  # Show at most 2 groups
                for episode in entry['episodes'][:3]:  # Show at most 3 episodes per group
                    sample_episodes.append(episode)

            if sample_episodes:
                console.print("[bold]Sample failed episodes:[/bold]")
                for i, episode in enumerate(sample_episodes, 1):
                    console.print(f"{i}. {episode}")

            # Prompt for action
            if click.confirm(f"Would you like to fix mappings for {anime_name}?", default=True):
                # For each group (episode type)
                for entry in group:
                    # Determine actual episode type if it's unknown
                    if entry.get('type', '').lower() == 'unknown' and not entry.get('trakt_type'):
                        # First try to infer from mapping types
                        inferred_type = None

                        # Try to get Trakt lists for this anime
                        try:
                            access_token = trakt_auth.ensure_trakt_auth(quiet=True)
                            if access_token:
                                headers = trakt_auth.get_trakt_headers(access_token)
                                trakt_api_url = 'https://api.trakt.tv'
                                lists_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists"
                                response = requests.get(lists_url, headers=headers)

                                if response.status_code == 200:
                                    lists = response.json()
                                    # Look for lists with this anime name
                                    for lst in lists:
                                        list_name = lst.get('name', '')
                                        if anime_name in list_name:
                                            # Extract the type from the list name
                                            if '_' in list_name:
                                                list_type = list_name.split('_', 1)[1]
                                                if 'anime' in list_type.lower():
                                                    inferred_type = 'ANIME'
                                                    break
                                                elif 'manga' in list_type.lower():
                                                    inferred_type = 'MANGA'
                                                    break
                                                elif 'filler' in list_type.lower():
                                                    inferred_type = 'FILLER'
                                                    break
                                                elif 'mixed' in list_type.lower():
                                                    inferred_type = 'MIXED'
                                                    break
                        except Exception as e:
                            # Ignore errors in getting lists
                            pass

                        # If we couldn't infer, check the episodes for patterns
                        if not inferred_type:
                            # For Code Geass - episodes with "Stage" or "Turn" are likely anime canon
                            stage_count = 0
                            turn_count = 0
                            for ep in entry['episodes']:
                                if 'stage' in ep.lower():
                                    stage_count += 1
                                if 'turn' in ep.lower():
                                    turn_count += 1

                            if stage_count > 0 or turn_count > 0:
                                inferred_type = 'ANIME'

                        # If still no type, prompt the user
                        if not inferred_type:
                            console.print(f"[yellow]Could not determine episode type for {anime_name}[/yellow]")
                            console.print("Please select the episode type:")
                            console.print("1. ANIME (canon anime episodes)")
                            console.print("2. MANGA (manga canon episodes)")
                            console.print("3. FILLER (filler episodes)")
                            console.print("4. MIXED (mixed canon/filler episodes)")

                            type_choice = click.prompt("Enter type (1-4)", type=int, default=1)
                            type_map = {1: 'ANIME', 2: 'MANGA', 3: 'FILLER', 4: 'MIXED'}
                            inferred_type = type_map.get(type_choice, 'ANIME')

                        entry['trakt_type'] = inferred_type
                        console.print(f"[green]Using episode type: {inferred_type}[/green]")

                    console.print(f"\n[bold]Fixing {entry.get('trakt_type', entry.get('type', 'unknown').upper())} episodes for {anime_name}[/bold]")

                    # Manual mappings
                    console.print("[yellow]Let's create manual mappings for these episodes.[/yellow]")
                    console.print("[dim]For each failed episode, enter the correct Trakt title.[/dim]")
                    console.print("[dim]Leave blank to skip an episode.[/dim]")

                    # Show how many episodes to map
                    console.print(f"[yellow]{len(entry['episodes'])} episodes need mapping[/yellow]")

                    # Ask how many to fix in this session
                    max_to_fix = click.prompt(
                        "How many episodes would you like to fix now?",
                        default=min(10, len(entry['episodes'])),
                        type=int
                    )

                    # Prompt for each episode
                    manual_mappings = {}
                    for i, episode in enumerate(entry['episodes'][:max_to_fix], 1):
                        console.print(f"[{i}/{max_to_fix}] Episode: {episode}")
                        trakt_name = click.prompt(f"Enter the correct Trakt title", default="")
                        if trakt_name:
                            manual_mappings[episode] = trakt_name

                    if manual_mappings:
                        # Create mapping configuration with manual mappings
                        create_title_mapping(anime_name, manual_mappings)
                        console.print(f"[bold green]Created {len(manual_mappings)} manual mappings![/bold green]")
                    else:
                        console.print("[yellow]No mappings were created.[/yellow]")

                    # Ask if they want to re-run the list creation
                    if manual_mappings and click.confirm(f"Would you like to regenerate the {entry.get('trakt_type', entry.get('type', 'unknown'))} list for {anime_name} now?", default=True):
                        # Get the correct episode type for create-list
                        actual_type = entry.get('trakt_type', entry.get('type', 'unknown').upper())
                        console.print(f"[bold blue]Regenerating {actual_type} list for {anime_name}...[/bold blue]")

                        reload_config()

                        # Check if we're running in Docker
                        if os.environ.get('RUNNING_IN_DOCKER') == 'true':
                            # In Docker, call the internal function directly
                            console.print("[yellow]Running inside Docker container, calling internal create_list function...[/yellow]")
                            success = _create_list_internal(anime_name, actual_type, "hybrid")
                            if success:
                                console.print("[bold green]List regenerated successfully with no mapping errors![/bold green]")
                            else:
                                console.print("[yellow]List regenerated but there may still be some mapping issues.[/yellow]")
                        else:
                            # Not in Docker, run Docker command
                            import subprocess
                            cmd = f"docker compose run --rm dakosys create-list {anime_name} {actual_type}"
                            console.print(f"[dim]Running: {cmd}[/dim]")
                            subprocess.run(cmd, shell=True)
                            success = True
                            console.print("[bold green]List regenerated![/bold green]")

                        # Clean error log regardless
                        clean_error_log(anime_name, entry['type'], list(manual_mappings.keys()))
                        console.print("[green]Cleaned fixed entries from error log.[/green]")

                fixed_any = True
                console.print(f"[bold green]Finished fixing mappings for {anime_name}[/bold green]")
            else:
                console.print(f"[yellow]Skipped fixing {anime_name}[/yellow]")

        # Only show completion if we fixed something
        if fixed_any:
            console.print("[bold green]Mapping fix process complete![/bold green]")
        else:
            console.print("[yellow]No mappings were fixed. Run again later when ready to fix.[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error fixing mappings: {str(e)}[/bold red]")
        import traceback
        console.print(traceback.format_exc())

def add_mapping(afl_name, plex_direct_match):
    """Add a mapping from AFL name to Plex name and save it to mappings.yaml."""
    import mappings_manager

    # Add the mapping using mappings_manager
    success = mappings_manager.add_plex_mapping(afl_name, plex_direct_match)

    if success:
        # Also update CONFIG for the current session
        if not CONFIG.get('mappings'):
            CONFIG['mappings'] = {}

        CONFIG['mappings'][afl_name] = plex_direct_match
        console.print(f"[bold green]Added mapping: {afl_name} → {plex_direct_match}[/bold green]")
        return True
    else:
        console.print(f"[bold red]Failed to add mapping to mappings.yaml: {afl_name} → {plex_direct_match}[/bold red]")
        console.print("[yellow]Continuing anyway with temporary mapping[/yellow]")

        # Still update CONFIG for the current session even if saving failed
        if not CONFIG.get('mappings'):
            CONFIG['mappings'] = {}

        CONFIG['mappings'][afl_name] = plex_direct_match
        return False

def create_title_mapping(anime_name, manual_mappings=None):
    """Create or update title mappings in the configuration."""
    try:
        # Directly import and use mappings_manager
        import mappings_manager
        # For each mapping, call the add_title_mapping function
        success = True
        if manual_mappings:
            for original, mapped in manual_mappings.items():
                if not mappings_manager.add_title_mapping(anime_name, original, mapped):
                    success = False
                    logger.error(f"Failed to add mapping: {original} -> {mapped}")
        return success
    except ImportError as e:
        logger.error(f"Error importing mappings_manager: {str(e)}")
        console.print("[yellow]mappings_manager module not found, falling back to direct file update[/yellow]")
        # Fallback to direct file
        try:
            # Always use mappings.yaml
            if os.environ.get('RUNNING_IN_DOCKER') == 'true':
                mappings_file = "/app/config/mappings.yaml"
            else:
                mappings_file = "config/mappings.yaml"

            # Create directory if needed
            os.makedirs(os.path.dirname(mappings_file), exist_ok=True)

            # Load existing mappings or create new
            mappings = {}
            if os.path.exists(mappings_file):
                with open(mappings_file, 'r') as file:
                    mappings = yaml.safe_load(file) or {}

            # Initialize if needed
            if 'title_mappings' not in mappings:
                mappings['title_mappings'] = {}
            if anime_name not in mappings['title_mappings']:
                mappings['title_mappings'][anime_name] = {}
            if 'special_matches' not in mappings['title_mappings'][anime_name]:
                mappings['title_mappings'][anime_name]['special_matches'] = {}

            # Add mappings
            for original, mapped in manual_mappings.items():
                mappings['title_mappings'][anime_name]['special_matches'][original] = mapped

            # Save to mappings.yaml
            with open(mappings_file, 'w') as file:
                yaml.dump(mappings, file)

            console.print(f"[green]Saved {len(manual_mappings)} title mappings to mappings.yaml[/green]")
            return True

        except Exception as e:
            logger.error(f"Error in create_title_mapping fallback: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    except Exception as e:
        logger.error(f"Error in create_title_mapping: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def clear_error_log():

    """Clear the error log file at the start of a new run."""
    try:
        data_dir = DATA_DIR
        if os.environ.get('RUNNING_IN_DOCKER') == 'true':
            data_dir = "/app/data"

        log_file = os.path.join(data_dir, "failed_episodes.log")

        # Create directory if it doesn't exist
        os.makedirs(data_dir, exist_ok=True)

        # Create empty log file (overwriting any existing one)
        with open(log_file, 'w') as f:
            f.write(f"# Mapping errors log - Created {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    except Exception as e:
        logger.error(f"Error clearing error log: {str(e)}")

@cli.command()
@click.argument('service', required=False, type=click.Choice(['anime_episode_type', 'tv_status_tracker', 'size_overlay', 'all']))
def run_update(service=None):
    """Run an immediate update of services.

    SERVICE: Optional service to update (anime_episode_type, tv_status_tracker, size_overlay, or all)
    """
    try:
        from auto_update import run_tv_status_update, run_size_overlay_update
        import logging

        # Configure a console handler to display logs
        logger = logging.getLogger("auto_update")
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')  # Simplified format for console
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # Parse which services to run
        if service and service != 'all':
            console.print(f"[bold blue]Running immediate update of {service} service...[/bold blue]")
        else:
            console.print("[bold blue]Running immediate update of all enabled services...[/bold blue]")

        # Show service status
        config = CONFIG
        if not service or service == 'all' or service == 'anime_episode_type':
            anime_enabled = config.get('services', {}).get('anime_episode_type', {}).get('enabled', True)
            if anime_enabled:
                console.print("[yellow]Anime Episode Type service is enabled[/yellow]")
            else:
                console.print("[yellow]Anime Episode Type service is disabled in config[/yellow]")

        if not service or service == 'all' or service == 'tv_status_tracker':
            tv_enabled = config.get('services', {}).get('tv_status_tracker', {}).get('enabled', False)
            if tv_enabled:
                console.print("[yellow]TV Status Tracker service is enabled[/yellow]")
            else:
                console.print("[yellow]TV Status Tracker service is disabled in config[/yellow]")
                
        if not service or service == 'all' or service == 'size_overlay':
            size_enabled = config.get('services', {}).get('size_overlay', {}).get('enabled', False)
            if size_enabled:
                console.print("[yellow]Size Overlay service is enabled[/yellow]")
            else:
                console.print("[yellow]Size Overlay service is disabled in config[/yellow]")

        # Keep track of successful updates
        success_count = 0

        # Run anime episode type updates using the ALL command logic
        if (not service or service == 'all' or service == 'anime_episode_type') and anime_enabled:
            scheduled_anime = config.get('scheduler', {}).get('scheduled_anime', [])
            console.print(f"[bold]Updating {len(scheduled_anime)} scheduled anime using ALL command:[/bold]")

            for anime_name in scheduled_anime:
                try:
                    console.print(f"[blue]Processing {anime_name}...[/blue]")
                    # Use the smart_create_all function that we know works
                    smart_create_all(anime_name)
                    success_count += 1
                except Exception as e:
                    console.print(f"[red]Error updating {anime_name}: {str(e)}[/red]")
                    import traceback
                    console.print(traceback.format_exc())

            console.print(f"[green]Successfully updated {success_count} of {len(scheduled_anime)} anime[/green]")

        # Run TV status tracker updates using the original logic
        if (not service or service == 'all' or service == 'tv_status_tracker') and tv_enabled:
            console.print("[bold blue]Running TV Status Tracker updates...[/bold blue]")
            if run_tv_status_update():
                console.print("[green]TV Status Tracker updated successfully[/green]")
                success_count += 1
            else:
                console.print("[red]TV Status Tracker update failed[/red]")
                
        # Run Size Overlay updates
        if (not service or service == 'all' or service == 'size_overlay') and size_enabled:
            console.print("[bold blue]Running Size Overlay updates...[/bold blue]")
            if run_size_overlay_update():
                console.print("[green]Size Overlay updated successfully[/green]")
                success_count += 1
            else:
                console.print("[red]Size Overlay update failed[/red]")

        console.print("[bold green]Update completed![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error running update: {str(e)}[/bold red]")

def delete_list_implementation(anime_name, episode_type, all_types, force):
    """Implementation of list deletion logic that can be called by multiple commands."""
    # Try to find in mappings first (Plex name)
    afl_name = None
    for name, plex_title in CONFIG.get('mappings', {}).items():
        if plex_title.lower() == anime_name.lower():
            afl_name = name
            break

    # If not found, try direct match with AFL name format
    if not afl_name:
        afl_name = format_anime_name(anime_name)

    # Get display name for messages
    plex_name = CONFIG.get('mappings', {}).get(afl_name, afl_name)
    if '-' in plex_name:
        plex_name = plex_name.replace('-', ' ').title()

    # Get auth token
    access_token = trakt_auth.ensure_trakt_auth()
    if not access_token:
        return

    # Get all Trakt lists
    headers = trakt_auth.get_trakt_headers(access_token)
    if not headers:
        console.print("[bold red]Failed to get Trakt API headers[/bold red]")
        return

    trakt_api_url = 'https://api.trakt.tv'
    lists_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists"

    response = requests.get(lists_url, headers=headers)
    if response.status_code != 200:
        console.print(f"[bold red]Failed to get Trakt lists. Status: {response.status_code}[/bold red]")
        return

    trakt_lists = response.json()

    # Find the lists to delete
    lists_to_delete = []

    for trakt_list in trakt_lists:
        name = trakt_list['name']
        # Match the list name format
        if name.startswith(afl_name + '_'):
            # If deleting all lists or this specific type
            if all_types or (episode_type and name == get_list_name_format(afl_name, episode_type)):
                lists_to_delete.append((trakt_list['ids']['trakt'], name))

    if not lists_to_delete:
        console.print(f"[yellow]No matching lists found for {plex_name}[/yellow]")
        return

    # Show lists that will be deleted
    console.print(f"\n[bold]Lists to delete for {plex_name}:[/bold]")
    list_types = []
    for list_id, list_name in lists_to_delete:
        # Extract the type from the name
        list_type = list_name.split('_', 1)[1] if '_' in list_name else 'unknown'
        list_types.append(list_type)
        console.print(f"- {list_type}")

    # Confirm deletion
    if not force and not click.confirm("Are you sure you want to delete these lists?", default=False):
        console.print("[yellow]Deletion canceled.[/yellow]")
        return

    # Delete the lists
    deleted_count = 0
    deleted_lists = []
    for list_id, list_name in lists_to_delete:
        delete_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists/{list_id}"
        response = requests.delete(delete_url, headers=headers)

        if response.status_code == 204:  # 204 No Content is success for DELETE
            deleted_count += 1
            list_type = list_name.split('_', 1)[1] if '_' in list_name else 'unknown'
            deleted_lists.append(list_type)
            console.print(f"[green]Deleted list: {list_name}[/green]")
        else:
            console.print(f"[red]Failed to delete list {list_name}. Status: {response.status_code}[/red]")

    console.print(f"\n[bold green]Deleted {deleted_count} of {len(lists_to_delete)} lists for {plex_name}[/bold green]")

    # Send Discord notification
    if deleted_count > 0:
        try:
            from notifications import send_discord_notification

            title = f"Lists Deleted: {plex_name}"
            message = f"Deleted {deleted_count} list(s) for {plex_name}"

            # Use the new deleted_items parameter
            send_discord_notification(
                title,
                message,
                deleted_items=deleted_lists,
                color=16754470  # Orange color
            )
            console.print("[green]Sent deletion notification to Discord[/green]")
        except Exception as e:
            console.print(f"[yellow]Error sending Discord notification: {str(e)}[/yellow]")

    if deleted_count > 0:
        # Sync collections after successful deletions
        try:
            from asset_manager import sync_anime_episode_collections
            console.print("[blue]Synchronizing collections file after deletion...[/blue]")
            if sync_anime_episode_collections(CONFIG, force_update=True):
                console.print("[green]Collections synchronized successfully[/green]")
            else:
                console.print("[yellow]Failed to synchronize collections after deletion[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Error synchronizing collections: {str(e)}[/yellow]")

    # If this anime is in scheduled list, ask if it should be removed
    scheduled_anime = CONFIG.get('scheduler', {}).get('scheduled_anime', [])
    if afl_name in scheduled_anime and (all_types or deleted_count > 0):
        # When using force flag, automatically remove from scheduler without asking
        should_remove = force or click.confirm(f"Do you want to remove {plex_name} from the scheduler?", default=False)

        if should_remove:
            # Remove from scheduled list
            scheduled_anime.remove(afl_name)

            # Create a config copy without mappings
            config_to_save = CONFIG.copy()
            if 'mappings' in config_to_save:
                del config_to_save['mappings']
            if 'trakt_mappings' in config_to_save:
                del config_to_save['trakt_mappings']
            if 'title_mappings' in config_to_save:
                del config_to_save['title_mappings']
            
            # Save the cleaned config
            config_path = "/app/config/config.yaml" if os.environ.get('RUNNING_IN_DOCKER') == 'true' else CONFIG_FILE
            with open(config_path, 'w') as file:
                yaml.dump(config_to_save, file)

            console.print(f"[green]Removed {plex_name} from scheduler.[/green]")

            # Send scheduler removal notification
            try:
                from notifications import send_discord_notification

                title = f"Scheduler Update: {plex_name}"
                message = f"Removed {plex_name} from automatic update schedule"

                send_discord_notification(
                    title,
                    message,
                    color=16754470  # Orange color
                )
            except Exception as e:
                console.print(f"[yellow]Error sending scheduler notification: {str(e)}[/yellow]")

@cli.command()
@click.argument('anime_name')
@click.argument('episode_type', type=click.Choice(['FILLER', 'MANGA', 'ANIME', 'MIXED'], case_sensitive=False), required=False)
@click.option('--all', is_flag=True, help='Delete all lists for this anime')
@click.option('--force', is_flag=True, help='Delete without confirmation')
def delete_list(anime_name, episode_type, all, force):
    """Delete a Trakt list.

    ANIME_NAME: Name of the anime (e.g. 'one-piece', 'Attack on Titan')
    EPISODE_TYPE: Type of list to delete (FILLER, MANGA, ANIME, MIXED)
    """
    delete_list_implementation(anime_name, episode_type, all, force)

@cli.command()
@click.argument('anime_name')
@click.argument('episode_type', required=False)
@click.option('--force', is_flag=True, help='Delete without confirmation')
def delete_piped(anime_name, episode_type, force):
    """Delete a list from piped input.

    This command is designed to work with piped input from list-lists --format plain

    Example: list-lists --format plain --anime "Boruto" | xargs -n2 docker compose run --rm dakosys delete_piped --force
    """
    # Map standardized episode types to the format needed for get_list_name_format
    if episode_type:
        if episode_type == 'FILLER':
            std_episode_type = 'FILLER'
        elif episode_type == 'MANGA':
            std_episode_type = 'MANGA'
        elif episode_type == 'ANIME':
            std_episode_type = 'ANIME'
        elif episode_type == 'MIXED':
            std_episode_type = 'MIXED'
        else:
            console.print(f"[yellow]Unrecognized episode type: {episode_type}. Using as-is.[/yellow]")
            std_episode_type = episode_type
    else:
        std_episode_type = None

    # Call the implementation function
    delete_list_implementation(anime_name, std_episode_type, False, force)

@cli.command()
@click.option('--format', type=click.Choice(['table', 'plain', 'json']), default='table',
              help='Output format (table=visual, plain=pipeable, json=machine readable)')
@click.option('--filter', help='Filter lists by name')
@click.option('--anime', help='Show only lists for a specific anime')
@click.option('--all', is_flag=True, help='Show all lists including non-project lists')
def list_lists(format, filter, anime, all):
    """List all Trakt lists.

    By default, only shows lists created by this application.
    Use --all to show all Trakt lists including personal ones.

    Can be piped to other commands using --format plain
    Example: docker compose run --rm dakosys list-lists --format plain --anime "Naruto" | xargs -I{} docker compose run --rm dakosys delete-list {} --force
    """
    # Get auth token
    access_token = trakt_auth.ensure_trakt_auth(quiet=True if format != 'table' else False)
    if not access_token:
        if format == 'json':
            print(json.dumps({"error": "Failed to get auth token"}))
        else:
            console.print("[bold red]Failed to get auth token[/bold red]")
        return

    # Get all Trakt lists
    headers = trakt_auth.get_trakt_headers(access_token)
    if not headers:
        if format == 'json':
            print(json.dumps({"error": "Failed to get API headers"}))
        else:
            console.print("[bold red]Failed to get Trakt API headers[/bold red]")
        return

    trakt_api_url = 'https://api.trakt.tv'
    lists_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists"

    response = requests.get(lists_url, headers=headers)
    if response.status_code != 200:
        if format == 'json':
            print(json.dumps({"error": f"Failed to get lists: {response.status_code}"}))
        else:
            console.print(f"[bold red]Failed to get Trakt lists. Status: {response.status_code}[/bold red]")
        return

    trakt_lists = response.json()

    # Count filtered lists before project filtering for accurate hidden count
    filtered_lists = []
    for trakt_list in trakt_lists:
        name = trakt_list['name']

        # Apply text filter if provided
        if filter and filter.lower() not in name.lower():
            continue

        # If looking for a specific anime
        if anime:
            # Try to match Plex name to AFL name
            afl_name = None
            for name_key, plex_title in CONFIG.get('mappings', {}).items():
                if plex_title.lower() == anime.lower():
                    afl_name = name_key
                    break

            # If not found by Plex name, try AFL format
            if not afl_name:
                afl_name = format_anime_name(anime)

            # Only include lists for this anime
            if not name.startswith(f"{afl_name}_"):
                continue

        # This list passes all filters
        filtered_lists.append(trakt_list)

    # Filter project lists
    anime_lists = []
    for trakt_list in filtered_lists:
        name = trakt_list['name']

        # Check if this is a project list (has the format anime_name_episode_type)
        is_project_list = '_' in name and any(
            name.endswith(f"_{suffix}") for suffix in ['filler', 'manga canon', 'anime canon', 'mixed canon/filler']
        )

        # Skip non-project lists unless --all is specified
        if not is_project_list and not all:
            continue

        # Extract anime name and type from list name if it follows the format
        anime_name = "Unknown"
        episode_type = "Unknown"

        if '_' in name:
            parts = name.split('_', 1)
            if len(parts) == 2:
                anime_name = parts[0]
                episode_type = parts[1]

                # Convert AFL name to display name
                plex_name = CONFIG.get('mappings', {}).get(anime_name, anime_name)
                if '-' in plex_name:
                    plex_name = plex_name.replace('-', ' ').title()
                else:
                    plex_name = plex_name
            else:
                plex_name = name
        else:
            plex_name = name

        # Get list item count
        list_items_url = f"{trakt_api_url}/users/{CONFIG['trakt']['username']}/lists/{trakt_list['ids']['trakt']}/items/episode"
        count_response = requests.get(list_items_url, headers=headers)

        episode_count = 0
        if count_response.status_code == 200:
            episode_count = len(count_response.json())

        # Add to our results
        anime_lists.append({
            'id': trakt_list['ids']['trakt'],
            'name': name,
            'display_name': plex_name,
            'anime_name': anime_name,
            'episode_type': episode_type,
            'episode_count': episode_count,
            'description': trakt_list.get('description', ''),
            'url': f"https://trakt.tv/users/{CONFIG['trakt']['username']}/lists/{trakt_list['ids']['slug']}",
            'is_project_list': is_project_list
        })

    # Calculate how many lists are hidden that match our filters
    hidden_count = len(filtered_lists) - len(anime_lists)

    # Output the results in the requested format
    if format == 'json':
        print(json.dumps(anime_lists, indent=2))

    elif format == 'plain':
        # Output just the names for piping
        for list_info in anime_lists:
            if '_' in list_info['name']:
                anime_name, episode_type = list_info['name'].split('_', 1)

                # Convert the episode_type to the format expected by delete_piped
                if episode_type.lower() == 'filler':
                    std_type = 'FILLER'
                elif episode_type.lower() == 'manga canon':
                    std_type = 'MANGA'
                elif episode_type.lower() == 'anime canon':
                    std_type = 'ANIME'
                elif episode_type.lower() == 'mixed canon/filler':
                    std_type = 'MIXED'
                else:
                    std_type = episode_type.upper()

                # Print in a format that works with xargs -n2
                print(f"{anime_name} {std_type}")
            else:
                print(list_info['name'])

    else:  # table format
        # Create a rich table
        if all:
            table_title = f"All Trakt Lists for {CONFIG['trakt']['username']}"
        else:
            table_title = f"Project Trakt Lists for {CONFIG['trakt']['username']}"

        table = Table(title=table_title)
        table.add_column("Anime", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Episodes", justify="right")
        table.add_column("Trakt URL", style="blue")

        # Sort by anime name then type
        sorted_lists = sorted(anime_lists, key=lambda x: (x['display_name'], x['episode_type']))

        for list_info in sorted_lists:
            table.add_row(
                list_info['display_name'],
                list_info['episode_type'],
                str(list_info['episode_count']),
                list_info['url']
            )

        console.print(table)
        console.print(f"\nTotal Lists: {len(anime_lists)}")

        if not all and hidden_count > 0:
            if anime:
                console.print(f"[yellow]Note: {hidden_count} non-project lists for '{anime}' are hidden. Use --all to show them.[/yellow]")
            else:
                console.print(f"[yellow]Note: {hidden_count} non-project lists are hidden. Use --all to show them.[/yellow]")

@cli.command()
def sync_collections():
    """Manually synchronize the collections file with Trakt lists."""
    try:
        # First reload configuration to get the latest mappings
        reload_config()

        # Import the sync function
        from asset_manager import sync_anime_episode_collections

        console.print("[bold blue]Synchronizing collections file with Trakt lists...[/bold blue]")

        if sync_anime_episode_collections(CONFIG, force_update=True):
            console.print("[bold green]Collections synchronized successfully![/bold green]")
            # Show the path to the updated file for the user
            collections_dir = CONFIG.get('services', {}).get('tv_status_tracker', {}).get('collections_dir', '/kometa/config/collections')
            collections_file = os.path.join(collections_dir, 'anime_episode_type.yml')
            console.print(f"[blue]Updated file: {collections_file}[/blue]")
        else:
            console.print("[bold red]Failed to synchronize collections[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Error synchronizing collections: {str(e)}[/bold red]")
        import traceback
        console.print(traceback.format_exc())

if __name__ == '__main__':
    # Save original for later if needed
    original_arg0 = sys.argv[0]
    # Replace with docker command
    sys.argv[0] = 'docker compose run --rm dakosys'
    # Now let Click use this modified argv
    cli()
