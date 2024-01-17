"""Platform for lock integration."""
import logging
from typing import Any, Union

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.helpers.device_registry import DeviceEntryType
from smartrent import DoorLock

from .const import CONFIGURATION_URL, PROPER_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup lock platform."""
    client = hass.data["smartrent"][entry.entry_id]
    locks = client.get_locks()
    for lock in locks:
        async_add_entities([SmartrentLock(lock)])


class SmartrentLock(LockEntity):
    def __init__(self, lock: DoorLock) -> None:
        super().__init__()
        self.device = lock
        self._attr_supported_features = LockEntityFeature.OPEN

        self.device.start_updater()
        self.device.set_update_callback(self.async_schedule_update_ha_state)

    @property
    def supported_features(self):
        """Flag supported features."""
        return LockEntityFeature.OPEN

    @property
    def should_poll(self):
        """Return the polling state, if needed."""
        return False

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self.device._device_id

    @property
    def name(self):
        """Return the display name of this lock."""
        return self.device._name

    @property
    def changed_by(self) -> Union[str, None]:
        return self.device.get_notification()

    @property
    def is_locked(self) -> Union[bool, None]:
        return self.device.get_locked()

    @property
    def is_jammed(self) -> Union[bool, None]:
        return "ALARM_TYPE_9" in str(self.device.get_notification())

    async def async_lock(self, **kwargs: Any):
        await self.device.async_set_locked(True)

    async def async_unlock(self, **kwargs: Any):
        await self.device.async_set_locked(False)

    @property
    def device_info(self):
        return dict(
            identifiers={("id", self.device._device_id)},
            name=str(self.name),
            manufacturer=PROPER_NAME,
            model=str(self.device.__class__.__name__),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=CONFIGURATION_URL,
        )
