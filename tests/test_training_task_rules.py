from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from tools import training_ground as training_ground_module
from tools.app_settings import MONEY_CURRENCIES, local_purchase_price
from tools.money import to_minor
from tools.training_catalog import (
    TRAINING_MODULES,
    build_training_project_catalog,
    training_module_for_product,
    training_task_fee_minor,
)
from tools.training_ground import FACILITIES, REMOVED_FACILITY_SKUS


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
        "unlocked_floors": [],
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


if __name__ == "__main__":
    unittest.main()
