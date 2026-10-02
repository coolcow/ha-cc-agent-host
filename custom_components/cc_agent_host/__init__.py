"""CC Agent Host: Home Assistant side of the CC Agent Host add-on.

Generic bridge only: an action to run jobs and entities for the add-on's state.
Use cases (digests, usage statistics, ...) belong in the user's configuration.
"""
from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .api import AgentHostApi, AgentHostError
from .const import (ATTR_PROFILE, ATTR_PROMPT, ATTR_TIMEOUT, CONF_API_KEY, DOMAIN, RUN_TIMEOUT_MAX,
                    SERVICE_RUN)
from .coordinator import AgentHostConfigEntry, AgentHostCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

RUN_SCHEMA = vol.Schema({
    vol.Required(ATTR_PROFILE): cv.string,
    vol.Required(ATTR_PROMPT): cv.string,
    vol.Optional(ATTR_TIMEOUT): vol.All(vol.Coerce(int), vol.Range(min=10, max=RUN_TIMEOUT_MAX)),
})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the run action."""

    async def run(call: ServiceCall) -> ServiceResponse:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("CC Agent Host is not set up")
        coordinator: AgentHostCoordinator = entries[0].runtime_data
        try:
            result = await coordinator.api.run(call.data[ATTR_PROFILE], call.data[ATTR_PROMPT],
                                               call.data.get(ATTR_TIMEOUT))
        except AgentHostError as err:
            if err.status in (400, 404):
                raise ServiceValidationError(str(err)) from err
            raise HomeAssistantError(f"CC Agent Host: {err}") from err
        finally:
            await coordinator.async_request_refresh()
        return result

    hass.services.async_register(DOMAIN, SERVICE_RUN, run, schema=RUN_SCHEMA,
                                 supports_response=SupportsResponse.ONLY)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AgentHostConfigEntry) -> bool:
    """Connect to the add-on."""
    api = AgentHostApi(async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT],
                       entry.data[CONF_API_KEY])
    coordinator = AgentHostCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AgentHostConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
