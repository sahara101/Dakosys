#!/usr/bin/env python3
"""
Scheduler for DAKOSYS
Handles flexible per-service scheduling options from config file
"""

import os
import sys
import time
import datetime
import logging
import yaml
import re
import schedule
from threading import Event
from shared_utils import setup_rotating_logger

# Set up data directory
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

# Global variables
CONFIG_FILE = "config/config.yaml"
if os.environ.get('RUNNING_IN_DOCKER') == 'true':
    CONFIG_FILE = "/app/config/config.yaml"
stop_event = Event()

def load_config():
    """Load configuration from YAML file."""
    try:
        if not os.path.exists(CONFIG_FILE):
            logger.error(f"Configuration file not found at {CONFIG_FILE}")
            return None

        with open(CONFIG_FILE, 'r') as file:
            config = yaml.safe_load(file)

        # Apply timezone from config if available
        if config and 'timezone' in config:
            os.environ['TZ'] = config['timezone']
            # Reload time module to use new timezone
            import time
            time.tzset()
            logger.info(f"Using timezone from config: {config['timezone']}")

        return config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        return None

def validate_time_format(time_str):
    """Validate time string format (HH:MM)."""
    time_str = str(time_str)
    if not re.match(r'^([0-1][0-9]|2[0-3]):([0-5][0-9])$', time_str):
        logger.error(f"Invalid time format '{time_str}'. Use HH:MM (e.g., 14:30)")
        return False
    return True

def validate_day_format(day_str):
    """Validate day string format (monday, tuesday, etc.)."""
    valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    return day_str.lower() in valid_days

def validate_date_format(date):
    """Validate date (1-31)."""
    try:
        return 1 <= int(date) <= 31
    except ValueError:
        return False

def run_anime_episode_update():
    """Run the anime episode type update job."""
    config = load_config()
    if not config:
        logger.error("Failed to load configuration")
        return

    # Check if anime episode type service is enabled
    if not config.get('services', {}).get('anime_episode_type', {}).get('enabled', False):
        logger.info("Anime Episode Type service is disabled, skipping update")
        return

    # Check if dry run is enabled
    dry_run = config.get('scheduler', {}).get('anime_episode_type', {}).get('dry_run', False)

    logger.info(f"Running Anime Episode Type update (dry_run={dry_run})")

    if dry_run:
        logger.info("DRY RUN: Would update anime lists now")
    else:
        try:
            # Set environment variable to indicate we're running from scheduler
            os.environ['SCHEDULER_MODE'] = 'true'

            # Import and run anime update
            from auto_update import run_update
            run_update(['anime_episode_type'])
        except Exception as e:
            logger.error(f"Error running anime update: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # Unset environment variable
            if 'SCHEDULER_MODE' in os.environ:
                del os.environ['SCHEDULER_MODE']

def run_tv_status_update():
    """Run the TV/Anime Status Tracker update job."""
    config = load_config()
    if not config:
        logger.error("Failed to load configuration")
        return

    # Check if TV status tracker service is enabled
    if not config.get('services', {}).get('tv_status_tracker', {}).get('enabled', False):
        logger.info("TV/Anime Status Tracker service is disabled, skipping update")
        return

    # Check if dry run is enabled
    dry_run = config.get('scheduler', {}).get('tv_status_tracker', {}).get('dry_run', False)

    logger.info(f"Running TV/Anime Status Tracker update (dry_run={dry_run})")

    if dry_run:
        logger.info("DRY RUN: Would update TV/Anime status overlays now")
    else:
        try:
            # Set environment variable to indicate we're running from scheduler
            os.environ['SCHEDULER_MODE'] = 'true'

            # Import and run TV status update
            from auto_update import run_update
            run_update(['tv_status_tracker'])
        except Exception as e:
            logger.error(f"Error running TV/Anime Status update: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # Unset environment variable
            if 'SCHEDULER_MODE' in os.environ:
                del os.environ['SCHEDULER_MODE']

def run_size_overlay_update():
    """Run the Size Overlay update job."""
    config = load_config()
    if not config:
        logger.error("Failed to load configuration")
        return

    # Check if Size Overlay service is enabled
    if not config.get('services', {}).get('size_overlay', {}).get('enabled', False):
        logger.info("Size Overlay service is disabled, skipping update")
        return

    # Check if dry run is enabled
    dry_run = config.get('scheduler', {}).get('size_overlay', {}).get('dry_run', False)

    logger.info(f"Running Size Overlay update (dry_run={dry_run})")

    if dry_run:
        logger.info("DRY RUN: Would update size overlays now")
    else:
        try:
            # Set environment variable to indicate we're running from scheduler
            os.environ['SCHEDULER_MODE'] = 'true'

            # Import and run Size Overlay update
            from auto_update import run_update
            run_update(['size_overlay'])
        except Exception as e:
            logger.error(f"Error running Size Overlay update: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # Unset environment variable
            if 'SCHEDULER_MODE' in os.environ:
                del os.environ['SCHEDULER_MODE']

def setup_run_once(service_name, job_func):
    """Setup to run once for a specific service."""
    logger.info(f"Setting up {service_name} to run once")
    schedule.every().day.at("00:00").do(job_func).tag(service_name)
    job_func()  # Run immediately

def setup_hourly_schedule(service_name, minute, job_func):
    """Setup hourly schedule for a specific service."""
    try:
        minute = int(minute)
        if 0 <= minute <= 59:
            logger.info(f"Setting up {service_name} hourly schedule at minute {minute}")
            schedule.every().hour.at(f":{minute:02d}").do(job_func).tag(service_name)
            return True
        else:
            logger.error(f"Invalid minute for {service_name} hourly schedule: {minute}")
            return False
    except ValueError:
        logger.error(f"Invalid minute for {service_name} hourly schedule: {minute}")
        return False

def setup_daily_schedule(service_name, times, job_func):
    """Setup daily schedule with one or more times for a specific service."""
    if not times:
        logger.error(f"No times provided for {service_name} daily schedule")
        return False

    success = False
    for time_str in times:
        if validate_time_format(time_str):
            logger.info(f"Setting up {service_name} daily schedule at {time_str}")
            schedule.every().day.at(time_str).do(job_func).tag(service_name)
            success = True
        else:
            logger.error(f"Invalid time format for {service_name} daily schedule: {time_str}")

    return success

def setup_weekly_schedule(service_name, days, time_str, job_func):
    """Setup weekly schedule on specific days for a specific service."""
    if not days or not time_str:
        logger.error(f"Missing days or time for {service_name} weekly schedule")
        return False

    if not validate_time_format(time_str):
        logger.error(f"Invalid time format for {service_name} weekly schedule: {time_str}")
        return False

    success = False
    for day in days:
        if validate_day_format(day):
            logger.info(f"Setting up {service_name} weekly schedule on {day} at {time_str}")
            getattr(schedule.every(), day.lower()).at(time_str).do(job_func).tag(service_name)
            success = True
        else:
            logger.error(f"Invalid day format for {service_name} weekly schedule: {day}")

    return success

def setup_monthly_schedule(service_name, dates, time_str, job_func):
    """Setup monthly schedule on specific dates for a specific service."""
    if not dates or not time_str:
        logger.error(f"Missing dates or time for {service_name} monthly schedule")
        return False

    if not validate_time_format(time_str):
        logger.error(f"Invalid time format for {service_name} monthly schedule: {time_str}")
        return False

    # For monthly schedules, we need a custom job using a lambda
    success = False
    for date in dates:
        if validate_date_format(date):
            logger.info(f"Setting up {service_name} monthly schedule on day {date} at {time_str}")

            # Parse the time
            hour, minute = map(int, time_str.split(':'))

            # Create a custom scheduler that checks if it's the right day of month
            def monthly_job():
                now = datetime.datetime.now()
                if now.day == int(date):
                    job_func()

            # Schedule to run daily at the specified time, but the job will check the date
            schedule.every().day.at(time_str).do(monthly_job).tag(service_name)
            success = True
        else:
            logger.error(f"Invalid date format for {service_name} monthly schedule: {date}")

    return success

def setup_cron_schedule(service_name, expression, job_func):
    """Setup a cron-like schedule for a specific service."""
    try:
        logger.info(f"Setting up {service_name} cron schedule with expression: {expression}")

        # Parse the cron expression (minute hour day month day_of_week)
        parts = expression.split()
        if len(parts) < 5:
            logger.error(f"Invalid cron expression: {expression}")
            return False

        minute, hour, day, month, day_of_week = parts[:5]

        # Currently, we'll implement a simple subset of cron for common cases

        # Case: Daily at specific time (0 3 * * *)
        if minute.isdigit() and hour.isdigit() and day == '*' and month == '*' and day_of_week == '*':
            time_str = f"{int(hour):02d}:{int(minute):02d}"
            logger.info(f"Interpreted as {service_name} daily schedule at {time_str}")
            return setup_daily_schedule(service_name, [time_str], job_func)

        # Case: Every X hours (0 */3 * * *)
        if minute == '0' and hour.startswith('*/') and day == '*' and month == '*' and day_of_week == '*':
            try:
                interval = int(hour[2:])
                logger.info(f"Interpreted as {service_name} every {interval} hours")
                for h in range(0, 24, interval):
                    time_str = f"{h:02d}:00"
                    schedule.every().day.at(time_str).do(job_func).tag(service_name)
                return True
            except ValueError:
                logger.error(f"Invalid hour interval in cron expression: {hour}")
                return False

        # Case: Every X minutes (*/15 * * *)
        if minute.startswith('*/') and hour == '*' and day == '*' and month == '*' and day_of_week == '*':
            try:
                interval = int(minute[2:])
                logger.info(f"Interpreted as {service_name} every {interval} minutes")
                schedule.every(interval).minutes.do(job_func).tag(service_name)
                return True
            except ValueError:
                logger.error(f"Invalid minute interval in cron expression: {minute}")
                return False

        # For more complex expressions, we'd need a full cron parser
        logger.warning(f"Complex cron expressions not fully supported. Defaulting to {service_name} daily at 3:00 AM")
        return setup_daily_schedule(service_name, ["03:00"], job_func)

    except Exception as e:
        logger.error(f"Error setting up {service_name} cron schedule: {str(e)}")
        return False

def setup_service_schedule(service_name, schedule_config, job_func):
    """Setup schedule for a specific service based on configuration."""
    if not schedule_config:
        logger.warning(f"No schedule configuration found for {service_name}. Using default daily schedule at 3:00 AM")
        return setup_daily_schedule(service_name, ["03:00"], job_func)

    schedule_type = schedule_config.get('type', '').lower()

    if schedule_type == 'run':
        setup_run_once(service_name, job_func)
        return True

    elif schedule_type == 'hourly':
        minute = schedule_config.get('minute', 0)
        return setup_hourly_schedule(service_name, minute, job_func)

    elif schedule_type == 'daily':
        times = schedule_config.get('times', ["03:00"])
        if isinstance(times, str):
            times = [times]
        return setup_daily_schedule(service_name, times, job_func)

    elif schedule_type == 'weekly':
        days = schedule_config.get('days', ["monday"])
        if isinstance(days, str):
            days = [days]
        time_str = schedule_config.get('time', "03:00")
        return setup_weekly_schedule(service_name, days, time_str, job_func)

    elif schedule_type == 'monthly':
        dates = schedule_config.get('dates', [1])
        if isinstance(dates, int):
            dates = [dates]
        time_str = schedule_config.get('time', "03:00")
        return setup_monthly_schedule(service_name, dates, time_str, job_func)

    elif schedule_type == 'cron':
        expression = schedule_config.get('expression', "0 3 * * *")
        return setup_cron_schedule(service_name, expression, job_func)

    else:
        logger.error(f"Unknown schedule type for {service_name}: {schedule_type}")
        return False

def setup_scheduler():
    """Setup scheduler based on configuration."""
    config = load_config()
    if not config:
        logger.error("Failed to load configuration")
        return False

    # Clear any existing jobs
    schedule.clear()

    logger.info("=" * 50)
    logger.info("DAKOSYS SCHEDULER CONFIGURATION")
    logger.info("=" * 50)

    # Setup schedules for enabled services
    services_configured = False
    scheduled_services = []

    # Configure Anime Episode Type service if enabled
    if config.get('services', {}).get('anime_episode_type', {}).get('enabled', True):
        service_scheduler = config.get('scheduler', {}).get('anime_episode_type', {})

        # Log the anime list that will be updated
        scheduled_anime = config.get('scheduler', {}).get('scheduled_anime', [])

        # Create a list of display names (Plex titles) with better mapping
        anime_display_list = []
        for afl_name in scheduled_anime:
            # Get Plex name from mappings
            plex_name = config.get('mappings', {}).get(afl_name, afl_name)
            # If still AFL format, make it user-friendly
            if '-' in plex_name:
                plex_name = plex_name.replace('-', ' ').title()
            anime_display_list.append(plex_name)

        logger.info(f"Anime Episode Type service enabled - {len(scheduled_anime)} anime scheduled")
        if scheduled_anime:
            # Use the display names (Plex titles) in the log instead of AFL names
            logger.info(f"Scheduled anime titles: {', '.join(anime_display_list)}")
        
        if setup_service_schedule('anime_episode_type', service_scheduler, run_anime_episode_update):
            services_configured = True
            
            # Show detailed schedule information
            schedule_type = service_scheduler.get('type', 'daily')
            times = service_scheduler.get('times', ["03:00"])
            if isinstance(times, str):
                times = [times]
            scheduled_services.append({
                'name': 'Anime Episode Type',
                'type': schedule_type,
                'times': times
            })

    # Configure TV/Anime Status Tracker service if enabled
    if config.get('services', {}).get('tv_status_tracker', {}).get('enabled', False):
        # Get service-specific schedule config
        service_scheduler = config.get('scheduler', {}).get('tv_status_tracker', {})
        if setup_service_schedule('tv_status_tracker', service_scheduler, run_tv_status_update):
            services_configured = True
            logger.info("TV/Anime Status Tracker service scheduled successfully")

    # Configure Size Overlay service if enabled
    if config.get('services', {}).get('size_overlay', {}).get('enabled', False):
        # Get service-specific schedule config
        service_scheduler = config.get('scheduler', {}).get('size_overlay', {})
        if setup_service_schedule('size_overlay', service_scheduler, run_size_overlay_update):
            services_configured = True
            logger.info("Size Overlay service scheduled successfully")

    if scheduled_services:
        logger.info("\nScheduled services:")
        for service in scheduled_services:
            logger.info(f"  • {service['name']}: {service['type']} at {', '.join(service['times'])}")

    # If no services were configured, log a warning
    if not services_configured:
        logger.warning("No services were scheduled")

    return services_configured

def run_scheduler():
    """Run the scheduler loop."""
    # Make sure we mark this process as a daemon for logging
    os.environ['SCHEDULER_MODE'] = 'true'

    logger.info("Starting scheduler")

    if not setup_scheduler():
        logger.error("Failed to setup scheduler. No services will run.")
        return False

    # Run pending jobs on startup in case we're close to a scheduled time
    schedule.run_pending()

    # Log the next scheduled runs for each service
    logger.info("Scheduler running...")
    next_jobs = []
    for job in schedule.get_jobs():
        next_run = job.next_run
        if next_run:
            tag = "Unknown"
            if job.tags and len(job.tags) > 0:
                tag = next(iter(job.tags))  # Get first item from set safely
            next_jobs.append(f"{tag}: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

    if next_jobs:
        logger.info("Next scheduled runs:")
        for job_info in next_jobs:
            logger.info(f"  - {job_info}")

    try:
        while not stop_event.is_set():
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user")
        stop_scheduler()
    except Exception as e:
        logger.error(f"Unexpected error in scheduler: {str(e)}")
        return False

    logger.info("Scheduler stopped.")
    return True

def stop_scheduler():
    """Stop the scheduler."""
    stop_event.set()

if __name__ == "__main__":
    try:
        run_scheduler()
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user")
        stop_scheduler()
    except Exception as e:
        logger.error(f"Unexpected error in scheduler: {str(e)}")
