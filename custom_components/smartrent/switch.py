"""Platform for switch integration."""
import logging
from typing import Any, Union

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.device_registry import DeviceEntryType
from smartrent import BinarySwitch
from smartrent.api import API

from .const import CONFIGURATION_URL, PROPER_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup switch platform."""
    client: API = hass.data["smartrent"][entry.entry_id]
    switches = client.get_binary_switches()
    for switch in switches:
        async_add_entities([SmartrentBinarySwitch(switch)])


class SmartrentBinarySwitch(SwitchEntity):
    def __init__(self, switch: BinarySwitch) -> None:
        super().__init__()
        self.device = switch

        self.device.start_updater()
        self.device.set_update_callback(self.async_schedule_update_ha_state)

    @property
    def should_poll(self):
        """Return the polling state, if needed."""
        return False

    @property
    def unique_id(self):
        return self.device._device_id

    @property
    def name(self):
        """Return the display name of this switch."""
        return self.device._name

    @property
    def is_on(self) -> Union[bool, None]:
        return self.device.get_on()

    async def async_turn_on(self, **kwargs: Any):
        await self.device.async_set_on(True)

    async def async_turn_off(self, **kwargs: Any):
        await self.device.async_set_on(False)

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
