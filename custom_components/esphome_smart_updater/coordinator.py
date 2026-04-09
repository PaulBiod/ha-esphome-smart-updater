from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "esphome_smart_updater"


class CampaignManager:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.running = False
        self.current = None
        self.queue = []

    async def start(self):
        if self.running:
            _LOGGER.info("ESU already running")
            return

        self.queue = self._find_updates()

        if not self.queue:
            _LOGGER.warning("ESU no updates found")
            return

        # 🔥 max_items = 1
        self.queue = self.queue[:1]

        _LOGGER.warning(f"ESU ESPHome queue: {self.queue}")

        self.running = True
        await self._process_next()

    async def _process_next(self):
        if not self.queue:
            _LOGGER.warning("ESU done")
            self.running = False
            self.current = None
            return

        entity_id = self.queue.pop(0)
        self.current = entity_id

        _LOGGER.warning(f"ESU updating {entity_id}")

        try:
            await self.hass.services.async_call(
                "update",
                "install",
                {"entity_id": entity_id},
                blocking=False,
            )
        except Exception as e:
            _LOGGER.error(f"ESU failed to start update {entity_id}: {e}")
            self.running = False
            return

        # 🔥 check toutes les 10s
        async_call_later(self.hass, 10, self._check_done)

    async def _check_done(self, *_):
        if not self.current:
            return

        state = self.hass.states.get(self.current)

        if not state:
            return

        in_progress = state.attributes.get("in_progress")

        if in_progress:
            _LOGGER.debug(f"ESU still updating {self.current}")
            async_call_later(self.hass, 10, self._check_done)
            return

        _LOGGER.warning(f"ESU finished {self.current}")

        self.current = None
        await self._process_next()

    def _find_updates(self):
        result = []

        for state in self.hass.states.async_all("update"):
            attrs = state.attributes

            if attrs.get("device_class") != "firmware":
                continue

            if not state.state == "on":
                continue

            result.append(state.entity_id)

        return result
