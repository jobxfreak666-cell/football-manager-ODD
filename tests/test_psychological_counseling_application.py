from __future__ import annotations

import __future__
import ast
import shutil
import threading
from pathlib import Path
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from tools import app_settings, betting_account, club_economy, club_reader
from tools.money import to_minor, write_minor


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def scratch_dir():
    path = ROOT / "output" / f"counseling-test-{uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class RecordingLock:
    """Context-manager lock that records acquisition order/release pairing."""

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
    """Load the real ``LocalOddsState`` source without importing native modules.

    ``fm_odds_web`` imports the FM native core at module import time, which is
    unavailable in this environment.  The class body is loaded from the actual
    file and compiled in an explicit namespace so the real method source is
    exercised; only the already native-free ``tools`` collaborators are bound.
    """
    source = (ROOT / "src" / "fm_odds_web.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    class_node = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LocalOddsState"
    )
    method_names = {"psychological_counseling", "_counseling_application"}
    methods = [
        node for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name in method_names
    ]
    assert any(node.name == "psychological_counseling" for node in methods)
    class_node.body = methods
    class_node.decorator_list = []
    # Execute the facade's real service import too: a missing or misspelled
    # production import must fail rather than being supplied by this harness.
    service_imports = [
        node for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "tools.counseling_application"
    ]
    module = ast.Module(body=[*service_imports, class_node], type_ignores=[])
    namespace: dict = {
        "CLUB_DEFERRED_REFRESH_REASONS": frozenset(),
        "TEMPORARY_BANK_CHEAT": False,
        "PSYCHOLOGICAL_COUNSELING_SESSION_PRICE":
            club_economy.PSYCHOLOGICAL_COUNSELING_SESSION_PRICE,
        "read_game_clock": None,
        "local_purchase_price": app_settings.local_purchase_price,
        "available_balance": betting_account.available_balance,
        "adjust_balance": betting_account.adjust_balance,
        "player_has_unhappiness": club_reader.player_has_unhappiness,
        "apply_psychological_counseling_effect":
            club_reader.apply_psychological_counseling_effect,
        "adjust_manager_intimacy_points": club_reader.adjust_manager_intimacy_points,
        "restore_player_activity_effect": club_reader.restore_player_activity_effect,
        "perform_psychological_counseling":
            club_economy.perform_psychological_counseling,
        "public_economy": club_economy.public_economy,
        "welfare_status": club_economy.welfare_status,
    }
    code = compile(
        module, str(ROOT / "src" / "fm_odds_web.py"), "exec",
        flags=__future__.annotations.compiler_flag,
    )
    exec(code, namespace)
    return namespace["LocalOddsState"], namespace


def economy_state(*, balance: float = 0.0) -> dict:
    return {
        "general_balance": float(balance),
        "transactions": [],
        "owned_activity_centres": ["talk_room"],
        "owned_activity_facilities": [],
        "activity_floor_cooldowns": {},
        "activity_centre_rules_version": club_economy.ACTIVITY_CENTRE_RULES_VERSION,
        "media_activity_daily_usage": {},
        "activity_progress": {},
        "activity_daily_usage": {},
        "activity_history": [],
        "psychological_counseling": {},
        "medical_treatments": {},
    }


def counseling_host(*, archive_error: Exception | None = None):
    events: list[tuple[str, str]] = []
    facade, _namespace = load_facade_class()
    state = object.__new__(facade)
    state.memory_lock = RecordingLock("memory_lock", events)
    state.lock = RecordingLock("lock", events)
    state.output = {
        "selected_manager_id": 1,
        "manager": {"id": 1, "manager_address": "0x1000"},
        "game_date": "2028-01-01",
    }
    player = {
        "id": 2, "name": "球员", "address": "0x2000",
        "manager_intimacy": 40, "has_unhappiness": True,
    }
    profile = {"team": {"id": 3, "address": "0x3000"}}
    state._bind_current_save = MagicMock()
    state._live_player_profile = MagicMock(return_value=(profile, player))
    state._archive_activity_relationship = MagicMock(
        return_value=None, side_effect=archive_error,
    )
    return state, player, events, facade, _namespace


def native_effect() -> dict:
    return {
        "field": "psychological_counseling",
        "effects": [{"field": "unhappiness", "before": True, "after": False}],
        "_restores": [(0x4000, b"original")],
    }


def run_old_facade(
    scratch_dir, wallet_balance: float, *, relationship_error=None, archive_error=None,
    force_points: int | None = None,
):
    economy = economy_state(balance=5_000_000.0)
    state, player, events, _facade, namespace = counseling_host(
        archive_error=archive_error,
    )
    effect = native_effect()

    def perform_with_points(
        manager_id, player_id, player_name, game_date, current_intimacy, apply_effects,
    ):
        memory = apply_effects("unlocked", int(force_points))
        return {
            "id": "row", "outcome": "unlocked", "outcome_name": "彻底释怀",
            "integer_applied": int(force_points),
            "intimacy": memory.get("after", current_intimacy),
            "effect": memory.get("effect") or {},
        }

    perform = (
        perform_with_points if force_points is not None
        else club_economy.perform_psychological_counseling
    )
    with (
        patch("tools.betting_account.save_data_root", return_value=scratch_dir),
        patch.object(club_economy, "load_economy", return_value=economy),
        patch.object(club_economy, "save_economy"),
        patch.dict(namespace, {
            "read_game_clock": MagicMock(return_value={"date": "2028-01-01"}),
            "player_has_unhappiness": MagicMock(return_value=True),
            "local_purchase_price": MagicMock(side_effect=float),
            "charge_combined_funds": MagicMock(),
            "apply_psychological_counseling_effect": MagicMock(return_value=effect),
            "adjust_manager_intimacy_points": MagicMock(
                side_effect=relationship_error,
                return_value={
                    "before": 40, "after": 40, "applied": 0,
                    "effect": effect,
                },
            ),
            "restore_player_activity_effect": MagicMock(),
            "public_economy": MagicMock(return_value={}),
            "welfare_status": MagicMock(return_value={}),
            "perform_psychological_counseling": perform,
        }),
    ):
        wallet = betting_account.load_wallet()
        write_minor(wallet, "balance", to_minor(wallet_balance))
        betting_account.save_wallet(wallet)
        outcome = {"response": None, "error": None}
        try:
            outcome["response"] = state.psychological_counseling(
                {"player_id": 2, "team_id": 3}
            )
        except Exception as error:  # surfaced for assertions
            outcome["error"] = error
        outcome["wallet_after"] = betting_account.available_balance()
        outcome["combined"] = namespace["charge_combined_funds"]
        outcome["apply_effect"] = namespace["apply_psychological_counseling_effect"]
        outcome["intimacy"] = namespace["adjust_manager_intimacy_points"]
        outcome["restore"] = namespace["restore_player_activity_effect"]
    outcome.update(
        state=state, player=player, events=events, bank_after=economy["general_balance"],
        namespace=namespace,
    )
    return outcome


def test_old_facade_always_unlocks_and_charges_wallet_not_bank(scratch_dir):
    price = club_economy.PSYCHOLOGICAL_COUNSELING_SESSION_PRICE
    assert price == 100_000.0
    run = run_old_facade(scratch_dir, 250_000.0)

    assert run["error"] is None
    counseling = run["response"]["counseling"]
    assert counseling["outcome"] == "unlocked"
    assert counseling["outcome_name"] == "彻底释怀"
    assert counseling["payment"] == {"bank": 0.0, "wallet": price, "total": price}
    assert "guaranteed" not in counseling
    assert run["wallet_after"] == 250_000.0 - price
    assert run["bank_after"] == 5_000_000.0
    run["combined"].assert_not_called()
    run["state"]._archive_activity_relationship.assert_called_once()
    assert run["player"]["has_unhappiness"] is False


def test_old_facade_rejects_wallet_shortfall_without_effect_or_archive(scratch_dir):
    run = run_old_facade(scratch_dir, 99_999.99)

    assert isinstance(run["error"], ValueError)
    assert "余额不足" in str(run["error"])
    assert run["wallet_after"] == 99_999.99
    run["apply_effect"].assert_not_called()
    run["restore"].assert_not_called()
    run["state"]._archive_activity_relationship.assert_not_called()
    assert run["player"]["has_unhappiness"] is True


def test_old_facade_takes_memory_lock_before_state_lock(scratch_dir):
    run = run_old_facade(scratch_dir, 250_000.0)

    assert run["error"] is None
    assert run["events"][:2] == [
        ("enter", "memory_lock"), ("enter", "lock"),
    ]
    assert run["state"].memory_lock.enters == run["state"].memory_lock.exits == 1
    assert run["state"].lock.enters == run["state"].lock.exits
    assert run["events"][-1] == ("exit", "memory_lock")


def test_old_facade_restores_effect_and_refunds_when_relationship_write_fails(scratch_dir):
    run = run_old_facade(
        scratch_dir, 150_000.0, relationship_error=RuntimeError("relationship failed"),
        force_points=1,
    )

    assert isinstance(run["error"], RuntimeError)
    assert run["wallet_after"] == 150_000.0
    assert run["bank_after"] == 5_000_000.0
    run["restore"].assert_called_once_with(native_effect())
    run["state"]._archive_activity_relationship.assert_not_called()
    assert run["player"]["manager_intimacy"] == 40
    assert run["player"]["has_unhappiness"] is True


def test_old_facade_archive_failure_is_outside_compensation_boundary(scratch_dir):
    run = run_old_facade(
        scratch_dir, 150_000.0, archive_error=RuntimeError("archive failed"),
    )

    assert isinstance(run["error"], RuntimeError)
    assert run["wallet_after"] == 50_000.0
    assert run["bank_after"] == 5_000_000.0
    run["restore"].assert_not_called()
    assert run["player"]["manager_intimacy"] == 40
    assert run["player"]["has_unhappiness"] is True



def direct_io(*, perform=None, adjust=None):
    from tools.counseling_application import CounselingIO

    effect = native_effect()
    calls = {"adjust": [], "restore": [], "archive": [], "bind": 0}

    def default_perform(
        manager_id, player_id, player_name, game_date, current_intimacy, apply_effects,
    ):
        memory = apply_effects("unlocked", 0)
        return {
            "id": "row", "outcome": "unlocked", "outcome_name": "彻底释怀",
            "integer_applied": 0, "intimacy": memory.get("after", current_intimacy),
            "effect": memory.get("effect") or {},
        }

    def default_adjust(amount, transaction_type, **metadata):
        calls["adjust"].append((amount, transaction_type, metadata))
        return {"amount": amount}

    io = CounselingIO(
        read_game_clock=lambda: {"date": "2028-01-01"},
        local_purchase_price=float,
        session_price=100_000.0,
        available_balance=lambda: 250_000.0,
        adjust_balance=adjust or default_adjust,
        player_has_unhappiness=lambda _player_id, _address: True,
        apply_effect=lambda _player_id, _address, _outcome: effect,
        adjust_manager_intimacy=lambda *args, **kwargs: {
            "before": 40, "after": 40, "applied": 0, "effect": effect,
        },
        restore_effect=lambda value: calls["restore"].append(value),
        perform_counseling=perform or default_perform,
        public_economy=lambda: {"wallet": 150_000.0},
        welfare_status=lambda: {"treatments": {}},
    )
    return io, effect, calls


def direct_runtime(output=None, player=None):
    from types import SimpleNamespace

    player = player or {
        "id": 2, "name": "球员", "address": "0x2000",
        "manager_intimacy": 40, "has_unhappiness": True,
    }
    runtime = SimpleNamespace(
        memory_lock=threading.RLock(),
        lock=threading.RLock(),
        output=output or {
            "selected_manager_id": 1,
            "manager": {"id": 1, "manager_address": "0x1000"},
            "game_date": "2028-01-01",
        },
        _bind_current_save=MagicMock(),
        _live_player_profile=MagicMock(return_value=(
            {"team": {"id": 3, "address": "0x3000"}}, player,
        )),
        _archive_activity_relationship=MagicMock(return_value=True),
    )
    return runtime, player


def test_direct_service_owns_use_case_flow_and_response_shape():
    from tools.counseling_application import CounselingApplicationService

    io, effect, calls = direct_io()
    runtime, player = direct_runtime()
    response = CounselingApplicationService(runtime, io).counsel(
        {"player_id": 2, "team_id": 3}
    )

    assert response["counseling"]["outcome"] == "unlocked"
    assert response["counseling"]["payment"] == {
        "bank": 0.0, "wallet": 100_000.0, "total": 100_000.0,
    }
    assert response["counseling"]["relationship_archived"] is True
    assert response["economy"] == {"wallet": 150_000.0}
    assert response["welfare"] == {"treatments": {}}
    assert calls["adjust"] == [(
        -100_000.0, "psychological_counseling_session",
        {
            "manager_id": 1, "player_id": 2, "player_name": "球员",
            "game_date": "2028-01-01",
        },
    )]
    assert calls["restore"] == []
    runtime._bind_current_save.assert_called_once()
    runtime._archive_activity_relationship.assert_called_once()
    assert player["has_unhappiness"] is False


def test_direct_service_io_is_frozen():
    from dataclasses import FrozenInstanceError

    io, _effect, _calls = direct_io()
    with pytest.raises(FrozenInstanceError):
        io.session_price = 1.0


def test_facade_factory_rebinds_current_dependencies_each_call():
    facade, namespace = load_facade_class()
    state = object.__new__(facade)
    first = MagicMock(name="first_clock")
    second = MagicMock(name="second_clock")
    with patch.dict(namespace, {"read_game_clock": first}):
        app1 = state._counseling_application()
    with patch.dict(namespace, {"read_game_clock": second}):
        app2 = state._counseling_application()

    assert app1 is not app2
    assert app1._io.read_game_clock is first
    assert app2._io.read_game_clock is second


def test_direct_service_rebinds_account_and_player_on_each_call():
    from tools.counseling_application import CounselingApplicationService

    io, _effect, calls = direct_io()
    runtime, first_player = direct_runtime()
    second_player = {
        "id": 9, "name": "另一名球员", "address": "0x9000",
        "manager_intimacy": 60, "has_unhappiness": True,
    }
    profile = {"team": {"id": 30, "address": "0x3000"}}
    runtime._live_player_profile.side_effect = [
        (profile, first_player), (profile, second_player),
    ]
    service = CounselingApplicationService(runtime, io)

    service.counsel({"player_id": 2, "team_id": 3})
    runtime.output = {
        "selected_manager_id": 7,
        "manager": {"id": 7, "manager_address": "0x7000"},
        "game_date": "2028-01-02",
    }
    service.counsel({"player_id": 9, "team_id": 30})

    assert runtime._bind_current_save.call_count == 2
    assert [call[2]["manager_id"] for call in calls["adjust"]] == [1, 7]
    assert [call[2]["player_id"] for call in calls["adjust"]] == [2, 9]
    assert [call[2]["game_date"] for call in calls["adjust"]] == [
        "2028-01-01", "2028-01-01",
    ]


def test_service_module_imports_without_native_dll():
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-c", "import tools.counseling_application"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("failure_stage", ["native_apply", "domain_after_effect", "relationship_restore"])
def test_failure_preserves_restore_attempts_refund_order_and_original_exception(failure_stage):
    """Refunding must not imply that a failed native restoration succeeded."""
    from dataclasses import replace
    from tools.counseling_application import CounselingApplicationService

    io, effect, _calls = direct_io()
    runtime, player = direct_runtime()
    events = []
    failure = RuntimeError(failure_stage)
    restore_failure = OSError("restore failed")

    def payment(amount, kind, **metadata):
        events.append(("wallet", amount, kind))

    def apply(*args):
        events.append(("apply",))
        if failure_stage == "native_apply":
            raise failure
        return effect

    def relationship(*args, **kwargs):
        events.append(("relationship",))
        raise failure

    def restore(value):
        assert value is effect
        events.append(("restore",))
        raise restore_failure

    def settle(*args):
        callback = args[-1]
        callback("unlocked", 1 if failure_stage == "relationship_restore" else 0)
        raise failure

    service = CounselingApplicationService(runtime, replace(
        io, adjust_balance=payment, apply_effect=apply,
        adjust_manager_intimacy=relationship, restore_effect=restore,
        perform_counseling=settle,
    ))
    expected_error = restore_failure if failure_stage == "relationship_restore" else failure
    with pytest.raises(type(expected_error)) as caught:
        service.counsel({"player_id": 2, "team_id": 3})
    assert caught.value is expected_error
    middle = {
        "native_apply": [("apply",)],
        "domain_after_effect": [("apply",), ("restore",)],
        "relationship_restore": [("apply",), ("relationship",), ("restore",), ("restore",)],
    }[failure_stage]
    assert events == [
        ("wallet", -100_000.0, "psychological_counseling_session"),
        *middle,
        ("wallet", 100_000.0, "psychological_counseling_session_rollback"),
    ]
    assert player["has_unhappiness"] is True
    runtime._archive_activity_relationship.assert_not_called()


def test_converted_price_controls_wallet_debit_and_response():
    from dataclasses import replace
    from tools.counseling_application import CounselingApplicationService

    io, _effect, calls = direct_io()
    runtime, _player = direct_runtime()
    response = CounselingApplicationService(runtime, replace(
        io, local_purchase_price=lambda base: base * 2,
    )).counsel({"player_id": 2, "team_id": 3})
    assert calls["adjust"][0][0] == -200_000.0
    assert response["counseling"]["payment"] == {
        "bank": 0.0, "wallet": 200_000.0, "total": 200_000.0,
    }


def test_reused_service_resolves_new_addresses_and_output_date_after_account_switch():
    from dataclasses import replace
    from tools.counseling_application import CounselingApplicationService

    io, _effect, calls = direct_io()
    runtime, _player = direct_runtime()
    observed = []

    def apply(player_id, address, outcome):
        observed.append((player_id, address))
        return native_effect()

    service = CounselingApplicationService(runtime, replace(
        io, read_game_clock=lambda: None, apply_effect=apply,
    ))
    service.counsel({"player_id": 2, "team_id": 3})
    runtime.output = {"selected_manager_id": 7, "manager": {"id": 7}, "game_date": "2028-02-02"}
    runtime._live_player_profile.return_value = (
        {"team": {"id": 30}},
        {"id": 9, "name": "Second", "address": "0x9999", "manager_intimacy": 80},
    )
    service.counsel({"player_id": 9, "team_id": 30})
    assert observed == [(2, "0x2000"), (9, "0x9999")]
    assert [entry[2]["manager_id"] for entry in calls["adjust"]] == [1, 7]
    assert [entry[2]["game_date"] for entry in calls["adjust"]] == ["2028-01-01", "2028-02-02"]