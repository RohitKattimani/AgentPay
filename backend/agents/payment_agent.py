"""Controls payment authorization, verification-gated capture, and payment holds."""

import json
import logging
from datetime import datetime, timezone

from config import settings
from database.models import (
    AgentEvent,
    Contract,
    ContractStatus,
    Payment,
    PaymentStatus,
    SessionLocal,
    VerificationReport,
    VerificationStatus,
)
from services.paypal_service import paypal_service

logger = logging.getLogger("agentpay.payment")


class PaymentAgent:
    name = "PayPal Payment Agent"

    @property
    def mock_mode(self) -> bool:
        return paypal_service.mock_mode

    async def authorize_payment(self, task_id: int, amount: float, idempotency_key: str | None = None) -> dict:
        db = SessionLocal()
        try:
            contract = db.query(Contract).filter(Contract.task_id == task_id).first()
            if (
                not contract
                or contract.status not in (ContractStatus.APPROVED, ContractStatus.COMPLETED)
                or not contract.buyer_approved
                or round(contract.agreed_price, 2) != round(amount, 2)
            ):
                raise ValueError("Payment amount must match the approved contract.")
            if amount <= 0 or amount > settings.MAX_BUDGET:
                raise ValueError("Payment is outside the permitted budget.")

            payment = db.query(Payment).filter(Payment.task_id == task_id).first()
            if payment:
                if payment.status in (PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED):
                    return self._serialize(payment, duplicate=True)
                if payment.status == PaymentStatus.AWAITING_APPROVAL:
                    return self._serialize(payment, duplicate=True)
                if payment.status == PaymentStatus.HELD:
                    raise ValueError("This payment is on hold and cannot be re-authorized.")
            else:
                payment = Payment(
                    task_id=task_id,
                    amount=round(amount, 2),
                    status=PaymentStatus.PENDING,
                    idempotency_key=idempotency_key or f"ap-task-{task_id}-auth",
                )
                db.add(payment)
                db.commit()
                db.refresh(payment)

            order = await paypal_service.create_order(
                amount=amount,
                currency="USD",
                idempotency_key=f"ap-task-{task_id}-order",
                return_url=f"{settings.PAYPAL_RETURN_URL}?task_id={task_id}",
                cancel_url=f"{settings.PAYPAL_CANCEL_URL}?task_id={task_id}",
            )
            payment.paypal_order_id = order.get("id")
            payment.paypal_approval_url = order.get("approval_url")
            if not payment.paypal_order_id:
                raise RuntimeError("Payment provider did not return an order ID.")
            if not self.mock_mode and not payment.paypal_approval_url:
                raise RuntimeError("Payment provider did not return a checkout approval URL.")

            if self.mock_mode:
                authorization = await paypal_service.authorize_order(
                    payment.paypal_order_id, idempotency_key=f"ap-task-{task_id}-auth"
                )
                payment.paypal_authorization_id = authorization["id"]
                payment.status = PaymentStatus.AUTHORIZED
            else:
                payment.status = PaymentStatus.AWAITING_APPROVAL

            payment.updated_at = datetime.now(timezone.utc)
            db.add(
                AgentEvent(
                    task_id=task_id,
                    agent_name=self.name,
                    event_type="payment_authorization_started",
                    event_data=json.dumps(
                        {
                            "amount": amount,
                            "order_id": payment.paypal_order_id,
                            "mock": self.mock_mode,
                            "status": payment.status.value,
                        }
                    ),
                )
            )
            db.commit()
            db.refresh(payment)
            result = self._serialize(payment, duplicate=False)
            result["approval_url"] = order.get("approval_url")
            result["mock"] = self.mock_mode
            return result
        except Exception:
            db.rollback()
            logger.exception("Payment authorization failed for task %s", task_id)
            raise
        finally:
            db.close()

    async def complete_authorization(self, task_id: int, order_id: str) -> dict:
        db = SessionLocal()
        try:
            payment = db.query(Payment).filter(Payment.task_id == task_id).first()
            if not payment:
                raise ValueError("No payment order exists for this task.")
            if payment.paypal_order_id != order_id:
                raise ValueError("The returned PayPal order does not match this task.")
            if payment.status == PaymentStatus.AUTHORIZED:
                return self._serialize(payment, duplicate=True)
            if payment.status != PaymentStatus.AWAITING_APPROVAL:
                raise ValueError(f"Payment is not awaiting approval (status: {payment.status.value}).")

            authorization = await paypal_service.authorize_order(
                order_id, idempotency_key=f"ap-task-{task_id}-auth"
            )
            payment.paypal_authorization_id = authorization["id"]
            payment.status = PaymentStatus.AUTHORIZED
            payment.updated_at = datetime.now(timezone.utc)
            db.add(
                AgentEvent(
                    task_id=task_id,
                    agent_name=self.name,
                    event_type="payment_authorized",
                    event_data=json.dumps({"authorization_id": authorization["id"]}),
                )
            )
            db.commit()
            db.refresh(payment)
            return self._serialize(payment, duplicate=False)
        except Exception:
            db.rollback()
            logger.exception("PayPal approval completion failed for task %s", task_id)
            raise
        finally:
            db.close()

    async def capture_payment(self, task_id: int) -> dict:
        db = SessionLocal()
        try:
            payment = db.query(Payment).filter(Payment.task_id == task_id).first()
            if not payment:
                raise ValueError("No payment exists for this task.")
            if payment.status == PaymentStatus.CAPTURED:
                return self._serialize(payment, duplicate=True)
            if payment.status != PaymentStatus.AUTHORIZED:
                raise ValueError(f"Payment is not authorized (status: {payment.status.value}).")

            contract = db.query(Contract).filter(Contract.task_id == task_id).first()
            if not contract or not contract.buyer_approved:
                raise ValueError("Payment capture requires an approved contract.")
            verification = db.query(VerificationReport).filter(
                VerificationReport.task_id == task_id
            ).first()
            if not verification or verification.verification_status != VerificationStatus.PASS:
                raise ValueError("Payment capture is blocked until independent verification passes.")

            capture = await paypal_service.capture_authorization(
                payment.paypal_authorization_id,
                idempotency_key=f"ap-task-{task_id}-capture",
            )
            if capture.get("status") != "COMPLETED":
                raise RuntimeError(f"PayPal capture was not completed (status: {capture.get('status')}).")
            payment.paypal_capture_id = capture.get("id")
            payment.status = PaymentStatus.CAPTURED
            payment.updated_at = datetime.now(timezone.utc)
            db.add(
                AgentEvent(
                    task_id=task_id,
                    agent_name=self.name,
                    event_type="payment_captured",
                    event_data=json.dumps(
                        {"capture_id": payment.paypal_capture_id, "amount": payment.amount}
                    ),
                )
            )
            db.commit()
            db.refresh(payment)
            return self._serialize(payment, duplicate=False)
        except Exception:
            db.rollback()
            logger.exception("Payment capture failed for task %s", task_id)
            raise
        finally:
            db.close()

    def hold_payment(self, task_id: int, reason: str) -> dict:
        db = SessionLocal()
        try:
            payment = db.query(Payment).filter(Payment.task_id == task_id).first()
            if not payment:
                raise ValueError("No payment exists for this task.")
            if payment.status == PaymentStatus.CAPTURED:
                raise ValueError("A captured payment cannot be moved to a hold state.")
            payment.status = PaymentStatus.HELD
            payment.updated_at = datetime.now(timezone.utc)
            db.add(
                AgentEvent(
                    task_id=task_id,
                    agent_name=self.name,
                    event_type="payment_held",
                    event_data=json.dumps({"reason": reason}),
                )
            )
            db.commit()
            return {"payment_id": payment.id, "status": "held", "reason": reason}
        except Exception:
            db.rollback()
            logger.exception("Payment hold failed for task %s", task_id)
            raise
        finally:
            db.close()

    @staticmethod
    def _serialize(payment: Payment, duplicate: bool) -> dict:
        return {
            "payment_id": payment.id,
            "order_id": payment.paypal_order_id,
            "approval_url": payment.paypal_approval_url,
            "authorization_id": payment.paypal_authorization_id,
            "capture_id": payment.paypal_capture_id,
            "status": payment.status.value,
            "amount": payment.amount,
            "duplicate": duplicate,
        }


payment_agent = PaymentAgent()
