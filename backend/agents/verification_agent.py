"""Independently checks a seller's output before funds can be released."""

import json
import logging
from pathlib import Path

from config import settings
from database.models import (
    AgentEvent,
    SessionLocal,
    VerificationReport,
    VerificationStatus,
)
from services.csv_pipeline import verify_csv

logger = logging.getLogger("agentpay.verification")


class VerificationAgent:
    name = "Independent Verification Agent"

    async def verify_deliverable(
        self,
        task_id: int,
        original_file_path: str,
        cleaned_file_path: str,
        acceptance_criteria: list[str],
        revision_count: int = 0,
    ) -> dict:
        db = SessionLocal()
        try:
            if not original_file_path or not Path(original_file_path).is_file():
                raise FileNotFoundError("The original CSV file is missing.")
            if not cleaned_file_path or not Path(cleaned_file_path).is_file():
                raise FileNotFoundError("The seller's cleaned CSV file is missing.")

            checks = verify_csv(cleaned_file_path)
            failed_checks = [name for name, value in checks.items() if value > 0]
            if not failed_checks:
                status = VerificationStatus.PASS
                report_text = "All automated data-quality checks passed."
            elif revision_count >= 2:
                status = VerificationStatus.MANUAL_REVIEW
                report_text = (
                    "The deliverable still contains unresolved data-quality issues: "
                    + ", ".join(failed_checks)
                    + ". Manual review is required."
                )
            else:
                status = VerificationStatus.FAIL
                report_text = (
                    "Verification found unresolved data-quality issues: "
                    + ", ".join(failed_checks)
                    + ". Payment will not be released."
                )

            report = db.query(VerificationReport).filter(
                VerificationReport.task_id == task_id
            ).first()
            if report is None:
                report = VerificationReport(task_id=task_id)
            report.missing_values = checks["missing_values"]
            report.duplicate_records = checks["duplicate_records"]
            report.invalid_emails = checks["invalid_emails"]
            report.formatting_errors = checks["formatting_errors"]
            report.verification_status = status
            report.report_text = report_text
            report.revision_count = revision_count
            db.add(report)
            db.add(
                AgentEvent(
                    task_id=task_id,
                    agent_name=self.name,
                    event_type="verification_completed",
                    event_data=json.dumps({"status": status.value, **checks}),
                )
            )
            db.commit()
            db.refresh(report)
            return {
                "verification_id": report.id,
                "task_id": task_id,
                **checks,
                "verification_status": status.value,
                "report": report_text,
            }
        except Exception:
            db.rollback()
            logger.exception("Verification failed for task %s", task_id)
            raise
        finally:
            db.close()


verification_agent = VerificationAgent()
