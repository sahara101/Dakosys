#!/usr/bin/env python3
"""
TV/Anime Status Tracker Module for DAKOSYS

This module tracks TV show statuses and creates Kometa overlays and Trakt lists
for airing episodes, season finales, and other special events.
"""

import os
import sys
import json
import yaml
import time
import shutil
import logging
import requests
import pytz
from datetime import datetime
from plexapi.server import PlexServer
from rich.console import Console

import tmdb_metadata
import tvdb_metadata

console = Console()

logger = logging.getLogger("tv_status_tracker")

TRAKT_ACCESS_DENIED_STATUSES = {401, 403, 420, 426}

TEXT_FILE_MIN_KOMETA = (2, 3, 1)

OVERLAY_STYLES = {'background_color', 'colored_text'}

_AIR_DATE_FORMATS = (
    '%Y-%m-%dT%H:%M:%S.%fZ',
    '%Y-%m-%dT%H:%M:%SZ',
    '%Y-%m-%dT%H:%M:%S%z',
    '%Y-%m-%d',
)


def _kometa_supports_text_file(collections_dir):
    """Return (supported, version) for the Kometa install next to a collections dir."""
    version_file = os.path.join(
        os.path.dirname(os.path.dirname(str(collections_dir).rstrip('/'))), 'VERSION'
    )
    try:
        with open(version_file, 'r') as handle:
            raw = handle.read().strip().split()[0]
    except (OSError, IndexError):
        return True, None

    try:
        parts = tuple(int(p) for p in raw.split('-')[0].split('.')[:3])
    except ValueError:
        return True, None

    return parts >= TEXT_FILE_MIN_KOMETA, raw


def _parse_air_date(value):
    """Parse an air date that may be a full timestamp or a bare calendar date."""
    if not value:
        return datetime.max
    text = str(value).strip()
    for fmt in _AIR_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    logger.warning(f"Unrecognized air date format: {value}")
    return datetime.max

class TVStatusTracker:
    """TV and Anime Status Tracker for DAKOSYS."""

    def __init__(self, config):
        """Initialize with DAKOSYS configuration."""
        self.config = config

        self.data_dir = "data"
        if os.environ.get('RUNNING_IN_DOCKER') == 'true':
            self.data_dir = "/app/data"

        os.makedirs(self.data_dir, exist_ok=True)

        self.setup_logging()

        self.plex_url = config['plex']['url']
        self.plex_token = config['plex']['token']

        self.libraries = []
        plex_libs = config['plex'].get('libraries', {})
        self.libraries.extend(plex_libs.get('anime', []))
        self.libraries.extend(plex_libs.get('tv', []))

        self.timezone = config['timezone']

        self.trakt_config = config.get('trakt', {}) or {}

        self.tv_status_config = config['services']['tv_status_tracker']
        self.colors = self.tv_status_config.get('colors', {})

        _default_labels = {
            'ended': 'E N D E D',
            'cancelled': 'C A N C E L L E D',
            'returning': 'R E T U R N I N G',
            'airing': 'AIRING',
            'season_finale': 'SEASON FINALE',
            'mid_season_finale': 'MID SEASON FINALE',
            'final_episode': 'FINAL EPISODE',
            'season_premiere': 'SEASON PREMIERE',
        }
        self.labels = {**_default_labels, **self.tv_status_config.get('labels', {})}
        self.yaml_output_dir = config.get('kometa_config', {}).get('yaml_output_dir', '/kometa/config/overlays')
        self.collections_dir = config.get('kometa_config', {}).get('collections_dir', '/kometa/config/collections')

        next_airing_config = self.tv_status_config.get('next_airing', {}) or {}
        provider = str(next_airing_config.get('provider', 'text_file')).strip().lower()
        if provider not in ('trakt', 'text_file'):
            logger.warning(f"Unknown next_airing provider '{provider}', falling back to 'trakt'")
            provider = 'trakt'
        self.next_airing_provider = provider
        self.next_airing_text_file = (
            next_airing_config.get('text_file_path')
            or os.path.join(self.collections_dir, 'next-airing.txt')
        )
        kometa_path = next_airing_config.get('kometa_text_file_path')
        if not kometa_path:
            collections_name = os.path.basename(self.collections_dir.rstrip('/')) or 'collections'
            kometa_path = os.path.join('config', collections_name,
                                       os.path.basename(self.next_airing_text_file))
        self.next_airing_text_file_ref = kometa_path

        self.tmdb_api_key = str(config.get('tmdb_api_key', '') or '').strip()
        default_provider = 'tvdb' if self.tmdb_api_key else 'trakt'
        metadata_provider = str(
            self.tv_status_config.get('metadata_provider', default_provider)
        ).strip().lower()
        if metadata_provider not in ('trakt', 'tmdb', 'tvdb'):
            logger.warning(f"Unknown metadata_provider '{metadata_provider}', falling back to 'trakt'")
            metadata_provider = 'trakt'
        self.metadata_provider = metadata_provider
        self.tvdb_api_key = str(config.get('tvdb_api_key', '') or '').strip() or tvdb_metadata.DEFAULT_API_KEY
        self.use_tvmaze = bool(self.tv_status_config.get('use_tvmaze', True))
        self.needs_trakt_auth = self.next_airing_provider == 'trakt'
        self.trakt_metadata_degraded = False
        self._last_trakt_status = None

        font_path = self.tv_status_config.get('font_path')
        if not font_path or not os.path.exists(font_path):
            kometa_config = os.path.dirname(self.collections_dir)
            fallback_path = os.path.join(kometa_config, "fonts", "Juventus-Fans-Bold.ttf")

            if os.path.exists(fallback_path):
                font_path = fallback_path
            elif os.path.exists('/app/fonts/Juventus-Fans-Bold.ttf'):
                font_path = '/app/fonts/Juventus-Fans-Bold.ttf'
            else:
                logger.warning(f"Font not found. Using system default.")
                font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

        self.font_path = font_path
        kometa_conf = self.config.get('kometa_config', {})
        self.overlay_config = self.tv_status_config.get('overlay', {})

        logger.debug(f"Overlay config loaded: {self.overlay_config}")
        font_path_from_get = self.overlay_config.get('font_path')
        logger.debug(f"Font path from get: '{font_path_from_get}' (type: {type(font_path_from_get)})") 
        self.font_path_yaml = font_path_from_get
        if not self.font_path_yaml:
            font_dir = kometa_conf.get('font_directory', 'config/fonts')
            font_name = self.overlay_config.get('font_name', 'Juventus-Fans-Bold.ttf')
            self.font_path_yaml = os.path.join(font_dir, font_name)

        asset_dir = kometa_conf.get('asset_directory', 'config/assets')
        gradient_name = self.overlay_config.get('gradient_name', 'gradient_top.png')
        self.gradient_image_path_yaml = os.path.join(asset_dir, gradient_name)
        
        logger.info(f"Using font for script (fallback logic): {self.font_path}")
        logger.info(f"Using font for Kometa YAML: {self.font_path_yaml}")
        logger.info(f"Using gradient for Kometa YAML: {self.gradient_image_path_yaml}")

        self.airing_shows = []

        self.token_file = os.path.join(self.data_dir, "trakt_token.json")

        self.overlay_style = str(self.overlay_config.get('overlay_style', 'background_color')).strip().lower()
        if self.overlay_style not in OVERLAY_STYLES:
            console.print(
                f"[yellow]Warning: unknown overlay_style '{self.overlay_style}', "
                f"falling back to 'background_color'. Valid values: {', '.join(sorted(OVERLAY_STYLES))}[/yellow]"
            )
            logging.warning(f"Unknown overlay_style '{self.overlay_style}', falling back to 'background_color'")
            self.overlay_style = 'background_color'
        self.apply_gradient_background = self.overlay_config.get('apply_gradient_background', False)


        self.yaml_file_template = "overlay_tv_status_{library}.yml"

    def setup_logging(self):
        """Set up logging for the TV Status Tracker."""
        os.makedirs(self.data_dir, exist_ok=True)

        log_file = os.path.join(self.data_dir, "tv_status_tracker.log")

        from logging.handlers import RotatingFileHandler

        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        handler = RotatingFileHandler(
            log_file,
            maxBytes=5*1024*1024, 
            backupCount=3
        )

        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        handler.setFormatter(formatter)

        logger.addHandler(handler)

        logging.debug("TV Status Tracker started.")

    def get_trakt_token(self):
        """Get or refresh Trakt API token."""
        import trakt_auth
        access_token = trakt_auth.ensure_trakt_auth()
        return access_token

    def get_trakt_headers(self, access_token):
        """Get Trakt API headers."""
        return {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'Authorization': f'Bearer {access_token}',
            'trakt-api-key': self.trakt_config.get('client_id', '')
        }

    def get_public_trakt_headers(self):
        """Get Trakt API headers for public endpoints, which need no user token."""
        return {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'trakt-api-key': self.trakt_config.get('client_id', '')
        }

    def get_user_slug(self, headers):
        """Retrieve the user's slug (username) for list operations."""
        response = requests.get('https://api.trakt.tv/users/me', headers=headers)
        if response.status_code == 200:
            return response.json()['ids']['slug']
        logging.error("Failed to retrieve Trakt user slug.")
        return None

    def get_or_create_trakt_list(self, list_name, headers):
        """Ensure a Trakt list exists and return its slug, creating it if necessary."""
        user_slug = self.get_user_slug(headers)
        lists_url = f'https://api.trakt.tv/users/{user_slug}/lists'
        response = requests.get('https://api.trakt.tv/users/me/lists', headers=headers, params={"limit": 1000})
        if response.status_code == 429:
            retry_after = 60
            try:
                retry_after = int(response.headers.get('Retry-After', retry_after))
            except (ValueError, TypeError):
                pass
            logging.warning(f"Rate limit hit fetching Trakt lists, waiting {retry_after}s...")
            console.print(f"[yellow]Rate limit hit fetching Trakt lists, waiting {retry_after}s...[/yellow]")
            time.sleep(retry_after)
            response = requests.get('https://api.trakt.tv/users/me/lists', headers=headers, params={"limit": 1000})
        if response.status_code == 200:
            for lst in response.json():
                if lst['name'].lower() == list_name.lower():
                    return lst['ids']['slug']

        privacy = self.config.get('lists', {}).get('default_privacy', 'private')
        create_payload = {
            "name": list_name,
            "description": "List of shows with their next airing episodes.",
            "privacy": privacy,
            "display_numbers": False,
            "allow_comments": False
        }
        create_resp = requests.post(lists_url, json=create_payload, headers=headers)
        if create_resp.status_code in [200, 201]:
            console.print(f"[green]Created Trakt list: {list_name}[/green]")
            return create_resp.json()['ids']['slug']

        logging.error(f"Failed to create Trakt list: {create_resp.status_code} - {create_resp.text}")
        return None

    def process_show(self, show, headers):
        """Process a show to determine its status and next airing info."""
        logging.debug(f"Processing show: {show.title}")
        console.print(f"[dim]Processing show: {show.title}[/dim]")

        for guid in show.guids:
            if 'tmdb://' in guid.id:
                tmdb_id = guid.id.split('//')[1]

                def make_trakt_api_call(url, max_retries=5, initial_wait=5, timeout_seconds=20):
                    current_wait = initial_wait
                    for attempt in range(max_retries):
                        try:
                            response = requests.get(url, headers=headers, timeout=timeout_seconds)
                    
                            if response.status_code == 200:
                                return response
                            if response.status_code == 204:
                                return None  # No content — expected when no next episode is scheduled

                            if response.status_code == 429:
                                retry_after = 10 
                                if 'Retry-After' in response.headers:
                                    try:
                                        retry_after = int(response.headers['Retry-After'])
                                    except (ValueError, TypeError):
                                        pass 
                        
                                rate_limit_info = response.headers.get('X-Ratelimit', '{}')
                                logging.warning(f"Rate limit hit for {url}: {rate_limit_info}")
                                logging.warning(f"Waiting {retry_after}s before retry ({attempt+1}/{max_retries})...")
                                console.print(f"[yellow]Rate limit hit for {show.title}, waiting {retry_after}s (attempt {attempt+1}/{max_retries})...[/yellow]")
                                time.sleep(retry_after)
                                continue 
                            
                            self._last_trakt_status = response.status_code
                            logging.error(f"API error (HTTP {response.status_code}) for {url}: {response.text}")
                            return None

                        except requests.exceptions.Timeout as e:
                            logging.warning(f"Timeout connecting to {url} (attempt {attempt+1}/{max_retries}): {e}")
                        except requests.exceptions.ConnectionError as e: 
                            logging.warning(f"ConnectionError for {url} (attempt {attempt+1}/{max_retries}): {e}")
                        except requests.exceptions.RequestException as e: 
                            logging.warning(f"RequestException for {url} (attempt {attempt+1}/{max_retries}): {e}")
                        
                        if attempt < max_retries - 1:
                            logging.info(f"Waiting {current_wait}s before retrying {url} due to network/request issue...")
                            console.print(f"[yellow]Network/request issue for {show.title}. Waiting {current_wait}s before retry ({attempt+1}/{max_retries})...[/yellow]")
                            time.sleep(current_wait)
                            current_wait = min(current_wait * 2, 60) 
                        else:
                            logging.error(f"Failed after {max_retries} attempts for URL: {url} due to persistent network/request issues.")
                            return None 
                
                    logging.error(f"Failed after {max_retries} attempts for URL: {url} (exhausted all retries).")
                    return None

                if self.metadata_provider == 'tvdb':
                    record = tmdb_metadata.get_show_metadata(
                        tmdb_id, self.tmdb_api_key, use_tvmaze=False
                    )
                    self._apply_tvdb_air_details(record, tmdb_id)
                    if self.use_tvmaze and tmdb_metadata.apply_tvmaze_airstamp(
                        record, tmdb_id, self.tmdb_api_key
                    ):
                        logging.debug(f"TVmaze supplied the air time for TMDB {tmdb_id}")
                    trakt_id = None
                elif self.metadata_provider == 'tmdb' or self.trakt_metadata_degraded:
                    record = tmdb_metadata.get_show_metadata(
                        tmdb_id, self.tmdb_api_key, use_tvmaze=self.use_tvmaze
                    )
                    trakt_id = None
                else:
                    self._last_trakt_status = None
                    record, trakt_id = self._fetch_trakt_metadata(tmdb_id, make_trakt_api_call)

                    if record is None and self._last_trakt_status in TRAKT_ACCESS_DENIED_STATUSES:
                        if self.tmdb_api_key:
                            self.trakt_metadata_degraded = True
                            logging.warning(
                                f"Trakt returned HTTP {self._last_trakt_status} for metadata; "
                                "falling back to TMDB for the rest of this run"
                            )
                            console.print(
                                f"[yellow]Trakt denied metadata access (HTTP {self._last_trakt_status}). "
                                "Falling back to TMDB for this run.[/yellow]"
                            )
                            record = tmdb_metadata.get_show_metadata(
                                tmdb_id, self.tmdb_api_key, use_tvmaze=self.use_tvmaze
                            )
                            trakt_id = None
                        else:
                            logging.error(
                                f"Trakt returned HTTP {self._last_trakt_status} and no tmdb_api_key "
                                "is set to fall back to"
                            )

                if record:
                        status = record['status']
                        text_content = 'UNKNOWN'
                        back_color = self.colors.get(status.upper(), '#FFFFFF')

                        status_type = 'UNKNOWN'

                        if status == 'ended':
                            text_content = self.labels['ended']
                            back_color = self.colors['ENDED']
                            status_type = 'ENDED'
                        elif status == 'canceled':
                            text_content = self.labels['cancelled']
                            back_color = self.colors['CANCELLED']
                            status_type = 'CANCELLED'
                        elif status == 'returning':
                            first_aired = record.get('first_aired')
                            episode_type = record.get('episode_type', 'standard')

                            if first_aired:
                                    date_str = self._format_air_date(first_aired, record.get('date_only', False))

                                    if episode_type == 'season_finale':
                                        text_content = f"{self.labels['season_finale']} {date_str}"
                                        back_color = self.colors['SEASON_FINALE']
                                        status_type = 'SEASON_FINALE'
                                    elif episode_type == 'mid_season_finale':
                                        text_content = f"{self.labels['mid_season_finale']} {date_str}"
                                        back_color = self.colors['MID_SEASON_FINALE']
                                        status_type = 'MID_SEASON_FINALE'
                                    elif episode_type == 'series_finale':
                                        text_content = f"{self.labels['final_episode']} {date_str}"
                                        back_color = self.colors['FINAL_EPISODE']
                                        status_type = 'FINAL_EPISODE'
                                    elif episode_type == 'season_premiere':
                                        text_content = f"{self.labels['season_premiere']} {date_str}"
                                        back_color = self.colors['SEASON_PREMIERE']
                                        status_type = 'SEASON_PREMIERE'
                                    else:
                                        text_content = f"{self.labels['airing']} {date_str}"
                                        back_color = self.colors['AIRING']
                                        status_type = 'AIRING'

                                    try:
                                        tmdb_id_value = int(tmdb_id)
                                    except (TypeError, ValueError):
                                        tmdb_id_value = None

                                    self.airing_shows.append({
                                        'trakt_id': trakt_id,
                                        'tmdb_id': tmdb_id_value,
                                        'title': show.title,
                                        'year': show.year,
                                        'first_aired': first_aired,
                                        'date_only': record.get('date_only', False),
                                        'episode_type': episode_type,
                                        'status': status_type,
                                        'date': date_str,
                                        'text': text_content
                                    })
                            else:
                                text_content = self.labels['returning']
                                back_color = self.colors['RETURNING']
                                status_type = 'RETURNING'

                        console.print(f"[blue]Status: {text_content}[/blue]")
                        return {
                            'text_content': text_content,
                            'back_color': back_color,
                            'font': self.font_path_yaml,
                            'status_type': status_type,
                        }

        logging.debug(f"No status information found for: {show.title}")
        return None

    def _apply_tvdb_air_details(self, record, tmdb_id):
        """Upgrade a date-only TMDB record with TheTVDB's air instant and finale type."""
        if not record or not record.get('first_aired') or not record.get('date_only'):
            return

        timestamp, episode_type = tvdb_metadata.get_air_details(
            tmdb_id, self.tvdb_api_key, self.tmdb_api_key
        )

        if timestamp:
            record['first_aired'] = timestamp
            record['date_only'] = False
        else:
            logging.debug(f"TheTVDB had no air time for TMDB {tmdb_id}, keeping date-only value")

        if episode_type:
            record['episode_type'] = episode_type

    def _fetch_trakt_metadata(self, tmdb_id, make_trakt_api_call):
        """Resolve status and next airing episode from Trakt."""
        search_response = make_trakt_api_call(f'https://api.trakt.tv/search/tmdb/{tmdb_id}?type=show')
        if not search_response or not search_response.json():
            return None, None

        trakt_id = search_response.json()[0]['show']['ids']['trakt']
        status_response = make_trakt_api_call(f'https://api.trakt.tv/shows/{trakt_id}?extended=full')
        if not status_response:
            return None, trakt_id

        raw_status = status_response.json().get('status', '').lower()
        if raw_status == 'ended':
            status = 'ended'
        elif raw_status == 'canceled':
            status = 'canceled'
        elif raw_status == 'returning series':
            status = 'returning'
        else:
            status = raw_status

        record = {
            'status': status,
            'first_aired': None,
            'date_only': False,
            'episode_type': 'standard'
        }

        if status != 'returning':
            return record, trakt_id

        next_response = make_trakt_api_call(
            f'https://api.trakt.tv/shows/{trakt_id}/next_episode?extended=full'
        )
        if next_response and next_response.json():
            episode_data = next_response.json()
            record['first_aired'] = episode_data.get('first_aired')
            record['episode_type'] = episode_data.get('episode_type', '').lower() or 'standard'

        return record, trakt_id

    def _format_air_date(self, first_aired, date_only):
        """Format an air date for display, converting only real timestamps."""
        strftime_pattern = '%m/%d' if self.config.get('date_format', 'DD/MM').upper() == 'MM/DD' else '%d/%m'

        if date_only:
            return _parse_air_date(first_aired).strftime(strftime_pattern)

        parsed = _parse_air_date(first_aired)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=pytz.utc)
        return parsed.astimezone(pytz.timezone(self.timezone)).strftime(strftime_pattern)

    def sanitize_title_for_search(self, title):
        safe_title = title  
    
        if "'" in safe_title:  
            safe_title = safe_title.replace("'", "%'%")
    
        if "," in safe_title:
            safe_title = safe_title.replace(",", ",%")
    
        if "&" in safe_title:
            safe_title = safe_title.replace("&", "%&%")
    
        if ":" in safe_title:
            safe_title = safe_title.replace(":", "%:%")
        
        if "/" in safe_title:
            safe_title = safe_title.replace("/", "%/%")
    
        logging.debug(f"Sanitized title for search (no leading %): '{safe_title}' from original '{title}'")
        return safe_title

    def create_yaml(self, library_name, headers):
        """Create YAML overlay file for a library."""
        logging.info(f"Processing library: {library_name}")
        console.print(f"[bold blue]Processing library: {library_name}[/bold blue]")

        try:
            plex = PlexServer(self.plex_url, self.plex_token)
            library = plex.library.section(library_name)
            yaml_data = {'overlays': {}}

            for show in library.all():
                logging.debug(f"Processing {show.title}...")
                show_info = self.process_show(show, headers)

                if show_info:
                    formatted_title = f"{show.title}_{show.year}".replace(' ', '_') if show.year else show.title.replace(' ', '_')

                    safe_title = self.sanitize_title_for_search(show.title)
                    logging.debug(f"Using sanitized title for search: '{safe_title}'")

                    plex_search_all = {'title.is': safe_title}
                    if show.year:
                        plex_search_all['year'] = show.year

                    yaml_data['overlays'][f'{library_name}_Status_{formatted_title}'] = {
                        'overlay': {
                            'back_color': show_info['back_color'],
                            'back_height': self.overlay_config.get('back_height', 90),
                            'back_width': self.overlay_config.get('back_width', 1000),
                            'color': self.overlay_config.get('color', '#FFFFFF'),
                            'font': show_info['font'],
                            'font_size': self.overlay_config.get('font_size', 70),
                            'horizontal_align': self.overlay_config.get('horizontal_align', 'center'),
                            'horizontal_offset': self.overlay_config.get('horizontal_offset', 0),
                            'name': f"text({show_info['text_content']})",
                            'vertical_align': self.overlay_config.get('vertical_align', 'top'),
                            'vertical_offset': self.overlay_config.get('vertical_offset', 0),
                        },
                        'plex_search': {
                            'all': plex_search_all
                        }
                    }
                    logging.debug(f"Processed {show.title} with status {show_info['text_content']}.")

            yaml_file_path = os.path.join(self.yaml_output_dir, self.yaml_file_template.format(library=library_name.lower()))
            with open(yaml_file_path, 'w') as file:
                yaml.dump(yaml_data, file, allow_unicode=True, default_flow_style=False)

            logging.info(f'YAML file created for {library_name}: {yaml_file_path}')
            console.print(f"[green]YAML file created: {yaml_file_path}[/green]")

        except Exception as e:
            logging.error(f"Error processing library {library_name}: {str(e)}")
            console.print(f"[red]Error processing library {library_name}: {str(e)}[/red]")

    def create_yaml_collections(self):
        """Create YAML collection files for libraries."""
        trakt_template = """
collections:
  Next Airing {library_name}:
    trakt_list: https://trakt.tv/users/{trakt_username}/lists/next-airing?sort=rank,asc
    file_poster: 'config/assets/Next Airing/poster.jpg'
    collection_order: custom
    visible_home: true
    visible_shared: true
    sync_mode: sync
"""
        text_file_template = """
collections:
  Next Airing {library_name}:
    text_file: {text_file_path}
    file_poster: 'config/assets/Next Airing/poster.jpg'
    collection_order: custom
    visible_home: true
    visible_shared: true
    sync_mode: sync
"""
        for library_name in self.libraries:
            yaml_filename = f"{library_name.lower().replace(' ', '-')}-next-airing.yml"
            yaml_filepath = os.path.join(self.collections_dir, yaml_filename)

            if self.next_airing_provider == 'text_file':
                file_content = text_file_template.format(
                    library_name=library_name,
                    text_file_path=self.next_airing_text_file_ref
                )
                expected_builder = 'text_file:'
                other_builder = 'trakt_list:'
            else:
                file_content = trakt_template.format(
                    library_name=library_name,
                    trakt_username=self.trakt_config.get('username', '')
                )
                expected_builder = 'trakt_list:'
                other_builder = 'text_file:'

            if os.path.exists(yaml_filepath):
                try:
                    with open(yaml_filepath, 'r') as file:
                        existing_content = file.read()
                except Exception as e:
                    logging.error(f"Error reading collection file for {library_name}: {str(e)}")
                    console.print(f"[red]Error reading collection file for {library_name}: {str(e)}[/red]")
                    continue

                if expected_builder in existing_content:
                    console.print(f"[dim]YAML collections file for {library_name} already exists[/dim]")
                    continue

                if other_builder not in existing_content:
                    logging.warning(f"Unrecognized builder in {yaml_filepath}, leaving it untouched")
                    console.print(f"[yellow]Collection file for {library_name} uses an unrecognized builder, leaving it untouched[/yellow]")
                    continue

                try:
                    shutil.copy2(yaml_filepath, f"{yaml_filepath}.bak")
                    console.print(f"[yellow]Next Airing provider changed, backed up {yaml_filename} to {yaml_filename}.bak[/yellow]")
                    logging.info(f"Backed up {yaml_filepath} before switching builder to {expected_builder}")
                except Exception as e:
                    logging.error(f"Error backing up collection file for {library_name}: {str(e)}")
                    console.print(f"[red]Error backing up collection file for {library_name}: {str(e)}[/red]")
                    continue
            else:
                console.print(f"[blue]Creating YAML collections file for {library_name}[/blue]")

            try:
                with open(yaml_filepath, 'w') as file:
                    file.write(file_content)
                console.print(f"[green]File created: {yaml_filepath}[/green]")
            except Exception as e:
                logging.error(f"Error creating collection file for {library_name}: {str(e)}")
                console.print(f"[red]Error creating collection file: {str(e)}[/red]")

    def sort_airing_shows_by_date(self):
        """Sort airing shows by air date."""
        return sorted(
            self.airing_shows,
            key=lambda x: (
                _parse_air_date(x['first_aired']).replace(tzinfo=None),
                str(x.get('title', '')).lower()
            )
        )

    def write_next_airing_json(self, airing_shows):
        """Write the ordered Next Airing list consumed by the web dashboard."""
        output_path = os.path.join(self.data_dir, "next_airing.json")
        temp_path = f"{output_path}.tmp"

        payload = []
        for rank, show in enumerate(airing_shows, 1):
            payload.append({
                'rank': rank,
                'tmdb_id': show.get('tmdb_id'),
                'trakt_id': show.get('trakt_id'),
                'title': show.get('title', ''),
                'year': show.get('year'),
                'status': show.get('status', 'UNKNOWN'),
                'date': show.get('date', ''),
                'text': show.get('text', ''),
                'first_aired': show.get('first_aired', ''),
                'date_only': show.get('date_only', False)
            })

        try:
            with open(temp_path, 'w') as file:
                json.dump(payload, file, indent=2)
            os.replace(temp_path, output_path)
            logging.info(f"Wrote Next Airing data for {len(payload)} shows: {output_path}")
        except Exception as e:
            logging.error(f"Error writing Next Airing JSON: {str(e)}")
            console.print(f"[red]Failed to write Next Airing data: {str(e)}[/red]")
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def write_next_airing_text_file(self, airing_shows):
        """Write the ordered ID file consumed by the Kometa text_file builder."""
        lines = []
        missing_ids = []
        for show in airing_shows:
            tmdb_id = show.get('tmdb_id')
            if tmdb_id:
                lines.append(f"tmdb:{tmdb_id}")
            else:
                missing_ids.append(show.get('title', 'Unknown'))

        if missing_ids:
            logging.warning(f"Skipped {len(missing_ids)} show(s) without a TMDB ID: {', '.join(missing_ids)}")
            console.print(f"[yellow]Skipped {len(missing_ids)} show(s) without a TMDB ID[/yellow]")

        temp_path = f"{self.next_airing_text_file}.tmp"
        try:
            parent_dir = os.path.dirname(self.next_airing_text_file)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(temp_path, 'w') as file:
                for line in lines:
                    file.write(f"{line}\n")
            os.replace(temp_path, self.next_airing_text_file)
            logging.info(f"Wrote Next Airing text file with {len(lines)} entries: {self.next_airing_text_file}")
            console.print(f"[green]Next Airing text file written with {len(lines)} shows: {self.next_airing_text_file}[/green]")
        except Exception as e:
            logging.error(f"Error writing Next Airing text file: {str(e)}")
            console.print(f"[red]Failed to write Next Airing text file: {str(e)}[/red]")
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def fetch_current_trakt_list_shows(self, list_slug, headers):
        """Fetch current shows in a Trakt list."""
        user_slug = self.get_user_slug(headers)
        list_items_url = f'https://api.trakt.tv/users/{user_slug}/lists/{list_slug}/items'
        response = requests.get(list_items_url, headers=headers, params={"limit": 1000})

        if response.status_code == 200:
            current_shows = response.json()
            current_trakt_ids = [item['show']['ids']['trakt'] for item in current_shows if item.get('show')]
            return current_trakt_ids
        else:
            logging.error(f"Failed to fetch current Trakt list shows: {response.status_code} - {response.text}")
            return []

    def update_trakt_list(self, list_slug, airing_shows, headers):
        """Update a Trakt list with airing shows."""
        user_slug = self.get_user_slug(headers)
        current_trakt_ids = self.fetch_current_trakt_list_shows(list_slug, headers)
        new_trakt_ids = [int(show['trakt_id']) for show in airing_shows]

        if current_trakt_ids == new_trakt_ids:
            console.print("[yellow]No update necessary for the Trakt list[/yellow]")
            return

        list_items_url = f'https://api.trakt.tv/users/me/lists/{list_slug}/items'
        console.print("[blue]Updating Trakt list with airing shows...[/blue]")

        if current_trakt_ids:
            console.print(f"[dim]Removing {len(current_trakt_ids)} existing items from list[/dim]")
            remove_payload = {"shows": [{"ids": {"trakt": trakt_id}} for trakt_id in current_trakt_ids]}
            remove_response = requests.post(f"{list_items_url}/remove", json=remove_payload, headers=headers)

            if remove_response.status_code not in [200, 201, 204]:
                logging.error(f"Failed to remove items from list: {remove_response.status_code} - {remove_response.text}")
                console.print("[red]Failed to remove existing items from list[/red]")

            time.sleep(1)  

        if new_trakt_ids:
            console.print(f"[dim]Adding {len(new_trakt_ids)} new items to list[/dim]")
            shows_payload = {"shows": [{"ids": {"trakt": trakt_id}} for trakt_id in new_trakt_ids]}
            add_response = requests.post(list_items_url, json=shows_payload, headers=headers)

            if add_response.status_code in [200, 201, 204]:
                console.print(f"[green]Trakt list updated successfully with {len(airing_shows)} shows[/green]")
            else:
                logging.error(f"Failed to add items to list: {add_response.status_code} - {add_response.text}")
                console.print(f"[red]Failed to update Trakt list. Response: {add_response.text}[/red]")

            time.sleep(1)  

    def run(self):
        """Run the TV Status Tracker."""
        console.print("[bold]Starting TV/Anime Status Tracker...[/bold]")

        if not os.path.exists(self.yaml_output_dir):
            console.print(f"[red]Error: YAML output directory does not exist: {self.yaml_output_dir}[/red]")
            logging.error(f"YAML output directory does not exist: {self.yaml_output_dir}")
            return False

        if not os.path.exists(self.collections_dir):
            console.print(f"[red]Error: Collections directory does not exist: {self.collections_dir}[/red]")
            logging.error(f"Collections directory does not exist: {self.collections_dir}")
            return False

        if self.next_airing_provider == 'text_file':
            supported, kometa_version = _kometa_supports_text_file(self.collections_dir)
            if not supported:
                console.print(
                    f"[yellow]Warning: Kometa {kometa_version} does not support the text_file builder "
                    f"(needs {'.'.join(str(p) for p in TEXT_FILE_MIN_KOMETA)}+). The Next Airing collection "
                    "will fail to load. Upgrade Kometa or set next_airing.provider: trakt[/yellow]"
                )
                logging.warning(
                    f"Kometa {kometa_version} predates the text_file builder "
                    f"({'.'.join(str(p) for p in TEXT_FILE_MIN_KOMETA)}+); Next Airing collection will not load"
                )

        needs_trakt = self.needs_trakt_auth or self.metadata_provider == 'trakt'
        if needs_trakt and not self.trakt_config.get('client_id'):
            console.print(
                "[red]Error: Trakt is required here but no trakt.client_id is configured. "
                "Set metadata_provider to 'tvdb' and next_airing.provider to 'text_file' "
                "to run without Trakt.[/red]"
            )
            logging.error("Trakt is required by the current providers but trakt.client_id is missing")
            return False

        if self.metadata_provider in ('tmdb', 'tvdb') and not self.tmdb_api_key:
            console.print(f"[red]Error: metadata_provider is '{self.metadata_provider}' but tmdb_api_key is not set[/red]")
            logging.error(f"metadata_provider is '{self.metadata_provider}' but tmdb_api_key is not configured")
            return False

        if self.metadata_provider == 'tvdb':
            if not self.tvdb_api_key and not tvdb_metadata.PROXY_URL:
                console.print("[red]Error: metadata_provider is 'tvdb' but no tvdb_api_key is set and no proxy is available[/red]")
                logging.error("metadata_provider is 'tvdb' but no key or proxy is available")
                return False
            if self.tvdb_api_key and not tvdb_metadata.verify_api_key(self.tvdb_api_key):
                console.print("[red]Error: TheTVDB rejected tvdb_api_key[/red]")
                logging.error("TheTVDB rejected the configured tvdb_api_key")
                return False

        headers = None
        if self.needs_trakt_auth:
            access_token = self.get_trakt_token()
            if not access_token:
                console.print("[red]Failed to get Trakt token[/red]")
                return False
            headers = self.get_trakt_headers(access_token)
        elif self.metadata_provider == 'trakt':
            headers = self.get_public_trakt_headers()
            console.print("[dim]Using Trakt public API for metadata (client_id only, no login required)[/dim]")
        else:
            console.print(f"[dim]Running without Trakt (metadata: {self.metadata_provider}, next airing: text_file)[/dim]")

        changes = {
            'AIRING': [],
            'SEASON_FINALE': [],
            'MID_SEASON_FINALE': [],
            'FINAL_EPISODE': [],
            'SEASON_PREMIERE': [],
            'RETURNING': [],
            'ENDED': [],
            'CANCELLED': [],
            'DATE_CHANGED': []  
        }

        previous_status = {}
        status_cache_file = os.path.join(self.data_dir, "tv_status_cache.json")

        is_first_run = not os.path.exists(status_cache_file)

        try:
            if os.path.exists(status_cache_file):
                with open(status_cache_file, 'r') as f:
                    previous_status = json.load(f)
        except Exception as e:
            logging.error(f"Error loading previous status cache: {str(e)}")

        current_status = {}

        total_shows_processed = 0

        for library_name in self.libraries:
            try:
                plex = PlexServer(self.plex_url, self.plex_token)
                library = plex.library.section(library_name)
                yaml_data = {'overlays': {}}

                for show in library.all():
                    total_shows_processed += 1
                    logging.debug(f"Processing {show.title}...")
                    show_info = self.process_show(show, headers)

                    if show_info:
                        text_parts = show_info['text_content'].split()
                        status_text = text_parts[0]

                        date_str = ''
                        for part in text_parts:
                            if '/' in part and any(c.isdigit() for c in part):
                                date_str = part
                                break

                        show_key = f"{show.title} ({show.year})" if show.year else show.title

                        current_status[show_key] = {
                            'status': status_text,
                            'date': date_str,
                            'text': show_info['text_content']
                        }

                        if show_key in previous_status:
                            prev = previous_status[show_key]
                            curr = current_status[show_key]

                            status_changed = prev['status'] != curr['status']
                            date_changed = prev['date'] != curr['date'] and curr['date']

                            if status_changed or date_changed:
                                logging.debug(f"Change detected for {show_key}: Status changed: {status_changed}, Date changed: {date_changed}")
                                logging.debug(f"Previous: {prev['status']} ({prev['date']}), Current: {curr['status']} ({curr['date']})")

                                status_key = None

                                if status_changed:
                                    status_key = show_info.get('status_type')
                                elif date_changed and not status_changed:
                                    status_key = 'DATE_CHANGED'

                                if status_key:
                                    changes[status_key].append({
                                        'title': show_key,
                                        'prev_status': prev['status'],
                                        'new_status': curr['status'],
                                        'prev_date': prev['date'],
                                        'new_date': curr['date'],
                                        'full_text': curr['text'],
                                        'library': library_name
                                    })
                        else:
                            curr = current_status[show_key]

                            if is_first_run:
                                status_key = show_info.get('status_type')

                                if status_key and (bool(curr['date']) or status_key == 'FINAL_EPISODE'):
                                    changes[status_key].append({
                                        'title': show_key,
                                        'prev_status': 'NEW',
                                        'new_status': curr['status'],
                                        'prev_date': '',
                                        'new_date': curr['date'],
                                        'full_text': curr['text'],
                                        'library': library_name
                                    })
                            else:
                                status_key = show_info.get('status_type')

                                if status_key:
                                    changes[status_key].append({
                                        'title': show_key,
                                        'prev_status': 'NEW',
                                        'new_status': curr['status'],
                                        'prev_date': '',
                                        'new_date': curr['date'],
                                        'full_text': curr['text'],
                                        'library': library_name
                                    })

                        formatted_title = f"{show.title}_{show.year}".replace(' ', '_') if show.year else show.title.replace(' ', '_')

                        safe_title = self.sanitize_title_for_search(show.title)
                        
                        overlay_details = {
                            'font': show_info['font'],
                            'font_size': self.overlay_config.get('font_size', 70),
                            'horizontal_align': self.overlay_config.get('horizontal_align', 'center'),
                            'horizontal_offset': self.overlay_config.get('horizontal_offset', 0),
                            'name': f"text({show_info['text_content']})",
                            'vertical_align': self.overlay_config.get('vertical_align', 'top'),
                            'vertical_offset': self.overlay_config.get('vertical_offset', 0),
                            'back_width': self.overlay_config.get('back_width', 1000),
                            'back_height': self.overlay_config.get('back_height', 90)
                        }

                        plex_search_all = {'title.is': safe_title}
                        if show.year:
                            plex_search_all['year'] = show.year
                        plex_search_block = {'all': plex_search_all}

                        if self.apply_gradient_background:
                            gradient_overlay_key = f'{library_name}_StatusGradient_{formatted_title}'
                            yaml_data['overlays'][gradient_overlay_key] = {
                                'overlay': {
                                    'file': self.gradient_image_path_yaml,
                                    'height': self.overlay_config.get('back_height', 90),
                                    'horizontal_align': self.overlay_config.get('horizontal_align', "center"),
                                    'horizontal_offset': self.overlay_config.get('horizontal_offset', 0),
                                    'name': f"status_gradient_for_{formatted_title.replace('|', '_')}",
                                    'order': 10,
                                    'vertical_align': self.overlay_config.get('vertical_align', "top"),
                                    'vertical_offset': self.overlay_config.get('vertical_offset', 0),
                                    'width': self.overlay_config.get('back_width', 1000)
                                },
                                'plex_search': plex_search_block
                            }
                            logging.debug(f"Added gradient layer for {show.title}")

                        if self.overlay_style == 'colored_text':
                            text_overlay_key = f'{library_name}_StatusText_{formatted_title}'
                            text_overlay_details = {
                                'name': f"text({show_info['text_content']})",
                                'font': show_info['font'],
                                'font_size': self.overlay_config.get('font_size', 70),
                                'font_color': show_info['back_color'], 
                                'back_color': '#00000000', 
                                'horizontal_align': self.overlay_config.get('horizontal_align', 'center'),
                                'vertical_align': self.overlay_config.get('vertical_align', 'top'),
                                'horizontal_offset': self.overlay_config.get('horizontal_offset', 0),
                                'vertical_offset': self.overlay_config.get('vertical_offset', 0),
                                'back_width': self.overlay_config.get('back_width', 1000),
                                'back_height': self.overlay_config.get('back_height', 90),
                                'order': 20 
                            }
                            yaml_data['overlays'][text_overlay_key] = {
                                'overlay': text_overlay_details,
                                'plex_search': plex_search_block
                            }
                            logger.info(f"Added text layer for {show.title} with status {show_info['text_content']}.")

                        elif self.overlay_style == 'background_color':
                            overlay_key = f'{library_name}_Status_{formatted_title}'
                            overlay_details = {
                                'font': show_info['font'],
                                'font_size': self.overlay_config.get('font_size', 70),
                                'horizontal_align': self.overlay_config.get('horizontal_align', 'center'),
                                'horizontal_offset': self.overlay_config.get('horizontal_offset', 0),
                                'name': f"text({show_info['text_content']})",
                                'vertical_align': self.overlay_config.get('vertical_align', 'top'),
                                'vertical_offset': self.overlay_config.get('vertical_offset', 0),
                                'back_width': self.overlay_config.get('back_width', 1000),
                                'back_height': self.overlay_config.get('back_height', 90),
                                'color': self.overlay_config.get('color', '#FFFFFF'), 
                                'back_color': show_info['back_color'] 
                            }
                            yaml_data['overlays'][overlay_key] = {
                                'overlay': overlay_details,
                                'plex_search': plex_search_block
                            }
                            logging.debug(f"Processed {show.title} with status {show_info['text_content']} (background_color style).")

                yaml_file_path = os.path.join(self.yaml_output_dir, self.yaml_file_template.format(library=library_name.lower()))
                with open(yaml_file_path, 'w') as file:
                    yaml.dump(yaml_data, file, allow_unicode=True, default_flow_style=False)

                logging.info(f'YAML file created for {library_name}: {yaml_file_path}')
                console.print(f"[green]YAML file created: {yaml_file_path}[/green]")

            except Exception as e:
                logging.error(f"Error processing library {library_name}: {str(e)}")
                console.print(f"[red]Error processing library {library_name}: {str(e)}[/red]")

        self.create_yaml_collections()

        sorted_airing_shows = self.sort_airing_shows_by_date()
        self.write_next_airing_json(sorted_airing_shows)

        if self.next_airing_provider == 'text_file':
            self.write_next_airing_text_file(sorted_airing_shows)
        else:
            list_name = "Next Airing"
            list_slug = self.get_or_create_trakt_list(list_name, headers)

            if list_slug and sorted_airing_shows:
                self.update_trakt_list(list_slug, sorted_airing_shows, headers)
                console.print(f"[green]Updated '{list_name}' Trakt list with {len(sorted_airing_shows)} airing shows[/green]")
            elif not sorted_airing_shows:
                console.print("[yellow]No airing shows found to add to Trakt list[/yellow]")

        try:
            with open(status_cache_file, 'w') as f:
                json.dump(current_status, f)
        except Exception as e:
            logging.error(f"Error saving status cache: {str(e)}")

        have_changes = any(len(shows) > 0 for status, shows in changes.items())
        if have_changes and not os.environ.get('QUIET_MODE') == 'true':
            try:
                from notifications import notify_tv_status_updates
                notify_tv_status_updates(changes, total_shows_processed)
                logging.info("Sent TV status notifications")
            except Exception as e:
                logging.error(f"Error sending TV status notifications: {str(e)}")

        console.print("[bold green]TV/Anime Status Tracker completed successfully[/bold green]")
        return True

def run_tv_status_tracker(config=None):
    """Run the TV Status Tracker as a standalone function."""
    if not config:
        config_path = "/app/config/config.yaml" if os.environ.get('RUNNING_IN_DOCKER') == 'true' else "config/config.yaml"
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
        except Exception as e:
            print(f"Error loading configuration: {str(e)}")
            return False

    if not config.get('services', {}).get('tv_status_tracker', {}).get('enabled', False):
        print("TV/Anime Status Tracker is disabled in configuration.")
        return False

    tracker = TVStatusTracker(config)
    return tracker.run()

if __name__ == "__main__":
    run_tv_status_tracker()
