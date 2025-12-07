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

        summary = "; ".join([i.describe() for i in state.order.items])

        llm_result = self.llm.parse_intent(user_input, self.menu.menu, summary)

        if not llm_result.success or not llm_result.intent:

            return self.llm.generate_reply(user_input, self.menu.menu, summary)

        intent = llm_result.intent
        response_buffer = []

        if intent.end_order:
            total = self.cart.calculate_total(state.order)
            return f"Order completed. Amount due: ${total:.2f}. Thank you!"

        for item in intent.ordered_items:

            is_valid, error_msg = self.cart.validate_item(item)

            if is_valid:
                self.cart.add_item(state.order, item)
                response_buffer.append(f"Added {item.name}.")
            else:

                return f"{error_msg}"

        if not response_buffer:

            return self.llm.generate_reply(user_input, self.menu.menu, summary)

        total = self.cart.calculate_total(state.order)
        return " ".join(response_buffer) + f" (Total: ${total:.2f}). Anything else?"
