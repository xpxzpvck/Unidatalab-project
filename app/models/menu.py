from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Ingredient(BaseModel):
    name: str
    price: float = 0.0


class MenuItem(BaseModel):
    name: str
    category: Optional[str] = None
    price: Optional[float] = None
    properties: Dict[str, List[str]] = Field(default_factory=dict)
    default_ingredients: List[str] = Field(default_factory=list)
    possible_ingredients: List[str] = Field(default_factory=list)
    virtual: bool = False
    possible_items: List[str] = Field(default_factory=list)

    def requires_property(self, prop: str) -> bool:
        return prop in self.properties and bool(self.properties[prop])


class ComboSlot(BaseModel):
    name: str
    options: List[str]
    optional: bool = False


class Combo(BaseModel):
    name: str
    category: Optional[str] = None
    price: Optional[float] = None
    slots: Dict[str, ComboSlot] = Field(default_factory=dict)
    virtual: bool = False
    possible_items: List[str] = Field(default_factory=list)

    def requires_slot(self, slot: str) -> bool:
        combo_slot = self.slots.get(slot)
        return combo_slot is not None and not combo_slot.optional


class DoubleDeal(BaseModel):
    name: str
    category: str = "deals"
    possible_items: List[str] = Field(default_factory=list)
    discount: float = 0.2


class Menu(BaseModel):
    items: Dict[str, MenuItem] = Field(default_factory=dict)
    combos: Dict[str, Combo] = Field(default_factory=dict)
    deals: Dict[str, DoubleDeal] = Field(default_factory=dict)
    ingredients: Dict[str, Ingredient] = Field(default_factory=dict)

    def get_item(self, name: str) -> Optional[MenuItem]:
        return self.items.get(name)

    def get_combo(self, name: str) -> Optional[Combo]:
        return self.combos.get(name)

    def get_double_deal(self, name: str) -> Optional[DoubleDeal]:
        return self.deals.get(name)

    def list_virtual_options(self, name: str) -> List[str]:
        item = self.items.get(name)
        combo = self.combos.get(name)
        possible: List[str] = []
        if item and item.virtual:
            possible = item.possible_items
        if combo and combo.virtual:
            possible = combo.possible_items
        return possible

    def as_prompt_payload(self) -> Dict[str, object]:
        return {
            "items": [
                {
                    "name": item.name,
                    "category": item.category,
                    "price": item.price,
                    "properties": item.properties,
                    "default_ingredients": item.default_ingredients,
                }
                for item in self.items.values()
            ],
            "combos": [
                {
                    "name": combo.name,
                    "category": combo.category,
                    "price": combo.price,
                    "slots": {
                        slot: slot_def.options for slot, slot_def in combo.slots.items()
                    },
                }
                for combo in self.combos.values()
            ],
            "double_deals": [
                {
                    "name": deal.name,
                    "possible_items": deal.possible_items,
                    "discount": deal.discount,
                }
                for deal in self.deals.values()
            ],
            "ingredients": [
                {"name": ingredient.name, "price": ingredient.price}
                for ingredient in self.ingredients.values()
            ],
        }
