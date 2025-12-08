from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum

class ItemType(str, Enum):
    ITEM = "item"
    COMBO = "combo"
    DOUBLE_DEAL = "double_deal"


class Ingredient(BaseModel):
    name: str
    price: float = 0.0


class ComboSlot(BaseModel):
    name: str                   # e.g. fries, drinks, sauces
    options: List[str]          # possible item names for this slot
    optional: bool = False      # is this slot optional?


class MenuItem(BaseModel):
    name: str
    category: Optional[str] = None                                   # e.g. burgers, fries, desserts
    price: Optional[float] = None
    properties: Dict[str, List[str]] = Field(default_factory=dict)  # e.g. size: [small, medium, large]
    default_ingredients: List[str] = Field(default_factory=list)    # ingredients included by default
    possible_ingredients: List[str] = Field(default_factory=list)   # ingredients that can be added/removed
    virtual: bool = False
    possible_items: List[str] = Field(default_factory=list)         # for virtuals / double deals

    slots: Dict[str, ComboSlot] = Field(default_factory=dict)       # for additional combo components (e.g. fries, drinks)
    discount: float = 0.0                                           # for deals
    is_deal: bool = False


class Menu(BaseModel):
    items: Dict[str, MenuItem] = Field(default_factory=dict)
    ingredients: Dict[str, Ingredient] = Field(default_factory=dict)


class OrderComponent(BaseModel):
    name: str
    slot: Optional[str] = None
    properties: Dict[str, str] = Field(default_factory=dict)
    add_ingredients: List[str] = Field(default_factory=list)
    remove_ingredients: List[str] = Field(default_factory=list)


class OrderItem(BaseModel):
    name: str
    kind: ItemType = ItemType.ITEM
    quantity: int = 1
    properties: Dict[str, str] = Field(default_factory=dict)              # e.g. size: large
    components: List[OrderComponent] = Field(default_factory=list)        # for combos/deals
    add_ingredients: List[str] = Field(default_factory=list)
    remove_ingredients: List[str] = Field(default_factory=list)

    def describe(self) -> str:
        parts = [self.name]
        for comp in self.components:
            parts.append(f"[{comp.slot or 'incl'}: {comp.name}]")
        return f"{self.quantity}x {' '.join(parts)}"


class Order(BaseModel):
    items: List[OrderItem] = Field(default_factory=list)


class SessionState(BaseModel):
    order: Order = Field(default_factory=Order)

    pending_item: Optional[OrderItem] = None
    pending_clarification: Optional[str] = None
    last_system_message: str = ""


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatReply(BaseModel):
    message: str
    order_complete: bool
    used_llm_fallback: bool
    order_summary: List[str]
    total: float
