from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def now() -> datetime:
    return datetime.now()


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now,
        onupdate=now,
        nullable=False,
    )


class ClassRoom(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    course: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    semester: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now,
        nullable=False,
    )


class ClassStudent(Base):
    __tablename__ = "class_students"
    __table_args__ = (
        UniqueConstraint(
            "class_id",
            "student_id",
            name="uq_class_student",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    question_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=10,
    )
    total_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now,
        onupdate=now,
        nullable=False,
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "number",
            name="uq_assessment_question_number",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    option_count: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_answer: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1,
    )


class AssessmentStudent(Base):
    __tablename__ = "assessment_students"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "student_id",
            name="uq_assessment_student",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "student_id",
            name="uq_submission_assessment_student",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )
    original_file: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    processed_file: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now,
        onupdate=now,
        nullable=False,
    )


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    correct_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    blank_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
    )
    maximum_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
    )
    percentage: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
    )
    earned_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
    )
    total_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now,
        onupdate=now,
        nullable=False,
    )


class DetectedAnswer(Base):
    __tablename__ = "detected_answers"
    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "question_number",
            name="uq_submission_question_answer",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    selected_answer: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="",
    )
    correct_answer: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="",
    )
    is_correct: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_blank: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1,
    )
    question_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
    )
    earned_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
    )
