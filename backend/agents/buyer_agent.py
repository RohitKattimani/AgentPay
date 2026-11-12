"""Turns a buyer's CSV request into an explicit, budget-bounded work order."""

import json
import logging
from typing import Any, Dict

from config import settings
from database.models import AgentEvent, SessionLocal, Task

logger = logging.getLogger("agentpay.buyer")


class BuyerAgent:
    name = "Buyer Agent"

    def decompose_task(
        self,
        task_description: str,
        user_id: int,
        csv_file_path: str | None = None,
        existing_task_id: int | None = None,
    ) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == existing_task_id).first()
            if task is None:
                raise ValueError("The task could not be found.")

            budget = round(min(float(task.budget), settings.MAX_BUDGET), 2)
            decomposition = {
                "task_name": "CSV Data Cleaning",
                "deliverables": [
                    "A cleaned CSV file with standardized column names and whitespace",
                    "Duplicate records removed without modifying customer values",
                    "A processing report describing changes and unresolved data-quality issues",
                ],
                "budget": budget,
                "currency": "USD",
                "deadline_minutes": max(1, int(task.deadline_minutes or 5)),
                "acceptance_criteria": [
                    "The output is a readable CSV file with at least one data row",
                    "No duplicate records remain",
                    "No missing values remain",
                    "Email fields contain valid email addresses",
                    "Column names and text values are consistently formatted",
                ],
            }

            task.title = decomposition["task_name"]
            task.description = task_description.strip()
            task.budget = budget
            task.currency = "USD"
            task.deliverables = json.dumps(decomposition["deliverables"])
            task.acceptance_criteria = json.dumps(decomposition["acceptance_criteria"])
            if csv_file_path:
                task.csv_file_path = csv_file_path

            db.add(
                AgentEvent(
                    task_id=task.id,
                    agent_name=self.name,
                    event_type="buyer_decomposition_complete",
                    event_data=json.dumps(decomposition),
                )
            )
            db.commit()
            return {"task_id": task.id, "decomposition": decomposition}
        except Exception:
            db.rollback()
            logger.exception("Buyer Agent failed for task %s", existing_task_id)
            raise
        finally:
            db.close()


buyer_agent = BuyerAgent()
