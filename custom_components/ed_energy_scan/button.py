"""'Scan nu'-knop: verschijnt als apparaat/entiteit in HA (Apparaten-pagina, dashboards),
zodat je met één klik een scan kunt starten om een wijziging in je installatie te
bevestigen — in plaats van via Ontwikkelhulpmiddelen naar de scan_now-service te zoeken.
"""
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([EdEnergyScanButton(entry)])


class EdEnergyScanButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Scan nu"
    _attr_icon = "mdi:magnify-scan"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_scan_now"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Home Energy Manager",
            manufacturer="Embedded Design",
            entry_type="service",
        )

    async def async_press(self) -> None:
        data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if data and data.get("trigger_scan"):
            await data["trigger_scan"]()
