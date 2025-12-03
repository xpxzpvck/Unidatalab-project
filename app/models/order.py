from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .menu import Menu, MenuItem


class IngredientChange(BaseModel):
    name: str
    action: str  # "add" or "remove"


class OrderComponent(BaseModel):
    name: str
    slot: Optional[str] = None
    properties: Dict[str, str] = Field(default_factory=dict)
    add_ingredients: List[str] = Field(default_factory=list)
    remove_ingredients: List[str] = Field(default_factory=list)


class OrderItem(BaseModel):
    name: str
    kind: str = "item"  # item | combo | double_deal
    quantity: int = 1
    properties: Dict[str, str] = Field(default_factory=dict)
    components: List[OrderComponent] = Field(default_factory=list)
    add_ingredients: List[str] = Field(default_factory=list)
    remove_ingredients: List[str] = Field(default_factory=list)

    def describe(self) -> str:
        modifiers: List[str] = []
        if self.properties:
            prop_bits = ", ".join(f"{k}={v}" for k, v in self.properties.items())
            modifiers.append(prop_bits)
        if self.add_ingredients:
            modifiers.append(f"add {', '.join(self.add_ingredients)}")
        if self.remove_ingredients:
            modifiers.append(f"no {', '.join(self.remove_ingredients)}")
        comp_bits = []
        for comp in self.components:
            label = comp.name
            inner_mods = []
            if comp.properties:
                inner_mods.append(
                    ", ".join(f"{k}={v}" for k, v in comp.properties.items())
                )
            if comp.add_ingredients:
                inner_mods.append(f"add {', '.join(comp.add_ingredients)}")
            if comp.remove_ingredients:
                inner_mods.append(f"no {', '.join(comp.remove_ingredients)}")
            if inner_mods:
                label = f"{label} ({'; '.join(inner_mods)})"
            if comp.slot:
                label = f"{comp.slot}: {label}"
            comp_bits.append(label)
        parts = [self.name]
        if modifiers:
            parts.append(f"({'; '.join(modifiers)})")
        if comp_bits:
            parts.append(f"[{'; '.join(comp_bits)}]")
        prefix = f"{self.quantity}x "
        return prefix + " ".join(parts)


class Order(BaseModel):
    items: List[OrderItem] = Field(default_factory=list)
    dessert_offered: bool = False

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def add_item(self, item: OrderItem) -> None:
        self.items.append(item)

    def _base_item_price(self, item: OrderItem, menu: Menu) -> float:
        menu_item: Optional[MenuItem] = menu.get_item(item.name)
        if not menu_item or menu_item.price is None:
            return 0.0
        price = menu_item.price
        for ingredient in item.add_ingredients:
            ingredient_meta = menu.ingredients.get(ingredient)
            if ingredient_meta:
                price += ingredient_meta.price
        # Removals do not change price.
        return price

    def _component_price(self, comp: OrderComponent, menu: Menu) -> float:
        menu_item = menu.get_item(comp.name)
        base = menu_item.price if menu_item and menu_item.price else 0.0
        for ingredient in comp.add_ingredients:
            ingredient_meta = menu.ingredients.get(ingredient)
            if ingredient_meta:
                base += ingredient_meta.price
        return base

    def item_total(self, item: OrderItem, menu: Menu) -> float:
        if item.kind == "double_deal":
            subtotal = sum(
                self._component_price(comp, menu) for comp in item.components
            )
            deal = (
                menu.get_double_deal(item.name)
                if hasattr(menu, "get_double_deal")
                else None
            )
            discount = deal.discount if deal else 0.2
            total = subtotal * (1 - discount)
            return total * max(item.quantity, 1)
        if item.kind == "combo":
            combo = menu.get_combo(item.name)
            price = combo.price if combo and combo.price else 0.0
            for comp in item.components:
                if comp.slot == "sauces":
                    price += self._component_price(comp, menu)
            return price * max(item.quantity, 1)
        return self._base_item_price(item, menu) * max(item.quantity, 1)

    def total(self, menu: Menu) -> float:
        return sum(self.item_total(item, menu) for item in self.items)

    def summary_lines(self, menu: Menu) -> List[str]:
        return [item.describe() for item in self.items]
