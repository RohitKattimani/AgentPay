"""Collects registered demo bids and selects a seller using fixed scoring rules."""

import json
import logging
from typing import Any, Dict

from config import settings
from database.models import AgentEvent, Bid, Negotiation, SessionLocal

logger = logging.getLogger("agentpay.negotiation")

PRICE_WEIGHT = 0.50
DELIVERY_WEIGHT = 0.25
REPUTATION_WEIGHT = 0.25

# Seed sellers make the application reproducible without requiring external vendors.
REGISTERED_SELLERS = [
    {"name": "Seller Alpha", "price": 4.20, "delivery_minutes": 2, "rating": 4.9},
    {"name": "Seller Beta", "price": 3.80, "delivery_minutes": 4, "rating": 4.7},
    {"name": "Seller Gamma", "price": 4.50, "delivery_minutes": 1, "rating": 4.8},
]


class NegotiationAgent:
    name = "Negotiation Agent"

    @staticmethod
    def calculate_score(price: float, delivery_minutes: int, rating: float, budget: float) -> float:
        if budget <= 0:
            return 0.0
        price_score = max(0.0, (budget - price) / budget) * 100
        fastest_reference = max(seller["delivery_minutes"] for seller in REGISTERED_SELLERS)
        delivery_score = max(
            0.0, (fastest_reference - delivery_minutes) / fastest_reference
        ) * 100
        reputation_score = min(max(rating, 0.0), 5.0) * 20
        score = (
            price_score * PRICE_WEIGHT
            + delivery_score * DELIVERY_WEIGHT
            + reputation_score * REPUTATION_WEIGHT
        )
        return round(score, 2)

    def start_negotiation(
        self, task_id: int, task_description: str, budget: float, deadline_minutes: int
    ) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            existing = db.query(Negotiation).filter(Negotiation.task_id == task_id).first()
            if existing:
                return self._serialize_negotiation(db, existing)

            negotiation = Negotiation(task_id=task_id, status="in_progress")
            db.add(negotiation)
            db.flush()

            eligible = [
                seller for seller in REGISTERED_SELLERS
                if seller["price"] <= min(budget, settings.MAX_BUDGET)
                and seller["delivery_minutes"] <= deadline_minutes
            ]
            if not eligible:
                raise ValueError("No registered seller can meet the task budget and deadline.")

            bid_records = []
            for seller in eligible:
                score = self.calculate_score(
                    seller["price"], seller["delivery_minutes"], seller["rating"], budget
                )
                bid = Bid(
                    negotiation_id=negotiation.id,
                    seller_name=seller["name"],
                    price=seller["price"],
                    delivery_minutes=seller["delivery_minutes"],
                    rating=seller["rating"],
                    score=score,
                )
                db.add(bid)
                bid_records.append(bid)

            db.flush()
            # Stable tie-breaking keeps repeated demo runs predictable.
            winner = max(
                bid_records,
                key=lambda bid: (bid.score or 0, bid.rating, -bid.price, bid.seller_name),
            )
            winner.is_winner = True
            negotiation.winning_bid_id = winner.id
            negotiation.selection_explanation = (
                "Selected using a weighted score: price 50%, delivery time 25%, "
                "and seller rating 25%. Only bids within the buyer's budget and deadline were considered."
            )
            negotiation.status = "completed"

            event_data = {
                "bid_count": len(bid_records),
                "winning_seller": winner.seller_name,
                "winning_price": winner.price,
            }
            db.add(
                AgentEvent(
                    task_id=task_id,
                    agent_name=self.name,
                    event_type="negotiation_completed",
                    event_data=json.dumps(event_data),
                )
            )
            db.commit()
            db.refresh(negotiation)
            return self._serialize_negotiation(db, negotiation)
        except Exception:
            db.rollback()
            logger.exception("Negotiation failed for task %s", task_id)
            raise
        finally:
            db.close()

    def _serialize_negotiation(self, db, negotiation: Negotiation) -> Dict[str, Any]:
        bids = db.query(Bid).filter(Bid.negotiation_id == negotiation.id).all()
        winner = next((bid for bid in bids if bid.is_winner), None)
        return {
            "negotiation_id": negotiation.id,
            "winning_seller": winner.seller_name if winner else None,
            "winning_price": winner.price if winner else None,
            "delivery_minutes": winner.delivery_minutes if winner else None,
            "score": winner.score if winner else None,
            "explanation": negotiation.selection_explanation or "",
            "all_bids": [
                {
                    "id": bid.id,
                    "seller_name": bid.seller_name,
                    "price": bid.price,
                    "delivery_minutes": bid.delivery_minutes,
                    "rating": bid.rating,
                    "score": bid.score,
                    "is_winner": bid.is_winner,
                }
                for bid in bids
            ],
        }


negotiation_agent = NegotiationAgent()
