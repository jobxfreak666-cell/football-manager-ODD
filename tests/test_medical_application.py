from __future__ import annotations

import __future__
import ast
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[1]
FACADE_METHODS = {
    "update_medical_treatment",
    "update_default_medical_treatment",
    "_process_due_medical_treatments",
    "_apply_default_medical_treatments",
}


class RecordingLock:
    """Context manager that records acquisition order and pairing."""

    def __init__(self, name: str, events: list[tuple[str, str]]) -> None:
        self.name = name
        self.events = events
        self._lock = threading.RLock()
        self.enters = 0
        self.exits = 0

    def __enter__(self) -> "RecordingLock":
        self.events.append(("enter", self.name))
        self._lock.acquire()
        self.enters += 1
        return self

    def __exit__(self, *_exc: object) -> bool:
        self.events.append(("exit", self.name))
        self._lock.release()
        self.exits += 1
        return False


def load_facade_class():
    """Load only the four real medical facade methods from the source file.

    ``fm_odds_web`` imports native modules at module import time, so the narrow
    class fragment is compiled in an explicit namespace.  The production import
    of ``tools.medical_application`` is taken from the source itself after the
    migration; it is never injected by this test.
    """
    source = (ROOT / "src" / "fm_odds_web.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    class_node = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LocalOddsState"
    )
    wanted = FACADE_METHODS | {"_medical_application"}
    methods = [
        node for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert {node.name for node in methods} >= FACADE_METHODS
    class_node.body = methods
    class_node.decorator_list = []
    service_imports = [
        node for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "tools.medical_application"
    ]
    module = ast.Module(body=[*service_imports, class_node], type_ignores=[])
    namespace: dict = {
        "read_game_clock": None,
        "welfare_status": None,
        "public_economy": None,
        "update_player_injury_treatment": None,
        "set_medical_treatment": None,
        "set_default_medical_treatment": None,
        "process_medical_treatments": None,
        "complete_player_medical_treatment": None,
        "apply_default_medical_treatments": None,
    }
    code = compile(
        module, str(ROOT / "src" / "fm_odds_web.py"), "exec",
        flags=__future__.annotations.compiler_flag,
    )
    exec(code, namespace)
    return namespace["LocalOddsState"], namespace


class MedicalHost:
    """Minimal runtime host for the loaded facade methods."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.memory_lock = RecordingLock("memory", self.events)
        self.lock = RecordingLock("state", self.events)
        self.output: dict = {"game_date": "2028-01-02"}
        self.club_profiles: dict = {}
        self.club_profile: dict | None = None
        self.club_medical_auto_result = None
        self.bind_count = 0
        self.live_calls: list[tuple[int, int]] = []
        self.live_result: tuple[dict | None, dict | None] = ({}, {})

    def _bind_current_save(self) -> None:
        self.bind_count += 1

    def _live_player_profile(self, player_id: int, requested_team_id: int):
        self.live_calls.append((player_id, requested_team_id))
        return self.live_result


@pytest.fixture()
def facade():
    return load_facade_class()


@pytest.fixture()
def io(monkeypatch, facade):
    _facade, namespace = facade
    mocks = {
        "read_game_clock": MagicMock(return_value={"date": "2028-01-02"}),
        "welfare_status": MagicMock(return_value={"treatments": {}}),
        "public_economy": MagicMock(return_value={"balance": 1}),
        "update_player_injury_treatment": MagicMock(return_value={"injuries": []}),
        "set_medical_treatment": MagicMock(return_value={"injuries": []}),
        "set_default_medical_treatment": MagicMock(return_value={"default_treatment": "manual"}),
        "process_medical_treatments": MagicMock(return_value={"pending": []}),
        "complete_player_medical_treatment": MagicMock(return_value=None),
        "apply_default_medical_treatments": MagicMock(return_value={"mode": "manual"}),
    }
    for name, mock in mocks.items():
        monkeypatch.setitem(namespace, name, mock)
    return mocks


def make_host(facade, *, profile=None, player=None) -> MedicalHost:
    if isinstance(facade, tuple):
        facade = facade[0]
    host = object.__new__(facade)
    MedicalHost.__init__(host)

    def bind_current_save() -> None:
        host.bind_count += 1

    def live_player_profile(player_id: int, requested_team_id: int):
        host.live_calls.append((player_id, requested_team_id))
        return host.live_result

    host._bind_current_save = MagicMock(side_effect=bind_current_save)
    host._live_player_profile = MagicMock(side_effect=live_player_profile)
    host.live_result = (
        profile if profile is not None else {"team": {"id": 20}},
        player if player is not None else {
            "id": 7, "name": "Seven", "address": "0xabc",
            "availability": {"injury_count": 3, "injuries": [{"start_date": "old"}]},
        },
    )
    return host


def test_old_manual_switch_transforms_injury_and_updates_availability(facade, io):
    host = make_host(facade)
    io["welfare_status"].return_value = {"treatments": {"7": {"factor": 1.5}}}
    io["update_player_injury_treatment"].return_value = {
        "injuries": [{"start_date": "2028-01-01"}], "native": "ok",
    }
    io["set_medical_treatment"].return_value = {
        "injuries": [{"start_date": "2028-01-01"}], "mode": "aggressive",
    }

    result = host.update_medical_treatment(
        {"player_id": 7, "team_id": 20, "mode": "aggressive"},
    )

    set_call = io["set_medical_treatment"].call_args
    assert set_call.args[:6] == (7, "Seven", 20, "0xabc", "aggressive", "2028-01-02")
    transform = set_call.args[6]
    assert transform(1.0, 1.5) == {
        "injuries": [{"start_date": "2028-01-01"}], "native": "ok",
    }
    io["update_player_injury_treatment"].assert_called_once_with(
        7, "0xabc", "2028-01-02", 1.0, 1.5,
    )
    # The old turnover reads the prior treatment factor even though it is unused.
    io["welfare_status"].assert_called()
    assert host.bind_count == 1
    assert host.live_calls == [(7, 20)]
    assert host.live_result[1]["availability"] == {
        "injuries": [{"start_date": "2028-01-01"}], "injury_count": 1,
    }
    assert result["treatment"]["mode"] == "aggressive"
    assert result["economy"] == {"balance": 1}
    assert result["welfare"] == {"treatments": {"7": {"factor": 1.5}}}
    assert host.events == [
        ("enter", "memory"), ("enter", "state"), ("exit", "state"),
        ("enter", "state"), ("exit", "state"), ("exit", "memory"),
    ]


@pytest.mark.parametrize(
    ("live_result", "message"),
    [
        ((None, {"id": 7}), "不属于当前执教球队"),
        (({"team": {"id": 20}}, None), "不属于当前执教球队"),
    ],
)
def test_old_missing_player_is_rejected_before_any_treatment(
    facade, io, live_result, message,
):
    host = make_host(facade)
    host.live_result = live_result
    with pytest.raises(ValueError, match=message):
        host.update_medical_treatment({"player_id": 7, "mode": "aggressive"})
    io["set_medical_treatment"].assert_not_called()
    io["welfare_status"].assert_not_called()


def test_old_missing_game_clock_is_rejected_before_any_treatment(facade, io):
    host = make_host(facade)
    host.output = {}
    io["read_game_clock"].return_value = {}
    with pytest.raises(ValueError, match="尚未读取当前游戏日期"):
        host.update_medical_treatment({"player_id": 7, "mode": "aggressive"})
    io["set_medical_treatment"].assert_not_called()


def test_old_update_default_forwards_snapshot_through_replacement_point(facade, io):
    host = make_host(facade)
    profile = {"team": {"id": 20}, "players": []}
    host.club_profiles = {"20": profile}
    snapshot = {"default_treatment": "aggressive", "treatments": {}}
    io["set_default_medical_treatment"].return_value = snapshot
    io["welfare_status"].return_value = {"treatments": {}}

    def set_default(mode):
        host.events.append(("call", "set_default"))
        return snapshot

    io["set_default_medical_treatment"].side_effect = set_default
    replacement = MagicMock(return_value={"mode": "aggressive", "applied": [7]})
    host._apply_default_medical_treatments = replacement

    result = host.update_default_medical_treatment({"mode": "aggressive"})

    io["set_default_medical_treatment"].assert_called_once_with("aggressive")
    replacement.assert_called_once_with(
        "2028-01-02", [profile], status=snapshot,
    )
    assert host.club_medical_auto_result == {"mode": "aggressive", "applied": [7]}
    assert result == {
        "economy": {"balance": 1},
        "welfare": {"treatments": {}},
        "auto_treatment": {"mode": "aggressive", "applied": [7]},
    }
    assert host.bind_count == 1
    assert host.events == [
        ("enter", "memory"), ("enter", "state"), ("exit", "state"),
        ("call", "set_default"),
        ("enter", "state"), ("exit", "state"), ("exit", "memory"),
    ]


def test_old_update_default_no_date_or_empty_profiles_publishes_none(facade, io):
    host = make_host(facade)
    host.club_profiles = {"20": {"team": {"id": 20}, "players": []}}
    io["read_game_clock"].return_value = {}
    host.output = {}
    replacement = MagicMock()
    host._apply_default_medical_treatments = replacement

    result = host.update_default_medical_treatment({"mode": "conservative"})

    io["set_default_medical_treatment"].assert_called_once_with("conservative")
    replacement.assert_not_called()
    assert host.club_medical_auto_result is None
    assert result["auto_treatment"] is None

    # Empty profiles fall back to the single club_profile snapshot.
    host2 = make_host(facade)
    host2.output = {"game_date": "2028-01-02"}
    host2.club_profiles = {}
    host2.club_profile = {"team": {"id": 30}, "players": []}
    replacement2 = MagicMock(return_value={"mode": "conservative"})
    host2._apply_default_medical_treatments = replacement2
    result2 = host2.update_default_medical_treatment({"mode": "conservative"})
    replacement2.assert_called_once_with(
        "2028-01-02", [host2.club_profile], status={"default_treatment": "manual"},
    )
    assert result2["auto_treatment"] == {"mode": "conservative"}

    host3 = make_host(facade)
    host3.club_profiles = {"20": {"team": {"id": 20}}}
    host3.club_profile = None
    replacement3 = MagicMock()
    host3._apply_default_medical_treatments = replacement3
    host3.output = {}
    io["read_game_clock"].return_value = {}
    assert host3.update_default_medical_treatment({})["auto_treatment"] is None
    replacement3.assert_not_called()


def test_old_process_due_resolved_ids_callbacks_and_unknown_players(facade, io):
    host = make_host(facade)
    injured = {
        "id": 1, "address": "0x1",
        "availability": {"injury_count": 1},
    }
    healthy = {
        "id": 2, "address": "0x2",
        "availability": {"injury_count": 0},
    }
    profiles = [{"team": {"id": 20}, "players": [injured, healthy, {"id": 0}]}]
    io["update_player_injury_treatment"].return_value = {
        "injuries": [{"start_date": "2028-01-01"}],
    }
    captured: dict = {}

    def process(game_date, injured_ids, cancel, complete, *, resolved_player_ids):
        captured.update(
            game_date=game_date, injured_ids=injured_ids, cancel=cancel,
            complete=complete, resolved_player_ids=resolved_player_ids,
        )
        return {"pending": [99]}

    io["process_medical_treatments"].side_effect = process

    result = host._process_due_medical_treatments("2028-01-02", profiles)

    assert result == {"pending": [99]}
    assert captured["game_date"] == "2028-01-02"
    assert captured["injured_ids"] == {1}
    assert captured["resolved_player_ids"] == {1, 2}
    assert host.lock.enters == 0
    # Cancel resolves the current player address and updates availability.
    captured["cancel"]({
        "player_id": 1, "factor": 0.5, "player_address": "stale",
    })
    io["update_player_injury_treatment"].assert_called_once_with(
        1, "0x1", "2028-01-02", 0.5, 1.0,
    )
    assert injured["availability"] == {
        "injuries": [{"start_date": "2028-01-01"}], "injury_count": 1,
    }
    # Completion forwards stored injury-start dates and the current address.
    captured["complete"]({
        "player_id": 2, "player_address": "stale",
        "injury_start_dates": ["2028-01-01", "2028-01-03"],
    })
    io["complete_player_medical_treatment"].assert_called_once_with(
        2, "0x2", "2028-01-02", ["2028-01-01", "2028-01-03"],
    )
    # Unknown player: wait, and fall back to the treatment's recorded address.
    captured["cancel"]({
        "player_id": 99, "factor": 1.25, "player_address": "0x99",
    })
    io["update_player_injury_treatment"].assert_called_with(
        99, "0x99", "2028-01-02", 1.25, 1.0,
    )
    captured["complete"]({
        "player_id": 99, "player_address": "0x98", "injury_start_dates": [],
    })
    io["complete_player_medical_treatment"].assert_called_with(
        99, "0x98", "2028-01-02", [],
    )
    assert healthy["availability"] == {"injury_count": 0}


def test_old_apply_default_copies_candidates_and_updates_original_player(facade, io):
    host = make_host(facade)
    original = {
        "id": 7, "name": "Seven", "address": "0xabc",
        "availability": {"injury_count": 1, "injuries": [{"start_date": "old"}]},
    }
    profile = {"team": {"id": 20}, "players": [original]}
    captured: dict = {}

    def apply(game_date, candidates, transform, *, status=None):
        captured.update(
            game_date=game_date, candidates=candidates,
            transform=transform, status=status,
        )
        return {"applied": []}

    io["apply_default_medical_treatments"].side_effect = apply
    io["update_player_injury_treatment"].return_value = {
        "injuries": [{"start_date": "2028-01-01"}],
    }

    result = host._apply_default_medical_treatments("2028-01-02", [profile])

    assert result == {"applied": []}
    assert captured["status"] is None
    candidate = captured["candidates"][0]
    assert candidate is not original
    assert candidate["team_id"] == 20
    assert candidate["_profile_player"] is original
    assert candidate["availability"] == {
        "injury_count": 1, "injuries": [{"start_date": "old"}],
    }
    captured["transform"](candidate, 1.0, 2.0)
    io["update_player_injury_treatment"].assert_called_once_with(
        7, "0xabc", "2028-01-02", 1.0, 2.0,
    )
    assert original["availability"] == {
        "injuries": [{"start_date": "2028-01-01"}], "injury_count": 1,
    }
    assert candidate["availability"]["injuries"] == [{"start_date": "old"}]
    io["apply_default_medical_treatments"].assert_called_once()
    assert io["apply_default_medical_treatments"].call_args.kwargs == {"status": None}
    assert host.lock.enters == 0


def test_dependencies_and_live_address_rebind_across_calls(facade, io, monkeypatch):
    _facade, namespace = facade
    host = make_host(facade)
    # Capture the first transform through the recorded call.
    host.update_medical_treatment({"player_id": 7, "mode": "aggressive"})
    first_transform = io["set_medical_treatment"].call_args.args[6]
    assert first_transform(1.0, 1.5) == {"injuries": []}
    io["update_player_injury_treatment"].assert_called_with(
        7, "0xabc", "2028-01-02", 1.0, 1.5,
    )

    # Replace every dependency and the live player address between calls.
    new_transform_source = MagicMock(return_value={"injuries": [{"start_date": "new"}]})
    new_clock = MagicMock(return_value={"date": "2028-02-03"})
    new_welfare = MagicMock(return_value={"treatments": {"7": {"factor": 2.0}}})
    new_set = MagicMock(return_value={"injuries": [{"start_date": "new"}]})
    monkeypatch.setitem(namespace, "read_game_clock", new_clock)
    monkeypatch.setitem(namespace, "welfare_status", new_welfare)
    monkeypatch.setitem(namespace, "update_player_injury_treatment", new_transform_source)
    monkeypatch.setitem(namespace, "set_medical_treatment", new_set)
    host.live_result[1]["address"] = "0xdef"

    host.update_medical_treatment({"player_id": 7, "team_id": 21, "mode": "none"})

    assert new_clock.called
    assert new_welfare.called
    assert new_set.called
    new_call = new_set.call_args
    assert new_call.args[:6] == (7, "Seven", 20, "0xdef", "none", "2028-02-03")
    assert new_call.args[6](1.0, 2.0) == {"injuries": [{"start_date": "new"}]}
    new_transform_source.assert_called_once_with(
        7, "0xdef", "2028-02-03", 1.0, 2.0,
    )
    io["set_medical_treatment"].assert_called_once()
    assert host.bind_count == 2
    assert host.live_calls == [(7, 0), (7, 21)]


# --- Direct application-service tests -------------------------------------

class ServiceRuntime:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.memory_lock = RecordingLock("memory", self.events)
        self.lock = RecordingLock("state", self.events)
        self.output: dict = {"game_date": "2028-01-02"}
        self.club_profiles: dict = {}
        self.club_profile: dict | None = None
        self.club_medical_auto_result = None
        self.bind_count = 0
        self.live_calls: list[tuple[int, int]] = []
        self.live_result: tuple[dict | None, dict | None] = ({}, {})
        self.default_calls: list[tuple] = []
        self.default_result: dict = {}

    def _bind_current_save(self) -> None:
        self.bind_count += 1

    def _live_player_profile(self, player_id: int, requested_team_id: int):
        self.live_calls.append((player_id, requested_team_id))
        return self.live_result

    def _apply_default_medical_treatments(
        self, game_date: str, profiles: list[dict], *, status=None,
    ) -> dict:
        self.default_calls.append((game_date, profiles, status))
        return self.default_result


def service_io(**overrides):
    from tools.medical_application import MedicalIO

    values = {
        "read_game_clock": MagicMock(return_value={"date": "2028-01-02"}),
        "welfare_status": MagicMock(return_value={"treatments": {}}),
        "public_economy": MagicMock(return_value={"balance": 1}),
        "update_player_injury_treatment": MagicMock(return_value={"injuries": []}),
        "set_medical_treatment": MagicMock(return_value={"injuries": []}),
        "set_default_medical_treatment": MagicMock(
            return_value={"default_treatment": "manual"},
        ),
        "process_medical_treatments": MagicMock(return_value={"pending": []}),
        "complete_player_medical_treatment": MagicMock(return_value=None),
        "apply_default_medical_treatments": MagicMock(return_value={"mode": "manual"}),
    }
    values.update(overrides)
    return MedicalIO(**values)


def test_service_import_is_independent_of_the_native_entrypoint():
    import tools.medical_application as application

    assert application.MedicalApplicationService
    assert application.MedicalIO
    source = Path(application.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "fm_odds_web" not in modules
    assert not any(
        isinstance(node, ast.ImportFrom) and (node.module or "").startswith("tools.club_reader")
        for node in ast.walk(tree)
    )


def test_service_update_treatment_transforms_and_updates_availability():
    from tools.medical_application import MedicalApplicationService

    runtime = ServiceRuntime()
    player = {
        "id": 7, "name": "Seven", "address": "0xabc",
        "availability": {"injury_count": 3, "injuries": [{"start_date": "old"}]},
    }
    runtime.live_result = ({"team": {"id": 20}}, player)
    update = MagicMock(return_value={"injuries": [{"start_date": "2028-01-01"}]})
    set_treatment = MagicMock(return_value={
        "injuries": [{"start_date": "2028-01-01"}], "mode": "aggressive",
    })
    io = service_io(
        update_player_injury_treatment=update,
        set_medical_treatment=set_treatment,
        welfare_status=MagicMock(return_value={"treatments": {"7": {"factor": 1.5}}}),
    )

    result = MedicalApplicationService(runtime, io).update_treatment(
        {"player_id": 7, "team_id": 20, "mode": "aggressive"},
    )

    assert set_treatment.call_args.args[:6] == (
        7, "Seven", 20, "0xabc", "aggressive", "2028-01-02",
    )
    assert set_treatment.call_args.args[6](1.0, 1.5) == {
        "injuries": [{"start_date": "2028-01-01"}],
    }
    update.assert_called_once_with(7, "0xabc", "2028-01-02", 1.0, 1.5)
    assert player["availability"] == {
        "injuries": [{"start_date": "2028-01-01"}], "injury_count": 1,
    }
    assert result["treatment"]["mode"] == "aggressive"
    assert result["economy"] == {"balance": 1}
    assert runtime.bind_count == 1
    assert runtime.events == [
        ("enter", "memory"), ("enter", "state"), ("exit", "state"),
        ("enter", "state"), ("exit", "state"), ("exit", "memory"),
    ]


def test_service_update_default_uses_the_runtime_replacement_point():
    from tools.medical_application import MedicalApplicationService

    runtime = ServiceRuntime()
    profile = {"team": {"id": 20}, "players": []}
    runtime.club_profiles = {"20": profile}
    snapshot = {"default_treatment": "aggressive", "treatments": {}}
    runtime.default_result = {"mode": "aggressive", "applied": [7]}
    set_default = MagicMock(return_value=snapshot)
    io = service_io(set_default_medical_treatment=set_default)

    result = MedicalApplicationService(runtime, io).update_default(
        {"mode": "aggressive"},
    )

    set_default.assert_called_once_with("aggressive")
    assert runtime.default_calls == [("2028-01-02", [profile], snapshot)]
    assert runtime.club_medical_auto_result == {
        "mode": "aggressive", "applied": [7],
    }
    assert result["auto_treatment"] == {"mode": "aggressive", "applied": [7]}
    assert runtime.bind_count == 1


def test_service_process_due_waits_for_unresolved_players():
    from tools.medical_application import MedicalApplicationService

    runtime = ServiceRuntime()
    injured = {"id": 1, "address": "0x1", "availability": {"injury_count": 1}}
    profiles = [{"team": {"id": 20}, "players": [injured, {"id": 2, "address": "0x2"}]}]
    captured: dict = {}

    def process(game_date, injured_ids, cancel, complete, *, resolved_player_ids):
        captured.update(
            game_date=game_date, injured_ids=injured_ids,
            cancel=cancel, complete=complete,
            resolved_player_ids=resolved_player_ids,
        )
        return {"pending": [99]}

    io = service_io(
        process_medical_treatments=MagicMock(side_effect=process),
        update_player_injury_treatment=MagicMock(
            return_value={"injuries": [{"start_date": "2028-01-01"}]},
        ),
    )

    result = MedicalApplicationService(runtime, io).process_due(
        "2028-01-02", profiles,
    )

    assert result == {"pending": [99]}
    assert captured["injured_ids"] == {1}
    assert captured["resolved_player_ids"] == {1, 2}
    assert runtime.lock.enters == 0
    captured["cancel"]({"player_id": 99, "factor": 1.25, "player_address": "0x99"})
    io.update_player_injury_treatment.assert_called_once_with(
        99, "0x99", "2028-01-02", 1.25, 1.0,
    )
    captured["complete"]({
        "player_id": 99, "player_address": "0x98",
        "injury_start_dates": ["2028-01-01"],
    })
    io.complete_player_medical_treatment.assert_called_once_with(
        99, "0x98", "2028-01-02", ["2028-01-01"],
    )


def test_service_apply_default_forwards_status_and_updates_original_player():
    from tools.medical_application import MedicalApplicationService

    runtime = ServiceRuntime()
    original = {
        "id": 7, "name": "Seven", "address": "0xabc",
        "availability": {"injury_count": 1},
    }
    profile = {"team": {"id": 20}, "players": [original]}
    captured: dict = {}
    status = {"default_treatment": "conservative", "treatments": {}}

    def apply(game_date, candidates, transform, *, status=None):
        captured.update(candidates=candidates, transform=transform, status=status)
        return {"applied": [7]}

    update = MagicMock(return_value={"injuries": [{"start_date": "2028-01-01"}]})
    io = service_io(
        apply_default_medical_treatments=MagicMock(side_effect=apply),
        update_player_injury_treatment=update,
    )

    result = MedicalApplicationService(runtime, io).apply_default(
        "2028-01-02", [profile], status=status,
    )

    assert result == {"applied": [7]}
    assert captured["status"] is status
    candidate = captured["candidates"][0]
    assert candidate["_profile_player"] is original
    assert candidate is not original
    captured["transform"](candidate, 1.0, 2.0)
    update.assert_called_once_with(7, "0xabc", "2028-01-02", 1.0, 2.0)
    assert original["availability"] == {
        "injuries": [{"start_date": "2028-01-01"}], "injury_count": 1,
    }
    assert runtime.lock.enters == 0
