"""Orchestrates the AgentPay transaction lifecycle."""

import json
import logging

from agents.buyer_agent import buyer_agent
from agents.contract_agent import contract_agent
from agents.negotiation_agent import negotiation_agent
from agents.payment_agent import payment_agent
from agents.seller_agent import seller_agent
from agents.verification_agent import verification_agent
from database.models import (
    AgentEvent,
    Contract,
    ContractStatus,
    Payment,
    PaymentStatus,
    SessionLocal,
    Task,
    TaskExecution,
    TaskStatus,
    VerificationReport,
    VerificationStatus,
)

logger = logging.getLogger("agentpay.orchestration")


class AgentPayGraph:
    """Coordinates bidding, contract approval, execution, verification, and settlement."""

    async def run(
        self, task_id: int, task_description: str, csv_file_path: str, user_id: int
    ) -> dict:
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise ValueError(f"Task {task_id} not found.")
            if not csv_file_path:
                raise ValueError("Upload a CSV file before starting the task.")
            if not task.csv_file_path:
                raise ValueError("This task does not have a source CSV file.")

            existing_contract = db.query(Contract).filter(Contract.task_id == task_id).first()
            if existing_contract:
                if task.status == TaskStatus.COMPLETED:
                    return self._completed_result(db, task_id)
                return self._pending_workflow_result(db, task, existing_contract)
            if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                raise ValueError(f"A task in {task.status.value} state cannot be started.")

            task.status = TaskStatus.IN_PROGRESS
            db.commit()

            buyer_result = buyer_agent.decompose_task(
                task_description=task_description,
                user_id=user_id,
                csv_file_path=csv_file_path,
                existing_task_id=task_id,
            )
            decomposition = buyer_result["decomposition"]
            negotiation_result = negotiation_agent.start_negotiation(
                task_id=task_id,
                task_description=task_description,
                budget=decomposition["budget"],
                deadline_minutes=decomposition["deadline_minutes"],
            )
            if not negotiation_result.get("winning_seller"):
                raise ValueError("No eligible seller bid was received.")

            contract_result = contract_agent.generate_contract(
                task_id=task_id,
                seller_name=negotiation_result["winning_seller"],
                agreed_price=negotiation_result["winning_price"],
                deadline_minutes=negotiation_result["delivery_minutes"],
                deliverables=decomposition["deliverables"],
                acceptance_criteria=decomposition["acceptance_criteria"],
            )
            return {
                "task_id": task_id,
                "status": "pending_approval",
                "buyer_result": buyer_result,
                "negotiation_result": negotiation_result,
                "contract_result": contract_result,
            }
        except Exception as exc:
            db.rollback()
            task = db.query(Task).filter(Task.id == task_id).first()
            if task and task.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                task.status = TaskStatus.FAILED
                db.commit()
            logger.exception("Workflow setup failed for task %s", task_id)
            raise exc
        finally:
            db.close()

    async def approve_contract(self, task_id: int) -> dict:
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            contract = db.query(Contract).filter(Contract.task_id == task_id).first()
            if not task or not contract:
                raise ValueError("Task or contract not found.")
            if contract.status == ContractStatus.REJECTED:
                raise ValueError("This contract has been rejected.")
            if contract.status == ContractStatus.PENDING_APPROVAL:
                contract.status = ContractStatus.APPROVED
                contract.buyer_approved = True
                task.status = TaskStatus.IN_PROGRESS
                db.add(
                    AgentEvent(
                        task_id=task_id,
                        agent_name="Contract Agent",
                        event_type="contract_approved",
                        event_data=json.dumps({"contract_id": contract.id}),
                    )
                )
                db.commit()
            elif contract.status not in (ContractStatus.APPROVED, ContractStatus.COMPLETED):
                raise ValueError(f"Contract cannot be approved from {contract.status.value} state.")
            agreed_price = contract.agreed_price
            if task.status == TaskStatus.COMPLETED:
                return self._completed_result(db, task_id)
        finally:
            db.close()

        authorization = await payment_agent.authorize_payment(
            task_id=task_id,
            amount=agreed_price,
            idempotency_key=f"ap-task-{task_id}-auth",
        )
        if authorization["status"] == PaymentStatus.AWAITING_APPROVAL.value:
            return {
                "task_id": task_id,
                "status": "awaiting_payment_approval",
                "contract_approved": True,
                "payment": authorization,
                "approval_url": authorization.get("approval_url"),
                "message": "Approve the PayPal order to begin execution.",
            }
        return await self.execute_after_authorization(task_id)

    async def execute_after_authorization(self, task_id: int) -> dict:
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            contract = db.query(Contract).filter(Contract.task_id == task_id).first()
            payment = db.query(Payment).filter(Payment.task_id == task_id).first()
            if not task or not contract or not payment:
                raise ValueError("Task, contract, or payment record not found.")
            if task.status == TaskStatus.COMPLETED:
                return self._completed_result(db, task_id)
            if contract.status not in (ContractStatus.APPROVED, ContractStatus.COMPLETED):
                raise ValueError("The buyer must approve the contract before execution.")
            if payment.status == PaymentStatus.CAPTURED:
                return self._completed_result(db, task_id)
            if payment.status != PaymentStatus.AUTHORIZED:
                raise ValueError("Payment must be authorized before seller execution.")
            if not task.csv_file_path:
                raise ValueError("The source CSV file is missing.")
            deliverables = json.loads(contract.deliverables or "[]")
            criteria = json.loads(contract.acceptance_criteria or "[]")
            seller_name = contract.seller_name
            source_path = task.csv_file_path
        finally:
            db.close()

        try:
            seller_result = await seller_agent.execute_task(
                task_id=task_id,
                seller_name=seller_name,
                csv_file_path=source_path,
                deliverables=deliverables,
                acceptance_criteria=criteria,
            )
            verification_result = await verification_agent.verify_deliverable(
                task_id=task_id,
                original_file_path=source_path,
                cleaned_file_path=seller_result["output_file_path"],
                acceptance_criteria=criteria,
                revision_count=0,
            )
            if verification_result["verification_status"] == VerificationStatus.PASS.value:
                capture_result = await payment_agent.capture_payment(task_id)
                final_status = TaskStatus.COMPLETED
                payment_captured = True
            else:
                capture_result = payment_agent.hold_payment(
                    task_id,
                    reason=verification_result["report"],
                )
                final_status = TaskStatus.FAILED
                payment_captured = False

            db = SessionLocal()
            try:
                task = db.query(Task).filter(Task.id == task_id).first()
                contract = db.query(Contract).filter(Contract.task_id == task_id).first()
                task.status = final_status
                if final_status == TaskStatus.COMPLETED:
                    contract.status = ContractStatus.COMPLETED
                db.add(
                    AgentEvent(
                        task_id=task_id,
                        agent_name="AgentPay Orchestrator",
                        event_type="workflow_completed" if payment_captured else "workflow_failed_verification",
                        event_data=json.dumps(
                            {"status": final_status.value, "payment_captured": payment_captured}
                        ),
                    )
                )
                db.commit()
            finally:
                db.close()

            return {
                "task_id": task_id,
                "status": final_status.value,
                "contract_approved": True,
                "seller_result": seller_result,
                "verification_result": verification_result,
                "payment_result": capture_result,
                "payment_captured": payment_captured,
            }
        except Exception:
            db = SessionLocal()
            try:
                task = db.query(Task).filter(Task.id == task_id).first()
                if task and task.status != TaskStatus.COMPLETED:
                    task.status = TaskStatus.FAILED
                    db.commit()
            finally:
                db.close()
            logger.exception("Execution failed for task %s", task_id)
            raise

    async def reject_contract(self, task_id: int) -> dict:
        db = SessionLocal()
        try:
            contract = db.query(Contract).filter(Contract.task_id == task_id).first()
            task = db.query(Task).filter(Task.id == task_id).first()
            if not contract or not task:
                raise ValueError("Task or contract not found.")
            if contract.status != ContractStatus.PENDING_APPROVAL:
                raise ValueError("Only a contract awaiting approval can be rejected.")
            contract.status = ContractStatus.REJECTED
            task.status = TaskStatus.CANCELLED
            db.add(
                AgentEvent(
                    task_id=task_id,
                    agent_name="Contract Agent",
                    event_type="contract_rejected",
                    event_data=json.dumps({"contract_id": contract.id}),
                )
            )
            db.commit()
            return {"task_id": task_id, "status": "rejected"}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _pending_workflow_result(db, task, contract) -> dict:
        return {
            "task_id": task.id,
            "status": "pending_approval" if contract.status == ContractStatus.PENDING_APPROVAL else task.status.value,
            "contract_result": {
                "contract_id": contract.id,
                "seller_name": contract.seller_name,
                "agreed_price": contract.agreed_price,
                "deadline_minutes": contract.deadline_minutes,
                "status": contract.status.value,
                "buyer_approved": contract.buyer_approved,
            },
        }

    @staticmethod
    def _completed_result(db, task_id: int) -> dict:
        verification = db.query(VerificationReport).filter(
            VerificationReport.task_id == task_id
        ).first()
        payment = db.query(Payment).filter(Payment.task_id == task_id).first()
        execution = db.query(TaskExecution).filter(TaskExecution.task_id == task_id).first()
        return {
            "task_id": task_id,
            "status": "completed",
            "contract_approved": True,
            "seller_result": {
                "output_file_path": execution.output_file_path if execution else None,
                "processing_report": json.loads(execution.processing_report or "{}") if execution else {},
            } if execution else None,
            "verification_result": {
                "verification_status": verification.verification_status.value,
                "report": verification.report_text,
            } if verification else None,
            "payment_captured": bool(payment and payment.status == PaymentStatus.CAPTURED),
            "payment_result": payment_agent._serialize(payment, duplicate=True) if payment else None,
        }


agentpay_graph = AgentPayGraph()
