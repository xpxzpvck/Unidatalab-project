from typing import Tuple
from app.schemas import Order, OrderItem, OrderComponent


class CartService:
    def __init__(self, menu_service):
        self.menu_service = menu_service

    def calculate_total(self, order: Order) -> float:
        total = 0.0
        for item in order.items:
            meta = self.menu_service.get_item(item.name)
            if not meta:
                continue

            item_total = 0.0

            if meta.is_deal:
                subtotal = 0.0
                for comp in item.components:
                    comp_meta = self.menu_service.get_item(comp.name)
                    if comp_meta and comp_meta.price:
                        comp_price = comp_meta.price
                        for ing_name in comp.add_ingredients:
                            ing = self.menu_service.get_ingredient(ing_name)
                            if ing:
                                comp_price += ing.price
                        subtotal += comp_price

                discount = meta.discount or 0.0
                item_total = subtotal * (1.0 - discount)

            else:
                item_total = meta.price or 0.0

                for ing_name in item.add_ingredients:
                    ing = self.menu_service.get_ingredient(ing_name)
                    if ing:
                        item_total += ing.price

                for comp in item.components:
                    if comp.slot == "sauces":
                        sauce = self.menu_service.get_item(comp.name)
                        if sauce and sauce.price:
                            item_total += sauce.price

            total += item_total * item.quantity

        return total

    def validate_item(self, item: OrderItem) -> Tuple[bool, str]:
        """Checks if item is valid (exists, has required options)."""
        meta = self.menu_service.get_item(item.name)
        if not meta:
            return False, f"Sorry, I couldn't find '{item.name}' on the menu."

        if meta.virtual:
            options = ", ".join(meta.possible_items)
            return False, f"Please specify which {item.name}? Options: {options}."
        if meta.properties.get("size") and "size" not in item.properties:
            return (
                False,
                f"What size {item.name}? ({', '.join(meta.properties['size'])})",
            )

        if meta.slots:
            for slot_name, slot_def in meta.slots.items():
                if slot_def.optional:
                    continue

                found = any(
                    c.slot == slot_name or c.name in slot_def.options
                    for c in item.components
                )

                if slot_name in ["drink", "drinks"] and not found:
                    found = any(c.slot in ["drink", "drinks"] for c in item.components)

                if not found:
                    examples = (
                        slot_def.options[:3] if slot_def.options else ["Cola", "Fanta"]
                    )
                    return (
                        False,
                        f"Please choose a drink for {item.name}: {', '.join(examples)}...",
                    )

        return True, ""

    def _are_items_equal(self, item1: OrderItem, item2: OrderItem) -> bool:
        """Checks if two items are identical (for merging in the cart)."""
        if item1.name != item2.name:
            return False
        if item1.properties != item2.properties:
            return False

        if set(item1.add_ingredients) != set(item2.add_ingredients):
            return False
        if set(item1.remove_ingredients) != set(item2.remove_ingredients):
            return False

        comps1 = sorted(
            [c.model_dump(exclude_none=True) for c in item1.components],
            key=lambda x: x["name"],
        )
        comps2 = sorted(
            [c.model_dump(exclude_none=True) for c in item2.components],
            key=lambda x: x["name"],
        )

        return comps1 == comps2

    def add_item(self, order: Order, item: OrderItem) -> None:
        """Adds an item to the order, merging duplicates."""
        for existing_item in order.items:
            if self._are_items_equal(existing_item, item):
                existing_item.quantity += item.quantity
                return

        order.items.append(item)
