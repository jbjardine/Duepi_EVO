"""Duepi EVO integration setup."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_extract_entity_ids

from .client import DuepiEvoClient, DuepiEvoClientError
from .const import (
    CONF_AUTO_RESET,
    CONF_INIT_COMMAND,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_NOFEEDBACK,
    DEFAULT_AUTO_RESET,
    DEFAULT_INIT_COMMAND,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_NAME,
    DEFAULT_NOFEEDBACK,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICE_MANUAL_RESET,
)
from .coordinator import DuepiEvoCoordinator
from .entity_migration import migrate_climate_entity_registry

SERVICE_MANUAL_RESET_SCHEMA = cv.make_entity_service_schema({})


def _build_client_from_entry(entry: ConfigEntry) -> DuepiEvoClient:
    """Build a client from a config entry."""
    return DuepiEvoClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        min_temp=float(entry.options.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)),
        max_temp=float(entry.options.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)),
        no_feedback=float(entry.options.get(CONF_NOFEEDBACK, DEFAULT_NOFEEDBACK)),
        auto_reset=bool(entry.options.get(CONF_AUTO_RESET, DEFAULT_AUTO_RESET)),
        init_command=bool(entry.options.get(CONF_INIT_COMMAND, DEFAULT_INIT_COMMAND)),
    )


async def _async_handle_manual_reset(call: ServiceCall, hass: HomeAssistant) -> None:
    """Handle a manual reset service call."""
    entity_ids = await async_extract_entity_ids(hass, call, expand_group=True)
    if not entity_ids:
        entity_id = call.data.get(ATTR_ENTITY_ID)
        if entity_id:
            entity_ids = {entity_id} if isinstance(entity_id, str) else set(entity_id)

    if not entity_ids:
        raise HomeAssistantError("No target entity provided")

    registry = er.async_get(hass)
    config_entry_ids: set[str] = set()

    for entity_id in entity_ids:
        if not entity_id.startswith("climate."):
            raise HomeAssistantError(f"Entity {entity_id} is not a climate entity")

        registry_entry = registry.async_get(entity_id)
        if registry_entry is None or registry_entry.config_entry_id is None:
            raise HomeAssistantError(f"Entity {entity_id} is not tied to a Duepi EVO config entry")

        if registry_entry.config_entry_id not in hass.data.get(DOMAIN, {}):
            raise HomeAssistantError(f"Entity {entity_id} is not managed by Duepi EVO")

        config_entry_ids.add(registry_entry.config_entry_id)

    for config_entry_id in config_entry_ids:
        coordinator: DuepiEvoCoordinator = hass.data[DOMAIN][config_entry_id]
        try:
            await hass.async_add_executor_job(coordinator.client.remote_reset, "manual_reset")
        except DuepiEvoClientError as err:
            raise HomeAssistantError(f"Reset failed for {coordinator.name}: {err}") from err

        await coordinator.async_request_refresh()


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services."""
    if hass.services.has_service(DOMAIN, SERVICE_MANUAL_RESET):
        return

    async def _handle_manual_reset(call: ServiceCall) -> None:
        await _async_handle_manual_reset(call, hass)

    hass.services.async_register(
        DOMAIN,
        SERVICE_MANUAL_RESET,
        _handle_manual_reset,
        schema=SERVICE_MANUAL_RESET_SCHEMA,
    )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Duepi EVO component."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Duepi EVO from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    migrate_climate_entity_registry(er.async_get(hass), entry)
    await _async_register_services(hass)

    client = _build_client_from_entry(entry)
    scan_interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    coordinator = DuepiEvoCoordinator(
        hass=hass,
        client=client,
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        update_interval=timedelta(seconds=scan_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
