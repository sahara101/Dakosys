#!/usr/bin/env python3
"""
Size Overlay Service for DAKOSYS
Creates Kometa/PMM overlays displaying file sizes for movies and TV shows
"""

import os
import re
import yaml
import json
import logging
from plexapi.server import PlexServer
from rich.console import Console
import requests
from shared_utils import setup_rotating_logger
from datetime import datetime

# Initialize console for rich output
console = Console()

# Set up data directory and logging
DATA_DIR = "data" if os.environ.get('RUNNING_IN_DOCKER') != 'true' else "/app/data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

log_file = os.path.join(DATA_DIR, "size_overlay.log")
logger = setup_rotating_logger("size_overlay", log_file)

# Global configuration
CONFIG = None

# File to store previous sizes for change detection
SIZES_FILE = os.path.join(DATA_DIR, "previous_sizes.json")

def extract_key(full_key):
    """Extract numeric key from a Plex metadata key."""
    match = re.search(r'(\d+)', full_key)
    return match.group(1) if match else None

def format_size_change(old_size, new_size):
    """Format size change with appropriate symbols and colors for logging."""
    if old_size is None:
        return f"NEW: {new_size:.2f} GB"
    
    change = new_size - old_size
    if change > 0:
        return f"{old_size:.2f} GB → {new_size:.2f} GB (+{change:.2f} GB)"
    elif change < 0:
        return f"{old_size:.2f} GB → {new_size:.2f} GB ({change:.2f} GB)"
    else:
        return f"{new_size:.2f} GB (no change)"

def load_previous_sizes():
    """Load previously saved sizes from JSON file."""
    if os.path.exists(SIZES_FILE):
        try:
            with open(SIZES_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading previous sizes: {str(e)}")
    return {}

def save_current_sizes(sizes_data):
    """Save current sizes to JSON file for future reference."""
    try:
        with open(SIZES_FILE, 'w') as f:
            json.dump(sizes_data, f, indent=2)
        logger.debug(f"Saved size data to {SIZES_FILE}")
        return True
    except Exception as e:
        logger.error(f"Error saving sizes data: {str(e)}")
        return False

def connect_to_plex():
    """Connect to Plex server using shared utility."""
    try:
        logger.info("Connecting to Plex server...")
        plex = PlexServer(CONFIG['plex']['url'], CONFIG['plex']['token'])
        logger.info("Connected to Plex server successfully!")
        return plex
    except Exception as e:
        logger.error(f"Failed to connect to Plex server: {str(e)}")
        return None

def get_library_sections(plex, library_types=None):
    """Get all library sections from Plex.
    
    Args:
        plex: PlexServer instance
        library_types: Optional list of library types to filter (e.g., ['movie', 'show'])
        
    Returns:
        List of library sections
    """
    try:
        sections = []
        for section in plex.library.sections():
            if not library_types or section.type in library_types:
                sections.append({
                    'key': section.key,
                    'title': section.title,
                    'type': section.type
                })
        return sections
    except Exception as e:
        logger.error(f"Error getting library sections: {str(e)}")
        return []

def process_movie_library(plex, library):
    """Process a movie library to get size information.
    
    Args:
        plex: PlexServer instance
        library: Dictionary with library information
        
    Returns:
        List of movies with size information
    """
    logger.info(f"Processing movie library '{library['title']}'...")
    
    movies_info = []
    try:
        library_section = plex.library.sectionByID(library['key'])
        total_movies = 0
        processed_movies = 0
        total_size_gb = 0
        
        # Get count for progress logging
        all_movies = library_section.all()
        total_movies = len(all_movies)
        logger.info(f"Found {total_movies} movies to process")
        
        for movie in all_movies:
            try:
                # Calculate total size for all media parts
                total_size_bytes = 0
                for media in movie.media:
                    for part in media.parts:
                        total_size_bytes += part.size
                
                # Convert to GB and round to 2 decimal places
                size_gb = round(total_size_bytes / 1073741824, 2)
                total_size_gb += size_gb
                
                movies_info.append({
                    'title': movie.title,
                    'size_gb': size_gb,
                    'key': movie.key,
                    'numerical_key': extract_key(movie.key)
                })
                
                processed_movies += 1
                if processed_movies % 50 == 0 or processed_movies == total_movies:
                    logger.info(f"Processed {processed_movies}/{total_movies} movies ({processed_movies/total_movies*100:.1f}%)")
                
            except Exception as e:
                logger.warning(f"Error processing movie {movie.title}: {str(e)}")
        
        logger.info(f"Processed {len(movies_info)} movies in library '{library['title']}' with total size of {total_size_gb:.2f} GB")
        return movies_info
    except Exception as e:
        logger.error(f"Error processing movie library '{library['title']}': {str(e)}")
        return []

def process_show_library(plex, library):
    """Process a TV show library to get size information.
    
    Args:
        plex: PlexServer instance
        library: Dictionary with library information
        
    Returns:
        List of shows with size information
    """
    logger.info(f"Processing TV library '{library['title']}'...")
    
    shows_info = []
    try:
        library_section = plex.library.sectionByID(library['key'])
        total_shows = 0
        processed_shows = 0
        total_size_gb = 0
        total_episodes = 0
        
        # Get count for progress logging
        all_shows = library_section.all()
        total_shows = len(all_shows)
        logger.info(f"Found {total_shows} shows to process")
        
        for show in all_shows:
            try:
                # Calculate total size for all episodes
                total_size_bytes = 0
                episode_count = 0
                
                for season in show.seasons():
                    for episode in season.episodes():
                        episode_count += 1
                        for media in episode.media:
                            for part in media.parts:
                                total_size_bytes += part.size
                
                # Convert to GB and round to 2 decimal places
                size_gb = round(total_size_bytes / 1073741824, 2)
                total_size_gb += size_gb
                total_episodes += episode_count
                
                shows_info.append({
                    'title': show.title,
                    'size_gb': size_gb,
                    'key': show.key,
                    'numerical_key': extract_key(show.key),
                    'episode_count': episode_count
                })
                
                processed_shows += 1
                if processed_shows % 10 == 0 or processed_shows == total_shows:
                    logger.info(f"Processed {processed_shows}/{total_shows} shows ({processed_shows/total_shows*100:.1f}%)")
                
            except Exception as e:
                logger.warning(f"Error processing show {show.title}: {str(e)}")
        
        logger.info(f"Processed {len(shows_info)} shows with {total_episodes} episodes in library '{library['title']}' with total size of {total_size_gb:.2f} GB")
        return shows_info
    except Exception as e:
        logger.error(f"Error processing TV library '{library['title']}': {str(e)}")
        return []

# Function copied from tv_status_tracker.py for consistent title searching
def sanitize_title_for_search(title):
    """Sanitize title for Plex search, adding wildcards."""
    # Start with a wildcard
    safe_title = "%" + title

    # Add wildcards around special characters that might cause issues
    # Check from the second character onwards to avoid double % at the start
    if "'" in title:
        safe_title = safe_title.replace("'", "%'%")
    if "," in title:
        safe_title = safe_title.replace(",", "%,%") # Kometa uses ,%
    if "&" in title:
        safe_title = safe_title.replace("&", "%&%")
    if ":" in title:
        safe_title = safe_title.replace(":", "%:%")
    if "/" in title:
        safe_title = safe_title.replace("/", "%/%")

    # Removed incorrect logic that added a trailing %

    logger.debug(f"Sanitized title for search: '{safe_title}' from original '{title}'")
    return safe_title

def generate_movie_overlay_yaml(movies_info, library_title, overlay_config):
    """Generate overlay YAML file for movies.

    Args:
        movies_info: List of movies with size information
        library_title: Library title
        overlay_config: Overlay configuration settings

    Returns:
        YAML content as dictionary
    """
    yaml_data = {"overlays": {}}

    # Get overlay style settings with defaults
    font_size = overlay_config.get('font_size', 63)
    font_color = overlay_config.get('font_color', "#FFFFFF")
    back_color = overlay_config.get('back_color', "#00000099")
    back_height = overlay_config.get('back_height', 80)
    vertical_align = overlay_config.get('vertical_align', "top")
    horizontal_align = overlay_config.get('horizontal_align', "center")
    horizontal_offset = overlay_config.get('horizontal_offset', 0)
    vertical_offset = overlay_config.get('vertical_offset', 0)
    back_width = overlay_config.get('back_width', 1920)

    for movie in movies_info:
        overlay_key = f"{movie['numerical_key']}-{movie['size_gb']}-GB-overlay"

        yaml_data["overlays"][overlay_key] = {
            "overlay": {
                "name": f"text({movie['size_gb']} GB)",
                "horizontal_offset": horizontal_offset,
                "horizontal_align": horizontal_align,
                "vertical_offset": vertical_offset,
                "vertical_align": vertical_align,
                "font_size": font_size,
                "font_color": font_color,
                "back_color": back_color,
                "back_width": back_width,
                "back_height": back_height,
            },
            "plex_search": {
                "all": {
                    "title.is": sanitize_title_for_search(movie['title'])
                }
            }
        }

    return yaml_data

def generate_show_overlay_yaml(shows_info, library_title, overlay_config):
    """Generate overlay YAML file for TV shows.

    Args:
        shows_info: List of shows with size information
        library_title: Library title
        overlay_config: Overlay configuration settings

    Returns:
        YAML content as dictionary
    """
    yaml_data = {"overlays": {}}

    # Get overlay style settings with defaults
    font_size = overlay_config.get('font_size', 55)
    font_color = overlay_config.get('font_color', "#FFFFFF")
    back_color = overlay_config.get('back_color', "#00000099")
    back_height = overlay_config.get('back_height', 80)
    vertical_align = overlay_config.get('vertical_align', "bottom")
    horizontal_align = overlay_config.get('horizontal_align', "center")
    show_episode_count = overlay_config.get('show_episode_count', False)
    horizontal_offset = overlay_config.get('horizontal_offset', 0)
    vertical_offset = overlay_config.get('vertical_offset', 0)
    back_width = overlay_config.get('back_width', 1920)

    for show in shows_info:
        overlay_key = f"{show['numerical_key']}-{show['size_gb']}-GB-overlay"

        # Prepare overlay text based on settings
        if show_episode_count:
            overlay_text = f"{show['size_gb']} GB ({show['episode_count']} episodes)"
        else:
            overlay_text = f"{show['size_gb']} GB"

        yaml_data["overlays"][overlay_key] = {
            "overlay": {
                "name": f"text({overlay_text})",
                "horizontal_offset": horizontal_offset,
                "horizontal_align": horizontal_align,
                "vertical_offset": vertical_offset,
                "vertical_align": vertical_align,
                "font_size": font_size,
                "font_color": font_color,
                "back_color": back_color,
                "back_width": back_width,
                "back_height": back_height,
            },
            "plex_search": {
                "all": {
                    "title.is": sanitize_title_for_search(show['title'])
                }
            }
        }

    return yaml_data

def write_overlay_yaml(yaml_data, overlay_path, library_title):
    """Write overlay YAML file.
    
    Args:
        yaml_data: YAML content as dictionary
        overlay_path: Path to write the overlay file
        library_title: Library title for filename
        
    Returns:
        Boolean indicating success or failure
    """
    filename = f"size-overlays-{library_title.lower().replace(' ', '-')}.yml"
    file_path = os.path.join(overlay_path, filename)
    
    try:
        with open(file_path, 'w') as file:
            yaml.dump(yaml_data, file, default_flow_style=False, sort_keys=False)
        logger.info(f"Successfully wrote overlay file: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error writing overlay file {file_path}: {str(e)}")
        return False

def track_library_changes(library_title, library_type, current_data, previous_sizes):
    """Track changes to library sizes for better reporting.

    Args:
        library_title: Title of the library
        library_type: Type of library ('movie' or 'show')
        current_data: Current size information
        previous_sizes: Previous size information

    Returns:
        Tuple of (library_key, total_size, size_diff, item_changes)
    """
    library_key = f"{library_type}:{library_title}"

    # Calculate total size of current data
    total_size = sum(item['size_gb'] for item in current_data)

    # Get previous total size
    previous_total = 0
    if library_key in previous_sizes and 'total_size' in previous_sizes[library_key]:
        previous_total = previous_sizes[library_key]['total_size']

    # Calculate size difference
    size_diff = total_size - previous_total

    # Track individual item changes
    item_changes = []
    
    # Get previous items data
    previous_items = {}
    previous_episodes = {}
    
    if library_key in previous_sizes and 'items' in previous_sizes[library_key]:
        previous_items = previous_sizes[library_key]['items']
    
    # Get previous episode counts if they exist
    if library_key in previous_sizes and 'episodes' in previous_sizes[library_key]:
        previous_episodes = previous_sizes[library_key]['episodes']
    else:
        previous_episodes = {}

    # Check if this is the first run (no previous data)
    is_first_run = not previous_items

    # Skip change detection on first run, just record current state
    if not is_first_run:
        for item in current_data:
            title = item['title']
            current_size = item['size_gb']
            previous_size = previous_items.get(title, None)
            
            # Get episode counts for shows
            current_episode_count = item.get('episode_count', 0) if library_type == 'show' else 0
            previous_episode_count = previous_episodes.get(title, 0) if library_type == 'show' else 0

            # Determine change type based on what changed
            if previous_size is None:
                change_type = "NEW"
                size_change = current_size
            elif library_type == 'show' and current_episode_count > previous_episode_count:
                change_type = "NEW_EPISODES"
                size_change = current_size - previous_size
                episodes_added = current_episode_count - previous_episode_count
            elif library_type == 'show' and current_episode_count < previous_episode_count:
                change_type = "REMOVED_EPISODES"
                size_change = current_size - previous_size
                episodes_removed = previous_episode_count - current_episode_count
            elif abs(current_size - previous_size) > 0.01:  
                change_type = "QUALITY_CHANGE"
                size_change = current_size - previous_size
            else:
                continue

            change_item = {
                'title': title,
                'previous_size': previous_size,
                'current_size': current_size,
                'change': size_change,
                'type': change_type,
                'library_type': library_type
            }

            # Add episode info for TV shows and anime
            if library_type == 'show':
                change_item['episode_count'] = current_episode_count
                if change_type in ["NEW_EPISODES", "REMOVED_EPISODES", "QUALITY_CHANGE"]:
                    change_item['previous_episode_count'] = previous_episode_count
                    if change_type == "NEW_EPISODES":
                        change_item['episodes_added'] = episodes_added
                    elif change_type == "REMOVED_EPISODES":
                        change_item['episodes_removed'] = episodes_removed

            item_changes.append(change_item)
        
        # Check for items that were removed completely
        for title, previous_size in previous_items.items():
            if not any(item['title'] == title for item in current_data):
                change_type = "REMOVED"
                size_change = -previous_size  
                
                change_item = {
                    'title': title,
                    'previous_size': previous_size,
                    'current_size': 0,
                    'change': size_change,
                    'type': change_type,
                    'library_type': library_type
                }
                
                # Add episode info for removed shows
                if library_type == 'show' and title in previous_episodes:
                    change_item['previous_episode_count'] = previous_episodes[title]
                
                item_changes.append(change_item)

    # Update previous sizes for next run
    new_items = {item['title']: item['size_gb'] for item in current_data}
    
    # Save episode counts for shows
    new_episodes = {}
    if library_type == 'show':
        new_episodes = {item['title']: item.get('episode_count', 0) for item in current_data}
    
    previous_sizes[library_key] = {
        'total_size': total_size,
        'items': new_items,
        'episodes': new_episodes,
        'last_updated': datetime.now().isoformat()
    }

    return library_key, total_size, size_diff, item_changes

def format_filesize(size_in_gb):
    """Format file size in a human-readable way."""
    if size_in_gb >= 1000:
        return f"{size_in_gb/1024:.2f} TB"
    else:
        return f"{size_in_gb:.2f} GB"

# Helper function to split a large text block into chunks for Discord fields
def split_text_into_fields(name_prefix, text, max_len=1024, max_fields=25):
    """Splits text into chunks suitable for Discord embed field values."""
    fields = []
    if not text or not text.strip():
        return fields

    lines = text.strip().split('\n')
    current_chunk = ""
    field_count = 0

    for line in lines:
        # Check if adding the next line exceeds max length
        if len(current_chunk) + len(line) + 1 > max_len:
            if current_chunk:
                field_name = f"{name_prefix}" if field_count == 0 else f"{name_prefix} (cont. {field_count})"
                field_name = field_name[:256]
                fields.append({"name": field_name, "value": current_chunk.strip()})
                field_count += 1
                if field_count >= max_fields:
                    logger.warning(f"Reached max fields ({max_fields}) for '{name_prefix}'. Truncating changes.")
                    if fields: 
                         fields[-1]["value"] = fields[-1]["value"][:max_len - 50] + "\n... (message truncated due to field limit)"
                    return fields 
                current_chunk = "" 

            if len(line) > max_len:
                logger.warning(f"Single line exceeds max field length ({max_len}). Truncating line: {line[:100]}...")
                line = line[:max_len - 20] + "... (line truncated)"

            if line:
                current_chunk = line + '\n'
            else:
                continue
        else:
            current_chunk += line + '\n'

    if current_chunk.strip() and field_count < max_fields:
        field_name = f"{name_prefix}" if field_count == 0 else f"{name_prefix} (cont. {field_count})"
        field_name = field_name[:256] 
        fields.append({"name": field_name, "value": current_chunk.strip()})

    return fields

def run_size_overlay_service():
    """Main function to run the size overlay service."""
    global CONFIG

    import trakt_auth

    # Start time for performance tracking
    start_time = datetime.now()
    logger.info(f"Size Overlay service started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Load configuration
    CONFIG = trakt_auth.load_config()
    if not CONFIG:
        logger.error("Failed to load configuration")
        return False

    # Check if service is enabled
    if not CONFIG.get('services', {}).get('size_overlay', {}).get('enabled', False):
        logger.info("Size Overlay service is disabled, skipping")
        return True  

    # Get paths for Kometa overlays
    yaml_output_dir = CONFIG.get('kometa_config', {}).get('yaml_output_dir', '/kometa/config/overlays')

    if not os.path.exists(yaml_output_dir):
        logger.warning(f"Overlay directory doesn't exist: {yaml_output_dir}")
        try:
            os.makedirs(yaml_output_dir, exist_ok=True)
            logger.info(f"Created overlay directory: {yaml_output_dir}")
        except Exception as e:
            logger.error(f"Failed to create overlay directory: {str(e)}")
            return False

    # Get service-specific configuration
    service_config = CONFIG.get('services', {}).get('size_overlay', {})
    movie_overlay_config = service_config.get('movie_overlay', {})
    show_overlay_config = service_config.get('show_overlay', {})

    # Get enabled libraries
    enabled_movie_libraries = service_config.get('movie_libraries', [])
    enabled_tv_libraries = service_config.get('tv_libraries', [])
    enabled_anime_libraries = service_config.get('anime_libraries', [])

    # Connect to Plex
    plex = connect_to_plex()
    if not plex:
        logger.error("Failed to connect to Plex server")
        return False

    # Get all libraries
    libraries = get_library_sections(plex)
    logger.info(f"Found {len(libraries)} libraries in Plex")

    # Load previous sizes for change tracking
    previous_sizes = load_previous_sizes()

    # Process each library based on type
    success = True
    created_files = []
    library_changes = []
    total_items_processed = 0

    # Track totals for reporting
    total_movies = 0
    total_shows = 0
    total_episodes = 0
    total_size_gb = 0
    size_change_gb = 0
    significant_changes = []

    for library in libraries:
        library_title = library['title']
        library_type = library['type']

        # Process movie libraries
        if library_type == 'movie' and (not enabled_movie_libraries or library_title in enabled_movie_libraries):
            logger.info(f"Processing movie library: {library_title}")
            movies_info = process_movie_library(plex, library)
            total_items_processed += len(movies_info)
            total_movies += len(movies_info)

            if movies_info:
                # Track changes for this library
                library_key, lib_total_size, lib_size_diff, item_changes = track_library_changes(
                    library_title, "movie", movies_info, previous_sizes
                )

                total_size_gb += lib_total_size
                size_change_gb += lib_size_diff

                # Log significant changes
                for change in item_changes:
                    if change['type'] == "NEW":
                        logger.info(f"New movie: {change['title']} ({change['current_size']:.2f} GB)")
                        significant_changes.append(change)
                    elif change['type'] == "QUALITY_CHANGE":
                        size_diff = change['change']
                        if abs(size_diff) > 0:
                            logger.info(f"Movie quality change: {change['title']} - {format_size_change(change['previous_size'], change['current_size'])}")
                            significant_changes.append(change)
                    elif change['type'] == "REMOVED":
                        logger.info(f"Removed movie: {change['title']} ({change['previous_size']:.2f} GB)")
                        significant_changes.append(change)

                library_changes.append({
                    'library': library_title,
                    'type': 'movie',
                    'total_size': lib_total_size,
                    'size_diff': lib_size_diff,
                    'item_count': len(movies_info),
                    'changed_items': item_changes
                })

                # Generate and write overlay YAML
                yaml_data = generate_movie_overlay_yaml(movies_info, library_title, movie_overlay_config)
                if write_overlay_yaml(yaml_data, yaml_output_dir, library_title):
                    created_files.append(f"size-overlays-{library_title.lower().replace(' ', '-')}.yml")
                else:
                    success = False

        # Process TV libraries (both regular TV and anime)
        elif library_type == 'show' and (
            (not enabled_tv_libraries or library_title in enabled_tv_libraries) or
            (not enabled_anime_libraries or library_title in enabled_anime_libraries)
        ):
            logger.info(f"Processing TV library: {library_title}")
            shows_info = process_show_library(plex, library)
            total_items_processed += len(shows_info)
            total_shows += len(shows_info)

            # Sum episode counts only for TV shows
            show_episodes = sum(show.get('episode_count', 0) for show in shows_info)
            total_episodes += show_episodes

            if shows_info:
                # Track changes for this library
                library_key, lib_total_size, lib_size_diff, item_changes = track_library_changes(
                    library_title, "show", shows_info, previous_sizes
                )

                total_size_gb += lib_total_size
                size_change_gb += lib_size_diff

                # Log significant changes
                for change in item_changes:
                    if change['type'] == "NEW":
                        episode_text = f"({change.get('episode_count', 0)} episodes)" if 'episode_count' in change else ""
                        logger.info(f"New show: {change['title']} {episode_text} - {change['current_size']:.2f} GB")
                        significant_changes.append(change)
                    elif change['type'] == "NEW_EPISODES":
                        size_diff = change['change']
                        episodes_added = change.get('episodes_added', 'unknown')
                        episode_count = change.get('episode_count', 0)
                        logger.info(f"New episodes: {change['title']} (+{episodes_added} episodes, now {episode_count} total) - {format_size_change(change['previous_size'], change['current_size'])}")
                        significant_changes.append(change)
                    elif change['type'] == "REMOVED_EPISODES":
                        size_diff = change['change']
                        episodes_removed = change.get('episodes_removed', 'unknown')
                        episode_count = change.get('episode_count', 0)
                        logger.info(f"Removed episodes: {change['title']} (-{episodes_removed} episodes, now {episode_count} total) - {format_size_change(change['previous_size'], change['current_size'])}")
                        significant_changes.append(change)
                    elif change['type'] == "QUALITY_CHANGE":
                        size_diff = change['change']
                        if abs(size_diff) > 0:
                            episode_text = f"({change.get('episode_count', 0)} episodes)" if 'episode_count' in change else ""
                            logger.info(f"Show quality change: {change['title']} {episode_text} - {format_size_change(change['previous_size'], change['current_size'])}")
                            significant_changes.append(change)
                    elif change['type'] == "REMOVED":
                        prev_ep_count = change.get('previous_episode_count', 0)
                        logger.info(f"Removed show: {change['title']} ({prev_ep_count} episodes, {change['previous_size']:.2f} GB)")
                        significant_changes.append(change)

                library_changes.append({
                    'library': library_title,
                    'type': 'show',
                    'total_size': lib_total_size,
                    'size_diff': lib_size_diff,
                    'item_count': len(shows_info),
                    'episode_count': show_episodes,  
                    'changed_items': item_changes
                })

                # Generate and write overlay YAML
                yaml_data = generate_show_overlay_yaml(shows_info, library_title, show_overlay_config)
                if write_overlay_yaml(yaml_data, yaml_output_dir, library_title):
                    created_files.append(f"size-overlays-{library_title.lower().replace(' ', '-')}.yml")
                else:
                    success = False

    # Save updated sizes for next run
    save_current_sizes(previous_sizes)

    # Calculate elapsed time
    end_time = datetime.now()
    elapsed_time = end_time - start_time
    elapsed_seconds = elapsed_time.total_seconds()

    # Log summary
    logger.info(f"Size Overlay service completed in {elapsed_seconds:.1f} seconds")
    logger.info(f"Processed {total_movies} movies and {total_shows} shows with {total_episodes} episodes")
    logger.info(f"Total media size: {total_size_gb:.2f} GB ({'+' if size_change_gb > 0 else ''}{size_change_gb:.2f} GB change)")
    logger.info(f"Created {len(created_files)} overlay files")

    # Send notification if configured
    if CONFIG.get('notifications', {}).get('enabled', False):
        try:
            from notifications import send_discord_notification

            # Determine if this is the first run or if there are changes
            is_first_run = not os.path.exists(SIZES_FILE) or previous_sizes == {}
            has_changes = len(significant_changes) > 0

            # Skip notification entirely if no changes and not first run
            if not is_first_run and not has_changes and not created_files:
                logger.info("Skipping notification - no changes to report")
                return True

            # Create the common library summary that will be included in all notifications
            libraries_text = ""
            for library in library_changes:
                lib_name = library['library']
                lib_type = library['type']
                lib_size = library['total_size']
                lib_count = library['item_count']

                # Get episode count for show libraries
                if lib_type == "movie":
                    libraries_text += f"• {lib_name}: {format_filesize(lib_size)} - {lib_count} movies\n"
                else:
                    episode_count = library.get('episode_count', 0)
                    libraries_text += f"• {lib_name}: {format_filesize(lib_size)} - {lib_count} shows ({episode_count} episodes)\n"

            # Create total summary text
            summary_text = f"{format_filesize(total_size_gb)} across {total_movies} movies and {total_shows} shows with {total_episodes} episodes."

            if is_first_run:
                # First run notification
                title = "Size Overlay Service - Initial Scan"
                message = f"Completed initial media size scan in {elapsed_seconds:.1f} seconds."

                custom_fields = [
                    {
                        "name": "Media Libraries",
                        "value": libraries_text.strip()
                    },
                    {
                        "name": "Total Media Size",
                        "value": summary_text
                    }
                ]

                color = 5763719

            elif has_changes:
                num_new_media = len([c for c in significant_changes if c['type'] == "NEW"])
                num_new_episodes = len([c for c in significant_changes if c['type'] == "NEW_EPISODES"])
                num_removed_episodes = len([c for c in significant_changes if c['type'] == "REMOVED_EPISODES"])
                num_quality_changes = len([c for c in significant_changes if c['type'] == "QUALITY_CHANGE"])
                num_removed_media = len([c for c in significant_changes if c['type'] == "REMOVED"])

                diff_text = f"{'+' if size_change_gb > 0 else ''}{format_filesize(size_change_gb)}"
                
                changes = []
                if num_new_media > 0:
                    changes.append(f"{num_new_media} new {'items' if num_new_media != 1 else 'item'}")
                if num_new_episodes > 0:
                    changes.append(f"{num_new_episodes} {'shows' if num_new_episodes != 1 else 'show'} with new episodes")
                if num_removed_episodes > 0:
                    changes.append(f"{num_removed_episodes} {'shows' if num_removed_episodes != 1 else 'show'} with removed episodes")
                if num_quality_changes > 0:
                    changes.append(f"{num_quality_changes} quality {'changes' if num_quality_changes != 1 else 'change'}")
                if num_removed_media > 0:
                    changes.append(f"{num_removed_media} removed {'items' if num_removed_media != 1 else 'item'}")
                
                if len(changes) > 1:
                    message_changes = ", ".join(changes[:-1]) + ", and " + changes[-1]
                else:
                    message_changes = changes[0] if changes else "changes"
                
                if num_new_media > 0 and num_new_episodes > 0:
                    title = "Size Overlay Service - New Media and Episodes"
                elif num_new_media > 0:
                    title = "Size Overlay Service - New Media Added"
                elif num_new_episodes > 0:
                    title = "Size Overlay Service - New Episodes Added"
                elif num_removed_media > 0 or num_removed_episodes > 0:
                    title = "Size Overlay Service - Media Removed"
                elif num_quality_changes > 0:
                    title = "Size Overlay Service - Quality Changes"
                else:
                    title = "Size Overlay Service - Media Changes Detected"
                
                message = f"Detected {message_changes}. Total change: {diff_text}"

                changes_text = ""

                item_changes = []
                for library in library_changes:
                    for item in library['changed_items']:
                        item['library_name'] = library['library']
                        item['library_type'] = library['type']
                        item_changes.append(item)

                sorted_changes = sorted(
                    item_changes,
                    key=lambda x: (
                        0 if x['type'] == "NEW" else 
                        (1 if x['type'] == "NEW_EPISODES" else 
                         (2 if x['type'] == "QUALITY_CHANGE" else 
                          (3 if x['type'] == "REMOVED_EPISODES" else 4))), 
                        -abs(x.get('change', 0) or 0)
                    )
                )

                changes_by_library = {}
                for change in sorted_changes:
                    library = change.get('library_name', "Unknown")

                    if library not in changes_by_library:
                        changes_by_library[library] = []
                    changes_by_library[library].append(change)

                for library, changes in changes_by_library.items():
                    changes_text += f"**{library}**\n"
                    
                    new_items = [c for c in changes if c['type'] == "NEW"]
                    if new_items:
                        for item in new_items: 
                            item_title = item['title']
                            curr = item['current_size']
                            episode_text = f" ({item['episode_count']} episodes)" if item.get('library_type') == 'show' and 'episode_count' in item else ""
                            changes_text += f"• NEW: {item_title}{episode_text} - {format_filesize(curr)}\n"
                    
                    new_episode_items = [c for c in changes if c['type'] == "NEW_EPISODES"]
                    if new_episode_items:
                        for item in new_episode_items: 
                            item_title = item['title']
                            prev = item['previous_size']
                            curr = item['current_size']
                            diff = item['change']
                            diff_sign = "+" if diff > 0 else ""

                            episodes_added = item.get('episodes_added', 'unknown')
                            current_episodes = item.get('episode_count', 0)
                            episode_text = f" ({current_episodes} episodes, +{episodes_added} new)"

                            changes_text += f"• NEW EPISODES: {item_title}{episode_text} - {prev:.2f} GB → {curr:.2f} GB ({diff_sign}{diff:.2f} GB)\n"
                    
                    quality_items = [c for c in changes if c['type'] == "QUALITY_CHANGE"]
                    if quality_items:
                        for item in quality_items: 
                            item_title = item['title']
                            prev = item['previous_size']
                            curr = item['current_size']
                            diff = item['change']
                            diff_sign = "+" if diff > 0 else ""

                            episode_text = ""
                            if item.get('library_type') == 'show' and 'episode_count' in item:
                                episode_text = f" ({item['episode_count']} episodes)"

                            changes_text += f"• QUALITY CHANGE: {item_title}{episode_text} - {prev:.2f} GB → {curr:.2f} GB ({diff_sign}{diff:.2f} GB)\n"
                    
                    removed_episode_items = [c for c in changes if c['type'] == "REMOVED_EPISODES"]
                    if removed_episode_items:
                        for item in removed_episode_items: 
                            item_title = item['title']
                            prev = item['previous_size']
                            curr = item['current_size']
                            diff = item['change']
                            diff_sign = "+" if diff > 0 else ""

                            episodes_removed = item.get('episodes_removed', 'unknown')
                            current_episodes = item.get('episode_count', 0)
                            episode_text = f" ({current_episodes} episodes, {episodes_removed} removed)"

                            changes_text += f"• REMOVED EPISODES: {item_title}{episode_text} - {prev:.2f} GB → {curr:.2f} GB ({diff_sign}{diff:.2f} GB)\n"
                    
                    removed_items = [c for c in changes if c['type'] == "REMOVED"]
                    if removed_items:
                        for item in removed_items: 
                            item_title = item['title']
                            prev = item['previous_size']

                            episode_text = ""
                            if item.get('library_type') == 'show' and 'previous_episode_count' in item:
                                episode_text = f" ({item['previous_episode_count']} episodes)"

                            changes_text += f"• REMOVED: {item_title}{episode_text} - {prev:.2f} GB\n"
                    
                    changes_text += "\n"  

                custom_fields = [
                    {
                        "name": "Media Libraries",
                        "value": libraries_text.strip()
                    },
                    {
                        "name": "Total Media Size",
                        "value": summary_text
                    }
                ]

                if changes_text.strip():
                    change_fields = split_text_into_fields("Changes Detected", changes_text.strip())
                    custom_fields.extend(change_fields)

                color = 15105570

            else:
                title = "Size Overlay Service - Updated"
                message = f"Completed scan in {elapsed_seconds:.1f} seconds."

                custom_fields = [
                    {
                        "name": "Media Libraries",
                        "value": libraries_text.strip()
                    },
                    {
                        "name": "Total Media Size",
                        "value": summary_text
                    }
                ]

                color = 3447003

            # Send the notification
            send_discord_notification(
                title,
                message,
                color=color,
                custom_fields=custom_fields
            )
            logger.info("Sent notification about Size Overlay updates")
        except Exception as e:
            logger.error(f"Failed to send notification: {str(e)}")

    if success:
        if created_files:
            logger.info(f"Size Overlay service completed successfully. Created {len(created_files)} overlay files.")
        else:
            logger.info("Size Overlay service completed successfully. No changes were needed.")
        return True
    else:
        logger.error("Size Overlay service completed with errors.")
        return False

if __name__ == "__main__":
    # When run directly, execute the service
    success = run_size_overlay_service()
    if success:
        console.print("[bold green]Size Overlay service completed successfully![/bold green]")
    else:
        console.print("[bold red]Size Overlay service completed with errors. Check the logs for details.[/bold red]")
