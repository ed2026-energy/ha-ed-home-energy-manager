"""Scanlogica: bekende apparaten via HA's eigen registries, onbekende apparaten via
lokale ARP-tabel + MAC-OUI-vendorlookup (+ best-effort mDNS-servicenamen).

Verstuurt bewust geen IP-adressen of huishoudidentificerende data mee — alleen
merk/model/domain (bekend) of vendor/mDNS-naam (onbekend), consistent met de
privacybelofte op de website.
"""
import logging
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .oui_table import lookup_vendor

_LOGGER = logging.getLogger(__name__)


def scan_known_devices(hass: HomeAssistant) -> list[dict]:
    # Stuurt bewust ALLE devices uit de registry door, inclusief niet-fysieke
    # "software-devices" (HACS/Scheduler/etc.) — filteren gebeurt server-side
    # (ha/scan/ingest op de website), niet hier. Zo kan de filterlijst worden
    # bijgesteld zonder dat elke gebruiker deze integratie opnieuw hoeft te installeren.
    # entry_type wordt wel meegestuurd, want dat is het betrouwbaarste server-side signaal.
    registry = dr.async_get(hass)
    known = []
    for device in registry.devices.values():
        if not device.manufacturer and not device.model:
            continue
        domain = next(iter(device.identifiers), (None, None))[0]
        entry_type = getattr(device, "entry_type", None)
        known.append({
            "manufacturer": device.manufacturer,
            "model": device.model,
            "domain": domain,
            "deviceId": device.id,
            "entryType": getattr(entry_type, "value", entry_type),
        })
    return known


def _read_arp_table() -> list[tuple[str, str]]:
    """Leest de lokale ARP-tabel (ip -> mac). Geen netwerkverkeer, alleen wat het OS al weet."""
    entries = []
    try:
        with open("/proc/net/arp", encoding="utf-8") as handle:
            lines = handle.readlines()[1:]
        for line in lines:
            parts = line.split()
            if len(parts) >= 4:
                ip, _, _, mac = parts[0], parts[1], parts[2], parts[3]
                if mac != "00:00:00:00:00:00":
                    entries.append((ip, mac))
    except OSError:
        _LOGGER.debug("ARP-tabel niet beschikbaar op dit platform (verwacht op niet-Linux hosts).")
    return entries


async def scan_unknown_devices(hass: HomeAssistant) -> list[dict]:
    def _scan():
        discovered = []
        for _ip, mac in _read_arp_table():
            vendor = lookup_vendor(mac)
            if not vendor:
                continue
            # identificatie = geanonimiseerde vendor+laatste 3 octetten, geen IP en geen vol MAC-adres.
            identificatie = f"{vendor}:{mac.upper()[-8:]}"
            discovered.append({"vendor": vendor, "model": None, "identificatie": identificatie})
        return discovered

    return await hass.async_add_executor_job(_scan)
