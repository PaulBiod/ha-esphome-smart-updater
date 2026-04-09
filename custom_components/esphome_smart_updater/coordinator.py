from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)


class CampaignManager:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.state = "idle"
        self.queue: list[str] = []
        self.current: str | None = None
        self.done: list[str] = []
        self.failed: list[str] = []
        self._listeners = []

    def add_listener(self, cb) -> None:
        self._listeners.append(cb)

    def _push(self) -> None:
        for cb in self._listeners:
            cb()

    async def start(self) -> None:
        if self.state == "running":
            _LOGGER.warning("ESU start ignored: already running")
            return

        ent_reg = er.async_get(self.hass)
        all_updates = list(self.hass.states.async_entity_ids("update"))

        _LOGGER.warning("ESU start pressed")
        _LOGGER.warning("ESU total update.* found: %s", len(all_updates))

        selected = []

        for eid in all_updates:
            st = self.hass.states.get(eid)
            entry = ent_reg.async_get(eid)

            state_value = st.state if st else None
            friendly = st.attributes.get("friendly_name") if st else None
            title = st.attributes.get("title") if st else None
            installed = st.attributes.get("installed_version") if st else None
            latest = st.attributes.get("latest_version") if st else None
            entity_category = st.attributes.get("entity_category") if st else None

            platform = entry.platform if entry else None
            config_entry_id = entry.config_entry_id if entry else None

            _LOGGER.warning(
                "ESU candidate eid=%s state=%s platform=%s config_entry_id=%s friendly=%s title=%s installed=%s latest=%s entity_category=%s",
                eid,
                state_value,
                platform,
                config_entry_id,
                friendly,
                title,
                installed,
                latest,
                entity_category,
            )

            if not st:
                continue

            if st.state != "on":
                continue

            selected.append(eid)

        _LOGGER.warning("ESU selected after state==on: %s", selected)

        max_items = 3
        selected = selected[:max_items]

        _LOGGER.warning("ESU final queue (max %s): %s", max_items, selected)

        self.queue = selected
        self.done = []
        self.failed = []
        self.current = None
        self.state = "running" if self.queue else "idle"
        self._push()

        if self.queue:
            self.hass.async_create_task(self._run())
        else:
            _LOGGER.warning("ESU no eligible updates found, returning to idle")

    async def _run(self) -> None:
        _LOGGER.warning("ESU run started with queue=%s", self.queue)

        while self.queue:
            self.current = self.queue.pop(0)
            _LOGGER.warning("ESU installing current=%s remaining=%s", self.current, self.queue)
            self._push()

            try:
                await self.hass.services.async_call(
                    "update",
                    "install",
                    {"entity_id": self.current},
                    blocking=True,
                )
                _LOGGER.warning("ESU install service returned for %s", self.current)

                await asyncio.sleep(5)

                st = self.hass.states.get(self.current)
                _LOGGER.warning(
                    "ESU post-install state for %s => %s",
                    self.current,
                    st.state if st else None,
                )

                self.done.append(self.current)

            except Exception:
                _LOGGER.exception("ESU update failed for %s", self.current)
                self.failed.append(self.current)

            self.current = None
            self._push()

        self.state = "idle"
        _LOGGER.warning("ESU run finished done=%s failed=%s", self.done, self.failed)
        self._push()
