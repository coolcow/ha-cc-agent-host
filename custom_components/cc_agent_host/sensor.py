"""Sensors: plan usage (5-hour and weekly windows) as reported by Claude Code."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any

from homeassistant.components.sensor import (SensorDeviceClass, SensorEntity, SensorEntityDescription,
                                             SensorStateClass)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AgentHostConfigEntry
from .entity import AgentHostEntity


def _limit(usage: dict[str, Any], window: str, field: str) -> Any:
    return ((usage.get("rate_limits") or {}).get(window) or {}).get(field)


def _ts(value: Any) -> datetime | None:
    return datetime.fromtimestamp(value, UTC) if isinstance(value, int | float) else None


@dataclass(frozen=True, kw_only=True)
class AgentHostSensorDescription(SensorEntityDescription):
    value: Callable[[dict[str, Any]], Any]


DESCRIPTIONS = (
    AgentHostSensorDescription(key="usage_5h", native_unit_of_measurement=PERCENTAGE,
                               state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0,
                               value=lambda u: _limit(u, "five_hour", "used_percentage")),
    AgentHostSensorDescription(key="usage_week", native_unit_of_measurement=PERCENTAGE,
                               state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0,
                               value=lambda u: _limit(u, "seven_day", "used_percentage")),
    AgentHostSensorDescription(key="reset_5h", device_class=SensorDeviceClass.TIMESTAMP,
                               value=lambda u: _ts(_limit(u, "five_hour", "resets_at"))),
    AgentHostSensorDescription(key="reset_week", device_class=SensorDeviceClass.TIMESTAMP,
                               value=lambda u: _ts(_limit(u, "seven_day", "resets_at"))),
    AgentHostSensorDescription(key="usage_updated", device_class=SensorDeviceClass.TIMESTAMP,
                               entity_category=EntityCategory.DIAGNOSTIC,
                               value=lambda u: _ts(u.get("updated_at"))),
)


async def async_setup_entry(hass: HomeAssistant, entry: AgentHostConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(AgentHostSensor(entry.runtime_data, d) for d in DESCRIPTIONS)


class AgentHostSensor(AgentHostEntity, SensorEntity):
    entity_description: AgentHostSensorDescription

    def __init__(self, coordinator, description: AgentHostSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data["usage"])
