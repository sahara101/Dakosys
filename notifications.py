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
        all_embeds = []
        current_embed = {
            "title": title[:256],
            "description": message[:4096],
            "color": color,
            "fields": []
        }
        current_char_count = len(current_embed['title']) + len(current_embed['description'])

        if custom_fields:
            for field in custom_fields:
                field_name = field['name'][:256]
                field_value = field['value'][:1024]
                field_size = len(field_name) + len(field_value)

                if len(current_embed['fields']) >= 25 or current_char_count + field_size > 6000:
                    all_embeds.append(current_embed)
                    if len(all_embeds) >= 10:
                        logger.warning("Reached maximum number of embeds (10). Some fields won't be shown.")
                        break
                    
                    current_embed = {
                        "title": f"{title[:200]} (continued)",
                        "color": color,
                        "fields": []
                    }
                    current_char_count = len(current_embed['title'])

                current_embed['fields'].append({"name": field_name, "value": field_value})
                current_char_count += field_size
        else:
            embed_fields = []

            if failed_episodes and len(failed_episodes) > 0:
                failed_count = total_failed if total_failed is not None else len(failed_episodes)
                episodes_text = ""
                for i, episode in enumerate(failed_episodes[:10], 1):
                    episodes_text += f"{i}. {episode}\n"
                if failed_count > len(failed_episodes[:10]):
                    episodes_text += f"\n... and {failed_count - min(len(failed_episodes), 10)} more episodes"
                embed_fields.append({"name": "Failed Episodes", "value": episodes_text})

            if added_episodes and len(added_episodes) > 0:
                added_count = total_added if total_added is not None else len(added_episodes)
                episodes_text = ""
                for i, episode in enumerate(added_episodes[:10], 1):
                    episodes_text += f"{i}. {episode}\n"
                if added_count > len(added_episodes[:10]):
                    episodes_text += f"\n... and {added_count - min(len(added_episodes), 10)} more episodes"
                embed_fields.append({"name": "Added Episodes", "value": episodes_text})

            if deleted_items and len(deleted_items) > 0:
                items_text = ""
                for i, item in enumerate(deleted_items[:10], 1):
                    items_text += f"{i}. {item}\n"
                if len(deleted_items) > 10:
                    items_text += f"\n... and {len(deleted_items) - 10} more items"
                embed_fields.append({"name": "Deleted Lists", "value": items_text})

            if details and len(details) > 0:
                details_text = ""
                for i, detail in enumerate(details[:5], 1):
                    details_text += f"{i}. {detail}\n"
                if len(details) > 5:
                    details_text += f"\n... and {len(details) - 5} more details"
                embed_fields.append({"name": "Error Details", "value": details_text})

            if embed_fields:
                current_embed["fields"] = embed_fields

        if current_embed['fields']:
            all_embeds.append(current_embed)

        if not all_embeds:
            logger.warning("No embeds to send.")
            return True

        timestamp = datetime.utcnow().isoformat()
        if all_embeds:
            all_embeds[0]['timestamp'] = timestamp
            if failed_episodes and len(failed_episodes) > 0:
                all_embeds[-1]["footer"] = {
                    "text": "Run 'docker compose run --rm dakosys fix-mappings' to resolve these issues"
                }

        for i in range(0, len(all_embeds), 10):
            chunk = all_embeds[i:i+10]
            payload = {
                "username": "DAKOSYS Monitor",
                "embeds": chunk
            }

            response = requests.post(
                webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"}
            )

            if response.status_code not in [200, 204]:
                logger.error(f"Failed to send Discord notification chunk: {response.status_code} {response.text}")
                return False
        
        return True
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
    if not isinstance(added_episodes, list):
        logger.warning(f"added_episodes is not a list: {type(added_episodes)} - value: {added_episodes}")
        added_episodes = []
    
    display_name = plex_name if plex_name else anime_name.replace('-', ' ').title()
    count = total_added if total_added is not None else len(added_episodes)
    
    title = f"New Episodes Added: {display_name}"
    message = f"Successfully added {count} new {episode_type.lower()} episodes for {display_name}."
    
    return send_discord_notification(
        title, 
        message, 
        added_episodes=added_episodes,
        total_added=count,
        color=5763719
    )

def notify_mapping_errors(anime_name, episode_type, failed_episodes, details=None):
    """
    Send notification about mapping errors
    """
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

    total_changes = sum(len(shows) for status, shows in changes.items())
    if total_changes == 0:
        logger.info("No status changes to notify about")
        return False

    title = "TV/Anime Status Updates"[:256]  
    message = f"Processed {total_shows} shows. Found changes for {total_changes} shows."[:4096]

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

    def sort_by_date(show):
        date_str = show.get('new_date', '')
        if not date_str:
            return datetime.max

        try:
            if '/' in date_str:
                day, month = map(int, date_str.split('/'))
                current_year = datetime.now().year
                current_month = datetime.now().month
                if month < current_month or (month == current_month and day < datetime.now().day):
                    current_year += 1
                return datetime(current_year, month, day)
            else:
                return datetime.max
        except (ValueError, IndexError) as e:
            logger.debug(f"Error parsing date '{date_str}': {str(e)}")
            return datetime.max

    all_embeds = []

    current_embed = {
        "title": title,
        "description": message,
        "color": 3447003,
        "fields": []
    }

    current_char_count = len(title) + len(message)
    for status in order:
        if status in changes and changes[status]:
            shows = changes[status]
            sorted_shows = sorted(shows, key=sort_by_date)

            shows_text = ""
            for show in sorted_shows:
                if status == 'DATE_CHANGED':
                    line = f"• {show['title']} - New date: {show['new_date']}\n"
                elif status in ['ENDED', 'CANCELLED']:
                    line = f"• {show['title']}\n"
                else:
                    date_info = f" ({show['new_date']})" if show['new_date'] else ""
                    line = f"• {show['title']}{date_info}\n"

                shows_text += line

            field_name = f"{status_names.get(status, status)} ({len(shows)})"[:256]

            if len(shows_text) <= 1024:
                field_value = shows_text.strip() or "No details available"
                field_size = len(field_name) + len(field_value)

                if current_char_count + field_size > 6000 or len(current_embed["fields"]) >= 25:
                    all_embeds.append(current_embed)
                    if len(all_embeds) >= 10:
                        logger.warning("Reached maximum number of embeds (10). Some status updates won't be shown.")
                        break

                    current_embed = {
                        "title": f"{title} (continued)",
                        "color": 3447003,
                        "fields": []
                    }
                    current_char_count = len(current_embed["title"])

                current_embed["fields"].append({
                    "name": field_name,
                    "value": field_value
                })
                current_char_count += field_size
            else:
                chunks = []
                current_chunk = ""

                lines = shows_text.strip().split('\n')
                for line in lines:
                    if len(current_chunk) + len(line) + 1 <= 1024:
                        current_chunk += line + '\n'
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = line + '\n'

                if current_chunk:
                    chunks.append(current_chunk.strip())

                for i, chunk in enumerate(chunks):
                    if i == 0:
                        chunk_name = field_name
                    else:
                        chunk_name = f"{status_names.get(status, status)} (continued {i})"[:256]

                    chunk_value = chunk or "No details available"
                    field_size = len(chunk_name) + len(chunk_value)

                    if current_char_count + field_size > 6000 or len(current_embed["fields"]) >= 25:
                        all_embeds.append(current_embed)
                        if len(all_embeds) >= 10:
                            logger.warning("Reached maximum number of embeds (10). Some status updates won't be shown.")
                            break

                        current_embed = {
                            "title": f"{title} (continued)",
                            "color": 3447003,
                            "fields": []
                        }
                        current_char_count = len(current_embed["title"])

                    current_embed["fields"].append({
                        "name": chunk_name,
                        "value": chunk_value
                    })
                    current_char_count += field_size

    if current_embed["fields"] and current_embed not in all_embeds and len(all_embeds) < 10:
        all_embeds.append(current_embed)

    if not all_embeds:
        logger.warning("No embeds created. This shouldn't happen if there were changes.")
        return False

    try:
        timestamp = datetime.utcnow().isoformat()

        if all_embeds:
            all_embeds[0]["timestamp"] = timestamp

        payload = {
            "username": "DAKOSYS Monitor",
            "embeds": all_embeds
        }

        config = load_config()
        if not config or 'notifications' not in config or 'discord' not in config['notifications']:
            logger.error("Discord webhook not configured")
            return False

        webhook_url = config['notifications']['discord'].get('webhook_url')
        if not webhook_url:
            logger.error("Discord webhook URL not found in configuration")
            return False

        webhook_url = webhook_url.strip('"\'')

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

            logger.debug(f"Total embeds: {len(all_embeds)}")
            for i, embed in enumerate(all_embeds):
                logger.debug(f"Embed {i+1}: {len(embed.get('fields', []))} fields")

            return False

    except Exception as e:
        logger.error(f"Error sending Discord notification: {str(e)}")
        return False
