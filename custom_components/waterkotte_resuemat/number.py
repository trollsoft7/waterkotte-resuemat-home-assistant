"""Number entities for Waterkotte Resümat CD4."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ResumatCoordinator
from .protocol import (
    MAX_HEATING_SETPOINT,
    MIN_HEATING_SETPOINT,
    ResumatProtocolError,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the heating target control."""
    coordinator: ResumatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ResumatHeatingSetpointNumber(coordinator, entry)])


class ResumatHeatingSetpointNumber(
    CoordinatorEntity[ResumatCoordinator], NumberEntity
):
    """Set and verify the heating target temperature."""

    entity_description = NumberEntityDescription(
        key="heating_setpoint_control",
        translation_key="heating_setpoint_control",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=MIN_HEATING_SETPOINT,
        native_max_value=MAX_HEATING_SETPOINT,
        native_step=0.5,
        mode=NumberMode.SLIDER,
    )
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ResumatCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the heating target control."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_heating_setpoint_control"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            manufacturer="Waterkotte",
            model="Resümat CD4",
            name="Waterkotte Resümat CD4",
        )

    @property
    def native_value(self) -> float | None:
        """Return the latest controller-reported heating target."""
        value = self.coordinator.data.get("heating_setpoint")
        return float(value) if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        """Write the target and update Home Assistant only after confirmation."""
        try:
            confirmed = await self.coordinator.client.async_set_heating_setpoint(
                value
            )
        except (OSError, TimeoutError, ResumatProtocolError) as err:
            self.coordinator.client.set_status("error", str(err))
            self.coordinator.client.close()
            raise HomeAssistantError(
                f"Heating target was not confirmed by the controller: {err}"
            ) from err

        updated_data = dict(self.coordinator.data)
        updated_data["heating_setpoint"] = confirmed
        self.coordinator.async_set_updated_data(updated_data)
