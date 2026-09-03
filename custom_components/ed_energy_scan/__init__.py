"""Home Energy Manager (voorheen "ED Energy Component Scan"): leest lokaal welke apparaten
HA al kent en welke onbekende apparaten er op het netwerk zijn, stuurt dat (alleen merk/
model/vendor-fingerprints, geen adresgegevens) naar de embedded-design.nl-cloud voor
review, en haalt daar de opgeslagen programmering (standaard/overrule/minimaal per
apparaat) weer op om als sensor-attributen beschikbaar te maken.
"""
import logging
import uuid

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import datetime as dt

from .actuate import apply_schedule
from .const import CONF_PAIRING_TOKEN, DEFAULT_API_BASE, DOMAIN, SCAN_INTERVAL_HOURS, SCHEDULE_POLL_MINUTES, SERVICE_SCAN_NOW
from .discovery import scan_known_devices, scan_unknown_devices
from .schedule import async_fetch_schedule

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BUTTON, Platform.SENSOR]


def _host_mac() -> str:
    """MAC-adres van deze HA-host, als hex-string met dubbele punten — identificeert de
    fysieke woning voor de cloud (zie mergeIntoCanonicalInstallation in haScanIngest.js),
    onafhankelijk van hoe vaak er opnieuw gepaird wordt. uuid.getnode() valt bij
    ontbreken van een MAC terug op een willekeurig maar wél stabiel (per proces) getal —
    dat is voor deze dedup-doeleinden acceptabel, al is het dan geen écht hardware-MAC.
    """
    node = uuid.getnode()
    return ":".join(f"{(node >> shift) & 0xFF:02x}" for shift in range(40, -8, -8))


async def _run_scan(hass: HomeAssistant, pairing_token: str) -> None:
    try:
        known = scan_known_devices(hass)
        discovered = await scan_unknown_devices(hass)
    except Exception:  # noqa: BLE001 - een fout in het scannen mag de integratie nooit stilzwijgend laten hangen
        _LOGGER.exception("Scannen van apparaten mislukt")
        return

    if not known and not discovered:
        _LOGGER.debug("Scan leverde niets op, niets te versturen.")
        return

    session = async_get_clientsession(hass)
    try:
        async with session.post(
            f"{DEFAULT_API_BASE}/ha/scan/ingest",
            json={"known": known, "discovered": discovered, "hostMac": _host_mac()},
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

    async def trigger_scan() -> None:
        """Door de 'Scan nu'-knop (button.py) en de scan_now-service aangeroepen."""
        await _run_scan(hass, pairing_token)

    async def _scheduled_scan(_now=None):
        await trigger_scan()

    async def _handle_scan_now(_call):
        await trigger_scan()

    async def _update_schedule():
        data = await async_fetch_schedule(hass, pairing_token)
        if data is None:
            raise UpdateFailed("Programmering ophalen mislukt")
        # Ophalen en toepassen gebeuren bewust in dezelfde cyclus (geen aparte timer) —
        # apply_schedule respecteert zelf blokkades en de per-apparaat opt-in.
        await apply_schedule(hass, data)
        return data

    schedule_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_schedule",
        update_method=_update_schedule,
        update_interval=dt.timedelta(minutes=SCHEDULE_POLL_MINUTES),
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "unsub": async_track_time_interval(hass, _scheduled_scan, dt.timedelta(hours=SCAN_INTERVAL_HOURS)),
        "trigger_scan": trigger_scan,
        "schedule_coordinator": schedule_coordinator,
    }
    hass.services.async_register(DOMAIN, SERVICE_SCAN_NOW, _handle_scan_now)

    # async_refresh (niet async_config_entry_first_refresh) zodat een tijdelijk
    # onbereikbare schedule-endpoint het opzetten van de integratie niet blokkeert —
    # scannen moet blijven werken ook als de programmering-cloud even niet reageert.
    await schedule_coordinator.async_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Eerste scan meteen bij het toevoegen van de integratie, niet pas na 6 uur wachten.
    hass.async_create_task(trigger_scan())

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and data.get("unsub"):
        data["unsub"]()
    return unloaded
