"""
Custom integration to integrate integration_blueprint with Home Assistant.

For more details about this integration, please refer to
https://github.com/custom-components/integration_blueprint
"""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from smartrent import async_login

from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    PLATFORMS,
    STARTUP_MESSAGE,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    session = async_get_clientsession(hass)
    api = await async_login(username, password, session)

    hass.data[DOMAIN][entry.entry_id] = api

    if api.get_locks():
        hass.async_add_job(hass.config_entries.async_forward_entry_setup(entry, "lock"))

    if api.get_thermostats():
        hass.async_add_job(
            hass.config_entries.async_forward_entry_setup(entry, "climate")
        )

    entry.add_update_listener(async_reload_entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    api = hass.data[DOMAIN][entry.entry_id]
    for device in api.get_locks() + api.get_thermostats():
        device.stop_updater()

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
