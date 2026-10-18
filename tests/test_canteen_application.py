"""Task 3 canteen sea-cucumber application-boundary tests.

The facade fragment loader extracts only the four real ``LocalOddsState``
canteen methods from ``src/fm_odds_web.py``.  ``fm_odds_web`` imports the
native FM core at module import time, so the narrow class fragment is compiled
in an explicit namespace that includes the real native-free
``tools.player_effects`` transaction types/functions.  After migration the
loader also executes the production ``tools.canteen_application`` ImportFrom
statement from the source instead of manufacturing that import.
"""
from __future__ import annotations

import __future__
import ast
import inspect
import subprocess
import sys
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tools.player_effects import (
    PlayerEffectOperationError,
    PlayerEffectRollbackError,
    PlayerEffectTarget,
    PlayerEffectTransactionResult,
    commit_player_effect,
    describe_player_effect_error,
)


ROOT = Path(__file__).resolve().parents[1]
FACADE_METHODS = {
    "_canteen_sea_cucumber_one",
    "_canteen_sea_cucumber_context",
    "canteen_sea_cucumber",
    "canteen_sea_cucumbers",
}
NAMESPACE_NAMES = {
    "read_game_clock",
    "local_purchase_price",
    "CANTEEN_SEA_CUCUMBER_PRICE",
    "charge_combined_funds",
    "refund_combined_funds",
    "apply_canteen_sea_cucumber_effect",
    "apply_manager_intimacy_points",
    "restore_player_activity_effect",
    "canteen_sea_cucumber_memory_session",
    "public_economy",
}


class RecordingLock:
    """Context manager that records acquisition order and pairing."""

    def __init__(self, name: str, events: list[tuple[str, str]]) -> None:
        self.name = name
        self.events = events
        self._lock = threading.RLock()

    def __enter__(self) -> "RecordingLock":
        self.events.append(("enter", self.name))
        self._lock.acquire()
        return self

    def __exit__(self, *_exc: object) -> bool:
        self.events.append(("exit", self.name))
        self._lock.release()
        return False


def load_facade_class():
    source = (ROOT / "src" / "fm_odds_web.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    class_node = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LocalOddsState"
    )
    wanted = FACADE_METHODS | {"_canteen_application"}
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
        and node.module == "tools.canteen_application"
    ]
    module = ast.Module(body=[*service_imports, class_node], type_ignores=[])
    namespace: dict = {
        name: None for name in NAMESPACE_NAMES
    }
    namespace.update(
        commit_player_effect=commit_player_effect,
        describe_player_effect_error=describe_player_effect_error,
        PlayerEffectOperationError=PlayerEffectOperationError,
        PlayerEffectRollbackError=PlayerEffectRollbackError,
        PlayerEffectTarget=PlayerEffectTarget,
        PlayerEffectTransactionResult=PlayerEffectTransactionResult,
    )
    code = compile(
        module, str(ROOT / "src" / "fm_odds_web.py"), "exec",
        flags=__future__.annotations.compiler_flag,
    )
    exec(code, namespace)
    return namespace["LocalOddsState"], namespace


class Host:
    """Minimal runtime host for the loaded facade methods."""

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.memory_lock = RecordingLock("memory", self.events)
        self.lock = RecordingLock("state", self.events)
        self.output = {
            "manager": {"id": 7, "manager_address": "0x7000"},
            "selected_manager_id": 7,
            "game_date": "2026-07-24",
        }
        self.bind_count = 0
        self.target_calls: list[tuple] = []
        self.players = {
            42: {
                "id": 42, "name": "First", "address": "0x4200",
                "manager_intimacy": 12, "fitness": 74.0, "sharpness": 68.0,
            },
        }
        self.teams = {
            42: {"id": 9, "team_type": "club", "address": "0x9000"},
        }
        self.targets: dict[int, SimpleNamespace] = {}
        for player_id, player in self.players.items():
            team = self.teams[player_id]
            self.targets[player_id] = SimpleNamespace(
                player_id=player_id, team_id=int(team["id"]),
                address=str(player["address"]), player=player, team=team,
                profile={"team": team, "players": [player]},
            )


def make_host(facade) -> Host:
    if isinstance(facade, tuple):
        facade = facade[0]
    host = object.__new__(facade)
    Host.__init__(host)

    def bind_current_save() -> None:
        host.bind_count += 1

    def live_player_effect_target(
        player_id: int, requested_team_id: int, **kwargs,
    ):
        host.target_calls.append((player_id, requested_team_id, kwargs))
        return host.targets[int(player_id)]

    host._bind_current_save = bind_current_save
    host._live_player_effect_target = live_player_effect_target
    return host


@pytest.fixture()
def facade():
    return load_facade_class()


@pytest.fixture()
def io(monkeypatch, facade):
    _facade, namespace = facade
    payment = {"bank": 40_000.0, "wallet": 20_000.0, "total": 60_000.0}
    condition = {
        "field": "canteen_sea_cucumber",
        "fitness": {"field": "fitness", "before": 74.0, "after": 100.0},
        "sharpness": {"field": "sharpness", "before": 68.0, "after": 100.0},
        "_restores": [(0x1234, b"old-fitness")],
    }
    intimacy = {"before": 12, "after": 13, "applied": 1}
    mocks = {
        "read_game_clock": MagicMock(return_value={"date": "2026-07-24"}),
        "local_purchase_price": MagicMock(side_effect=lambda value: float(value)),
        "CANTEEN_SEA_CUCUMBER_PRICE": 60_000.0,
        "charge_combined_funds": MagicMock(return_value=payment),
        "refund_combined_funds": MagicMock(return_value=None),
        "apply_canteen_sea_cucumber_effect": MagicMock(return_value=condition),
        "apply_manager_intimacy_points": MagicMock(return_value=intimacy),
        "restore_player_activity_effect": MagicMock(return_value=None),
        "canteen_sea_cucumber_memory_session": MagicMock(
            return_value=nullcontext(MemorySession()),
        ),
        "public_economy": MagicMock(return_value={"bank_balance": 10}),
        "describe_player_effect_error": describe_player_effect_error,
        "commit_player_effect": MagicMock(wraps=commit_player_effect),
    }
    for name, mock in mocks.items():
        monkeypatch.setitem(namespace, name, mock)
    return mocks


class MemorySession:
    def __init__(self) -> None:
        self.restored: list = []

    def resolve_roster_player(self, player_id, team_id=0):
        return player_id, team_id

    def apply_effect(self, player_id, address):
        return {
            "field": "canteen_sea_cucumber",
            "fitness": {"before": 70.0, "after": 100.0},
            "sharpness": {"before": 70.0, "after": 100.0},
            "_restores": [(player_id, b"old")],
        }

    def apply_intimacy(self, player_id, *_args, **_kwargs):
        return {"before": 1, "after": 2, "applied": 1}

    def restore(self, condition):
        self.restored.append(condition)


def add_player(host: Host, player_id: int, team_type: str = "club") -> None:
    player = {
        "id": player_id, "name": f"Player {player_id}",
        "address": f"0x{player_id:x}00", "manager_intimacy": 5,
        "fitness": 80.0, "sharpness": 70.0,
    }
    team = {"id": 9, "team_type": team_type, "address": "0x9000"}
    host.players[player_id] = player
    host.teams[player_id] = team
    host.targets[player_id] = SimpleNamespace(
        player_id=player_id, team_id=int(team["id"]),
        address=str(player["address"]), player=player, team=team,
        profile={"team": team, "players": [player]},
    )


# ---------------------------------------------------------------------------
# Characterization of the four OLD facade methods (also valid after migration)
# ---------------------------------------------------------------------------

def test_old_single_converts_price_charges_bank_split_and_applies_effects(
    facade, io,
):
    host = make_host(facade)
    converted = {"bank": 120_000.0, "wallet": 60_000.0, "total": 180_000.0}
    io["local_purchase_price"].side_effect = None
    io["local_purchase_price"].return_value = 180_000.0
    io["charge_combined_funds"].return_value = converted
    events = host.events

    def clock():
        events.append(("call", "clock"))
        return {"date": "2026-07-24"}

    def charge(*args, **kwargs):
        events.append(("call", "charge", args, kwargs))
        return converted

    io["read_game_clock"].side_effect = clock
    io["charge_combined_funds"].side_effect = charge
    io["apply_canteen_sea_cucumber_effect"].side_effect = (
        lambda *a: events.append(("call", "effect", a)) or io[
            "apply_canteen_sea_cucumber_effect"
        ].return_value
    )
    io["apply_manager_intimacy_points"].side_effect = (
        lambda *a, **k: events.append(("call", "intimacy", a, k)) or io[
            "apply_manager_intimacy_points"
        ].return_value
    )
    io["public_economy"].side_effect = (
        lambda: events.append(("call", "economy")) or {"bank_balance": 10}
    )

    result = host.canteen_sea_cucumber({"player_id": 42, "team_id": 9})

    io["local_purchase_price"].assert_called_once_with(60_000.0)
    assert io["charge_combined_funds"].call_args.args[:2] == (
        180_000.0, "canteen_sea_cucumber",
    )
    assert io["charge_combined_funds"].call_args.kwargs == {
        "player_id": 42, "player_name": "First", "manager_id": 7,
        "team_id": 9, "game_date": "2026-07-24",
    }
    assert result["price_gbp"] == 180_000.0
    assert result["payment"] == converted
    assert result["payment"]["bank"] == 120_000.0
    assert result["payment"]["wallet"] == 60_000.0
    assert result["fitness"]["after"] == 100.0
    assert result["sharpness"]["after"] == 100.0
    assert result["intimacy"]["applied"] == 1
    assert "_restores" not in result["condition"]
    assert all(not key.startswith("_") for key in result["condition"])
    assert host.players[42]["fitness"] == 100.0
    assert host.players[42]["sharpness"] == 100.0
    assert host.players[42]["manager_intimacy"] == 13
    assert result["economy"] == {"bank_balance": 10}
    order = [event[1] for event in events if event[0] == "call"]
    assert order == ["clock", "charge", "effect", "intimacy", "economy"]
    assert [event[1] for event in events if event[0] in {"enter", "exit"}] == [
        "memory", "state", "state", "state", "state", "memory",
    ]
    assert host.bind_count == 1


def test_old_national_team_is_rejected_before_any_charge(facade, io):
    host = make_host(facade)
    host.teams[42]["team_type"] = "national"
    with pytest.raises(ValueError, match="国家队球员不能使用球队食堂奖励"):
        host.canteen_sea_cucumber({"player_id": 42})
    io["charge_combined_funds"].assert_not_called()
    io["apply_canteen_sea_cucumber_effect"].assert_not_called()
    io["apply_manager_intimacy_points"].assert_not_called()


def test_old_intimacy_failure_restores_once_and_refunds_exact_payment(facade, io):
    host = make_host(facade)
    payment = {"bank": 60_000.0, "wallet": 0.0, "total": 60_000.0}
    io["charge_combined_funds"].return_value = payment
    io["apply_manager_intimacy_points"].side_effect = RuntimeError("write failed")
    restore = MagicMock()
    io["restore_player_activity_effect"].side_effect = restore
    condition = io["apply_canteen_sea_cucumber_effect"].return_value

    with pytest.raises(RuntimeError, match="write failed"):
        host.canteen_sea_cucumber({"player_id": 42})

    restore.assert_called_once_with(condition)
    io["refund_combined_funds"].assert_called_once_with(
        payment, "canteen_sea_cucumber_rollback",
        player_id=42, player_name="First",
    )
    assert host.players[42]["fitness"] == 74.0
    assert host.players[42]["manager_intimacy"] == 12


def test_old_effect_failure_refunds_without_a_restore(facade, io):
    host = make_host(facade)
    payment = {"bank": 60_000.0, "wallet": 0.0, "total": 60_000.0}
    io["charge_combined_funds"].return_value = payment
    io["apply_canteen_sea_cucumber_effect"].side_effect = OSError("native access")
    restore = MagicMock()
    io["restore_player_activity_effect"].side_effect = restore

    with pytest.raises(OSError, match="native access"):
        host.canteen_sea_cucumber({"player_id": 42})

    restore.assert_not_called()
    io["refund_combined_funds"].assert_called_once_with(
        payment, "canteen_sea_cucumber_rollback",
        player_id=42, player_name="First",
    )


def test_old_single_invalid_player_is_rejected_before_context(facade, io):
    host = make_host(facade)
    with pytest.raises(ValueError, match="请选择球员"):
        host.canteen_sea_cucumber({"player_id": 0})
    assert host.bind_count == 0
    io["charge_combined_funds"].assert_not_called()


def test_old_context_rebinds_manager_address_and_clock_on_every_call(
    facade, io,
):
    host = make_host(facade)
    host.canteen_sea_cucumber({"player_id": 42})
    second_charge = MagicMock(return_value={"total": 60_000.0})
    io["charge_combined_funds"].side_effect = second_charge
    io["read_game_clock"].return_value = {"date": "2026-08-01"}
    host.output["manager"] = {"id": 7, "manager_address": "0x9999"}
    host.teams[42]["address"] = "0xAAAA"

    host.canteen_sea_cucumber({"player_id": 42})

    assert host.bind_count == 2
    assert set(host.target_calls[-1][2]) == {"missing_message"}
    second_charge.assert_called_once()
    assert second_charge.call_args.kwargs["game_date"] == "2026-08-01"
    assert set(host.target_calls[0][2]) == {"missing_message"}
    assert io["apply_manager_intimacy_points"].call_args.kwargs[
        "team_address"
    ] == "0xAAAA"
    assert io["apply_manager_intimacy_points"].call_args.kwargs[
        "manager_address"
    ] == "0x9999"


def test_old_batch_deduplicates_and_shares_one_memory_session(facade, io):
    host = make_host(facade)
    add_player(host, 43)
    session = MemorySession()
    open_session = MagicMock(return_value=nullcontext(session))
    io["canteen_sea_cucumber_memory_session"].side_effect = open_session

    result = host.canteen_sea_cucumbers(
        {"player_ids": [42, 43, 42], "team_id": 9},
    )

    assert result["requested"] == 2
    assert result["completed"] == 2
    assert result["failure"] is None
    assert result["economy"] == {"bank_balance": 10}
    assert [row["player_id"] for row in result["results"]] == [42, 43]
    open_session.assert_called_once_with()
    assert io["charge_combined_funds"].call_count == 2
    # The callable(resolve_roster_player) branch passes the shared session.
    assert [call[2].get("memory_session") for call in host.target_calls] == [
        session, session,
    ]


def test_old_batch_rejects_empty_invalid_duplicate_and_over_200(facade, io):
    host = make_host(facade)
    with pytest.raises(ValueError, match="请选择球员"):
        host.canteen_sea_cucumbers({"player_ids": "42"})
    with pytest.raises(ValueError, match="请选择有效球员"):
        host.canteen_sea_cucumbers({"player_ids": []})
    with pytest.raises(ValueError, match="请选择有效球员"):
        host.canteen_sea_cucumbers({"player_ids": [42, 0]})
    with pytest.raises(ValueError, match="单次最多奖励 200 名球员"):
        host.canteen_sea_cucumbers({"player_ids": list(range(1, 202))})
    assert host.bind_count == 0
    io["canteen_sea_cucumber_memory_session"].assert_not_called()
    io["charge_combined_funds"].assert_not_called()


def test_old_batch_second_failure_stops_third_and_returns_partial(facade, io):
    host = make_host(facade)
    add_player(host, 43)
    add_player(host, 44)
    calls: list[tuple] = []
    session = MemorySession()

    def apply_effect(player_id, _address):
        calls.append(("effect", player_id))
        return {
            "field": "canteen_sea_cucumber",
            "fitness": {"before": 70.0, "after": 100.0},
            "sharpness": {"before": 70.0, "after": 100.0},
            "_restores": [(player_id, b"old")],
        }

    def apply_intimacy(player_id, *_args, **_kwargs):
        calls.append(("intimacy", player_id))
        if player_id == 43:
            raise RuntimeError("write failed")
        return {"before": 1, "after": 2, "applied": 1}

    io["canteen_sea_cucumber_memory_session"].return_value = nullcontext(session)
    session.apply_effect = apply_effect
    session.apply_intimacy = apply_intimacy

    result = host.canteen_sea_cucumbers({"player_ids": [42, 43, 44]})

    assert result["completed"] == 1
    assert result["requested"] == 3
    assert result["failure"] == {
        "player_id": 43,
        "error": "write failed",
        "error_code": "effect_failed",
        "error_phase": "apply",
        "retryable": False,
        "operation": "sea_cucumber_batch",
        "error_type": "RuntimeError",
    }
    assert [row["player_id"] for row in result["results"]] == [42]
    assert calls == [
        ("effect", 42), ("intimacy", 42),
        ("effect", 43), ("intimacy", 43),
    ]
    assert io["refund_combined_funds"].call_count == 1
    assert session.restored and session.restored[0]["_restores"][0][0] == 43


def test_old_facade_preserves_context_and_one_replacement_points(facade, io):
    host = make_host(facade)
    add_player(host, 43)
    context = MagicMock(return_value=({"id": 7}, 7, "2026-07-24"))
    one = MagicMock(return_value={"player_id": 42, "price_gbp": 60_000.0})
    host._canteen_sea_cucumber_context = context
    host._canteen_sea_cucumber_one = one

    single = host.canteen_sea_cucumber({"player_id": 42})

    assert single["economy"] == {"bank_balance": 10}
    context.assert_called_once_with()
    one.assert_called_once_with(
        42, 0, manager={"id": 7}, manager_id=7, game_date="2026-07-24",
    )
    context.reset_mock()
    one.reset_mock()
    session = MemorySession()
    io["canteen_sea_cucumber_memory_session"].return_value = nullcontext(session)

    result = host.canteen_sea_cucumbers(
        {"player_ids": [42, 43, 42], "team_id": 9},
    )

    assert result["requested"] == 2
    assert result["completed"] == 2
    context.assert_called_once_with()
    assert one.call_count == 2
    assert one.call_args_list[0].args == (42, 9)
    assert one.call_args_list[1].args == (43, 9)
    assert one.call_args_list[0].kwargs == {
        "manager": {"id": 7}, "manager_id": 7,
        "game_date": "2026-07-24", "memory_session": session,
    }
    assert one.call_args_list[1].kwargs["memory_session"] is session


# ---------------------------------------------------------------------------
# Direct service boundary
# ---------------------------------------------------------------------------

class ServiceRuntime:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.memory_lock = RecordingLock("memory", self.events)
        self.lock = RecordingLock("state", self.events)
        self.output = {
            "manager": {"id": 7, "manager_address": "0x7000"},
            "selected_manager_id": 7,
            "game_date": "2026-07-24",
        }
        self.context_result = ({"id": 7}, 7, "2026-07-24")
        self.one_result = {"player_id": 42, "price_gbp": 60_000.0}
        self.target = SimpleNamespace(
            player={"id": 42, "name": "First"},
            team={"id": 9, "team_type": "club", "address": "0x9000"},
            team_id=9, address="0x4200",
        )

    def _canteen_sea_cucumber_context(self):
        self.events.append(("context",))
        return self.context_result

    def _canteen_sea_cucumber_one(self, *args, **kwargs):
        self.events.append(("one", args, kwargs))
        return self.one_result

    def _bind_current_save(self) -> None:
        return None

    def _live_player_effect_target(self, *_args, **_kwargs):
        return self.target


def service_io(**overrides):
    payment = {"bank": 60_000.0, "wallet": 0.0, "total": 60_000.0}
    values = {
        "read_game_clock": MagicMock(return_value={"date": "2026-07-24"}),
        "local_purchase_price": MagicMock(side_effect=lambda value: float(value)),
        "base_price": 60_000.0,
        "charge_combined_funds": MagicMock(return_value=payment),
        "refund_combined_funds": MagicMock(return_value=None),
        "commit_player_effect": commit_player_effect,
        "apply_effect": MagicMock(return_value={
            "field": "canteen_sea_cucumber",
            "fitness": {"before": 74.0, "after": 100.0},
            "sharpness": {"before": 68.0, "after": 100.0},
            "_restores": [(0x1234, b"old")],
        }),
        "apply_intimacy": MagicMock(
            return_value={"before": 12, "after": 13, "applied": 1},
        ),
        "restore_effect": MagicMock(return_value=None),
        "memory_session_factory": MagicMock(
            return_value=nullcontext(MemorySession()),
        ),
        "describe_error": describe_player_effect_error,
        "public_economy": MagicMock(return_value={"bank_balance": 10}),
    }
    values.update(overrides)
    from tools.canteen_application import CanteenIO

    return CanteenIO(**values)


def test_service_module_has_no_native_or_facade_import():
    import tools.canteen_application as application

    source = Path(application.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "fm_odds_web" not in modules
    assert not any((module or "").startswith("tools.club_reader") for module in modules)


def test_service_import_succeeds_in_a_fresh_native_free_process():
    completed = subprocess.run(
        [
            sys.executable, "-c",
            "import tools.canteen_application as m; "
            "print(m.CanteenApplicationService.__name__)",
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""},
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "CanteenApplicationService"


def test_service_signatures_match_the_plan():
    from tools.canteen_application import CanteenApplicationService

    assert list(inspect.signature(
        CanteenApplicationService.reward_one,
    ).parameters) == ["self", "payload"]
    assert list(inspect.signature(
        CanteenApplicationService.reward_batch,
    ).parameters) == ["self", "payload"]
    assert list(inspect.signature(
        CanteenApplicationService.context,
    ).parameters) == ["self"]
    parameters = inspect.signature(
        CanteenApplicationService.reward_player,
    ).parameters
    assert list(parameters) == [
        "self", "player_id", "requested_team_id", "manager", "manager_id",
        "game_date", "memory_session",
    ]
    assert parameters["manager"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["memory_session"].default is None


def test_service_reward_one_uses_runtime_replacement_points_each_call():
    from tools.canteen_application import CanteenApplicationService

    runtime = ServiceRuntime()
    io = service_io()
    service = CanteenApplicationService(runtime, io)

    first = service.reward_one({"player_id": 42, "team_id": 9})
    second = service.reward_one({"player_id": 42, "team_id": 9})

    assert first["economy"] == {"bank_balance": 10}
    assert second["economy"] == {"bank_balance": 10}
    assert [
        event[0] for event in runtime.events
        if event[0] in {"context", "one"}
    ] == ["context", "one", "context", "one"]
    one_call = runtime.events[[
        event[0] for event in runtime.events
    ].index("one")]
    assert one_call[1] == (42, 9)
    assert one_call[2] == {
        "manager": {"id": 7},
        "manager_id": 7, "game_date": "2026-07-24",
    }
    assert io.public_economy.call_count == 2


def test_service_reward_batch_deduplicates_and_opens_a_fresh_short_session():
    from tools.canteen_application import CanteenApplicationService

    runtime = ServiceRuntime()
    io = service_io()
    service = CanteenApplicationService(runtime, io)

    result = service.reward_batch({"player_ids": [42, 43, 42]})
    service.reward_batch({"player_ids": [44]})

    assert result == {
        "requested": 2, "completed": 2,
        "results": [runtime.one_result, runtime.one_result],
        "failure": None, "economy": {"bank_balance": 10},
    }
    assert [event[1][0] for event in runtime.events if event[0] == "one"] == [
        42, 43, 44,
    ]
    assert io.memory_session_factory.call_count == 2


def test_service_reward_batch_stops_and_reports_classified_failure():
    from tools.canteen_application import CanteenApplicationService

    runtime = ServiceRuntime()
    error = PlayerEffectOperationError(
        "write failed", code="native_write", phase="persist",
    )

    def one(player_id, *_args, **_kwargs):
        runtime.events.append(("one", (player_id,), {}))
        if player_id == 43:
            raise error
        return {"player_id": player_id}

    runtime._canteen_sea_cucumber_one = one
    io = service_io()

    result = CanteenApplicationService(runtime, io).reward_batch(
        {"player_ids": [42, 43, 44]},
    )

    assert result["requested"] == 3
    assert result["completed"] == 1
    assert result["failure"]["player_id"] == 43
    assert result["failure"]["error_code"] == "native_write"
    assert result["failure"]["error_phase"] == "persist"
    assert result["failure"]["operation"] == "sea_cucumber_batch"
    assert [event[1][0] for event in runtime.events if event[0] == "one"] == [
        42, 43,
    ]


def test_service_reward_player_keeps_compensation_order():
    from tools.canteen_application import CanteenApplicationService

    events: list[tuple] = []
    runtime = ServiceRuntime()
    condition = {
        "fitness": {"before": 74.0, "after": 100.0},
        "sharpness": {"before": 68.0, "after": 100.0},
        "_restores": [(42, b"old")],
    }
    payment = {"bank": 60_000.0, "wallet": 0.0, "total": 60_000.0}
    io = service_io(
        charge_combined_funds=MagicMock(
            side_effect=lambda *a, **k: events.append(("charge",)) or payment,
        ),
        apply_effect=MagicMock(
            side_effect=lambda *a: events.append(("effect",)) or condition,
        ),
        apply_intimacy=MagicMock(
            side_effect=lambda *a, **k: events.append(("intimacy",))
            or (_ for _ in ()).throw(RuntimeError("write failed")),
        ),
        restore_effect=MagicMock(
            side_effect=lambda value: events.append(("restore", value)),
        ),
        refund_combined_funds=MagicMock(
            side_effect=lambda *a, **k: events.append(("refund",)),
        ),
    )

    with pytest.raises(RuntimeError, match="write failed"):
        CanteenApplicationService(runtime, io).reward_player(
            42, 9, manager={"id": 7, "manager_address": "0x7000"},
            manager_id=7, game_date="2026-07-24",
        )

    assert events == [
        ("charge",), ("effect",), ("intimacy",),
        ("restore", condition), ("refund",),
    ]
    io.refund_combined_funds.assert_called_once_with(
        payment, "canteen_sea_cucumber_rollback",
        player_id=42, player_name="First",
    )


def test_service_context_returns_manager_id_and_clock_fallback():
    from tools.canteen_application import CanteenApplicationService

    runtime = ServiceRuntime()
    io = service_io()
    io.read_game_clock.return_value = {}

    assert CanteenApplicationService(runtime, io).context() == (
        {"id": 7, "manager_address": "0x7000"}, 7, "2026-07-24",
    )
    io.read_game_clock.return_value = {"date": "2026-08-02"}
    assert CanteenApplicationService(runtime, io).context() == (
        {"id": 7, "manager_address": "0x7000"}, 7, "2026-08-02",
    )


def test_facade_incomplete_restore_preserves_error_and_refunds_payment(facade, io):
    """A refund must not conceal that the existing native rollback failed."""
    host = make_host(facade)
    events = []
    operation_error = RuntimeError("relationship write failed")
    rollback_error = OSError("native restore failed")
    payment = io["charge_combined_funds"].return_value
    condition = io["apply_canteen_sea_cucumber_effect"].return_value

    def fail_relationship(*args, **kwargs):
        events.append("relationship")
        raise operation_error

    def fail_restore(value):
        assert value is condition
        events.append("restore")
        raise rollback_error

    io["apply_manager_intimacy_points"].side_effect = fail_relationship
    io["restore_player_activity_effect"].side_effect = fail_restore
    io["refund_combined_funds"].side_effect = lambda *args, **kwargs: events.append("refund")

    with pytest.raises(PlayerEffectRollbackError) as caught:
        host.canteen_sea_cucumber({"player_id": 42, "team_id": 9})

    assert caught.value.operation_error is operation_error
    assert caught.value.rollback_error is rollback_error
    assert describe_player_effect_error(caught.value)["error_code"] == "rollback_incomplete"
    assert events == ["relationship", "restore", "refund"]
    io["restore_player_activity_effect"].assert_called_once_with(condition)
    io["refund_combined_funds"].assert_called_once_with(
        payment, "canteen_sea_cucumber_rollback", player_id=42, player_name="First",
    )
    assert host.players[42]["fitness"] == 74.0
    assert host.players[42]["sharpness"] == 68.0
