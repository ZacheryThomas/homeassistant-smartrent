"""
Custom integration to integrate integration_blueprint with Home Assistant.

For more details about this integration, please refer to
https://github.com/custom-components/integration_blueprint
"""
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


def _install_token_persist_hook(
    hass: HomeAssistant, entry: ConfigEntry, api: API
) -> None:
    """Wrap the client's token refresh so every rotation is persisted immediately.

    The smartrent-py library rotates the refresh token on every call to
    ``_async_refresh_token`` (WebSocket reconnects, retries, etc.).  The old
    token is invalidated server-side, so we must persist the new one right away
    — waiting for ``async_unload_entry`` is not sufficient because a crash or
    power-off would leave a stale (invalidated) token on disk.
    """
    client = api.client
    original_refresh = client._async_refresh_token

    async def _persist_after_refresh() -> None:
        await original_refresh()
        new_token = client._refresh_token
        if new_token and new_token != entry.data.get(CONF_REFRESH_TOKEN):
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_REFRESH_TOKEN: new_token}
            )
            _LOGGER.debug("Persisted rotated refresh token")

    client._async_refresh_token = _persist_after_refresh


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    tfa_token = entry.data.get(CONF_TOKEN)
    stored_refresh_token = entry.data.get(CONF_REFRESH_TOKEN)

    session = async_get_clientsession(hass)
    try:
        if stored_refresh_token:
            try:
                api = API(username, password, session, tfa_token=tfa_token)
                api.client._refresh_token = stored_refresh_token
                await api.async_fetch_devices()
                _LOGGER.info("Rehydrated auth using stored refresh token")
            except (InvalidAuthError, KeyError):
                _LOGGER.warning(
                    "Stored refresh token rejected. Falling back to full login."
                )
                api = await async_login(username, password, session, tfa_token=tfa_token)
        else:
            api = await async_login(username, password, session, tfa_token=tfa_token)
    except InvalidAuthError as exception:
        raise ConfigEntryAuthFailed("Credentials expired!") from exception
    except ClientConnectorError as exception:
        raise ConfigEntryNotReady from exception
    except EOFError as exception:
        raise ConfigEntryAuthFailed("TFA not supplied. Please Reauth!") from exception

    _install_token_persist_hook(hass, entry, api)

    hass.data[DOMAIN][entry.entry_id] = api

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    api: API | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if api:
        for device in api.get_device_list():
            device.stop_updater()

    return unloaded
