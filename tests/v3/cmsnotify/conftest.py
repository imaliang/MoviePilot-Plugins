"""Isolated SDK doubles for offline tests; this is not a MoviePilot host test."""

import importlib
import logging
import sys
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


class EventType(Enum):
    """Event values used by the V3 host."""

    TransferComplete = "transfer.complete"
    MetadataScrape = "metadata.scrape"


@pytest.fixture
def plugin_module(monkeypatch):
    """Import the real plugin in its production namespace with host boundaries stubbed."""
    registrations = []

    def register(events):
        def decorate(handler):
            registrations.extend(events if isinstance(events, list) else [events])
            return handler
        return decorate

    root = Path(__file__).resolve().parents[3]
    modules = {
        "app": {},
        "app.sdk": {},
        "app.schemas": {},
        "app.plugins": {"__path__": [str(root / "plugins.v3")]},
        "app.schemas.types": {"EventType": EventType},
        "app.sdk.events": {"eventmanager": SimpleNamespace(register=register), "Event": SimpleNamespace},
        "app.sdk.logging": {"logger": logging.getLogger("cmsnotify")},
        "app.sdk.network": {"RequestUtils": Mock()},
        "app.sdk.plugin": {"_PluginBase": object},
    }
    for name, attrs in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "app.plugins.cmsnotify", raising=False)
    module = importlib.import_module("app.plugins.cmsnotify")
    module.registrations = registrations
    yield module
    sys.modules.pop("app.plugins.cmsnotify", None)


@pytest.fixture
def plugin(plugin_module, monkeypatch):
    """Initialize using existing V2 configuration keys and a controlled clock."""
    monkeypatch.setattr(plugin_module.time, "time", lambda: 1000)
    instance = plugin_module.CMSNotify()
    instance.init_plugin({
        "enabled": True,
        "cms_domain": "https://cms.example/",
        "cms_api_token": "token&with=reserved?characters",
        "cms_notify_type": "auto_organize",
    })
    return instance
