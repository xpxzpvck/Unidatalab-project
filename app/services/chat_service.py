from app.schemas import SessionState, OrderItem, OrderComponent, ItemType
from app.services.llm_service import LLMService
from app.services.cart_service import CartService
from app.services.menu_service import MenuService


class ChatService:
    def __init__(
        self,
        menu_service: MenuService,
        llm_service: LLMService,
        cart_service: CartService,
    ):
        self.menu = menu_service
        self.llm = llm_service
        self.cart = cart_service

    def process_message(self, state: SessionState, user_input: str) -> str:
        response_buffer = []
        items_added_this_turn = []

        if state.pending_items:
            item = state.pending_items[0]

            meta = self.menu.get_item(item.name)
            resolved = False
            if meta:
                for prop_name, valid_values in meta.properties.items():
                    if prop_name not in item.properties:
                        if user_input.lower().strip(".,!?") in [v.lower() for v in valid_values]:
                            item.properties[prop_name] = user_input.lower().strip(".,!?")
                            resolved = True
                            break

            is_valid, error_msg = self.cart.validate_item(item)
            if is_valid:
                self.cart.add_item(state.order, item)
                items_added_this_turn.append(item)
                state.pending_items.pop(0)
                response_buffer.append(f"Added {item.name}.")
            elif resolved:
                pass
            else:
                exact_match = self.menu.get_item(user_input.title())
                if not exact_match:
                    context = (
                        f"Previous Question: {state.last_system_message}. Current Order: "
                        + "; ".join([str(i) for i in state.order.items])
                    )
                    llm_result = self.llm.parse_intent(
                        user_input, self.menu.menu, context
                    )
                    
                    if llm_result.success:
                        if llm_result.intent.cancel_pending:
                            state.pending_items.pop(0)
                            response_buffer.append("Cancelled.")
                            exact_match = None 
                        elif llm_result.intent.ordered_items:
                            found_name = llm_result.intent.ordered_items[0].name
                            exact_match = self.menu.get_item(found_name)

                if exact_match:
                    added_to_slot = False
                    if meta and meta.slots:
                        for slot_name, slot_def in meta.slots.items():
                            if exact_match.name in slot_def.options:
                                item.components.append(
                                    OrderComponent(
                                        name=exact_match.name, slot=slot_name
                                    )
                                )
                                added_to_slot = True
                                break
                    
                    added_to_deal = False
                    if not added_to_slot and meta and meta.is_deal and meta.possible_items:
                        if exact_match.name in meta.possible_items:
                            item.components.append(OrderComponent(name=exact_match.name))
                            added_to_deal = True

                    if added_to_slot or added_to_deal:
                        is_valid, error_msg = self.cart.validate_item(item)
                        if is_valid:
                            self.cart.add_item(state.order, item)
                            items_added_this_turn.append(item)
                            state.pending_items.pop(0)
                            if added_to_slot:
                                response_buffer.append(f"Added {item.name} with {exact_match.name}.")
                            else:
                                response_buffer.append(f"Added {item.name}.")
                        else:
                            state.last_system_message = error_msg
                            return f"{error_msg}"

                    elif not exact_match.virtual:
                        item.name = exact_match.name
                        is_valid, error_msg = self.cart.validate_item(item)
                        if is_valid:
                            self.cart.add_item(state.order, item)
                            items_added_this_turn.append(item)
                            state.pending_items.pop(0)
                            response_buffer.append(f"Added {item.name}.")
                        else:
                            state.last_system_message = error_msg
                            return f"{error_msg}"
                else:
                    pass

        if not response_buffer and not state.pending_items:
            context = (
                f"Previous Question: {state.last_system_message}. Current Order: "
                + "; ".join([str(i) for i in state.order.items])
            )
            llm_result = self.llm.parse_intent(user_input, self.menu.menu, context)
            if (
                not llm_result.success
                or not llm_result.intent
                or (
                    not llm_result.intent.ordered_items
                    and not llm_result.intent.end_order
                )
            ):
                reply = self.llm.generate_reply(
                    user_input, 
                    self.menu.menu, 
                    context, 
                    has_upsell=bool(state.upsell_queue)
                )
                reply = f"[LLM] {reply}"

                if state.upsell_queue:
                    next_upsell = state.upsell_queue.pop(0)

                    final_msg = f"{reply} {next_upsell}"
                    state.last_system_message = final_msg
                    return final_msg

                state.last_system_message = reply
                return reply

            intent = llm_result.intent
            if intent.end_order:
                total = self.cart.calculate_total(state.order)
                order_summary = ", ".join([str(i) for i in state.order.items])
                msg = f"Order completed. Your order: {order_summary}. Amount due: ${total:.2f}. Thank you!"
                state.last_system_message = msg
                return msg

            state.pending_items.extend(intent.ordered_items)
            self._check_and_apply_deals(state)

        while state.pending_items:
            item = state.pending_items[0]
            is_valid, error_msg = self.cart.validate_item(item)

            if is_valid:
                self.cart.add_item(state.order, item)
                items_added_this_turn.append(item)
                response_buffer.append(f"Added {item.name}.")
                state.pending_items.pop(0)
            else:
                msg = " ".join(response_buffer)
                if msg:
                    msg += " "
                final_msg = f"{msg}{error_msg}"
                state.last_system_message = final_msg
                return final_msg

        if items_added_this_turn:
            new_upsells = self._get_upsells(state, items_added_this_turn)

            for u in new_upsells:
                if u not in state.upsell_queue:
                    state.upsell_queue.append(u)

        base_msg = " ".join(response_buffer)

        if state.upsell_queue:
            next_upsell = state.upsell_queue.pop(0)
            if base_msg:
                final_msg = f"{base_msg} {next_upsell}"
            else:
                final_msg = next_upsell
        else:
            total = self.cart.calculate_total(state.order)
            if base_msg:
                final_msg = f"{base_msg} (Total: ${total:.2f}). Anything else?"
            else:
                final_msg = f"Current order total: ${total:.2f}. Anything else?"

        state.last_system_message = final_msg
        return final_msg

    def _check_and_apply_deals(self, state: SessionState) -> None:
        deals = [
            item
            for item in self.menu.menu.items.values()
            if item.is_deal and item.possible_items
        ]
        if not deals:
            return

        flat_pending = []
        for item in state.pending_items:
            if item.quantity > 1:
                for _ in range(item.quantity):
                    new_item = item.model_copy(deep=True)
                    new_item.quantity = 1
                    flat_pending.append(new_item)
            else:
                flat_pending.append(item)

        pending = flat_pending
        new_pending = []
        used_indices = set()

        for i in range(len(pending)):
            if i in used_indices:
                continue

            item_a = pending[i]
            
            potential_deals = [d for d in deals if item_a.name in d.possible_items]
            
            matched_deal = None
            match_index = -1

            if potential_deals:
                for j in range(i + 1, len(pending)):
                    if j in used_indices:
                        continue
                    item_b = pending[j]
                    
                    valid_deals = [
                        d for d in potential_deals 
                        if item_b.name in d.possible_items
                    ]
                    
                    if valid_deals:
                        matched_deal = valid_deals[0]
                        match_index = j
                        break
            
            if matched_deal and match_index != -1:
                item_b = pending[match_index]
                
                comp_a = OrderComponent(
                    name=item_a.name,
                    properties=item_a.properties,
                    add_ingredients=item_a.add_ingredients,
                    remove_ingredients=item_a.remove_ingredients
                )
                comp_b = OrderComponent(
                    name=item_b.name,
                    properties=item_b.properties,
                    add_ingredients=item_b.add_ingredients,
                    remove_ingredients=item_b.remove_ingredients
                )

                deal_item = OrderItem(
                    name=matched_deal.name,
                    kind=ItemType.DOUBLE_DEAL,
                    quantity=1,
                    components=[comp_a, comp_b]
                )
                
                new_pending.append(deal_item)
                used_indices.add(i)
                used_indices.add(match_index)
            else:
                new_pending.append(item_a)
                used_indices.add(i)
        
        state.pending_items = new_pending

    def _get_upsells(
        self, state: SessionState, new_items: list[OrderItem]
    ) -> list[str]:
        messages = []
        has_dessert = any(
            self.menu.get_item(i.name)
            and self.menu.get_item(i.name).category == "desserts"
            for i in state.order.items
        )
        offered_dessert = False

        for item in new_items:
            meta = self.menu.get_item(item.name)
            if not meta:
                continue

            if meta.category == "burgers" and not meta.slots:
                meal_name = f"{item.name} Meal"
                meal_meta = self.menu.get_item(meal_name)
                if meal_meta:
                    messages.append(
                        f"Would you like to make that {item.name} a meal for just ${meal_meta.price}?"
                    )

            if meta.slots:
                messages.append("Would you like to add a dipping sauce?")

            is_main = meta.category == "burgers" or meta.slots
            if is_main and not has_dessert and not offered_dessert:
                messages.append("Would you like a dessert with that?")
                offered_dessert = True

        return messages
