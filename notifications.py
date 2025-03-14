#!/usr/bin/env python3
"""
Notifications module for DAKOSYS
Handles sending notifications about errors and events
"""

import os
import requests
import json
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("data/notifications.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("notifications")

def load_config():
    """Load configuration from YAML file."""
    import yaml
    
    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        config_path = "/app/config/config.yaml"
    else:
        config_path = "config/config.yaml"

    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
        return config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        return None

# Update the send_discord_notification function in notifications.py to support custom fields

def send_discord_notification(title, message, failed_episodes=None, details=None, 
                             added_episodes=None, total_added=None, total_failed=None, 
                             deleted_items=None, color=16711680, custom_fields=None):
    """
    Send a notification to Discord using webhooks
    
    Args:
        title: Title of the notification
        message: Main message content
        failed_episodes: List of episode names that failed to map
        details: Additional details about the errors
        added_episodes: List of episode names that were successfully added
        deleted_items: List of items that were deleted
        total_added: Total count of added episodes (may be more than in the list)
        total_failed: Total count of failed episodes (may be more than in the list)
        color: Embed color (default: red)
        custom_fields: Pre-formatted list of fields for the embed (overrides automatic field generation)
    """
    config = load_config()
    if not config or 'notifications' not in config or 'discord' not in config['notifications']:
        logger.error("Discord webhook not configured")
        return False

    webhook_url = config['notifications']['discord'].get('webhook_url')
    if not webhook_url:
        logger.error("Discord webhook URL not found in configuration")
        return False

    try:
        # Create timestamp
        timestamp = datetime.utcnow().isoformat()

        # Build the embed
        embed = {
            "title": title,
            "description": message,
            "color": color,
            "timestamp": timestamp
        }

        # Use provided custom fields if available
        if custom_fields:
            embed["fields"] = custom_fields
        else:
            # Initialize fields list
            embed_fields = []

            # Handle failed episodes if provided
            if failed_episodes and len(failed_episodes) > 0:
                # Use total_failed if provided, otherwise count the list
                failed_count = total_failed if total_failed is not None else len(failed_episodes)

                # Create a formatted list, but limit to 10 episodes with a note if there are more
                episodes_text = ""
                for i, episode in enumerate(failed_episodes[:10], 1):
                    episodes_text += f"{i}. {episode}\n"

                # Add note about additional episodes if total_failed is greater
                if failed_count > len(failed_episodes[:10]):
                    episodes_text += f"\n... and {failed_count - min(len(failed_episodes), 10)} more episodes"

                embed_fields.append({
                    "name": "Failed Episodes",
                    "value": episodes_text
                })

            # Handle added episodes if provided
            if added_episodes and len(added_episodes) > 0:
                # Use total_added if provided, otherwise count the list
                added_count = total_added if total_added is not None else len(added_episodes)

                # Create a formatted list, but limit to 10 episodes with a note if there are more
                episodes_text = ""
                for i, episode in enumerate(added_episodes[:10], 1):
                    episodes_text += f"{i}. {episode}\n"

                # Add note about additional episodes if total_added is greater
                if added_count > len(added_episodes[:10]):
                    episodes_text += f"\n... and {added_count - min(len(added_episodes), 10)} more episodes"

                embed_fields.append({
                    "name": "Added Episodes",
                    "value": episodes_text
                })

            # Handle deleted items if provided
            if deleted_items and len(deleted_items) > 0:
                # Format similarly to added_episodes
                items_text = ""
                for i, item in enumerate(deleted_items[:10], 1):
                    items_text += f"{i}. {item}\n"

                # Add note if there are more than shown
                if len(deleted_items) > 10:
                    items_text += f"\n... and {len(deleted_items) - 10} more items"

                embed_fields.append({
                    "name": "Deleted Lists",
                    "value": items_text
                })

            # Add details if provided
            if details and len(details) > 0:
                details_text = ""
                for i, detail in enumerate(details[:5], 1):
                    details_text += f"{i}. {detail}\n"

                if len(details) > 5:
                    details_text += f"\n... and {len(details) - 5} more details"

                embed_fields.append({
                    "name": "Error Details",
                    "value": details_text
                })

            # Add fields to embed if we have any
            if embed_fields:
                embed["fields"] = embed_fields

        # Add fix command hint for failures
        if failed_episodes and len(failed_episodes) > 0:
            embed["footer"] = {
                "text": "Run 'docker compose run --rm dakosys fix-mappings' to resolve these issues"
            }

        # Create the payload
        payload = {
            "username": "DAKOSYS Monitor",
            "embeds": [embed]
        }

        # Send the webhook
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 204:
            return True
        else:
            logger.error(f"Failed to send Discord notification: {response.status_code} {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error sending Discord notification: {str(e)}")
        return False

def notify_successful_updates(anime_name, episode_type, added_episodes, plex_name=None, total_added=None):
    """
    Send notification about successfully added episodes
    
    Args:
        anime_name: Name of the anime (AnimeFillerList name)
        episode_type: Type of episodes (FILLER, MANGA, etc.)
        added_episodes: List of episode names that were added
        plex_name: User-friendly Plex name (if available)
        total_added: Total number of episodes added (may be more than the list if truncated)
    """
    # Validate that added_episodes is actually a list
    if not isinstance(added_episodes, list):
        logger.warning(f"added_episodes is not a list: {type(added_episodes)} - value: {added_episodes}")
        # Create empty list if not valid
        added_episodes = []
    
    # Use the friendly Plex name if provided
    display_name = plex_name if plex_name else anime_name.replace('-', ' ').title()
    
    # Use the total_added parameter if provided, otherwise count the list
    count = total_added if total_added is not None else len(added_episodes)
    
    title = f"New Episodes Added: {display_name}"
    message = f"Successfully added {count} new {episode_type.lower()} episodes for {display_name}."
    
    # Use a green color for success
    return send_discord_notification(
        title, 
        message, 
        added_episodes=added_episodes,
        total_added=count,
        color=5763719  # Green color
    )

def notify_mapping_errors(anime_name, episode_type, failed_episodes, details=None):
    """
    Send notification about mapping errors
    """
    # Convert to Plex name if possible
    import yaml
    config = load_config()
    plex_name = config.get('mappings', {}).get(anime_name, anime_name)
    if '-' in plex_name:
        plex_name = plex_name.replace('-', ' ').title()

    title = f"Mapping Errors: {plex_name}"
    message = f"Failed to map {len(failed_episodes)} {episode_type} episodes for {plex_name}."

    return send_discord_notification(title, message, failed_episodes, details)

def notify_tv_status_updates(changes, total_shows):
    """
    Send notification about TV/Anime status tracker changes with proper DD/MM date sorting
    and respect ALL Discord webhook limits.

    Args:
        changes: Dictionary of shows grouped by status type including both status and date changes
        total_shows: Total number of shows processed
    """
    from datetime import datetime

    # Count all changes
    total_changes = sum(len(shows) for status, shows in changes.items())

    # Skip if there are no changes
    if total_changes == 0:
        logger.info("No status changes to notify about")
        return False

    # Create title and message (with limits)
    title = "TV/Anime Status Updates"[:256]  # Discord title limit: 256 chars
    message = f"Processed {total_shows} shows. Found changes for {total_changes} shows."[:4096]  # Desc limit: 4096 chars

    # Display friendly names for each status
    status_names = {
        'AIRING': 'Now Airing',
        'SEASON_PREMIERE': 'Season Premieres',
        'SEASON_FINALE': 'Season Finales',
        'MID_SEASON_FINALE': 'Mid-Season Finales',
        'FINAL_EPISODE': 'Series Finales',
        'RETURNING': 'Returning Shows',
        'DATE_CHANGED': 'Date Changes',
        'ENDED': 'Ended Shows',
        'CANCELLED': 'Cancelled Shows'
    }

    # Define a friendly order for display (most interesting first)
    order = [
        'AIRING',
        'SEASON_PREMIERE',
        'SEASON_FINALE',
        'MID_SEASON_FINALE',
        'FINAL_EPISODE',
        'RETURNING',
        'DATE_CHANGED',
        'ENDED',
        'CANCELLED'
    ]

    # Helper function to parse date and sort shows - fixed for DD/MM format
    def sort_by_date(show):
        date_str = show.get('new_date', '')
        if not date_str:
            return datetime.max  # Shows without dates go last

        try:
            # Parse as DD/MM format
            if '/' in date_str:
                day, month = map(int, date_str.split('/'))
                # Assume current year, but this could be enhanced to handle year transitions
                current_year = datetime.now().year
                # If the date seems to be in the past, assume it's for next year
                current_month = datetime.now().month
                if month < current_month or (month == current_month and day < datetime.now().day):
                    current_year += 1
                return datetime(current_year, month, day)
            else:
                # If no date format is recognized, put at the end
                return datetime.max
        except (ValueError, IndexError) as e:
            # Log the error for debugging
            logger.debug(f"Error parsing date '{date_str}': {str(e)}")
            # If parsing fails, put at the end
            return datetime.max

    # Create a list to hold our embeds (Discord allows up to 10)
    all_embeds = []

    # Create the first embed with the main message
    current_embed = {
        "title": title,
        "description": message,
        "color": 3447003,  # Blue
        "fields": []
    }

    # Track total character count for the current embed
    # Title + description counts toward the total
    current_char_count = len(title) + len(message)

    # Process each status type in the defined order
    for status in order:
        if status in changes and changes[status]:
            shows = changes[status]

            # Sort shows by date if they have dates
            sorted_shows = sorted(shows, key=sort_by_date)

            # Create a formatted list of shows with their status details
            shows_text = ""
            for show in sorted_shows:
                # Format based on what changed
                if status == 'DATE_CHANGED':
                    line = f"• {show['title']} - New date: {show['new_date']}\n"
                elif status in ['ENDED', 'CANCELLED']:
                    line = f"• {show['title']} - {show['new_status']}\n"
                else:
                    # For airing shows, include the date if available
                    date_info = f" ({show['new_date']})" if show['new_date'] else ""
                    line = f"• {show['title']}{date_info}\n"

                shows_text += line

            # Chunk text if it exceeds Discord's 1024 character limit per field
            field_name = f"{status_names.get(status, status)} ({len(shows)})"[:256]  # Limit name to 256 chars

            if len(shows_text) <= 1024:
                # Short enough to fit in one field
                field_value = shows_text.strip() or "No details available"
                field_size = len(field_name) + len(field_value)

                # Check if adding this field would exceed the total character limit
                if current_char_count + field_size > 6000 or len(current_embed["fields"]) >= 25:
                    # This embed is full, create a new one
                    all_embeds.append(current_embed)
                    if len(all_embeds) >= 10:  # Discord limit of 10 embeds per message
                        logger.warning("Reached maximum number of embeds (10). Some status updates won't be shown.")
                        break

                    # Start a new embed
                    current_embed = {
                        "title": f"{title} (continued)",
                        "color": 3447003,  # Blue
                        "fields": []
                    }
                    current_char_count = len(current_embed["title"])

                # Add the field to the current embed
                current_embed["fields"].append({
                    "name": field_name,
                    "value": field_value
                })
                current_char_count += field_size
            else:
                # Need to split into multiple fields due to Discord's 1024 char limit
                chunks = []
                current_chunk = ""

                # Split by lines to preserve whole show entries
                lines = shows_text.strip().split('\n')
                for line in lines:
                    if len(current_chunk) + len(line) + 1 <= 1024:  # +1 for newline
                        current_chunk += line + '\n'
                    else:
                        # Current chunk is full
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = line + '\n'

                # Add the last chunk if it has content
                if current_chunk:
                    chunks.append(current_chunk.strip())

                # Add each chunk as a separate field
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        chunk_name = field_name
                    else:
                        chunk_name = f"{status_names.get(status, status)} (continued {i})"[:256]

                    chunk_value = chunk or "No details available"
                    field_size = len(chunk_name) + len(chunk_value)

                    # Check if adding this field would exceed limits
                    if current_char_count + field_size > 6000 or len(current_embed["fields"]) >= 25:
                        # This embed is full, create a new one
                        all_embeds.append(current_embed)
                        if len(all_embeds) >= 10:  # Discord limit
                            logger.warning("Reached maximum number of embeds (10). Some status updates won't be shown.")
                            break

                        # Start a new embed
                        current_embed = {
                            "title": f"{title} (continued)",
                            "color": 3447003,  # Blue
                            "fields": []
                        }
                        current_char_count = len(current_embed["title"])

                    # Add the chunk as a field
                    current_embed["fields"].append({
                        "name": chunk_name,
                        "value": chunk_value
                    })
                    current_char_count += field_size

    # Add the final embed if it has fields and hasn't been added yet
    if current_embed["fields"] and current_embed not in all_embeds and len(all_embeds) < 10:
        all_embeds.append(current_embed)

    # Check if we have any embeds to send
    if not all_embeds:
        logger.warning("No embeds created. This shouldn't happen if there were changes.")
        return False

    # Send the notification with all embeds
    try:
        timestamp = datetime.utcnow().isoformat()

        # Add timestamp to the first embed
        if all_embeds:
            all_embeds[0]["timestamp"] = timestamp

        # Create the payload
        payload = {
            "username": "DAKOSYS Monitor",
            "embeds": all_embeds
        }

        # Get Discord webhook URL from config
        config = load_config()
        if not config or 'notifications' not in config or 'discord' not in config['notifications']:
            logger.error("Discord webhook not configured")
            return False

        webhook_url = config['notifications']['discord'].get('webhook_url')
        if not webhook_url:
            logger.error("Discord webhook URL not found in configuration")
            return False

        # Remove any quotes that might have been added in the config
        webhook_url = webhook_url.strip('"\'')

        # Send the webhook
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 204:
            logger.info(f"Successfully sent TV status notification with {len(all_embeds)} embeds")
            return True
        else:
            logger.error(f"Failed to send Discord notification: {response.status_code} {response.text}")

            # Debug output of what we tried to send
            logger.debug(f"Total embeds: {len(all_embeds)}")
            for i, embed in enumerate(all_embeds):
                logger.debug(f"Embed {i+1}: {len(embed.get('fields', []))} fields")

            return False

    except Exception as e:
        logger.error(f"Error sending Discord notification: {str(e)}")
        return False
