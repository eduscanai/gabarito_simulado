from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select

from .database import initialize_database, session_scope
from .models import (
    Assessment,
    AssessmentStudent,
    DetectedAnswer,
    Question,
    Result,
    Student,
    Submission,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass

    return datetime.now()


def as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def upsert_student(
    session,
    registration: str,
    name: str,
) -> Student:
    student = session.scalar(
        select(Student).where(
            Student.registration == registration
        )
    )

    if student is None:
        student = Student(
            registration=registration,
            name=name or "Aluno",
        )
        session.add(student)
        session.flush()
    else:
        student.name = name or student.name

    return student


def sync_assessment_directory(
    assessment_dir: Path,
) -> dict[str, int | str]:
    initialize_database()

    assessment_path = assessment_dir / "avaliacao.json"

    if not assessment_path.exists():
        raise FileNotFoundError(
            f"avaliacao.json não encontrado em {assessment_dir}"
        )

    assessment_data = read_json(assessment_path)
    students_path = assessment_dir / "alunos.json"
    students_data = (
        read_json(students_path)
        if students_path.exists()
        else {"students": []}
    )

    assessment_id = str(
        assessment_data.get("id") or assessment_dir.name
    )
    questions_data = assessment_data.get("questions", [])
    total_score = as_float(
        assessment_data.get(
            "maximum_score",
            assessment_data.get("total_score", 10),
        ),
        10,
    )
    total_weight = as_float(
        assessment_data.get("total_weight"),
        sum(
            as_float(question.get("weight"), 1)
            for question in questions_data
            if isinstance(question, dict)
        ),
    )

    with session_scope() as session:
        assessment = session.get(Assessment, assessment_id)

        if assessment is None:
            assessment = Assessment(id=assessment_id)
            session.add(assessment)

        assessment.title = str(
            assessment_data.get("title", "Avaliação sem título")
        )
        assessment.question_count = as_int(
            assessment_data.get(
                "question_count",
                len(questions_data),
            )
        )
        assessment.total_score = total_score
        assessment.total_weight = total_weight
        assessment.created_at = parse_datetime(
            assessment_data.get("created_at")
        )

        existing_questions = {
            question.number: question
            for question in session.scalars(
                select(Question).where(
                    Question.assessment_id == assessment_id
                )
            )
        }

        received_numbers: set[int] = set()

        for index, raw_question in enumerate(
            questions_data,
            start=1,
        ):
            if not isinstance(raw_question, dict):
                continue

            number = as_int(
                raw_question.get("number"),
                index,
            )
            received_numbers.add(number)
            question = existing_questions.get(number)

            if question is None:
                question = Question(
                    assessment_id=assessment_id,
                    number=number,
                )
                session.add(question)

            question.option_count = as_int(
                raw_question.get("option_count"),
                len(raw_question.get("options", [])) or 5,
            )
            question.correct_answer = str(
                raw_question.get("answer", "")
            )
            question.weight = as_float(
                raw_question.get("weight"),
                1,
            )

        for number, question in existing_questions.items():
            if number not in received_numbers:
                session.delete(question)

        students = students_data.get("students", [])

        if not isinstance(students, list):
            students = []

        imported_students = 0
        imported_submissions = 0

        for raw_student in students:
            if not isinstance(raw_student, dict):
                continue

            registration = str(raw_student.get("id", "")).strip()

            if not registration:
                continue

            student = upsert_student(
                session,
                registration=registration,
                name=str(raw_student.get("name", "Aluno")),
            )

            link = session.scalar(
                select(AssessmentStudent).where(
                    AssessmentStudent.assessment_id
                    == assessment_id,
                    AssessmentStudent.student_id == student.id,
                )
            )

            if link is None:
                link = AssessmentStudent(
                    assessment_id=assessment_id,
                    student_id=student.id,
                )
                session.add(link)

            status = str(
                raw_student.get("status", "pending")
            )
            link.status = status
            imported_students += 1

            raw_result = raw_student.get("result")
            uploaded_file = raw_student.get("uploaded_file")

            submission = session.scalar(
                select(Submission).where(
                    Submission.assessment_id == assessment_id,
                    Submission.student_id == student.id,
                )
            )

            if uploaded_file or isinstance(raw_result, dict):
                if submission is None:
                    submission = Submission(
                        assessment_id=assessment_id,
                        student_id=student.id,
                    )
                    session.add(submission)
                    session.flush()

                submission.status = status
                submission.original_file = (
                    str(uploaded_file)
                    if uploaded_file
                    else None
                )
                submission.processed_file = (
                    str(raw_result.get("processed_image"))
                    if isinstance(raw_result, dict)
                    and raw_result.get("processed_image")
                    else None
                )
                submission.uploaded_at = datetime.now()
                imported_submissions += 1

            if submission is None:
                continue

            if not isinstance(raw_result, dict):
                session.execute(
                    delete(DetectedAnswer).where(
                        DetectedAnswer.submission_id
                        == submission.id
                    )
                )
                existing_result = session.scalar(
                    select(Result).where(
                        Result.submission_id == submission.id
                    )
                )
                if existing_result is not None:
                    session.delete(existing_result)
                continue

            result = session.scalar(
                select(Result).where(
                    Result.submission_id == submission.id
                )
            )

            if result is None:
                result = Result(
                    submission_id=submission.id
                )
                session.add(result)

            result.correct_count = as_int(
                raw_result.get("correct")
            )
            result.error_count = as_int(
                raw_result.get("errors")
            )
            result.blank_count = as_int(
                raw_result.get("blank")
            )
            result.score = as_float(
                raw_result.get("score")
            )
            result.maximum_score = as_float(
                raw_result.get("maximum_score"),
                total_score,
            )
            result.percentage = as_float(
                raw_result.get("percentage")
            )
            result.earned_weight = as_float(
                raw_result.get("earned_weight")
            )
            result.total_weight = as_float(
                raw_result.get("total_weight"),
                total_weight,
            )

            session.execute(
                delete(DetectedAnswer).where(
                    DetectedAnswer.submission_id
                    == submission.id
                )
            )

            details = raw_result.get("details", [])

            if not isinstance(details, list):
                details = []

            for detail in details:
                if not isinstance(detail, dict):
                    continue

                session.add(
                    DetectedAnswer(
                        submission_id=submission.id,
                        question_number=as_int(
                            detail.get("question")
                        ),
                        selected_answer=str(
                            detail.get("selected", "")
                        ),
                        correct_answer=str(
                            detail.get(
                                "correct_answer",
                                "",
                            )
                        ),
                        is_correct=bool(
                            detail.get("is_correct")
                        ),
                        is_blank=bool(
                            detail.get("is_blank")
                        ),
                        weight=as_float(
                            detail.get("weight"),
                            1,
                        ),
                        question_value=as_float(
                            detail.get("question_value")
                        ),
                        earned_score=as_float(
                            detail.get("earned_score")
                        ),
                    )
                )

    return {
        "assessment_id": assessment_id,
        "students": imported_students,
        "submissions": imported_submissions,
    }


def sync_all_assessments(
    assessments_dir: Path,
) -> dict[str, object]:
    initialize_database()

    imported = 0
    errors: list[dict[str, str]] = []

    if not assessments_dir.exists():
        return {
            "imported": 0,
            "errors": [],
        }

    for assessment_dir in assessments_dir.iterdir():
        if not assessment_dir.is_dir():
            continue

        if not (assessment_dir / "avaliacao.json").exists():
            continue

        try:
            sync_assessment_directory(assessment_dir)
            imported += 1
        except Exception as exc:
            errors.append(
                {
                    "assessment": assessment_dir.name,
                    "error": str(exc),
                }
            )

    return {
        "imported": imported,
        "errors": errors,
    }


def find_student_profile(registration: str) -> dict[str, str] | None:
    initialize_database()
    wanted = str(registration).strip()

    with session_scope() as session:
        student = session.scalar(
            select(Student).where(Student.registration == wanted)
        )

        if student is None and wanted.isdigit():
            wanted_key = wanted.lstrip("0") or "0"
            candidates = list(session.scalars(select(Student)))
            matches = [
                candidate
                for candidate in candidates
                if candidate.registration.isdigit()
                and (candidate.registration.lstrip("0") or "0")
                == wanted_key
            ]
            student = matches[0] if len(matches) == 1 else None

        if student is None:
            return None

        return {
            "registration": student.registration,
            "name": student.name,
        }


def database_counts() -> dict[str, int]:
    initialize_database()

    with session_scope() as session:
        return {
            "students": session.scalar(
                select(func.count()).select_from(Student)
            ) or 0,
            "classes": 0,
            "assessments": session.scalar(
                select(func.count()).select_from(Assessment)
            ) or 0,
            "questions": session.scalar(
                select(func.count()).select_from(Question)
            ) or 0,
            "assessment_students": session.scalar(
                select(func.count()).select_from(
                    AssessmentStudent
                )
            ) or 0,
            "submissions": session.scalar(
                select(func.count()).select_from(Submission)
            ) or 0,
            "results": session.scalar(
                select(func.count()).select_from(Result)
            ) or 0,
            "detected_answers": session.scalar(
                select(func.count()).select_from(
                    DetectedAnswer
                )
            ) or 0,
        }
