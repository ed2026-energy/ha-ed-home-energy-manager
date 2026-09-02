"""Eén sensor-entiteit per gescand apparaat met de opgehaalde programmering (standaard/
overrule/minimaal, 96 kwartier-slots) als attributen — zichtbaar/bruikbaar in HA-
automatiseringen en dashboards. Deze integratie stuurt hiermee zelf nog geen apparaten
aan; dat is een latere, merk-specifieke stap.
"""
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["schedule_coordinator"]
    known_device_ids: set[int] = set()

    def _sync_entities() -> None:
        devices = (coordinator.data or {}).get("devices", [])
        new_entities = [
            EnergyManagerScheduleSensor(coordinator, entry, device["deviceId"])
            for device in devices
            if device["deviceId"] not in known_device_ids
        ]
        if new_entities:
            known_device_ids.update(e.device_id for e in new_entities)
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


class EnergyManagerScheduleSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, device_id: int) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self.device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_schedule_{device_id}"

    def _device_data(self) -> dict | None:
        for device in (self.coordinator.data or {}).get("devices", []):
            if device["deviceId"] == self.device_id:
                return device
        return None

    @property
    def name(self) -> str:
        data = self._device_data()
        merk = (data or {}).get("merk") or "Onbekend"
        model = (data or {}).get("model") or ""
        return f"Programma {merk} {model}".strip()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_device_{self.device_id}")},
            name=(self._device_data() or {}).get("merk") or "Home Energy Manager-apparaat",
            manufacturer="Embedded Design",
            via_device=(DOMAIN, self._entry.entry_id),
        )

    @property
    def native_value(self) -> str | None:
        return (self.coordinator.data or {}).get("datum")

    @property
    def extra_state_attributes(self) -> dict:
        data = self._device_data() or {}
        return {
            "ruimte": data.get("ruimte"),
            "groep_slug": data.get("groepSlug"),
            "standaard": data.get("standaard"),
            "overrule": data.get("overrule"),
            "minimaal": data.get("minimaal"),
        }
