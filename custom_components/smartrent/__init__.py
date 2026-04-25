"""
Custom integration to integrate integration_blueprint with Home Assistant.

For more details about this integration, please refer to
https://github.com/custom-components/integration_blueprint
"""
import asyncio
import logging

from aiohttp.client_exceptions import ClientConnectorError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from smartrent import async_login
from smartrent.api import API
from smartrent.utils import InvalidAuthError

from .const import (
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN,
    CONF_USERNAME,
    DOMAIN,
    PLATFORMS,
    STARTUP_MESSAGE,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


def _persist_refresh_token(hass: HomeAssistant, entry: ConfigEntry, api: API) -> None:
    """Save the client's current refresh token into the config entry."""
    new_refresh_token = api.client._refresh_token
    if new_refresh_token and new_refresh_token != entry.data.get(CONF_REFRESH_TOKEN):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_REFRESH_TOKEN: new_refresh_token}
        )


async def _async_login_with_refresh_token(
    entry: ConfigEntry, session, username, password, tfa_token
) -> API:
    """Try authenticating using a stored refresh token to avoid TFA prompts."""
    refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
    if not refresh_token:
        raise InvalidAuthError("No stored refresh token")

    api = API(username, password, session, tfa_token=tfa_token)
    api.client._refresh_token = refresh_token
    await api.async_fetch_devices()
    return api


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    tfa_token = entry.data.get(CONF_TOKEN)

    session = async_get_clientsession(hass)
    api = None

    if entry.data.get(CONF_REFRESH_TOKEN):
        try:
            api = await _async_login_with_refresh_token(
                entry, session, username, password, tfa_token
            )
            _LOGGER.debug("Authenticated using stored refresh token")
        except Exception as exc:
            _LOGGER.warning(
                "Refresh token login failed (%s), falling back to full login",
                type(exc).__name__,
            )
            api = None

    if api is None:
        try:
            api = await async_login(username, password, session, tfa_token=tfa_token)
        except InvalidAuthError as exception:
            raise ConfigEntryAuthFailed("Credentials expired!") from exception
        except ClientConnectorError as exception:
            raise ConfigEntryNotReady from exception
        except EOFError as exception:
            raise ConfigEntryAuthFailed(
                "TFA not supplied. Please Reauth!"
            ) from exception

    _persist_refresh_token(hass, entry, api)

    hass.data[DOMAIN][entry.entry_id] = api

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.add_update_listener(async_reload_entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    api: API = hass.data[DOMAIN][entry.entry_id]

    _persist_refresh_token(hass, entry, api)

    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    for device in api.get_device_list():
        device.stop_updater()

    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
