"""HTTP API for task submission, marketplace orchestration, and settlement."""

import json
import logging
import math
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from agents.negotiation_agent import negotiation_agent
from agents.payment_agent import payment_agent
from agents.verification_agent import verification_agent
from config import settings
from database.models import (
    AgentEvent,
    Bid,
    Contract,
    ContractStatus,
    Negotiation,
    Payment,
    PaymentStatus,
    SessionLocal,
    Task,
    TaskExecution,
    TaskStatus,
    User,
    VerificationReport,
)
from services.csv_pipeline import read_csv
from workflows.agentpay_graph import agentpay_graph

logger = logging.getLogger("agentpay.api")
router = APIRouter()


class AuthorizationCompletion(BaseModel):
    order_id: str = Field(min_length=5, max_length=120)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Dict[int, List[Any]] = {}

    async def connect(self, websocket, task_id: int) -> None:
        await websocket.accept()
        self.active_connections.setdefault(task_id, []).append(websocket)

    def disconnect(self, websocket, task_id: int) -> None:
        connections = self.active_connections.get(task_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.active_connections.pop(task_id, None)

    async def broadcast(self, task_id: int, message: Dict[str, Any]) -> None:
        connections = list(self.active_connections.get(task_id, []))
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection, task_id)


manager = ConnectionManager()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _task_payload(task: Task) -> dict:
    execution = task.execution
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "budget": task.budget,
        "currency": task.currency,
        "deadline_minutes": task.deadline_minutes,
        "deliverables": task.deliverables,
        "acceptance_criteria": task.acceptance_criteria,
        "has_source_file": bool(task.csv_file_path and Path(task.csv_file_path).is_file()),
        "has_output_file": bool(execution and execution.output_file_path and Path(execution.output_file_path).is_file()),
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    logger.exception("Unhandled AgentPay API error", exc_info=exc)
    return HTTPException(status_code=500, detail="The operation could not be completed.")


@router.post("/tasks")
async def create_task(
    description: str = Form(..., min_length=5, max_length=2000),
    budget: float = Form(default=5.0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    description = description.strip()
    if len(description) < 5:
        raise HTTPException(status_code=400, detail="Please provide a task description of at least 5 characters.")
    if not math.isfinite(budget) or budget <= 0:
        raise HTTPException(status_code=400, detail="Budget must be a positive amount.")
    if budget > settings.MAX_BUDGET:
        raise HTTPException(status_code=400, detail=f"Budget cannot exceed ${settings.MAX_BUDGET:.2f} USD.")
    if not file.filename or Path(file.filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Upload a file with a .csv extension.")

    file_size = 0
    saved_path = settings.UPLOAD_DIR / f"source_{uuid.uuid4().hex}.csv"
    try:
        with saved_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > settings.MAX_CSV_SIZE_MB * 1024 * 1024:
                    raise HTTPException(
                        status_code=413,
                        detail=f"CSV exceeds the {settings.MAX_CSV_SIZE_MB} MB upload limit.",
                    )
                destination.write(chunk)
        if file_size == 0:
            raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")
        read_csv(saved_path)
    except HTTPException:
        saved_path.unlink(missing_ok=True)
        raise
    except ValueError as exc:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        saved_path.unlink(missing_ok=True)
        logger.exception("Could not save uploaded CSV")
        raise HTTPException(status_code=500, detail="Could not save the uploaded CSV file.") from exc
    finally:
        await file.close()

    try:
        user = db.query(User).filter(User.email == "buyer@agentpay.local").first()
        if user is None:
            user = User(email="buyer@agentpay.local", name="AgentPay Buyer")
            db.add(user)
            db.flush()
        task = Task(
            title="CSV Data Cleaning",
            description=description,
            budget=round(budget, 2),
            currency="USD",
            csv_file_path=str(saved_path),
            buyer_id=user.id,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
    except Exception as exc:
        db.rollback()
        saved_path.unlink(missing_ok=True)
        logger.exception("Could not create task")
        raise HTTPException(status_code=500, detail="Could not create the task.") from exc

    await manager.broadcast(task.id, {"event": "task_created", "task_id": task.id})
    return {"task_id": task.id, **_task_payload(task)}


@router.get("/tasks")
async def list_tasks(db: Session = Depends(get_db)):
    tasks = db.query(Task).order_by(Task.created_at.desc()).limit(100).all()
    return [_task_payload(task) for task in tasks]


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return _task_payload(task)


@router.get("/tasks/{task_id}/download")
async def download_cleaned_file(task_id: int, db: Session = Depends(get_db)):
    execution = db.query(TaskExecution).filter(TaskExecution.task_id == task_id).first()
    if not execution or not execution.output_file_path:
        raise HTTPException(status_code=404, detail="No cleaned file is available for this task.")
    path = Path(execution.output_file_path).resolve()
    if not path.is_file() or path.parent != settings.UPLOAD_DIR.resolve():
        raise HTTPException(status_code=404, detail="The cleaned file could not be found.")
    return FileResponse(path, media_type="text/csv", filename=f"agentpay-task-{task_id}-cleaned.csv")


@router.post("/tasks/{task_id}/start")
async def start_workflow(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    try:
        result = await agentpay_graph.run(
            task_id=task_id,
            task_description=task.description,
            csv_file_path=task.csv_file_path,
            user_id=task.buyer_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    await manager.broadcast(task_id, {"event": "workflow_started", "task_id": task_id, "result": result})
    return result


@router.post("/tasks/{task_id}/execute")
async def execute_task(task_id: int, db: Session = Depends(get_db)):
    try:
        result = await agentpay_graph.execute_after_authorization(task_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    await manager.broadcast(task_id, {"event": "task_executed", "task_id": task_id, "result": result})
    return result


@router.post("/negotiations/{task_id}/start")
async def start_negotiation(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    try:
        result = negotiation_agent.start_negotiation(
            task_id=task_id,
            task_description=task.description,
            budget=task.budget,
            deadline_minutes=task.deadline_minutes,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    await manager.broadcast(task_id, {"event": "negotiation_completed", "task_id": task_id, "result": result})
    return result


@router.get("/negotiations/{task_id}/bids")
async def get_bids(task_id: int, db: Session = Depends(get_db)):
    negotiation = db.query(Negotiation).filter(Negotiation.task_id == task_id).first()
    if not negotiation:
        return []
    bids = db.query(Bid).filter(Bid.negotiation_id == negotiation.id).order_by(Bid.id.asc()).all()
    return [
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
    ]


@router.get("/contracts/{task_id}")
async def get_contract(task_id: int, db: Session = Depends(get_db)):
    contract = db.query(Contract).filter(Contract.task_id == task_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found.")
    return {
        "id": contract.id,
        "task_id": contract.task_id,
        "seller_name": contract.seller_name,
        "agreed_price": contract.agreed_price,
        "deadline_minutes": contract.deadline_minutes,
        "deliverables": contract.deliverables,
        "acceptance_criteria": contract.acceptance_criteria,
        "revision_policy": contract.revision_policy,
        "payment_conditions": contract.payment_conditions,
        "status": contract.status.value,
        "buyer_approved": contract.buyer_approved,
    }


@router.post("/contracts/{task_id}/approve")
async def approve_contract(task_id: int):
    try:
        result = await agentpay_graph.approve_contract(task_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    await manager.broadcast(task_id, {"event": "contract_approved", "task_id": task_id, "result": result})
    return result


@router.post("/contracts/{task_id}/reject")
async def reject_contract(task_id: int):
    try:
        result = await agentpay_graph.reject_contract(task_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    await manager.broadcast(task_id, {"event": "contract_rejected", "task_id": task_id})
    return result


@router.post("/verification/{task_id}/run")
async def run_verification(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    execution = db.query(TaskExecution).filter(TaskExecution.task_id == task_id).first()
    contract = db.query(Contract).filter(Contract.task_id == task_id).first()
    if not task or not execution or not execution.output_file_path:
        raise HTTPException(status_code=404, detail="Task execution or output file not found.")
    criteria = json.loads(contract.acceptance_criteria) if contract and contract.acceptance_criteria else []
    try:
        result = await verification_agent.verify_deliverable(
            task_id=task_id,
            original_file_path=task.csv_file_path,
            cleaned_file_path=execution.output_file_path,
            acceptance_criteria=criteria,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    await manager.broadcast(task_id, {"event": "verification_completed", "task_id": task_id, "result": result})
    return result


@router.get("/verification/{task_id}")
async def get_verification(task_id: int, db: Session = Depends(get_db)):
    report = db.query(VerificationReport).filter(VerificationReport.task_id == task_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Verification report not found.")
    return {
        "id": report.id,
        "task_id": report.task_id,
        "missing_values": report.missing_values,
        "empty_output": report.empty_output,
        "duplicate_records": report.duplicate_records,
        "invalid_emails": report.invalid_emails,
        "formatting_errors": report.formatting_errors,
        "verification_status": report.verification_status.value,
        "report_text": report.report_text,
        "revision_count": report.revision_count,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@router.post("/payments/{task_id}/authorize")
async def authorize_payment(task_id: int, db: Session = Depends(get_db)):
    contract = db.query(Contract).filter(Contract.task_id == task_id).first()
    if not contract or contract.status not in (ContractStatus.APPROVED, ContractStatus.COMPLETED):
        raise HTTPException(status_code=400, detail="The contract must be approved before payment authorization.")
    try:
        result = await payment_agent.authorize_payment(
            task_id, contract.agreed_price, f"ap-task-{task_id}-auth"
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    await manager.broadcast(task_id, {"event": "payment_authorization_updated", "task_id": task_id, "result": result})
    return result


@router.post("/payments/{task_id}/complete-authorization")
async def complete_payment_authorization(
    task_id: int, body: AuthorizationCompletion, db: Session = Depends(get_db)
):
    contract = db.query(Contract).filter(Contract.task_id == task_id).first()
    if not contract or contract.status not in (ContractStatus.APPROVED, ContractStatus.COMPLETED):
        raise HTTPException(status_code=400, detail="The contract is not approved.")
    try:
        authorization = await payment_agent.complete_authorization(task_id, body.order_id)
        result = await agentpay_graph.execute_after_authorization(task_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    await manager.broadcast(task_id, {"event": "task_executed", "task_id": task_id, "result": result})
    return {"authorization": authorization, **result}


@router.get("/transactions")
async def get_transactions(db: Session = Depends(get_db)):
    payments = db.query(Payment).order_by(Payment.created_at.desc()).all()
    results = []
    for payment in payments:
        task = db.query(Task).filter(Task.id == payment.task_id).first()
        contract = db.query(Contract).filter(Contract.task_id == payment.task_id).first()
        verification = db.query(VerificationReport).filter(
            VerificationReport.task_id == payment.task_id
        ).first()
        results.append(
            {
                "id": payment.id,
                "task_id": payment.task_id,
                "task_name": task.title if task else "Unknown",
                "seller": contract.seller_name if contract else "Unknown",
                "amount": payment.amount,
                "verification_status": verification.verification_status.value if verification else "unknown",
                "payment_status": payment.status.value,
                "paypal_order_id": payment.paypal_order_id,
                "paypal_capture_id": payment.paypal_capture_id,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
            }
        )
    return results


@router.get("/agents")
async def get_agents(db: Session = Depends(get_db)):
    agent_names = [
        "Buyer Agent",
        "Negotiation Agent",
        "Contract Agent",
        "Seller Agent",
        "Independent Verification Agent",
        "PayPal Payment Agent",
    ]
    results = []
    for name in agent_names:
        events = (
            db.query(AgentEvent)
            .filter(AgentEvent.agent_name == name)
            .order_by(AgentEvent.created_at.desc())
            .limit(5)
            .all()
        )
        latest = events[0] if events else None
        results.append(
            {
                "name": name,
                "status": "error" if latest and "failed" in latest.event_type else "idle",
                "last_activity": latest.event_type if latest else "none",
                "last_activity_time": latest.created_at.isoformat() if latest else None,
                "event_count": db.query(AgentEvent).filter(AgentEvent.agent_name == name).count(),
            }
        )
    return results


@router.get("/dashboard/stats")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    total_tasks = db.query(Task).count()
    completed_tasks = db.query(Task).filter(Task.status == TaskStatus.COMPLETED).count()
    failed_tasks = db.query(Task).filter(Task.status == TaskStatus.FAILED).count()
    active_tasks = db.query(Task).filter(Task.status == TaskStatus.IN_PROGRESS).count()
    total_volume = (
        db.query(func.sum(Payment.amount))
        .filter(Payment.status == PaymentStatus.CAPTURED)
        .scalar()
        or 0
    )
    recent_events = db.query(AgentEvent).order_by(AgentEvent.created_at.desc()).limit(10).all()
    return {
        "total_tasks": total_tasks,
        "active_tasks": active_tasks,
        "completed_tasks": completed_tasks,
        "failed_tasks": failed_tasks,
        "total_volume": round(float(total_volume), 2),
        "recent_activity": [
            {
                "agent": event.agent_name,
                "event": event.event_type,
                "task_id": event.task_id,
                "time": event.created_at.isoformat() if event.created_at else None,
            }
            for event in recent_events
        ],
    }
