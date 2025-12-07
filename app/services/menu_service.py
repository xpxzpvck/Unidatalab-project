from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml
from app.schemas import Menu, MenuItem, Ingredient, ComboSlot

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class MenuService:
    def __init__(self):
        self.menu = Menu()
        self._load_menu()

    def _transform_properties(self, raw_props: Any) -> Dict[str, List[str]]:
        """
        Converts a list of properties from YAML to a dictionary format for Pydantic.
        Input: [{'name': 'size', 'values': ['small', 'medium']}]
        Output: {'size': ['small', 'medium']}
        """
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
        files = [
            "menu_deals.yaml",
            "menu_ingredients.yaml",
            "menu_upsells.yaml",
            "menu_virtual_items.yaml",
        ]
        raw_data = {"items": [], "combos": [], "deals": [], "ingredients": []}

        for fname in files:
            fpath = DATA_DIR / fname
            if fpath.exists():
                with open(fpath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}

                    for key in raw_data:
                        if key in data and isinstance(data[key], list):
                            raw_data[key].extend(data[key])

                    if "ingredients" in data and isinstance(data["ingredients"], list):
                        for ing in data["ingredients"]:
                            self.menu.ingredients[ing["name"]] = Ingredient(**ing)

        for item in raw_data["items"]:

            if "properties" in item:
                item["properties"] = self._transform_properties(item["properties"])

            self.menu.items[item["name"]] = MenuItem(**item)

        for combo in raw_data["combos"]:
            if "properties" in combo:
                combo["properties"] = self._transform_properties(combo["properties"])

            raw_slots = combo.pop("slots", {})
            processed_slots = {}
            for s_name, s_val in raw_slots.items():
                opts = s_val if isinstance(s_val, list) else s_val.get("options", [])
                opt = s_val.get("optional", False) if isinstance(s_val, dict) else False
                processed_slots[s_name] = ComboSlot(
                    name=s_name, options=opts, optional=opt
                )

            c_item = MenuItem(**combo)
            c_item.slots = processed_slots
            self.menu.items[combo["name"]] = c_item

        for deal in raw_data["deals"]:
            if "properties" in deal:
                deal["properties"] = self._transform_properties(deal["properties"])

            d_item = MenuItem(**deal)
            d_item.is_deal = True
            self.menu.items[deal["name"]] = d_item

    def get_item(self, name: str) -> Optional[MenuItem]:
        return self.menu.items.get(name)

    def get_ingredient(self, name: str) -> Optional[Ingredient]:
        return self.menu.ingredients.get(name)

    def get_virtual_options(self, name: str) -> List[str]:
        item = self.get_item(name)
        return item.possible_items if item and item.virtual else []
