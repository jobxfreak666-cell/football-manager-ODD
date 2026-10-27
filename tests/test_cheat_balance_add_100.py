from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools import betting_account, club_economy
from tools.money import to_minor, write_minor


def _wallet(root: Path, balance: float) -> None:
    path = root / "bets" / "fm26_wallet.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema_version": 1, "balance": balance,
        "credit_effective_bet_count": 0, "transactions": [],
    }), encoding="utf-8")


@pytest.mark.parametrize("amount", [100, 100_000_000_000])
def test_cheat_balance_adds_requested_amount_and_persists(tmp_path, amount):
    _wallet(tmp_path, 12.5)
    with patch("tools.betting_account.save_data_root", return_value=tmp_path):
        wallet = betting_account.cheat_balance(amount=amount)
        assert wallet["balance"] == 12.5 + amount
        assert betting_account.available_balance() == 12.5 + amount
        last = betting_account.load_wallet()["transactions"][-1]
    assert last["type"] == "cheat_funding" and last["amount"] == amount


def test_cheat_balance_still_rejects_other_amounts(tmp_path):
    _wallet(tmp_path, 0)
    with patch("tools.betting_account.save_data_root", return_value=tmp_path):
        with pytest.raises(ValueError):
            betting_account.cheat_balance(amount=99)


@pytest.mark.parametrize("amount", [100, 100_000_000_000])
def test_cheat_balance_leaves_bank_unchanged(tmp_path, amount):
    _wallet(tmp_path, 0)
    economy = club_economy._new_state()
    write_minor(economy, "general_balance", to_minor(1_000_000))
    economy["wallet_mode"] = "bank_v2"
    path = tmp_path / "economy" / "club_economy.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(economy), encoding="utf-8")
    with (
        patch("tools.club_economy.save_data_root", return_value=tmp_path),
        patch("tools.betting_account.save_data_root", return_value=tmp_path),
    ):
        bank_before = club_economy.public_economy()["bank_balance"]
        betting_account.cheat_balance(amount=amount)
        assert betting_account.available_balance() == amount
        assert club_economy.public_economy()["bank_balance"] == bank_before
