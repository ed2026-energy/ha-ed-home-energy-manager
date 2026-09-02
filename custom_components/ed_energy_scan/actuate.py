"""Het opgehaalde schema (schedule.py) daadwerkelijk toepassen op apparaten — generiek,
niet per merk: de gebruiker vult op de website zelf de HA-entity_id in die het gewenste
vermogen (Watt) moet ontvangen (`sturing.vermogenEntity` per apparaat). Dat invullen is
zelf de opt-in; een apparaat zonder ingevulde entiteit wordt hier nooit aangeraakt.

Simpel eerste resolutiemodel voor de 3 programma-lagen (standaard/overrule/minimaal):
'overrule' overschrijft 'standaard' waar ingevuld, 'minimaal' werkt als vloer (het
effectieve doel wordt nooit lager dan 'minimaal'). De exacte betekenis van "hoger
vermogen" verschilt per apparaattype (batterij laden vs. omvormer vs. lader) — dat is
bewuste scope voor een latere verfijning, niet iets wat deze eerste versie oplost.

Blokkades (geblokkeerd/blokkadeReden, door haScheduleFetch.js meegegeven) worden altijd
gerespecteerd, ongeacht wat het programma zegt.
"""
import logging

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def current_slot_index(now=None) -> int:
    """Kwartier-index (0-95) van het huidige moment, lokale tijd."""
    import datetime as dt

    now = now or dt.datetime.now()
    return now.hour * 4 + now.minute // 15


def resolve_target_watt(device: dict, slot_index: int) -> float | None:
    """Effectief vermogens-doel voor 1 apparaat op 1 kwartier-slot, of None als er
    niets te sturen valt (geen enkele laag heeft voor dit slot een waarde)."""

    def slot_value(laag: str) -> float | None:
        slots = device.get(laag)
        if not slots or slot_index >= len(slots):
            return None
        slot = slots[slot_index]
        if not slot:
            return None
        return slot.get("vermogenW")

    target = slot_value("standaard")

    overrule = slot_value("overrule")
    if overrule is not None:
        target = overrule

    minimaal = slot_value("minimaal")
    if minimaal is not None:
        target = minimaal if target is None else max(target, minimaal)

    return target


async def _write_target_watt(hass: HomeAssistant, entity_id: str, watt: float) -> None:
    domain = entity_id.split(".", 1)[0]
    if domain == "number":
        service, field = "number.set_value", "value"
    elif domain == "input_number":
        service, field = "input_number.set_value", "value"
    else:
        _LOGGER.warning("Sturings-entiteit %s heeft een niet-ondersteund domain (%s) — alleen number/input_number.", entity_id, domain)
        return

    service_domain, service_name = service.split(".", 1)
    await hass.services.async_call(
        service_domain, service_name, {"entity_id": entity_id, field: watt}, blocking=True
    )
    _LOGGER.info("Home Energy Manager: %s -> %sW geschreven op %s", entity_id, watt, entity_id)


async def apply_schedule(hass: HomeAssistant, schedule_data: dict | None) -> None:
    if not schedule_data:
        return

    if schedule_data.get("geblokkeerd"):
        _LOGGER.info("Home Energy Manager: aansturing geblokkeerd voor de hele installatie (%s) — niets toegepast.", schedule_data.get("blokkadeReden") or "geen reden opgegeven")
        return

    slot_index = current_slot_index()

    for device in schedule_data.get("devices", []):
        if device.get("geblokkeerd"):
            _LOGGER.debug("Apparaat %s is geblokkeerd (%s) — overgeslagen.", device.get("deviceId"), device.get("blokkadeReden") or "geen reden opgegeven")
            continue

        sturing = device.get("sturing") or {}
        entity_id = sturing.get("vermogenEntity")
        if not entity_id:
            continue  # Geen sturings-entiteit ingevuld = geen opt-in, niets doen.

        target = resolve_target_watt(device, slot_index)
        if target is None:
            continue

        try:
            await _write_target_watt(hass, entity_id, target)
        except Exception:  # noqa: BLE001 - een mislukte write voor 1 apparaat mag de rest niet blokkeren
            _LOGGER.exception("Sturing schrijven mislukt voor apparaat %s (%s)", device.get("deviceId"), entity_id)
