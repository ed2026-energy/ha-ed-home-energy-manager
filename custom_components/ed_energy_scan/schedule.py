"""Programmering ophalen bij de Home Energy Manager-cloud (embedded-design.nl): voor elk
gescand apparaat de resolved standaard/overrule/minimaal-programma's voor een dag
(96 kwartier-slots). Toepassen op specifieke merken/entiteiten gebeurt hier bewust
nog niet — dat vraagt per-merk service-call-mappings die nu nergens vastliggen.
"""
import logging

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_API_BASE

_LOGGER = logging.getLogger(__name__)


async def async_fetch_schedule(hass: HomeAssistant, pairing_token: str, datum: str | None = None) -> dict | None:
    session = async_get_clientsession(hass)
    params = {"datum": datum} if datum else None
    try:
        async with session.get(
            f"{DEFAULT_API_BASE}/ha/schedule",
            params=params,
            headers={"x-pairing-token": pairing_token},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status != 200:
                text = await response.text()
                _LOGGER.warning("Programmering ophalen mislukt (HTTP %s): %s", response.status, text)
                return None
            return await response.json()
    except aiohttp.ClientError as err:
        _LOGGER.warning("Programmering ophalen mislukt: %s", err)
        return None
