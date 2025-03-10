#!/usr/bin/env python3
"""
Improved Trakt.tv Authentication Module for DAKOSYS
Handles authentication, token refresh, and persistent sessions with simplified flows
"""

import os
import json
import time
import yaml
import requests
import logging
from rich.console import Console

# Initialize console and logger
console = Console()
logger = logging.getLogger("trakt_auth")

# Constants
DEFAULT_CONFIG_PATH = "config/config.yaml"
DEFAULT_DATA_DIR = "data"

def get_config_path():
    """Get the appropriate config path based on environment."""
    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        return "/app/config/config.yaml"
    return DEFAULT_CONFIG_PATH

def get_data_dir():
    """Get the appropriate data directory based on environment."""
    if os.environ.get('RUNNING_IN_DOCKER') == 'true':
        return "/app/data"
    return DEFAULT_DATA_DIR

def load_config():
    """Load configuration from YAML file."""
    config_path = get_config_path()
    
    try:
        if not os.path.exists(config_path):
            logger.error(f"Configuration file not found at {config_path}")
            console.print(f"[bold red]Configuration file not found at {config_path}[/bold red]")
            return None
            
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
            
        return config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        console.print(f"[bold red]Error loading configuration: {str(e)}[/bold red]")
        return None

def get_stored_trakt_tokens():
    """Retrieve stored Trakt access token and refresh token."""
    token_file = os.path.join(get_data_dir(), 'trakt_token.json')
    try:
        if os.path.exists(token_file):
            with open(token_file, 'r') as file:
                data = json.load(file)
                return data.get('access_token'), data.get('refresh_token'), data.get('created_at', 0), data.get('expires_in', 0)
    except Exception as e:
        logger.warning(f"Error reading token file: {str(e)}")
        console.print(f"[yellow]Error reading token file: {str(e)}[/yellow]")
    return None, None, 0, 0

def store_trakt_tokens(access_token, refresh_token, created_at, expires_in):
    """Store Trakt access and refresh tokens."""
    data_dir = get_data_dir()
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    token_file = os.path.join(data_dir, 'trakt_token.json')
    try:
        with open(token_file, 'w') as file:
            json.dump({
                'access_token': access_token,
                'refresh_token': refresh_token,
                'created_at': created_at,
                'expires_in': expires_in
            }, file)
        return True
    except Exception as e:
        logger.error(f"Error storing tokens: {str(e)}")
        console.print(f"[bold red]Error storing tokens: {str(e)}[/bold red]")
        return False

def get_device_code(config=None):
    """Get a device code using Trakt's device authentication flow."""
    if config is None:
        config = load_config()
        if not config:
            return None, None
            
    try:
        trakt_api_url = 'https://api.trakt.tv'
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-key': config['trakt']['client_id'],
            'trakt-api-version': '2',
        }
        
        # Request device code
        device_code_url = f'{trakt_api_url}/oauth/device/code'
        payload = {
            'client_id': config['trakt']['client_id'],
        }
        
        response = requests.post(device_code_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            device_code = data.get('device_code')
            user_code = data.get('user_code')
            verification_url = data.get('verification_url')
            expires_in = data.get('expires_in', 600)  # Usually 10 minutes
            interval = data.get('interval', 5)  # Usually 5 seconds
            
            return {
                'device_code': device_code,
                'user_code': user_code,
                'verification_url': verification_url,
                'expires_in': expires_in,
                'interval': interval
            }, None
        else:
            logger.error(f"Failed to get device code. Status Code: {response.status_code}, Response: {response.text}")
            return None, f"Failed to get device code. Status Code: {response.status_code}"
    except Exception as e:
        logger.error(f"Error getting device code: {str(e)}")
        return None, f"Error getting device code: {str(e)}"

def poll_for_token(device_code, interval, expires_in, config=None):
    """Poll for access token using device code."""
    if config is None:
        config = load_config()
        if not config:
            return None, None
            
    try:
        trakt_api_url = 'https://api.trakt.tv'
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-key': config['trakt']['client_id'],
            'trakt-api-version': '2',
        }
        
        # Poll for token
        token_url = f'{trakt_api_url}/oauth/device/token'
        payload = {
            'code': device_code,
            'client_id': config['trakt']['client_id'],
            'client_secret': config['trakt']['client_secret'],
        }
        
        start_time = time.time()
        console.print("[yellow]Waiting for authorization...[/yellow]")
        
        while time.time() - start_time < expires_in:
            response = requests.post(token_url, json=payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                access_token = data.get('access_token')
                refresh_token = data.get('refresh_token')
                token_expires_in = data.get('expires_in', 7776000)  # 90 days in seconds
                created_at = int(time.time())
                
                store_trakt_tokens(access_token, refresh_token, created_at, token_expires_in)
                return access_token, None
            elif response.status_code == 400:
                # User hasn't authorized yet, wait and try again
                time.sleep(interval)
            elif response.status_code == 404:
                # Invalid device code
                return None, "Invalid device code"
            elif response.status_code == 409:
                # Already used
                return None, "Device code already used"
            elif response.status_code == 410:
                # Expired
                return None, "Device code expired"
            elif response.status_code == 418:
                # Denied by user
                return None, "Authorization denied by user"
            elif response.status_code == 429:
                # Rate limited
                retry_after = int(response.headers.get('Retry-After', interval))
                time.sleep(retry_after)
            else:
                return None, f"Error polling for token. Status Code: {response.status_code}"
        
        return None, "Timeout waiting for authorization"
    except Exception as e:
        logger.error(f"Error polling for token: {str(e)}")
        return None, f"Error polling for token: {str(e)}"

def direct_token_auth(config=None):
    """Attempt to get token using client credentials (useful for single-user access)."""
    if config is None:
        config = load_config()
        if not config:
            return None, None
            
    try:
        trakt_api_url = 'https://api.trakt.tv'
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-key': config['trakt']['client_id'],
            'trakt-api-version': '2',
        }
        
        # Try client credentials flow
        token_url = f'{trakt_api_url}/oauth/token'
        payload = {
            'client_id': config['trakt']['client_id'],
            'client_secret': config['trakt']['client_secret'],
            'grant_type': 'client_credentials',
        }
        
        response = requests.post(token_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            access_token = data.get('access_token')
            created_at = int(time.time())
            expires_in = data.get('expires_in', 7776000)  # Default to 90 days
            
            # This flow doesn't provide a refresh token
            store_trakt_tokens(access_token, None, created_at, expires_in)
            return access_token, None
        else:
            logger.error(f"Failed to get token with client credentials. Status Code: {response.status_code}, Response: {response.text}")
            return None, f"Failed to get token with client credentials. Status Code: {response.status_code}"
    except Exception as e:
        logger.error(f"Error with client credentials auth: {str(e)}")
        return None, f"Error with client credentials auth: {str(e)}"

def refresh_trakt_token(refresh_token, config=None):
    """Refresh Trakt access token using refresh token."""
    try:
        if config is None:
            config = load_config()
            if not config:
                return None
                
        trakt_auth_url = 'https://api.trakt.tv/oauth/token'

        refresh_payload = {
            'refresh_token': refresh_token,
            'client_id': config['trakt']['client_id'],
            'client_secret': config['trakt']['client_secret'],
            'redirect_uri': config['trakt']['redirect_uri'],
            'grant_type': 'refresh_token',
        }

        response = requests.post(trakt_auth_url, json=refresh_payload)

        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get('access_token')
            new_refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 7776000)  # Default 90 days in seconds
            created_at = int(time.time())
            
            store_trakt_tokens(access_token, new_refresh_token, created_at, expires_in)
            logger.info("Successfully refreshed Trakt access token")
            return access_token
        else:
            logger.error(f"Failed to refresh Trakt access token. Status Code: {response.status_code}, Response: {response.text}")
            console.print(f"[bold red]Failed to refresh Trakt access token. Status Code: {response.status_code}[/bold red]")
            console.print(f"[yellow]Response: {response.text}[/yellow]")
            return None
    except Exception as e:
        logger.error(f"Error during token refresh: {str(e)}")
        console.print(f"[bold red]Error during token refresh: {str(e)}[/bold red]")
        return None

def perform_device_auth(config=None, quiet=False):
    """Perform device code authentication flow."""
    if not quiet:
        console.print("[bold]Trakt.tv Authentication Required[/bold]")
        
    # Start device auth flow
    device_info, error = get_device_code(config)
    if error:
        if not quiet:
            console.print(f"[bold red]Error: {error}[/bold red]")
        return None
    
    if not quiet:
        console.print(f"\n[bold]To authorize DAKOSYS, please:[/bold]")
        console.print(f"1. Go to: [bold blue]{device_info['verification_url']}[/bold blue]")
        console.print(f"2. Enter code: [bold green]{device_info['user_code']}[/bold green]")
        console.print(f"\nThe code expires in {device_info['expires_in'] // 60} minutes.")
    
    # Poll for token
    access_token, error = poll_for_token(
        device_info['device_code'], 
        device_info['interval'], 
        device_info['expires_in'],
        config
    )
    
    if error:
        if not quiet:
            console.print(f"[bold red]Error: {error}[/bold red]")
        return None
    
    if not quiet and access_token:
        console.print("[bold green]Successfully authenticated with Trakt.tv![/bold green]")
    
    return access_token

def ensure_trakt_auth(quiet=False):
    """Ensure we have a valid Trakt authorization.
    
    Args:
        quiet: If True, suppresses console output
    
    Returns:
        Access token string or None
    """
    config = load_config()
    if not config:
        return None
        
    access_token = get_access_token(config=config, quiet=quiet)
    if not access_token and not quiet:
        console.print("[bold red]Failed to authenticate with Trakt.tv.[/bold red]")
    
    return access_token

def get_trakt_headers(access_token=None):
    """Get headers for Trakt API requests."""
    if not access_token:
        access_token = ensure_trakt_auth(quiet=True)
        if not access_token:
            return None
    
    config = load_config()
    if not config:
        return None
        
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}',
        'trakt-api-key': config['trakt']['client_id'],
        'trakt-api-version': '2',
    }

def get_access_token(config=None, quiet=False):
    """Get a valid access token using the most appropriate method."""
    if config is None:
        config = load_config()
        if not config:
            return None
    
    # First check if we have stored tokens
    access_token, refresh_token, created_at, expires_in = get_stored_trakt_tokens()
    
    # Check if access token exists and is still valid (with 1 hour buffer)
    current_time = int(time.time())
    if access_token and refresh_token and created_at + expires_in - 3600 > current_time:
        logger.debug("Using existing valid access token with refresh token")
        return access_token
    elif access_token and not refresh_token and created_at + expires_in - 3600 > current_time:
        # We have a client credentials token - but we need a user token
        logger.warning("Found client credentials token without refresh token - need user token")
        if not quiet:
            console.print("[yellow]Current token doesn't have user access. Need to authenticate as user.[/yellow]")
        # Fall through to device auth
    elif refresh_token:
        if not quiet:
            console.print("[yellow]Access token expired, attempting to refresh...[/yellow]")
        new_access_token = refresh_trakt_token(refresh_token, config)
        if new_access_token:
            if not quiet:
                console.print("[green]Successfully refreshed Trakt access token.[/green]")
            return new_access_token
        else:
            if not quiet:
                console.print("[yellow]Token refresh failed, will need to re-authorize.[/yellow]")
    
    # Skip client credentials - we need user context
    # Use device code flow directly (user authentication)
    return perform_device_auth(config, quiet)

def ensure_auth_during_setup(config):
    """Initialize authentication during setup."""
    # Create data directory if it doesn't exist
    data_dir = get_data_dir()
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    console.print("\n[bold]Authenticating with Trakt.tv...[/bold]")
    console.print("[yellow]This will authorize DAKOSYS to access your Trakt.tv account.[/yellow]")
    
    # Skip client credentials and use device code flow directly
    console.print("[blue]Setting up user authentication via device code...[/blue]")
    access_token = perform_device_auth(config)
    
    if access_token:
        # Verify the user matches the config
        trakt_api_url = 'https://api.trakt.tv'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
            'trakt-api-key': config['trakt']['client_id'],
            'trakt-api-version': '2',
        }
        
        # Get authenticated user
        me_url = f'{trakt_api_url}/users/me'
        response = requests.get(me_url, headers=headers)
        
        if response.status_code == 200:
            user_data = response.json()
            authenticated_username = user_data.get('username')
            
            if authenticated_username != config['trakt']['username']:
                console.print(f"[yellow]Warning: Authenticated as '{authenticated_username}' but config has '{config['trakt']['username']}'[/yellow]")
                console.print("[yellow]Updating username in config to match authenticated user[/yellow]")
                
                # Update config
                config['trakt']['username'] = authenticated_username
                
                # Save config
                if os.environ.get('RUNNING_IN_DOCKER') == 'true':
                    config_path = "/app/config/config.yaml"
                else:
                    config_path = get_config_path()
                    
                with open(config_path, 'w') as file:
                    yaml.dump(config, file)
                
            console.print(f"[green]Successfully authenticated as {authenticated_username}[/green]")
        else:
            console.print(f"[yellow]Could not verify username (status {response.status_code})[/yellow]")
        
        return True
    else:
        console.print("[bold yellow]Authentication can be completed later when running commands.[/bold yellow]")
        return False

def make_trakt_request(endpoint, method="GET", data=None, params=None):
    """Make an authenticated request to the Trakt API."""
    headers = get_trakt_headers()
    if not headers:
        return None
        
    trakt_api_url = 'https://api.trakt.tv'
    url = f"{trakt_api_url}/{endpoint.lstrip('/')}"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, params=params)
        elif method.upper() == "PUT":
            response = requests.put(url, headers=headers, json=data, params=params)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, params=params)
        else:
            logger.error(f"Unsupported HTTP method: {method}")
            return None
            
        if response.status_code in (200, 201, 204):
            if response.status_code == 204 or not response.text:
                return True
            return response.json()
        elif response.status_code == 404 and 'users/' in endpoint:
            # Specific error for user not found
            username = endpoint.split('users/')[1].split('/')[0]
            logger.error(f"User '{username}' not found on Trakt or token lacks permission")
            return None
        else:
            logger.error(f"Trakt API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error making Trakt API request: {str(e)}")
        return None

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(get_data_dir(), "trakt_auth.log")),
            logging.StreamHandler()
        ]
    )
    
    # Simple test of authentication
    console.print("[bold]Testing Trakt.tv authentication...[/bold]")
    access_token = ensure_trakt_auth()
    
    if access_token:
        console.print("[bold green]Authentication successful![/bold green]")
        # Test API access
        config = load_config()
        user = make_trakt_request(f"users/{config['trakt']['username']}")
        if user:
            console.print(f"[green]Successfully accessed Trakt user: {user.get('username')}[/green]")
        else:
            console.print("[bold red]Failed to access Trakt API![/bold red]")
    else:
        console.print("[bold red]Authentication failed![/bold red]")
