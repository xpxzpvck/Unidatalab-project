from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.core.llm_service import LLMResult, LLMService
from app.models.menu import Combo, Menu, MenuItem
from app.models.order import Order, OrderComponent, OrderItem


@dataclass
class ChatResponse:
    message: str
    order_complete: bool = False
    used_llm_fallback: bool = False


@dataclass
class SessionState:
    order: Order = field(default_factory=Order)
    pending_combo_drinks: List[OrderItem] = field(default_factory=list)
    pending_double_deal: Optional[OrderItem] = None
    last_system_message: str = ""


def _base_burger_name_from_combo(combo_name: str) -> Optional[str]:
    if combo_name.lower().endswith(" meal"):
        return combo_name[:-5].strip()
    return None


class OrderManager:
    def __init__(self, menu: Menu, llm_service: LLMService):
        self.menu = menu
        self.llm = llm_service

    def _normalize_combo_slots(self, item: OrderItem) -> None:
        """Normalize slot names so 'drinks' maps to 'drink' for validation."""
        for comp in item.components:
            if comp.slot == "drinks":
                comp.slot = "drink"

    def greeting(self) -> str:
        return "Welcome to McDonald's! What can I get you started with?"

    def _menu_item(self, name: str) -> Optional[MenuItem]:
        return self.menu.get_item(name)

    def _combo(self, name: str) -> Optional[Combo]:
        return self.menu.get_combo(name)

    def _format_options(self, values: List[str]) -> str:
        return ", ".join(values)

    def _validate_standalone_size(self, item: OrderItem) -> Optional[str]:
        meta = self._menu_item(item.name)
        if not meta:
            return "unknown"
        if meta.requires_property("size") and "size" not in item.properties:
            return f"What size {item.name} would you like? (options: {self._format_options(meta.properties['size'])})"
        return None

    def _validate_virtual(self, name: str) -> Optional[str]:
        options = self.menu.list_virtual_options(name)
        if options:
            return f"Which {name} would you like? Options: {self._format_options(options)}."
        return None

    def _assign_drinks_to_pending_combos(
        self, state: SessionState, incoming: List[OrderItem], confirmations: List[str]
    ) -> Tuple[List[OrderItem], List[OrderItem]]:
        remaining: List[OrderItem] = []
        drink_candidates: List[OrderItem] = []
        updated_combos: List[OrderItem] = []

        for item in incoming:
            meta = self._menu_item(item.name)
            if meta and meta.category == "drinks":
                drink_candidates.append(item)
            else:
                remaining.append(item)

        for combo_item in list(state.pending_combo_drinks):
            if not drink_candidates:
                break
            drink = drink_candidates.pop(0)
            combo_item.components.append(OrderComponent(name=drink.name, slot="drink", properties=drink.properties))
            confirmations.append(f"Added {drink.name} to your {combo_item.name}.")
            state.pending_combo_drinks.remove(combo_item)
            updated_combos.append(combo_item)
            
        remaining.extend(drink_candidates)
        return remaining, updated_combos

    def _validate_combo(self, item: OrderItem, clarifications: List[str], confirmations: List[str], state: SessionState) -> bool:
        combo_meta = self._combo(item.name)
        if not combo_meta:
            clarifications.append(f"I couldn't find {item.name} as a combo. Can you rephrase the combo order?")
            return False
        self._normalize_combo_slots(item)
        has_drink = any(comp.slot == "drink" for comp in item.components)
        has_fries = any(comp.slot == "fries" for comp in item.components)
        
        
        existing_match = None
        for existing in reversed(state.order.items):
            if existing.name == item.name and existing.kind == "combo":
                existing_match = existing
                break

        if not has_drink and existing_match:
            
            if any(c.slot == "drink" for c in existing_match.components):
                has_drink = True
        
        if not has_fries:
            
            props = {}
            fries_meta = self.menu.get_item("French Fries")
            if fries_meta and fries_meta.requires_property("size"):
                props["size"] = "medium"
            
            item.components.append(OrderComponent(name="French Fries", slot="fries", properties=props))
            confirmations.append(f"Added default French Fries to your {item.name}.")
            
        if not has_drink:
            drink_slot = combo_meta.slots.get("drinks") or combo_meta.slots.get("drink")
            drink_options = drink_slot.options if drink_slot else []
            clarifications.append(
                f"Which drink would you like with your {item.name}? Options: "
                f"{self._format_options(drink_options) or 'any listed soft drink/coffee/tea'}."
            )
            return False

        
        for comp in item.components:
            slot_def = combo_meta.slots.get(comp.slot or "") or (
                combo_meta.slots.get("drinks") if comp.slot == "drink" else None
            )
            if slot_def and comp.name not in slot_def.options:
                clarifications.append(
                    f"{comp.name} is not available for {item.name} {comp.slot or 'item'}. "
                    f"Available: {self._format_options(slot_def.options)}."
                )
                return False
            
            
            comp_meta = self._menu_item(comp.name)
            if comp_meta and comp_meta.requires_property("size") and "size" not in comp.properties:
                
                if "medium" in comp_meta.properties.get("size", []):
                    comp.properties["size"] = "medium"
                else:
                    clarifications.append(
                        f"What size {comp.name} would you like with the {item.name}? "
                        f"(options: {self._format_options(comp_meta.properties['size'])})"
                    )
                    return False
        return True

    def _pick_double_deal(self, first: str, second: str) -> Optional[str]:
        for deal in self.menu.deals.values():
            if first in deal.possible_items and second in deal.possible_items:
                return deal.name
        return None

    def _optimize_order_deals(
        self, state: SessionState, confirmations: List[str]
    ) -> None:
        """
        Scans the ENTIRE order state for standalone burgers and merges them 
        into double deals if applicable.
        """
        
        
        burgers: List[OrderItem] = []
        non_burgers: List[OrderItem] = []

        for item in state.order.items:
            meta = self._menu_item(item.name)
            if item.kind == "item" and meta and meta.category == "burgers":
                burgers.append(item)
            else:
                non_burgers.append(item)

        if len(burgers) < 2:
            return  

        new_deals: List[OrderItem] = []
        
        
        while len(burgers) >= 2:
            first = burgers.pop(0)
            second = burgers.pop(0)
            
            deal_name = self._pick_double_deal(first.name, second.name) or "Double Deal"
            double_deal = OrderItem(
                name=deal_name,
                kind="double_deal",
                components=[
                    OrderComponent(
                        name=first.name, 
                        slot="item1", 
                        properties=first.properties,
                        add_ingredients=first.add_ingredients,
                        remove_ingredients=first.remove_ingredients
                    ),
                    OrderComponent(
                        name=second.name, 
                        slot="item2", 
                        properties=second.properties,
                        add_ingredients=second.add_ingredients,
                        remove_ingredients=second.remove_ingredients
                    ),
                ],
            )
            confirmations.append(
                f"I've bundled your {first.name} and {second.name} into a {deal_name} for a discount."
            )
            new_deals.append(double_deal)

        
        state.order.items = non_burgers + new_deals + burgers

    def _validate_ingredients(self, item: OrderItem) -> Optional[str]:
        """Validate added/removed ingredients against the menu."""
        meta = self._menu_item(item.name)
        if not meta:
            return None
        
        
        for ing in item.add_ingredients:
            if ing not in self.menu.ingredients:
                return f"I don't have the ingredient '{ing}'."
            
            if meta.possible_ingredients and ing not in meta.possible_ingredients:
                return f"I cannot add {ing} to {item.name}."

        
        for ing in item.remove_ingredients:
             if meta.default_ingredients and ing not in meta.default_ingredients:
                 pass 
        return None

    def _apply_validations(
        self, incoming: List[OrderItem], state: SessionState, clarifications: List[str], confirmations: List[str]
    ) -> List[OrderItem]:
        valid_items: List[OrderItem] = []
        for item in incoming:
            
            virtual_prompt = self._validate_virtual(item.name)
            if virtual_prompt:
                clarifications.append(virtual_prompt)
                continue
            
            meta = self._menu_item(item.name)
            
            if item.kind == "double_deal":
                if not item.components or len(item.components) < 2:
                    state.pending_double_deal = item
                    clarifications.append(
                        "Which second item would you like to include in your double deal?"
                        if item.components
                        else "Which two items should go into your double deal?"
                    )
                    continue
                if not all(self._menu_item(comp.name) for comp in item.components):
                    clarifications.append("I could not match those items for the double deal. Can you list them again?")
                    continue
                deal_name = self._pick_double_deal(item.components[0].name, item.components[1].name)
                if deal_name:
                    item.name = deal_name
                else:
                    clarifications.append("Those items are not available as a double deal. Choose burgers from the menu.")
                    continue
                valid_items.append(item)
                continue

            if item.kind == "combo":
                if not self._validate_combo(item, clarifications, confirmations, state):
                    continue
                if not any(comp.slot == "drink" for comp in item.components):
                    state.pending_combo_drinks.append(item)
                valid_items.append(item)
                continue

            if not meta:
                clarifications.append(f"I couldn't find {item.name} on the menu. Can you rephrase?")
                continue
            
            size_prompt = self._validate_standalone_size(item)
            if size_prompt:
                clarifications.append(size_prompt)
                continue
            
            
            ing_error = self._validate_ingredients(item)
            if ing_error:
                clarifications.append(ing_error)
                continue

            valid_items.append(item)
        return valid_items

    def _apply_pending_double_deal(
        self, state: SessionState, incoming: List[OrderItem], confirmations: List[str]
    ) -> Tuple[List[OrderItem], List[OrderItem]]:
        if not state.pending_double_deal:
            return [], incoming
        completed: List[OrderItem] = []
        remaining: List[OrderItem] = []
        for item in incoming:
            meta = self._menu_item(item.name)
            if meta and meta.category == "burgers" and state.pending_double_deal:
                pending = state.pending_double_deal
                pending.components.append(
                    OrderComponent(
                        name=item.name, 
                        slot="item2",
                        properties=item.properties,
                        add_ingredients=item.add_ingredients,
                        remove_ingredients=item.remove_ingredients
                    )
                )
                confirmations.append(f"Added {item.name} as the second item in your double deal.")
                completed.append(pending)
                state.pending_double_deal = None
                continue
            remaining.append(item)
        return completed, remaining

    def _compose_confirmation(self, added_items: List[OrderItem]) -> str:
        if not added_items:
            return ""
        line = "; ".join(item.describe() for item in added_items)
        return f"Got it: {line}."

    def _upsell_prompts(self, items: List[OrderItem], state: SessionState) -> List[str]:
        prompts: List[str] = []
        for item in items:
            
            if item.kind == "combo":
                prompts.append(f"Would you like to add a dipping sauce to your {item.name} for an extra charge?")
                if not state.order.dessert_offered:
                    prompts.append("Care for a dessert to go with that?")
                    state.order.dessert_offered = True
                continue

            
            meta = self._menu_item(item.name)
            if not meta:
                continue
            if item.kind == "item" and meta.category == "burgers":
                prompts.append(f"Would you like to make the {item.name} a combo?")
                if not state.order.dessert_offered:
                    prompts.append("Care for a dessert to go with that?")
                    state.order.dessert_offered = True
        return prompts

    def _finalize_or_continue(
        self, state: SessionState, clarifications: List[str], confirmations: List[str], upsells: List[str], intent_end: bool
    ) -> ChatResponse:
        if clarifications:
            message = " ".join(clarifications + confirmations)
            return ChatResponse(message=message)
        if intent_end:
            if state.order.is_empty():
                return ChatResponse("I don't have any items on your order yet. What would you like?", order_complete=False)
            summary = state.order.summary_lines(self.menu)
            total = state.order.total(self.menu)
            message = "Your order total is ${:.2f}. Items: {}.".format(total, "; ".join(summary))
            return ChatResponse(message=message, order_complete=True)
        trailing = upsells or ["Anything else I can get you?"]
        message = " ".join(confirmations + trailing)
        return ChatResponse(message=message)
    
    def _update_or_add_item(self, state: SessionState, incoming: OrderItem, confirmations: List[str]) -> None:
        existing = None
        
        for item in reversed(state.order.items):
            if item.name == incoming.name:
                existing = item
                break
        
        if existing:
            
            existing.add_ingredients.extend(incoming.add_ingredients)
            existing.remove_ingredients.extend(incoming.remove_ingredients)
            existing.properties.update(incoming.properties)

            
            for inc_comp in incoming.components:
                match = None
                for ex_comp in existing.components:
                    
                    if ex_comp.name == inc_comp.name or (ex_comp.slot and ex_comp.slot == inc_comp.slot):
                        match = ex_comp
                        break
                
                if match:
                    match.properties.update(inc_comp.properties)
                    match.add_ingredients.extend(inc_comp.add_ingredients)
                    match.remove_ingredients.extend(inc_comp.remove_ingredients)
                else:
                    existing.components.append(inc_comp)
            
            confirmations.append(f"Updated your {existing.name}.")
        else:
            state.order.add_item(incoming)

    def process_message(self, state: SessionState, user_message: str) -> ChatResponse:
        prior_summary = "; ".join(state.order.summary_lines(self.menu))
        result: LLMResult = self.llm.parse_intent(
            user_message, self.menu, prior_summary, state.last_system_message
        )
        if not result.success or not result.intent:
            fallback_text = ""
            if self.llm:
                try:
                    fallback_text = self.llm.generate_reply(user_message, self.menu, prior_summary)
                except Exception:
                    fallback_text = ""
            response = ChatResponse(
                message=(
                    f"I had trouble understanding that. {fallback_text or 'Could you rephrase your order?'}"
                    + (f" (LLM error: {result.error})" if result and result.error else "")
                ),
                used_llm_fallback=bool(fallback_text),
            )
            state.last_system_message = response.message
            return response

        clarifications: List[str] = []
        confirmations: List[str] = []

        incoming = list(result.intent.ordered_items)
        incoming, updated_combos = self._assign_drinks_to_pending_combos(state, incoming, confirmations)
        completed_deals, incoming = self._apply_pending_double_deal(state, incoming, confirmations)
        incoming = completed_deals + incoming

        valid_items = self._apply_validations(incoming, state, clarifications, confirmations)
        
        

        for item in valid_items:
            if item.kind == "combo":
                self._replace_burger_with_combo(state, item, confirmations)
            self._update_or_add_item(state, item, confirmations)
        
        
        self._optimize_order_deals(state, confirmations)

        confirmation_text = self._compose_confirmation(valid_items)
        if confirmation_text:
            confirmations.insert(0, confirmation_text)

        upsell_candidates = valid_items + updated_combos
        upsells = self._upsell_prompts(upsell_candidates, state)

        
        if not valid_items and not updated_combos and not clarifications and not confirmations and not result.intent.end_order:
            reply = self.llm.generate_reply(user_message, self.menu, prior_summary)
            state.last_system_message = reply
            return ChatResponse(message=reply, used_llm_fallback=True)

        chat_response = self._finalize_or_continue(
            state, clarifications, confirmations, upsells, result.intent.end_order
        )
        state.last_system_message = chat_response.message
        return chat_response

    def _replace_burger_with_combo(self, state: SessionState, combo_item: OrderItem, confirmations: List[str]) -> None:
        base = _base_burger_name_from_combo(combo_item.name)
        if not base:
            return
        for idx, existing in enumerate(state.order.items):
            if existing.kind == "item" and existing.name.lower() == base.lower():
                state.order.items.pop(idx)
                confirmations.append(f"Converted your {base} into a combo.")
                break