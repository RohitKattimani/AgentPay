"""SQLAlchemy models and database session management."""

import enum
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from config import settings


def utc_now():
    return datetime.now(timezone.utc)


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VerificationStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    MANUAL_REVIEW = "manual_review"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    HELD = "held"


class AgentStatus(str, enum.Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"


# Keep the default SQLite database beside the backend package rather than
# depending on the directory from which Uvicorn was launched.
database_url = settings.DATABASE_URL
if database_url.startswith("sqlite:///./"):
    relative_path = database_url.removeprefix("sqlite:///./")
    absolute_path = Path(__file__).resolve().parents[1] / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{absolute_path.as_posix()}"

engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    tasks = relationship("Task", back_populates="buyer")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    csv_file_path = Column(String(1024), nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    budget = Column(Float, default=5.00, nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    deadline_minutes = Column(Integer, default=5, nullable=False)
    deliverables = Column(Text, nullable=True)
    acceptance_criteria = Column(Text, nullable=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    buyer = relationship("User", back_populates="tasks")
    negotiations = relationship("Negotiation", back_populates="task")
    contract = relationship("Contract", back_populates="task", uselist=False)
    execution = relationship("TaskExecution", back_populates="task", uselist=False)
    verification = relationship("VerificationReport", back_populates="task", uselist=False)
    payment = relationship("Payment", back_populates="task", uselist=False)


class Negotiation(Base):
    __tablename__ = "negotiations"
    __table_args__ = (UniqueConstraint("task_id", name="uq_negotiation_task"),)

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    status = Column(String(30), default="in_progress", nullable=False)
    winning_bid_id = Column(Integer, nullable=True)
    selection_explanation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    task = relationship("Task", back_populates="negotiations")
    bids = relationship("Bid", back_populates="negotiation", cascade="all, delete-orphan")


class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True, index=True)
    negotiation_id = Column(Integer, ForeignKey("negotiations.id"), nullable=False)
    seller_name = Column(String(120), nullable=False)
    price = Column(Float, nullable=False)
    delivery_minutes = Column(Integer, nullable=False)
    rating = Column(Float, nullable=False)
    score = Column(Float, nullable=True)
    is_winner = Column(Boolean, default=False, nullable=False)
    counteroffer_price = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    negotiation = relationship("Negotiation", back_populates="bids")


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (UniqueConstraint("task_id", name="uq_contract_task"),)

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    seller_name = Column(String(120), nullable=False)
    agreed_price = Column(Float, nullable=False)
    deadline_minutes = Column(Integer, nullable=False)
    deliverables = Column(Text, nullable=True)
    acceptance_criteria = Column(Text, nullable=True)
    revision_policy = Column(Text, nullable=True)
    payment_conditions = Column(Text, nullable=True)
    status = Column(Enum(ContractStatus), default=ContractStatus.DRAFT, nullable=False)
    buyer_approved = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    task = relationship("Task", back_populates="contract")


class TaskExecution(Base):
    __tablename__ = "task_executions"
    __table_args__ = (UniqueConstraint("task_id", name="uq_execution_task"),)

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    seller_name = Column(String(120), nullable=False)
    output_file_path = Column(String(1024), nullable=True)
    processing_report = Column(Text, nullable=True)
    status = Column(String(30), default="pending", nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    task = relationship("Task", back_populates="execution")


class VerificationReport(Base):
    __tablename__ = "verification_reports"
    __table_args__ = (UniqueConstraint("task_id", name="uq_verification_task"),)

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    missing_values = Column(Integer, default=0, nullable=False)
    empty_output = Column(Integer, default=0, nullable=False)
    duplicate_records = Column(Integer, default=0, nullable=False)
    invalid_emails = Column(Integer, default=0, nullable=False)
    formatting_errors = Column(Integer, default=0, nullable=False)
    verification_status = Column(
        Enum(VerificationStatus), default=VerificationStatus.MANUAL_REVIEW, nullable=False
    )
    report_text = Column(Text, nullable=True)
    revision_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    task = relationship("Task", back_populates="verification")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("task_id", name="uq_payment_task"),)

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    paypal_order_id = Column(String(120), nullable=True)
    paypal_approval_url = Column(String(1024), nullable=True)
    paypal_authorization_id = Column(String(120), nullable=True)
    paypal_capture_id = Column(String(120), nullable=True)
    amount = Column(Float, nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    idempotency_key = Column(String(120), unique=True, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    task = relationship("Task", back_populates="payment")


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    agent_name = Column(String(120), nullable=False)
    event_type = Column(String(100), nullable=False)
    event_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
