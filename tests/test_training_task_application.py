from __future__ import annotations

import multiprocessing
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fm_odds_web import Handler, LocalOddsState, _training_error
from tools import account_store
from tools import training_ground as training_ground_module
from tools.app_settings import load_settings
from tools.betting_account import load_wallet, save_wallet
from tools.club_economy import load_economy, save_economy
from tools.i18n_runtime import MESSAGE_CATALOGS
from tools.money import read_minor, to_minor, write_minor
from tools.training_catalog import training_task_fee_minor
from tools.training_ground import (
    POSITION_TRAINING_AREA_ID, FACILITIES, active_training_focuses,
    load_training_ground, place_facility, purchase_facility,
    record_position_training_focus, save_training_ground,
)


def _fee_minor(sku: str) -> int:
    return training_task_fee_minor(FACILITIES[sku], load_settings())


def _storage_patches(root: Path) -> list:
    return [
        patch.object(account_store, "account_save_path", return_value=root / "save.fmodd"),
        patch.object(account_store, "save_data_root", return_value=root),
        patch("tools.training_ground.save_data_root", return_value=root),
        patch("tools.club_economy.save_data_root", return_value=root),
        patch("tools.betting_account.save_data_root", return_value=root),
    ]


def _submit_training_process(root, player_id, submission_id, started, preview, resume, results):
    """Use independent application/account locks against the same temporary file."""
    with ExitStack() as stack:
        for storage_patch in _storage_patches(Path(root)):
            stack.enter_context(storage_patch)
        case = TrainingTaskApplicationTests()
        state = case.state()
        case.player_target(state, player_id=player_id)
        state._bind_current_save.side_effect = lambda: started.set()

        def read_preview(_rows):
            preview.set()
            if resume is not None and not resume.wait(timeout=15):
                raise RuntimeError("Timed out waiting to resume training")
            return {"training-preview": 10}

        stack.enter_context(patch("fm_odds_web.read_player_training_attributes", side_effect=read_preview))
        stack.enter_context(patch("fm_odds_web.estimate_player_training_ca", return_value={
            "attribute_before": 10, "ca_cost": 1, "ca_before": 100,
            "pa": 130, "model": "test", "verified": True,
        }))
        try:
            response = state.training_run({
                "project_sku": "strength_rack", "player_id": player_id,
                "team_id": 1, "operation": "attribute", "attribute_key": "身体:强壮",
                "duration_mode": "until_increase", "client_submission_id": submission_id,
            })
            results.put(("ok", response["duplicate"]))
        except Exception as error:  # Report child failures to the parent assertions.
            results.put(("error", str(error)))


class TrainingTaskApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.account_path = self.root / "save.fmodd"
        self.storage_patches = _storage_patches(self.root)
        for storage_patch in self.storage_patches:
            storage_patch.start()
        self.set_wallet_balance(2_000_000_000)

    def tearDown(self) -> None:
        for storage_patch in reversed(self.storage_patches):
            storage_patch.stop()
        self.temporary.cleanup()

    def set_wallet_balance(self, minor: int) -> None:
        wallet = load_wallet()
        write_minor(wallet, "balance", int(minor))
        save_wallet(wallet)

    def wallet_minor(self) -> int:
        return read_minor(load_wallet(), "balance")

    def set_bank_balance(self, minor: int) -> None:
        economy = load_economy()
        write_minor(economy, "general_balance", int(minor))
        save_economy(economy)

    def training_fee_count(self) -> int:
        return sum(
            1 for row in load_economy().get("transactions") or []
            if row.get("type") == "training_task_fee"
        )

    def state(
        self, *, team_id: int = 1, team_type: str = "club",
        staff: list[dict] | None = None,
    ) -> LocalOddsState:
        state = LocalOddsState.__new__(LocalOddsState)
        state.lock = threading.RLock()
        state.memory_lock = threading.Lock()
        team = {
            "id": team_id, "name": "测试队", "address": "0xteam",
            "team_type": team_type,
        }
        state.output = {
            "game_date": "2026-01-01", "save_instance_id": "save-a",
            "managed_teams": [dict(team)],
        }
        state.club_context = {"team": dict(team)}
        state.club_contexts = {team_id: {"team": dict(team)}}
        state.club_profile = None
        state.club_profiles = (
            {team_id: {"team": dict(team), "staff": list(staff)}}
            if staff else {}
        )
        state._bind_current_save = MagicMock(return_value="save-a")
        state.attribute_growth_hook = MagicMock()
        state.attribute_growth_hook.sync.return_value = {"installed": False}
        state.attribute_growth_hook.status.return_value = {"installed": False}
        return state

    @staticmethod
    def player_target(
        state: LocalOddsState, *, player_id: int = 10,
        attribute: int = 10, hidden: dict | None = None,
        first_team: bool = True,
    ) -> dict:
        player = {
            "id": player_id, "name": f"球员{player_id}",
            "address": f"0x{player_id:x}",
            "attributes": {"身体": {"强壮": attribute, "速度": attribute}},
            "hidden_attributes": dict(hidden or {"适应性": 15}),
            "position_ratings": {"MC": 10}, "ca": 100, "pa": 130,
        }
        profile = {
            "team": {"id": 1, "name": "测试队", "address": "0xteam",
                     "team_type": "club"},
            "players": [player] if first_team else [],
            "squads": [] if first_team else [{
                "team_id": 2, "label": "U21", "players": [player],
            }],
        }
        state._live_player_effect_target = MagicMock(
            return_value=SimpleNamespace(
                profile=profile, player=player, address=player["address"],
            ),
        )
        return player

    @staticmethod
    def player_targets(state: LocalOddsState, *player_ids: int) -> None:
        players = {
            int(player_id): {
                "id": int(player_id), "name": f"球员{player_id}",
                "address": f"0x{int(player_id):x}",
                "attributes": {"身体": {"强壮": 10, "速度": 10}},
                "hidden_attributes": {"适应性": 15},
                "position_ratings": {"MC": 10}, "ca": 100, "pa": 130,
            }
            for player_id in player_ids
        }
        profile = {
            "team": {"id": 1, "name": "测试队", "address": "0xteam",
                     "team_type": "club"},
            "players": list(players.values()),
        }

        def resolve(player_id, _team_id, **_kwargs):
            player = players[int(player_id)]
            return SimpleNamespace(
                profile=profile, player=player, address=player["address"],
            )

        state._live_player_effect_target = MagicMock(side_effect=resolve)

    def run_attribute(
        self, state: LocalOddsState, *, submission_id: str = "task-1",
        player_id: int = 10, attribute: int = 10,
        attribute_key: str = "身体:强壮", duration_mode: str = "until_increase",
        project_sku: str = "strength_rack",
    ) -> dict:
        with (
            patch(
                "fm_odds_web.read_player_training_attributes",
                return_value={"training-preview": attribute},
            ),
            patch(
                "fm_odds_web.estimate_player_training_ca",
                return_value={
                    "attribute_before": attribute, "ca_cost": 1,
                    "ca_before": 100, "pa": 130, "model": "test",
                    "verified": True,
                },
            ),
        ):
            return state.training_run({
                "project_sku": project_sku, "player_id": player_id,
                "team_id": 1, "operation": "attribute",
                "attribute_key": attribute_key,
                "duration_mode": duration_mode,
                "client_submission_id": submission_id,
            })

    def test_paid_attribute_task_charges_server_fee_once(self) -> None:
        state = self.state()
        self.player_target(state)
        wallet_before = self.wallet_minor()
        result = self.run_attribute(state)

        fee = _fee_minor("strength_rack")
        self.assertFalse(result["duplicate"])
        self.assertEqual(to_minor(result["payment"]["total"]), fee)
        self.assertEqual(to_minor(result["focus"]["payment"]["total"]), fee)
        self.assertEqual(result["focus"]["project_sku"], "strength_rack")
        self.assertEqual(result["focus"]["module"], "player_training")
        self.assertEqual(
            result["focus"]["task_rules_version"],
            1,
        )
        self.assertEqual(self.wallet_minor(), wallet_before - fee)
        self.assertEqual(self.training_fee_count(), 1)
        self.assertEqual(result["player"]["required_points"], 14)
        for key in (
            "training_ground", "economy", "focus", "session", "payment",
            "duplicate", "player",
        ):
            self.assertIn(key, result)

    def test_duration_choice_does_not_change_fee(self) -> None:
        state = self.state()
        self.player_targets(state, 10, 11)
        with patch(
            "fm_odds_web.read_player_training_attributes",
            return_value={"training-preview": 10},
        ), patch(
            "fm_odds_web.estimate_player_training_ca",
            return_value={
                "attribute_before": 10, "ca_cost": 1,
                "ca_before": 100, "pa": 130, "model": "test",
                "verified": True,
            },
        ):
            short = state.training_run({
                "project_sku": "strength_rack", "player_id": 10,
                "team_id": 1, "operation": "attribute",
                "attribute_key": "身体:强壮", "duration_mode": "until_increase",
                "client_submission_id": "short-task",
            })
            long = state.training_run({
                "project_sku": "strength_rack", "player_id": 11,
                "team_id": 1, "operation": "attribute",
                "attribute_key": "身体:强壮", "duration_mode": "until_20",
                "client_submission_id": "long-task",
            })
        self.assertEqual(short["payment"]["total"], long["payment"]["total"])
        self.assertLess(
            short["focus"]["target_attribute"],
            long["focus"]["target_attribute"],
        )

    def test_free_project_creates_no_charge(self) -> None:
        state = self.state()
        self.player_target(state)
        wallet_before = self.wallet_minor()
        with patch(
            "fm_odds_web.read_player_training_positions",
            return_value={"position-training-preview": 8},
        ):
            result = state.training_run({
                "project_sku": "position_training_area", "player_id": 10,
                "team_id": 1, "operation": "position",
                "position_key": "AMC", "duration_mode": "until_14",
            })
        self.assertEqual(result["payment"]["total"], 0.0)
        self.assertEqual(result["focus"]["payment"]["total"], 0.0)
        self.assertEqual(self.wallet_minor(), wallet_before)
        self.assertEqual(self.training_fee_count(), 0)
        self.assertFalse(result["duplicate"])

    def test_coaching_license_uses_paid_admission(self) -> None:
        state = self.state(staff=[{
            "id": 88, "name": "测试教练", "role": "教练", "job_type": 2,
            "address": "0xstaff", "coaching_license": {
                "code": 2, "name": "洲际 A 级", "next_code": 1,
                "next_name": "洲际职业级", "maximum": False,
            },
        }])
        wallet_before = self.wallet_minor()
        result = state.training_run({
            "project_sku": "coaching_desk", "staff_id": 88, "player_id": 88,
            "team_id": 1, "operation": "coaching_license",
            "target_license_code": 1, "client_submission_id": "coach-a",
        })
        fee = _fee_minor("coaching_desk")
        self.assertEqual(to_minor(result["payment"]["total"]), fee)
        self.assertEqual(result["staff"]["target_license_code"], 1)
        self.assertEqual(result["focus"]["focus_type"], "coaching_license")
        self.assertEqual(result["focus"]["due_on"], "2026-06-30")
        self.assertEqual(self.wallet_minor(), wallet_before - fee)
        with self.assertRaisesRegex(ValueError, "证书已发生变化"):
            state.training_run({
                "project_sku": "coaching_desk", "staff_id": 88,
                "player_id": 88, "team_id": 1,
                "operation": "coaching_license", "target_license_code": 2,
                "client_submission_id": "coach-b",
            })

    def test_player_manager_coaching_uses_paid_admission(self) -> None:
        state = self.state(staff=[])
        state.output.update({
            "selected_manager_id": 77,
            "manager": {
                "id": 77, "name": "玩家经理",
                "manager_address": "0xmanager",
                "coaching_license": {
                    "code": 3, "name": "洲际 B 级", "next_code": 2,
                    "next_name": "洲际 A 级", "maximum": False,
                },
            },
        })
        result = state.training_run({
            "project_sku": "coaching_desk", "staff_id": 77, "player_id": 77,
            "team_id": 1, "operation": "coaching_license",
            "subject_type": "player_manager", "target_license_code": 2,
            "client_submission_id": "manager-a",
        })
        self.assertEqual(
            to_minor(result["payment"]["total"]), _fee_minor("coaching_desk"),
        )
        self.assertEqual(result["focus"]["subject_type"], "player_manager")
        self.assertEqual(result["focus"]["staff_role"], "玩家经理")

    def test_duplicate_submission_returns_original_payment(self) -> None:
        state = self.state()
        self.player_target(state)
        first = self.run_attribute(state)
        wallet_after_first = self.wallet_minor()
        second = self.run_attribute(state)
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["payment"], first["payment"])
        self.assertEqual(second["focus"]["id"], first["focus"]["id"])
        self.assertEqual(self.wallet_minor(), wallet_after_first)
        self.assertEqual(self.training_fee_count(), 1)

    def test_duplicate_submission_with_other_intent_is_rejected(self) -> None:
        state = self.state()
        self.player_target(state)
        self.run_attribute(state)
        wallet_before = self.wallet_minor()
        with self.assertRaisesRegex(ValueError, "编号已用于其他安排"):
            self.run_attribute(state, attribute_key="身体:速度")
        self.assertEqual(self.wallet_minor(), wallet_before)

    def test_second_request_for_same_player_is_rejected(self) -> None:
        state = self.state()
        self.player_target(state)
        self.run_attribute(state, submission_id="task-a")
        wallet_before = self.wallet_minor()
        with self.assertRaisesRegex(ValueError, "已有进行中的专项训练"):
            self.run_attribute(state, submission_id="task-b")
        self.assertEqual(self.wallet_minor(), wallet_before)
        self.assertEqual(self.training_fee_count(), 1)

    def test_two_concurrent_requests_for_one_player_allow_one_task(self) -> None:
        state = self.state()
        state.memory_lock = threading.RLock()
        self.player_target(state)
        fee = _fee_minor("strength_rack")
        wallet_before = self.wallet_minor()
        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def submit(submission_id: str) -> None:
            try:
                barrier.wait(timeout=5)
                state.training_run({
                    "project_sku": "strength_rack", "player_id": 10,
                    "team_id": 1, "operation": "attribute",
                    "attribute_key": "身体:强壮",
                    "duration_mode": "until_increase",
                    "client_submission_id": submission_id,
                })
            except Exception as error:  # noqa: BLE001 - reported via assertion
                errors.append(error)

        with (
            patch(
                "fm_odds_web.read_player_training_attributes",
                return_value={"training-preview": 10},
            ),
            patch(
                "fm_odds_web.estimate_player_training_ca",
                return_value={
                    "attribute_before": 10, "ca_cost": 1,
                    "ca_before": 100, "pa": 130, "model": "test",
                    "verified": True,
                },
            ),
        ):
            threads = [
                threading.Thread(target=submit, args=(submission_id,))
                for submission_id in ("concurrent-a", "concurrent-b")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
        self.assertEqual(len(errors), 1, ascii([str(error) for error in errors]))
        self.assertIn(
            "已有进行中的专项训练", str(errors[0]), ascii(str(errors[0])),
        )
        active = active_training_focuses("2026-01-01")
        self.assertEqual(len(active), 1)
        self.assertEqual(self.wallet_minor(), wallet_before - fee)
        self.assertEqual(self.training_fee_count(), 1)

    def test_cross_process_training_serializes_reads_checks_and_payment(self) -> None:
        for scenario in ("different_players_wallet", "different_players_bank", "same_player", "retry"):
            with self.subTest(scenario=scenario):
                save_training_ground(training_ground_module._new_state())
                fee = _fee_minor("strength_rack")
                wallet_before = 2_000_000_000
                self.set_wallet_balance(wallet_before)
                economy = load_economy()
                economy["transactions"] = []
                bank_before = fee * 3 if scenario.endswith("bank") else 0
                write_minor(economy, "general_balance", bank_before)
                save_economy(economy)
                ctx = multiprocessing.get_context("spawn")
                first_started, first_preview, resume = ctx.Event(), ctx.Event(), ctx.Event()
                second_started, second_preview = ctx.Event(), ctx.Event()
                results = ctx.Queue()
                second_player = 11 if scenario.startswith("different_players") else 10
                second_id = "process-a" if scenario == "retry" else "process-b"
                processes = [
                    ctx.Process(target=_submit_training_process, args=(
                        str(self.root), 10, "process-a", first_started, first_preview, resume, results,
                    )),
                    ctx.Process(target=_submit_training_process, args=(
                        str(self.root), second_player, second_id, second_started, second_preview, None, results,
                    )),
                ]
                try:
                    processes[0].start()
                    self.assertTrue(first_preview.wait(timeout=15), "first process never reached preview")
                    processes[1].start()
                    self.assertTrue(second_started.wait(timeout=15), "second process never attempted submission")
                    # Before the fix both processes reach preview with stale task snapshots.
                    # With the account transaction the second must wait until the first commits.
                    second_preview.wait(timeout=0.5)
                    resume.set()
                    for process in processes:
                        process.join(timeout=20)
                        self.assertEqual(process.exitcode, 0)
                    outcomes = [results.get(timeout=5) for _ in processes]
                finally:
                    resume.set()
                    for process in processes:
                        if process.is_alive():
                            process.terminate()
                        if process.pid is not None:
                            process.join(timeout=5)
                    results.close()
                    results.join_thread()
                expected_tasks = 2 if scenario.startswith("different_players") else 1
                self.assertEqual(len(active_training_focuses("2026-01-01")), expected_tasks, outcomes)
                self.assertEqual(self.training_fee_count(), expected_tasks, outcomes)
                self.assertEqual(self.wallet_minor(), wallet_before - (0 if bank_before else expected_tasks * fee))
                self.assertEqual(read_minor(load_economy(), "general_balance"), bank_before - (expected_tasks * fee if bank_before else 0))
                if scenario == "same_player":
                    self.assertEqual(sum(row[0] == "error" for row in outcomes), 1, outcomes)
                    self.assertTrue(any("已有进行中的专项训练" in str(row[1]) for row in outcomes), outcomes)
                elif scenario == "retry":
                    self.assertCountEqual(outcomes, [("ok", False), ("ok", True)])
                else:
                    self.assertEqual(outcomes, [("ok", False), ("ok", False)])

    def test_two_players_can_use_one_project(self) -> None:
        state = self.state()
        self.player_targets(state, 10, 11)
        fee = _fee_minor("strength_rack")
        wallet_before = self.wallet_minor()
        self.run_attribute(state, submission_id="p10", player_id=10)
        self.run_attribute(state, submission_id="p11", player_id=11)
        active = active_training_focuses("2026-01-01")
        self.assertEqual(
            sorted(int(row["player_id"]) for row in active), [10, 11],
        )
        self.assertEqual(self.wallet_minor(), wallet_before - fee * 2)

    def test_insufficient_funds_leaves_no_task_or_charge(self) -> None:
        state = self.state()
        self.player_target(state)
        self.set_wallet_balance(to_minor(100))
        with self.assertRaisesRegex(ValueError, "余额合计不足"):
            self.run_attribute(state)
        self.assertEqual(load_training_ground()["focuses"], [])
        self.assertEqual(self.wallet_minor(), to_minor(100))

    def test_commit_failure_leaves_no_task_or_charge(self) -> None:
        state = self.state()
        self.player_target(state)
        wallet_before = self.wallet_minor()
        with patch(
            "fm_odds_web.commit_documents_with_wallet_adjustments",
            side_effect=RuntimeError("save failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.run_attribute(state)
        self.assertEqual(load_training_ground()["focuses"], [])
        self.assertEqual(self.wallet_minor(), wallet_before)
        self.assertEqual(self.training_fee_count(), 0)

    def test_hidden_and_reverse_attribute_is_charged(self) -> None:
        state = self.state()
        player = self.player_target(state, hidden={"适应性": 15})
        player["attributes"] = {"身体": {"强壮": 10}}
        with patch(
            "fm_odds_web.read_player_training_attributes",
            return_value={"training-preview": 15},
        ):
            result = state.training_run({
                "project_sku": "adaptation_pod", "player_id": 10,
                "team_id": 1, "operation": "attribute",
                "attribute_key": "隐藏:适应性", "duration_mode": "until_10",
                "direction": -1, "client_submission_id": "hidden-a",
            })
        self.assertEqual(
            to_minor(result["payment"]["total"]), _fee_minor("adaptation_pod"),
        )
        self.assertEqual(result["focus"]["attribute_kind"], "hidden")
        self.assertEqual(result["focus"]["direction"], -1)

    def test_habit_task_charges_fixed_course(self) -> None:
        state = self.state()
        self.player_target(state)
        with (
            patch(
                "fm_odds_web.preferred_move_catalog_for_current_game",
                return_value=[{"bit": 13, "name": "喜欢反越位"}],
            ),
            patch(
                "fm_odds_web.read_player_preferred_moves",
                return_value={"moves": []},
            ),
        ):
            result = state.training_run({
                "project_sku": "habit_lab", "player_id": 10, "team_id": 1,
                "operation": "learn", "preferred_move_bit": 13,
                "client_submission_id": "habit-a",
            })
        self.assertEqual(
            to_minor(result["payment"]["total"]), _fee_minor("habit_lab"),
        )
        self.assertEqual(result["focus"]["duration_days"], 7)
        self.assertEqual(result["focus"]["expires_on"], "2026-01-08")

    def test_requested_team_must_be_current_club(self) -> None:
        state = self.state()
        self.player_target(state)
        wallet_before = self.wallet_minor()
        with self.assertRaisesRegex(ValueError, "只能为当前执教球队"):
            state.training_run({
                "project_sku": "strength_rack", "player_id": 10,
                "team_id": 999, "operation": "attribute",
                "attribute_key": "身体:强壮",
                "duration_mode": "until_increase",
                "client_submission_id": "forged-team",
            })
        self.assertEqual(self.wallet_minor(), wallet_before)
        self.assertEqual(load_training_ground()["focuses"], [])

    def test_non_first_team_player_is_rejected(self) -> None:
        state = self.state()
        self.player_target(state, first_team=False)
        with self.assertRaisesRegex(ValueError, "只能为当前一线队球员"):
            self.run_attribute(state)
        self.assertEqual(load_training_ground()["focuses"], [])

    def test_staff_from_other_team_is_rejected(self) -> None:
        state = self.state()
        state.club_profiles = {
            2: {
                "team": {"id": 2, "name": "其他队", "address": "0xother",
                         "team_type": "club"},
                "staff": [{
                    "id": 88, "name": "他队教练", "role": "教练",
                    "job_type": 2, "address": "0xstaff",
                    "coaching_license": {
                        "code": 2, "next_code": 1, "maximum": False,
                    },
                }],
            },
        }
        with self.assertRaisesRegex(ValueError, "不属于当前执教俱乐部"):
            state.training_run({
                "project_sku": "coaching_desk", "staff_id": 88,
                "player_id": 88, "team_id": 1,
                "operation": "coaching_license", "target_license_code": 1,
                "client_submission_id": "foreign-coach",
            })

    def test_legacy_paid_facility_request_requires_submission_id(self) -> None:
        state = self.state()
        self.player_target(state)
        facility = purchase_facility("treadmill")
        place_facility(facility["id"], "indoor", 40, 50)
        wallet_before = self.wallet_minor()
        with (
            patch(
                "fm_odds_web.read_player_training_attributes",
                return_value={"training-preview": 10},
            ),
            patch(
                "fm_odds_web.estimate_player_training_ca",
                return_value={
                    "attribute_before": 10, "ca_cost": 1,
                    "ca_before": 100, "pa": 130, "model": "test",
                    "verified": True,
                },
            ),
        ):
            with self.assertRaisesRegex(ValueError, "重新提交"):
                state.training_run({
                    "facility_id": facility["id"], "player_id": 10,
                    "team_id": 1, "operation": "attribute",
                    "attribute_key": "身体:速度",
                    "duration_mode": "until_increase",
                })
            self.assertEqual(self.wallet_minor(), wallet_before)
            self.assertEqual(load_training_ground()["focuses"], [])
            with self.assertRaisesRegex(ValueError, "训练项目不匹配"):
                state.training_run({
                    "project_sku": "strength_rack",
                    "facility_id": facility["id"], "player_id": 10,
                    "team_id": 1, "operation": "attribute",
                    "attribute_key": "身体:速度",
                    "duration_mode": "until_increase",
                    "client_submission_id": "mismatched-project",
                })
            compatible = state.training_run({
                "facility_id": facility["id"], "player_id": 10,
                "team_id": 1, "operation": "attribute",
                "attribute_key": "身体:速度",
                "duration_mode": "until_increase",
                "client_submission_id": "legacy-paid",
            })
        self.assertEqual(
            to_minor(compatible["payment"]["total"]),
            _fee_minor("treadmill"),
        )
        self.assertEqual(
            compatible["focus"]["project_sku"], "treadmill",
        )
        self.assertEqual(self.wallet_minor(), wallet_before - _fee_minor("treadmill"))

    def test_legacy_active_task_is_migrated_before_new_task(self) -> None:
        legacy = {
            "id": "legacy-focus", "at": "2025-01-01T00:00:00",
            "status": "active", "focus_type": "attribute",
            "facility_id": "legacy-facility", "player_id": 10,
            "player_name": "A", "attribute_key": "身体:速度",
            "initial_attribute": 10, "started_on": "2025-01-01",
            "duration_mode": "until_increase", "direction": 1,
        }
        payload = load_training_ground()
        payload["task_rules_version"] = 0
        payload["focuses"].append(legacy)
        save_training_ground(payload)

        state = self.state()
        self.player_target(state)
        result = self.run_attribute(state, submission_id="after-migration")

        payload = load_training_ground()
        self.assertEqual(payload["task_rules_version"], 1)
        old = next(
            row for row in payload["focuses"]
            if row.get("id") == "legacy-focus"
        )
        self.assertEqual(old["status"], "cancelled")
        self.assertEqual(
            old["cancel_reason"], "training_task_model_migration",
        )
        active = active_training_focuses("2026-01-01")
        self.assertEqual([row["id"] for row in active], [result["focus"]["id"]])
        self.assertEqual(self.training_fee_count(), 1)

        # One-time marker: a new task is never cancelled by a later migration.
        state._ensure_training_task_migration("2026-01-02")
        active = active_training_focuses("2026-01-01")
        self.assertEqual([row["id"] for row in active], [result["focus"]["id"]])

    def test_legacy_rooms_migrate_independently_of_training_document(self) -> None:
        for entry in ("refresh_without_training", "refresh_with_new_training", "submit"):
            with self.subTest(entry=entry):
                if entry == "refresh_without_training":
                    self.assertIsNone(account_store.load_document("training_ground", None))
                else:
                    save_training_ground(training_ground_module._new_state())
                account_store.save_document("relationship_training_rooms", {
                    "schema_version": 2,
                    "rooms": [{"id": "old-room", "sku": "tactical_room",
                               "status": "occupied", "participants": [{"id": 10}],
                               "attributes": ["技术:传球"], "started_on": "2025-01-01"}],
                })
                state = self.state()
                self.player_target(state)
                wallet_before = self.wallet_minor()
                if entry == "submit":
                    self.run_attribute(state, submission_id="rooms-migration")
                else:
                    self.assertTrue(state._ensure_training_task_migration("2026-01-01"))
                    self.assertEqual(self.wallet_minor(), wallet_before)
                rooms = account_store.load_document("relationship_training_rooms", {})
                room = rooms["rooms"][0]
                self.assertEqual(room["status"], "idle")
                self.assertEqual(room["participants"], [])
                self.assertEqual(room["cancelled_session"]["cancel_reason"], "training_task_model_migration")
                self.assertNotIn("effects", room["cancelled_session"])
                self.assertFalse(state._ensure_training_task_migration("2026-01-02"))
                if entry == "submit":
                    self.assertEqual(len(active_training_focuses("2026-01-01")), 1)

    def test_room_migration_failed_commit_can_retry_without_partial_marker(self) -> None:
        account_store.save_document("relationship_training_rooms", {
            "rooms": [{"id": "old-room", "sku": "tactical_room",
                       "status": "occupied", "participants": [{"id": 10}]}],
        })
        state = self.state()
        wallet_before = self.wallet_minor()
        with patch("fm_odds_web.save_documents", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                state._ensure_training_task_migration("2026-01-01")
        stored = account_store.load_document("relationship_training_rooms", {})
        self.assertNotIn("task_rules_version", stored)
        self.assertEqual(stored["rooms"][0]["status"], "occupied")
        self.assertTrue(state._ensure_training_task_migration("2026-01-01"))
        self.assertFalse(state._ensure_training_task_migration("2026-01-02"))
        self.assertEqual(self.wallet_minor(), wallet_before)

    def test_duplicate_submission_persists_independent_room_migration(self) -> None:
        state = self.state()
        self.player_target(state)
        self.run_attribute(state, submission_id="existing-task")
        account_store.save_document("relationship_training_rooms", {
            "rooms": [{"id": "old-room", "sku": "tactical_room",
                       "status": "occupied", "participants": [{"id": 10}]}],
        })
        wallet_before = self.wallet_minor()
        self.assertTrue(self.run_attribute(state, submission_id="existing-task")["duplicate"])
        room = account_store.load_document("relationship_training_rooms", {})["rooms"][0]
        self.assertEqual(room["status"], "idle")
        self.assertFalse(state._ensure_training_task_migration("2026-01-02"))
        self.assertEqual(self.wallet_minor(), wallet_before)

    def test_duplicate_response_releases_account_lock_before_public_readers(self) -> None:
        state = self.state()
        self.player_target(state)
        self.run_attribute(state)
        completed = threading.Event()
        threads = []

        def response_hook(_rows):
            def read():
                active_training_focuses("2026-01-01")
                completed.set()
            thread = threading.Thread(target=read, daemon=True)
            threads.append(thread)
            thread.start()
            self.assertTrue(completed.wait(timeout=2), "public reader blocked by replay account lock")
            return {"installed": False}

        state.attribute_growth_hook.sync.side_effect = response_hook
        try:
            self.assertTrue(self.run_attribute(state)["duplicate"])
        finally:
            for thread in threads:
                thread.join(timeout=5)
        self.assertTrue(all(not thread.is_alive() for thread in threads))

    def test_direct_legacy_room_settlement_migrates_before_effects(self) -> None:
        account_store.save_document("relationship_training_rooms", {
            "rooms": [{"id": "old-room", "sku": "tactical_room",
                       "status": "occupied", "participants": [{"id": 10}]}],
        })
        state = self.state()
        state._data_scope_id = MagicMock(return_value="test-account")
        wallet_before = self.wallet_minor()
        with (
            patch("fm_odds_web.FROZEN", False),
            patch("fm_odds_web.assert_training_floor_unlocked"),
            patch("fm_odds_web.borrow_game_operation", side_effect=AssertionError("old effects")) as native,
        ):
            with self.assertRaisesRegex(ValueError, "当前未被占用"):
                state.relationship_training_room_settle({"room_id": "old-room"})
            native.assert_not_called()
        room = account_store.load_document("relationship_training_rooms", {})["rooms"][0]
        self.assertEqual(room["status"], "idle")
        self.assertEqual(room["cancelled_session"]["status"], "cancelled")
        self.assertEqual(self.wallet_minor(), wallet_before)

    def test_room_read_and_entry_migrate_before_new_occupancy(self) -> None:
        from tools.relationship_training import enter_relationship_training_room

        for entry in ("read", "enter"):
            with self.subTest(entry=entry):
                account_store.save_document("relationship_training_rooms", {
                    "rooms": [{"id": "old-room", "sku": "mentoring_room",
                               "status": "occupied", "participants": [{"id": 10}]}],
                })
                state = self.state()
                state._bind_request_scope = MagicMock(return_value="test-account")
                if entry == "read":
                    state.relationship_training_rooms_state()
                else:
                    with patch("fm_odds_web.assert_training_floor_unlocked"):
                        with self.assertRaisesRegex(ValueError, "参与者已不属于当前执教球队"):
                            state.relationship_training_room_enter({
                                "room_id": "old-room", "attributes": ["精神:领导力"],
                                "participants": [{"id": 10, "team_id": 1, "kind": "player"}],
                            })
                room = account_store.load_document("relationship_training_rooms", {})["rooms"][0]
                self.assertEqual(room["status"], "idle")
                # The same room can now take a new task; later migration must preserve it.
                enter_relationship_training_room("old-room", [
                    {"id": 10, "kind": "player", "name": "A", "role": "mentor"},
                    {"id": 11, "kind": "player", "name": "B", "role": "student"},
                ], ["精神:领导力"], "2026-01-01", client_submission_id=f"new-{entry}")
                self.assertFalse(state._ensure_training_task_migration("2026-01-02"))
                room = account_store.load_document("relationship_training_rooms", {})["rooms"][0]
                self.assertEqual(room["status"], "occupied")
                self.assertEqual(room["client_submission_id"], f"new-{entry}")

    def test_retry_after_history_retention_returns_receipt_without_charge(self) -> None:
        state = self.state()
        self.player_target(state)
        original = self.run_attribute(state, submission_id="old-paid-task")
        training_ground_module.cancel_training_focus(original["focus"]["id"], "2026-01-01")
        payload = load_training_ground()
        for index in range(501):
            focus_id = f"later-{index}"
            training_ground_module.append_training_task(
                payload,
                dict(original["focus"], id=focus_id, status="completed"),
                dict(original["session"], id=f"session-{index}", focus_id=focus_id),
                f"submission-{index}",
            )
        self.assertNotIn(original["focus"]["id"], [row["id"] for row in payload["focuses"]])
        save_training_ground(payload)
        account_store._CONTAINER_CACHE.clear()  # Verify persisted receipts, not an in-memory index.
        wallet_before = self.wallet_minor()
        fee_count = self.training_fee_count()
        replay = self.run_attribute(state, submission_id="old-paid-task")
        self.assertTrue(replay["duplicate"])
        self.assertEqual(replay["focus"]["id"], original["focus"]["id"])
        self.assertEqual(replay["focus"]["status"], "cancelled")
        self.assertEqual(replay["session"]["id"], original["session"]["id"])
        self.assertEqual(replay["payment"], original["payment"])
        self.assertEqual(self.wallet_minor(), wallet_before)
        self.assertEqual(self.training_fee_count(), fee_count)
        with self.assertRaisesRegex(ValueError, "编号已用于其他安排"):
            self.run_attribute(state, submission_id="old-paid-task", attribute_key="身体:速度")
        self.assertEqual(self.wallet_minor(), wallet_before)

    def test_task_completes_at_target_without_renewal(self) -> None:
        state = self.state()
        player = self.player_target(state)
        state.club_profiles = {1: {
            "team": {"id": 1, "name": "测试队", "address": "0xteam",
                     "team_type": "club"},
            "players": [player],
        }}
        result = self.run_attribute(state, submission_id="complete-a")
        focus_id = result["focus"]["id"]
        fee_count = self.training_fee_count()
        wallet_after = self.wallet_minor()
        develop_result = {
            "attributes": {"身体": {"强壮": 11, "速度": 10}},
            "ca": 100, "pa": 130, "attribute_after": 11,
            "_original_raw": b"raw", "_original_ca": 100, "_original_pa": 130,
        }
        with (
            patch(
                "fm_odds_web.read_player_training_attributes",
                return_value={focus_id: 10},
            ),
            patch(
                "fm_odds_web.develop_player",
                return_value=develop_result,
            ) as develop,
        ):
            status = state._sync_training_focuses("2026-01-10")

        develop.assert_called_once_with(
            10, "0xa", "身体:强壮", 10, "training", 1,
            allow_ca_over_pa=False,
        )
        self.assertEqual(status["completed_attribute_focus_ids"], [focus_id])
        self.assertEqual(active_training_focuses("2026-01-10"), [])
        payload = load_training_ground()
        completed = next(
            row for row in payload["focuses"] if row["id"] == focus_id
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(payload["facilities"], [])
        archived = account_store.load_document("training_archive", {})
        event = archived["events"][-1]
        self.assertEqual(event["details"]["facility_sku"], "strength_rack")
        self.assertEqual(event["details"]["floor"], "1F")
        self.assertEqual(event["details"]["training_content"], "身体:强壮")
        self.assertEqual(
            len([
                row for row in payload["focuses"]
                if int(row.get("player_id") or 0) == 10
            ]), 1,
        )
        self.assertEqual(self.training_fee_count(), fee_count)
        self.assertEqual(self.wallet_minor(), wallet_after)

    def test_target_progress_and_native_guards_are_unchanged(self) -> None:
        attribute = {
            "id": "attribute-stage", "status": "active",
            "focus_type": "attribute", "initial_attribute": 10,
            "target_attribute": 14, "duration_mode": "until_14",
            "direction": 1, "required_points": 14, "progress_points": 0,
        }
        settled = training_ground_module._settle_attribute_focus(
            attribute, "2026-01-01", {"attribute_after": 11},
        )
        self.assertEqual(settled["status"], "active")
        self.assertEqual(settled["initial_attribute"], 11)
        self.assertEqual(settled["progress_points"], 0)

        position = {
            "id": "position-stage", "status": "active",
            "focus_type": "position", "initial_position": 10,
            "target_position": 14, "duration_mode": "until_14",
            "required_points": 14, "progress_points": 0,
        }
        with self.assertRaisesRegex(ValueError, "每次只能提升1点"):
            training_ground_module._settle_position_focus(
                position, "2026-01-01",
                {"position_before": 10, "position_after": 12},
            )

    def test_maxed_position_focus_completes_without_native_write(self) -> None:
        state = self.state()
        player = self.player_target(state)
        state.club_profiles = {1: {
            "team": {"id": 1, "name": "测试队", "address": "0xteam",
                     "team_type": "club"},
            "players": [player],
        }}
        focus, _session = record_position_training_focus(
            POSITION_TRAINING_AREA_ID, 10, "球员10", "2026-01-01",
            "ST", "until_20", 20,
        )
        with (
            patch(
                "fm_odds_web.read_player_training_positions",
                return_value={focus["id"]: 20},
            ),
            patch("fm_odds_web.develop_player_position") as develop,
        ):
            status = state._sync_training_focuses("2026-01-02")

        develop.assert_not_called()
        self.assertEqual(
            status["completed_position_focus_ids"], [focus["id"]],
        )
        self.assertEqual(active_training_focuses("2026-01-02"), [])
        completed = next(
            row for row in load_training_ground()["focuses"]
            if row["id"] == focus["id"]
        )
        self.assertEqual(completed["status"], "completed")

    def test_cancel_releases_person_without_refund(self) -> None:
        state = self.state(staff=[{
            "id": 88, "name": "测试教练", "role": "教练", "job_type": 2,
            "address": "0xstaff", "coaching_license": {
                "code": 2, "next_code": 1, "maximum": False,
            },
        }])
        self.player_targets(state, 10, 11)
        with (
            patch(
                "fm_odds_web.read_player_training_attributes",
                return_value={"training-preview": 10},
            ),
            patch(
                "fm_odds_web.estimate_player_training_ca",
                return_value={
                    "attribute_before": 10, "ca_cost": 1,
                    "ca_before": 100, "pa": 130, "model": "test",
                    "verified": True,
                },
            ),
            patch(
                "fm_odds_web.read_player_training_positions",
                return_value={"position-training-preview": 8},
            ),
        ):
            attribute = state.training_run({
                "project_sku": "strength_rack", "player_id": 10,
                "team_id": 1, "operation": "attribute",
                "attribute_key": "身体:强壮",
                "duration_mode": "until_increase",
                "client_submission_id": "cancel-attr",
            })
            position = state.training_run({
                "project_sku": "position_training_area", "player_id": 11,
                "team_id": 1, "operation": "position",
                "position_key": "AMC", "duration_mode": "until_14",
                "client_submission_id": "cancel-position",
            })
            coaching = state.training_run({
                "project_sku": "coaching_desk", "staff_id": 88,
                "player_id": 88, "team_id": 1,
                "operation": "coaching_license", "target_license_code": 1,
                "client_submission_id": "cancel-coach",
            })
        wallet_after = self.wallet_minor()
        fee_count = self.training_fee_count()
        ids = [
            attribute["focus"]["id"],
            position["focus"]["id"],
            coaching["focus"]["id"],
        ]
        for focus_id in ids:
            response = state.training_cancel({"focus_id": focus_id})
            self.assertEqual(response["focus"]["status"], "cancelled")
            self.assertIn("economy", response)
        self.assertEqual(active_training_focuses("2026-01-01"), [])
        self.assertEqual(self.wallet_minor(), wallet_after)
        self.assertEqual(self.training_fee_count(), fee_count)
        self.assertEqual(self.training_fee_count(), 2)
        with self.assertRaisesRegex(ValueError, "已不在使用"):
            state.training_cancel({"focus_id": ids[0]})

    def test_cancelled_task_cannot_be_settled_from_stale_snapshot(self) -> None:
        state = self.state()
        player = self.player_target(state)
        state.club_profiles = {1: {
            "team": {"id": 1, "name": "测试队", "address": "0xteam",
                     "team_type": "club"},
            "players": [player],
        }}
        result = self.run_attribute(state, submission_id="stale-a")
        state.training_cancel({"focus_id": result["focus"]["id"]})
        stale_focus = dict(result["focus"])
        stale_focus["status"] = "active"
        settle_result = {
            "attributes": {"身体": {"强壮": 11}},
            "ca": 100, "pa": 130, "attribute_after": 11,
            "_original_raw": b"raw", "_original_ca": 100, "_original_pa": 130,
        }
        with (
            patch(
                "fm_odds_web.active_training_focuses",
                return_value=[stale_focus],
            ),
            patch(
                "fm_odds_web.advance_training_focuses",
                return_value=[stale_focus],
            ),
            patch("fm_odds_web.due_coaching_license_focuses", return_value=[]),
            patch(
                "fm_odds_web.read_player_training_attributes",
                return_value={stale_focus["id"]: 10},
            ),
            patch(
                "fm_odds_web.develop_player",
                return_value=settle_result,
            ) as develop,
            patch("fm_odds_web.restore_player_development") as restore,
        ):
            status = state._sync_training_focuses("2026-01-02")

        self.assertEqual(status["completed_attribute_focus_ids"], [])
        self.assertIn("已失效", str(status.get("progress_error") or ""))
        develop.assert_called_once()
        restore.assert_called_once()
        persisted = next(
            row for row in load_training_ground()["focuses"]
            if row["id"] == stale_focus["id"]
        )
        self.assertEqual(persisted["status"], "cancelled")

    def test_legacy_purchase_and_sale_routes_have_no_financial_effect(self) -> None:
        state = self.state()
        self.set_bank_balance(to_minor(1_000_000))
        wallet_before = self.wallet_minor()
        bank_before = read_minor(load_economy(), "general_balance")
        training_before = load_training_ground()
        for handler, payload in (
            (state.training_purchase, {"sku": "treadmill"}),
            (state.training_floor_purchase, {"scene": "indoor_3f"}),
            (state.training_place, {"facility_id": "facility-1"}),
            (state.training_store, {"facility_id": "facility-1"}),
            (state.training_sell, {"facility_id": "facility-1"}),
        ):
            with self.assertRaisesRegex(ValueError, "不再支持"):
                handler(payload)
        self.assertEqual(self.wallet_minor(), wallet_before)
        self.assertEqual(
            read_minor(load_economy(), "general_balance"), bank_before,
        )
        self.assertEqual(load_training_ground(), training_before)
        self.assertEqual(self.training_fee_count(), 0)

    @staticmethod
    def _error_payload(error: Exception, locale: str) -> dict:
        handler = Handler.__new__(Handler)
        handler.headers = {"X-FMODD-Locale": locale}
        return Handler._localized_error_payload(
            handler, error, operation="/api/training/run",
        )

    def test_training_errors_render_localized_messages(self) -> None:
        error = _training_error(
            "training.error.current_team_only",
            "只能为当前执教的俱乐部球队安排训练",
        )
        self.assertIn("只能为当前执教的俱乐部球队安排训练", str(error))
        english = self._error_payload(error, "en-GB")
        chinese = self._error_payload(error, "zh-CN")
        self.assertEqual(
            english["message_key"], "training.error.current_team_only",
        )
        self.assertEqual(
            english["message"],
            MESSAGE_CATALOGS["en-GB"]["training.error.current_team_only"],
        )
        self.assertEqual(
            chinese["message"],
            MESSAGE_CATALOGS["zh-CN"]["training.error.current_team_only"],
        )
        self.assertEqual(
            english["error"], "只能为当前执教的俱乐部球队安排训练",
        )
        self.assertNotIn("error_detail_safe", english)
        self.assertNotIn("error_detail_safe", chinese)

    def test_training_validation_errors_carry_message_keys(self) -> None:
        state = self.state()
        self.player_target(state)
        with self.assertRaises(ValueError) as captured:
            state.training_run({
                "project_sku": "strength_rack", "player_id": 10,
                "team_id": 999, "operation": "attribute",
                "attribute_key": "身体:强壮",
                "duration_mode": "until_increase",
                "client_submission_id": "localized-team",
            })
        self.assertEqual(
            captured.exception.message_key,
            "training.error.current_team_mismatch",
        )
        payload = self._error_payload(captured.exception, "en-GB")
        self.assertEqual(
            payload["message"],
            MESSAGE_CATALOGS["en-GB"]["training.error.current_team_mismatch"],
        )

        state = self.state()
        self.player_target(state)
        self.set_wallet_balance(0)
        with self.assertRaisesRegex(ValueError, "余额合计不足") as captured:
            self.run_attribute(state, submission_id="localized-funds")
        self.assertEqual(
            captured.exception.message_key,
            "training.error.insufficient_funds",
        )
        payload = self._error_payload(captured.exception, "en-GB")
        self.assertEqual(
            payload["message_key"], "training.error.insufficient_funds",
        )
        self.assertEqual(
            payload["message"],
            MESSAGE_CATALOGS["en-GB"]["training.error.insufficient_funds"],
        )

        with self.assertRaises(ValueError) as captured:
            state.training_cancel({"focus_id": "missing-task"})
        self.assertEqual(
            captured.exception.message_key, "training.error.task_not_found",
        )

        with self.assertRaises(ValueError) as captured:
            state.training_purchase({})
        self.assertEqual(
            captured.exception.message_key,
            "training.error.equipment_route_retired",
        )

    def test_training_error_catalog_covers_both_locales(self) -> None:
        import re

        english = MESSAGE_CATALOGS["en-GB"]
        chinese = MESSAGE_CATALOGS["zh-CN"]
        keys = sorted(
            key for key in english if key.startswith("training.error.")
        )
        self.assertGreaterEqual(len(keys), 30)
        placeholder = re.compile(r"\{(\w+)\}")
        for key in keys:
            self.assertIn(key, chinese)
            self.assertEqual(
                placeholder.findall(english[key]),
                placeholder.findall(chinese[key]),
                key,
            )

    def test_bank_is_charged_before_wallet(self) -> None:
        state = self.state(staff=[
            {
                "id": 88, "name": "教练甲", "role": "教练", "job_type": 2,
                "address": "0xstaff", "coaching_license": {
                    "code": 2, "next_code": 1, "maximum": False,
                },
            },
            {
                "id": 89, "name": "教练乙", "role": "教练", "job_type": 2,
                "address": "0xstaff2", "coaching_license": {
                    "code": 2, "next_code": 1, "maximum": False,
                },
            },
        ])
        self.set_bank_balance(to_minor(60_000))
        wallet_before = self.wallet_minor()
        first = state.training_run({
            "project_sku": "coaching_desk", "staff_id": 88, "player_id": 88,
            "team_id": 1, "operation": "coaching_license",
            "target_license_code": 1, "client_submission_id": "bank-first-a",
        })
        self.assertEqual(to_minor(first["payment"]["bank"]), _fee_minor("coaching_desk"))
        self.assertEqual(to_minor(first["payment"]["wallet"]), 0)
        self.assertEqual(
            read_minor(load_economy(), "general_balance"),
            to_minor(10_000),
        )
        second = state.training_run({
            "project_sku": "coaching_desk", "staff_id": 89, "player_id": 89,
            "team_id": 1, "operation": "coaching_license",
            "target_license_code": 1, "client_submission_id": "bank-first-b",
        })
        self.assertEqual(to_minor(second["payment"]["bank"]), to_minor(10_000))
        self.assertEqual(
            to_minor(second["payment"]["wallet"]),
            _fee_minor("coaching_desk") - to_minor(10_000),
        )
        self.assertEqual(
            self.wallet_minor(),
            wallet_before - (_fee_minor("coaching_desk") - to_minor(10_000)),
        )


if __name__ == "__main__":
    unittest.main()
