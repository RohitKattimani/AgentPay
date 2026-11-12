"""Executes the CSV-cleaning service and stores its output artifact."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from database.models import AgentEvent, SessionLocal, Task, TaskExecution
from services.csv_pipeline import clean_csv
from config import settings

logger = logging.getLogger("agentpay.seller")


class SellerAgent:
    name = "Seller Agent"

    async def execute_task(
        self,
        task_id: int,
        seller_name: str,
        csv_file_path: str,
        deliverables: list[str],
        acceptance_criteria: list[str],
    ) -> dict:
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise ValueError(f"Task {task_id} not found.")
            if not csv_file_path or not Path(csv_file_path).is_file():
                raise FileNotFoundError("The source CSV file is missing.")

            existing = db.query(TaskExecution).filter(TaskExecution.task_id == task_id).first()
            if existing and existing.status == "completed" and existing.output_file_path:
                output = Path(existing.output_file_path)
                if output.is_file():
                    return {
                        "execution_id": existing.id,
                        "task_id": task_id,
                        "seller_name": existing.seller_name,
                        "output_file_path": str(output),
                        "processing_report": json.loads(existing.processing_report or "{}"),
                        "reused": True,
                    }

            execution = existing or TaskExecution(task_id=task_id, seller_name=seller_name)
            execution.seller_name = seller_name
            execution.status = "in_progress"
            execution.started_at = datetime.now(timezone.utc)
            db.add(execution)
            db.commit()
            db.refresh(execution)
            self._log_event(db, task_id, "seller_started", {"seller": seller_name})

            cleaned_frame, report = clean_csv(csv_file_path)
            output_filename = f"task_{task_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}_cleaned.csv"
            output_path = settings.UPLOAD_DIR / output_filename
            cleaned_frame.to_csv(output_path, index=False)

            execution.output_file_path = str(output_path)
            execution.processing_report = json.dumps(report)
            execution.status = "completed"
            execution.completed_at = datetime.now(timezone.utc)
            db.add(
                AgentEvent(
                    task_id=task_id,
                    agent_name=self.name,
                    event_type="seller_completed",
                    event_data=json.dumps({"output_file": output_filename, "report": report}),
                )
            )
            db.commit()
            return {
                "execution_id": execution.id,
                "task_id": task_id,
                "seller_name": seller_name,
                "output_file_path": str(output_path),
                "processing_report": report,
                "reused": False,
            }
        except Exception:
            db.rollback()
            logger.exception("Seller Agent failed for task %s", task_id)
            raise
        finally:
            db.close()

    @staticmethod
    def _log_event(db, task_id: int, event_type: str, data: dict) -> None:
        db.add(
            AgentEvent(
                task_id=task_id,
                agent_name=SellerAgent.name,
                event_type=event_type,
                event_data=json.dumps(data),
            )
        )
        db.commit()


seller_agent = SellerAgent()
