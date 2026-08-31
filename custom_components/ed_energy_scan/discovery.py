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

# Integraties die HA's device registry vullen met niet-fysieke "software-devices" (bv. één
# device per HACS-repo, met de GitHub-gebruikersnaam van de auteur als "manufacturer") —
# irrelevant voor deze scan, die alleen echte energie-/huishoudapparatuur wil vinden.
NON_HARDWARE_DOMAINS = {
    "hacs", "scheduler", "mobile_app", "persistent_notification", "met", "sun",
    "google_translate", "shopping_list", "tts", "stt", "wyoming", "rss_feed_template",
    "browser_mod", "spotcast", "lovelace_gen", "ed_energy_scan",
}


def scan_known_devices(hass: HomeAssistant) -> list[dict]:
    registry = dr.async_get(hass)
    known = []
    for device in registry.devices.values():
        # entry_type=SERVICE markeert HA-devices die geen fysiek apparaat zijn (precies wat
        # HACS/Scheduler/etc. gebruiken) — de belangrijkste filter, domain-lijst is een tweede
        # vangnet voor integraties die dat (nog) niet correct instellen.
        if getattr(device, "entry_type", None) is not None:
            continue
        if not device.manufacturer and not device.model:
            continue
        domain = next(iter(device.identifiers), (None, None))[0]
        if domain in NON_HARDWARE_DOMAINS:
            continue
        known.append({
            "manufacturer": device.manufacturer,
            "model": device.model,
            "domain": domain,
            "deviceId": device.id,
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
