"""Tests for the CC Agent Host integration (API mocked with aioclient_mock)."""

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cc_agent_host.const import CONF_API_KEY, DOMAIN

BASE = "http://local-cc-agent-host:8100"
DATA = {CONF_HOST: "local-cc-agent-host", CONF_PORT: 8100, CONF_API_KEY: "key"}
STATUS = {"version": "0.2.1", "claude_version": "2.1.287", "signed_in": True, "job_token": True,
          "plan": {"plan": "max_5x", "subscription": "max", "tier": "default_claude_max_5x", "multiplier": 5},
          "running": False, "running_profile": None, "profiles": ["read"]}
USAGE = {"source": "statusline", "available": True, "updated_at": 1790950000,
         "rate_limits": {"five_hour": {"used_percentage": 23.5, "resets_at": 1790958000},
                         "seven_day": {"used_percentage": 4, "resets_at": 1791489600}}}


def mock_api(aioclient_mock, status=STATUS, usage=USAGE):
    aioclient_mock.get(f"{BASE}/status", json=status)
    aioclient_mock.get(f"{BASE}/usage", json=usage)


async def setup(hass, aioclient_mock):
    mock_api(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_discovery_flow(hass: HomeAssistant, aioclient_mock):
    mock_api(aioclient_mock)
    info = HassioServiceInfo(config={"host": "local-cc-agent-host", "port": 8100, "api_key": "key"},
                             name="CC Agent Host", slug="local_cc_agent_host", uuid="1")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=info)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "hassio_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["data"] == DATA


async def test_rediscovery_updates_key(hass: HomeAssistant, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    info = HassioServiceInfo(config={"host": "local-cc-agent-host", "port": 8100, "api_key": "new"},
                             name="CC Agent Host", slug="local_cc_agent_host", uuid="1")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=info)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data[CONF_API_KEY] == "new"


async def test_user_flow_invalid_key(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/status", status=401, json={"error": "unauthorized"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "invalid_auth"}


async def test_entities(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock)
    assert hass.states.get("sensor.cc_agent_host_plan_usage_5_hour_window").state == "23.5"
    assert hass.states.get("sensor.cc_agent_host_plan_usage_weekly_window").state == "4"
    assert hass.states.get("sensor.cc_agent_host_5_hour_window_reset").state.startswith("2026-")
    assert hass.states.get("binary_sensor.cc_agent_host_signed_in").state == "on"
    assert hass.states.get("binary_sensor.cc_agent_host_job_running").state == "off"


async def test_usage_unavailable(hass: HomeAssistant, aioclient_mock):
    mock_api(aioclient_mock, usage={"source": "statusline", "available": False})
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.cc_agent_host_plan_usage_5_hour_window").state == "unknown"


async def test_run_action_returns_result(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock)
    aioclient_mock.post(f"{BASE}/run", json={"job_id": "x", "ok": True, "result": "hello", "cost_usd": 0.01})
    resp = await hass.services.async_call(DOMAIN, "run", {"profile": "read", "prompt": "hi"},
                                          blocking=True, return_response=True)
    assert resp["result"] == "hello"
    call = [c for c in aioclient_mock.mock_calls if c[0] == "POST"][0]
    assert call[2] == {"profile": "read", "prompt": "hi"}


@pytest.mark.parametrize(("status", "exc"), [(404, ServiceValidationError), (429, HomeAssistantError),
                                             (503, HomeAssistantError)])
async def test_run_action_errors(hass: HomeAssistant, aioclient_mock, status, exc):
    await setup(hass, aioclient_mock)
    aioclient_mock.post(f"{BASE}/run", status=status, json={"error": "nope"})
    with pytest.raises(exc):
        await hass.services.async_call(DOMAIN, "run", {"profile": "read", "prompt": "hi"},
                                       blocking=True, return_response=True)


async def test_auth_failure_starts_reauth(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/status", status=401, json={"error": "unauthorized"})
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_credit_sensors_from_usage_api(hass: HomeAssistant, aioclient_mock):
    usage = {**USAGE, "source": "api", "credits": [
        {"key": "x", "used": 30.27, "limit": 250, "remaining": 219.73, "resets_at": 1793865540}]}
    mock_api(aioclient_mock, usage=usage)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.cc_agent_host_usage_credit_used").state == "30.27"
    assert hass.states.get("sensor.cc_agent_host_usage_credit_remaining").state == "219.73"
    assert hass.states.get("sensor.cc_agent_host_usage_source").state == "api"


async def test_plan_sensor(hass: HomeAssistant, aioclient_mock):
    await setup(hass, aioclient_mock)
    st = hass.states.get("sensor.cc_agent_host_plan")
    assert st.state == "max_5x" and st.attributes["multiplier"] == 5 and st.attributes["subscription"] == "max"
