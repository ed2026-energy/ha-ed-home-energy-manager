DOMAIN = "ed_energy_scan"
CONF_PAIRING_TOKEN = "pairing_token"
DEFAULT_API_BASE = "https://func-ed-scan-8827.azurewebsites.net/api"
SCAN_INTERVAL_HOURS = 6
SERVICE_SCAN_NOW = "scan_now"

# EnergyManager-programmering: standaard/overrule/minimaal per apparaat, elke dag
# opnieuw opgehaald zodat een bijgewerkte overrule (bv. na nieuwe netbelasting-
# berekening) binnen een kwartier zichtbaar is. Let op: deze integratie haalt de
# programmering alleen op en zet 'm neer als sensor-attributen — het merk-specifiek
# aansturen van een device (service calls naar de juiste entiteit) is nog niet
# geïmplementeerd en moet per merk apart worden toegevoegd.
SCHEDULE_POLL_MINUTES = 15
