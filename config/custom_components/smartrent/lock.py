"""Platform for lock integration."""
import logging
from smartrent import async_login,  DoorLock

from typing import Union

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
# Import the device class from the component that you want to support
from homeassistant.components.lock import (PLATFORM_SCHEMA, SUPPORT_OPEN, LockEntity)

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    # vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_USERNAME): cv.string,
    vol.Optional(CONF_PASSWORD): cv.string,
})


async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Awesome Light platform."""
    # Assign configuration variables.
    # The configuration check takes care they are present.
    username = config[CONF_USERNAME]
    password = config.get(CONF_PASSWORD)

    api = await async_login(username, password)
    locks = api.get_locks()
    for lock in locks:
        add_entities([LockEnt(lock)])
    _LOGGER.error('deleting locks?')

import datetime
SCAN_INTERVAL = datetime.timedelta(seconds=5)
class LockEnt(LockEntity):
    def __init__(self, lock: DoorLock) -> None:
        super().__init__()
        self.device = lock

        import aiohttp
        self.device._session = aiohttp.ClientSession()

        self.device.set_update_callback(
            self.async_schedule_update_ha_state
        )
        self.device.start_updater()
        self._attr_supported_features = SUPPORT_OPEN

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_OPEN

    @property
    def should_poll(self):
        """Return the polling state, if needed."""
        return False

    @property
    def unique_id(self):
        return self.device._device_id

    @property
    def name(self):
        """Return the display name of this lock."""
        return self.device._name

    @property
    def changed_by(self) -> str:
        return self.device.get_notification()

    @property
    def is_locked(self) -> Union[bool, None]:
        return self.device.get_locked()

    @property
    def is_jammed(self) -> Union[bool, None]:
        return "ALARM_TYPE_9" in self.device.get_notification()

    async def async_lock(self):
        await self.device.async_set_locked(True)
        _LOGGER.error(self.device.get_locked())

    async def async_unlock(self):
        await self.device.async_set_locked(False)

    async def async_update(self):
        _LOGGER.info('Calling lock update')
        # await self.device.fetch_state()
        pass

