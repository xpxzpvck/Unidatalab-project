from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml
from app.schemas import Menu, MenuItem, Ingredient, ComboSlot
from app.config import settings

class MenuService:
    def __init__(self):
        self.menu = Menu()
        self._load_menu()

    def _merge_item(self, existing: MenuItem, incoming: MenuItem):
        existing.price = incoming.price or existing.price

        if incoming.properties:
            if existing.properties is None:
                existing.properties = {}
            existing.properties.update(incoming.properties)

        if incoming.slots:
            if existing.slots is None:
                existing.slots = {}
            for slot_name, slot_val in incoming.slots.items():
                if slot_name not in existing.slots:
                    existing.slots[slot_name] = slot_val

        if not existing.default_ingredients and incoming.default_ingredients:
            existing.default_ingredients = incoming.default_ingredients
        
        if not existing.possible_ingredients and incoming.possible_ingredients:
            existing.possible_ingredients = incoming.possible_ingredients

    def _upsert_item(self, item: MenuItem):
        if item.name in self.menu.items:
            existing_item = self.menu.items[item.name]
            self._merge_item(existing_item, item)
        else:
            self.menu.items[item.name] = item

    def _transform_properties(self, raw_props: Any) -> Dict[str, List[str]]:
        if isinstance(raw_props, dict):
            return raw_props
        if isinstance(raw_props, list):
            new_props = {}
            for p in raw_props:
                if isinstance(p, dict) and "name" in p:
                    new_props[p["name"]] = p.get("values", [])
            return new_props
        return {}

    def _load_menu(self):
        raw_data = {"items": [], "combos": [], "deals": [], "ingredients": []}

        for fname in settings.MENU_FILES:
            fpath = settings.DATA_DIR / fname
            if fpath.exists():
                with open(fpath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}

                    for key in raw_data:
                        if key in data and isinstance(data[key], list):
                            raw_data[key].extend(data[key])
        
        for ing in raw_data["ingredients"]:
            self.menu.ingredients[ing["name"]] = Ingredient(**ing)

        for item in raw_data["items"]:
            if "properties" in item:
                item["properties"] = self._transform_properties(item["properties"])
            menu_item = MenuItem(**item)
            self._upsert_item(menu_item)

        for combo in raw_data["combos"]:
            if "properties" in combo:
                combo["properties"] = self._transform_properties(combo["properties"])

            raw_slots = combo.pop("slots", {})
            processed_slots = {}
            for slot_name, slot_val in raw_slots.items():
                options = slot_val if isinstance(slot_val, list) else slot_val.get("options", [])
                optional = slot_val.get("optional", False) if isinstance(slot_val, dict) else False
                processed_slots[slot_name] = ComboSlot(
                    name=slot_name, options=options, optional=optional
                )

            combo_item = MenuItem(**combo)
            combo_item.slots = processed_slots
            self._upsert_item(combo_item)

        for deal in raw_data["deals"]:
            if "properties" in deal:
                deal["properties"] = self._transform_properties(deal["properties"])

            deal_item = MenuItem(**deal)
            deal_item.is_deal = True
            self._upsert_item(deal_item)

    def get_item(self, name: str) -> Optional[MenuItem]:
        return self.menu.items.get(name)

    def get_ingredient(self, name: str) -> Optional[Ingredient]:
        return self.menu.ingredients.get(name)

    def get_virtual_options(self, name: str) -> List[str]:
        item = self.get_item(name)
        return item.possible_items if item and item.virtual else []


if __name__ == "__main__":
    menu_service = MenuService()
    print(menu_service.menu)