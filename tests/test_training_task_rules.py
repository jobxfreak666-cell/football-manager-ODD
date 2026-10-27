from __future__ import annotations

import copy
import unittest
from unittest.mock import MagicMock, patch

from tools import relationship_training as relationship_training_module
from tools import training_ground as training_ground_module
from tools.app_settings import MONEY_CURRENCIES, local_purchase_price
from tools.money import to_minor
from tools.relationship_training import (
    RELATIONSHIP_TRAINING_MIGRATION_REASON,
    ROOMS as RELATIONSHIP_ROOMS,
    migrate_relationship_training_rooms,
)
from tools.training_catalog import (
    TRAINING_GROUND_MODULES,
    TRAINING_MODULES,
    build_training_project_catalog,
    training_module_for_product,
    training_task_fee_minor,
)
from tools.training_ground import (
    FACILITIES,
    POSITION_TRAINING_AREA_ID,
    REMOVED_FACILITY_SKUS,
    TASK_RULES_VERSION,
    TRAINING_TASK_MIGRATION_REASON,
    migrate_training_tasks,
    record_coaching_license_focus,
    record_habit_training_focus,
    record_position_training_focus,
    record_training_focus,
)


GBP_SETTINGS = {
    "money_currency": "GBP",
    "money_rate": MONEY_CURRENCIES["GBP"]["rate"],
    "purchase_money_scale": MONEY_CURRENCIES["GBP"]["display_scale"],
}
CNY_SETTINGS = {
    "money_currency": "CNY",
    "money_rate": MONEY_CURRENCIES["CNY"]["rate"],
    "purchase_money_scale": MONEY_CURRENCIES["CNY"]["display_scale"],
}


def _empty_payload(facilities: list[dict] | None = None) -> dict:
    return {
        "schema_version": 12,
        "facilities": list(facilities or []),
        "sessions": [],
        "focuses": [],
        "history": [],
    }


class TrainingProjectRulesTests(unittest.TestCase):
    def test_projects_have_exactly_three_modules(self) -> None:
        catalog = build_training_project_catalog(FACILITIES, GBP_SETTINGS)
        by_sku = {row["sku"]: row for row in catalog}

        self.assertEqual(
            TRAINING_MODULES,
            ("player_training", "position_training", "staff_training"),
        )
        self.assertEqual({row["module"] for row in catalog}, set(TRAINING_MODULES))
        self.assertEqual(set(by_sku), set(FACILITIES))
        self.assertEqual(len(by_sku), 29)
        self.assertEqual(
            TRAINING_GROUND_MODULES, (*TRAINING_MODULES, "team_training"),
        )
        # Modules come from the project itself; nothing carries a floor/scene.
        for row in catalog:
            self.assertNotIn("scene", row)
            self.assertNotIn("floor", row)
        self.assertEqual(by_sku["position_training_area"]["module"], "position_training")
        for sku in ("adaptation_pod", "career_terminal", "club_culture_screen",
                    "decisive_match_console", "brainwave_chair", "rules_learning_desk",
                    "leadership_desk", "defence_learning_desk"):
            self.assertEqual(by_sku[sku]["module"], "player_training", sku)
        self.assertEqual(by_sku["coaching_desk"]["module"], "staff_training")
        self.assertEqual(
            {row["sku"] for row in catalog if row["module"] == "staff_training"},
            {"coaching_desk"},
        )
        self.assertEqual(
            {row["sku"] for row in catalog if row["module"] == "position_training"},
            {"position_training_area"},
        )
        for sku in ("leadership_desk", "defence_learning_desk", "rules_learning_desk"):
            self.assertEqual(by_sku[sku]["module"], "player_training")
        self.assertEqual(
            training_module_for_product(
                "position_training_area", FACILITIES["position_training_area"],
            ),
            "position_training",
        )

    def test_task_fee_is_half_original_price(self) -> None:
        catalog = {row["sku"]: row for row in build_training_project_catalog(
            FACILITIES, GBP_SETTINGS,
        )}

        self.assertEqual(
            training_task_fee_minor(FACILITIES["strength_rack"], GBP_SETTINGS),
            to_minor(100_000.0),
        )
        self.assertEqual(
            training_task_fee_minor(FACILITIES["coaching_desk"], GBP_SETTINGS),
            to_minor(50_000.0),
        )
        self.assertEqual(catalog["strength_rack"]["task_price_minor"], to_minor(100_000.0))
        self.assertEqual(catalog["coaching_desk"]["task_price_minor"], to_minor(50_000.0))
        for sku in (
            "set_piece_area", "team_training_area", "goalkeeper_training_area",
            "passing_training_area", "position_training_area",
        ):
            self.assertEqual(
                training_task_fee_minor(FACILITIES[sku], GBP_SETTINGS), 0, sku,
            )
            self.assertEqual(catalog[sku]["task_price_minor"], 0, sku)

        # Base prices stay whole so a later projection cannot halve them again.
        self.assertEqual(FACILITIES["strength_rack"]["price"], 200_000.0)
        rebuilt = {row["sku"]: row for row in build_training_project_catalog(
            FACILITIES, GBP_SETTINGS,
        )}
        self.assertEqual(
            rebuilt["strength_rack"]["task_price_minor"], to_minor(100_000.0),
        )

    def test_task_fee_converts_currency_once(self) -> None:
        with patch(
            "tools.training_catalog.local_purchase_price",
            wraps=local_purchase_price,
        ) as convert:
            fee = training_task_fee_minor(FACILITIES["treadmill"], CNY_SETTINGS)

        convert.assert_called_once_with(400_000.0, CNY_SETTINGS)
        self.assertEqual(
            fee, to_minor(local_purchase_price(400_000.0, CNY_SETTINGS)),
        )

    def test_project_catalog_preserves_training_rules(self) -> None:
        before = copy.deepcopy(FACILITIES)
        catalog = build_training_project_catalog(FACILITIES, GBP_SETTINGS)
        by_sku = {row["sku"]: row for row in catalog}

        for sku, project in by_sku.items():
            product = FACILITIES[sku]
            for key in (
                "name", "scene", "attributes", "attribute_kind", "direction",
                "training_multiplier", "position_group", "capacity",
                "staff_training", "built_in", "unlimited",
            ):
                if key in product:
                    self.assertEqual(project[key], product[key], (sku, key))
        self.assertEqual(FACILITIES, before)
        for sku in REMOVED_FACILITY_SKUS:
            self.assertNotIn(sku, by_sku)

    def test_old_facility_ownership_does_not_gate_projects(self) -> None:
        with (
            patch.object(
                training_ground_module, "load_training_ground",
                return_value=_empty_payload(),
            ),
            patch.object(training_ground_module, "load_settings", return_value={}),
        ):
            empty = training_ground_module.public_training_ground()

        owned = _empty_payload([
            {"id": "legacy-rack", "sku": "strength_rack", "scene": "indoor", "status": "stored"},
            {"id": "legacy-desk", "sku": "coaching_desk", "scene": "office_6f", "status": "placed"},
        ])
        with (
            patch.object(
                training_ground_module, "load_training_ground",
                return_value=owned,
            ),
            patch.object(training_ground_module, "load_settings", return_value={}),
        ):
            with_ownership = training_ground_module.public_training_ground()

        self.assertEqual(len(empty["catalog"]), 29)
        self.assertEqual(empty["catalog"], with_ownership["catalog"])
        self.assertTrue(all("module" in row for row in empty["catalog"]))
        self.assertTrue(all("task_price_minor" in row for row in empty["catalog"]))


LEGACY_PURCHASE_HISTORY = [
    {"at": "2026-07-01T10:00:00", "type": "purchase", "sku": "strength_rack"},
    {"at": "2026-07-02T10:00:00", "type": "floor_unlock", "scene": "indoor_3f"},
]


def _legacy_focus(focus_id: str, focus_type: str, **extra: object) -> dict:
    focus = {
        "id": focus_id,
        "at": "2026-07-10T10:00:00",
        "status": "active",
        "focus_type": focus_type,
        "facility_id": "legacy-rack",
        "player_id": 10,
        "player_name": "A",
        "started_on": "2026-07-10",
    }
    focus.update(extra)
    return focus


def _legacy_payload() -> dict:
    payload = _empty_payload([
        {"id": "legacy-rack", "sku": "strength_rack", "scene": "indoor", "status": "placed"},
    ])
    payload["history"] = copy.deepcopy(LEGACY_PURCHASE_HISTORY)
    payload["focuses"] = [
        _legacy_focus("old-attribute", "attribute", attribute_key="身体:强壮"),
        _legacy_focus("old-position", "position", position_key="ST"),
        _legacy_focus("old-habit", "preferred_move", preferred_move_bit=13),
        _legacy_focus("old-coaching", "coaching_license", staff_id=88),
        _legacy_focus("old-completed", "attribute", status="completed"),
        _legacy_focus("old-cancelled", "attribute", status="cancelled"),
        _legacy_focus("new-format", "attribute", task_rules_version=1),
    ]
    payload["sessions"] = [{"id": "session-1", "focus_id": "old-attribute"}]
    return payload


def _relationship_payload() -> dict:
    participants = [
        {"role": "mentor", "role_label": "导师", "kind": "player", "id": 10, "name": "梅西"},
        {"role": "student", "role_label": "学员", "kind": "player", "id": 11, "name": "A"},
    ]
    pending = {
        "id": "pending-1", "focus_type": "relationship_training",
        "scene": "relationship_8f", "room_id": "room-settling", "room_sku": "mind_room",
        "participants": copy.deepcopy(participants), "attributes": ["hidden:适应性"],
        "started_on": "2026-07-02", "completed_on": "2026-07-10",
        "status": "pending_settlement",
    }
    state = relationship_training_module._new_state()
    state.pop("task_rules_version", None)  # An account saved before the new task model.
    state["rooms"] = [
        {
            "id": "room-occupied", "sku": "mentoring_room", "scene": "relationship_8f",
            "status": "occupied", "participants": copy.deepcopy(participants),
            "attributes": ["hidden:适应性"], "started_on": "2026-07-01",
            "entered_at": "2026-07-01T10:00:00", "client_submission_id": "sub-1",
        },
        {
            "id": "room-settling", "sku": "mind_room", "scene": "relationship_8f",
            "status": "settling", "participants": copy.deepcopy(participants),
            "attributes": ["hidden:适应性"], "started_on": "2026-07-02",
            "entered_at": "2026-07-02T10:00:00", "client_submission_id": "sub-2",
            "pending_session": pending,
            "settlement_started_at": "2026-07-11T10:00:00",
        },
        {
            "id": "room-idle", "sku": "tactical_room", "scene": "relationship_8f",
            "status": "idle", "participants": [], "attributes": [],
            "started_on": None, "entered_at": None, "client_submission_id": None,
        },
    ]
    state["submissions"] = ["sub-1", "sub-2"]
    return state


class TrainingTaskMigrationTests(unittest.TestCase):
    def test_migration_cancels_only_legacy_active_tasks_once(self) -> None:
        payload = _legacy_payload()
        untouched = {
            row["id"]: copy.deepcopy(row) for row in payload["focuses"]
            if row["id"] in {"old-completed", "old-cancelled", "new-format"}
        }
        with (
            patch.object(training_ground_module, "save_training_ground") as save,
            patch.object(training_ground_module, "save_document") as save_document,
            patch.object(training_ground_module, "_archive_completed_focus") as archive,
        ):
            self.assertTrue(migrate_training_tasks(payload, game_date="2026-07-19"))
            save.assert_not_called()
            save_document.assert_not_called()
            archive.assert_not_called()

        by_id = {row["id"]: row for row in payload["focuses"]}
        for focus_id in ("old-attribute", "old-position", "old-habit", "old-coaching"):
            focus = by_id[focus_id]
            self.assertEqual(focus["status"], "cancelled")
            self.assertEqual(focus["cancel_reason"], TRAINING_TASK_MIGRATION_REASON)
            self.assertEqual(focus["cancelled_on"], "2026-07-19")
            self.assertTrue(focus["cancelled_at"])
        for focus_id, row in untouched.items():
            self.assertEqual(by_id[focus_id], row)
        self.assertEqual(payload["task_rules_version"], TASK_RULES_VERSION)
        self.assertEqual(
            [
                row for row in payload["history"]
                if row.get("type") in {"purchase", "floor_unlock"}
            ],
            LEGACY_PURCHASE_HISTORY,
        )
        self.assertEqual(payload["history"][-1]["type"], TRAINING_TASK_MIGRATION_REASON)
        self.assertEqual(payload["history"][-1]["count"], 4)

        snapshot = copy.deepcopy(payload)
        self.assertFalse(migrate_training_tasks(payload, game_date="2026-07-20"))
        self.assertEqual(payload, snapshot)

    def test_migration_does_not_refund_or_apply_effects(self) -> None:
        original = _legacy_payload()
        facilities_before = copy.deepcopy(original["facilities"])
        effect_writers = (
            "advance_training_focuses", "complete_training_focuses",
            "complete_attribute_training_focus", "complete_position_training_focus",
            "complete_habit_training_focus", "complete_coaching_license_focus",
            "_archive_completed_focus",
        )
        with (
            patch.object(training_ground_module, "save_training_ground") as save,
            patch.multiple(
                training_ground_module,
                **{
                    name: MagicMock(side_effect=AssertionError(name))
                    for name in effect_writers
                },
            ),
        ):
            save.side_effect = RuntimeError("disk full")
            migrated = copy.deepcopy(original)
            self.assertTrue(migrate_training_tasks(migrated, game_date="2026-07-19"))
            with self.assertRaises(RuntimeError):
                training_ground_module.save_training_ground(migrated)

        # A failed save leaves the stored document untouched; retrying from it
        # repeats the one-time cancellation exactly once.
        retried = copy.deepcopy(original)
        self.assertTrue(migrate_training_tasks(retried, game_date="2026-07-19"))
        self.assertEqual(
            [row["id"] for row in retried["focuses"] if row.get("status") == "active"],
            ["new-format"],
        )
        self.assertEqual(retried["facilities"], facilities_before)
        self.assertEqual(retried["sessions"], original["sessions"])
        self.assertEqual(
            len([
                row for row in retried["history"]
                if row.get("type") == TRAINING_TASK_MIGRATION_REASON
            ]),
            1,
        )

    def test_migration_releases_legacy_relationship_occupancy(self) -> None:
        state = _relationship_payload()
        rooms_before = copy.deepcopy(RELATIONSHIP_ROOMS)
        with (
            patch.object(relationship_training_module, "update_document") as write,
            patch.object(relationship_training_module, "update_documents") as writes,
        ):
            self.assertTrue(
                migrate_relationship_training_rooms(state, game_date="2026-07-19"),
            )
            write.assert_not_called()
            writes.assert_not_called()

        by_id = {row["id"]: row for row in state["rooms"]}
        occupied = by_id["room-occupied"]
        self.assertEqual(
            (occupied["status"], occupied["participants"], occupied["attributes"]),
            ("idle", [], []),
        )
        self.assertIsNone(occupied["client_submission_id"])
        cancelled = occupied["cancelled_session"]
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(
            cancelled["cancel_reason"], RELATIONSHIP_TRAINING_MIGRATION_REASON,
        )
        self.assertEqual(
            [row["name"] for row in cancelled["participants"]], ["梅西", "A"],
        )
        self.assertEqual(cancelled["attributes"], ["hidden:适应性"])
        self.assertNotIn("effects", cancelled)
        settling = by_id["room-settling"]
        self.assertEqual(settling["status"], "idle")
        self.assertIsNone(settling["pending_session"])
        self.assertEqual(settling["cancelled_session"]["id"], "pending-1")
        self.assertEqual(settling["cancelled_session"]["completed_on"], "2026-07-10")
        self.assertEqual(by_id["room-idle"]["status"], "idle")

        # Room definitions and existing room records stay exactly as they were.
        self.assertEqual(RELATIONSHIP_ROOMS, rooms_before)
        self.assertEqual(len(state["rooms"]), 3)
        snapshot = copy.deepcopy(state)
        self.assertFalse(
            migrate_relationship_training_rooms(state, game_date="2026-07-20"),
        )
        self.assertEqual(state, snapshot)


class TrainingTaskIdentityTests(unittest.TestCase):
    def test_retention_keeps_active_tasks_and_their_submission_receipts(self) -> None:
        payload = _empty_payload()
        training_ground_module.append_training_task(
            payload,
            {"id": "active", "status": "active", "task_rules_version": TASK_RULES_VERSION},
            {"id": "active-session", "focus_id": "active", "task_rules_version": TASK_RULES_VERSION},
            "active-submission",
        )
        for index in range(501):
            training_ground_module.append_training_task(
                payload,
                {"id": str(index), "status": "completed", "task_rules_version": TASK_RULES_VERSION},
                {"id": f"session-{index}", "focus_id": str(index), "task_rules_version": TASK_RULES_VERSION},
                f"submission-{index}",
            )
        self.assertEqual(len(payload["focuses"]), 501)
        focus, session = training_ground_module.find_training_submission_in(payload, "active-submission")
        self.assertEqual(focus["status"], "active")
        self.assertEqual(session["id"], "active-session")
        retired_focus, retired_session = training_ground_module.find_training_submission_in(payload, "submission-0")
        self.assertEqual(retired_focus["id"], "0")
        self.assertEqual(retired_session["id"], "session-0")

    @staticmethod
    def _payload() -> dict:
        return _empty_payload([
            {"id": "rack-1", "sku": "strength_rack", "scene": "indoor", "status": "placed"},
            {"id": "habit-1", "sku": "habit_lab", "scene": "indoor", "status": "placed"},
            {"id": "desk-1", "sku": "coaching_desk", "scene": "office_6f", "status": "placed"},
        ])

    @staticmethod
    def _record(payload: dict, recorder):
        with (
            patch.object(
                training_ground_module, "load_training_ground", return_value=payload,
            ),
            patch.object(training_ground_module, "save_training_ground"),
        ):
            return recorder()

    def test_new_tasks_persist_project_module_and_rules_version(self) -> None:
        payload = self._payload()
        attribute, attribute_session = self._record(
            payload, lambda: record_training_focus(
                "rack-1", 10, "A", "2026-07-19", "身体:强壮", 0x33,
                "until_increase", 10,
            ),
        )
        position, position_session = self._record(
            payload, lambda: record_position_training_focus(
                POSITION_TRAINING_AREA_ID, 11, "B", "2026-07-19", "ST",
                "until_increase", 12,
            ),
        )
        habit, habit_session = self._record(
            payload, lambda: record_habit_training_focus(
                "habit-1", 12, "C", "2026-07-19", 13, "喜欢反越位", "learn",
            ),
        )
        coaching, coaching_session = self._record(
            payload, lambda: record_coaching_license_focus(
                "desk-1", 88, "教练", "教练", "0x1234", 679, "曼城",
                "2026-07-19", 2, 1,
            ),
        )

        for focus, session, project_sku, module in (
            (attribute, attribute_session, "strength_rack", "player_training"),
            (position, position_session, "position_training_area", "position_training"),
            (habit, habit_session, "habit_lab", "player_training"),
            (coaching, coaching_session, "coaching_desk", "staff_training"),
        ):
            for record in (focus, session):
                self.assertEqual(record["project_sku"], project_sku)
                self.assertEqual(record["module"], module)
                self.assertEqual(record["task_rules_version"], TASK_RULES_VERSION)

    def test_explicit_project_identity_is_validated(self) -> None:
        payload = self._payload()
        focus, _session = self._record(
            payload, lambda: record_training_focus(
                "rack-1", 10, "A", "2026-07-19", "身体:强壮", 0x33,
                "until_increase", 10,
                project_sku="strength_rack", module="player_training",
            ),
        )
        self.assertEqual(
            (focus["project_sku"], focus["module"]),
            ("strength_rack", "player_training"),
        )
        with self.assertRaisesRegex(ValueError, "训练模块无效"):
            self._record(
                payload, lambda: record_training_focus(
                    "rack-1", 21, "B", "2026-07-19", "身体:强壮", 0x33,
                    "until_increase", 10, project_sku="strength_rack",
                    module="staff_training",
                ),
            )
        with self.assertRaisesRegex(ValueError, "训练项目不存在"):
            self._record(
                payload, lambda: record_training_focus(
                    "rack-1", 22, "C", "2026-07-19", "身体:强壮", 0x33,
                    "until_increase", 10, project_sku="kick_target",
                ),
            )

    def test_settlement_resolves_project_without_inventory_instance(self) -> None:
        self.assertEqual(
            training_ground_module._focus_training_multiplier({
                "project_sku": "adaptation_pod", "facility_id": "",
            }),
            2,
        )
        self.assertEqual(
            training_ground_module._focus_training_multiplier({
                "project_sku": "position_training_area", "facility_id": "",
            }),
            4,
        )


if __name__ == "__main__":
    unittest.main()
