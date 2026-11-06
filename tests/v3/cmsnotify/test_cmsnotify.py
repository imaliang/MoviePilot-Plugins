"""Regression tests for V3 events, batching, retries, and lifecycle isolation."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import EventType


def event(kind=EventType.MetadataScrape, storage="u115", as_dict=False):
    """Build the host's relevant FileItem/TransferInfo event payload."""
    item = {"storage": storage, "name": "Example.mkv"}
    item = item if as_dict else SimpleNamespace(**item)
    data = {"fileitem": item}
    if kind == EventType.TransferComplete:
        info = {"success": True, "target_diritem": item, "target_item": item}
        data = {"transferinfo": info if as_dict else SimpleNamespace(**info)}
    return SimpleNamespace(event_type=kind, event_data=data)


def run_service(plugin):
    """Invoke the callable registered with the host scheduler."""
    plugin.get_service()[0]["func"]()


def test_v3_market_entry():
    """V3 must select a dedicated implementation instead of the V2 fallback."""
    root = Path(__file__).resolve().parents[3]
    assert (root / "package.v3.json").exists(), "V3 marketplace index is missing"
    entry = json.loads((root / "package.v3.json").read_text())["CMSNotify"]
    assert entry["system_version"] == ">=3.0.0"
    assert entry["version"] == "1.0.0"
    assert json.loads((root / "package.v2.json").read_text())["CMSNotify"]["v3"] is False


@pytest.mark.parametrize("kind", list(EventType))
@pytest.mark.parametrize("storage", ["u115", "115网盘Plus", "CloudDrive储存"])
@pytest.mark.parametrize("as_dict", [False, True])
def test_v3_storage_events_are_batched(plugin, plugin_module, monkeypatch, kind, storage, as_dict):
    """Object and serialized FileItem payloads must cause a CMS request after the quiet period."""
    plugin.monitor(event(kind, storage, as_dict))
    client = plugin_module.RequestUtils.return_value
    client.get_res.return_value = SimpleNamespace(status_code=200)
    run_service(plugin)
    client.get_res.assert_not_called()
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1061)
    run_service(plugin)
    client.get_res.assert_called_once_with(
        "https://cms.example/api/sync/lift_by_token",
        params={"token": "token&with=reserved?characters", "type": "auto_organize"},
    )
    run_service(plugin)
    assert client.get_res.call_count == 1


def test_only_relevant_events_registered(plugin_module):
    """Avoid listening to unrelated host events and their payloads."""
    assert set(plugin_module.registrations) == set(EventType)


@pytest.mark.parametrize("payload", [None, {}, {"fileitem": None}, {"fileitem": {}}, {"fileitem": "local"}])
def test_incomplete_payload_does_not_notify(plugin, plugin_module, monkeypatch, payload):
    """Malformed scrape events must not crash or trigger a sync."""
    plugin.monitor(SimpleNamespace(event_type=EventType.MetadataScrape, event_data=payload))
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1100)
    run_service(plugin)
    plugin_module.RequestUtils.return_value.get_res.assert_not_called()


def test_failed_transfer_and_local_storage_are_ignored(plugin, plugin_module, monkeypatch):
    """Only successful cloud transfers should trigger sync."""
    failed = event(EventType.TransferComplete)
    failed.event_data["transferinfo"].success = False
    plugin.monitor(failed)
    plugin.monitor(event(storage="local"))
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1100)
    run_service(plugin)
    plugin_module.RequestUtils.return_value.get_res.assert_not_called()


@pytest.mark.parametrize("failure", [None, SimpleNamespace(status_code=500), RuntimeError("network failure")])
def test_failed_request_is_retried(plugin, plugin_module, monkeypatch, failure):
    """A failed CMS request must retain the pending batch for the next tick."""
    plugin.monitor(event())
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1100)
    client = plugin_module.RequestUtils.return_value
    client.get_res.side_effect = [failure, SimpleNamespace(status_code=200)]
    run_service(plugin)
    run_service(plugin)
    run_service(plugin)
    assert client.get_res.call_count == 2


def test_new_events_extend_quiet_period(plugin, plugin_module, monkeypatch):
    """A second event must defer notification until it has also been quiet for 60 seconds."""
    plugin.monitor(event())
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1050)
    plugin.monitor(event())
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1100)
    run_service(plugin)
    plugin_module.RequestUtils.return_value.get_res.assert_not_called()


def test_large_batch_notifies_without_waiting(plugin, plugin_module):
    """More than 1000 pending events preserve the original immediate-flush behavior."""
    for _ in range(1001):
        plugin.monitor(event())
    plugin_module.RequestUtils.return_value.get_res.return_value = SimpleNamespace(status_code=200)
    run_service(plugin)
    assert plugin_module.RequestUtils.return_value.get_res.call_count == 1


def test_stop_and_reinitialize_cancel_pending_batch(plugin, plugin_module, monkeypatch):
    """A stale scheduler callback must not send after stopping or clearing configuration."""
    callback = plugin.get_service()[0]["func"]
    plugin.monitor(event())
    plugin.stop_service()
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1100)
    callback()
    assert plugin.get_state() is False
    assert plugin.get_service() == []
    plugin.init_plugin(None)
    callback()
    plugin_module.RequestUtils.return_value.get_res.assert_not_called()


@pytest.mark.parametrize("kind", list(EventType))
def test_model_event_data_is_not_mutated(plugin, plugin_module, monkeypatch, kind):
    """V3 BaseEventData-style attribute access must work without changing shared payloads."""
    original = event(kind)
    original.event_data = SimpleNamespace(**original.event_data)
    plugin.monitor(original)
    if kind == EventType.TransferComplete:
        assert original.event_data.transferinfo.target_item.name == "Example.mkv"
    else:
        assert original.event_data.fileitem.name == "Example.mkv"
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1100)
    plugin_module.RequestUtils.return_value.get_res.return_value = SimpleNamespace(status_code=200)
    run_service(plugin)
    assert plugin_module.RequestUtils.return_value.get_res.call_count == 1


def test_transfer_without_target_directory_uses_target_file(plugin, plugin_module, monkeypatch):
    """The host allows a successful transfer with only target_item populated."""
    payload = event(EventType.TransferComplete)
    payload.event_data["transferinfo"].target_diritem = None
    plugin.monitor(payload)
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1100)
    plugin_module.RequestUtils.return_value.get_res.return_value = SimpleNamespace(status_code=200)
    run_service(plugin)
    assert plugin_module.RequestUtils.return_value.get_res.call_count == 1


def test_reloading_empty_config_disables_active_instance(plugin, plugin_module, monkeypatch):
    """Clearing config directly must not leave the previous enabled state and credentials active."""
    callback = plugin.get_service()[0]["func"]
    plugin.monitor(event())
    plugin.init_plugin(None)
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1100)
    callback()
    assert plugin.get_state() is False
    assert plugin.get_service() == []
    plugin_module.RequestUtils.return_value.get_res.assert_not_called()


def test_instances_do_not_share_pending_notifications(plugin, plugin_module, monkeypatch):
    """A second instance must not flush the first instance's pending events."""
    other = plugin_module.CMSNotify()
    other.init_plugin({"enabled": True, "cms_domain": "https://other.example", "cms_api_token": "other"})
    plugin.monitor(event())
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1100)
    run_service(other)
    plugin_module.RequestUtils.return_value.get_res.assert_not_called()


@pytest.mark.parametrize("missing", ["cms_domain", "cms_api_token"])
def test_incomplete_configuration_never_sends(plugin, plugin_module, monkeypatch, missing):
    """Enabling a plugin without its destination or credential must not send a request."""
    config = {"enabled": True, "cms_domain": "https://cms.example", "cms_api_token": "token"}
    config.pop(missing)
    plugin.init_plugin(config)
    plugin.monitor(event())
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1100)
    run_service(plugin)
    plugin_module.RequestUtils.return_value.get_res.assert_not_called()
