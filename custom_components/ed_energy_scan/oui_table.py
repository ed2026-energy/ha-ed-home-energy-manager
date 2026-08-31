"""Kleine, statische MAC-OUI (eerste 3 octetten) -> vendor-tabel.

Bewust géén externe lookup (privacy: geen MAC-adressen het huis uit — alleen de
vendor-naam die hieruit lokaal wordt afgeleid gaat naar de cloud). Niet uitputtend;
uitbreiden met veelvoorkomende smart-home-fabrikanten naarmate scans false negatives
opleveren.
"""

OUI_VENDORS = {
    "B0:B2:1C": "Shelly",
    "CC:50:E3": "Shelly",
    "44:17:93": "Sonoff/eWeLink",
    "A0:20:A6": "Sonoff/eWeLink",
    "18:FE:34": "Espressif (ESP-apparaat)",
    "24:0A:C4": "Espressif (ESP-apparaat)",
    "3C:61:05": "Espressif (ESP-apparaat)",
    "EC:FA:BC": "Xiaomi/Aqara",
    "78:11:DC": "Xiaomi/Aqara",
    "50:EC:50": "TP-Link Kasa/Tapo",
    "B0:4E:26": "TP-Link Kasa/Tapo",
    "68:57:2D": "Philips Hue (Signify)",
    "00:17:88": "Philips Hue (Signify)",
    "34:29:8F": "SolarEdge",
    "70:B3:D5": "GoodWe",
}


def lookup_vendor(mac: str) -> str | None:
    prefix = mac.upper()[0:8]
    return OUI_VENDORS.get(prefix)
