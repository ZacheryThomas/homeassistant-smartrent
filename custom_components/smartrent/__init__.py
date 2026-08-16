"""
Custom integration to integrate integration_blueprint with Home Assistant.

For more details about this integration, please refer to
https://github.com/custom-components/integration_blueprint
"""

import logging
from typing import Any

from aiohttp.client_exceptions import ClientConnectorError
import voluptuous as vol
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, service
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.ssl import get_default_context
from smartrent import async_login
from smartrent.api import API
from smartrent.utils import InvalidAuthError

from .const import (
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    DOMAIN,
    PLATFORMS,
    SERVICE_CREATE_GUEST_CODE,
    SERVICE_DELETE_GUEST_CODE,
    SERVICE_GET_GUEST_CODES,
    SERVICE_UPDATE_GUEST_CODE,
    STARTUP_MESSAGE,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


def _positive_service_id(value: Any) -> int:
    """Validate an integer ID without truncating floats or accepting booleans."""
    if isinstance(value, bool):
        raise vol.Invalid("ID must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise vol.Invalid("ID must be a positive integer") from None
    if result < 1 or (isinstance(value, float) and not value.is_integer()):
        raise vol.Invalid("ID must be a positive integer")
    if isinstance(value, str) and value.strip() != str(result):
        raise vol.Invalid("ID must be a positive integer")
    return result


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register lock-targeted SmartRent guest access actions."""
    common_fields = {
        vol.Optional("activation_type"): vol.In(
            ("permanent", "temporary", "recurring")
        ),
        vol.Optional("first_name"): cv.string,
        vol.Optional("last_name"): cv.string,
        vol.Optional("phone"): cv.string,
        vol.Optional("email"): cv.string,
        vol.Optional("start_at"): cv.string,
        vol.Optional("end_at"): cv.string,
        vol.Optional("recurring_start_time"): cv.string,
        vol.Optional("recurring_end_time"): cv.string,
        vol.Optional("recurring_days"): vol.All(cv.ensure_list, [cv.string]),
    }

    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_GET_GUEST_CODES,
        entity_domain=LOCK_DOMAIN,
        schema=None,
        func=SERVICE_GET_GUEST_CODES,
        supports_response=SupportsResponse.ONLY,
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_CREATE_GUEST_CODE,
        entity_domain=LOCK_DOMAIN,
        schema={
            vol.Required("activation_type"): vol.In(
                ("permanent", "temporary", "recurring")
            ),
            vol.Required("first_name"): cv.string,
            vol.Required("last_name"): cv.string,
            vol.Optional("phone"): cv.string,
            vol.Optional("email"): cv.string,
            vol.Optional("start_at"): cv.string,
            vol.Optional("end_at"): cv.string,
            vol.Optional("recurring_start_time"): cv.string,
            vol.Optional("recurring_end_time"): cv.string,
            vol.Optional("recurring_days"): vol.All(cv.ensure_list, [cv.string]),
        },
        func=SERVICE_CREATE_GUEST_CODE,
        supports_response=SupportsResponse.ONLY,
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_UPDATE_GUEST_CODE,
        entity_domain=LOCK_DOMAIN,
        schema={
            vol.Required("code_id"): _positive_service_id,
            **common_fields,
        },
        func=SERVICE_UPDATE_GUEST_CODE,
        supports_response=SupportsResponse.ONLY,
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_DELETE_GUEST_CODE,
        entity_domain=LOCK_DOMAIN,
        schema={
            vol.Required("code_id"): _positive_service_id,
        },
        func=SERVICE_DELETE_GUEST_CODE,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy numeric IDs and generic device identifiers."""
    if entry.version != 1:
        return True

    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if entity_entry.unique_id is not None and not isinstance(
            entity_entry.unique_id, str
        ):
            entity_registry.async_update_entity(
                entity_entry.entity_id,
                new_unique_id=str(entity_entry.unique_id),
            )

    device_registry = dr.async_get(hass)
    for device_entry in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        identifiers = {
            (
                DOMAIN if identifier_domain == "id" else identifier_domain,
                str(identifier),
            )
            for identifier_domain, identifier in device_entry.identifiers
        }
        device_registry.async_update_device(
            device_entry.id,
            new_identifiers=identifiers,
            entry_type=None,
        )

    hass.config_entries.async_update_entry(entry, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    tfa_token = entry.data.get(CONF_TOKEN)

    session = async_get_clientsession(hass)
    try:
        api = await async_login(
            username,
            password,
            session,
            tfa_token=tfa_token,
            ssl_context=get_default_context(),
        )
    except InvalidAuthError as exception:
        raise ConfigEntryAuthFailed("Credentials expired!") from exception
    except ClientConnectorError as exception:
        raise ConfigEntryNotReady from exception
    except EOFError as exception:
        raise ConfigEntryAuthFailed("TFA not supplied. Please Reauth!") from exception

    hass.data[DOMAIN][entry.entry_id] = api

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    api: API = hass.data[DOMAIN][entry.entry_id]
    for device in api.get_device_list():
        device.stop_updater()

    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded
