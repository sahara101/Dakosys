#!/usr/bin/env python3
"""TMDB metadata provider for DAKOSYS."""

import logging

import requests

logger = logging.getLogger("tmdb_metadata")

TMDB_BASE = "https://api.themoviedb.org/3"
TVMAZE_BASE = "https://api.tvmaze.com"

ENDED_STATUSES = {"ended"}
CANCELED_STATUSES = {"canceled", "cancelled"}

_tvmaze_id_cache = {}


def _get(url, params=None, timeout=20, max_retries=4):
    wait = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                return response
            if response.status_code == 404:
                return None
            if response.status_code == 429:
                retry_after = 5
                try:
                    retry_after = int(response.headers.get("Retry-After", retry_after))
                except (ValueError, TypeError):
                    pass
                logger.warning(f"Rate limited on {url}, waiting {retry_after}s")
                import time
                time.sleep(retry_after)
                continue
            logger.error(f"HTTP {response.status_code} for {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed for {url} (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(wait)
                wait = min(wait * 2, 30)
    return None


def _normalize_status(tmdb_status):
    status = (tmdb_status or "").strip().lower()
    if status in ENDED_STATUSES:
        return "ended"
    if status in CANCELED_STATUSES:
        return "canceled"
    return "returning"


def _normalize_episode_type(next_episode):
    episode_type = (next_episode.get("episode_type") or "").strip().lower()
    try:
        episode_number = int(next_episode.get("episode_number"))
    except (TypeError, ValueError):
        episode_number = None

    if episode_type == "mid_season":
        return "mid_season_finale"
    if episode_type == "finale":
        return "season_finale"
    if episode_number == 1:
        return "season_premiere"
    return "standard"


def _tvmaze_airstamp(tmdb_id, api_key, season_number, episode_number):
    """Look up a real UTC air timestamp from TVmaze, or None."""
    if tmdb_id in _tvmaze_id_cache:
        tvmaze_id = _tvmaze_id_cache[tmdb_id]
    else:
        tvmaze_id = None
        external = _get(f"{TMDB_BASE}/tv/{tmdb_id}/external_ids", params={"api_key": api_key})
        if external:
            ids = external.json()
            for param, value in (("imdb", ids.get("imdb_id")), ("thetvdb", ids.get("tvdb_id"))):
                if not value:
                    continue
                lookup = _get(f"{TVMAZE_BASE}/lookup/shows", params={param: value})
                if lookup:
                    try:
                        tvmaze_id = lookup.json().get("id")
                    except ValueError:
                        tvmaze_id = None
                if tvmaze_id:
                    break
        _tvmaze_id_cache[tmdb_id] = tvmaze_id

    if not tvmaze_id:
        return None

    response = _get(f"{TVMAZE_BASE}/shows/{tvmaze_id}", params={"embed": "nextepisode"})
    if not response:
        return None
    try:
        episode = (response.json().get("_embedded") or {}).get("nextepisode") or {}
    except ValueError:
        return None

    if not episode.get("airstamp"):
        return None

    tvmaze_season = episode.get("season")
    tvmaze_number = episode.get("number")
    if season_number is not None and tvmaze_season is not None and tvmaze_season != season_number:
        return None
    if episode_number is not None and tvmaze_number is not None and tvmaze_number != episode_number:
        return None
    return episode["airstamp"]


def apply_tvmaze_airstamp(record, tmdb_id, api_key):
    """Upgrade a date-only record with TVmaze's air instant, if it has one."""
    if not record or not record.get("first_aired") or not record.get("date_only"):
        return False

    airstamp = _tvmaze_airstamp(
        tmdb_id, api_key, record.get("season_number"), record.get("episode_number")
    )
    if not airstamp:
        return False

    record["first_aired"] = airstamp
    record["date_only"] = False
    return True


def get_show_metadata(tmdb_id, api_key, use_tvmaze=True):
    """Return normalized status and next-airing data for a TMDB show id."""
    response = _get(f"{TMDB_BASE}/tv/{tmdb_id}", params={"api_key": api_key})
    if not response:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    status = _normalize_status(data.get("status"))
    record = {
        "status": status,
        "first_aired": None,
        "date_only": True,
        "episode_type": "standard",
        "season_number": None,
        "episode_number": None,
    }

    next_episode = data.get("next_episode_to_air")
    if status != "returning" or not next_episode or not next_episode.get("air_date"):
        return record

    try:
        record["season_number"] = int(next_episode.get("season_number"))
    except (TypeError, ValueError):
        record["season_number"] = None
    try:
        record["episode_number"] = int(next_episode.get("episode_number"))
    except (TypeError, ValueError):
        record["episode_number"] = None

    record["episode_type"] = _normalize_episode_type(next_episode)
    record["first_aired"] = next_episode["air_date"]

    if use_tvmaze:
        airstamp = _tvmaze_airstamp(tmdb_id, api_key, record["season_number"], record["episode_number"])
        if airstamp:
            record["first_aired"] = airstamp
            record["date_only"] = False

    return record
