"""Polls status and plan usage from the add-on."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AgentHostApi, AgentHostAuthError, AgentHostError
from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

type AgentHostConfigEntry = ConfigEntry[AgentHostCoordinator]


class AgentHostCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Status and usage of the add-on."""

    config_entry: AgentHostConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AgentHostConfigEntry, api: AgentHostApi) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
                         update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS))
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return {"status": await self.api.status(), "usage": await self.api.usage()}
        except AgentHostAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AgentHostError as err:
            raise UpdateFailed(str(err)) from err
