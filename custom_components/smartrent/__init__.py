"""
Custom integration to integrate integration_blueprint with Home Assistant.

For more details about this integration, please refer to
https://github.com/custom-components/integration_blueprint
"""
import asyncio
import logging

from aiohttp.client_exceptions import ClientConnectorError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from smartrent import async_login
from smartrent.api import API
from smartrent.utils import InvalidAuthError

from .const import (
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    DOMAIN,
    PLATFORMS,
    STARTUP_MESSAGE,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


@callback
def _migrate_unique_id(entry: er.RegistryEntry):
    """Rewrite a single integer unique ID as its string equivalent."""
    if isinstance(entry.unique_id, str):
        return None

    return {"new_unique_id": str(entry.unique_id)}


async def _async_migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Convert integer unique IDs written by earlier versions into strings.

    climate, light, lock, switch and binary_sensor used to return the SmartRent
    device id as a plain int. Home Assistant logs an error for every one of them
    ("has a non string unique_id") and intends to reject them outright.

    Rewriting has to happen before the platforms are set up. Without it the
    now-stringified unique IDs would not match the integers already in the
    registry, so every affected entity would be registered anew as
    `lock.front_door_lock_2` while the original stayed behind as an unavailable
    orphan -- silently breaking existing automations, dashboards and history.
    """
    await er.async_migrate_entries(hass, entry.entry_id, _migrate_unique_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    await _async_migrate_unique_ids(hass, entry)

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    tfa_token = entry.data.get(CONF_TOKEN)

    session = async_get_clientsession(hass)
    try:
        api = await async_login(username, password, session, tfa_token=tfa_token)
    except InvalidAuthError as exception:
        raise ConfigEntryAuthFailed("Credentials expired!") from exception
    except ClientConnectorError as exception:
        raise ConfigEntryNotReady from exception
    except EOFError as exception:
        raise ConfigEntryAuthFailed("TFA not supplied. Please Reauth!") from exception

    hass.data[DOMAIN][entry.entry_id] = api

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
    api: API = hass.data[DOMAIN][entry.entry_id]
    for device in api.get_device_list():
        device.stop_updater()

    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
