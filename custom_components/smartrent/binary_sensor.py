"""Platform for lock integration."""
import logging
from asyncio import create_task
from typing import Union

from homeassistant.components.binary_sensor import BinarySensorEntity

from smartrent import LeakSensor
from smartrent.api import API

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup lock platform."""
    client: API = hass.data["smartrent"][entry.entry_id]
    leak_sensors = client.get_leak_sensors()
    for leak_sensor in leak_sensors:
        async_add_entities([SensorEnt(leak_sensor)])


class SensorEnt(BinarySensorEntity):
    def __init__(self, leak_sensor: LeakSensor) -> None:
        super().__init__()
        self.device = leak_sensor

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
        """Return the display name of this leak sensor."""
        return self.device._name

    @property
    def device_class(self):
        return "moisture"

    @property
    def is_on(self) -> Union[bool, None]:
        return self.device.get_leak()
