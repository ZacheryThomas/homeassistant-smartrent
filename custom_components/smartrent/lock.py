"""Platform for lock integration."""

import logging
from typing import Any, Awaitable, Callable, Union

from homeassistant.components.lock import LockEntity
from homeassistant.core import ServiceResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from smartrent import DoorLock

from .access_manager import (
    AccessOperationError,
    AccessValidationError,
    SmartRentAccessManager,
)
from .const import CONFIGURATION_URL, DOMAIN, PROPER_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup lock platform."""
    client = hass.data["smartrent"][entry.entry_id]
    locks = client.get_locks()
    for lock in locks:
        async_add_entities([SmartrentLock(lock, client)])


class SmartrentLock(LockEntity):
    def __init__(self, lock: DoorLock, client: Any) -> None:
        super().__init__()
        self.device = lock
        self._access_manager = SmartRentAccessManager(client, lock._device_id)

        self.device.start_updater()
        self.device.set_update_callback(self.async_schedule_update_ha_state)

    @property
    def should_poll(self):
        """Return the polling state, if needed."""
        return False

    @property
    def unique_id(self):
        """Return a unique ID."""
        return str(self.device._device_id)

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

    async def _async_access_action(
        self, action: Callable[[], Awaitable[ServiceResponse]]
    ) -> ServiceResponse:
        """Run an access action while keeping upstream payloads out of errors."""
        try:
            return await action()
        except AccessValidationError as exception:
            raise ServiceValidationError(str(exception)) from None
        except AccessOperationError as exception:
            raise HomeAssistantError(str(exception)) from None

    async def get_guest_codes(self) -> ServiceResponse:
        """Return guest codes only in this explicit action response."""
        return await self._async_access_action(
            self._access_manager.async_get_guest_codes
        )

    async def create_guest_code(self, **kwargs: Any) -> ServiceResponse:
        """Create and return a verified, server-generated guest code."""
        return await self._async_access_action(
            lambda: self._access_manager.async_create_guest_code(**kwargs)
        )

    async def update_guest_code(self, code_id: int, **kwargs: Any) -> ServiceResponse:
        """Update a guest code and return a PIN-free verified result."""
        return await self._async_access_action(
            lambda: self._access_manager.async_update_guest_code(code_id, **kwargs)
        )

    async def delete_guest_code(self, code_id: int) -> ServiceResponse:
        """Delete a guest code and return a PIN-free verified result."""
        return await self._async_access_action(
            lambda: self._access_manager.async_delete_guest_code(code_id)
        )

    @property
    def device_info(self):
        return dict(
            identifiers={(DOMAIN, str(self.device._device_id))},
            name=str(self.name),
            manufacturer=PROPER_NAME,
            model=str(self.device.__class__.__name__),
            configuration_url=CONFIGURATION_URL,
        )
