"""Base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AgentHostCoordinator


class AgentHostEntity(CoordinatorEntity[AgentHostCoordinator]):
    """Entity of the CC Agent Host service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AgentHostCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_translation_key = key
        status = coordinator.data["status"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DOMAIN)}, name="CC Agent Host", manufacturer="CC Agent Host",
            model=f"Claude Code {status.get('claude_version', '')}".strip(),
            sw_version=status.get("version"), entry_type=DeviceEntryType.SERVICE)
