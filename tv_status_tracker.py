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
import logging
import requests
import pytz
from datetime import datetime
from plexapi.server import PlexServer
from rich.console import Console

# Initialize console for rich output
console = Console()

# Initialize logger
logger = logging.getLogger("tv_status_tracker")

class TVStatusTracker:
    """TV and Anime Status Tracker for DAKOSYS."""

    def __init__(self, config):
        """Initialize with DAKOSYS configuration."""
        self.config = config

        # Set up data storage first (before setup_logging is called)
        self.data_dir = "data"
        if os.environ.get('RUNNING_IN_DOCKER') == 'true':
            self.data_dir = "/app/data"

        # Ensure data directory exists
        os.makedirs(self.data_dir, exist_ok=True)

        # Now it's safe to call setup_logging as self.data_dir is defined
        self.setup_logging()

        # Extract configuration values
        self.plex_url = config['plex']['url']
        self.plex_token = config['plex']['token']

        # Get libraries to process
        self.libraries = []
        if 'libraries' in config['plex']:
            # Add anime libraries if configured to use them for TV status
            if config['plex']['libraries'].get('anime', []):
                self.libraries.extend(config['plex']['libraries']['anime'])

            # Add TV libraries
            if config['plex']['libraries'].get('tv', []):
                self.libraries.extend(config['plex']['libraries']['tv'])

        # Fallback to legacy config format if needed
        elif 'library' in config['plex']:
            self.libraries.append(config['plex']['library'])

        # Set timezone
        self.timezone = config['timezone']

        # Set Trakt configuration
        self.trakt_config = config['trakt']

        # Set file paths for TV Status Tracker
        self.tv_status_config = config['services']['tv_status_tracker']
        self.colors = self.tv_status_config.get('colors', {})
        self.yaml_output_dir = config.get('kometa_config', {}).get('yaml_output_dir', '/kometa/config/overlays')
        self.collections_dir = config.get('kometa_config', {}).get('collections_dir', '/kometa/config/collections')

        # Get font path from config
        font_path = self.tv_status_config.get('font_path')
        if not font_path or not os.path.exists(font_path):
            # Try to find the font in Kometa config directory
            kometa_config = os.path.dirname(self.collections_dir)
            fallback_path = os.path.join(kometa_config, "fonts", "Juventus-Fans-Bold.ttf")

            if os.path.exists(fallback_path):
                font_path = fallback_path
            # If not found there, use the container font
            elif os.path.exists('/app/fonts/Juventus-Fans-Bold.ttf'):
                font_path = '/app/fonts/Juventus-Fans-Bold.ttf'
            else:
                logger.warning(f"Font not found. Using system default.")
                # Use system default (should be available in Debian-based containers)
                font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

        self.font_path = font_path
        self.font_path_yaml = "config/fonts/Juventus-Fans-Bold.ttf"
        logger.info(f"Using font: {self.font_path}")

        # Set up data storage
        self.airing_shows = []

        # Set token file path
        self.token_file = os.path.join(self.data_dir, "trakt_token.json")

        self.overlay_config = self.tv_status_config.get('overlay', {})

        # YAML template for file naming
        self.yaml_file_template = "overlay_tv_status_{library}.yml"

    def setup_logging(self):
        """Set up logging for the TV Status Tracker."""
        # Ensure data directory exists
        os.makedirs(self.data_dir, exist_ok=True)

        log_file = os.path.join(self.data_dir, "tv_status_tracker.log")

        # Use rotating file handler
        from logging.handlers import RotatingFileHandler

        # Get logger
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        # Clear any existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # Create rotating handler
        handler = RotatingFileHandler(
            log_file,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3
        )

        # Set format
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(handler)

        logging.debug("TV Status Tracker started.")

    def get_trakt_token(self):
        """Get or refresh Trakt API token."""
        # Import the token handling code from trakt_auth module
        import trakt_auth
        access_token = trakt_auth.ensure_trakt_auth()
        return access_token

    def get_trakt_headers(self, access_token):
        """Get Trakt API headers."""
        return {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'Authorization': f'Bearer {access_token}',
            'trakt-api-key': self.trakt_config['client_id']
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
        response = requests.get(lists_url, headers=headers)
        if response.status_code == 200:
            for lst in response.json():
                if lst['name'].lower() == list_name.lower():
                    return lst['ids']['slug']  # List exists

        # Create the list if it doesn't exist
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
            return self.get_or_create_trakt_list(list_name, headers)  # Recursively get the newly created list

        logging.error(f"Failed to create Trakt list: {create_resp.status_code} - {create_resp.text}")
        return None

    def process_show(self, show, headers):
        """Process a show to determine its status and next airing info."""
        logging.debug(f"Processing show: {show.title}")
        console.print(f"[dim]Processing show: {show.title}[/dim]")

        for guid in show.guids:
            if 'tmdb://' in guid.id:
                tmdb_id = guid.id.split('//')[1]

                # Just copy your original code, but add retry only for rate limits
                search_api_url = f'https://api.trakt.tv/search/tmdb/{tmdb_id}?type=show'

                # Add retry logic
                max_retries = 3
                retry_count = 0
                retry_delay = 1

                response = requests.get(search_api_url, headers=headers)
                while response.status_code == 429 and retry_count < max_retries:
                    retry_count += 1
                    logging.warning(f"Rate limit hit, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    response = requests.get(search_api_url, headers=headers)

                # Continue with original code logic
                if response.status_code == 200 and response.json():
                    trakt_id = response.json()[0]['show']['ids']['trakt']
                    status_url = f'https://api.trakt.tv/shows/{trakt_id}?extended=full'

                    # Add retry for status request
                    retry_count = 0
                    retry_delay = 1

                    status_response = requests.get(status_url, headers=headers)
                    while status_response.status_code == 429 and retry_count < max_retries:
                        retry_count += 1
                        logging.warning(f"Rate limit hit, retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        status_response = requests.get(status_url, headers=headers)

                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        status = status_data.get('status', '').lower()
                        text_content = 'UNKNOWN'
                        back_color = self.colors.get(status.upper(), '#FFFFFF')

                        if status == 'ended':
                            text_content = 'E N D E D'
                            back_color = self.colors['ENDED']
                        elif status == 'canceled':
                            text_content = 'C A N C E L L E D'
                            back_color = self.colors['CANCELLED']
                        elif status == 'returning series':
                            next_episode_url = f'https://api.trakt.tv/shows/{trakt_id}/next_episode?extended=full'

                            # Add retry for next_episode request
                            retry_count = 0
                            retry_delay = 1

                            next_episode_response = requests.get(next_episode_url, headers=headers)
                            while next_episode_response.status_code == 429 and retry_count < max_retries:
                                retry_count += 1
                                logging.warning(f"Rate limit hit, retrying in {retry_delay}s...")
                                time.sleep(retry_delay)
                                retry_delay *= 2
                                next_episode_response = requests.get(next_episode_url, headers=headers)

                            if next_episode_response.status_code == 200 and next_episode_response.json():
                                episode_data = next_episode_response.json()
                                first_aired = episode_data.get('first_aired')
                                episode_type = episode_data.get('episode_type', '').lower()

                                if first_aired:
                                    utc_time = datetime.strptime(first_aired, '%Y-%m-%dT%H:%M:%S.000Z')
                                    local_time = utc_time.replace(tzinfo=pytz.utc).astimezone(pytz.timezone(self.timezone))
                                    date_str = local_time.strftime('%d/%m')

                                    # Handle different episode types
                                    if episode_type == 'season_finale':
                                        text_content = f'SEASON FINALE {date_str}'
                                        back_color = self.colors['SEASON_FINALE']
                                    elif episode_type == 'mid_season_finale':
                                        text_content = f'MID SEASON FINALE {date_str}'
                                        back_color = self.colors['MID_SEASON_FINALE']
                                    elif episode_type == 'series_finale':
                                        text_content = f'FINAL EPISODE {date_str}'
                                        back_color = self.colors['FINAL_EPISODE']
                                    elif episode_type == 'season_premiere':
                                        text_content = f'SEASON PREMIERE {date_str}'
                                        back_color = self.colors['SEASON_PREMIERE']
                                    else:
                                        text_content = f'AIRING {date_str}'
                                        back_color = self.colors['AIRING']

                                    self.airing_shows.append({
                                        'trakt_id': trakt_id,
                                        'title': show.title,
                                        'first_aired': first_aired,
                                        'episode_type': episode_type
                                    })
                            else:
                                text_content = 'R E T U R N I N G'
                                back_color = self.colors['RETURNING']

                        console.print(f"[blue]Status: {text_content}[/blue]")
                        return {
                            'text_content': text_content,
                            'back_color': back_color,
                            'font': self.font_path_yaml
                        }

        logging.debug(f"No status information found for: {show.title}")
        return None

    def sanitize_title_for_search(self, title):
        """
        Add wildcards (%) to handle special characters in title.is searches.
        Based on empirical testing with Plex's search behavior.
        """
        # Handle titles that start with apostrophes (like 'Allo 'Allo!)
        if title.startswith("'"):
            title = "%" + title  # Add % before starting apostrophe
        
        # Replace internal apostrophes with %'%
        if "'" in title and not title.startswith("'"):
            parts = title.split("'")
            # Join with %'% but be careful not to add it at the beginning if the title starts with '
            if title.startswith("'"):
                new_title = parts[0] + "'"
                for part in parts[1:]:
                    new_title += "%'%" + part
                title = new_title
            else:
                title = "%'%".join(parts)
        
        # Handle commas by adding % before the comma
        if ", " in title:
            parts = title.split(", ")
            title = "%,".join([part + "%" for part in parts[:-1]] + [parts[-1]])
        
        # Handle ampersands with % before and after
        if " & " in title:
            title = title.replace(" & ", " %&% ")
        
        # Special handling for specific characters that might cause issues
        # Add more rules based on testing
        
        logging.debug(f"Sanitized title for search: '{title}' from original '{title}'")
        return title

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
                    formatted_title = show.title.replace(' ', '_')
                    
                    # Create a safe version of the title with wildcards for special characters
                    safe_title = self.sanitize_title_for_search(show.title)
                    logging.debug(f"Using sanitized title for search: '{safe_title}'")
                    
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
                            'all': {
                                'title.is': safe_title
                            }
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
        yaml_template = """
collections:
  Next Airing {library_name}:
    trakt_list: https://trakt.tv/users/{trakt_username}/lists/next-airing?sort=rank,asc
    file_poster: 'config/assets/Next Airing/poster.jpg'
    collection_order: custom
    visible_home: true
    visible_shared: true
    sync_mode: sync
"""
        for library_name in self.libraries:
            # Format the filename
            yaml_filename = f"{library_name.lower().replace(' ', '-')}-next-airing.yml"
            yaml_filepath = os.path.join(self.collections_dir, yaml_filename)

            # Check if the file exists
            if not os.path.exists(yaml_filepath):
                console.print(f"[blue]Creating YAML collections file for {library_name}[/blue]")
                try:
                    with open(yaml_filepath, 'w') as file:
                        file_content = yaml_template.format(
                            library_name=library_name,
                            trakt_username=self.trakt_config['username']
                        )
                        file.write(file_content)
                    console.print(f"[green]File created: {yaml_filepath}[/green]")
                except Exception as e:
                    logging.error(f"Error creating collection file for {library_name}: {str(e)}")
                    console.print(f"[red]Error creating collection file: {str(e)}[/red]")
            else:
                console.print(f"[dim]YAML collections file for {library_name} already exists[/dim]")

    def sort_airing_shows_by_date(self):
        """Sort airing shows by air date."""
        return sorted(self.airing_shows, key=lambda x: datetime.strptime(x['first_aired'], '%Y-%m-%dT%H:%M:%S.000Z'))

    def fetch_current_trakt_list_shows(self, list_slug, headers):
        """Fetch current shows in a Trakt list."""
        user_slug = self.get_user_slug(headers)
        list_items_url = f'https://api.trakt.tv/users/{user_slug}/lists/{list_slug}/items'
        response = requests.get(list_items_url, headers=headers)

        if response.status_code == 200:
            current_shows = response.json()
            # Extract Trakt IDs of shows currently in the list
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

        # Check if the lists match (including order)
        if current_trakt_ids == new_trakt_ids:
            console.print("[yellow]No update necessary for the Trakt list[/yellow]")
            return

        list_items_url = f'https://api.trakt.tv/users/{user_slug}/lists/{list_slug}/items'
        console.print("[blue]Updating Trakt list with airing shows...[/blue]")

        # First, remove all existing items if there are any
        if current_trakt_ids:
            console.print(f"[dim]Removing {len(current_trakt_ids)} existing items from list[/dim]")
            remove_payload = {"shows": [{"ids": {"trakt": trakt_id}} for trakt_id in current_trakt_ids]}
            remove_response = requests.post(f"{list_items_url}/remove", json=remove_payload, headers=headers)

            if remove_response.status_code not in [200, 201, 204]:
                logging.error(f"Failed to remove items from list: {remove_response.status_code} - {remove_response.text}")
                console.print("[red]Failed to remove existing items from list[/red]")

            time.sleep(1)  # Respect rate limits

        # Then, add the new list of shows
        if new_trakt_ids:
            console.print(f"[dim]Adding {len(new_trakt_ids)} new items to list[/dim]")
            shows_payload = {"shows": [{"ids": {"trakt": trakt_id}} for trakt_id in new_trakt_ids]}
            add_response = requests.post(list_items_url, json=shows_payload, headers=headers)

            if add_response.status_code in [200, 201, 204]:
                console.print(f"[green]Trakt list updated successfully with {len(airing_shows)} shows[/green]")
            else:
                logging.error(f"Failed to add items to list: {add_response.status_code} - {add_response.text}")
                console.print(f"[red]Failed to update Trakt list. Response: {add_response.text}[/red]")

            time.sleep(1)  # Respect rate limits

    def run(self):
        """Run the TV Status Tracker."""
        console.print("[bold]Starting TV/Anime Status Tracker...[/bold]")

        # Check if output directories exist
        if not os.path.exists(self.yaml_output_dir):
            console.print(f"[red]Error: YAML output directory does not exist: {self.yaml_output_dir}[/red]")
            logging.error(f"YAML output directory does not exist: {self.yaml_output_dir}")
            return False

        if not os.path.exists(self.collections_dir):
            console.print(f"[red]Error: Collections directory does not exist: {self.collections_dir}[/red]")
            logging.error(f"Collections directory does not exist: {self.collections_dir}")
            return False

        # Get Trakt token
        access_token = self.get_trakt_token()
        if not access_token:
            console.print("[red]Failed to get Trakt token[/red]")
            return False

        headers = self.get_trakt_headers(access_token)

        # Dictionary to track all changes (both status and date)
        changes = {
            'AIRING': [],
            'SEASON_FINALE': [],
            'MID_SEASON_FINALE': [],
            'FINAL_EPISODE': [],
            'SEASON_PREMIERE': [],
            'RETURNING': [],
            'ENDED': [],
            'CANCELLED': [],
            'DATE_CHANGED': []  # Special category for date-only changes
        }

        # Load previous status from cache file if it exists
        previous_status = {}
        status_cache_file = os.path.join(self.data_dir, "tv_status_cache.json")

        # Check if this is the first run
        is_first_run = not os.path.exists(status_cache_file)

        try:
            if os.path.exists(status_cache_file):
                with open(status_cache_file, 'r') as f:
                    previous_status = json.load(f)
        except Exception as e:
            logging.error(f"Error loading previous status cache: {str(e)}")

        # New status will be saved at the end
        current_status = {}

        # Process each library
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
                        # Extract status and date information
                        text_parts = show_info['text_content'].split()
                        status_text = text_parts[0]  # First word is usually the status

                        # Extract date if present
                        date_str = ''
                        for part in text_parts:
                            if '/' in part and any(c.isdigit() for c in part):
                                date_str = part
                                break

                        # Store show status
                        current_status[show.title] = {
                            'status': status_text,
                            'date': date_str,
                            'text': show_info['text_content']
                        }

                        # Check if status or date changed from previous run
                        if show.title in previous_status:
                            prev = previous_status[show.title]
                            curr = current_status[show.title]

                            # Determine what changed
                            status_changed = prev['status'] != curr['status']
                            date_changed = prev['date'] != curr['date'] and curr['date']  # Only if we have a date

                            if status_changed or date_changed:
                                logging.debug(f"Change detected for {show.title}: Status changed: {status_changed}, Date changed: {date_changed}")
                                logging.debug(f"Previous: {prev['status']} ({prev['date']}), Current: {curr['status']} ({curr['date']})")

                                # Find the appropriate category
                                status_key = None

                                # If status changed, use the new status category
                                if status_changed:
                                    if 'AIRING' in show_info['text_content']:
                                        status_key = 'AIRING'
                                    elif 'SEASON FINALE' in show_info['text_content']:
                                        status_key = 'SEASON_FINALE'
                                    elif 'MID SEASON FINALE' in show_info['text_content']:
                                        status_key = 'MID_SEASON_FINALE'
                                    elif 'FINAL EPISODE' in show_info['text_content']:
                                        status_key = 'FINAL_EPISODE'
                                    elif 'SEASON PREMIERE' in show_info['text_content']:
                                        status_key = 'SEASON_PREMIERE'
                                    elif 'RETURNING' in show_info['text_content']:
                                        status_key = 'RETURNING'
                                    elif 'ENDED' in show_info['text_content']:
                                        status_key = 'ENDED'
                                    elif 'CANCELLED' in show_info['text_content']:
                                        status_key = 'CANCELLED'
                                # If only date changed, use DATE_CHANGED category
                                elif date_changed and not status_changed:
                                    status_key = 'DATE_CHANGED'

                                if status_key:
                                    changes[status_key].append({
                                        'title': show.title,
                                        'prev_status': prev['status'],
                                        'new_status': curr['status'],
                                        'prev_date': prev['date'],
                                        'new_date': curr['date'],
                                        'full_text': curr['text'],
                                        'library': library_name
                                    })
                        else:
                            # New show that wasn't processed before
                            curr = current_status[show.title]

                            # Only add to notification if it has an interesting status (not just ENDED/CANCELLED)
                            if status_text not in ['ENDED', 'CANCELLED']:
                                status_key = None
                                if 'AIRING' in show_info['text_content']:
                                    status_key = 'AIRING'
                                elif 'SEASON FINALE' in show_info['text_content']:
                                    status_key = 'SEASON_FINALE'
                                elif 'MID SEASON FINALE' in show_info['text_content']:
                                    status_key = 'MID_SEASON_FINALE'
                                elif 'FINAL EPISODE' in show_info['text_content']:
                                    status_key = 'FINAL_EPISODE'
                                elif 'SEASON PREMIERE' in show_info['text_content']:
                                    status_key = 'SEASON_PREMIERE'
                                elif 'RETURNING' in show_info['text_content']:
                                    status_key = 'RETURNING'

                                # On first run, only include shows with dates or FINAL_EPISODE status
                                if status_key:
                                    if is_first_run:
                                        # Check if the show has a date or is a final episode
                                        has_date = bool(curr['date'])

                                        # Only add if it has a date or is a final episode
                                        if has_date or status_key == 'FINAL_EPISODE':
                                            changes[status_key].append({
                                                'title': show.title,
                                                'prev_status': 'NEW',
                                                'new_status': curr['status'],
                                                'prev_date': '',
                                                'new_date': curr['date'],
                                                'full_text': curr['text'],
                                                'library': library_name
                                            })
                                    else:
                                        # Not first run, include all status changes
                                        changes[status_key].append({
                                            'title': show.title,
                                            'prev_status': 'NEW',
                                            'new_status': curr['status'],
                                            'prev_date': '',
                                            'new_date': curr['date'],
                                            'full_text': curr['text'],
                                            'library': library_name
                                        })

                        # Format the title for YAML key
                        formatted_title = show.title.replace(' ', '_')
                        
                        # Create a safe version of the title with wildcards for special characters
                        safe_title = self.sanitize_title_for_search(show.title)
                        
                        # Add to YAML data
                        yaml_data['overlays'][f'{library_name}_Status_{formatted_title}'] = {
                            'overlay': {
                                'back_color': show_info['back_color'],
                                'back_height': 90,
                                'back_width': 1000,
                                'color': '#FFFFFF',
                                'font': show_info['font'],
                                'font_size': 70,
                                'horizontal_align': 'center',
                                'horizontal_offset': 0,
                                'name': f"text({show_info['text_content']})",
                                'vertical_align': 'top',
                                'vertical_offset': 0,
                            },
                            'plex_search': {
                                'all': {
                                    'title.is': safe_title
                                }
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

        # Create collection files
        self.create_yaml_collections()

        # Update Trakt list with airing shows
        list_name = "Next Airing"
        list_slug = self.get_or_create_trakt_list(list_name, headers)

        if list_slug and self.airing_shows:
            sorted_airing_shows = self.sort_airing_shows_by_date()
            self.update_trakt_list(list_slug, sorted_airing_shows, headers)
            console.print(f"[green]Updated '{list_name}' Trakt list with {len(sorted_airing_shows)} airing shows[/green]")
        elif not self.airing_shows:
            console.print("[yellow]No airing shows found to add to Trakt list[/yellow]")

        # Save current status for next run
        try:
            with open(status_cache_file, 'w') as f:
                json.dump(current_status, f)
        except Exception as e:
            logging.error(f"Error saving status cache: {str(e)}")

        # Send notifications if there are changes and not running in quiet mode
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
    # Load config if not provided
    if not config:
        config_path = "/app/config/config.yaml" if os.environ.get('RUNNING_IN_DOCKER') == 'true' else "config/config.yaml"
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
        except Exception as e:
            print(f"Error loading configuration: {str(e)}")
            return False

    # Check if TV Status Tracker is enabled
    if not config.get('services', {}).get('tv_status_tracker', {}).get('enabled', False):
        print("TV/Anime Status Tracker is disabled in configuration.")
        return False

    # Run the tracker
    tracker = TVStatusTracker(config)
    return tracker.run()

# Allow running directly
if __name__ == "__main__":
    run_tv_status_tracker()
