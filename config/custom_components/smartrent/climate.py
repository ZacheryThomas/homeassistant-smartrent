"""Platform for lock integration."""
import logging
from smartrent import async_login, Thermostat

from typing import Union

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
# Import the device class from the component that you want to support
from homeassistant.components.climate import (PLATFORM_SCHEMA, ClimateEntity)

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, ATTR_TEMPERATURE, TEMP_FAHRENHEIT
from homeassistant.components.climate.const import (
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    HVAC_MODE_HEAT_COOL,
    SUPPORT_FAN_MODE,
    SUPPORT_TARGET_TEMPERATURE_RANGE,
    SUPPORT_TARGET_TEMPERATURE,
)

_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    # vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_USERNAME): cv.string,
    vol.Optional(CONF_PASSWORD): cv.string,
})

HA_STATE_TO_SMART_RENT = {
    HVAC_MODE_COOL: "cool",
    HVAC_MODE_HEAT: "heat",
    HVAC_MODE_OFF: "off",
    HVAC_MODE_HEAT_COOL: 'auto'
}
SMARTRENT_STATE_TO_HA = {value: key for key, value in HA_STATE_TO_SMART_RENT.items()}

SUPPORT_FAN = ['on', 'auto']
SUPPORT_HVAC = [HVAC_MODE_HEAT, HVAC_MODE_COOL, HVAC_MODE_OFF, HVAC_MODE_HEAT_COOL]

async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Awesome Light platform."""
    # Assign configuration variables.
    # The configuration check takes care they are present.
    username = config[CONF_USERNAME]
    password = config.get(CONF_PASSWORD)

    api = await async_login(username, password)

    thermostats = api.get_thermostats()
    for thermostat in thermostats:
        add_entities([ThermostatEntity(thermostat)])


class ThermostatEntity(ClimateEntity):
    def __init__(self, thermo: Thermostat) -> None:
        super().__init__()
        self.device = thermo

        import aiohttp
        self.device._session = aiohttp.ClientSession()

        self.last_desired_temp = None

        self.device.set_update_callback(
            self.async_schedule_update_ha_state
        )
        self.device.start_updater()

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
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE | SUPPORT_TARGET_TEMPERATURE_RANGE | SUPPORT_FAN_MODE

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_FAHRENHEIT

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
        if self.device.get_mode() == 'cool':
            return self.device.get_cooling_setpoint()
        elif self.device.get_mode() == 'heat':
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
        return SMARTRENT_STATE_TO_HA.get(self.device.get_mode(), None)

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return SUPPORT_HVAC

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target operation mode."""
        await self.device.async_set_mode(HA_STATE_TO_SMART_RENT.get(hvac_mode))

    async def async_set_temperature(self, **kwargs):
        _LOGGER.info(kwargs)
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature:
            if self.device.mode == 'cool':
                await self.device.async_set_cooling_setpoint(temperature)
            else:
                await self.device.async_set_heating_setpoint(temperature)

        tt_high = kwargs.get('target_temp_high')
        if tt_high:
            await self.device.async_set_cooling_setpoint(tt_high)

        tt_low = kwargs.get('target_temp_low')
        if tt_low:
            await self.device.async_set_heating_setpoint(tt_low)

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return self.device.get_fan_mode()

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""
        await self.device.async_set_fan_mode(fan_mode)

    @property
    def fan_modes(self):
        """List of available fan modes."""
        return SUPPORT_FAN

    # async def async_update(self):
    #     _LOGGER.error('FETCHING CLIMATE DATA!')
    #     pass
