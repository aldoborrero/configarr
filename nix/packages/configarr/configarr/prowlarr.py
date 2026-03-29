"""Prowlarr API client using prowlarr-py."""

import logging

import requests as http_requests
import prowlarr
from prowlarr.api import ApplicationApi, DownloadClientApi, IndexerApi
from prowlarr.models import (
    ApplicationResource,
    ApplicationSyncLevel,
    ContractField,
    DownloadClientResource,
    IndexerResource,
)

from configarr.models import SyncStatus

log = logging.getLogger(__name__)


class ProwlarrClient:
    """Prowlarr API client using prowlarr-py."""

    def __init__(self, base_url: str, api_key: str):
        config = prowlarr.Configuration(host=base_url)
        config.api_key["X-Api-Key"] = api_key
        self.api_client = prowlarr.ApiClient(config)

        # API instances
        self.indexers = IndexerApi(self.api_client)
        self.applications = ApplicationApi(self.api_client)
        self.download_clients = DownloadClientApi(self.api_client)

        # Schema caches
        self._indexer_schemas: dict[str, IndexerResource] | None = None
        self._app_schemas: dict[str, ApplicationResource] | None = None
        self._client_schemas: dict[str, DownloadClientResource] | None = None

    def get_indexer_schema(self, implementation: str) -> IndexerResource | None:
        """Get schema for indexer implementation (cached)."""
        if self._indexer_schemas is None:
            schemas = self.indexers.list_indexer_schema()
            self._indexer_schemas = {s.implementation: s for s in schemas if s.implementation}
        return self._indexer_schemas.get(implementation)

    def get_app_schema(self, implementation: str) -> ApplicationResource | None:
        """Get schema for application implementation (cached)."""
        if self._app_schemas is None:
            schemas = self.applications.list_applications_schema()
            self._app_schemas = {s.implementation: s for s in schemas if s.implementation}
        return self._app_schemas.get(implementation)

    def get_download_client_schema(self, implementation: str) -> DownloadClientResource | None:
        """Get schema for download client implementation (cached)."""
        if self._client_schemas is None:
            schemas = self.download_clients.list_download_client_schema()
            self._client_schemas = {s.implementation: s for s in schemas if s.implementation}
        return self._client_schemas.get(implementation)

    def build_fields(
        self, schema_fields: list[ContractField] | None, settings: dict
    ) -> list[ContractField]:
        """Transform settings dict to ContractField list using schema."""
        fields = []
        for schema_field in schema_fields or []:
            field = ContractField(name=schema_field.name)
            if schema_field.name in settings:
                field.value = settings[schema_field.name]
            elif schema_field.value is not None:
                field.value = schema_field.value
            fields.append(field)
        return fields

    def _find_by_name[T](self, resources: list[T], name: str) -> T | None:
        """Find resource by name in list."""
        for r in resources:
            if hasattr(r, "name") and r.name == name:
                return r
        return None

    def sync_indexer(self, name: str, config: dict) -> SyncStatus:
        """Sync single indexer. Returns status."""
        implementation = config.get("implementation")
        if not implementation:
            raise ValueError(f"Missing 'implementation' for indexer: {name}")

        schema = self.get_indexer_schema(implementation)
        if not schema:
            raise ValueError(f"Unknown implementation: {implementation}")

        resource = IndexerResource(
            name=name,
            implementation=implementation,
            config_contract=schema.config_contract,
            enable=config.get("enable", True),
            priority=config.get("priority", 25),
            app_profile_id=config.get("app_profile_id", 1),
            redirect=config.get("redirect", False),
            fields=self.build_fields(schema.fields, config.get("settings", {})),
            tags=config.get("tags", []),
        )

        existing = self._find_by_name(self.indexers.list_indexer(), name)

        if existing:
            resource.id = existing.id
            self.indexers.update_indexer(str(existing.id), indexer_resource=resource)
            log.debug(f"Updated indexer: {name}")
            return SyncStatus.UPDATED
        else:
            self.indexers.create_indexer(indexer_resource=resource)
            log.debug(f"Created indexer: {name}")
            return SyncStatus.CREATED

    def sync_application(self, name: str, config: dict) -> SyncStatus:
        """Sync single application. Returns status."""
        implementation = config.get("implementation")
        if not implementation:
            raise ValueError(f"Missing 'implementation' for application: {name}")

        schema = self.get_app_schema(implementation)
        if not schema:
            raise ValueError(f"Unknown implementation: {implementation}")

        sync_level_str = config.get("sync_level", "fullSync")
        sync_level = ApplicationSyncLevel(sync_level_str)

        resource = ApplicationResource(
            name=name,
            implementation=implementation,
            config_contract=schema.config_contract,
            sync_level=sync_level,
            fields=self.build_fields(schema.fields, config.get("settings", {})),
            tags=config.get("tags", []),
        )

        existing = self._find_by_name(self.applications.list_applications(), name)

        if existing:
            resource.id = existing.id
            self.applications.update_applications(
                str(existing.id), application_resource=resource
            )
            log.debug(f"Updated application: {name}")
            return SyncStatus.UPDATED
        else:
            self.applications.create_applications(application_resource=resource)
            log.debug(f"Created application: {name}")
            return SyncStatus.CREATED

    def sync_download_client(self, name: str, config: dict) -> SyncStatus:
        """Sync single download client using raw HTTP (prowlarr-py has issues)."""
        implementation = config.get("implementation")
        if not implementation:
            raise ValueError(f"Missing 'implementation' for download client: {name}")

        schema = self.get_download_client_schema(implementation)
        if not schema:
            raise ValueError(f"Unknown implementation: {implementation}")

        protocol_map = {
            "Transmission": "torrent",
            "Sabnzbd": "usenet",
            "NzbGet": "usenet",
            "QBittorrent": "torrent",
            "Deluge": "torrent",
            "RTorrent": "torrent",
        }

        base_url = self.api_client.configuration.host
        api_key = self.api_client.configuration.api_key.get("X-Api-Key", "")
        headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}

        # Build fields from schema + settings
        # Filter out None values — Prowlarr NullReferenceException on null fields
        settings = config.get("settings", {})
        fields_list = []
        for sf in (schema.fields or []):
            value = settings.get(sf.name)
            if value is None:
                value = sf.value if sf.value is not None else ""
            fields_list.append({"name": sf.name, "value": value})

        payload = {
            "name": name,
            "enable": config.get("enable", True),
            "protocol": protocol_map.get(implementation, "torrent"),
            "priority": config.get("priority", 1),
            "implementation": implementation,
            "configContract": schema.config_contract,
            "tags": config.get("tags", []),
            "categories": [],
            "fields": fields_list,
        }

        # Check if already exists
        resp = http_requests.get(
            f"{base_url}/api/v1/downloadclient",
            headers=headers,
        )
        resp.raise_for_status()
        existing = None
        for client in resp.json():
            if client.get("name") == name:
                existing = client
                break

        if existing:
            payload["id"] = existing["id"]
            resp = http_requests.put(
                f"{base_url}/api/v1/downloadclient/{existing['id']}?forceSave=true",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            log.debug(f"Updated download client: {name}")
            return SyncStatus.UPDATED
        else:
            resp = http_requests.post(
                f"{base_url}/api/v1/downloadclient?forceSave=true",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            log.debug(f"Created download client: {name}")
            return SyncStatus.CREATED
