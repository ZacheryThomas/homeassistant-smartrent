"""Platform for light integration."""
import logging
from typing import Any, Optional, Set

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    COLOR_MODE_BRIGHTNESS,
    LightEntity,
)
from homeassistant.helpers.device_registry import DeviceEntryType
from smartrent import MultilevelSwitch

from .const import CONFIGURATION_URL, DOMAIN, PROPER_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup climate platform."""
    client = hass.data[DOMAIN][entry.entry_id]
    ml_switches = client.get_multilevel_switches()
    for ml_switch in ml_switches:
        async_add_entities([SmartrentLight(ml_switch)])


class SmartrentLight(LightEntity):
    def __init__(self, ml_switch: MultilevelSwitch) -> None:
        super().__init__()

        self.device = ml_switch

        # Cache the level from smartrent.
        # Useful when light is turned on & we want to set it to the previous level
        # it was at when on last.
        self._prev_level_in_ha: int = self.device.get_level() or 50

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
        """Return the display name of this light."""
        return self.device._name

    @property
    def supported_color_modes(self) -> Optional[Set[str]]:
        """Return list of available color modes."""
        modes: Set[str] = set()
        modes.add(COLOR_MODE_BRIGHTNESS)
        return modes

    @property
    def color_mode(self) -> str:
        """Return the active color mode."""
        return COLOR_MODE_BRIGHTNESS

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return bool(self.device.get_level())

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        brightness = self.device.get_level()

        # store current level in case light turns off
        # & we have a refrence how bright light used to be
        self._prev_level_in_ha = brightness or self._prev_level_in_ha

        return round((brightness * 255.0) / 100.0)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if (brightness := kwargs.get(ATTR_BRIGHTNESS)) is not None:
            brightness = round((brightness * 100.0) / 255.0)

        brightness = brightness or self._prev_level_in_ha

        self._prev_level_in_ha = brightness
        await self.device.async_set_level(brightness)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self.device.async_set_level(0)

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
