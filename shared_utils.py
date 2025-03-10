import logging
import datetime

def connect_to_plex():
    """Connect to Plex server."""
    try:
        # Import the shared utility if available
        try:
            from shared_utils import connect_to_plex as shared_connect
            plex = shared_connect(CONFIG)
            if plex:
                return plex
        except ImportError:
            # Fallback to original method if shared_utils isn't available
            pass
        console.print("[bold blue]Connecting to Plex server...[/bold blue]")
        plex = PlexServer(CONFIG['plex']['url'], CONFIG['plex']['token'])
        console.print("[bold green]Connected to Plex server successfully![/bold green]")
        return plex
    except Exception as e:
        console.print(f"[bold red]Failed to connect to Plex server: {str(e)}[/bold red]")
        console.print("[yellow]Please check your Plex URL and token in the configuration file.[/yellow]")
        return None
def get_anime_libraries(plex):
    """Get all configured anime libraries."""
    libraries = []
    # Check for multiple libraries in new config format
    if 'libraries' in CONFIG.get('plex', {}) and 'anime' in CONFIG['plex']['libraries']:
        library_names = CONFIG['plex']['libraries']['anime']
    else:
        # Fallback to legacy single library
        library_names = [CONFIG['plex']['library']]
    for library_name in library_names:
        try:
            library = plex.library.section(library_name)
            libraries.append(library)
            console.print(f"[blue]Using library: {library_name}[/blue]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not access library '{library_name}': {str(e)}[/yellow]")
    if not libraries:
        console.print("[bold red]No valid anime libraries found. Please check your configuration.[/bold red]")
    return libraries

def setup_rotating_logger(logger_name, log_file, level=logging.INFO, max_size_mb=10, backup_count=5):
    """Set up a rotating file logger with beautiful formatting."""
    import os
    import logging
    import sys
    from logging.handlers import RotatingFileHandler
    import datetime

    # Ensure directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Get logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False

    # Clear any existing handlers to prevent duplicate logs
    if logger.handlers:
        logger.handlers = []

    # Create a rotating file handler
    max_bytes = max_size_mb * 1024 * 1024  # Convert MB to bytes
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setLevel(level)

    # Create a cleaner file formatter that doesn't repeat the logger name
    # Format: "2023-01-01 14:30:45 [INFO] Your message here"
    file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(file_formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)

    # Add console handler with appropriate level
    console_handler = logging.StreamHandler()

    # Check if we're in a CLI command
    is_cli_command = (
        'create-list' in sys.argv or
        'create-all' in sys.argv or
        'setup' in sys.argv or
        'list-lists' in sys.argv or
        'fix-mappings' in sys.argv or
        'delete-list' in sys.argv
    )

    # If explicitly CLI command, force WARNING level with minimal formatting
    if is_cli_command:
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    # If in daemon/Docker log mode, use fancy formatter
    elif os.environ.get('DAEMON_MODE') == 'true' or os.environ.get('SCHEDULER_MODE') == 'true' or os.environ.get('RUNNING_IN_DOCKER') == 'true':
        console_handler.setLevel(level)  # Use same level as file
        console_formatter = DockerLogFormatter()
    # Default fallback
    else:
        console_handler.setLevel(logging.WARNING)  # Less verbose
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger

class DockerLogFormatter(logging.Formatter):
    """Beautiful formatter for Docker logs with improved readability."""
    # ANSI color codes for beautiful logs
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[95m', # Bright magenta
        'RESET': '\033[0m',     # Reset
        'BOLD': '\033[1m',      # Bold
        'DIM': '\033[2m',       # Dim
        'TIMESTAMP': '\033[90m' # Gray for timestamp
    }

    # Icons to visually distinguish log levels
    ICONS = {
        'DEBUG': '🔍',
        'INFO': '✓',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }

    def format(self, record):
        # Get current timestamp in a nice format
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')

        # Get appropriate colors and icons
        log_level = record.levelname
        color = self.COLORS.get(log_level, self.COLORS['RESET'])
        icon = self.ICONS.get(log_level, '')
        reset = self.COLORS['RESET']

        # Format message with color, icon and timestamp
        # Timestamp is in gray, level is bold and colored, message is regular
        formatted_msg = (
            f"{self.COLORS['TIMESTAMP']}{timestamp}{reset} "
            f"{color}{self.COLORS['BOLD']}{icon} {log_level}:{reset} "
            f"{record.getMessage()}"
        )

        # Handle multiline messages with proper indentation
        if '\n' in formatted_msg:
            lines = formatted_msg.split('\n')
            indent = ' ' * (len(timestamp) + 3)  # Space for timestamp + icon
            formatted_msg = '\n'.join([lines[0]] + [f"{self.COLORS['TIMESTAMP']}{indent}{reset} {line}" for line in lines[1:]])

        # Add exception info if available, with proper formatting
        if record.exc_info:
            exception = self.formatException(record.exc_info)
            formatted_msg += f"\n{self.COLORS['TIMESTAMP']}{timestamp}{reset} {self.COLORS['ERROR']}⚡ EXCEPTION:{reset} {exception}"

        return formatted_msg
