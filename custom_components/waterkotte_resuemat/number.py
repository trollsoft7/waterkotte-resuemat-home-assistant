"""Number entities for Waterkotte Resümat CD4."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ResumatCoordinator


@dataclass(frozen=True, kw_only=True)
class ResumatNumberDescription(NumberEntityDescription):
    """Describe a writable Resümat setpoint."""

    address: int


DESCRIPTIONS = (
    ResumatNumberDescription(
        key="heating_setpoint",
        translation_key="heating_setpoint",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=5,
        native_max_value=60,
        native_step=0.5,
        mode=NumberMode.BOX,
        address=0x00F8,
    ),
    ResumatNumberDescription(
        key="hot_water_setpoint",
        translation_key="hot_water_setpoint",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=5,
        native_max_value=60,
        native_step=0.5,
        mode=NumberMode.BOX,
        address=0x013B,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Resümat setpoint controls."""
    coordinator: ResumatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ResumatNumber(coordinator, entry, description)
        for description in DESCRIPTIONS
    )


class ResumatNumber(CoordinatorEntity[ResumatCoordinator], NumberEntity):
    """Set a Resümat temperature setpoint."""

    entity_description: ResumatNumberDescription

    def __init__(
        self,
        coordinator: ResumatCoordinator,
        entry: ConfigEntry,
        description: ResumatNumberDescription,
    ) -> None:
        """Initialize the number."""
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
    def native_value(self) -> float | None:
        """Return the currently configured setpoint."""
        value = self.coordinator.data.get(self.entity_description.key)
        return float(value) if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        """Write a new setpoint and refresh the confirmed device state."""
        await self.coordinator.client.async_write_float(
            self.entity_description.address, value
        )
        await self.coordinator.async_request_refresh()
