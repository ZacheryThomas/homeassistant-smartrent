"""Platform for sensor integration."""
from typing import Optional, Union

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceEntryType
from smartrent import DoorLock, LeakSensor, Thermostat
from smartrent.api import API

from .const import CONFIGURATION_URL, PROPER_NAME


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensor platform."""
    client: API = hass.data["smartrent"][entry.entry_id]

    for thermo in client.get_thermostats():
        async_add_entities(
            [
                SmartrentSensor(thermo, "current_temp", "temperature"),
                SmartrentSensor(thermo, "mode"),
            ]
        )
        if thermo.get_fan_mode():
            async_add_entities([SmartrentSensor(thermo, "fan_mode")])
        if thermo.get_current_humidity():
            async_add_entities(
                [SmartrentSensor(thermo, "current_humidity", "humidity")]
            )

    for lock in client.get_locks():
        async_add_entities(
            [
                SmartrentSensor(lock, "battery_level", "battery"),
                SmartrentSensor(lock, "notification"),
                SmartrentSensor(lock, "locked"),
            ]
        )

    for leak_sensor in client.get_leak_sensors():
        async_add_entities([SmartrentSensor(leak_sensor, "battery_level", "battery")])


class SmartrentSensor(SensorEntity):
    def __init__(
        self,
        device: Union[DoorLock, Thermostat, LeakSensor],
        sensor_name: str,
        device_class: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.device = device
        self.sensor_name = sensor_name
        self._device_class = device_class

        self.device.start_updater()
        self.device.set_update_callback(self.async_schedule_update_ha_state)

    @property
    def available(self) -> bool:
        return self.device.get_online()

    @property
    def should_poll(self):
        """Return the polling state, if needed."""
        return False

    @property
    def unique_id(self):
        sname_id = "".join([str(ord(char)) for char in self.sensor_name])
        uid = str(self.device._device_id) + str(sname_id)

        return uid

    @property
    def name(self):
        """Return the display name of this sensor."""
        return self.device._name + " " + self.sensor_name

    @property
    def native_value(self):
        """Return native value for entity."""
        return getattr(self.device, f"get_{self.sensor_name}")()

    @property
    def device_class(self):
        return self._device_class

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT if self._device_class else None

    @property
    def native_unit_of_measurement(self):
        if self._device_class == "temperature":
            return UnitOfTemperature.FAHRENHEIT
        if self._device_class in ["humidity", "battery"]:
            return PERCENTAGE

    @property
    def device_info(self):
        return dict(
            identifiers={("id", self.device._device_id)},
            manufacturer=PROPER_NAME,
            model=str(self.device.__class__.__name__),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=CONFIGURATION_URL,
        )
