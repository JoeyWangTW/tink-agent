from types import SimpleNamespace
from tink_agent.menubar import TinkAgentApp


def _fake_app(capture):
    calls = []
    cfg = SimpleNamespace(device_name="USB Audio Device",
                          save=lambda: calls.append("save"))
    app = SimpleNamespace(
        config=cfg,
        capture=capture,
        stop_listening=lambda _: calls.append("stop"),
        start_listening=lambda _: calls.append("start"),
    )
    return app, calls


def test_set_device_name_persists_and_restarts_when_running():
    app, calls = _fake_app(SimpleNamespace(is_running=True))
    TinkAgentApp.set_device_name(app, "Built-in Microphone")
    assert app.config.device_name == "Built-in Microphone"
    assert calls == ["save", "stop", "start"]


def test_set_device_name_persists_without_restart_when_stopped():
    app, calls = _fake_app(None)
    TinkAgentApp.set_device_name(app, "Built-in Microphone")
    assert app.config.device_name == "Built-in Microphone"
    assert calls == ["save"]


def test_set_device_name_no_restart_when_capture_idle():
    app, calls = _fake_app(SimpleNamespace(is_running=False))
    TinkAgentApp.set_device_name(app, "Built-in Microphone")
    assert app.config.device_name == "Built-in Microphone"
    assert calls == ["save"]


def test_set_slot_action_persists_and_updates_live_router():
    calls = []
    cfg = SimpleNamespace(slot_actions={1: "enter"},
                          save=lambda: calls.append("save"))
    router = SimpleNamespace(slot_actions={1: "enter"})
    app = SimpleNamespace(config=cfg, engine=SimpleNamespace(router=router))

    TinkAgentApp.set_slot_action(app, 1, "type:continue")

    assert cfg.slot_actions[1] == "type:continue"   # persisted to config
    assert router.slot_actions[1] == "type:continue" # applied without restart
    assert calls == ["save"]


def test_set_slot_action_coerces_slot_to_int():
    cfg = SimpleNamespace(slot_actions={}, save=lambda: None)
    router = SimpleNamespace(slot_actions={})
    app = SimpleNamespace(config=cfg, engine=SimpleNamespace(router=router))
    TinkAgentApp.set_slot_action(app, "5", "down")
    assert cfg.slot_actions[5] == "down"


def test_restore_default_slot_actions_resets_and_updates_router():
    from tink_agent.config import Config
    calls = []
    cfg = SimpleNamespace(slot_actions={1: "noop", 2: "noop"},
                          save=lambda: calls.append("save"))
    router = SimpleNamespace(slot_actions={1: "noop"})
    app = SimpleNamespace(config=cfg, engine=SimpleNamespace(router=router))

    TinkAgentApp.restore_default_slot_actions(app)

    assert cfg.slot_actions == Config().slot_actions       # back to factory map
    assert router.slot_actions == Config().slot_actions     # applied to live router
    assert calls == ["save"]


def _enable_app():
    app, calls = _fake_app(None)
    app.engine = SimpleNamespace(enabled=True)
    app.config.enabled = True
    return app, calls


def test_disable_closes_mic_stream():
    app, calls = _enable_app()
    TinkAgentApp.set_enabled(app, False)
    assert app.engine.enabled is False and app.config.enabled is False
    assert calls == ["save", "stop"]


def test_enable_reopens_mic_stream():
    app, calls = _enable_app()
    TinkAgentApp.set_enabled(app, True)
    assert calls == ["save", "start"]
