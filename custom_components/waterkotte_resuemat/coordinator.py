"""Data coordinator for the Resümat CD4."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .protocol import ResumatClient, ResumatProtocolError

_LOGGER = logging.getLogger(__name__)


class ResumatCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and share Resümat measurements."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: ResumatClient,
        update_interval: timedelta,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client
        self.config_entry = config_entry

    async def _async_update_data(self) -> dict[str, Any]:
        """Read both Node-RED data ranges from the heat pump."""
        try:
            return await self.client.async_read_data()
        except (OSError, TimeoutError, ResumatProtocolError) as err:
            self.client.close()
            raise UpdateFailed(f"Unable to read the Resümat CD4: {err}") from err
