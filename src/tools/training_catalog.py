from __future__ import annotations

from typing import Any

from tools.app_settings import local_purchase_price
from tools.money import to_minor


TRAINING_MODULES = ("player_training", "position_training", "staff_training")
TASK_PRICE_RATIO = 0.5


def training_module_for_product(sku: str, product: dict[str, Any]) -> str:
    """Return the stable three-module key for one original facility definition."""
    if product.get("staff_training"):
        return "staff_training"
    if str(product.get("scene") or "") == "position_training":
        return "position_training"
    return "player_training"


def training_task_fee_minor(
    product: dict[str, Any], settings: dict[str, Any],
) -> int:
    """Half the original GBP base price in local minor units, converted once."""
    price = float(product.get("price") or 0)
    if price <= 0:
        return 0
    return to_minor(local_purchase_price(price * TASK_PRICE_RATIO, settings))


def build_training_project_catalog(
    products: dict[str, dict[str, Any]], settings: dict[str, Any],
) -> list[dict[str, Any]]:
    """Public project rows for kept SKUs only: rules, module and fixed task fee."""
    return [
        {
            **product,
            "sku": sku,
            "module": training_module_for_product(sku, product),
            # Legacy shop projection; the paid task always reads task_price_minor.
            "price": local_purchase_price(product.get("price") or 0, settings),
            "task_price_minor": training_task_fee_minor(product, settings),
        }
        for sku, product in products.items()
    ]
