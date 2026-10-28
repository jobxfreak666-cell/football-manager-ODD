"""Focused tests for ``tools.competition_catalog``.

The module is a pure projection: it joins the native competition table with the
already-published standings payload and publishes, for every competition, an
explicit, stable reason when no native table exists.  These tests use a fake
reader so they never touch a live game, a save or an account.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import probe_competition_catalog as catalog_probe
from tools import competition_catalog
from tools.competition_catalog import (
    LEAGUE_CATALOG_SOURCE_NATIVE,
    LEAGUE_CATALOG_SOURCE_UNAVAILABLE,
    STANDINGS_REASON_CODES,
    STANDINGS_REASON_ORDER,
    STANDINGS_SOURCE_NATIVE,
    STANDINGS_SOURCE_RECONSTRUCTED,
    build_league_catalog,
    catalog_competitions,
    catalog_layout,
    formats_index,
    invalidate_league_catalog,
    last_league_catalog_metrics,
    native_skip_reason,
    scan_native_competitions,
    unavailable_league_catalog,
)

TOP_LEVEL_KEYS = {
    "source", "scope_id", "game_layout", "native", "scanned_at", "competitions",
}
COMPETITION_KEYS = {
    "competition_id", "name", "short_name", "reputation",
    "standings_available", "standings_source", "standings_reason",
}


class FakeLayout:
    """Minimal GameLayout surface used by the catalog."""

    def __init__(self, offset=0x188, width=1, name="Football Manager 26"):
        self.competition_reputation_offset = offset
        self.competition_reputation_bytes = width
        self.display_name = name


class FakeIndex:
    def __init__(self, addresses, token=("t", 1, "fp")):
        self._addresses = tuple(addresses)
        self.token = token
        self.address_calls = 0
        self.token_calls = 0

    def addresses(self, name, *, force=False):
        self.address_calls += 1
        return self._addresses

    def table_token(self, name):
        self.token_calls += 1
        return self.token


class FakeReader:
    """Fake read-only reader returning canned competition rows."""

    def __init__(self, rows, *, layout=None, token=("t", 1, "fp")):
        self.rows = dict(rows)
        self.layout = layout or FakeLayout()
        self.index = FakeIndex(sorted(self.rows), token=token)
        self.database_index_provider = lambda *a, **k: self.index
        self.database_index_error_provider = lambda: ""
        self.reads = 0
        self.reputations = {address: 50 for address in self.rows}
        self.prefetched = []

    # -- plumbing the scanner uses ------------------------------------------
    def prefetch(self, address, size):
        self.prefetched.append((address, size))

    def competition(self, address):
        self.reads += 1
        return self.rows.get(address)

    def u8(self, address):
        return self.reputations.get(address - self.layout.competition_reputation_offset, 0)

    def u16(self, address):
        return self.reputations.get(address - self.layout.competition_reputation_offset, 0)

    def read_metrics(self):
        return {"memory_read_calls": self.reads}


def _row(competition_id, name="League", short_name="LG", address=0x1000, reputation=50):
    return {
        "competition_id": competition_id,
        "name": name,
        "short_name": short_name,
        "address": hex(address),
        "reputation": reputation,
    }


def _format(**overrides):
    item = {
        "competition_id": 10,
        "competition_name": "Test League",
        "competition_kind": "league",
        "opening_stage_type": "league",
        "opening_field_complete": True,
        "opening_slot_count": 2,
        "opening_teams": [
            {"id": 1, "name": "A", "played": 10, "native_standing_verified": True},
            {"id": 2, "name": "B", "played": 10, "native_standing_verified": True},
        ],
    }
    item.update(overrides)
    return item


def _team(team_id, played, name):
    return {"team_id": team_id, "team_name": name, "played": played}


def _standings(*competitions):
    return {"competitions": list(competitions), "source": "reconstructed_results"}


@contextmanager
def _no_game(*args, **kwargs):
    raise RuntimeError("no live game in tests")
    yield  # pragma: no cover - keeps this a generator


class ReasonCodeContractTests(unittest.TestCase):
    def test_contract_documents_every_code_with_source_lines(self):
        self.assertEqual(set(STANDINGS_REASON_CODES), set(STANDINGS_REASON_ORDER))
        for code, (condition, lines) in STANDINGS_REASON_CODES.items():
            self.assertEqual(code, code.lower(), code)
            self.assertEqual(code, code.encode("ascii").decode("ascii"), code)
            self.assertEqual(code.replace("_", "").isalnum(), True, code)
            self.assertTrue(condition.strip(), code)
            # Every code must name the branch it mirrors.
            self.assertRegex(lines, r":\d", code)

    def test_unknown_layout_publishes_empty_string(self):
        self.assertEqual(catalog_layout(None), "")
        self.assertEqual(catalog_layout({}), "")
        self.assertEqual(catalog_layout({"game_layout": "fm23"}), "")
        self.assertEqual(catalog_layout({"game_layout": "fm26"}), "fm26")
        self.assertEqual(catalog_layout({"game_layout": "fm24"}), "fm24")


class SkipReasonTests(unittest.TestCase):
    """One test per branch of league_standings._native_format_standings."""

    def test_eligible_format_has_no_reason(self):
        self.assertIsNone(native_skip_reason(_format()))

    def test_missing_format_is_no_native_format(self):
        self.assertEqual(native_skip_reason(None), "no_native_format")

    def test_zero_competition_id_is_no_native_format(self):
        self.assertEqual(
            native_skip_reason(_format(competition_id=0)), "no_native_format",
        )

    def test_non_league_kind(self):
        self.assertEqual(
            native_skip_reason(_format(competition_kind="cup")), "not_a_league",
        )

    def test_non_league_opening_stage(self):
        self.assertEqual(
            native_skip_reason(_format(opening_stage_type="group")),
            "not_league_opening_stage",
        )

    def test_incomplete_opening_field(self):
        self.assertEqual(
            native_skip_reason(_format(opening_field_complete=False)),
            "opening_field_incomplete",
        )

    def test_slot_count_mismatch(self):
        self.assertEqual(
            native_skip_reason(_format(opening_slot_count=3)),
            "opening_slot_count_invalid",
        )

    def test_slot_count_too_small(self):
        self.assertEqual(
            native_skip_reason(_format(opening_slot_count=1, opening_teams=[
                {"id": 1, "native_standing_verified": True},
            ])),
            "opening_slot_count_invalid",
        )

    def test_unverified_team(self):
        item = _format(opening_teams=[
            {"id": 1, "played": 10, "native_standing_verified": True},
            {"id": 2, "played": 10, "native_standing_verified": False},
        ])
        self.assertEqual(native_skip_reason(item), "team_standing_unverified")

    def test_zero_team_id_breaks_the_row_build(self):
        item = _format(opening_teams=[
            {"id": 1, "played": 10, "native_standing_verified": True},
            {"id": 0, "played": 10, "native_standing_verified": True},
        ])
        self.assertEqual(native_skip_reason(item), "native_rows_incomplete")

    def test_reconstructed_ahead_suppresses_native(self):
        item = _format()
        reconstructed = [_team(1, 11, "A"), _team(2, 11, "B")]
        self.assertEqual(
            native_skip_reason(item, reconstructed),
            "reconstructed_ahead_of_native",
        )

    def test_reconstructed_behind_keeps_native(self):
        item = _format()
        reconstructed = [_team(1, 9, "A"), _team(2, 10, "B")]
        self.assertIsNone(native_skip_reason(item, reconstructed))

    def test_reconstructed_same_played_keeps_native(self):
        item = _format()
        reconstructed = [_team(1, 10, "A"), _team(2, 10, "B")]
        self.assertIsNone(native_skip_reason(item, reconstructed))

    def test_reconstructed_different_teams_keeps_native(self):
        item = _format()
        reconstructed = [_team(1, 12, "A"), _team(3, 12, "C")]
        self.assertIsNone(native_skip_reason(item, reconstructed))

    def test_precedence_follows_reason_order(self):
        # Both a wrong kind and an incomplete field hold; the earlier branch wins.
        item = _format(competition_kind="cup", opening_field_complete=False)
        self.assertEqual(native_skip_reason(item), "not_a_league")


class CatalogJoinTests(unittest.TestCase):
    def test_native_rows_become_entries_with_seven_keys(self):
        entries = catalog_competitions((_row(11, "Alpha"),), None, None)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(set(entry), COMPETITION_KEYS)
        self.assertEqual(entry["competition_id"], 11)
        self.assertEqual(entry["name"], "Alpha")
        self.assertEqual(entry["short_name"], "LG")
        self.assertEqual(entry["reputation"], 50)
        self.assertFalse(entry["standings_available"])
        self.assertIsNone(entry["standings_source"])
        self.assertEqual(entry["standings_reason"], "no_native_format")

    def test_native_standings_are_available_with_native_source(self):
        standings = _standings({
            "competition_id": 11,
            "competition_name": "Alpha",
            "source": "native_league_stage",
            "teams": [_team(1, 10, "A")],
        })
        entries = catalog_competitions((_row(11),), standings, None)
        entry = entries[0]
        self.assertTrue(entry["standings_available"])
        self.assertEqual(entry["standings_source"], STANDINGS_SOURCE_NATIVE)
        self.assertIsNone(entry["standings_reason"])

    def test_reconstructed_standings_are_available_with_a_reason(self):
        output = {"competition_formats": [_format(competition_id=11, opening_slot_count=1, opening_teams=[
            {"id": 1, "played": 8, "native_standing_verified": True},
        ])]}
        standings = _standings({
            "competition_id": 11,
            "competition_name": "Alpha",
            "teams": [_team(1, 8, "A")],
        })
        entries = catalog_competitions((_row(11),), standings, output)
        entry = entries[0]
        self.assertTrue(entry["standings_available"])
        self.assertEqual(entry["standings_source"], STANDINGS_SOURCE_RECONSTRUCTED)
        # Available, but still explains why the native table was not used.
        self.assertIn(entry["standings_reason"], STANDINGS_REASON_ORDER)

    def test_formats_only_competition_is_listed(self):
        output = {"competition_formats": [_format(competition_id=12, competition_name="Cup")]}
        entries = catalog_competitions((), None, output)
        self.assertEqual([item["competition_id"] for item in entries], [12])
        self.assertEqual(entries[0]["reputation"], 0)

    def test_unlisted_cup_reports_its_real_branch_not_a_suppression(self):
        """A cup in neither list must not be blamed on a suppression branch."""
        output = {"competition_formats": [_format(competition_id=21, competition_kind="cup")]}
        entry = catalog_competitions((_row(21),), None, output)[0]
        self.assertFalse(entry["standings_available"])
        self.assertIsNone(entry["standings_source"])
        self.assertEqual(entry["standings_reason"], "not_a_league")

    def test_unlisted_eligible_league_reports_no_standings_yet(self):
        """Eligible but unpublished is 'no rows yet', not a suppression."""
        output = {"competition_formats": [_format(
            competition_id=22, opening_slot_count=2,
            opening_teams=[
                {"id": 1, "native_standing_verified": True},
                {"id": 2, "native_standing_verified": True},
            ],
        )]}
        entry = catalog_competitions((_row(22),), None, output)[0]
        self.assertFalse(entry["standings_available"])
        self.assertIsNone(entry["standings_source"])
        self.assertEqual(entry["standings_reason"], "no_native_format")
        self.assertNotEqual(entry["standings_reason"], "reconstructed_ahead_of_native")

    def test_entries_are_sorted_by_reputation_then_name(self):
        rows = (
            _row(1, "Zeta", reputation=10),
            _row(2, "alpha", reputation=90),
            _row(3, "Beta", reputation=10),
        )
        entries = catalog_competitions(rows, None, None)
        self.assertEqual([item["competition_id"] for item in entries], [2, 3, 1])

    def test_unavailable_entries_always_carry_a_reason(self):
        output = {"competition_formats": [
            _format(competition_id=13, competition_kind="cup"),
            _format(competition_id=14, opening_field_complete=False),
        ]}
        entries = catalog_competitions((_row(13), _row(14)), None, output)
        self.assertEqual(len(entries), 2)
        for entry in entries:
            if entry["standings_available"]:
                continue
            self.assertIsInstance(entry["standings_reason"], str)
            self.assertIn(entry["standings_reason"], STANDINGS_REASON_ORDER)

    def test_duplicate_native_ids_collapse(self):
        rows = (_row(5, "First", short_name="F"), _row(5, "", short_name=""))
        entries = catalog_competitions(rows, None, None)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "First")

    def test_formats_index_skips_blank_rows(self):
        index = formats_index({"competition_formats": [
            _format(competition_id=20),
            {"competition_id": 0},
            "not-a-mapping",
            _format(competition_id=21),
        ]})
        self.assertEqual(sorted(index), [20, 21])


class ScanTests(unittest.TestCase):
    def test_scan_reads_every_address_and_dedupes(self):
        reader = FakeReader({
            0x1000: {"id": 7, "name": "Seven", "short_name": "", "address": "0x1000"},
            0x1008: {"id": 7, "name": "Seven", "short_name": "S7", "address": "0x1008"},
            0x1010: {"id": 8, "name": "Eight", "short_name": "E", "address": "0x1010"},
        })
        rows = scan_native_competitions(reader)
        self.assertEqual([row["competition_id"] for row in rows], [7, 8])
        # The thin duplicate at 0x1000 must not blank the real short name.
        self.assertEqual(rows[0]["short_name"], "S7")
        self.assertEqual(len(reader.prefetched), 3)

    def test_scan_skips_zero_addresses(self):
        reader = FakeReader({0x1000: {"id": 7, "name": "Seven", "short_name": "S",
                                      "address": "0x1000"}})
        reader.index = FakeIndex([0x1000, 0])
        reader.database_index_provider = lambda *a, **k: reader.index
        rows = scan_native_competitions(reader)
        self.assertEqual([row["competition_id"] for row in rows], [7])

    def test_scan_publishes_zero_reputation_when_layout_has_no_offset(self):
        reader = FakeReader(
            {0x1000: {"id": 7, "name": "Seven", "short_name": "S", "address": "0x1000"}},
            layout=FakeLayout(offset=None, width=None),
        )
        rows = scan_native_competitions(reader)
        self.assertEqual(rows[0]["reputation"], 0)

    def test_scan_rejects_out_of_range_reputation(self):
        reader = FakeReader(
            {0x1000: {"id": 7, "name": "Seven", "short_name": "S", "address": "0x1000"}},
        )
        reader.reputations = {0x1000: 250}
        rows = scan_native_competitions(reader)
        self.assertEqual(rows[0]["reputation"], 0)

    def test_scan_reads_two_bytes_for_fm24_layout(self):
        class TwoByteReader(FakeReader):
            def __init__(self, rows, **kwargs):
                super().__init__(rows, **kwargs)
                self.widths = []

            def u16(self, address):
                self.widths.append(16)
                return 42

            def u8(self, address):
                self.widths.append(8)
                return 1

        reader = TwoByteReader(
            {0x1000: {"id": 7, "name": "Seven", "short_name": "S", "address": "0x1000"}},
            layout=FakeLayout(offset=0x188, width=2, name="Football Manager 24"),
        )
        rows = scan_native_competitions(reader)
        self.assertEqual(reader.widths, [16])
        self.assertEqual(rows[0]["reputation"], 42)


class BuildTests(unittest.TestCase):
    def tearDown(self):
        competition_catalog.invalidate_league_catalog()

    def test_unavailable_payload_keeps_the_six_key_contract(self):
        payload = unavailable_league_catalog(
            {"game_layout": "fm26", "competition_formats": [_format(competition_id=9)]},
            scope_id="scope-a",
        )
        self.assertEqual(set(payload), TOP_LEVEL_KEYS)
        self.assertEqual(payload["source"], LEAGUE_CATALOG_SOURCE_UNAVAILABLE)
        self.assertEqual(payload["scope_id"], "scope-a")
        self.assertEqual(payload["game_layout"], "fm26")
        self.assertFalse(payload["native"])
        self.assertTrue(payload["scanned_at"])
        self.assertEqual(len(payload["competitions"]), 1)
        self.assertEqual(set(payload["competitions"][0]), COMPETITION_KEYS)

    def test_build_degrades_when_no_game_session(self):
        with patch("tools.game_session.borrow_game_reader", _no_game):
            payload = build_league_catalog(
                {"game_layout": "fm26", "competition_formats": [_format(competition_id=9)]},
                scope_id="scope-b",
            )
        self.assertEqual(payload["source"], LEAGUE_CATALOG_SOURCE_UNAVAILABLE)
        self.assertFalse(payload["native"])
        self.assertEqual(payload["scope_id"], "scope-b")
        self.assertEqual(len(payload["competitions"]), 1)
        metrics = last_league_catalog_metrics()
        self.assertIn("session", metrics["note"])

    def test_build_reads_natively_with_an_explicit_reader(self):
        reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        payload = build_league_catalog(
            {"game_layout": "fm26"}, scope_id="scope-c", reader=reader,
        )
        self.assertEqual(set(payload), TOP_LEVEL_KEYS)
        self.assertEqual(payload["source"], LEAGUE_CATALOG_SOURCE_NATIVE)
        self.assertTrue(payload["native"])
        self.assertEqual(payload["scanned_at"], payload["scanned_at"])
        self.assertEqual(len(payload["competitions"]), 1)
        self.assertEqual(payload["competitions"][0]["competition_id"], 30)

    def test_build_uses_the_passed_standings_not_a_recompute(self):
        reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        standings = _standings({
            "competition_id": 30,
            "competition_name": "Alpha",
            "source": "native_league_stage",
            "teams": [_team(1, 10, "A")],
        })
        payload = build_league_catalog(
            {"game_layout": "fm26"}, standings=standings, reader=reader,
        )
        self.assertTrue(payload["competitions"][0]["standings_available"])
        self.assertEqual(
            payload["competitions"][0]["standings_source"], STANDINGS_SOURCE_NATIVE,
        )

    def test_second_build_reuses_the_cached_scan(self):
        reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        first = build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)
        reads_after_first = reader.reads
        second = build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)
        self.assertEqual(reader.reads, reads_after_first, "cache hit must not re-walk")
        self.assertTrue(last_league_catalog_metrics()["cache_hit"])
        self.assertEqual(first["competitions"], second["competitions"])
        # scanned_at is the cache timestamp, so it is stable across a hit.
        self.assertEqual(first["scanned_at"], second["scanned_at"])

    def test_force_rescans(self):
        reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)
        reads_after_first = reader.reads
        build_league_catalog(
            {"game_layout": "fm26"}, scope_id="s", reader=reader, force=True,
        )
        self.assertGreater(reader.reads, reads_after_first)

    def test_table_token_change_invalidates_the_cache(self):
        reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)
        reader.index.token = ("t", 2, "fp2")
        reader.rows[0x1008] = {
            "id": 31, "name": "Beta", "short_name": "B", "address": "0x1008",
        }
        reader.index._addresses = (0x1000, 0x1008)
        payload = build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)
        self.assertEqual(
            [item["competition_id"] for item in payload["competitions"]], [30, 31],
        )
        self.assertFalse(last_league_catalog_metrics()["cache_hit"])

    def test_new_session_generation_does_not_reuse_native_rows(self):
        first_reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        first_reader.session_generation = 1
        build_league_catalog({"game_layout": "fm26"}, scope_id="same-save", reader=first_reader)

        second_reader = FakeReader({
            0x1000: {"id": 31, "name": "Beta", "short_name": "B", "address": "0x1000"},
        })
        # Model a new lease in a new session where the pointer table token is
        # unchanged, so generation must participate in the cache identity.
        second_reader.index = first_reader.index
        second_reader.session_generation = 2
        payload = build_league_catalog(
            {"game_layout": "fm26"}, scope_id="same-save", reader=second_reader,
        )

        self.assertEqual([item["competition_id"] for item in payload["competitions"]], [31])
        self.assertFalse(last_league_catalog_metrics()["cache_hit"])

    def test_same_table_token_refreshes_changed_competition_fields_after_ttl(self):
        reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        with patch("tools.competition_catalog.time.monotonic", side_effect=[100.0, 100.0]):
            first = build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)
        reader.rows[0x1000] = {
            "id": 30, "name": "Renamed", "short_name": "R", "address": "0x1000",
        }
        reader.reputations[0x1000] = 77

        with patch("tools.competition_catalog.time.monotonic", side_effect=[106.0, 106.0]):
            second = build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)

        self.assertEqual(first["competitions"][0]["name"], "Alpha")
        self.assertEqual(second["competitions"][0]["name"], "Renamed")
        self.assertEqual(second["competitions"][0]["reputation"], 77)
        self.assertFalse(last_league_catalog_metrics()["cache_hit"])

    def test_incomplete_object_scan_is_not_cached_and_can_recover(self):
        class RecoveringReader(FakeReader):
            fail = True

            def competition(self, address):
                if self.fail:
                    self.reads += 1
                    raise OSError("transient read failure")
                return super().competition(address)

        reader = RecoveringReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        fallback = build_league_catalog(
            {"game_layout": "fm26", "competition_formats": [_format(competition_id=9)]},
            scope_id="s", reader=reader,
        )
        self.assertEqual(fallback["source"], LEAGUE_CATALOG_SOURCE_UNAVAILABLE)
        self.assertEqual([item["competition_id"] for item in fallback["competitions"]], [9])
        self.assertEqual(last_league_catalog_metrics()["cached_scopes"], 0)

        reader.fail = False
        recovered = build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)
        self.assertEqual(recovered["source"], LEAGUE_CATALOG_SOURCE_NATIVE)
        self.assertEqual([item["competition_id"] for item in recovered["competitions"]], [30])
        self.assertFalse(last_league_catalog_metrics()["cache_hit"])

    def test_none_object_read_is_not_cached_and_can_recover(self):
        class NoneOnceReader(FakeReader):
            fail = True

            def competition(self, address):
                if address == 0x1010 and self.fail:
                    self.reads += 1
                    return None
                return super().competition(address)

        reader = NoneOnceReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
            0x1010: {"id": 31, "name": "Beta", "short_name": "B", "address": "0x1010"},
        })
        reader.index = FakeIndex([0x1000, 0x1010])
        reader.database_index_provider = lambda *a, **k: reader.index
        output = {"game_layout": "fm26", "competition_formats": [_format(competition_id=30)]}

        incomplete = build_league_catalog(output, scope_id="none-once", reader=reader)
        self.assertEqual(incomplete["source"], LEAGUE_CATALOG_SOURCE_UNAVAILABLE)
        self.assertEqual([row["competition_id"] for row in incomplete["competitions"]], [30])
        self.assertEqual(last_league_catalog_metrics()["cached_scopes"], 0)

        reader.fail = False
        recovered = build_league_catalog(output, scope_id="none-once", reader=reader)
        self.assertEqual(recovered["source"], LEAGUE_CATALOG_SOURCE_NATIVE)
        self.assertEqual([row["competition_id"] for row in recovered["competitions"]], [30, 31])
        self.assertFalse(last_league_catalog_metrics()["cache_hit"])

    def test_scope_change_does_not_reuse_another_scope_rows(self):
        reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        build_league_catalog({"game_layout": "fm26"}, scope_id="one", reader=reader)
        build_league_catalog({"game_layout": "fm26"}, scope_id="two", reader=reader)
        self.assertGreaterEqual(last_league_catalog_metrics()["cached_scopes"], 1)
        self.assertFalse(last_league_catalog_metrics()["cache_hit"])

    def test_invalidate_forces_a_rescan(self):
        reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)
        reads_after_first = reader.reads
        invalidate_league_catalog()
        build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)
        self.assertGreater(reader.reads, reads_after_first)

    def test_failed_native_scan_degrades_instead_of_raising(self):
        class BoomReader(FakeReader):
            def competition(self, address):
                raise OSError("read failed")

        reader = BoomReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        payload = build_league_catalog({"game_layout": "fm26"}, scope_id="s", reader=reader)
        self.assertEqual(payload["source"], LEAGUE_CATALOG_SOURCE_UNAVAILABLE)
        self.assertFalse(payload["native"])
        self.assertIn("object read failed", last_league_catalog_metrics()["note"])
        self.assertEqual(last_league_catalog_metrics()["cached_scopes"], 0)

    def test_failed_native_scan_preserves_passed_standings(self):
        class BoomReader(FakeReader):
            def competition(self, address):
                raise OSError("read failed")

        reader = BoomReader({
            0x1000: {"id": 42, "name": "Reconstructed League", "short_name": "RL",
                     "address": "0x1000"},
        })
        standings = _standings({
            "competition_id": 42,
            "competition_name": "Reconstructed League",
            "source": "reconstructed_results",
            "teams": [_team(1, 10, "A")],
        })
        payload = build_league_catalog(
            {"game_layout": "fm26", "competition_formats": [_format(competition_id=42)]},
            scope_id="same-request", standings=standings, reader=reader,
        )

        entry = next(row for row in payload["competitions"] if row["competition_id"] == 42)
        self.assertEqual(payload["source"], LEAGUE_CATALOG_SOURCE_UNAVAILABLE)
        self.assertTrue(entry["standings_available"])
        self.assertEqual(entry["standings_source"], STANDINGS_SOURCE_RECONSTRUCTED)

    def test_missing_session_index_degrades_without_a_cold_scan(self):
        """A session that cannot supply its index must not trigger a 1.3s scan."""
        reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        # The borrowed reader advertises a provider, but the session has no index.
        reader.database_index_provider = lambda *a, **k: None

        with patch("tools.competition_catalog.DatabaseIndex") as cold_index:
            payload = build_league_catalog(
                {"game_layout": "fm26"}, scope_id="s", reader=reader,
            )
        cold_index.assert_not_called()
        self.assertEqual(payload["source"], LEAGUE_CATALOG_SOURCE_UNAVAILABLE)
        self.assertFalse(payload["native"])
        self.assertEqual(reader.reads, 0)
        self.assertIn("table read failed", last_league_catalog_metrics()["note"])

    def test_reader_without_a_provider_still_gets_a_local_index(self):
        reader = FakeReader({
            0x1000: {"id": 30, "name": "Alpha", "short_name": "A", "address": "0x1000"},
        })
        del reader.database_index_provider

        with patch("tools.competition_catalog.DatabaseIndex", return_value=reader.index) as local:
            rows = scan_native_competitions(reader)
        local.assert_called_once_with(reader)
        self.assertEqual([row["competition_id"] for row in rows], [30])

    def test_empty_output_still_publishes_a_valid_payload(self):
        with patch("tools.game_session.borrow_game_reader", _no_game):
            payload = build_league_catalog(None)
        self.assertEqual(set(payload), TOP_LEVEL_KEYS)
        self.assertEqual(payload["scope_id"], "")
        self.assertEqual(payload["game_layout"], "")
        self.assertEqual(payload["competitions"], [])

    def test_build_does_not_mutate_the_output(self):
        output = {"game_layout": "fm26", "competition_formats": [_format(competition_id=9)]}
        before = repr(output)
        with patch("tools.game_session.borrow_game_reader", _no_game):
            build_league_catalog(output, scope_id="s")
        self.assertEqual(repr(output), before)


class StandingsContractTests(unittest.TestCase):
    def test_public_league_standings_shape_is_untouched(self):
        from tools import league_standings

        table = league_standings.build_standings([
            {
                "competition_id": 1,
                "competition_name": "L",
                "competition_kind": "league",
                "date": "2026-08-01",
                "home": {"id": 10, "name": "A"},
                "away": {"id": 11, "name": "B"},
                "home_goals": 2,
                "away_goals": 0,
            },
        ])
        self.assertEqual(len(table), 1)
        self.assertEqual(table[0]["competition_id"], 1)
        row = table[0]["teams"][0]
        for key in ("team_id", "played", "won", "drawn", "lost", "points",
                    "goal_difference", "position", "goals_for", "goals_against"):
            self.assertIn(key, row)
        # The catalog must never inject its own keys into the standings rows.
        self.assertNotIn("standings_reason", row)
        self.assertNotIn("standings_available", row)


class CompetitionCatalogProbeTests(unittest.TestCase):
    def test_no_game_report_path_writes_utf8_labeled_full_catalog(self):
        state = {
            "output": {
                "game_layout": "fm26",
                "competition_formats": [
                    _format(competition_id=90, competition_name="甲级联赛"),
                    _format(competition_id=91, competition_name="杯赛"),
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            report_path = root / "probe.json"
            state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            argv = [
                "probe_competition_catalog.py", "--no-game",
                "--state-file", str(state_path), "--report-path", str(report_path),
                "--label", "before", "--limit", "1", "--full-catalog",
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                exit_code = catalog_probe.main()

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0, "explicit offline mode remains successful")
        self.assertTrue(report["ok"])
        self.assertEqual(report["label"], "before")
        self.assertEqual(report["catalog_source"], "unavailable")
        self.assertEqual(len(report["catalog_sample"]), 1)
        entries = sorted(
            report["catalog_entries"], key=lambda item: item["competition_id"],
        )
        self.assertEqual([item["competition_id"] for item in entries], [90, 91])
        self.assertEqual([item["name"] for item in entries], ["甲级联赛", "杯赛"])
        self.assertEqual(
            set(entries[0]), {"competition_id", "name", "short_name", "reputation"},
        )
        for provider in ("selection_provider", "hierarchy_provider"):
            self.assertEqual(report[provider]["status"], "unsupported")
            self.assertFalse(report[provider]["supported"])
        self.assertNotIn("loaded_competitions", report)

    def test_live_unavailable_catalog_fails_and_reports_layout_identity(self):
        class Layout:
            key = "fm26"
            display_name = "Football Manager 26"
            distribution = "steam"
            executable_sha256 = "profile-hash"
            module_name = "game_plugin.dll"

        class Reader:
            process_path = "C:/Games/FM26.exe"
            layout = Layout()

            def read_metrics(self):
                return {"memory_read_calls": 0, "memory_requested_bytes": 0}

        @contextmanager
        def borrow_reader(*args, **kwargs):
            yield Reader()

        rows = ({
            "competition_id": 30, "name": "Alpha", "short_name": "A", "reputation": 50,
        },)
        unavailable = {"source": "unavailable", "native": False, "competitions": []}
        with (
            patch("tools.game_session.borrow_game_reader", borrow_reader),
            patch.object(catalog_probe, "scan_native_competitions", return_value=rows),
            patch.object(catalog_probe, "build_league_catalog", return_value=unavailable),
        ):
            report = catalog_probe.probe_live({}, limit=5)

        self.assertFalse(report["ok"])
        self.assertEqual(report["catalog_source"], "unavailable")
        self.assertIn("unavailable", report["error"])
        self.assertEqual(report["game_identity"]["layout_key"], "fm26")
        self.assertEqual(report["game_identity"]["distribution"], "steam")
        self.assertEqual(report["game_identity"]["module_name"], "game_plugin.dll")
        self.assertEqual(report["game_identity"]["executable_sha256"], "profile-hash")
        self.assertNotIn("module_base", report["game_identity"])

        with patch.object(catalog_probe, "probe_live", return_value=report):
            with patch.object(sys, "argv", ["probe_competition_catalog.py"]):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(catalog_probe.main(), 1)


if __name__ == "__main__":
    unittest.main()
