"""Separate full inventory snapshots from fast state updates."""

import asyncio
import logging
from datetime import timedelta
from time import monotonic

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthenticationError, GatewayError
from .const import DOMAIN, INVENTORY_INTERVAL
from .models import discover, index_devices

_LOGGER = logging.getLogger(__name__)


class HomeWizardCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client, identity, interval):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.serial = identity["serial"]
        self.firmware = identity.get("version")
        self.inventory = {}
        self.status = {}
        self.specs = set()
        self._inventory_at = None
        self._operation_lock = asyncio.Lock()

    async def _async_update_data(self):
        async with self._operation_lock:
            try:
                inventory = self.inventory
                refresh_inventory = (
                    self._inventory_at is None
                    or monotonic() - self._inventory_at >= INVENTORY_INTERVAL
                )
                if refresh_inventory:
                    inventory = index_devices(await self.client.get_sensors())
                status = index_devices(await self.client.get_status())
            except AuthenticationError:
                raise ConfigEntryAuthFailed("Gateway authentication failed") from None
            except GatewayError:
                raise UpdateFailed("Cannot update the HomeWizard gateway") from None
            # Commit together; a failed request must never look like device removal.
            self.inventory = inventory
            self.status = status
            if refresh_inventory:
                self._inventory_at = monotonic()
                self._update_devices()
            self.specs |= discover(inventory, status)
            return status

    def _update_devices(self):
        """Refresh names and register weather devices even without measurements."""
        registry = dr.async_get(self.hass)
        registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, self.serial)},
            name="HomeWizard Smart Home",
            manufacturer="HomeWizard",
            model="Legacy gateway",
            sw_version=self.firmware,
        )
        supported = {spec.device_key for spec in discover(self.inventory, self.status)}
        for (category, device_id), record in self.inventory.items():
            if (category, device_id) not in supported and category not in {
                "thermometers",
                "rainmeters",
                "windmeters",
                "weatherdisplays",
            }:
                continue
            registry.async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                identifiers={(DOMAIN, f"{self.serial}:{category}:{device_id}")},
                name=record.get("name") or f"{category} {device_id}",
                manufacturer="HomeWizard",
                model=record.get("type", category),
                via_device=(DOMAIN, self.serial),
            )

    async def async_command(self, family, device_id, action):
        try:
            async with self._operation_lock:
                await self.client.command(family, device_id, action)
        except AuthenticationError:
            self.async_set_update_error(UpdateFailed("Gateway authentication failed"))
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Gateway authentication failed") from None
        except GatewayError:
            self.async_set_update_error(UpdateFailed("Gateway command failed"))
            raise HomeAssistantError("Gateway command failed; delivery may be uncertain") from None
        await self.async_request_refresh()
