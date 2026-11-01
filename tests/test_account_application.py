"""Account application tests with isolated state and temporary account documents."""
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

import fm_odds_web as web
from tools import account_application as services, account_store, app_paths
from tools import betting_account, club_economy


class OperationLock:
    def __init__(self):
        self.depth = 0

    def __enter__(self):
        self.depth += 1

    def __exit__(self, *args):
        self.depth -= 1


def account_state():
    state = web.LocalOddsState.__new__(web.LocalOddsState)
    state.lock = OperationLock()
    state.output = {"save_instance_id": "career-a", "game_date": "2028-01-01"}
    state.data_version = 7
    state.connection_scope_id = "account-a"
    state.club_contexts = {}
    state._has_verified_save = lambda: True
    state._data_scope_id = lambda _output: "account-a"
    state._bind_current_save = Mock(return_value="account-a")
    state._bind_wallet_scope = Mock(return_value="account-a")
    return state


def test_wallet_update_holds_account_guard_through_write_and_projection(monkeypatch):
    state = account_state()

    def change_wallet(**kwargs):
        assert state.lock.depth > 0, "account guard released before wallet write"
        assert kwargs == {"amount": 250.0, "clear": False}
        return {"balance": 250.0}

    def economy():
        assert state.lock.depth > 0, "account guard released before projection"
        return {"casino_balance": 250.0}

    monkeypatch.setattr(services, "cheat_balance", change_wallet)
    monkeypatch.setattr(services, "public_economy", economy)
    result = state.update_cheat_balance({"amount": 250})
    assert result == {
        "balance": 250.0,
        "state_patch": {"balance": 250.0, "economy": {"casino_balance": 250.0}},
        "state_sync": {"data_version": 7, "data_scope_id": "account-a"},
    }
    assert state.lock.depth == 0


def test_frozen_wallet_cheat_allows_the_100b_addition(monkeypatch):
    state = account_state()
    write = Mock(return_value={"balance": 100_000_000_000})
    monkeypatch.setattr(web, "FROZEN", True)
    monkeypatch.setattr(services, "cheat_balance", write)
    monkeypatch.setattr(services, "public_economy", lambda: {})
    result = state.update_cheat_balance({"amount": 100_000_000_000})
    assert result == {
        "balance": 100_000_000_000,
        "state_patch": {"balance": 100_000_000_000, "economy": {}},
        "state_sync": {"data_version": 7, "data_scope_id": "account-a"},
    }
    state._bind_current_save.assert_called_once_with()
    write.assert_called_once_with(amount=100_000_000_000.0, clear=False)
    assert state.lock.depth == 0


def test_frozen_wallet_cheat_adds_once_and_rejected_requests_do_not_write(tmp_path, monkeypatch):
    scope_id = "wallet-cheat-test"
    account_path = tmp_path / "saves" / f"{scope_id}.fmodd"
    data_root = tmp_path / "saves" / scope_id
    monkeypatch.setattr(
        account_store, "account_save_path",
        lambda requested=None: tmp_path / "saves" / f"{requested or scope_id}.fmodd",
    )
    monkeypatch.setattr(
        account_store, "save_data_root",
        lambda requested=None: tmp_path / "saves" / str(requested or scope_id),
    )
    monkeypatch.setattr(betting_account, "save_data_root", lambda _scope=None: data_root)
    monkeypatch.setattr(club_economy, "save_data_root", lambda _scope=None: data_root)
    previous_scope = app_paths.active_save_id()
    app_paths.set_active_save_id(scope_id)
    try:
        betting_account.save_wallet({
            "schema_version": 1, "balance": 12.5,
            "credit_effective_bet_count": 0, "transactions": [],
        })
        state = account_state()
        bind = Mock(side_effect=lambda: app_paths.set_active_save_id(scope_id))
        state._bind_current_save = bind
        monkeypatch.setattr(web, "FROZEN", True)

        state.update_cheat_balance({"amount": 100_000_000_000})

        wallet = account_store.read_persisted_document("wallet", scope_id)
        assert wallet["balance"] == 100_000_000_012.5
        assert len(wallet["transactions"]) == 1
        assert wallet["transactions"][0]["type"] == "cheat_funding"
        assert wallet["transactions"][0]["amount"] == 100_000_000_000
        persisted_after_add = account_path.read_bytes()

        with pytest.raises(web.NotFoundError):
            state.update_cheat_balance({"clear": True})
        with pytest.raises(web.NotFoundError):
            state.update_cheat_balance({"amount": 100})

        assert account_path.read_bytes() == persisted_after_add
        assert bind.call_count == 1
    finally:
        app_paths.set_active_save_id(previous_scope)


@pytest.mark.parametrize("payload", [
    {"clear": True}, {"amount": 100}, {"amount": 500}, {"amount": 5000},
])
def test_frozen_wallet_cheat_rejects_other_operations_before_binding_or_writing(monkeypatch, payload):
    state = account_state()
    write = Mock(return_value={"balance": 100})
    monkeypatch.setattr(web, "FROZEN", True)
    monkeypatch.setattr(services, "cheat_balance", write)
    monkeypatch.setattr(services, "public_economy", lambda: {})
    with pytest.raises(web.NotFoundError):
        state.update_cheat_balance(payload)
    state._bind_current_save.assert_not_called()
    write.assert_not_called()


@pytest.mark.parametrize("frozen", [False, True])
def test_wallet_cheat_http_route_is_registered_in_all_builds(monkeypatch, frozen):
    monkeypatch.setattr(web, "FROZEN", frozen)
    routes = web.build_api_routes()
    assert routes.resolve("POST", "/api/cheat-balance") is not None
    bank_cheat_route = routes.resolve("POST", "/api/bank/cheat-hundred-trillion")
    assert (bank_cheat_route is not None) is (not frozen)


@pytest.mark.parametrize("method,payload,target,args,kwargs,transient", [
    ("shop_purchase", {"sku": "item-a", "quantity": "2", "free_purchase": True},
     "buy_item", ("item-a", 2), {}, ("payment",)),
    ("shop_batch_purchase", {"items": [{"sku": "item-a", "quantity": 2}]},
     "buy_items", ([{"sku": "item-a", "quantity": 2}],), {},
     ("payment", "purchases")),
    ("transfer_wallet", {"direction": "recharge", "amount": "25", "data_scope_id": "account-a"},
     "transfer_wallet", ("recharge", 25.0), {}, ()),
    ("grant_temporary_bank_cheat", {}, "adjust_bank_balance",
     (100_000_000_000_000, "temporary_bank_cheat"), {"source": "bank_cheat_button"}, ()),
])
def test_economy_mutations_keep_arguments_guard_and_transient_projection(
    monkeypatch, method, payload, target, args, kwargs, transient,
):
    state = account_state()
    response = {"casino_balance": 75, "bank_balance": 125,
                "payment": {"id": "p1"}, "purchases": ["item-a"]}

    def mutate(*received_args, **received_kwargs):
        assert state.lock.depth == 1
        assert received_args == args
        assert received_kwargs == kwargs
        return dict(response)

    monkeypatch.setattr(services, target, mutate)
    result = getattr(state._account_application(), method)(payload)
    assert {key: result[key] for key in response} == response
    assert result["state_patch"] == {
        "balance": 75.0,
        "economy": {key: value for key, value in response.items() if key not in transient},
    }
    assert result["state_sync"] == {"data_version": 7, "data_scope_id": "account-a"}
    assert state.lock.depth == 0
    if method in {"transfer_wallet", "grant_temporary_bank_cheat"}:
        state._bind_wallet_scope.assert_called_once_with(payload.get("data_scope_id", ""))
        state._bind_current_save.assert_not_called()
    else:
        state._bind_current_save.assert_called_once_with()
        state._bind_wallet_scope.assert_not_called()


def test_credit_clear_uses_guarded_context_and_preserves_status(monkeypatch):
    state = account_state()
    state._total_weekly_salary = Mock(return_value=120.0)
    monkeypatch.setattr(services, "clear_credit_cheat", lambda: {"bank_balance": 900})
    monkeypatch.setattr(services, "credit_effective_bet_count", lambda: 12)

    def status(game_date, salary, effective_bets):
        assert state.lock.depth == 1
        assert (game_date, salary, effective_bets) == ("2028-01-01", 120.0, 12)
        return {"eligible": True}

    monkeypatch.setattr(services, "credit_status", status)
    result = state._account_application().clear_credit()
    assert result["credit"] == {"eligible": True}
    assert result["state_patch"]["economy"]["credit"] == result["credit"]
    state._total_weekly_salary.assert_called_once_with(state.club_contexts)
    assert state.lock.depth == 0


def test_account_guard_rejects_scope_before_any_wallet_write(monkeypatch):
    state = account_state()
    state._bind_wallet_scope.side_effect = ValueError("scope changed")
    transfer = Mock()
    monkeypatch.setattr(services, "transfer_wallet", transfer)
    with pytest.raises(ValueError, match="scope changed"):
        state._account_application().transfer_wallet({"data_scope_id": "other"})
    transfer.assert_not_called()
    assert state.lock.depth == 0


def test_wallet_response_is_tagged_with_the_account_actually_bound(monkeypatch):
    state = account_state()
    state._bind_wallet_scope.return_value = "account-wallet"
    monkeypatch.setattr(services, "transfer_wallet", lambda *args: {"casino_balance": 25})
    result = state._account_application().transfer_wallet({
        "data_scope_id": "account-wallet", "direction": "recharge", "amount": 25,
    })
    assert result["state_sync"] == {"data_version": 7, "data_scope_id": "account-wallet"}


def test_storage_failure_releases_guard_without_retry_or_projection(monkeypatch):
    state = account_state()
    write = Mock(side_effect=OSError("failed account commit"))
    project = Mock()
    monkeypatch.setattr(services, "cheat_balance", write)
    monkeypatch.setattr(services, "public_economy", project)
    with pytest.raises(OSError, match="failed account commit"):
        state.update_cheat_balance({"clear": True, "amount": "ignored"})
    write.assert_called_once_with(amount=None, clear=True)
    project.assert_not_called()
    assert state.lock.depth == 0


def test_account_service_runs_with_explicit_context_without_runtime_host(monkeypatch):
    events = []

    @contextmanager
    def operation(scope):
        events.append(("enter", scope))
        try:
            yield services.AccountOperation(
                scope_id="account-a", game_date="2028-01-01",
                weekly_salary=lambda: 0, temporary_bank_cheat=(1, "test"),
                state_patch=lambda response, patch: {**response, "patch": patch},
                economy_patch=lambda response, **kwargs: response,
            )
        finally:
            events.append(("exit", scope))

    def add(amount):
        assert events[-1] == ("enter", None)
        return {"balance": amount}

    monkeypatch.setattr(services, "add_wallet_funds", add)
    service = services.AccountApplicationService(operation)
    assert service.add_funds(50) == {"balance": 50}
    assert events == [("enter", None), ("exit", None)]
