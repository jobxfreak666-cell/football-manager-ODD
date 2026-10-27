from __future__ import annotations

import unittest
import struct
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools import club_reader
from tools.player_effects import PlayerEffectRollbackError

from tools.club_economy import (
    perform_psychological_counseling,
    psychological_counseling_outcome,
)
from tools.club_reader import PERSON_CONTRACT, _fm24_unhappiness_records, _person_has_unhappiness


class _Fm24UnhappinessReader:
    def __init__(self) -> None:
        self.layout = SimpleNamespace(key="fm24")
        self.pointers = {
            0x1000 + 0xC8: 0x2000,
            0x2000 + 0x08: 0x1000,
            0x2000 + 0x10: 0x3000,
            0x2000 + 0x28: 0x4000,
            0x4000 + 0x08: 0x5000,
        }
        self.values = {
            0x4000: 1,
            0x5000: (2023 << 16) | 295,
            0x5000 + 0x04: (1900 << 16) | 1,
        }

    def ptr(self, address: int) -> int:
        return self.pointers.get(address, 0)

    def u32(self, address: int) -> int | None:
        return self.values.get(address)


@pytest.mark.parametrize("rollback_failure", [None, "write", "readback"])
def test_counseling_partial_write_is_restored_and_verified_or_classified(rollback_failure):
    """A write API may mutate its destination before reporting failure."""
    reader = _Fm24UnhappinessReader()
    module = SimpleNamespace(base_address=0x9000)
    reader.layout = SimpleNamespace(key="fm24", game_date_rva=0x20, module=lambda _p: module)
    reader.values[0x9020] = (2023 << 16) | 296
    reader.values[0x4000] = 2
    second_record = 0x5000 + club_reader.FM24_UNHAPPINESS_RECORD_SIZE
    reader.values[second_record] = (2023 << 16) | 295
    reader.values[second_record + 4] = (1900 << 16) | 1
    original = struct.pack("<I", (1900 << 16) | 1)
    addresses = (0x5004, second_record + 4)
    memory = {address: original for address in addresses}
    reads = []
    writes = []
    operation_error = OSError("partial write failed")
    restore_error = OSError("restore write failed")

    def read_bytes(address, size):
        reads.append((address, bytes(memory[address])))
        return memory[address][:size]

    reader.bytes = read_bytes
    reader.invalidate_prefetch = lambda: None
    process = object()

    def write(handle, address, encoded):
        assert handle is process
        writes.append((address, encoded))
        if len(writes) == 2:
            memory[address] = encoded[:1] + memory[address][1:]
            raise operation_error
        if encoded == original and address == addresses[1]:
            if rollback_failure == "write":
                raise restore_error
            if rollback_failure == "readback":
                return  # The native call claims success without restoring the bytes.
        memory[address] = encoded

    with (
        patch.object(club_reader, "select_process_layout", return_value=(7, "", reader.layout)),
        patch.object(club_reader, "open_process", return_value=nullcontext(process)),
        patch.object(club_reader, "Reader", return_value=reader),
        patch.object(club_reader, "_validated_player_person", return_value=0x1000),
        patch.object(club_reader, "write_process_memory", side_effect=write),
    ):
        expected = PlayerEffectRollbackError if rollback_failure else OSError
        with pytest.raises(expected) as caught:
            club_reader.apply_psychological_counseling_effect(2, "0x8000", "unlocked")

    assert [address for address, _ in writes] == [
        addresses[0], addresses[1], addresses[1], addresses[0],
    ]
    assert memory[addresses[0]] == original  # Keep restoring after another rollback fails.
    assert (addresses[0], original) in reads[2:]
    if rollback_failure:
        assert caught.value.operation_error is operation_error
        assert caught.value.__cause__ is operation_error
        if rollback_failure == "write":
            assert caught.value.rollback_error is restore_error
        else:
            assert isinstance(caught.value.rollback_error, RuntimeError)
    else:
        assert caught.value is operation_error
        assert memory == {address: original for address in addresses}
        assert (addresses[1], original) in reads[2:]


class PsychologicalCounselingTests(unittest.TestCase):
    def test_fm24_unhappiness_reads_active_contract_record(self) -> None:
        _contract, records = _fm24_unhappiness_records(
            _Fm24UnhappinessReader(), 0x1000, date(2023, 10, 23),
        )
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["active"])
        self.assertEqual(records[0]["init_date"], date(2023, 10, 22))

    def test_roster_unhappiness_status_reuses_validated_person_contract(self) -> None:
        reader = _Fm24UnhappinessReader()
        self.assertTrue(
            _person_has_unhappiness(reader, 0x1000, date(2023, 10, 23))
        )

        fm26 = _Fm24UnhappinessReader()
        fm26.layout = SimpleNamespace(key="fm26")
        fm26.pointers = {
            0x1000 + PERSON_CONTRACT: 0x2000,
            0x2000 + 0x08: 0x1000,
            0x2000 + 0x10: 0x3000,
            0x2000 + 0x30: 0x4000,
        }
        self.assertTrue(_person_has_unhappiness(fm26, 0x1000, None))

    def test_outcome_is_always_relief(self) -> None:
        self.assertEqual(
            {psychological_counseling_outcome() for _ in range(100)}, {"unlocked"},
        )

    def test_every_session_resolves_unhappiness(self) -> None:
        state = {
            "owned_activity_centres": ["talk_room"],
            "owned_activity_facilities": [],
            "activity_floor_cooldowns": {},
            "psychological_counseling": {},
            "activity_progress": {},
            "activity_history": [],
        }
        applied = []
        with patch("tools.club_economy.load_economy", return_value=state), patch(
            "tools.club_economy.save_economy"
        ), patch("tools.club_economy.account_transaction", nullcontext), patch(
            "tools.club_economy.random.random", side_effect=AssertionError("no roll"),
        ):
            result = perform_psychological_counseling(
                1, 2, "球员", "2028-01-01", 20,
                lambda outcome, points: applied.append((outcome, points)) or {
                    "before": 20, "after": 20, "applied": points,
                    "effect": {"field": outcome, "effects": [
                        {"field": "unhappiness", "after": False},
                    ]},
                },
            )
        self.assertEqual(result["outcome"], "unlocked")
        self.assertEqual(result["outcome_name"], "彻底释怀")
        self.assertEqual(applied, [("unlocked", 0)])
        self.assertFalse(result["effect"]["effects"][0]["after"])

    def test_session_uses_shared_two_day_floor_cooldown(self) -> None:
        state = {
            "owned_activity_centres": ["talk_room"],
            "owned_activity_facilities": [],
            "activity_floor_cooldowns": {},
            "psychological_counseling": {},
            "activity_progress": {},
            "activity_history": [],
        }
        with patch("tools.club_economy.load_economy", return_value=state), patch(
            "tools.club_economy.save_economy"
        ), patch("tools.club_economy.account_transaction", nullcontext):
            result = perform_psychological_counseling(
                1, 2, "球员", "2028-01-01", 20,
                lambda outcome, points: {
                    "before": 20, "after": 20, "applied": points,
                    "effect": {"field": outcome, "effects": []},
                },
            )
            self.assertEqual(result["cooldown_until"], "2028-01-03")
            with self.assertRaisesRegex(ValueError, "2F活动冷却至 2028-01-03"):
                perform_psychological_counseling(
                    1, 2, "球员", "2028-01-02", 19,
                    lambda _outcome, _points: {},
                )


if __name__ == "__main__":
    unittest.main()
