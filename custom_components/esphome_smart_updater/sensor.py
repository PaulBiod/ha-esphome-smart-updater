from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    m = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        State(m),
        Current(m),
        Progress(m),
        Remaining(m),
        Done(m),
        Failed(m),
        Eta(m),
        Delay(m),
    ])


class Base(SensorEntity):
    def __init__(self, m):
        self.m = m

    async def async_added_to_hass(self):
        self.m.add_listener(self.async_write_ha_state)


class State(Base):
    _attr_name = "ESU State"
    @property
    def state(self): return self.m.state


class Current(Base):
    _attr_name = "ESU Current"
    @property
    def state(self): return self.m.current


class Progress(Base):
    _attr_name = "ESU Progress"
    @property
    def state(self): return self.m.progress()


class Remaining(Base):
    _attr_name = "ESU Remaining"
    @property
    def state(self): return len(self.m.queue)


class Done(Base):
    _attr_name = "ESU Done"
    @property
    def state(self): return len(self.m.done)


class Failed(Base):
    _attr_name = "ESU Failed"
    @property
    def state(self): return len(self.m.failed)


class Eta(Base):
    _attr_name = "ESU ETA"
    @property
    def state(self): return self.m.eta()


class Delay(Base):
    _attr_name = "ESU Delay"
    @property
    def state(self): return self.m.delay
