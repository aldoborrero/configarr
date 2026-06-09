"""SABnzbd API client for configuration management."""

import logging
from typing import Any

import requests

from configarr.models import SyncStatus

log = logging.getLogger(__name__)


class SabnzbdClient:
    """SABnzbd API client for configuration."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._config_cache: dict[str, Any] | None = None

    def _call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Make API call to SABnzbd."""
        params["apikey"] = self.api_key
        params["output"] = "json"
        resp = requests.get(f"{self.base_url}/api", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"SABnzbd API error: {data['error']}")
        return data

    def get_config(self, section: str | None = None) -> dict[str, Any]:
        """Get configuration, optionally filtered by section."""
        params: dict[str, Any] = {"mode": "get_config"}
        if section:
            params["section"] = section
        return self._call(params).get("config", {})

    def get_full_config(self) -> dict[str, Any]:
        """Get full configuration (cached)."""
        if self._config_cache is None:
            self._config_cache = self.get_config()
        return self._config_cache

    def set_config(self, section: str, name: str, **kwargs: Any) -> dict[str, Any]:
        """Set configuration for a section item."""
        params: dict[str, Any] = {
            "mode": "set_config",
            "section": section,
            "name": name,
        }
        params.update(kwargs)
        result = self._call(params)
        self._config_cache = None  # Invalidate cache
        return result

    def set_misc(self, keyword: str, value: Any) -> dict[str, Any]:
        """Set a single misc configuration setting."""
        params: dict[str, Any] = {
            "mode": "set_config",
            "section": "misc",
            "keyword": keyword,
            "value": value,
        }
        result = self._call(params)
        self._config_cache = None
        return result

    def del_config(self, section: str, keyword: str) -> dict[str, Any]:
        """Delete a configuration item."""
        result = self._call({
            "mode": "del_config",
            "section": section,
            "keyword": keyword,
        })
        self._config_cache = None
        return result

    # High-level sync methods

    def _find_server(self, name: str) -> dict[str, Any] | None:
        """Find server by name."""
        config = self.get_full_config()
        servers = config.get("servers", [])
        for server in servers:
            if server.get("name") == name:
                return server
        return None

    def _find_category(self, name: str) -> dict[str, Any] | None:
        """Find category by name."""
        config = self.get_full_config()
        categories = config.get("categories", [])
        for cat in categories:
            if cat.get("name") == name:
                return cat
        return None

    def sync_server(self, name: str, config: dict[str, Any]) -> SyncStatus:
        """Sync a news server configuration."""
        host = config.get("host")
        if not host:
            raise ValueError(f"SABnzbd server '{name}' is missing required 'host'")

        existing = self._find_server(name)

        # Build server params
        params = {
            "host": host,
            "port": config.get("port", 563),
            "ssl": 1 if config.get("ssl", True) else 0,
            "ssl_verify": config.get("ssl_verify", 2),
            "ssl_ciphers": config.get("ssl_ciphers", ""),
            "username": config.get("username", ""),
            "password": config.get("password", ""),
            "connections": config.get("connections", 8),
            "priority": config.get("priority", 0),
            "retention": config.get("retention", 0),
            "timeout": config.get("timeout", 60),
            "enable": 1 if config.get("enable", True) else 0,
            "required": 1 if config.get("required", False) else 0,
            "optional": 1 if config.get("optional", False) else 0,
            "send_group": 1 if config.get("send_group", False) else 0,
            "notes": config.get("notes", ""),
        }

        # Filter out None values
        params = {k: v for k, v in params.items() if v is not None}

        if existing:
            self.set_config("servers", name, **params)
            log.debug(f"Updated server: {name}")
            return SyncStatus.UPDATED

        self.set_config("servers", name, **params)
        log.debug(f"Created server: {name}")
        return SyncStatus.CREATED

    def sync_category(self, name: str, config: dict[str, Any]) -> SyncStatus:
        """Sync a category configuration."""
        existing = self._find_category(name)

        # Build category params
        params = {
            "pp": config.get("pp", ""),  # Post-processing: "", "0", "1", "2", "3"
            "script": config.get("script", "None"),
            "dir": config.get("dir", ""),
            "newzbin": config.get("newzbin", ""),
            "priority": config.get("priority", -100),  # -100 = Default
        }

        # Filter out None values
        params = {k: v for k, v in params.items() if v is not None}

        if existing:
            self.set_config("categories", name, **params)
            log.debug(f"Updated category: {name}")
            return SyncStatus.UPDATED

        self.set_config("categories", name, **params)
        log.debug(f"Created category: {name}")
        return SyncStatus.CREATED

    def sync_misc_settings(self, config: dict[str, Any]) -> SyncStatus:
        """Sync misc settings."""
        # Map config keys to SABnzbd API keys
        key_map = {
            "download_dir": "download_dir",
            "complete_dir": "complete_dir",
            "nzb_backup_dir": "nzb_backup_dir",
            "scripts_dir": "scripts_dir",
            "log_dir": "log_dir",
            "bandwidth_max": "bandwidth_max",
            "bandwidth_perc": "bandwidth_perc",
            "cache_limit": "cache_limit",
            "pause_on_post_processing": "pause_on_post_processing",
            "auto_sort": "auto_sort",
            "enable_all_par": "enable_all_par",
            "enable_recursive": "enable_recursive",
            "par_option": "par_option",
            "nice": "nice",
            "ionice": "ionice",
            "pre_check": "pre_check",
            "auto_disconnect": "auto_disconnect",
            "flat_unpack": "flat_unpack",
            "safe_postproc": "safe_postproc",
        }

        updated = False
        for config_key, api_key in key_map.items():
            if config_key in config:
                value = config[config_key]
                if isinstance(value, bool):
                    value = 1 if value else 0
                self.set_misc(api_key, value)
                updated = True
                log.debug(f"Updated misc setting: {api_key}={value}")

        if updated:
            return SyncStatus.UPDATED

        return SyncStatus.UNCHANGED
