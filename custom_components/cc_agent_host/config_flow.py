"""Config flow: set up from the add-on's discovery, or manually."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
import voluptuous as vol

from .api import AgentHostApi, AgentHostAuthError, AgentHostError
from .const import CONF_API_KEY, DEFAULT_PORT, DOMAIN

USER_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    vol.Required(CONF_API_KEY): str,
})


class AgentHostConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CC Agent Host."""

    VERSION = 1
    _discovered: dict[str, Any]

    async def _check(self, data: Mapping[str, Any]) -> str | None:
        api = AgentHostApi(async_get_clientsession(self.hass), data[CONF_HOST], data[CONF_PORT], data[CONF_API_KEY])
        try:
            await api.status()
        except AgentHostAuthError:
            return "invalid_auth"
        except AgentHostError:
            return "cannot_connect"
        return None

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        """Discovery from the add-on (Supervisor)."""
        cfg = discovery_info.config
        self._discovered = {CONF_HOST: cfg["host"], CONF_PORT: int(cfg["port"]), CONF_API_KEY: cfg["api_key"]}
        await self.async_set_unique_id(DOMAIN)
        # a rediscovery (new host or key) updates the existing entry silently
        self._abort_if_unique_id_configured(updates=self._discovered)
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (error := await self._check(self._discovered)) is None:
                return self.async_create_entry(title="CC Agent Host", data=self._discovered)
            errors["base"] = error
        return self.async_show_form(step_id="hassio_confirm", errors=errors)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manual setup (e.g. when discovery is not available)."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            if (error := await self._check(user_input)) is None:
                return self.async_create_entry(title="CC Agent Host", data=user_input)
            errors["base"] = error
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            if (error := await self._check(data)) is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error
        return self.async_show_form(step_id="reauth_confirm", errors=errors,
                                    data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}))
