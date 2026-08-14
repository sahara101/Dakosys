#!/usr/bin/env python3
"""TheTVDB metadata provider for DAKOSYS."""

import logging
import os
import threading
import time
from datetime import datetime

import pytz
import requests

logger = logging.getLogger("tvdb_metadata")

TVDB_BASE = "https://api4.thetvdb.com/v4"
TMDB_BASE = "https://api.themoviedb.org/3"

DEFAULT_API_KEY = os.environ.get("DAKOSYS_TVDB_API_KEY", "")
PROXY_URL = os.environ.get(
    "DAKOSYS_TVDB_PROXY_URL", "https://dakosys-tvdb.dakosys.workers.dev"
)

STREAMING_NETWORKS = {
    "netflix", "disney+", "hulu", "max", "hbo max", "apple tv", "apple tv+",
    "prime video", "amazon prime video", "paramount+", "peacock", "amc+",
    "starz", "showtime", "crunchyroll", "stan", "britbox", "acorn tv",
    "shudder", "youtube", "paramount+ with showtime",
}

STREAMING_TIMEZONE = "America/New_York"

COUNTRY_TIMEZONES = {
    "usa": "America/New_York", "can": "America/Toronto", "gbr": "Europe/London",
    "jpn": "Asia/Tokyo", "kor": "Asia/Seoul", "aus": "Australia/Sydney",
    "nzl": "Pacific/Auckland", "deu": "Europe/Berlin", "fra": "Europe/Paris",
    "esp": "Europe/Madrid", "ita": "Europe/Rome", "irl": "Europe/Dublin",
    "swe": "Europe/Stockholm", "nor": "Europe/Oslo", "dnk": "Europe/Copenhagen",
    "fin": "Europe/Helsinki", "nld": "Europe/Amsterdam", "bel": "Europe/Brussels",
    "ukr": "Europe/Kyiv", "rus": "Europe/Moscow", "pol": "Europe/Warsaw",
    "bra": "America/Sao_Paulo", "mex": "America/Mexico_City", "ind": "Asia/Kolkata",
    "chn": "Asia/Shanghai", "twn": "Asia/Taipei", "isr": "Asia/Jerusalem",
    "tur": "Europe/Istanbul", "zaf": "Africa/Johannesburg", "cze": "Europe/Prague",
    "arg": "America/Argentina/Buenos_Aires", "aut": "Europe/Vienna",
    "che": "Europe/Zurich", "hkg": "Asia/Hong_Kong", "sgp": "Asia/Singapore",
    "tha": "Asia/Bangkok", "phl": "Asia/Manila", "idn": "Asia/Jakarta",
    "col": "America/Bogota", "chl": "America/Santiago", "isl": "Atlantic/Reykjavik",
    "prt": "Europe/Lisbon", "hun": "Europe/Budapest", "rou": "Europe/Bucharest",
    "grc": "Europe/Athens", "bgr": "Europe/Sofia", "hrv": "Europe/Zagreb",
    "srb": "Europe/Belgrade", "svk": "Europe/Bratislava", "svn": "Europe/Ljubljana",
    "ltu": "Europe/Vilnius", "lva": "Europe/Riga", "est": "Europe/Tallinn",
    "mda": "Europe/Chisinau", "blr": "Europe/Minsk", "bih": "Europe/Sarajevo",
    "mkd": "Europe/Skopje", "alb": "Europe/Tirane", "mne": "Europe/Podgorica",
    "cyp": "Asia/Nicosia", "mlt": "Europe/Malta", "lux": "Europe/Luxembourg",
    "vnm": "Asia/Ho_Chi_Minh", "mys": "Asia/Kuala_Lumpur", "pak": "Asia/Karachi",
    "bgd": "Asia/Dhaka", "lka": "Asia/Colombo", "npl": "Asia/Kathmandu",
    "sau": "Asia/Riyadh", "are": "Asia/Dubai", "qat": "Asia/Qatar",
    "egy": "Africa/Cairo", "mar": "Africa/Casablanca", "nga": "Africa/Lagos",
    "ken": "Africa/Nairobi", "per": "America/Lima", "ven": "America/Caracas",
    "ury": "America/Montevideo", "cri": "America/Costa_Rica", "pri": "America/Puerto_Rico",
    "dom": "America/Santo_Domingo", "cub": "America/Havana", "geo": "Asia/Tbilisi",
    "arm": "Asia/Yerevan", "aze": "Asia/Baku", "kaz": "Asia/Almaty",
}

EPISODE_PAGE_SCAN = 2

FINALE_TYPES = {
    "series": "series_finale",
    "season": "season_finale",
    "midseason": "mid_season_finale",
}

_token = None
_token_lock = threading.Lock()
_series_cache = {}
_tvdb_id_cache = {}


def _login(api_key):
    """Exchange an API key for a bearer token."""
    try:
        response = requests.post(
            f"{TVDB_BASE}/login", json={"apikey": api_key}, timeout=20
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"TheTVDB login failed: {e}")
        return None

    if response.status_code != 200:
        logger.error(f"TheTVDB login rejected the API key (HTTP {response.status_code})")
        return None

    try:
        return response.json()["data"]["token"]
    except (ValueError, KeyError):
        logger.error("TheTVDB login returned an unexpected response")
        return None


def verify_api_key(api_key):
    """Return True when the API key authenticates against TheTVDB."""
    return _login(api_key) is not None


def _request(path, api_key, params=None, max_retries=4, full=False):
    global _token
    wait = 3
    for attempt in range(max_retries):
        with _token_lock:
            if _token is None:
                _token = _login(api_key)
            token = _token
        if not token:
            return None

        try:
            response = requests.get(
                f"{TVDB_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=20,
            )
        except requests.exceptions.RequestException as e:
            logger.warning(f"TheTVDB request failed for {path} (attempt {attempt + 1}): {e}")
            time.sleep(wait)
            wait = min(wait * 2, 30)
            continue

        if response.status_code == 200:
            try:
                body = response.json()
            except ValueError:
                return None
            return body if full else body.get("data")
        if response.status_code == 401:
            with _token_lock:
                _token = None
            continue
        if response.status_code == 404:
            return None
        if response.status_code == 429:
            retry_after = 5
            try:
                retry_after = int(response.headers.get("Retry-After", retry_after))
            except (ValueError, TypeError):
                pass
            logger.warning(f"TheTVDB rate limited {path}, waiting {retry_after}s")
            time.sleep(retry_after)
            continue

        logger.error(f"TheTVDB HTTP {response.status_code} for {path}")
        return None
    return None


def resolve_tvdb_id(tmdb_id, tmdb_api_key):
    """Map a TMDB show id to a TheTVDB series id, or None."""
    if tmdb_id in _tvdb_id_cache:
        return _tvdb_id_cache[tmdb_id]

    tvdb_id = None
    try:
        response = requests.get(
            f"{TMDB_BASE}/tv/{tmdb_id}/external_ids",
            params={"api_key": tmdb_api_key},
            timeout=20,
        )
        if response.status_code == 200:
            tvdb_id = response.json().get("tvdb_id")
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.warning(f"Could not resolve TheTVDB id for TMDB {tmdb_id}: {e}")

    _tvdb_id_cache[tmdb_id] = tvdb_id
    return tvdb_id


def _series_extended(tvdb_id, api_key):
    if tvdb_id not in _series_cache:
        _series_cache[tvdb_id] = _request(
            f"/series/{tvdb_id}/extended", api_key, params={"short": "true"}
        )
    return _series_cache[tvdb_id]


def _series_timezone(series):
    """Return the timezone a series' air time is expressed in."""
    for key in ("latestNetwork", "originalNetwork"):
        name = ((series.get(key) or {}).get("name") or "").strip().lower()
        if name in STREAMING_NETWORKS:
            return STREAMING_TIMEZONE

    country = (series.get("originalCountry") or series.get("country") or "").strip().lower()
    return COUNTRY_TIMEZONES.get(country)


def _to_utc(aired, airs_time, timezone_name):
    """Combine a calendar date and broadcast time into a UTC timestamp."""
    if not aired or not airs_time or not timezone_name:
        return None
    try:
        naive = datetime.strptime(f"{aired} {airs_time}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return None
    try:
        localized = pytz.timezone(timezone_name).localize(naive)
    except Exception as e:
        logger.warning(f"Could not localize {aired} {airs_time} to {timezone_name}: {e}")
        return None
    return localized.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_episode(tvdb_id, api_key):
    """Return the earliest unaired episode, ignoring specials."""
    body = _request(f"/series/{tvdb_id}/episodes/default", api_key, params={"page": 0}, full=True)
    if not body:
        return None

    links = body.get("links") or {}
    page_size = links.get("page_size") or 500
    total = links.get("total_items") or 0
    last_page = max(0, (total - 1) // page_size) if page_size else 0

    today = datetime.utcnow().strftime("%Y-%m-%d")
    best = None
    for page in range(last_page, max(-1, last_page - EPISODE_PAGE_SCAN), -1):
        if page == 0:
            episodes = (body.get("data") or {}).get("episodes") or []
        else:
            result = _request(
                f"/series/{tvdb_id}/episodes/default", api_key, params={"page": page}
            )
            episodes = (result or {}).get("episodes") or []
        if not episodes:
            continue

        for episode in episodes:
            aired = (episode.get("aired") or "").strip()
            if not aired or aired < today or episode.get("seasonNumber") == 0:
                continue
            if best is None or aired < best.get("aired", ""):
                best = episode

        earliest = (episodes[0].get("aired") or "").strip()
        if earliest and earliest < today:
            break

    return best


def _derive_air_details(series, episode):
    """Turn a series record and its next episode into (utc_timestamp, episode_type)."""
    if not series or not episode:
        return None, None

    aired = (episode.get("aired") or "").strip()
    if not aired:
        return None, None

    timestamp = _to_utc(aired, series.get("airsTime"), _series_timezone(series))
    episode_type = FINALE_TYPES.get((episode.get("finaleType") or "").strip().lower())
    return timestamp, episode_type


def _proxy_series(tvdb_id, proxy_url):
    """Fetch a series record and its next episode through the DAKOSYS proxy."""
    try:
        response = requests.get(
            f"{proxy_url.rstrip('/')}/v1/airing",
            params={"tvdb_id": tvdb_id},
            timeout=20,
        )
    except requests.exceptions.RequestException as e:
        logger.warning(f"TheTVDB proxy unreachable for {tvdb_id}: {e}")
        return None, None

    if response.status_code != 200:
        logger.warning(f"TheTVDB proxy returned HTTP {response.status_code} for {tvdb_id}")
        return None, None

    try:
        data = response.json() or {}
    except ValueError:
        logger.warning(f"TheTVDB proxy returned malformed JSON for {tvdb_id}")
        return None, None

    return data.get("series"), data.get("episode")


def get_air_details(tmdb_id, tvdb_api_key, tmdb_api_key):
    """Return (utc_timestamp, episode_type) for a series' next episode."""
    tvdb_id = resolve_tvdb_id(tmdb_id, tmdb_api_key)
    if not tvdb_id:
        return None, None

    if not tvdb_api_key:
        if not PROXY_URL:
            return None, None
        return _derive_air_details(*_proxy_series(tvdb_id, PROXY_URL))

    series = _series_extended(tvdb_id, tvdb_api_key)
    if not series:
        return None, None

    return _derive_air_details(series, _next_episode(tvdb_id, tvdb_api_key))
