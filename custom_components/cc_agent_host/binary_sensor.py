"""Binary sensors: sign-in, job token, job running."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (BinarySensorDeviceClass, BinarySensorEntity,
                                                    BinarySensorEntityDescription)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AgentHostConfigEntry
from .entity import AgentHostEntity


@dataclass(frozen=True, kw_only=True)
class AgentHostBinaryDescription(BinarySensorEntityDescription):
    value: Callable[[dict[str, Any]], bool]


DESCRIPTIONS = (
    AgentHostBinaryDescription(key="signed_in", device_class=BinarySensorDeviceClass.CONNECTIVITY,
                               entity_category=EntityCategory.DIAGNOSTIC, value=lambda s: s["signed_in"]),
    AgentHostBinaryDescription(key="job_token", entity_category=EntityCategory.DIAGNOSTIC,
                               value=lambda s: s["job_token"]),
    AgentHostBinaryDescription(key="job_running", device_class=BinarySensorDeviceClass.RUNNING,
                               value=lambda s: s["running"]),
)


async def async_setup_entry(hass: HomeAssistant, entry: AgentHostConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(AgentHostBinarySensor(entry.runtime_data, d) for d in DESCRIPTIONS)


class AgentHostBinarySensor(AgentHostEntity, BinarySensorEntity):
    entity_description: AgentHostBinaryDescription

    def __init__(self, coordinator, description: AgentHostBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return bool(self.entity_description.value(self.coordinator.data["status"]))
