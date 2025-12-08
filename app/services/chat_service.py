from app.schemas import SessionState, OrderItem
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
        if state.pending_items:
            item = state.pending_items[0]
            
            meta = self.menu.get_item(item.name)
            resolved = False
            if meta:
                for prop_name, valid_values in meta.properties.items():
                    if prop_name not in item.properties:
                        if user_input.lower() in [v.lower() for v in valid_values]:
                            item.properties[prop_name] = user_input.lower()
                            resolved = True
                            break
                 
            is_valid, error_msg = self.cart.validate_item(item)
            if is_valid:
                self.cart.add_item(state.order, item)
                state.pending_items.pop(0) 
                response_buffer.append(f"Added {item.name}.")
            elif resolved: 
                return f"{error_msg}"
            else:
                exact_match = self.menu.get_item(user_input.title()) 
                if not exact_match:
                    llm_result = self.llm.parse_intent(user_input, self.menu.menu)
                    if llm_result.success and llm_result.intent.ordered_items:
                        found_name = llm_result.intent.ordered_items[0].name
                        exact_match = self.menu.get_item(found_name)

                if exact_match and not exact_match.virtual:
                    item.name = exact_match.name
                    item.components = [] 
                    is_valid, error_msg = self.cart.validate_item(item)
                    if is_valid:
                        self.cart.add_item(state.order, item)
                        state.pending_items.pop(0)
                        response_buffer.append(f"Added {item.name}.")
                    else:
                        return f"{error_msg}"
                else:
                    pass

        if not response_buffer and not state.pending_items:
            summary = "; ".join([str(i) for i in state.order.items])
            llm_result = self.llm.parse_intent(user_input, self.menu.menu, summary)

            if not llm_result.success or not llm_result.intent:
                return self.llm.generate_reply(user_input, self.menu.menu, summary)

            intent = llm_result.intent
            if intent.end_order:
                total = self.cart.calculate_total(state.order)
                order_summary = ", ".join([str(i) for i in state.order.items])
                return f"Order completed. Your order: {order_summary}. Amount due: ${total:.2f}. Thank you!"
            
            state.pending_items.extend(intent.ordered_items)

        while state.pending_items:
            item = state.pending_items[0]
            is_valid, error_msg = self.cart.validate_item(item)
            
            if is_valid:
                self.cart.add_item(state.order, item)
                response_buffer.append(f"Added {item.name}.")
                state.pending_items.pop(0)
            else:        
                msg = " ".join(response_buffer)
                if msg: msg += " "
                return f"{msg}{error_msg}"

        if not response_buffer:
             return self.llm.generate_reply(user_input, self.menu.menu, "; ".join([str(i) for i in state.order.items]))

        total = self.cart.calculate_total(state.order)
        return " ".join(response_buffer) + f" (Total: ${total:.2f}). Anything else?"
