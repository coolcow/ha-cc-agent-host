"""Update entity: newer Claude Code versions, installed in the add-on only on request."""
from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import AgentHostError
from .coordinator import AgentHostConfigEntry
from .entity import AgentHostEntity

RELEASE_URL = "https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md"


async def async_setup_entry(hass: HomeAssistant, entry: AgentHostConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([CliUpdate(entry.runtime_data)])


class CliUpdate(AgentHostEntity, UpdateEntity):
    """Claude Code in the add-on; the add-on downloads and verifies the official package."""

    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.SPECIFIC_VERSION
    _attr_release_url = RELEASE_URL
    _attr_title = "Claude Code"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "cli")

    @property
    def installed_version(self) -> str | None:
        return self.coordinator.data["status"].get("claude_version")

    @property
    def latest_version(self) -> str | None:
        # add-on versions before 0.7.0 do not report the latest version
        return self.coordinator.data["status"].get("claude_latest") or self.installed_version

    @property
    def in_progress(self) -> bool:
        return bool(self.coordinator.data["status"].get("claude_updating"))

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        try:
            await self.coordinator.api.update_cli(version or self.latest_version)
        except AgentHostError as err:
            raise HomeAssistantError(f"Claude Code update failed: {err}") from err
        finally:
            await self.coordinator.async_request_refresh()
