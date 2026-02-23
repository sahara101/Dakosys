import logging
import datetime

def connect_to_plex():
    """Connect to Plex server."""
    try:
        try:
            from shared_utils import connect_to_plex as shared_connect
            plex = shared_connect(CONFIG)
            if plex:
                return plex
        except ImportError:
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
    library_names = CONFIG.get('plex', {}).get('libraries', {}).get('anime', [])
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

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        logger.handlers = []

    max_bytes = max_size_mb * 1024 * 1024
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setLevel(level)

    file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(file_formatter)

    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()

    is_cli_command = (
        'create-list' in sys.argv or
        'create-all' in sys.argv or
        'setup' in sys.argv or
        'list-lists' in sys.argv or
        'fix-mappings' in sys.argv or
        'delete-list' in sys.argv
    )

    if is_cli_command:
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    elif os.environ.get('DAEMON_MODE') == 'true' or os.environ.get('SCHEDULER_MODE') == 'true' or os.environ.get('RUNNING_IN_DOCKER') == 'true':
        console_handler.setLevel(level)
        console_formatter = DockerLogFormatter()
    else:
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger

class DockerLogFormatter(logging.Formatter):
    """Beautiful formatter for Docker logs with improved readability."""
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

    ICONS = {
        'DEBUG': '🔍',
        'INFO': '✓',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }

    def format(self, record):
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')

        log_level = record.levelname
        color = self.COLORS.get(log_level, self.COLORS['RESET'])
        icon = self.ICONS.get(log_level, '')
        reset = self.COLORS['RESET']

        formatted_msg = (
            f"{self.COLORS['TIMESTAMP']}{timestamp}{reset} "
            f"{color}{self.COLORS['BOLD']}{icon} {log_level}:{reset} "
            f"{record.getMessage()}"
        )

        if '\n' in formatted_msg:
            lines = formatted_msg.split('\n')
            indent = ' ' * (len(timestamp) + 3)  # Space for timestamp + icon
            formatted_msg = '\n'.join([lines[0]] + [f"{self.COLORS['TIMESTAMP']}{indent}{reset} {line}" for line in lines[1:]])

        if record.exc_info:
            exception = self.formatException(record.exc_info)
            formatted_msg += f"\n{self.COLORS['TIMESTAMP']}{timestamp}{reset} {self.COLORS['ERROR']}⚡ EXCEPTION:{reset} {exception}"

        return formatted_msg
