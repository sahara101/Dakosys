#!/usr/bin/env python3
"""
DAKOSYS Setup Script
Handles configuration for all services
"""

import os
import sys
import yaml
import click
import time as time_module
import datetime
import requests
import json
import argparse
from rich.console import Console

console = Console()

DATA_DIR = "data"

def test_discord_notification(webhook_url):
    """Test Discord notification system."""
    try:
        console.print("[bold blue]Testing Discord notification system...[/bold blue]")

        payload = {
            "content": None,
            "embeds": [
                {
                    "title": "DAKOSYS Notification Test",
                    "description": "Your Discord notifications are configured correctly! 🎉",
                    "color": 5814783,  
                    "footer": {
                        "text": "DAKOSYS - Setup"
                    },
                    "timestamp": datetime.datetime.now().isoformat()
                }
            ]
        }

        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 204:
            console.print("[bold green]✅ Test notification sent successfully![/bold green]")
            console.print("[yellow]Please check your Discord channel to confirm you received it.[/yellow]")
            return True
        else:
            console.print(f"[bold red]❌ Failed to send test notification. Status code: {response.status_code}[/bold red]")
            console.print(f"[yellow]Error message: {response.text}[/yellow]")
            return False
    except Exception as e:
        console.print(f"[bold red]❌ Error testing notification: {str(e)}[/bold red]")
        return False

def setup_service_scheduler(config, service_name):
    """Configure scheduler for a specific service."""
    console.print(f"\n[bold cyan]{service_name.replace('_', ' ').title()} Schedule[/bold cyan]")
    
    if 'scheduler' not in config:
        config['scheduler'] = {}
    
    if service_name not in config['scheduler']:
        config['scheduler'][service_name] = {}
    
    schedule_type = click.prompt(
        "Schedule type",
        type=click.Choice(['daily', 'hourly', 'weekly', 'monthly']),
        default=config['scheduler'].get(service_name, {}).get('type', 'daily')
    )
    config['scheduler'][service_name]['type'] = schedule_type
    
    if schedule_type == 'daily':
        default_time = config['scheduler'].get(service_name, {}).get('times', ["03:00"])[0] if 'times' in config['scheduler'].get(service_name, {}) else "03:00"
        update_time = click.prompt("Daily update time (HH:MM in 24-hour format)", default=default_time)
        config['scheduler'][service_name]['times'] = [update_time]
    elif schedule_type == 'hourly':
        default_minute = config['scheduler'].get(service_name, {}).get('minute', 0)
        minute = click.prompt("Minute of each hour to run update (0-59)", default=default_minute)
        config['scheduler'][service_name]['minute'] = int(minute)
    elif schedule_type == 'weekly':
        default_day = config['scheduler'].get(service_name, {}).get('days', ["monday"])[0] if 'days' in config['scheduler'].get(service_name, {}) else "monday"
        day = click.prompt(
            "Day of week",
            type=click.Choice(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']),
            default=default_day
        )
        default_time = config['scheduler'].get(service_name, {}).get('time', "03:00")
        time = click.prompt("Time (HH:MM in 24-hour format)", default=default_time)
        config['scheduler'][service_name]['days'] = [day]
        config['scheduler'][service_name]['time'] = time
    elif schedule_type == 'monthly':
        default_date = config['scheduler'].get(service_name, {}).get('dates', [1])[0] if 'dates' in config['scheduler'].get(service_name, {}) else 1
        date = click.prompt("Day of month (1-31)", default=default_date)
        default_time = config['scheduler'].get(service_name, {}).get('time', "03:00")
        time = click.prompt("Time (HH:MM in 24-hour format)", default=default_time)
        config['scheduler'][service_name]['dates'] = [int(date)]
        config['scheduler'][service_name]['time'] = time

def setup_anime_episode_type(config):
    """Setup for Anime Episode Type service."""
    console.print("\n[bold cyan]Anime Episode Type Tracker[/bold cyan]")
    console.print("[yellow]This service tracks anime episodes by type (filler, manga canon, etc.) and creates Trakt lists for each type.[/yellow]")
    
    enable_service = click.confirm("Enable Anime Episode Type service?", 
                                  default=config.get('services', {}).get('anime_episode_type', {}).get('enabled', False))
    
    if 'anime_episode_type' not in config.get('services', {}):
        config['services']['anime_episode_type'] = {}

    config['services']['anime_episode_type']['enabled'] = enable_service

    if 'overlay' not in config['services']['anime_episode_type']:
        config['services']['anime_episode_type']['overlay'] = {
            'horizontal_offset': 0,
            'horizontal_align': "center",
            'vertical_offset': 0,
            'vertical_align': "top",
            'font_size': 75,
            'back_width': 1920,
            'back_height': 125,
            'back_color': '#262626'
        }
    
    if not enable_service:
        console.print("[yellow]Service disabled. No further configuration needed.[/yellow]")
        return

    console.print("\n[bold]Library Configuration[/bold]")

    anime_libraries = []
    existing_libraries = config.get('plex', {}).get('libraries', {}).get('anime', [])
    
    if existing_libraries:
        console.print(f"[green]Found existing anime libraries: {', '.join(existing_libraries)}[/green]")
        use_existing = click.confirm("Use these existing anime libraries?", default=True)
        if use_existing:
            anime_libraries = existing_libraries
    
    if not anime_libraries:
        console.print("[yellow]Please configure at least one anime library.[/yellow]")
        anime_library = click.prompt("Enter anime library name", default="Anime")
        anime_libraries = [anime_library]
        
        while click.confirm("Do you want to add another anime library?", default=False):
            additional_library = click.prompt("Enter additional anime library name")
            anime_libraries.append(additional_library)

        if 'plex' not in config:
            config['plex'] = {}
        if 'libraries' not in config['plex']:
            config['plex']['libraries'] = {}

        config['plex']['libraries']['anime'] = anime_libraries

    config['services']['anime_episode_type']['libraries'] = anime_libraries

    setup_service_scheduler(config, 'anime_episode_type')

def setup_tv_status_tracker(config):
    """Setup for TV/Anime Status Tracker service."""
    console.print("\n[bold cyan]TV/Anime Status Tracker[/bold cyan]")
    console.print("[yellow]This service creates Kometa overlays and Trakt lists for next airing episodes, season finales, etc.[/yellow]")
    console.print("[yellow]It can work with both anime and regular TV shows.[/yellow]")
    
    enable_service = click.confirm("Enable TV/Anime Status Tracker service?",
                                  default=config.get('services', {}).get('tv_status_tracker', {}).get('enabled', False))

    if 'tv_status_tracker' not in config.get('services', {}):
        config['services']['tv_status_tracker'] = {}
        config['services']['tv_status_tracker']['colors'] = {
            'AIRING': '#006580',
            'ENDED': '#000000',
            'CANCELLED': '#FF0000',
            'RETURNING': '#008000',
            'SEASON_FINALE': '#9932CC',
            'MID_SEASON_FINALE': '#FFA500',
            'FINAL_EPISODE': '#8B0000',
            'SEASON_PREMIERE': '#228B22'
        }
    
    # Ensure 'overlay' dictionary and its keys exist with defaults from main config init if this function is called by setup_service
    # The main config object in run_setup() is the primary source for these defaults.
    overlay_config = config['services']['tv_status_tracker'].setdefault('overlay', {})
    overlay_config.setdefault('font_path', "config/fonts/Juventus-Fans-Bold.ttf")
    overlay_config.setdefault('overlay_style', "background_color")
    overlay_config.setdefault('gradient_name', "gradient_top.png")
    overlay_config.setdefault('back_height', 90)
    overlay_config.setdefault('back_width', 1000)
    overlay_config.setdefault('color', '#FFFFFF')
    overlay_config.setdefault('font_size', 70)
    overlay_config.setdefault('horizontal_align', "center")
    overlay_config.setdefault('horizontal_offset', 0)
    overlay_config.setdefault('vertical_align', "top")
    overlay_config.setdefault('vertical_offset', 0)
    overlay_config.setdefault('apply_gradient_background', False)

    config['services']['tv_status_tracker']['enabled'] = enable_service
    
    if not enable_service:
        console.print("[yellow]Service disabled. No further configuration needed.[/yellow]")
        return

    apply_gradient = click.confirm(
        "Apply gradient background for TV/Anime Status Tracker overlays?",
        default=overlay_config.get('apply_gradient_background', False)
    )
    overlay_config['apply_gradient_background'] = apply_gradient
    
    console.print("\n[bold]Library Configuration[/bold]")

    selected_libraries = []

    anime_libraries = config.get('plex', {}).get('libraries', {}).get('anime', [])
    if anime_libraries:
        console.print(f"[green]Found anime libraries: {', '.join(anime_libraries)}[/green]")
        if click.confirm("Include anime libraries for TV/Anime Status Tracker?", default=True):
            selected_libraries.extend(anime_libraries)
    else:
        console.print("[yellow]No anime libraries found in configuration.[/yellow]")
        if click.confirm("Do you want to add anime libraries?", default=False):
            anime_library = click.prompt("Enter anime library name", default="Anime")
            anime_libraries = [anime_library]
            
            while click.confirm("Do you want to add another anime library?", default=False):
                additional_library = click.prompt("Enter additional anime library name")
                anime_libraries.append(additional_library)

            if 'plex' not in config:
                config['plex'] = {}
            if 'libraries' not in config['plex']:
                config['plex']['libraries'] = {}

            config['plex']['libraries']['anime'] = anime_libraries
            selected_libraries.extend(anime_libraries)

    tv_libraries = config.get('plex', {}).get('libraries', {}).get('tv', [])
    if tv_libraries:
        console.print(f"[green]Found TV libraries: {', '.join(tv_libraries)}[/green]")
        if click.confirm("Include TV show libraries for TV/Anime Status Tracker?", default=True):
            selected_libraries.extend(tv_libraries)
    else:
        console.print("[yellow]No TV libraries found in configuration.[/yellow]")
        if click.confirm("Do you want to add TV show libraries?", default=True):
            tv_library = click.prompt("Enter TV show library name", default="TV Shows")
            tv_libraries = [tv_library]
            
            while click.confirm("Do you want to add another TV show library?", default=False):
                additional_library = click.prompt("Enter additional TV show library name")
                tv_libraries.append(additional_library)

            if 'plex' not in config:
                config['plex'] = {}
            if 'libraries' not in config['plex']:
                config['plex']['libraries'] = {}

            config['plex']['libraries']['tv'] = tv_libraries
            selected_libraries.extend(tv_libraries)

    if not selected_libraries:
        console.print("[bold yellow]Warning: No libraries selected for TV/Anime Status Tracker.[/bold yellow]")
        console.print("[yellow]The service may not function properly without libraries.[/yellow]")

    config['services']['tv_status_tracker']['libraries'] = selected_libraries

    setup_service_scheduler(config, 'tv_status_tracker')

def setup_size_overlay(config):
    """Setup for Size Overlay service."""
    console.print("\n[bold cyan]Size Overlay Service[/bold cyan]")
    console.print("[yellow]This service creates Kometa overlays displaying file sizes for movies and TV shows.[/yellow]")
    
    enable_service = click.confirm("Enable Size Overlay service?",
                                  default=config.get('services', {}).get('size_overlay', {}).get('enabled', False))
    
    if 'size_overlay' not in config.get('services', {}):
        config['services']['size_overlay'] = {
            'movie_overlay': {
                'apply_gradient_background': False,
                'gradient_name': 'gradient_top.png',
                'font_path': 'config/fonts/Juventus-Fans-Bold.ttf',
                'horizontal_offset': 0,
                'horizontal_align': 'center',
                'vertical_offset': 0,
                'vertical_align': 'top',
                'font_size': 63,
                'font_color': "#FFFFFF",
                'back_color': "#000000",
                'back_width': 1920,
                'back_height': 125
            },
            'show_overlay': {
                'apply_gradient_background': False,
                'gradient_name': 'gradient_bottom.png',
                'font_path': 'config/fonts/Juventus-Fans-Bold.ttf',
                'horizontal_offset': 0,
                'horizontal_align': 'center',
                'vertical_offset': 0,
                'vertical_align': 'bottom',
                'font_size': 55,
                'font_color': '#FFFFFF',
                'back_color': '#00000099',
                'back_width': 1920,
                'back_height': 80,
                'show_episode_count': False
            }
        }
    
    config['services']['size_overlay']['enabled'] = enable_service
    
    if not enable_service:
        console.print("[yellow]Service disabled. No further configuration needed.[/yellow]")
        return

    console.print("\n[bold]Movie Overlay Configuration[/bold]")
    apply_gradient_movies = click.confirm(
        "Apply gradient background for Movie Size Overlays?",
        default=config['services']['size_overlay']['movie_overlay'].get('apply_gradient_background', False)
    )
    config['services']['size_overlay']['movie_overlay']['apply_gradient_background'] = apply_gradient_movies
    if apply_gradient_movies:
        gradient_name_movies = click.prompt(
            "Enter gradient image name for movies",
            default=config['services']['size_overlay']['movie_overlay'].get('gradient_name', 'gradient_top.png')
        )
        config['services']['size_overlay']['movie_overlay']['gradient_name'] = gradient_name_movies

    console.print("\n[bold]TV Show Overlay Configuration[/bold]")
    apply_gradient_shows = click.confirm(
        "Apply gradient background for TV Show Size Overlays?",
        default=config['services']['size_overlay']['show_overlay'].get('apply_gradient_background', False)
    )
    config['services']['size_overlay']['show_overlay']['apply_gradient_background'] = apply_gradient_shows
    if apply_gradient_shows:
        gradient_name_shows = click.prompt(
            "Enter gradient image name for TV shows",
            default=config['services']['size_overlay']['show_overlay'].get('gradient_name', 'gradient_bottom.png')
        )
        config['services']['size_overlay']['show_overlay']['gradient_name'] = gradient_name_shows
    
    console.print("\n[bold]Library Configuration[/bold]")

    selected_movie_libraries = []
    selected_tv_libraries = []
    selected_anime_libraries = []

    movie_libraries = config.get('plex', {}).get('libraries', {}).get('movie', [])
    if movie_libraries:
        console.print(f"[green]Found movie libraries: {', '.join(movie_libraries)}[/green]")
        if click.confirm("Include movie libraries for Size Overlay?", default=True):
            selected_movie_libraries.extend(movie_libraries)
    else:
        console.print("[yellow]No movie libraries found in configuration.[/yellow]")
        if click.confirm("Do you want to add movie libraries?", default=True):
            movie_library = click.prompt("Enter movie library name", default="Movies")
            movie_libraries = [movie_library]
            
            while click.confirm("Do you want to add another movie library?", default=False):
                additional_library = click.prompt("Enter additional movie library name")
                movie_libraries.append(additional_library)

            if 'plex' not in config:
                config['plex'] = {}
            if 'libraries' not in config['plex']:
                config['plex']['libraries'] = {}

            config['plex']['libraries']['movie'] = movie_libraries
            selected_movie_libraries.extend(movie_libraries)

    tv_libraries = config.get('plex', {}).get('libraries', {}).get('tv', [])
    if tv_libraries:
        console.print(f"[green]Found TV libraries: {', '.join(tv_libraries)}[/green]")
        if click.confirm("Include TV show libraries for Size Overlay?", default=True):
            selected_tv_libraries.extend(tv_libraries)
    else:
        console.print("[yellow]No TV libraries found in configuration.[/yellow]")
        if click.confirm("Do you want to add TV show libraries?", default=False):
            tv_library = click.prompt("Enter TV show library name", default="TV Shows")
            tv_libraries = [tv_library]
            
            while click.confirm("Do you want to add another TV show library?", default=False):
                additional_library = click.prompt("Enter additional TV show library name")
                tv_libraries.append(additional_library)

            if 'plex' not in config:
                config['plex'] = {}
            if 'libraries' not in config['plex']:
                config['plex']['libraries'] = {}

            config['plex']['libraries']['tv'] = tv_libraries
            selected_tv_libraries.extend(tv_libraries)

    anime_libraries = config.get('plex', {}).get('libraries', {}).get('anime', [])
    if anime_libraries:
        console.print(f"[green]Found anime libraries: {', '.join(anime_libraries)}[/green]")
        if click.confirm("Include anime libraries for Size Overlay?", default=True):
            selected_anime_libraries.extend(anime_libraries)
    else:
        console.print("[yellow]No anime libraries found in configuration.[/yellow]")
        if click.confirm("Do you want to add anime libraries?", default=False):
            anime_library = click.prompt("Enter anime library name", default="Anime")
            anime_libraries = [anime_library]
            
            while click.confirm("Do you want to add another anime library?", default=False):
                additional_library = click.prompt("Enter additional anime library name")
                anime_libraries.append(additional_library)

            if 'plex' not in config:
                config['plex'] = {}
            if 'libraries' not in config['plex']:
                config['plex']['libraries'] = {}

            config['plex']['libraries']['anime'] = anime_libraries
            selected_anime_libraries.extend(anime_libraries)

    if not (selected_movie_libraries or selected_tv_libraries or selected_anime_libraries):
        console.print("[bold yellow]Warning: No libraries selected for Size Overlay.[/bold yellow]")
        console.print("[yellow]The service may not function properly without libraries.[/yellow]")

    config['services']['size_overlay']['movie_libraries'] = selected_movie_libraries
    config['services']['size_overlay']['tv_libraries'] = selected_tv_libraries
    config['services']['size_overlay']['anime_libraries'] = selected_anime_libraries

    setup_service_scheduler(config, 'size_overlay')

def setup_service(service_name):
    """Run setup for a specific service only."""
    if service_name not in ['anime_episode_type', 'tv_status_tracker', 'size_overlay']:
        console.print(f"[bold red]Error: Unknown service '{service_name}'.[/bold red]")
        console.print("[yellow]Available services: anime_episode_type, tv_status_tracker, size_overlay[/yellow]")
        return
    
    console.print(f"[bold]Running targeted setup for {service_name} service.[/bold]")

    config_dir = 'config'
    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        config_dir = "/app/config"
    
    config_path = os.path.join(config_dir, 'config.yaml')
    
    if not os.path.exists(config_path):
        console.print("[bold red]Error: Configuration file not found. Please run full setup first.[/bold red]")
        return

    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)

    if 'services' not in config:
        config['services'] = {}

    if service_name == 'anime_episode_type':
        setup_anime_episode_type(config)
    elif service_name == 'tv_status_tracker':
        setup_tv_status_tracker(config)
    elif service_name == 'size_overlay':
        setup_size_overlay(config)

    save_config_with_comments(config, config_path)

    console.print(f"[bold green]Configuration for {service_name} updated successfully![/bold green]")

    console.print("\n[bold]Service Configuration Summary:[/bold]")
    
    if service_name == 'anime_episode_type':
        if config['services']['anime_episode_type']['enabled']:
            console.print("✅ Anime Episode Type Tracker [green]ENABLED[/green]")
            
            libraries = config['services']['anime_episode_type'].get('libraries', [])
            if libraries:
                console.print(f"   [dim]Libraries: {', '.join(libraries)}[/dim]")

            if 'anime_episode_type' in config['scheduler']:
                sched = config['scheduler']['anime_episode_type']
                sched_type = sched.get('type')
                if sched_type == 'daily' and 'times' in sched:
                    console.print(f"   [dim]Schedule: Daily at {', '.join(sched['times'])}[/dim]")
                elif sched_type == 'hourly' and 'minute' in sched:
                    console.print(f"   [dim]Schedule: Hourly at minute {sched['minute']}[/dim]")
                elif sched_type == 'weekly' and 'days' in sched and 'time' in sched:
                    console.print(f"   [dim]Schedule: Weekly on {', '.join(sched['days'])} at {sched['time']}[/dim]")
                elif sched_type == 'monthly' and 'dates' in sched and 'time' in sched:
                    console.print(f"   [dim]Schedule: Monthly on day(s) {', '.join(map(str, sched['dates']))} at {sched['time']}[/dim]")
        else:
            console.print("❌ Anime Episode Type Tracker [red]DISABLED[/red]")
            
    elif service_name == 'tv_status_tracker':
        if config['services']['tv_status_tracker']['enabled']:
            console.print("✅ TV/Anime Status Tracker [green]ENABLED[/green]")
            
            libraries = config['services']['tv_status_tracker'].get('libraries', [])
            if libraries:
                console.print(f"   [dim]Libraries: {', '.join(libraries)}[/dim]")

            if 'tv_status_tracker' in config['scheduler']:
                sched = config['scheduler']['tv_status_tracker']
                sched_type = sched.get('type')
                if sched_type == 'daily' and 'times' in sched:
                    console.print(f"   [dim]Schedule: Daily at {', '.join(sched['times'])}[/dim]")
                elif sched_type == 'hourly' and 'minute' in sched:
                    console.print(f"   [dim]Schedule: Hourly at minute {sched['minute']}[/dim]")
                elif sched_type == 'weekly' and 'days' in sched and 'time' in sched:
                    console.print(f"   [dim]Schedule: Weekly on {', '.join(sched['days'])} at {sched['time']}[/dim]")
                elif sched_type == 'monthly' and 'dates' in sched and 'time' in sched:
                    console.print(f"   [dim]Schedule: Monthly on day(s) {', '.join(map(str, sched['dates']))} at {sched['time']}[/dim]")
        else:
            console.print("❌ TV/Anime Status Tracker [red]DISABLED[/red]")
            
    elif service_name == 'size_overlay':
        if config['services']['size_overlay']['enabled']:
            console.print("✅ Size Overlay Service [green]ENABLED[/green]")
            
            libraries = []
            if config['services']['size_overlay'].get('movie_libraries', []):
                libraries.extend([f"Movie: {name}" for name in config['services']['size_overlay']['movie_libraries']])
            if config['services']['size_overlay'].get('tv_libraries', []):
                libraries.extend([f"TV: {name}" for name in config['services']['size_overlay']['tv_libraries']])
            if config['services']['size_overlay'].get('anime_libraries', []):
                libraries.extend([f"Anime: {name}" for name in config['services']['size_overlay']['anime_libraries']])

            if libraries:
                console.print(f"   [dim]Libraries: {', '.join(libraries)}[/dim]")

            if 'size_overlay' in config['scheduler']:
                sched = config['scheduler']['size_overlay']
                sched_type = sched.get('type')
                if sched_type == 'daily' and 'times' in sched:
                    console.print(f"   [dim]Schedule: Daily at {', '.join(sched['times'])}[/dim]")
                elif sched_type == 'hourly' and 'minute' in sched:
                    console.print(f"   [dim]Schedule: Hourly at minute {sched['minute']}[/dim]")
                elif sched_type == 'weekly' and 'days' in sched and 'time' in sched:
                    console.print(f"   [dim]Schedule: Weekly on {', '.join(sched['days'])} at {sched['time']}[/dim]")
                elif sched_type == 'monthly' and 'dates' in sched and 'time' in sched:
                    console.print(f"   [dim]Schedule: Monthly on day(s) {', '.join(map(str, sched['dates']))} at {sched['time']}[/dim]")
        else:
            console.print("❌ Size Overlay Service [red]DISABLED[/red]")
    
    console.print("\n[yellow]Remember to restart the updater to apply changes:[/yellow]")
    console.print("[green]docker compose restart dakosys-updater[/green]")

def run_setup():
    """Interactive setup to create configuration file."""
    console.print("[bold]Welcome to the DAKOSYS Setup![/bold]")

    config_dir = 'config'
    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        config_dir = "/app/config"

    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    config_path = os.path.join(config_dir, 'config.yaml')

    console.print("\n[bold]Timezone Configuration[/bold]")
    console.print("[yellow]Enter your timezone (e.g., 'America/New_York', 'Europe/London', 'Asia/Tokyo')[/yellow]")
    console.print("[yellow]This ensures the scheduler runs at the correct local time.[/yellow]")

    console.print("\n[bold]Common timezones:[/bold]")
    common_timezones = [
        "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
        "Europe/London", "Europe/Paris", "Europe/Berlin", "Asia/Tokyo", "Australia/Sydney"
    ]
    for tz in common_timezones:
        console.print(f"- {tz}")

    default_timezone = time_module.tzname[0]
    timezone = click.prompt("Enter your timezone", default=default_timezone)

    console.print("\n[bold]Display Settings[/bold]")
    existing_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as file:
                existing_config = yaml.safe_load(file) or {}
        except Exception:
            pass
            
    default_date_format = existing_config.get('date_format', 'DD/MM')
    date_format_preference = click.prompt(
        "Preferred date format for display (e.g., in TV Status Tracker)",
        type=click.Choice(['DD/MM', 'MM/DD'], case_sensitive=False),
        default=default_date_format
    )

    config = {
        'timezone': timezone,
        'date_format': date_format_preference.upper(),
        'plex': {
            'libraries': {
                'anime': [],
                'tv': [],
                'movie': []
            }
        },
        'trakt': {},
        'lists': {},
        'kometa_config': {
            'yaml_output_dir': '/kometa/config/overlays',
            'collections_dir': '/kometa/config/collections',
            'font_directory': 'config/fonts',
            'asset_directory': 'config/assets'
        },
        'scheduler': {},
        'services': {
            'anime_episode_type': {
                'enabled': False,
                'overlay': {
                    'horizontal_offset': 0,
                    'horizontal_align': "center",
                    'vertical_offset': 0,
                    'vertical_align': "top",
                    'font_size': 75,
                    'back_width': 1920,
                    'back_height': 125,
                    'back_color': '#262626'
                }
            },
            'tv_status_tracker': {
                'enabled': False,
                'colors': {
                    'AIRING': '#006580',
                    'ENDED': '#000000',
                    'CANCELLED': '#FF0000',
                    'RETURNING': '#008000',
                    'SEASON_FINALE': '#9932CC',
                    'MID_SEASON_FINALE': '#FFA500',
                    'FINAL_EPISODE': '#8B0000',
                    'SEASON_PREMIERE': '#228B22'
                },
                'overlay': {
                    'back_height': 90,
                    'back_width': 1000,
                    'color': '#FFFFFF',
                    'font_size': 70,
                    'horizontal_align': "center",
                    'horizontal_offset': 0,
                    'vertical_align': "top",
                    'vertical_offset': 0,
                    'font_name': "Juventus-Fans-Bold.ttf",
                    'overlay_style': "background_color",
                    'gradient_name': "gradient_top.png",
                    'apply_gradient_background': False
                }
            },
            'size_overlay': {
                'enabled': False,
                'movie_overlay': {
                    'apply_gradient_background': False,
                    'gradient_name': 'gradient_top.png',
                    'font_path': 'config/fonts/Juventus-Fans-Bold.ttf',
                    'horizontal_offset': 0,
                    'horizontal_align': 'center',
                    'vertical_offset': 0,
                    'vertical_align': 'top',
                    'font_size': 63,
                    'font_color': '#FFFFFF',
                    'back_color': '#000000',
                    'back_width': 1920,
                    'back_height': 125
                },
                'show_overlay': {
                    'apply_gradient_background': False,
                    'gradient_name': 'gradient_bottom.png',
                    'font_path': 'config/fonts/Juventus-Fans-Bold.ttf',
                    'horizontal_offset': 0,
                    'horizontal_align': 'center',
                    'vertical_offset': 0,
                    'vertical_align': 'bottom',
                    'font_size': 55,
                    'font_color': '#FFFFFF',
                    'back_color': '#00000099',
                    'back_width': 1920,
                    'back_height': 80,
                    'show_episode_count': False
                }
            }
        }
    }

    console.print("\n[bold]Plex Configuration[/bold]")
    console.print("[yellow]You'll need your Plex server URL and an authentication token.[/yellow]")
    console.print("[yellow]To get your token, see: https://support.plex.tv/articles/204059436-finding-an-authentication-token/[/yellow]")
    config['plex']['url'] = click.prompt("Enter your Plex server URL", default="http://localhost:32400")
    config['plex']['token'] = click.prompt("Enter your Plex authentication token")

    console.print("\n[bold]Kometa Configuration[/bold]")
    console.print("[yellow]DAKOSYS integrates with Kometa/PMM by generating overlay and collection files.[/yellow]")
    console.print("[yellow]These settings will be used by all services that create Kometa configurations.[/yellow]")
    yaml_output_dir = click.prompt("Enter path for overlay YAML files", default="/kometa/config/overlays")
    collections_dir = click.prompt("Enter path for collections YAML files", default="/kometa/config/collections")
    config['kometa_config']['yaml_output_dir'] = yaml_output_dir
    config['kometa_config']['collections_dir'] = collections_dir

    console.print("\n[bold]Kometa Asset & Font Directories[/bold]")
    console.print("[yellow]Specify directories for Kometa to find custom fonts and assets (like gradients).[/yellow]")
    console.print("[yellow]These paths are relative to Kometa's main configuration directory (e.g., '/kometa/config').[/yellow]")
    
    font_dir = click.prompt("Enter Kometa font directory", default=config['kometa_config'].get('font_directory', "config/fonts"))
    config['kometa_config']['font_directory'] = font_dir
    
    asset_dir = click.prompt("Enter Kometa asset directory", default=config['kometa_config'].get('asset_directory', "config/assets"))
    config['kometa_config']['asset_directory'] = asset_dir

    console.print("\n[bold]Service Configuration[/bold]")
    console.print("[yellow]DAKOSYS supports multiple services that can be enabled independently.[/yellow]")

    console.print("\n[bold cyan]Anime Episode Type Tracker[/bold cyan]")
    console.print("[yellow]This service tracks anime episodes by type (filler, manga canon, etc.) and creates Trakt lists for each type.[/yellow]")
    anime_episode_service = click.confirm("Enable Anime Episode Type service?", default=True)
    config['services']['anime_episode_type']['enabled'] = anime_episode_service

    console.print("\n[bold cyan]TV/Anime Status Tracker[/bold cyan]")
    console.print("[yellow]This service creates Kometa overlays and Trakt lists for next airing episodes, season finales, etc.[/yellow]")
    console.print("[yellow]It can work with both anime and regular TV shows.[/yellow]")
    tv_status_service = click.confirm("Enable TV/Anime Status Tracker service?", default=False)
    config['services']['tv_status_tracker']['enabled'] = tv_status_service

    console.print("\n[bold cyan]Size Overlay Service[/bold cyan]")
    console.print("[yellow]This service creates Kometa overlays displaying file sizes for movies and TV shows.[/yellow]")
    size_overlay_service = click.confirm("Enable Size Overlay service?", default=False)
    config['services']['size_overlay']['enabled'] = size_overlay_service

    anime_libraries = []
    tv_libraries = []
    movie_libraries = []

    console.print("\n[bold]Plex Library Discovery[/bold]")
    console.print("[yellow]Let's first identify all your Plex libraries by type.[/yellow]")

    has_anime = click.confirm("\nDo you have anime libraries in Plex?", default=False)
    if has_anime:
        console.print("\n[bold cyan]Anime Libraries[/bold cyan]")
        anime_library = click.prompt("Enter your first anime library name", default="Anime")
        anime_libraries.append(anime_library)

        while click.confirm("Do you want to add another anime library?", default=False):
            additional_library = click.prompt("Enter additional anime library name")
            anime_libraries.append(additional_library)

    has_tv = click.confirm("\nDo you have TV show libraries in Plex?", default=True)
    if has_tv:
        console.print("\n[bold cyan]TV Show Libraries[/bold cyan]")
        tv_library = click.prompt("Enter your first TV show library name", default="TV Shows")
        tv_libraries.append(tv_library)

        while click.confirm("Do you want to add another TV show library?", default=False):
            additional_library = click.prompt("Enter additional TV show library name")
            tv_libraries.append(additional_library)

    has_movies = click.confirm("\nDo you have movie libraries in Plex?", default=True)
    if has_movies:
        console.print("\n[bold cyan]Movie Libraries[/bold cyan]")
        movie_library = click.prompt("Enter your first movie library name", default="Movies")
        movie_libraries.append(movie_library)

        while click.confirm("Do you want to add another movie library?", default=False):
            additional_library = click.prompt("Enter additional movie library name")
            movie_libraries.append(additional_library)

    config['plex']['libraries']['anime'] = anime_libraries
    config['plex']['libraries']['tv'] = tv_libraries
    config['plex']['libraries']['movie'] = movie_libraries

    console.print("\n[bold]Service Library Configuration[/bold]")
    console.print("[yellow]Now let's configure which libraries to use with each service.[/yellow]")

    if anime_episode_service:
        console.print("\n[bold cyan]Anime Episode Type Library Selection[/bold cyan]")
        if anime_libraries:
            config['services']['anime_episode_type']['libraries'] = anime_libraries.copy()
            console.print(f"[green]Using anime libraries: {', '.join(anime_libraries)}[/green]")
        else:
            console.print("[yellow]No anime libraries available for Anime Episode Type service.[/yellow]")
            console.print("[yellow]This service requires anime libraries to function.[/yellow]")

    if tv_status_service:
        console.print("\n[bold cyan]TV/Anime Status Tracker Library Selection[/bold cyan]")
        
        selected_libraries = []
        
        if anime_libraries:
            if click.confirm("Include anime libraries for TV/Anime Status Tracker?", default=True):
                selected_libraries.extend(anime_libraries)
                console.print(f"[green]Including anime libraries: {', '.join(anime_libraries)}[/green]")
        
        if tv_libraries:
            if click.confirm("Include TV show libraries for TV/Anime Status Tracker?", default=True):
                selected_libraries.extend(tv_libraries)
                console.print(f"[green]Including TV libraries: {', '.join(tv_libraries)}[/green]")
        
        if not selected_libraries:
            console.print("[yellow]Warning: No libraries selected for TV/Anime Status Tracker.[/yellow]")
        
        config['services']['tv_status_tracker']['libraries'] = selected_libraries

    if size_overlay_service:
        console.print("\n[bold cyan]Size Overlay Library Selection[/bold cyan]")
        
        selected_movie_libraries = []
        selected_tv_libraries = []
        selected_anime_libraries = []
        
        if movie_libraries:
            if click.confirm("Include movie libraries for Size Overlay?", default=True):
                selected_movie_libraries.extend(movie_libraries)
                console.print(f"[green]Including movie libraries: {', '.join(movie_libraries)}[/green]")
        
        if tv_libraries:
            if click.confirm("Include TV show libraries for Size Overlay?", default=True):
                selected_tv_libraries.extend(tv_libraries)
                console.print(f"[green]Including TV libraries: {', '.join(tv_libraries)}[/green]")
        
        if anime_libraries:
            if click.confirm("Include anime libraries for Size Overlay?", default=True):
                selected_anime_libraries.extend(anime_libraries)
                console.print(f"[green]Including anime libraries: {', '.join(anime_libraries)}[/green]")
        
        if not (selected_movie_libraries or selected_tv_libraries or selected_anime_libraries):
            console.print("[yellow]Warning: No libraries selected for Size Overlay.[/yellow]")
        
        config['services']['size_overlay']['movie_libraries'] = selected_movie_libraries
        config['services']['size_overlay']['tv_libraries'] = selected_tv_libraries
        config['services']['size_overlay']['anime_libraries'] = selected_anime_libraries

    if tv_status_service:
        console.print("\n[bold]TV/Anime Status Tracker Configuration[/bold]")
        console.print("[yellow]This service will use the global Kometa configuration paths.[/yellow]")
        
        console.print("\n[bold]TV/Anime Status Tracker - Overlay Style[/bold]")
        console.print("Choose how the status overlay will be displayed:")
        console.print("  - [cyan]background_color[/cyan]: Displays status text (typically white) on a solid background.")
        console.print("                         The background color is determined by the show's status (e.g., red for CANCELLED).")
        console.print("  - [cyan]colored_text[/cyan]: Displays status text directly on a semi-transparent gradient image.")
        console.print("                         The text itself will be colored according to the show's status.")
        console.print("                         (Requires 'gradient_top.png' in 'config/assets/' relative to Kometa's config root).")

        # Ensure overlay dict exists (it should from main config init)
        overlay_settings = config['services']['tv_status_tracker'].setdefault('overlay', {})
        # Get current or default style (default is set in main config init in run_setup)
        current_overlay_style = overlay_settings.get('overlay_style', 'background_color') 
        
        chosen_overlay_style = click.prompt(
            "Choose overlay style",
            type=click.Choice(['background_color', 'colored_text'], case_sensitive=False),
            default=current_overlay_style
        )
        overlay_settings['overlay_style'] = chosen_overlay_style
        # The font_name will default to "Juventus-Fans-Bold.ttf" as per the initial config dictionary.
        # The user can manually edit config.yaml to change services.tv_status_tracker.overlay.font_name.

    console.print("\n[bold]Trakt Configuration[/bold]")
    console.print("[yellow]You'll need to create a Trakt.tv API application first at: https://trakt.tv/oauth/applications[/yellow]")
    console.print("\n[bold]When creating your Trakt application:[/bold]")
    console.print("1. Name: [green]DAKOSYS[/green] (or any name you prefer)")
    console.print("2. Redirect URI: [bold green]urn:ietf:wg:oauth:2.0:oob[/bold green] (use exactly this value)")
    console.print("3. JavaScript Origins: [green]Leave blank[/green]")
    console.print("4. Permissions: Select [green]Auto-refresh token[/green] to avoid manual reauthorization")
    console.print("5. Check: [green]Skip authorization (single user)[/green]")
    console.print("\n[yellow]After creating your application, you'll see both a Client ID and Client Secret that you'll need below.[/yellow]")

    console.print("\n[bold]Enter your Trakt application details:[/bold]")
    config['trakt']['client_id'] = click.prompt("Enter your Trakt Client ID (a long string of letters and numbers)")
    config['trakt']['client_secret'] = click.prompt("Enter your Trakt Client Secret (needed for auto-refresh)")
    config['trakt']['username'] = click.prompt("Enter your Trakt username")
    config['trakt']['redirect_uri'] = click.prompt("Enter redirect URI", default="urn:ietf:wg:oauth:2.0:oob")

    console.print("\n[bold]List Settings[/bold]")
    config['lists']['default_privacy'] = click.prompt(
        "Default privacy for created lists",
        type=click.Choice(['private', 'public']),
        default="private"
    )

    console.print("\n[bold]Service Schedules[/bold]")
    console.print("[yellow]Configure when each enabled service will run.[/yellow]")

    if anime_episode_service:
        if 'scheduler' not in config:
            config['scheduler'] = {}

        if 'anime_episode_type' not in config['scheduler']:
            config['scheduler']['anime_episode_type'] = {}

        console.print("\n[bold cyan]Anime Episode Type Schedule[/bold cyan]")
        schedule_type = click.prompt(
            "Schedule type",
            type=click.Choice(['daily', 'hourly', 'weekly', 'monthly']),
            default="daily"
        )
        config['scheduler']['anime_episode_type']['type'] = schedule_type

        if schedule_type == 'daily':
            update_time = click.prompt("Daily update time (HH:MM in 24-hour format)", default="03:00")
            config['scheduler']['anime_episode_type']['times'] = [update_time]
        elif schedule_type == 'hourly':
            minute = click.prompt("Minute of each hour to run update (0-59)", default=0)
            config['scheduler']['anime_episode_type']['minute'] = int(minute)
        elif schedule_type == 'weekly':
            day = click.prompt(
                "Day of week",
                type=click.Choice(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']),
                default="monday"
            )
            time = click.prompt("Time (HH:MM in 24-hour format)", default="03:00")
            config['scheduler']['anime_episode_type']['days'] = [day]
            config['scheduler']['anime_episode_type']['time'] = time
        elif schedule_type == 'monthly':
            date = click.prompt("Day of month (1-31)", default=1)
            time = click.prompt("Time (HH:MM in 24-hour format)", default="03:00")
            config['scheduler']['anime_episode_type']['dates'] = [int(date)]
            config['scheduler']['anime_episode_type']['time'] = time

    if tv_status_service:
        if 'scheduler' not in config:
            config['scheduler'] = {}

        if 'tv_status_tracker' not in config['scheduler']:
            config['scheduler']['tv_status_tracker'] = {}

        console.print("\n[bold cyan]TV/Anime Status Tracker Schedule[/bold cyan]")
        schedule_type = click.prompt(
            "Schedule type",
            type=click.Choice(['daily', 'hourly', 'weekly', 'monthly']),
            default="daily"
        )
        config['scheduler']['tv_status_tracker']['type'] = schedule_type

        if schedule_type == 'daily':
            update_time = click.prompt("Daily update time (HH:MM in 24-hour format)", default="04:00")
            config['scheduler']['tv_status_tracker']['times'] = [update_time]
        elif schedule_type == 'hourly':
            minute = click.prompt("Minute of each hour to run update (0-59)", default=30)
            config['scheduler']['tv_status_tracker']['minute'] = int(minute)
        elif schedule_type == 'weekly':
            day = click.prompt(
                "Day of week",
                type=click.Choice(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']),
                default="monday"
            )
            time = click.prompt("Time (HH:MM in 24-hour format)", default="04:00")
            config['scheduler']['tv_status_tracker']['days'] = [day]
            config['scheduler']['tv_status_tracker']['time'] = time
        elif schedule_type == 'monthly':
            date = click.prompt("Day of month (1-31)", default=1)
            time = click.prompt("Time (HH:MM in 24-hour format)", default="04:00")
            config['scheduler']['tv_status_tracker']['dates'] = [int(date)]
            config['scheduler']['tv_status_tracker']['time'] = time

    if size_overlay_service:
        if 'scheduler' not in config:
            config['scheduler'] = {}

        if 'size_overlay' not in config['scheduler']:
            config['scheduler']['size_overlay'] = {}

        console.print("\n[bold cyan]Size Overlay Schedule[/bold cyan]")
        schedule_type = click.prompt(
            "Schedule type",
            type=click.Choice(['daily', 'hourly', 'weekly', 'monthly']),
            default="daily"
        )
        config['scheduler']['size_overlay']['type'] = schedule_type

        if schedule_type == 'daily':
            update_time = click.prompt("Daily update time (HH:MM in 24-hour format)", default="03:30")
            config['scheduler']['size_overlay']['times'] = [update_time]
        elif schedule_type == 'hourly':
            minute = click.prompt("Minute of each hour to run update (0-59)", default=30)
            config['scheduler']['size_overlay']['minute'] = int(minute)
        elif schedule_type == 'weekly':
            day = click.prompt(
                "Day of week",
                type=click.Choice(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']),
                default="sunday"
            )
            time = click.prompt("Time (HH:MM in 24-hour format)", default="04:00")
            config['scheduler']['size_overlay']['days'] = [day]
            config['scheduler']['size_overlay']['time'] = time
        elif schedule_type == 'monthly':
            date = click.prompt("Day of month (1-31)", default=1)
            time = click.prompt("Time (HH:MM in 24-hour format)", default="04:00")
            config['scheduler']['size_overlay']['dates'] = [int(date)]
            config['scheduler']['size_overlay']['time'] = time

    console.print("\n[bold]Notifications[/bold]")
    console.print("[yellow]Would you like to enable Discord notifications for updates and errors?[/yellow]")
    enable_notifications = click.confirm("Enable notifications?", default=True)

    config['notifications'] = {'enabled': enable_notifications}

    if enable_notifications:
        console.print("\n[bold]Discord Integration[/bold]")
        console.print("[yellow]To enable Discord notifications, you'll need a webhook URL.[/yellow]")
        console.print("[yellow]To create one, go to your Discord server settings, select 'Integrations', then 'Webhooks'.[/yellow]")
        use_discord = click.confirm("Enable Discord notifications?", default=True)

        if use_discord:
            webhook_url = click.prompt("Enter your Discord webhook URL", default="")
            config['notifications']['discord'] = {'webhook_url': webhook_url}

            if webhook_url:
                if click.confirm("Would you like to test Discord notifications now?", default=True):
                    notification_works = test_discord_notification(webhook_url)

                    if not notification_works:
                        console.print("[yellow]The test notification failed. Would you like to update your webhook URL?[/yellow]")
                        if click.confirm("Update webhook URL?", default=True):
                            webhook_url = click.prompt("Enter your Discord webhook URL")
                            config['notifications']['discord']['webhook_url'] = webhook_url

                            if webhook_url:
                                test_discord_notification(webhook_url)

    save_config_with_comments(config, config_path)

    console.print(f"\n[bold green]Configuration saved to {config_path}[/bold green]")
    console.print(f"[dim]Note: In {config_path}, under 'services.tv_status_tracker.overlay',")
    console.print(f"[dim]the 'overlay_style' can be 'background_color' or 'colored_text'.[/dim]")

    data_dir = DATA_DIR
    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        data_dir = "/app/data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    yaml_output_dir = config['kometa_config']['yaml_output_dir']
    collections_dir = config['kometa_config']['collections_dir']

    # Only try to create if running in Docker
    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        try:
            if not os.path.exists(yaml_output_dir):
                os.makedirs(yaml_output_dir)
                console.print(f"[green]Created directory: {yaml_output_dir}[/green]")

            if not os.path.exists(collections_dir):
                os.makedirs(collections_dir)
                console.print(f"[green]Created directory: {collections_dir}[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not create directories: {str(e)}[/yellow]")
            console.print("[yellow]Make sure these directories are mapped in your docker-compose.yml[/yellow]")

    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        console.print("\n[bold]Setting up assets...[/bold]")
        try:
            from asset_manager import setup_assets
            setup_assets(config)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not setup assets: {str(e)}[/yellow]")
            console.print("[yellow]You may need to manually copy collection posters and fonts.[/yellow]")

    console.print("\n[bold]Now authenticating with Trakt.tv...[/bold]")
    import trakt_auth
    auth_success = trakt_auth.ensure_auth_during_setup(config)

    if auth_success:
        console.print("\n[bold green]Setup complete! Authentication successful![/bold green]")
    else:
        console.print("\n[bold yellow]Setup complete, but Trakt authentication will be needed when you run commands.[/bold yellow]")

    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        console.print("\n[bold]Setting up assets and overlay files...[/bold]")
        try:
            from asset_manager import setup_assets, create_anime_overlay_files
            setup_assets(config)
            if create_anime_overlay_files(config):
                console.print("[green]✅ Created anime episode type overlay files[/green]")
            else:
                console.print("[yellow]⚠️ Some overlay files could not be created[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not setup all assets: {str(e)}[/yellow]")
            console.print("[yellow]You may need to manually create overlay files.[/yellow]")

    console.print("\n[bold]Services Configuration Summary:[/bold]")
    if config['services']['anime_episode_type']['enabled']:
        console.print("✅ Anime Episode Type Tracker [green]ENABLED[/green]")
        
        libraries = config['services']['anime_episode_type'].get('libraries', [])
        if libraries:
            console.print(f"   [dim]Libraries: {', '.join(libraries)}[/dim]")

        if 'anime_episode_type' in config['scheduler']:
            sched = config['scheduler']['anime_episode_type']
            sched_type = sched.get('type')
            if sched_type == 'daily' and 'times' in sched:
                console.print(f"   [dim]Schedule: Daily at {', '.join(sched['times'])}[/dim]")
            elif sched_type == 'hourly' and 'minute' in sched:
                console.print(f"   [dim]Schedule: Hourly at minute {sched['minute']}[/dim]")
            elif sched_type == 'weekly' and 'days' in sched and 'time' in sched:
                console.print(f"   [dim]Schedule: Weekly on {', '.join(sched['days'])} at {sched['time']}[/dim]")
            elif sched_type == 'monthly' and 'dates' in sched and 'time' in sched:
                console.print(f"   [dim]Schedule: Monthly on day(s) {', '.join(map(str, sched['dates']))} at {sched['time']}[/dim]")
    else:
        console.print("❌ Anime Episode Type Tracker [red]DISABLED[/red]")

    if config['services']['tv_status_tracker']['enabled']:
        console.print("✅ TV/Anime Status Tracker [green]ENABLED[/green]")
        
        libraries = config['services']['tv_status_tracker'].get('libraries', [])
        if libraries:
            console.print(f"   [dim]Libraries: {', '.join(libraries)}[/dim]")

        if 'tv_status_tracker' in config['scheduler']:
            sched = config['scheduler']['tv_status_tracker']
            sched_type = sched.get('type')
            if sched_type == 'daily' and 'times' in sched:
                console.print(f"   [dim]Schedule: Daily at {', '.join(sched['times'])}[/dim]")
            elif sched_type == 'hourly' and 'minute' in sched:
                console.print(f"   [dim]Schedule: Hourly at minute {sched['minute']}[/dim]")
            elif sched_type == 'weekly' and 'days' in sched and 'time' in sched:
                console.print(f"   [dim]Schedule: Weekly on {', '.join(sched['days'])} at {sched['time']}[/dim]")
            elif sched_type == 'monthly' and 'dates' in sched and 'time' in sched:
                console.print(f"   [dim]Schedule: Monthly on day(s) {', '.join(map(str, sched['dates']))} at {sched['time']}[/dim]")
    else:
        console.print("❌ TV/Anime Status Tracker [red]DISABLED[/red]")

    if config['services']['size_overlay']['enabled']:
        console.print("✅ Size Overlay Service [green]ENABLED[/green]")
        
        libraries = []
        if config['services']['size_overlay'].get('movie_libraries', []):
            libraries.extend([f"Movie: {name}" for name in config['services']['size_overlay']['movie_libraries']])
        if config['services']['size_overlay'].get('tv_libraries', []):
            libraries.extend([f"TV: {name}" for name in config['services']['size_overlay']['tv_libraries']])
        if config['services']['size_overlay'].get('anime_libraries', []):
            libraries.extend([f"Anime: {name}" for name in config['services']['size_overlay']['anime_libraries']])

        if libraries:
            console.print(f"   [dim]Libraries: {', '.join(libraries)}[/dim]")

        if 'size_overlay' in config['scheduler']:
            sched = config['scheduler']['size_overlay']
            sched_type = sched.get('type')
            if sched_type == 'daily' and 'times' in sched:
                console.print(f"   [dim]Schedule: Daily at {', '.join(sched['times'])}[/dim]")
            elif sched_type == 'hourly' and 'minute' in sched:
                console.print(f"   [dim]Schedule: Hourly at minute {sched['minute']}[/dim]")
            elif sched_type == 'weekly' and 'days' in sched and 'time' in sched:
                console.print(f"   [dim]Schedule: Weekly on {', '.join(sched['days'])} at {sched['time']}[/dim]")
            elif sched_type == 'monthly' and 'dates' in sched and 'time' in sched:
                console.print(f"   [dim]Schedule: Monthly on day(s) {', '.join(map(str, sched['dates']))} at {sched['time']}[/dim]")
    else:
        console.print("❌ Size Overlay Service [red]DISABLED[/red]")

    console.print("\n[bold]Kometa Configuration:[/bold]")
    console.print(f"✅ Overlay YAML Path: [dim]{config['kometa_config']['yaml_output_dir']}[/dim]")
    console.print(f"✅ Collections Path: [dim]{config['kometa_config']['collections_dir']}[/dim]")

    if config['notifications']['enabled']:
        if 'discord' in config['notifications'] and config['notifications']['discord'].get('webhook_url'):
            console.print("✅ Discord Notifications [green]ENABLED[/green]")
        else:
            console.print("❌ Discord Notifications [red]NOT CONFIGURED[/red]")
    else:
        console.print("❌ Notifications [red]DISABLED[/red]")

    # Important volume mapping information
    console.print("\n[bold yellow]Important:[/bold yellow] Make sure to map these directories in your docker-compose.yml:")
    console.print(f"  Container path: {yaml_output_dir}")
    console.print(f"  Container path: {collections_dir}")
    console.print("\nExample docker-compose.yml volume mapping:")
    console.print("[green]volumes:[/green]")
    console.print("[green]  - ./local_folder:/kometa/config[/green]")
    console.print("\nWhere [yellow]./local_folder[/yellow] is your host system path that contains Kometa config.")

    console.print("[yellow]You can edit config/config.yaml anytime to modify these settings.[/yellow]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("1. Start the updater: [green]docker compose up -d dakosys-updater[/green]")

    if config['services']['anime_episode_type']['enabled']:
        console.print("2. Create your first anime list: [green]docker compose run --rm dakosys create-all 'One Piece' or docker compose run --rm dakosys create one-piece MANGA [/green]")

def save_config_with_comments(config, path):
    """Save config to YAML with comments."""
    with open(path, 'w') as file:
        # Write the tv_status_tracker.overlay section with a comment explaining overlay_style options
        if 'services' in config and 'tv_status_tracker' in config['services']:
            tv_status_overlay = config['services']['tv_status_tracker']['overlay']
            tv_status_overlay_yaml = yaml.dump({'overlay': tv_status_overlay}, allow_unicode=True, default_flow_style=False, sort_keys=False)

            lines = tv_status_overlay_yaml.split('\n')
            for i, line in enumerate(lines):
                if 'overlay_style:' in line:
                    lines.insert(i, '    # overlay_style: The style of the overlay. Options: background_color, colored_text')
                    break

            config['services']['tv_status_tracker']['overlay'] = yaml.safe_load('\n'.join(lines))['overlay']

        yaml.dump(config, file, allow_unicode=True, default_flow_style=False, sort_keys=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='DAKOSYS Setup Script')
    parser.add_argument('-service', '--service', help='Configure a specific service only (anime_episode_type, tv_status_tracker, size_overlay)')
    args = parser.parse_args()

    if args.service:
        setup_service(args.service)
    else:
        run_setup()
