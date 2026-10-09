"""Switches for Waterkotte Resümat CD4."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ResumatCoordinator


@dataclass(frozen=True, kw_only=True)
class ResumatSwitchDescription(SwitchEntityDescription):
    """Describe a Resümat writable switch."""

    address: int
    disabled_key: str


DESCRIPTIONS = (
    ResumatSwitchDescription(
        key="heating_enabled",
        translation_key="heating_enabled",
        address=0x00F3,
        disabled_key="heating_disabled",
    ),
    ResumatSwitchDescription(
        key="hot_water_enabled",
        translation_key="hot_water_enabled",
        address=0x0134,
        disabled_key="hot_water_disabled",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Resümat switches."""
    coordinator: ResumatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ResumatSwitch(coordinator, entry, description)
        for description in DESCRIPTIONS
    )


class ResumatSwitch(CoordinatorEntity[ResumatCoordinator], SwitchEntity):
    """Control heating or hot-water enablement."""

    entity_description: ResumatSwitchDescription

    def __init__(
        self,
        coordinator: ResumatCoordinator,
        entry: ConfigEntry,
        description: ResumatSwitchDescription,
    ) -> None:
        """Initialize the switch."""
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
        """Return whether this function is enabled on the heat pump."""
        value = self.coordinator.data.get(self.entity_description.disabled_key)
        return not value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable the selected function."""
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable the selected function."""
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        """Write enablement and refresh the confirmed state."""
        await self.coordinator.client.async_write_enabled(
            self.entity_description.address, enabled
        )
        await self.coordinator.async_request_refresh()
