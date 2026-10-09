"""Binary sensors for Waterkotte Resümat CD4."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ResumatCoordinator


@dataclass(frozen=True, kw_only=True)
class ResumatBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Resümat binary sensor."""


DESCRIPTIONS = (
    ResumatBinarySensorDescription(
        key="heating_disabled",
        translation_key="heating_disabled",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    ResumatBinarySensorDescription(
        key="hot_water_disabled",
        translation_key="hot_water_disabled",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    ResumatBinarySensorDescription(
        key="heating_running",
        translation_key="heating_running",
        device_class=BinarySensorDeviceClass.HEAT,
    ),
    ResumatBinarySensorDescription(
        key="hot_water_running",
        translation_key="hot_water_running",
        device_class=BinarySensorDeviceClass.HEAT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Resümat binary sensors."""
    coordinator: ResumatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ResumatBinarySensor(coordinator, entry, description)
        for description in DESCRIPTIONS
    )


class ResumatBinarySensor(
    CoordinatorEntity[ResumatCoordinator], BinarySensorEntity
):
    """Represent a Resümat binary sensor."""

    entity_description: ResumatBinarySensorDescription

    def __init__(
        self,
        coordinator: ResumatCoordinator,
        entry: ConfigEntry,
        description: ResumatBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            manufacturer="Waterkotte",
            model="Resümat CD4",
            name="Waterkotte Resümat CD4",
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether the reported condition is active."""
        value = self.coordinator.data.get(self.entity_description.key)
        return value if isinstance(value, bool) else None
