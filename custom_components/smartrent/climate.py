"""Platform for climate integration."""
import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_ON,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceEntryType
from smartrent import Thermostat

from .const import CONFIGURATION_URL, DOMAIN, PROPER_NAME

_LOGGER = logging.getLogger(__name__)

HA_MODE_TO_SMART_RENT = {
    HVACMode.COOL: "cool",
    HVACMode.HEAT: "heat",
    HVACMode.OFF: "off",
    HVACMode.HEAT_COOL: "auto",
}
SMARTRENT_MODE_TO_HA = {value: key for key, value in HA_MODE_TO_SMART_RENT.items()}

HA_FAN_TO_SMART_RENT = {FAN_ON: "on", FAN_AUTO: "auto"}
SMARTRENT_FAN_TO_HA = {value: key for key, value in HA_FAN_TO_SMART_RENT.items()}

SUPPORT_FAN = [FAN_ON, FAN_AUTO]
SUPPORT_HVAC = [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF, HVACMode.HEAT_COOL]


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup climate platform."""
    client = hass.data[DOMAIN][entry.entry_id]
    thermostats = client.get_thermostats()
    for thermostat in thermostats:
        async_add_entities([SmartrentThermostat(thermostat)])


class SmartrentThermostat(ClimateEntity):
    def __init__(self, thermo: Thermostat) -> None:
        super().__init__()
        self.device = thermo

        self.device.start_updater()
        self.device.set_update_callback(self.async_schedule_update_ha_state)

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
        """Return the display name of this thermostat."""
        return self.device._name

    @property
    def supported_features(self):
        """Return the list of supported features."""

        # binary list of supported features
        supports_features = 0
        fan_mode = self.device.get_fan_mode()
        mode = self.device.get_mode()

        if mode in ["auto", "off"]:
            supports_features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE

        if mode in ["heat", "cool"]:
            supports_features |= ClimateEntityFeature.TARGET_TEMPERATURE

        # if fan has an active mode, assume fan option exists on thermostat
        if fan_mode:
            supports_features |= ClimateEntityFeature.FAN_MODE

        return supports_features

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return UnitOfTemperature.FAHRENHEIT

    @property
    def current_temperature(self):
        return self.device.get_current_temp()

    @property
    def target_temperature_high(self):
        return self.device.get_cooling_setpoint()

    @property
    def target_temperature_low(self):
        return self.device.get_heating_setpoint()

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self.device.get_mode() == "cool":
            return self.device.get_cooling_setpoint()
        elif self.device.get_mode() == "heat":
            return self.device.get_heating_setpoint()
        else:
            return self.device.get_current_temp()

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return 60

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return 90

    @property
    def current_humidity(self):
        return self.device.get_current_humidity()

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        smartrent_hvac_mode = self.device.get_mode()

        return SMARTRENT_MODE_TO_HA.get(smartrent_hvac_mode, None)

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return SUPPORT_HVAC

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target operation mode."""
        smartrent_hvac_mode = HA_MODE_TO_SMART_RENT.get(hvac_mode)

        await self.device.async_set_mode(smartrent_hvac_mode)

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature:
            if self.device.get_mode() == "cool":
                await self.device.async_set_cooling_setpoint(temperature)
            else:
                await self.device.async_set_heating_setpoint(temperature)

        tt_high = kwargs.get("target_temp_high")
        if tt_high:
            await self.device.async_set_cooling_setpoint(tt_high)

        tt_low = kwargs.get("target_temp_low")
        if tt_low:
            await self.device.async_set_heating_setpoint(tt_low)

    @property
    def fan_mode(self):
        """Return the fan setting."""
        smartrent_fan_mode = self.device.get_fan_mode()

        return SMARTRENT_FAN_TO_HA.get(smartrent_fan_mode, None)

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""
        smartrent_fan_mode = HA_FAN_TO_SMART_RENT.get(fan_mode)

        await self.device.async_set_fan_mode(smartrent_fan_mode)

    @property
    def fan_modes(self):
        """List of available fan modes."""
        return SUPPORT_FAN

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
