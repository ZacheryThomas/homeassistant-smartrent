"""Config flow to configure the SmartRent integration."""

import logging

from smartrent import async_login

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SmartRentFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a SmartRent config flow."""

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.data_schema = vol.Schema(
            {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
        )

    async def _show_form(self, errors=None):
        """Show the form to the user."""
        return self.async_show_form(
            step_id="user", data_schema=self.data_schema, errors=errors or {}
        )

    async def async_step_import(self, import_config):
        """Import a config entry from configuration.yaml."""
        return await self.async_step_user(import_config)

    async def async_step_user(self, user_input=None):
        """Handle the start of the config flow."""
        if not user_input:
            _LOGGER.info("no user input. showing form")
            return await self._show_form()

        await self.async_set_unique_id(user_input[CONF_USERNAME])
        self._abort_if_unique_id_configured()

        session = aiohttp_client.async_get_clientsession(self.hass)

        try:
            await async_login(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD], session
            )
        except Exception as exc:
            _LOGGER.error(f"exc: {exc}")
            return await self._show_form({"base": "invalid_auth"})

        _LOGGER.info(f"created entry!")
        return self.async_create_entry(title=user_input[CONF_USERNAME], data=user_input)
