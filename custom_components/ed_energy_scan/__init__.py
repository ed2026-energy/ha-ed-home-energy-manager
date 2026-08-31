"""ED Energy Scan: leest lokaal welke apparaten HA al kent en welke onbekende
apparaten er op het netwerk zijn, en stuurt dat (alleen merk/model/vendor-fingerprints,
geen adresgegevens) naar de ED-catalogus-cloud voor review op embedded-design.nl.
"""
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
import datetime as dt

from .const import CONF_PAIRING_TOKEN, DEFAULT_API_BASE, DOMAIN, SCAN_INTERVAL_HOURS, SERVICE_SCAN_NOW
from .discovery import scan_known_devices, scan_unknown_devices

_LOGGER = logging.getLogger(__name__)


async def _run_scan(hass: HomeAssistant, pairing_token: str) -> None:
    known = scan_known_devices(hass)
    discovered = await scan_unknown_devices(hass)
    if not known and not discovered:
        _LOGGER.debug("Scan leverde niets op, niets te versturen.")
        return

    session = hass.helpers.aiohttp_client.async_get_clientsession()
    try:
        async with session.post(
            f"{DEFAULT_API_BASE}/ha/scan/ingest",
            json={"known": known, "discovered": discovered},
            headers={"x-pairing-token": pairing_token},
            timeout=aiohttp.ClientTimeout(total=60),
        ) as response:
            if response.status != 200:
                text = await response.text()
                _LOGGER.warning("Scan versturen mislukt (HTTP %s): %s", response.status, text)
            else:
                _LOGGER.info("Scan verstuurd: %d bekende, %d onbekende apparaten.", len(known), len(discovered))
    except aiohttp.ClientError as err:
        _LOGGER.warning("Scan versturen mislukt: %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    pairing_token = entry.data[CONF_PAIRING_TOKEN]

    async def _scheduled_scan(_now=None):
        await _run_scan(hass, pairing_token)

    async def _handle_scan_now(_call):
        await _run_scan(hass, pairing_token)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "unsub": async_track_time_interval(hass, _scheduled_scan, dt.timedelta(hours=SCAN_INTERVAL_HOURS)),
    }
    hass.services.async_register(DOMAIN, SERVICE_SCAN_NOW, _handle_scan_now)

    # Eerste scan meteen bij het toevoegen van de integratie, niet pas na 6 uur wachten.
    hass.async_create_task(_run_scan(hass, pairing_token))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and data.get("unsub"):
        data["unsub"]()
    return True
