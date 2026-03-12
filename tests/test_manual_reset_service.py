"""Manual reset service tests for Duepi EVO."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.duepi_evo.const import DOMAIN

duepi_init = importlib.import_module("custom_components.duepi_evo.__init__")


class FakeRegistry:
    """Small fake entity registry for service resolution tests."""

    def __init__(self, entries: dict[str, SimpleNamespace]) -> None:
        self._entries = entries

    def async_get(self, entity_id: str) -> SimpleNamespace | None:
        """Return the fake entity-registry entry for an entity ID."""
        return self._entries.get(entity_id)


@pytest.mark.asyncio
async def test_manual_reset_calls_remote_reset_and_refresh() -> None:
    """The manual reset service should reset targeted Duepi EVO climates."""

    coordinator = SimpleNamespace(
        name="Pellet Stove",
        client=SimpleNamespace(remote_reset=Mock()),
        async_request_refresh=AsyncMock(),
    )

    async def _async_add_executor_job(func, *args):
        return func(*args)

    hass = SimpleNamespace(
        data={DOMAIN: {"entry-1": coordinator}},
        async_add_executor_job=AsyncMock(side_effect=_async_add_executor_job),
    )
    registry = FakeRegistry(
        {"climate.pellet_stove": SimpleNamespace(config_entry_id="entry-1")}
    )

    with (
        patch.object(
            duepi_init,
            "async_extract_entity_ids",
            AsyncMock(return_value={"climate.pellet_stove"}),
        ),
        patch.object(duepi_init.er, "async_get", return_value=registry),
    ):
        await duepi_init._async_handle_manual_reset(object(), hass)

    coordinator.client.remote_reset.assert_called_once_with("manual_reset")
    coordinator.async_request_refresh.assert_awaited_once()
    hass.async_add_executor_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_reset_rejects_non_climate_entities() -> None:
    """The manual reset service should reject targets outside the climate domain."""

    hass = SimpleNamespace(
        data={DOMAIN: {}},
        async_add_executor_job=AsyncMock(),
    )
    registry = FakeRegistry({})

    with (
        patch.object(
            duepi_init,
            "async_extract_entity_ids",
            AsyncMock(return_value={"sensor.pellet_stove_error_code"}),
        ),
        patch.object(duepi_init.er, "async_get", return_value=registry),
    ):
        with pytest.raises(HomeAssistantError, match="is not a climate entity"):
            await duepi_init._async_handle_manual_reset(object(), hass)
