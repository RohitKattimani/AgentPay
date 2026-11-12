"""Creates a deterministic agreement from the selected bid and buyer work order."""

import json
import logging
from typing import Any, Dict, List

from config import settings
from database.models import AgentEvent, Contract, ContractStatus, SessionLocal, Task

logger = logging.getLogger("agentpay.contract")


class ContractAgent:
    name = "Contract Agent"

    def generate_contract(
        self,
        task_id: int,
        seller_name: str,
        agreed_price: float,
        deadline_minutes: int,
        deliverables: List[str],
        acceptance_criteria: List[str],
    ) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise ValueError("Task not found.")
            if agreed_price <= 0 or agreed_price > min(task.budget, settings.MAX_BUDGET):
                raise ValueError("The selected bid exceeds the approved task budget.")

            contract = db.query(Contract).filter(Contract.task_id == task_id).first()
            if contract is None:
                contract = Contract(task_id=task_id)
            contract.seller_name = seller_name
            contract.agreed_price = round(float(agreed_price), 2)
            contract.deadline_minutes = max(1, int(deadline_minutes))
            contract.deliverables = json.dumps(deliverables)
            contract.acceptance_criteria = json.dumps(acceptance_criteria)
            contract.revision_policy = (
                "Failed automated checks are held for buyer or manual review. "
                "Values are never fabricated or silently inferred."
            )
            contract.payment_conditions = (
                "Payment is authorized after buyer approval and captured only when independent verification passes."
            )
            contract.status = ContractStatus.PENDING_APPROVAL
            contract.buyer_approved = False
            db.add(contract)
            db.flush()
            db.add(
                AgentEvent(
                    task_id=task_id,
                    agent_name=self.name,
                    event_type="contract_generated",
                    event_data=json.dumps(
                        {"contract_id": contract.id, "seller": seller_name, "price": agreed_price}
                    ),
                )
            )
            db.commit()
            db.refresh(contract)
            return {
                "contract_id": contract.id,
                "task_id": task_id,
                "seller_name": contract.seller_name,
                "agreed_price": contract.agreed_price,
                "deadline_minutes": contract.deadline_minutes,
                "status": contract.status.value,
                "buyer_approved": contract.buyer_approved,
            }
        except Exception:
            db.rollback()
            logger.exception("Contract generation failed for task %s", task_id)
            raise
        finally:
            db.close()


contract_agent = ContractAgent()
