"""Config flow: gebruiker plakt hier het pairing-token dat de website na inloggen toont."""
import voluptuous as vol

from homeassistant import config_entries

from .const import CONF_PAIRING_TOKEN, DOMAIN


class EdEnergyScanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            token = user_input[CONF_PAIRING_TOKEN].strip()
            if not token.startswith("ha_"):
                errors["base"] = "invalid_token"
            else:
                await self.async_set_unique_id(token[:16])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="ED Energy Scan", data={CONF_PAIRING_TOKEN: token})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_PAIRING_TOKEN): str}),
            errors=errors,
            description_placeholders={
                "info": "Log in op embedded-design.nl/#/energie/home-assistant en maak daar een pairing-token aan."
            },
        )
