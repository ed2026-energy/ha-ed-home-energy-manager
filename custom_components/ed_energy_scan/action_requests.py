"""Verzoeken vanaf de website ("upgrade aanvragen" bij een merk-integratie) ophalen en
zo ver mogelijk voor de gebruiker klaarzetten.

Wat "uitvoeren" hier realistisch kan betekenen: als de doel-integratie (HA Core, of een
HACS-repo die de gebruiker al toegevoegd heeft) al op dit HA-systeem geïnstalleerd staat
maar nog niet geconfigureerd is, kunnen we de config-flow ervan programmatisch starten
(hass.config_entries.flow.async_init). Dat is de enige stap die een custom component zonder
supervisor-rechten mag doen — een HACS-repo die nog nergens geïnstalleerd staat kunnen we
NIET zelf downloaden/installeren (dat is HACS' eigen, niet-publieke interne API) en een
nieuwe Core-integratie kunnen we al helemaal niet on-the-fly wegschrijven.

In die gevallen zetten we voor de gebruiker een persistent notification in HA zelf klaar
met exact wat hij moet doen, inclusief een "My Home Assistant"-deeplink die zoveel mogelijk
al voor 'm klaarzet: bij een nog niet geïnstalleerde HACS-repo een link die direct naar de
downloadpagina van díe repo in HACS springt, bij een al geïnstalleerde maar nog niet
geconfigureerde integratie een link die het configuratiescherm ervoor meteen opent. Zo hoeft
de gebruiker nooit zelf te zoeken naar wat hij precies moet installeren/instellen.
"""
import logging
import re

import aiohttp

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import UnknownHandler
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_API_BASE

_LOGGER = logging.getLogger(__name__)

_GITHUB_REPO_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s#?]+)")


def _notification_id(request_id: int) -> str:
    return f"ed_energy_scan_upgrade_{request_id}"


def _hacs_repository_link(github_url: str | None) -> str | None:
    """My Home Assistant-deeplink die direct de HACS-downloadpagina van deze repo opent —
    scheelt de gebruiker het zelf opzoeken van de juiste repository in de HACS-store."""
    if not github_url:
        return None
    match = _GITHUB_REPO_RE.search(github_url)
    if not match:
        return None
    owner, repo = match.group(1), match.group(2).removesuffix(".git")
    return f"https://my.home-assistant.io/redirect/hacs_repository/?owner={owner}&repository={repo}&category=integration"


def _config_flow_start_link(domain: str) -> str:
    """My Home Assistant-deeplink die het "integratie toevoegen"-scherm voor dit domein
    direct opent — de gebruiker hoeft 'm dan alleen nog maar zelf in te vullen/bevestigen."""
    return f"https://my.home-assistant.io/redirect/config_flow_start/?domain={domain}"


def _notify(hass: HomeAssistant, request_id: int, merk: str, message: str) -> None:
    persistent_notification.async_create(
        hass,
        message,
        title=f"Home Energy Manager — actie nodig voor {merk}",
        notification_id=_notification_id(request_id),
    )


def _dismiss_notification(hass: HomeAssistant, request_id: int) -> None:
    persistent_notification.async_dismiss(hass, _notification_id(request_id))


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
    """Probeert de config-flow van het doel-domein te starten, en zet bij elke vorm van
    "kan niet automatisch" een persistent notification met concrete vervolgstap(pen) klaar
    in HA zelf. Geeft (gelukt, foutmelding) terug voor de terugmelding aan de website —
    'gelukt' betekent hier "de flow is afgerond of het was al geconfigureerd"."""
    request_id = req["id"]
    details = req.get("details") or {}
    domain = details.get("haCoreDomain")
    merk = req.get("merk") or "(onbekend merk)"
    hacs_link = _hacs_repository_link(details.get("githubUrl"))

    if not domain:
        if hacs_link:
            _notify(
                hass, request_id, merk,
                f"Voor **{merk}** is nog geen HA Core-domein bekend, maar wel een HACS-repository. "
                f"[Open de repository direct in HACS]({hacs_link}) en klik op **Downloaden**. Vraag de "
                f"upgrade daarna opnieuw aan op de website.",
            )
        else:
            _notify(
                hass, request_id, merk,
                f"Voor **{merk}** is nog geen automatische installatie mogelijk vanuit Home Assistant — "
                f"zoek de integratie handmatig op via HACS of Instellingen → Apparaten & diensten.",
            )
        return False, f"Geen HA-domein bekend voor {merk} — kan niet automatisch geïnstalleerd worden, notificatie klaargezet in HA."

    try:
        result = await hass.config_entries.flow.async_init(domain, context={"source": "user"})
    except UnknownHandler:
        if hacs_link:
            _notify(
                hass, request_id, merk,
                f"De integratie voor **{merk}** ({domain}) staat nog niet geïnstalleerd. "
                f"[Open de repository direct in HACS]({hacs_link}) en klik op **Downloaden** — herstart "
                f"Home Assistant daarna als HACS daarom vraagt. Vraag de upgrade hierna opnieuw aan op "
                f"de website, dan wordt 'm meteen verder geconfigureerd.",
            )
        else:
            handleiding = details.get("githubUrl") or details.get("homeAssistantUrl")
            _notify(
                hass, request_id, merk,
                f"De integratie voor **{merk}** ({domain}) staat nog niet geïnstalleerd op dit "
                f"HA-systeem. Voeg 'm eerst toe via HACS of Instellingen → Apparaten & diensten"
                f"{f' ({handleiding})' if handleiding else ''}, en vraag de upgrade daarna opnieuw aan.",
            )
        return False, f"Integratie voor {merk} ({domain}) staat nog niet geïnstalleerd — notificatie klaargezet in HA."
    except Exception as err:  # noqa: BLE001 - alle overige flow-fouten netjes als 'mislukt' terugmelden i.p.v. de hele poll-cyclus te laten crashen
        _LOGGER.exception("Config-flow starten voor %s (%s) mislukt", merk, domain)
        _notify(hass, request_id, merk, f"Er ging iets onverwachts mis bij het voorbereiden van **{merk}**: {err}")
        return False, f"Onverwachte fout bij het starten van de configuratie voor {merk}: {err}"

    if result["type"] == "create_entry":
        _LOGGER.info("Integratie voor %s (%s) succesvol geconfigureerd.", merk, domain)
        _dismiss_notification(hass, request_id)
        return True, None
    if result["type"] == "abort" and result.get("reason") == "already_configured":
        _LOGGER.info("Integratie voor %s (%s) was al geconfigureerd.", merk, domain)
        _dismiss_notification(hass, request_id)
        return True, None
    if result["type"] == "abort":
        _notify(hass, request_id, merk, f"Home Assistant brak de configuratie voor **{merk}** af: {result.get('reason')}.")
        return False, f"Configuratie voor {merk} afgebroken door Home Assistant: {result.get('reason')}"

    # 'form' (of iets anders wat verdere invoer vraagt, bv. OAuth) — kan niet zonder
    # gebruikersinvoer worden afgerond. De net gestarte flow zelf wordt afgebroken (die
    # blijft anders onzichtbaar hangen totdat 'ie verloopt) en vervangen door een
    # deeplink die exact hetzelfde scherm opnieuw en direct voor de gebruiker opent.
    await hass.config_entries.flow.async_abort(result["flow_id"])
    _notify(
        hass, request_id, merk,
        f"**{merk}** ({domain}) is geïnstalleerd maar vraagt nog invoer om te configureren "
        f"(bv. een API-sleutel of inloggegevens). "
        f"[Open het configuratiescherm direct]({_config_flow_start_link(domain)}) om 'm af te ronden.",
    )
    return False, f"Configuratie voor {merk} vraagt extra invoer van de gebruiker — notificatie met directe link klaargezet in HA."


async def async_process_action_requests(hass: HomeAssistant, pairing_token: str) -> None:
    requests = await async_fetch_action_requests(hass, pairing_token)
    if not requests:
        return
    for req in requests:
        ok, foutmelding = await _attempt_upgrade(hass, req)
        await _report_status(hass, pairing_token, req["id"], "uitgevoerd" if ok else "mislukt", foutmelding)
