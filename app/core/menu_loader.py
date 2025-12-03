from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

from app.models.menu import Combo, ComboSlot, DoubleDeal, Ingredient, Menu, MenuItem


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
MENU_FILES = [
    DATA_DIR / "menu_deals.yaml",
    DATA_DIR / "menu_ingredients.yaml",
    DATA_DIR / "menu_upsells.yaml",
    DATA_DIR / "menu_virtual_items.yaml",
]


def _as_property_map(raw_properties: Optional[Iterable[Dict]]) -> Dict[str, List[str]]:
    properties: Dict[str, List[str]] = {}
    if not raw_properties:
        return properties
    for prop in raw_properties:
        name = prop.get("name")
        values = prop.get("values", [])
        if name:
            properties[name] = values
    return properties


def _merge_item(menu: Menu, raw: Dict) -> None:
    name = raw.get("name")
    if not name:
        return
    existing = menu.items.get(name, MenuItem(name=name))
    properties = _as_property_map(raw.get("properties"))
    existing.properties.update({k: v for k, v in properties.items() if v})
    if raw.get("category"):
        existing.category = raw["category"]
    if raw.get("price") is not None:
        existing.price = float(raw["price"])
    if raw.get("default_ingredients"):
        existing.default_ingredients = list(raw.get("default_ingredients", []))
    if raw.get("possible_ingredients"):
        existing.possible_ingredients = list(raw.get("possible_ingredients", []))
    if raw.get("virtual"):
        existing.virtual = True
    if raw.get("possible_items"):
        existing.possible_items = list(raw["possible_items"])
    menu.items[name] = existing


def _parse_combo_slot(slot: str, value) -> ComboSlot:
    if isinstance(value, dict):
        options = value.get("options") or value.get("values") or []
        optional = bool(value.get("optional"))
    else:
        options = list(value) if isinstance(value, list) else [value]
        optional = False
    return ComboSlot(name=slot, options=options, optional=optional)


def _merge_combo(menu: Menu, raw: Dict) -> None:
    name = raw.get("name")
    if not name:
        return
    existing = menu.combos.get(name, Combo(name=name))
    if raw.get("category"):
        existing.category = raw["category"]
    if raw.get("price") is not None:
        existing.price = float(raw["price"])
    if raw.get("virtual"):
        existing.virtual = True
    if raw.get("possible_items"):
        existing.possible_items = list(raw["possible_items"])

    slots_raw = raw.get("slots", {})
    for slot_name, slot_value in slots_raw.items():
        existing.slots[slot_name] = _parse_combo_slot(slot_name, slot_value)
    menu.combos[name] = existing


def _merge_double_deal(menu: Menu, raw: Dict) -> None:
    name = raw.get("name")
    if not name:
        return
    deal = menu.deals.get(name, DoubleDeal(name=name))
    if raw.get("possible_items"):
        deal.possible_items = list(raw["possible_items"])
    if raw.get("discount") is not None:
        deal.discount = float(raw["discount"])
    menu.deals[name] = deal


def _merge_ingredients(menu: Menu, raw: Dict) -> None:
    for entry in raw.get("ingredients", []):
        name = entry.get("name")
        if not name:
            continue
        menu.ingredients[name] = Ingredient(name=name, price=float(entry.get("price", 0.0)))


def load_menu() -> Menu:
    menu = Menu()
    for path in MENU_FILES:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _merge_ingredients(menu, data)
        for item in data.get("items", []):
            _merge_item(menu, item)
        for combo in data.get("combos", []):
            _merge_combo(menu, combo)
        for deal in data.get("deals", []):
            _merge_double_deal(menu, deal)
    return menu
