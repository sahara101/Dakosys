#!/usr/bin/env python3
"""
FastAPI web server for DAKOSYS dashboard.
Serves the static Next.js frontend and provides API endpoints.
"""

import os
import json
import copy
import shutil
import threading
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

IN_DOCKER = os.environ.get("RUNNING_IN_DOCKER") == "true"

if IN_DOCKER:
    CONFIG_FILE = "/app/config/config.yaml"
    DATA_DIR = "/app/data"
    WEB_OUT = "/app/web/out"
else:
    CONFIG_FILE = "config/config.yaml"
    DATA_DIR = "data"
    WEB_OUT = "web/out"

LOG_FILE = os.path.join(DATA_DIR, "anime_trakt_manager.log")
TV_STATUS_CACHE = os.path.join(DATA_DIR, "tv_status_cache.json")
NEXT_AIRING_DATA = os.path.join(DATA_DIR, "next_airing.json")
PREVIOUS_SIZES_FILE = os.path.join(DATA_DIR, "previous_sizes.json")


def _expand_status(data: Dict[str, Any]) -> str:
    """Convert abbreviated cache status codes to full status keys."""
    code = data.get("status", "UNKNOWN").upper()
    text = data.get("text", "").upper()
    if code == "R":
        return "RETURNING"
    if code == "E":
        return "ENDED"
    if code == "C":
        return "CANCELLED"
    if code == "SEASON":
        return "SEASON_PREMIERE" if "PREMIERE" in text else "SEASON_FINALE"
    if code == "MID":
        return "MID_SEASON_FINALE"
    if code == "FINAL":
        return "FINAL_EPISODE"
    return code

SECRETS_PATHS = [
    ["tmdb_api_key"],
    ["plex", "token"],
    ["trakt", "client_id"],
    ["trakt", "client_secret"],
    ["trakt", "access_token"],
    ["trakt", "refresh_token"],
    ["notifications", "discord", "webhook_url"],
]
MASKED = "***MASKED***"

run_status: Dict[str, bool] = {
    "anime_episode_type": False,
    "tv_status_tracker": False,
    "size_overlay": False,
}

app = FastAPI(title="DAKOSYS Dashboard API", docs_url="/api/docs", redoc_url=None)

def load_config() -> Optional[dict]:
    """Load configuration from YAML file, return None on failure."""
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def mask_secrets(config: dict) -> dict:
    """Return a deep copy of config with secret values replaced by MASKED."""
    masked = copy.deepcopy(config)
    for path in SECRETS_PATHS:
        node = masked
        for key in path[:-1]:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                node = None
                break
        if node and isinstance(node, dict) and path[-1] in node:
            node[path[-1]] = MASKED
    return masked


def compute_next_run(schedule_config: dict) -> Optional[str]:
    """Compute the next ISO-8601 run time from a scheduler config block."""
    if not schedule_config:
        return None
    schedule_type = schedule_config.get("type", "daily").lower()
    now = datetime.now()

    try:
        if schedule_type == "run":
            return None

        if schedule_type == "hourly":
            minute = int(schedule_config.get("minute", 0))
            candidate = now.replace(second=0, microsecond=0, minute=minute)
            if candidate <= now:
                candidate += timedelta(hours=1)
            return candidate.isoformat()

        if schedule_type == "daily":
            times = schedule_config.get("times", ["03:00"])
            if isinstance(times, str):
                times = [times]
            candidates = []
            for t in times:
                h, m = map(int, t.split(":"))
                c = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if c <= now:
                    c += timedelta(days=1)
                candidates.append(c)
            return min(candidates).isoformat() if candidates else None

        if schedule_type == "weekly":
            days_map = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6,
            }
            days = schedule_config.get("days", ["monday"])
            if isinstance(days, str):
                days = [days]
            time_str = schedule_config.get("time", "03:00")
            h, m = map(int, time_str.split(":"))
            candidates = []
            for day in days:
                target_wd = days_map.get(day.lower(), 0)
                days_ahead = (target_wd - now.weekday()) % 7
                c = (now + timedelta(days=days_ahead)).replace(
                    hour=h, minute=m, second=0, microsecond=0
                )
                if c <= now:
                    c += timedelta(weeks=1)
                candidates.append(c)
            return min(candidates).isoformat() if candidates else None

        if schedule_type == "monthly":
            dates = schedule_config.get("dates", [1])
            if isinstance(dates, int):
                dates = [dates]
            time_str = schedule_config.get("time", "03:00")
            h, m = map(int, time_str.split(":"))
            candidates = []
            for date in dates:
                try:
                    c = now.replace(day=int(date), hour=h, minute=m, second=0, microsecond=0)
                    if c <= now:
                        if now.month == 12:
                            c = c.replace(year=now.year + 1, month=1)
                        else:
                            c = c.replace(month=now.month + 1)
                    candidates.append(c)
                except ValueError:
                    pass
            return min(candidates).isoformat() if candidates else None

        if schedule_type == "cron":
            expression = schedule_config.get("expression", "0 3 * * *")
            parts = expression.split()
            if len(parts) >= 5 and parts[0].isdigit() and parts[1].isdigit():
                h, minute = int(parts[1]), int(parts[0])
                c = now.replace(hour=h, minute=minute, second=0, microsecond=0)
                if c <= now:
                    c += timedelta(days=1)
                return c.isoformat()

    except Exception:
        pass

    return None

@app.get("/api/status")
def get_status():
    """Service health, next scheduled runs, and summary stats."""
    config = load_config()
    services_info: Dict[str, Any] = {}

    for svc in ("anime_episode_type", "tv_status_tracker", "size_overlay"):
        enabled = False
        next_run = None
        if config:
            enabled = bool(config.get("services", {}).get(svc, {}).get("enabled", False))
            if enabled:
                sched_cfg = config.get("scheduler", {}).get(svc, {})
                next_run = compute_next_run(sched_cfg)
        services_info[svc] = {
            "enabled": enabled,
            "running": run_status.get(svc, False),
            "next_run": next_run,
        }

    total_shows = 0
    total_size_gb = 0.0
    total_libraries = 0

    if os.path.exists(TV_STATUS_CACHE):
        try:
            with open(TV_STATUS_CACHE, "r") as f:
                total_shows = len(json.load(f))
        except Exception:
            pass

    if os.path.exists(PREVIOUS_SIZES_FILE):
        try:
            with open(PREVIOUS_SIZES_FILE, "r") as f:
                sizes = json.load(f)
            total_libraries = len(sizes)
            total_size_gb = sum(
                lib.get("total_size", 0)
                for lib in sizes.values()
                if isinstance(lib, dict)
            )
        except Exception:
            pass

    return {
        "services": services_info,
        "stats": {
            "total_shows": total_shows,
            "total_libraries": total_libraries,
            "total_size_gb": round(total_size_gb, 2),
        },
        "config_missing": not os.path.exists(CONFIG_FILE),
    }


@app.get("/api/tv-status")
def get_tv_status():
    """All shows from tv_status_cache.json."""
    if not os.path.exists(TV_STATUS_CACHE):
        return {"shows": []}
    try:
        with open(TV_STATUS_CACHE, "r") as f:
            cache = json.load(f)
        shows = [
            {
                "title": title,
                "status": _expand_status(data),
                "date": data.get("date", ""),
                "text": data.get("text", ""),
            }
            for title, data in cache.items()
        ]
        return {"shows": sorted(shows, key=lambda s: s["title"].lower())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/libraries")
def get_libraries():
    """All library data from previous_sizes.json."""
    if not os.path.exists(PREVIOUS_SIZES_FILE):
        return {"libraries": []}
    try:
        with open(PREVIOUS_SIZES_FILE, "r") as f:
            data = json.load(f)
        libraries = []
        for lib_name, lib_data in data.items():
            if not isinstance(lib_data, dict):
                continue
            items_dict = lib_data.get("items", {})
            episodes_dict = lib_data.get("episodes", {})
            items: List[Dict] = []
            for title, size in items_dict.items():
                item: Dict[str, Any] = {
                    "title": title,
                    "size_gb": round(float(size), 2),
                }
                if title in episodes_dict:
                    item["episode_count"] = episodes_dict[title]
                items.append(item)
            items.sort(key=lambda x: x["size_gb"], reverse=True)
            import re as _re
            display_name = _re.sub(r'^[a-zA-Z]+:', '', lib_name).strip() or lib_name
            libraries.append({
                "name": display_name,
                "total_size_gb": round(lib_data.get("total_size", 0), 2),
                "item_count": len(items),
                "episode_count": sum(episodes_dict.values()) if episodes_dict else None,
                "last_updated": lib_data.get("last_updated", ""),
                "items": items,
            })
        return {"libraries": libraries}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config")
def get_config():
    """Return config.yaml with secrets masked."""
    config = load_config()
    if config is None:
        return {"config": "", "error": "Config file not found"}
    masked = mask_secrets(config)
    return {"config": yaml.dump(masked, default_flow_style=False, allow_unicode=True)}


@app.get("/api/config/export")
def export_config():
    """Download config.yaml as a file (secrets included — handle with care)."""
    if not os.path.exists(CONFIG_FILE):
        raise HTTPException(status_code=404, detail="Config file not found")
    return FileResponse(CONFIG_FILE, media_type="application/x-yaml", filename="config.yaml")


class ConfigPayload(BaseModel):
    config: str


@app.put("/api/config")
def update_config(payload: ConfigPayload):
    """Write config.yaml — masked secrets are automatically restored from the current config."""
    try:
        parsed = yaml.safe_load(payload.config)
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="Invalid YAML: expected a mapping.")

        if MASKED in payload.config:
            current = load_config() or {}
            for path in SECRETS_PATHS:
                parsed_node = parsed
                current_node = current
                for key in path[:-1]:
                    if not isinstance(parsed_node, dict) or key not in parsed_node:
                        parsed_node = None
                        break
                    current_node = current_node.get(key, {}) if isinstance(current_node, dict) else {}
                    parsed_node = parsed_node[key]
                if parsed_node is None:
                    continue
                last_key = path[-1]
                if isinstance(parsed_node, dict) and parsed_node.get(last_key) == MASKED:
                    real_val = current_node.get(last_key) if isinstance(current_node, dict) else None
                    if real_val and real_val != MASKED:
                        parsed_node[last_key] = real_val
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Secret '{'.'.join(path)}' is masked and cannot be recovered — please enter the real value before saving.",
                        )

        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

        tmp_path = CONFIG_FILE + ".tmp"
        bak_path = CONFIG_FILE + ".bak"

        with open(tmp_path, "w") as f:
            yaml.dump(parsed, f, default_flow_style=False, allow_unicode=True)

        if os.path.exists(CONFIG_FILE):
            shutil.copy2(CONFIG_FILE, bak_path)

        os.replace(tmp_path, CONFIG_FILE)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_LOG_SERVICES = {
    "main": LOG_FILE,
    "anime_episode_type": LOG_FILE,
    "tv_status_tracker": os.path.join(DATA_DIR, "tv_status_tracker.log"),
    "size_overlay": os.path.join(DATA_DIR, "size_overlay.log"),
}


@app.get("/api/logs/{service}")
def get_logs(service: str, lines: int = 200):
    """Return last N lines of the service log."""
    log_path = _LOG_SERVICES.get(service)
    if log_path is None:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service}")
    if not os.path.exists(log_path):
        return {"lines": [], "service": service}
    try:
        with open(log_path, "r", errors="replace") as f:
            all_lines = f.readlines()
        return {"lines": [ln.rstrip() for ln in all_lines[-lines:]], "service": service}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_VALID_SERVICES = {"anime_episode_type", "tv_status_tracker", "size_overlay"}


@app.post("/api/run/{service}")
def trigger_run(service: str):
    """Trigger a manual run of the given service in a background thread."""
    if service not in _VALID_SERVICES:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service}")
    if run_status.get(service):
        return {"started": False, "message": f"{service} is already running"}

    def _run():
        import logging as _logging
        _log = _logging.getLogger("anime_trakt_manager")
        run_status[service] = True
        try:
            import anime_trakt_manager as _atm
            _atm.load_config()
            from auto_update import run_update
            run_update([service])
        except Exception as exc:
            import traceback as _tb
            _log.error(f"Manual run of '{service}' failed: {exc}\n{_tb.format_exc()}")
        finally:
            run_status[service] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "message": f"{service} started"}


@app.get("/api/run/{service}/status")
def get_run_status(service: str):
    """Check whether a service manual run is in progress."""
    if service not in _VALID_SERVICES:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service}")
    return {"service": service, "running": run_status.get(service, False)}


class ServiceEnabledPayload(BaseModel):
    enabled: bool


@app.put("/api/services/{service}")
def set_service_enabled(service: str, payload: ServiceEnabledPayload):
    """Enable or disable a service in config.yaml."""
    if service not in _VALID_SERVICES:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service}")
    config = load_config()
    if not config:
        raise HTTPException(status_code=500, detail="Config file not found")
    config.setdefault("services", {}).setdefault(service, {})["enabled"] = payload.enabled
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        tmp_path = CONFIG_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        if os.path.exists(CONFIG_FILE):
            shutil.copy2(CONFIG_FILE, CONFIG_FILE + ".bak")
        os.replace(tmp_path, CONFIG_FILE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "service": service, "enabled": payload.enabled}


@app.get("/api/anime-schedule")
def get_anime_schedule():
    """Return the scheduled anime list with display names from config."""
    config = load_config()
    if not config:
        return {"anime": [], "count": 0}

    scheduled = config.get("scheduler", {}).get("scheduled_anime", [])
    mappings = config.get("mappings", {})

    mappings_file = os.path.join(os.path.dirname(CONFIG_FILE), "mappings.yaml")
    if os.path.exists(mappings_file):
        try:
            with open(mappings_file, "r") as f:
                mdata = yaml.safe_load(f) or {}
            mappings = {**mdata.get("mappings", {}), **mappings}
        except Exception:
            pass

    anime_list = []
    for afl_name in scheduled:
        plex_name = mappings.get(afl_name, afl_name)
        display_name = plex_name if plex_name != afl_name else afl_name.replace("-", " ").title()
        anime_list.append({
            "afl_name": afl_name,
            "display_name": display_name,
        })

    return {"anime": anime_list, "count": len(anime_list)}

_DAKOSYS_SUFFIXES = ["_filler", "_manga canon", "_anime canon", "_mixed canon/filler"]

sync_running: bool = False

anime_run_status: Dict[str, bool] = {}
anime_run_errors: Dict[str, Optional[str]] = {}  # None = success, str = error message

_tmdb_poster_cache: Dict[int, str] = {}


def _load_all_mappings(config: dict) -> dict:
    """Return merged mappings from config + mappings.yaml."""
    mappings = dict(config.get("mappings", {}))
    mappings_file = os.path.join(os.path.dirname(CONFIG_FILE), "mappings.yaml")
    if os.path.exists(mappings_file):
        try:
            with open(mappings_file, "r") as f:
                mdata = yaml.safe_load(f) or {}
            mappings = {**mdata.get("mappings", {}), **mappings}
        except Exception:
            pass
    return mappings


def _fetch_tmdb_poster(tmdb_id: int, api_key: str) -> Optional[str]:
    """Fetch and cache a TMDB poster URL for a single show."""
    if tmdb_id in _tmdb_poster_cache:
        return _tmdb_poster_cache[tmdb_id]
    try:
        import requests as _req
        resp = _req.get(
            f"https://api.themoviedb.org/3/tv/{tmdb_id}",
            params={"api_key": api_key, "language": "en-US"},
            timeout=5,
        )
        if resp.status_code == 200:
            poster_path = resp.json().get("poster_path")
            if poster_path:
                url = f"https://image.tmdb.org/t/p/w342{poster_path}"
                _tmdb_poster_cache[tmdb_id] = url
                return url
    except Exception:
        pass
    return None


def _next_airing_from_local(tmdb_api_key: str):
    """Build the Next Airing response from the tracker's local data file."""
    try:
        with open(NEXT_AIRING_DATA, "r") as f:
            records = json.load(f)
    except Exception:
        return None

    if not isinstance(records, list):
        return None

    import concurrent.futures as _cf

    tmdb_ids_to_fetch = [
        r.get("tmdb_id") for r in records
        if r.get("tmdb_id") and r.get("tmdb_id") not in _tmdb_poster_cache
    ]

    if tmdb_ids_to_fetch:
        with _cf.ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(lambda tid: _fetch_tmdb_poster(tid, tmdb_api_key), tmdb_ids_to_fetch))

    shows = []
    for record in records:
        tmdb_id = record.get("tmdb_id")
        shows.append({
            "rank": record.get("rank", 0),
            "title": record.get("title", ""),
            "tmdb_id": tmdb_id,
            "trakt_slug": "",
            "trakt_id": record.get("trakt_id"),
            "poster_url": _tmdb_poster_cache.get(tmdb_id) if tmdb_id else None,
            "status": str(record.get("status") or "UNKNOWN").upper(),
            "date": record.get("date", ""),
            "text": record.get("text", ""),
        })

    shows.sort(key=lambda s: s["rank"])
    return {"shows": shows, "count": len(shows)}


@app.get("/api/tv-status/next-airing")
def get_next_airing():
    """Fetch the ordered 'Next Airing' list with TMDB posters and status info."""
    config = load_config()
    if not config:
        return {"shows": [], "count": 0, "error": "Config file not found"}

    tmdb_api_key = config.get("tmdb_api_key", "").strip()
    if not tmdb_api_key:
        return {"shows": [], "count": 0, "tmdb_key_missing": True}

    if os.path.exists(NEXT_AIRING_DATA):
        local_result = _next_airing_from_local(tmdb_api_key)
        if local_result is not None:
            return local_result

    username = config.get("trakt", {}).get("username")
    if not username:
        return {"shows": [], "count": 0, "error": "Trakt username not configured"}

    try:
        import trakt_auth as _ta
        import concurrent.futures as _cf

        import requests as _req2
        _headers = _ta.get_trakt_headers()
        _r = _req2.get("https://api.trakt.tv/users/me/lists/next-airing/items",
                       headers=_headers, params={"limit": 1000}, timeout=15)
        if _r.status_code == 404:
            return {"shows": [], "count": 0, "error": "Next Airing list not found on Trakt — run the TV Status Tracker to create it"}
        if _r.status_code != 200:
            return {"shows": [], "count": 0, "error": f"Trakt API error {_r.status_code} — check Trakt auth"}
        items = _r.json()

        import re as _re

        def _norm_title(t: str) -> str:
            t = t.lower().strip()
            t = _re.sub(r"\s*\(\d{4}\)\s*$", "", t)
            t = _re.sub(r"\s*\([a-z]{2,4}\)\s*$", "", t)
            return t.strip()

        status_map: Dict[str, Any] = {}
        norm_status_map: Dict[str, Any] = {}
        if os.path.exists(TV_STATUS_CACHE):
            try:
                with open(TV_STATUS_CACHE, "r") as f:
                    cache = json.load(f)
                for title, data in cache.items():
                    status_map[title.lower()] = data
                    norm_key = _norm_title(title)
                    if norm_key not in norm_status_map:
                        norm_status_map[norm_key] = data
            except Exception:
                pass

        def _find_status(trakt_title: str, year: int = None) -> Dict[str, Any]:
            if year:
                year_key = f"{trakt_title.lower()} ({year})"
                if year_key in status_map:
                    return status_map[year_key]
            key = trakt_title.lower()
            if key in status_map:
                return status_map[key]
            norm = _norm_title(trakt_title)
            if norm in norm_status_map:
                return norm_status_map[norm]
            if norm in status_map:
                return status_map[norm]
            return {}

        show_items = [i for i in items if i.get("type") == "show"]
        tmdb_ids_to_fetch = [
            i["show"]["ids"]["tmdb"]
            for i in show_items
            if i["show"]["ids"].get("tmdb") and i["show"]["ids"]["tmdb"] not in _tmdb_poster_cache
        ]

        if tmdb_ids_to_fetch:
            with _cf.ThreadPoolExecutor(max_workers=10) as pool:
                list(pool.map(lambda tid: _fetch_tmdb_poster(tid, tmdb_api_key), tmdb_ids_to_fetch))

        shows = []
        for item in show_items:
            show_data = item.get("show", {})
            title = show_data.get("title", "")
            year = show_data.get("year")
            tmdb_id = show_data.get("ids", {}).get("tmdb")
            status_data = _find_status(title, year)
            shows.append({
                "rank": item.get("rank", 0),
                "title": title,
                "tmdb_id": tmdb_id,
                "trakt_slug": show_data.get("ids", {}).get("slug", ""),
                "trakt_id": show_data.get("ids", {}).get("trakt"),
                "poster_url": _tmdb_poster_cache.get(tmdb_id) if tmdb_id else None,
                "status": _expand_status(status_data) if status_data else "UNKNOWN",
                "date": status_data.get("date", ""),
                "text": status_data.get("text", ""),
            })

        shows.sort(key=lambda s: s["rank"])
        return {"shows": shows, "count": len(shows)}

    except Exception as e:
        return {"shows": [], "count": 0, "error": str(e)}


@app.get("/api/trakt/test")
def test_trakt_connection():
    """Diagnose Trakt connection: token status, authenticated user, and list access."""
    import time, requests as _req

    result = {
        "config_ok": False,
        "config_username": None,
        "token_exists": False,
        "token_has_refresh": False,
        "token_expires_in_days": None,
        "auth_ok": False,
        "authenticated_username": None,
        "username_match": None,
        "total_lists": None,
        "dakosys_lists": None,
        "error": None,
    }

    config = load_config()
    if not config:
        result["error"] = "Config file not found"
        return result

    result["config_ok"] = True
    result["config_username"] = config.get("trakt", {}).get("username")

    try:
        import trakt_auth as _ta
        import os as _os

        token_file = _os.path.join(_ta.get_data_dir(), "trakt_token.json")
        result["token_exists"] = _os.path.exists(token_file)

        if result["token_exists"]:
            access_token, refresh_token, created_at, expires_in = _ta.get_stored_trakt_tokens()
            result["token_has_refresh"] = bool(refresh_token)
            current_time = int(time.time())
            if created_at and expires_in:
                remaining = (created_at + expires_in) - current_time
                result["token_expires_in_days"] = round(remaining / 86400, 1)

        live_token = _ta.ensure_trakt_auth(quiet=True)
        if not live_token:
            result["error"] = "Authentication failed — no valid access token"
            return result

        result["auth_ok"] = True
        headers = _ta.get_trakt_headers(live_token)

        me_resp = _req.get("https://api.trakt.tv/users/me", headers=headers, timeout=10)
        if me_resp.status_code == 200:
            result["authenticated_username"] = me_resp.json().get("username")
            result["username_match"] = result["authenticated_username"] == result["config_username"]
        else:
            result["error"] = f"/users/me HTTP {me_resp.status_code}"
            return result

        username = result["config_username"]
        lists_resp = _req.get(
            "https://api.trakt.tv/users/me/lists",
            headers=headers, timeout=10, params={"limit": 1000}
        )
        if lists_resp.status_code == 200:
            all_lists = lists_resp.json()
            suffixes = ["_filler", "_manga canon", "_anime canon", "_mixed canon/filler"]
            dakosys = [l for l in all_lists if any(l.get("name", "").endswith(s) for s in suffixes)]
            result["total_lists"] = len(all_lists)
            result["dakosys_lists"] = len(dakosys)
        else:
            result["error"] = f"/users/me/lists HTTP {lists_resp.status_code}: {lists_resp.text[:200]}"

    except Exception as e:
        result["error"] = str(e)

    return result


@app.get("/api/trakt/lists")
def get_trakt_lists():
    """Return all DAKOSYS Trakt lists with episode counts and mapped Plex names."""
    config = load_config()
    if not config:
        return {"lists": [], "total": 0, "error": "Config file not found"}

    username = config.get("trakt", {}).get("username")
    if not username:
        return {"lists": [], "total": 0, "error": "Trakt username not configured"}

    try:
        import trakt_auth

        all_lists = trakt_auth.make_trakt_request("users/me/lists", params={"limit": 1000})
        if all_lists is None:
            rl = trakt_auth.get_rate_limit_remaining()
            if rl > 0:
                error_msg = f"Trakt rate limited — retry in {rl:.0f}s"
            else:
                error_msg = "Failed to fetch Trakt lists — check Trakt authentication"
            return {"lists": [], "total": 0, "error": error_msg}

        mappings = _load_all_mappings(config)

        result = []
        for lst in all_lists:
            name = lst.get("name", "")
            for suffix in _DAKOSYS_SUFFIXES:
                if name.endswith(suffix):
                    anime_name = name[: -len(suffix)]
                    episode_type = suffix[1:]
                    plex_name = mappings.get(anime_name) or anime_name.replace("-", " ").title()
                    result.append(
                        {
                            "id": lst["ids"]["trakt"],
                            "name": name,
                            "anime_name": anime_name,
                            "plex_name": plex_name,
                            "episode_type": episode_type,
                            "item_count": lst.get("item_count", 0),
                        }
                    )
                    break

        return {"lists": result, "total": len(result), "error": None, "trakt_username": username}
    except Exception as e:
        return {"lists": [], "total": 0, "error": str(e)}


@app.delete("/api/trakt/lists/{list_id}")
def delete_trakt_list(list_id: int):
    """Delete a specific Trakt list by its Trakt ID."""
    config = load_config()
    if not config:
        raise HTTPException(status_code=500, detail="Config file not found")

    username = config.get("trakt", {}).get("username")
    if not username:
        raise HTTPException(status_code=400, detail="Trakt username not configured")

    try:
        import trakt_auth

        result = trakt_auth.make_trakt_request(
            f"users/me/lists/{list_id}", method="DELETE"
        )
        if result is None:
            raise HTTPException(status_code=502, detail="Failed to delete list on Trakt")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trakt/sync")
def trigger_sync():
    """Sync the Kometa collections YAML with current Trakt lists (background thread)."""
    global sync_running
    if sync_running:
        return {"started": False, "message": "Sync already in progress"}

    def _sync():
        global sync_running
        import logging as _logging
        _log = _logging.getLogger("anime_trakt_manager")
        sync_running = True
        try:
            from asset_manager import sync_anime_episode_collections
            cfg = load_config()
            if cfg:
                sync_anime_episode_collections(cfg, force_update=True)
            else:
                _log.error("Sync: failed to load config")
        except Exception as exc:
            import traceback as _tb
            _log.error(f"Collections sync failed: {exc}\n{_tb.format_exc()}")
        finally:
            sync_running = False

    threading.Thread(target=_sync, daemon=True).start()
    return {"started": True}


@app.get("/api/trakt/sync/status")
def get_sync_status():
    """Check whether a collections sync is currently running."""
    return {"running": sync_running}


@app.get("/api/plex/shows")
def get_plex_shows():
    """Return all show titles in the configured Plex anime library."""
    config = load_config()
    if not config:
        return {"shows": [], "error": "Config not found"}

    plex_cfg = config.get("plex", {})
    url = plex_cfg.get("url")
    token = plex_cfg.get("token")
    anime_libs = plex_cfg.get("libraries", {}).get("anime", [])

    if not url or not token or not anime_libs:
        return {"shows": [], "error": "Plex not fully configured (url/token/libraries.anime)"}

    try:
        from plexapi.server import PlexServer

        plex = PlexServer(url, token, timeout=15)
        section = plex.library.section(anime_libs[0])
        shows = sorted(show.title for show in section.all())
        return {"shows": shows, "error": None}
    except Exception as e:
        return {"shows": [], "error": str(e)}


@app.post("/api/run/anime/{afl_name}")
def trigger_anime_run(afl_name: str):
    """Trigger a create-all update for a single scheduled anime."""
    if anime_run_status.get(afl_name):
        return {"started": False, "message": f"Already running for {afl_name}"}

    def _run():
        import logging as _logging
        import traceback as _tb
        _log = _logging.getLogger("anime_trakt_manager")
        anime_run_status[afl_name] = True
        try:
            import auto_update as _au
            import anime_trakt_manager as _atm
            _au.load_config()
            _atm.load_config()
            if _au.CONFIG:
                original = list(_au.CONFIG.get("scheduler", {}).get("scheduled_anime", []))
                _au.CONFIG.setdefault("scheduler", {})["scheduled_anime"] = [afl_name]
                try:
                    _au.run_anime_episode_update()
                finally:
                    if _au.CONFIG:
                        _au.CONFIG.setdefault("scheduler", {})["scheduled_anime"] = original
        except Exception as exc:
            _log.error(f"Per-anime create-all for '{afl_name}' failed: {exc}\n{_tb.format_exc()}")
        finally:
            anime_run_status[afl_name] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True}


@app.get("/api/run/anime/{afl_name}/status")
def get_anime_run_status(afl_name: str):
    """Check whether a per-anime create-all is in progress."""
    return {"afl_name": afl_name, "running": anime_run_status.get(afl_name, False)}

@app.get("/api/afl/search")
def search_afl(q: str = ""):
    """Search AnimeFillerList shows using AFL's own search endpoint."""
    if not q:
        return {"shows": [], "error": None}
    try:
        import requests as _req
        from bs4 import BeautifulSoup

        resp = _req.get(
            f"https://www.animefillerlist.com/search/node/{q}",
            timeout=10
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        shows: List[str] = []
        for h3 in soup.find_all("h3"):
            link = h3.find("a", href=True)
            if link:
                href = link["href"]
                if "/shows/" in href:
                    slug = href.split("/shows/")[-1].strip("/")
                    if slug and "/" not in slug:
                        shows.append(slug)

        shows = list(dict.fromkeys(shows))  # deduplicate, preserve order
        return {"shows": shows[:50], "error": None}
    except Exception as e:
        return {"shows": [], "error": str(e)}


@app.get("/api/afl/episodes/{afl_name}")
def get_afl_episode_counts(afl_name: str):
    """Return episode type counts for a specific AnimeFillerList show."""
    try:
        import requests as _req
        from bs4 import BeautifulSoup

        resp = _req.get(
            f"https://www.animefillerlist.com/shows/{afl_name}", timeout=10
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"'{afl_name}' not found on AnimeFillerList")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"AnimeFillerList returned {resp.status_code}")

        soup = BeautifulSoup(resp.text, "html.parser")
        counts: Dict[str, int] = {}
        total = 0

        for row in soup.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) >= 3:
                ep_type = cols[2].text.strip()
                if ep_type:
                    counts[ep_type] = counts.get(ep_type, 0) + 1
                    total += 1

        lower_counts = {k.lower(): v for k, v in counts.items()}
        return {"afl_name": afl_name, "counts": lower_counts, "total": total, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AddAnimePayload(BaseModel):
    afl_name: str
    plex_name: str
    add_to_schedule: bool = True


def _write_scheduled_anime(scheduled: List[str]) -> None:
    """Persist the scheduled_anime list to config.yaml (atomic write)."""
    config = load_config()
    if not config:
        raise RuntimeError("Config file not found")
    config.setdefault("scheduler", {})["scheduled_anime"] = scheduled
    config_to_save = {
        k: v for k, v in config.items()
        if k not in ("mappings", "trakt_mappings", "title_mappings")
    }
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    bak = CONFIG_FILE + ".bak"
    with open(tmp, "w") as f:
        yaml.dump(config_to_save, f, default_flow_style=False, allow_unicode=True)
    if os.path.exists(CONFIG_FILE):
        shutil.copy2(CONFIG_FILE, bak)
    os.replace(tmp, CONFIG_FILE)


@app.post("/api/anime/add")
def add_anime(payload: AddAnimePayload):
    """Save AFL→Plex mapping and optionally add anime to the scheduled list."""
    afl_name = payload.afl_name.strip()
    plex_name = payload.plex_name.strip()

    if not afl_name or not plex_name:
        raise HTTPException(status_code=400, detail="afl_name and plex_name are required")

    try:
        import mappings_manager
        mappings_manager.add_plex_mapping(afl_name, plex_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save mapping: {e}")

    if payload.add_to_schedule:
        config = load_config()
        if not config:
            raise HTTPException(status_code=500, detail="Config file not found")
        scheduled: List[str] = config.get("scheduler", {}).get("scheduled_anime", [])
        if afl_name not in scheduled:
            try:
                _write_scheduled_anime(scheduled + [afl_name])
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to update config: {e}")

    return {"success": True, "afl_name": afl_name, "plex_name": plex_name}


@app.delete("/api/anime/schedule/{afl_name}")
def remove_from_schedule(afl_name: str):
    """Remove an anime from scheduled_anime in config.yaml."""
    config = load_config()
    if not config:
        raise HTTPException(status_code=500, detail="Config file not found")
    scheduled: List[str] = config.get("scheduler", {}).get("scheduled_anime", [])
    if afl_name not in scheduled:
        raise HTTPException(status_code=404, detail=f"{afl_name} not in schedule")
    try:
        _write_scheduled_anime([a for a in scheduled if a != afl_name])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {e}")
    return {"success": True, "afl_name": afl_name}

def _parse_failed_episodes_log() -> list:
    """Parse failed_episodes.log into structured list of error groups."""
    if os.environ.get("RUNNING_IN_DOCKER") == "true":
        log_path = "/app/data/failed_episodes.log"
    else:
        log_path = os.path.join(os.path.dirname(__file__), "data", "failed_episodes.log")

    if not os.path.exists(log_path):
        return []

    entries = []
    current = None
    in_episodes = False
    in_details = False

    with open(log_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("--- ") and line.endswith(" ---"):
                if current and current.get("anime_name"):
                    entries.append(current)
                ts = line.strip("- ").strip()
                current = {"timestamp": ts, "anime_name": "", "episode_type": "", "failed_episodes": [], "details": []}
                in_episodes = False
                in_details = False
            elif line == "---":
                in_episodes = False
                in_details = False
            elif current is not None:
                if line.startswith("Anime: "):
                    current["anime_name"] = line[7:].strip()
                elif line.startswith("Episode Type: "):
                    current["episode_type"] = line[14:].strip()
                elif line.startswith("Failed Episodes: "):
                    in_episodes = True
                    in_details = False
                elif line.startswith("Details:"):
                    in_episodes = False
                    in_details = True
                elif in_episodes and line and line[0].isdigit() and ". " in line:
                    ep = line.split(". ", 1)[1].strip()
                    current["failed_episodes"].append(ep)
                    import re as _re
                    m = _re.match(r"^Ep\.(\d+) - (.+)$", ep)
                    if m:
                        current.setdefault("failed_episode_details", []).append(
                            {"number": int(m.group(1)), "name": m.group(2)}
                        )
                    else:
                        current.setdefault("failed_episode_details", []).append(
                            {"number": None, "name": ep}
                        )
                elif in_details and line.startswith("- "):
                    current["details"].append(line[2:].strip())

    if current and current.get("anime_name"):
        entries.append(current)

    return entries


@app.get("/api/mappings/errors")
def get_mapping_errors():
    """Return grouped mapping errors from failed_episodes.log."""
    try:
        entries = _parse_failed_episodes_log()
        seen: dict = {}
        try:
            import auto_update as _au
            _au.load_config()
            _mappings = _au.CONFIG.get("mappings", {}) or {}
        except Exception:
            _mappings = {}

        try:
            import mappings_manager as _mmgr
            _ignored = {
                (e["anime_name"], e["episode_type"])
                for e in (_mmgr.get_ignored_mappings() or [])
            }
        except Exception:
            _ignored = set()

        for entry in entries:
            key = (entry["anime_name"], entry["episode_type"])
            if key in _ignored:
                continue
            if key not in seen:
                plex_name = _mappings.get(entry["anime_name"]) or entry["anime_name"].replace("-", " ").title()
                seen[key] = {
                    "anime_name": entry["anime_name"],
                    "episode_type": entry["episode_type"],
                    "plex_name": plex_name,
                    "failed_episodes": [],
                    "failed_episode_details": [],
                    "details": [],
                    "timestamp": entry["timestamp"],
                }
            for ep in entry["failed_episodes"]:
                if ep not in seen[key]["failed_episodes"]:
                    seen[key]["failed_episodes"].append(ep)
            for det in entry.get("failed_episode_details", []):
                if not any(d["name"] == det["name"] for d in seen[key]["failed_episode_details"]):
                    seen[key]["failed_episode_details"].append(det)
            for d in entry["details"]:
                if d not in seen[key]["details"]:
                    seen[key]["details"].append(d)
        result = list(seen.values())
        return {"errors": result, "count": len(result)}
    except Exception as e:
        return {"errors": [], "count": 0, "error": str(e)}


class FixMappingPayload(BaseModel):
    anime_name: str
    episode_type: str
    mappings: Dict[str, str]


@app.post("/api/mappings/fix")
def save_mapping_fix(payload: FixMappingPayload):
    """Save title mapping fixes, clean the error log, then regenerate the Trakt list."""
    saved = 0
    try:
        import mappings_manager as _mm
        for original, mapped in payload.mappings.items():
            if original.strip() and mapped.strip():
                _mm.add_title_mapping(payload.anime_name, original.strip(), mapped.strip())
                saved += 1
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save mappings: {e}")

    try:
        from anime_trakt_manager import clean_error_log
        clean_error_log(payload.anime_name, payload.episode_type, list(payload.mappings.keys()))
    except Exception as clean_err:
        import logging as _logging
        _logging.getLogger("anime_trakt_manager").warning(f"Could not clean error log: {clean_err}")

    if payload.episode_type and saved > 0:
        def _regen():
            import logging as _logging
            import traceback as _tb
            _log = _logging.getLogger("anime_trakt_manager")
            try:
                import anime_trakt_manager as _atm
                _atm.load_config()
                _atm._create_list_internal(payload.anime_name, payload.episode_type.upper(), "hybrid")
            except Exception as exc:
                _log.error(f"List regen after mapping fix failed: {exc}\n{_tb.format_exc()}")
        threading.Thread(target=_regen, daemon=True).start()

    return {"success": True, "saved": saved}


@app.get("/api/mappings/title")
def get_title_mappings():
    """Return all saved title mappings grouped by anime."""
    try:
        import mappings_manager as _mm
        data = _mm.load_mappings()
        title_mappings = data.get("title_mappings") or {}
        result = []
        for anime_name, section in title_mappings.items():
            matches = (section or {}).get("special_matches") or {}
            if matches:
                result.append({
                    "anime_name": anime_name,
                    "matches": [{"plex_title": k, "trakt_title": v} for k, v in matches.items()],
                })
        total = sum(len(r["matches"]) for r in result)
        return {"mappings": result, "count": total}
    except Exception as e:
        return {"mappings": [], "count": 0, "error": str(e)}


class DeleteTitleMappingPayload(BaseModel):
    anime_name: str
    plex_title: str


@app.delete("/api/mappings/title")
def delete_title_mapping(payload: DeleteTitleMappingPayload):
    """Delete a specific title mapping entry."""
    try:
        import mappings_manager as _mm  # noqa: PLC0415
        data = _mm.load_mappings()
        title_mappings = data.get("title_mappings") or {}
        matches = (title_mappings.get(payload.anime_name) or {}).get("special_matches") or {}
        if payload.plex_title not in matches:
            raise HTTPException(status_code=404, detail="Mapping not found")
        del data["title_mappings"][payload.anime_name]["special_matches"][payload.plex_title]
        # Remove empty anime section
        if not data["title_mappings"][payload.anime_name].get("special_matches"):
            del data["title_mappings"][payload.anime_name]
        _mm.save_mappings(data)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class IgnoreMappingPayload(BaseModel):
    anime_name: str
    episode_type: str


@app.get("/api/mappings/ignored")
def get_mapping_ignored():
    """Return all ignored mapping error groups."""
    try:
        import mappings_manager as _mm
        ignored = _mm.get_ignored_mappings()
        try:
            import auto_update as _au
            _au.load_config()
            _mappings = (_au.CONFIG or {}).get("mappings", {}) or {}
        except Exception:
            _mappings = {}
        result = []
        for e in ignored:
            plex_name = _mappings.get(e["anime_name"]) or e["anime_name"].replace("-", " ").title()
            result.append({"anime_name": e["anime_name"], "episode_type": e["episode_type"], "plex_name": plex_name})
        return {"ignored": result}
    except Exception as e:
        return {"ignored": [], "error": str(e)}


@app.post("/api/mappings/ignore")
def add_mapping_ignore(payload: IgnoreMappingPayload):
    """Add an anime/episode_type to the mapping error ignore list."""
    try:
        import mappings_manager as _mm
        _mm.add_ignored_mapping(payload.anime_name, payload.episode_type)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/mappings/ignore")
def remove_mapping_ignore(payload: IgnoreMappingPayload):
    """Remove an anime/episode_type from the mapping error ignore list."""
    try:
        import mappings_manager as _mm
        _mm.remove_ignored_mapping(payload.anime_name, payload.episode_type)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PlexConnectionPayload(BaseModel):
    url: str
    token: str

@app.post("/api/setup/plex/libraries")
def get_plex_libraries_for_setup(payload: PlexConnectionPayload):
    """Fetch all Plex library sections given URL and token (no config required)."""
    try:
        from plexapi.server import PlexServer
        plex = PlexServer(payload.url, payload.token, timeout=10)
        libraries = [
            {"title": s.title, "type": s.type}
            for s in plex.library.sections()
            if s.type in ("movie", "show")
        ]
        return {"libraries": libraries, "error": None}
    except Exception as e:
        return {"libraries": [], "error": str(e)}


class SetupPayload(BaseModel):
    timezone: str
    date_format: str  # "DD/MM" or "MM/DD"
    plex_url: str
    plex_token: str
    libraries: dict  # {"anime": [...], "tv": [...], "movie": [...]}
    services: dict   # see structure below
    kometa: dict     # yaml_output_dir, collections_dir, font_directory, asset_directory
    trakt: dict      # client_id, client_secret, username, redirect_uri
    notifications: dict  # enabled, discord_webhook
    list_privacy: str  # "private" or "public"
    tmdb_api_key: str = ""
    tvdb_api_key: str = ""

@app.post("/api/setup")
def run_setup_api(payload: SetupPayload):
    """Write initial config.yaml from setup wizard data."""
    try:
        anime_libs = payload.libraries.get("anime", [])
        tv_libs = payload.libraries.get("tv", [])
        movie_libs = payload.libraries.get("movie", [])

        svc = payload.services

        def _sched(svc_cfg: dict) -> dict:
            t = svc_cfg.get("schedule_type", "daily")
            if t == "daily":
                return {"type": "daily", "times": svc_cfg.get("schedule_times", ["03:00"])}
            if t == "hourly":
                return {"type": "hourly", "minute": svc_cfg.get("schedule_minute", 0)}
            if t == "weekly":
                return {"type": "weekly", "days": svc_cfg.get("schedule_days", ["monday"]), "time": svc_cfg.get("schedule_time", "03:00")}
            if t == "monthly":
                return {"type": "monthly", "dates": svc_cfg.get("schedule_dates", [1]), "time": svc_cfg.get("schedule_time", "03:00")}
            return {"type": "daily", "times": ["03:00"]}

        aet = svc.get("anime_episode_type", {})
        tst = svc.get("tv_status_tracker", {})
        so = svc.get("size_overlay", {})

        config = {
            "timezone": payload.timezone,
            "date_format": payload.date_format.upper(),
            "tmdb_api_key": payload.tmdb_api_key,
            "plex": {
                "url": payload.plex_url,
                "token": payload.plex_token,
                "libraries": {
                    "anime": anime_libs,
                    "tv": tv_libs,
                    "movie": movie_libs,
                },
            },
            "trakt": {
                "client_id": payload.trakt.get("client_id", ""),
                "client_secret": payload.trakt.get("client_secret", ""),
                "username": payload.trakt.get("username", ""),
                "redirect_uri": payload.trakt.get("redirect_uri", "urn:ietf:wg:oauth:2.0:oob"),
            },
            "lists": {"default_privacy": payload.list_privacy},
            "kometa_config": {
                "yaml_output_dir": payload.kometa.get("yaml_output_dir", "/kometa/config/overlays"),
                "collections_dir": payload.kometa.get("collections_dir", "/kometa/config/collections"),
                "font_directory": payload.kometa.get("font_directory", "config/fonts"),
                "asset_directory": payload.kometa.get("asset_directory", "config/assets"),
            },
            "scheduler": {
                "anime_episode_type": _sched(aet),
                "tv_status_tracker": _sched(tst),
                "size_overlay": _sched(so),
            },
            "services": {
                "anime_episode_type": {
                    "enabled": bool(aet.get("enabled", False)),
                    "libraries": aet.get("libraries", anime_libs),
                    "overlay": {
                        "horizontal_offset": 0, "horizontal_align": "center",
                        "vertical_offset": 0, "vertical_align": "top",
                        "font_size": 75, "back_width": 1920, "back_height": 125,
                        "back_color": "#262626",
                    },
                },
                "tv_status_tracker": {
                    "enabled": bool(tst.get("enabled", False)),
                    "libraries": tst.get("libraries", []),
                    "metadata_provider": "trakt" if tst.get("metadata_provider") == "trakt" else "tvdb",
                    "next_airing": {"provider": "text_file"},
                    "colors": {
                        "AIRING": "#006580", "ENDED": "#000000", "CANCELLED": "#FF0000",
                        "RETURNING": "#008000", "SEASON_FINALE": "#9932CC",
                        "MID_SEASON_FINALE": "#FFA500", "FINAL_EPISODE": "#8B0000",
                        "SEASON_PREMIERE": "#228B22",
                    },
                    "overlay": {
                        "back_height": 90, "back_width": 1000, "color": "#FFFFFF",
                        "font_size": 70, "horizontal_align": "center", "horizontal_offset": 0,
                        "vertical_align": "top", "vertical_offset": 0,
                        "font_name": "Juventus-Fans-Bold.ttf",
                        "overlay_style": "background_color",
                        "gradient_name": "gradient_top.png",
                        "apply_gradient_background": False,
                    },
                },
                "size_overlay": {
                    "enabled": bool(so.get("enabled", False)),
                    "movie_libraries": so.get("movie_libraries", []),
                    "tv_libraries": so.get("tv_libraries", []),
                    "anime_libraries": so.get("anime_libraries", []),
                    "movie_overlay": {
                        "apply_gradient_background": False, "gradient_name": "gradient_top.png",
                        "font_path": "config/fonts/Juventus-Fans-Bold.ttf",
                        "horizontal_offset": 0, "horizontal_align": "center",
                        "vertical_offset": 0, "vertical_align": "top",
                        "font_size": 63, "font_color": "#FFFFFF",
                        "back_color": "#000000", "back_width": 1920, "back_height": 125,
                    },
                    "show_overlay": {
                        "apply_gradient_background": False, "gradient_name": "gradient_bottom.png",
                        "font_path": "config/fonts/Juventus-Fans-Bold.ttf",
                        "horizontal_offset": 0, "horizontal_align": "center",
                        "vertical_offset": 0, "vertical_align": "bottom",
                        "font_size": 55, "font_color": "#FFFFFF",
                        "back_color": "#00000099", "back_width": 1920, "back_height": 80,
                        "show_episode_count": False,
                    },
                },
            },
            "notifications": {
                "enabled": bool(payload.notifications.get("enabled", False)),
            },
        }

        if payload.tvdb_api_key:
            config["tvdb_api_key"] = payload.tvdb_api_key

        tv_uses_trakt = bool(tst.get("enabled", False)) and tst.get("metadata_provider") == "trakt"
        if not bool(aet.get("enabled", False)):
            config.pop("lists", None)
            if not tv_uses_trakt:
                config.pop("trakt", None)

        if payload.notifications.get("enabled") and payload.notifications.get("discord_webhook"):
            config["notifications"]["discord"] = {"webhook_url": payload.notifications["discord_webhook"]}

        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        tmp_path = CONFIG_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        os.replace(tmp_path, CONFIG_FILE)

        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trakt/status")
def get_trakt_status():
    """Return current Trakt authentication status and credentials metadata."""
    import time as _time
    config = load_config()
    trakt_cfg = (config or {}).get("trakt", {})
    username = trakt_cfg.get("username", "")
    client_id = trakt_cfg.get("client_id", "")
    client_secret = trakt_cfg.get("client_secret", "")

    token_file = os.path.join(DATA_DIR, "trakt_token.json")
    connected = False
    token_expiry: Optional[int] = None

    if os.path.exists(token_file):
        try:
            with open(token_file, "r") as f:
                token_data = json.load(f)
            access_token = token_data.get("access_token")
            created_at = token_data.get("created_at", 0)
            expires_in = token_data.get("expires_in", 0)
            if access_token and expires_in:
                expiry_ts = created_at + expires_in
                connected = int(_time.time()) < expiry_ts
                token_expiry = expiry_ts
        except Exception:
            pass

    return {
        "connected": connected,
        "username": username,
        "client_id": client_id,
        "client_secret": client_secret,
        "token_expiry": token_expiry,
    }


class TraktCredentialsPayload(BaseModel):
    client_id: str
    client_secret: str
    username: str


@app.put("/api/trakt/credentials")
def update_trakt_credentials(payload: TraktCredentialsPayload):
    """Update Trakt credentials (client_id, client_secret, username) in config.yaml."""
    config = load_config()
    if config is None:
        raise HTTPException(status_code=500, detail="Config file not found")
    config.setdefault("trakt", {})
    config["trakt"]["client_id"] = payload.client_id
    config["trakt"]["client_secret"] = payload.client_secret
    config["trakt"]["username"] = payload.username
    config["trakt"].setdefault("redirect_uri", "urn:ietf:wg:oauth:2.0:oob")
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        tmp_path = CONFIG_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        if os.path.exists(CONFIG_FILE):
            shutil.copy2(CONFIG_FILE, CONFIG_FILE + ".bak")
        os.replace(tmp_path, CONFIG_FILE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True}


class TraktDeviceCodePayload(BaseModel):
    client_id: str

@app.post("/api/setup/trakt/device-code")
def get_trakt_device_code(payload: TraktDeviceCodePayload):
    """Get Trakt device code for in-browser auth during setup."""
    try:
        import requests as _req
        resp = _req.post(
            "https://api.trakt.tv/oauth/device/code",
            json={"client_id": payload.client_id},
            headers={"Content-Type": "application/json", "trakt-api-version": "2", "trakt-api-key": payload.client_id},
            timeout=10,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Trakt returned {resp.status_code}")
        data = resp.json()
        return {
            "device_code": data["device_code"],
            "user_code": data["user_code"],
            "verification_url": data["verification_url"],
            "expires_in": data.get("expires_in", 600),
            "interval": data.get("interval", 5),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TraktDevicePollPayload(BaseModel):
    device_code: str
    client_id: str
    client_secret: str

@app.post("/api/setup/trakt/device-poll")
def poll_trakt_device_token(payload: TraktDevicePollPayload):
    """Poll once for Trakt device token. Frontend should call this on an interval."""
    try:
        import requests as _req
        resp = _req.post(
            "https://api.trakt.tv/oauth/device/token",
            json={
                "code": payload.device_code,
                "client_id": payload.client_id,
                "client_secret": payload.client_secret,
            },
            headers={"Content-Type": "application/json", "trakt-api-version": "2"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            import trakt_auth as _ta
            _ta.store_trakt_tokens(
                data["access_token"],
                data["refresh_token"],
                data.get("created_at", int(__import__("time").time())),
                data.get("expires_in", 7776000),
            )
            return {"authorized": True, "access_token": data["access_token"]}
        if resp.status_code == 400:
            return {"authorized": False, "pending": True}
        if resp.status_code in (404, 409, 410, 418, 429):
            return {"authorized": False, "pending": False, "error": f"Trakt error {resp.status_code}"}
        return {"authorized": False, "pending": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if os.path.exists(WEB_OUT):
    app.mount("/", StaticFiles(directory=WEB_OUT, html=True), name="static")
