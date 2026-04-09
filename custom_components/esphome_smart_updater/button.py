from homeassistant.components.button import ButtonEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    m = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        Start(m),
        Pause(m),
        Resume(m),
        Stop(m),
    ])


class Base(ButtonEntity):
    def __init__(self, m):
        self.m = m


class Start(Base):
    _attr_name = "ESU Start"
    async def async_press(self): await self.m.start()


class Pause(Base):
    _attr_name = "ESU Pause"
    async def async_press(self): await self.m.pause()


class Resume(Base):
    _attr_name = "ESU Resume"
    async def async_press(self): await self.m.resume()


class Stop(Base):
    _attr_name = "ESU Stop"
    async def async_press(self): await self.m.stop()
