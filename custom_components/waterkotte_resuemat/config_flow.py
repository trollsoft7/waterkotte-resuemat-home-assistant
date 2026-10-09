"""Config flow for Waterkotte Resümat CD4."""

from __future__ import annotations

from typing import Any

from serial.tools import list_ports
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


def _serial_port_options() -> list[dict[str, str]]:
    """Return attached serial ports for the setup selector."""
    return [
        {
            "label": f"{port.description} ({port.device})",
            "value": port.device,
        }
        for port in sorted(
            list_ports.comports(include_links=True),
            key=lambda item: item.device,
        )
    ]


class ResumatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Resümat CD4."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Set up the serial connection."""
        errors: dict[str, str] = {}
        ports = await self.hass.async_add_executor_job(_serial_port_options)
        if user_input is not None:
            port = user_input[CONF_PORT].strip()
            if not port:
                errors["base"] = "invalid_port"
            else:
                await self.async_set_unique_id(port)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Waterkotte Resümat CD4",
                    data={
                        CONF_PORT: port,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    },
                )

        port_selector = (
            SelectSelector(
                SelectSelectorConfig(
                    options=ports,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
            if ports
            else TextSelector()
        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_PORT): port_selector}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ResumatOptionsFlow:
        """Get the options flow."""
        return ResumatOptionsFlow(config_entry)


class ResumatOptionsFlow(config_entries.OptionsFlow):
    """Configure polling options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage polling options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL,
                            self.config_entry.data.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            ),
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                        ),
                    )
                }
            ),
        )
