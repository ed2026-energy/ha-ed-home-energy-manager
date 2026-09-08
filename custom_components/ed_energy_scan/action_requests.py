"""Verzoeken vanaf de website ("upgrade aanvragen" bij een merk-integratie) ophalen en
proberen lokaal uit te voeren.

Wat "uitvoeren" hier realistisch kan betekenen: als de doel-integratie (HA Core, of een
HACS-repo die de gebruiker al toegevoegd heeft) al op dit HA-systeem geïnstalleerd staat
maar nog niet geconfigureerd is, kunnen we de config-flow ervan programmatisch starten
(hass.config_entries.flow.async_init). Dat is de enige stap die een custom component zonder
supervisor-rechten mag doen — een HACS-repo die nog nergens geïnstalleerd staat kunnen we
NIET zelf downloaden/installeren (dat is HACS' eigen, niet-publieke interne API) en een
nieuwe Core-integratie kunnen we al helemaal niet on-the-fly wegschrijven. In die gevallen
melden we netjes 'mislukt' met een foutmelding die naar de HACS/HA Core-documentatie-URL
uit de aanvraag verwijst, zodat de gebruiker het zelf via de HA-UI kan afronden.
"""
import logging

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import UnknownHandler
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_API_BASE

_LOGGER = logging.getLogger(__name__)


async def async_fetch_action_requests(hass: HomeAssistant, pairing_token: str) -> list[dict] | None:
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            f"{DEFAULT_API_BASE}/ha/action-requests",
            headers={"x-pairing-token": pairing_token},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status != 200:
                text = await response.text()
                _LOGGER.warning("Actie-verzoeken ophalen mislukt (HTTP %s): %s", response.status, text)
                return None
            data = await response.json()
            return data.get("requests", [])
    except aiohttp.ClientError as err:
        _LOGGER.warning("Actie-verzoeken ophalen mislukt: %s", err)
        return None


async def _report_status(hass: HomeAssistant, pairing_token: str, request_id: int, status: str, foutmelding: str | None = None) -> None:
    session = async_get_clientsession(hass)
    body = {"status": status}
    if foutmelding:
        body["foutmelding"] = foutmelding
    try:
        async with session.patch(
            f"{DEFAULT_API_BASE}/ha/action-requests/{request_id}/status",
            json=body,
            headers={"x-pairing-token": pairing_token},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status != 200:
                text = await response.text()
                _LOGGER.warning("Status terugmelden mislukt voor verzoek %s (HTTP %s): %s", request_id, response.status, text)
    except aiohttp.ClientError as err:
        _LOGGER.warning("Status terugmelden mislukt voor verzoek %s: %s", request_id, err)


async def _attempt_upgrade(hass: HomeAssistant, req: dict) -> tuple[bool, str | None]:
    """Probeert de config-flow van het doel-domein te starten. Geeft (gelukt, foutmelding)
    terug — 'gelukt' betekent hier "de flow is afgerond of het was al geconfigureerd", niet
    per se "er staat nu een werkende integratie" (bv. bij een form-stap die verdere invoer
    van de gebruiker vraagt melden we dat expliciet als niet-gelukt, met uitleg)."""
    details = req.get("details") or {}
    domain = details.get("haCoreDomain")
    merk = req.get("merk") or "(onbekend merk)"

    if not domain:
        handleiding = details.get("githubUrl") or details.get("homeAssistantUrl")
        return False, (
            f"Geen HA-domein bekend voor {merk} — dit kan alleen handmatig via HACS "
            f"worden toegevoegd{f' ({handleiding})' if handleiding else ''}."
        )

    try:
        result = await hass.config_entries.flow.async_init(domain, context={"source": "user"})
    except UnknownHandler:
        handleiding = details.get("githubUrl") or details.get("homeAssistantUrl")
        return False, (
            f"De integratie voor {merk} ({domain}) staat nog niet geïnstalleerd op dit HA-systeem — "
            f"voeg 'm eerst toe via HACS of Instellingen → Apparaten & diensten"
            f"{f' ({handleiding})' if handleiding else ''}, en vraag de upgrade daarna opnieuw aan."
        )
    except Exception as err:  # noqa: BLE001 - alle overige flow-fouten netjes als 'mislukt' terugmelden i.p.v. de hele poll-cyclus te laten crashen
        _LOGGER.exception("Config-flow starten voor %s (%s) mislukt", merk, domain)
        return False, f"Onverwachte fout bij het starten van de configuratie voor {merk}: {err}"

    if result["type"] == "create_entry":
        _LOGGER.info("Integratie voor %s (%s) succesvol geconfigureerd.", merk, domain)
        return True, None
    if result["type"] == "abort" and result.get("reason") == "already_configured":
        _LOGGER.info("Integratie voor %s (%s) was al geconfigureerd.", merk, domain)
        return True, None
    if result["type"] == "abort":
        return False, f"Configuratie voor {merk} afgebroken door Home Assistant: {result.get('reason')}"

    # 'form' (of iets anders wat verdere invoer vraagt) — de flow staat nu open in HA, maar
    # kan niet zonder gebruikersinvoer worden afgerond. Netjes als 'mislukt' melden i.p.v.
    # doen alsof het gelukt is.
    hass.async_create_task(hass.config_entries.flow.async_abort(result["flow_id"]))
    return False, (
        f"Configuratie voor {merk} vraagt extra invoer — open Instellingen → Apparaten & diensten "
        f"in Home Assistant om 'm af te ronden."
    )


async def async_process_action_requests(hass: HomeAssistant, pairing_token: str) -> None:
    requests = await async_fetch_action_requests(hass, pairing_token)
    if not requests:
        return
    for req in requests:
        ok, foutmelding = await _attempt_upgrade(hass, req)
        await _report_status(hass, pairing_token, req["id"], "uitgevoerd" if ok else "mislukt", foutmelding)
