"""Platform for switch integration."""
import logging
from typing import Union

from homeassistant.components.switch import SwitchEntity

from smartrent import BinarySwitch
from smartrent.api import API

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup switch platform."""
    client: API = hass.data["smartrent"][entry.entry_id]
    switches = client.get_switches()
    for switch in switches:
        async_add_entities([SwitchEnt(switch)])


class SwitchEnt(SwitchEntity):
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

    async def async_turn_on(self):
        await self.device.async_set_on(True)

    async def async_turn_off(self):
        await self.device.async_set_on(False)
