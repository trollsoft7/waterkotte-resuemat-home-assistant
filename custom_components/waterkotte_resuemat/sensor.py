"""Sensors for Waterkotte Resümat CD4."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ResumatCoordinator


@dataclass(frozen=True, kw_only=True)
class ResumatSensorDescription(SensorEntityDescription):
    """Describe a Resümat measurement."""


DESCRIPTIONS = (
    ResumatSensorDescription(
        key="outdoor_temperature",
        translation_key="outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    ResumatSensorDescription(
        key="outdoor_temperature_24h",
        translation_key="outdoor_temperature_24h",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    ResumatSensorDescription(
        key="return_temperature_target",
        translation_key="return_temperature_target",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    ResumatSensorDescription(
        key="return_temperature",
        translation_key="return_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    ResumatSensorDescription(
        key="flow_temperature",
        translation_key="flow_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    ResumatSensorDescription(
        key="hot_water_temperature",
        translation_key="hot_water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    ResumatSensorDescription(
        key="source_inlet_temperature",
        translation_key="source_inlet_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    ResumatSensorDescription(
        key="source_outlet_temperature",
        translation_key="source_outlet_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    ResumatSensorDescription(
        key="compressor_operating_hours",
        translation_key="compressor_operating_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
    ),
    ResumatSensorDescription(
        key="heating_operating_hours",
        translation_key="heating_operating_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
    ),
    ResumatSensorDescription(
        key="hot_water_operating_hours",
        translation_key="hot_water_operating_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
    ),
    ResumatSensorDescription(
        key="heating_start_temperature",
        translation_key="heating_start_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
)

COMMUNICATION_STATES = (
    "disconnected",
    "connecting",
    "waking",
    "sending_request",
    "waiting_response",
    "receiving",
    "parsing",
    "idle",
    "error",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Resümat sensors."""
    coordinator: ResumatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            *(
                ResumatSensor(coordinator, entry, description)
                for description in DESCRIPTIONS
            ),
            ResumatCommunicationSensor(coordinator, entry),
        ]
    )


class ResumatSensor(CoordinatorEntity[ResumatCoordinator], SensorEntity):
    """Represent a Resümat measurement."""

    _attr_has_entity_name = True
    entity_description: ResumatSensorDescription

    def __init__(
        self,
        coordinator: ResumatCoordinator,
        entry: ConfigEntry,
        description: ResumatSensorDescription,
    ) -> None:
        """Initialize the sensor."""
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
        """Return the latest measurement."""
        value = self.coordinator.data.get(self.entity_description.key)
        return float(value) if isinstance(value, (int, float)) else None


class ResumatCommunicationSensor(
    CoordinatorEntity[ResumatCoordinator], SensorEntity
):
    """Expose serial communication progress and errors."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = True
    _attr_icon = "mdi:serial-port"
    _attr_translation_key = "communication_status"

    def __init__(
        self, coordinator: ResumatCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the communication status sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_communication_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            manufacturer="Waterkotte",
            model="Resümat CD4",
            name="Waterkotte Resümat CD4",
        )
        self._attr_options = list(COMMUNICATION_STATES)

    @property
    def native_value(self) -> str:
        """Return the current serial communication state."""
        return self.coordinator.client.status

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the selected port and the latest communication error."""
        attributes = {"serial_port": self.coordinator.client.port}
        if self.coordinator.client.last_error:
            attributes["last_error"] = self.coordinator.client.last_error
        return attributes
