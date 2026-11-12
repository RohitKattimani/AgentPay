import asyncio

import pytest

from database.models import (
    Contract,
    ContractStatus,
    Negotiation,
    Payment,
    PaymentStatus,
    SessionLocal,
    Task,
    TaskStatus,
)
from agents.payment_agent import payment_agent


def create_task(client, csv_content: str, budget: str = "5.00") -> int:
    response = client.post(
        "/api/tasks",
        data={"description": "Clean and validate this customer CSV file.", "budget": budget},
        files={"file": ("customers.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["task_id"]


def test_successful_end_to_end_workflow_captures_payment_after_verification(client):
    csv_content = (
        " Customer Name , Email Address , Plan \n"
        " Ava Patel , ava@example.com , Pro \n"
        "Ava Patel,ava@example.com,Pro\n"
        "Noah Kim,noah@example.com,Basic\n"
    )
    task_id = create_task(client, csv_content)

    started = client.post(f"/api/tasks/{task_id}/start")
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "pending_approval"
    assert started.json()["negotiation_result"]["winning_seller"]

    contract = client.get(f"/api/contracts/{task_id}")
    assert contract.status_code == 200
    assert contract.json()["status"] == "pending_approval"

    approved = client.post(f"/api/contracts/{task_id}/approve")
    assert approved.status_code == 200, approved.text
    result = approved.json()
    assert result["status"] == "completed"
    assert result["verification_result"]["verification_status"] == "pass"
    assert result["payment_captured"] is True

    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == TaskStatus.COMPLETED.value
    assert task["has_output_file"] is True

    download = client.get(f"/api/tasks/{task_id}/download")
    assert download.status_code == 200
    assert b"customer_name,email_address,plan" in download.content

    # Repeating workflow calls must not create another contract, execution, report, or payment.
    assert client.post(f"/api/tasks/{task_id}/start").status_code == 200
    assert client.post(f"/api/contracts/{task_id}/approve").status_code == 200
    db = SessionLocal()
    try:
        assert db.query(Negotiation).filter(Negotiation.task_id == task_id).count() == 1
        assert db.query(Contract).filter(Contract.task_id == task_id).count() == 1
        assert db.query(Payment).filter(Payment.task_id == task_id).count() == 1
    finally:
        db.close()


def test_unresolved_values_fail_verification_and_hold_payment(client):
    csv_content = (
        "name,email,region\n"
        "Ava,ava@example.com,South\n"
        "Noah,,\n"
    )
    task_id = create_task(client, csv_content)
    assert client.post(f"/api/tasks/{task_id}/start").status_code == 200

    response = client.post(f"/api/contracts/{task_id}/approve")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "failed"
    assert result["verification_result"]["verification_status"] == "fail"
    assert result["payment_captured"] is False

    db = SessionLocal()
    try:
        payment = db.query(Payment).filter(Payment.task_id == task_id).one()
        task = db.query(Task).filter(Task.id == task_id).one()
        assert payment.status == PaymentStatus.HELD
        assert task.status == TaskStatus.FAILED
    finally:
        db.close()


def test_payment_capture_is_blocked_without_a_passing_verification(client):
    task_id = create_task(client, "name,email\nAva,ava@example.com\n")
    assert client.post(f"/api/tasks/{task_id}/start").status_code == 200

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).one()
        contract = db.query(Contract).filter(Contract.task_id == task_id).one()
        contract.status = ContractStatus.APPROVED
        contract.buyer_approved = True
        task.status = TaskStatus.IN_PROGRESS
        db.commit()
        amount = contract.agreed_price
    finally:
        db.close()

    authorization = asyncio.run(
        payment_agent.authorize_payment(task_id, amount, f"agentpay-test-{task_id}")
    )
    assert authorization["status"] == PaymentStatus.AUTHORIZED.value

    with pytest.raises(ValueError, match="verification passes"):
        asyncio.run(payment_agent.capture_payment(task_id))


def test_budget_above_platform_limit_is_rejected(client):
    response = client.post(
        "/api/tasks",
        data={"description": "Clean this uploaded CSV file.", "budget": "5.01"},
        files={"file": ("customers.csv", b"name,email\nAva,ava@example.com\n", "text/csv")},
    )
    assert response.status_code == 400
    assert "cannot exceed" in response.json()["detail"].lower()


def test_uploaded_filename_is_not_used_as_storage_path(client):
    response = client.post(
        "/api/tasks",
        data={"description": "Clean this uploaded CSV file.", "budget": "5.00"},
        files={"file": ("../../unsafe.csv", b"name,email\nAva,ava@example.com\n", "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert "unsafe.csv" not in response.json().get("csv_file_path", "")
    assert response.json()["has_source_file"] is True


def test_empty_cleaned_output_cannot_pass_verification(client):
    task_id = create_task(client, "name,email\n,\n")
    assert client.post(f"/api/tasks/{task_id}/start").status_code == 200

    response = client.post(f"/api/contracts/{task_id}/approve")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "failed"
    assert result["verification_result"]["empty_output"] == 1
    assert result["verification_result"]["verification_status"] == "fail"
    assert result["payment_captured"] is False
