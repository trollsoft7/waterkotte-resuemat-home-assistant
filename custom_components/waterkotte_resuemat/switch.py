"""Operating-mode switches for Waterkotte Resümat CD4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ResumatCoordinator
from .protocol import ResumatProtocolError, enabled_from_disabled_flag


@dataclass(frozen=True, kw_only=True)
class ResumatSwitchDescription(SwitchEntityDescription):
    """Describe a Resümat operating-mode switch."""


DESCRIPTIONS = (
    ResumatSwitchDescription(
        key="heating_disabled",
        translation_key="heating_enable_control",
    ),
    ResumatSwitchDescription(
        key="hot_water_disabled",
        translation_key="hot_water_enable_control",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up heating and hot-water enable switches."""
    coordinator: ResumatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ResumatSwitch(coordinator, entry, description)
        for description in DESCRIPTIONS
    )


class ResumatSwitch(CoordinatorEntity[ResumatCoordinator], SwitchEntity):
    """Represent a writable operating-mode enable flag."""

    _attr_has_entity_name = True
    entity_description: ResumatSwitchDescription

    def __init__(
        self,
        coordinator: ResumatCoordinator,
        entry: ConfigEntry,
        description: ResumatSwitchDescription,
    ) -> None:
        """Initialize the operating-mode switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.translation_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            manufacturer="Waterkotte",
            model="Resümat CD4",
            name="Waterkotte Resümat CD4",
        )

    @property
    def is_on(self) -> bool | None:
        """Return the actual enabled state reported by the controller."""
        value = self.coordinator.data.get(self.entity_description.key)
        if not isinstance(value, bool):
            return None
        return enabled_from_disabled_flag(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable this operating mode."""
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable this operating mode."""
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        """Write the selected mode and refresh the controller's actual state."""
        try:
            if self.entity_description.key == "heating_disabled":
                await self.coordinator.client.async_set_heating_enabled(enabled)
            else:
                await self.coordinator.client.async_set_hot_water_enabled(enabled)
        except (OSError, TimeoutError, ResumatProtocolError) as err:
            self.coordinator.client.set_status("error", str(err))
            self.coordinator.client.close()
            raise HomeAssistantError(
                f"Unable to update {self.entity_description.key}: {err}"
            ) from err

        self.hass.async_create_task(self.coordinator.async_request_refresh())
