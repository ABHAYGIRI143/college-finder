import csv
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NoReturn

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models import AdmissionRoute, College, CollegeType, Course, CourseFee, EntranceExam


CSV_HEADERS: dict[str, tuple[str, ...]] = {
    "entrance_exams.csv": ("name",),
    "colleges.csv": ("name", "city", "state", "college_type", "website", "description"),
    "courses.csv": ("college_name", "name", "duration_years"),
    "course_fees.csv": (
        "college_name",
        "course_name",
        "academic_year",
        "tuition_fee_per_year",
        "total_tuition_fee",
        "fee_source_url",
        "last_verified_at",
    ),
    "admission_routes.csv": (
        "college_name",
        "course_name",
        "entrance_exam_name",
        "minimum_percentage",
        "required_subjects",
        "admission_year",
        "other_requirements",
    ),
}

SUMMARY_LABELS = {
    "entrance_exams.csv": "Entrance exams",
    "colleges.csv": "Colleges",
    "courses.csv": "Courses",
    "course_fees.csv": "Course fees",
    "admission_routes.csv": "Admission routes",
}


class ImportDataError(Exception):
    """A safe, user-facing error tied to an import file or row."""


@dataclass
class ImportSummary:
    inserted: Counter[str] = field(default_factory=Counter)
    duplicates: Counter[str] = field(default_factory=Counter)


def _fail(filename: str, row_number: int, reason: str) -> NoReturn:
    raise ImportDataError(f"{filename} row {row_number}: {reason}")


def _normalize_name(value: str) -> str:
    """Normalize for matching; stored display names are only trimmed at the ends."""
    return " ".join(value.split()).casefold()


def _required_text(
    row: dict[str, str],
    field_name: str,
    filename: str,
    row_number: int,
    label: str | None = None,
    context: str | None = None,
) -> str:
    value = (row.get(field_name) or "").strip()
    if not value:
        context_text = f" for {context}" if context else ""
        _fail(filename, row_number, f"{label or field_name}{context_text} is required.")
    return value


def _optional_text(row: dict[str, str], field_name: str) -> str | None:
    value = (row.get(field_name) or "").strip()
    return value or None


def _load_rows(filename: str) -> list[tuple[int, dict[str, str]]]:
    path = DATA_DIR / filename
    expected_headers = CSV_HEADERS[filename]

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames != list(expected_headers):
                found = reader.fieldnames if reader.fieldnames is not None else "no header row"
                raise ImportDataError(
                    f"{filename}: expected headers {list(expected_headers)!r}; found {found!r}."
                )

            rows: list[tuple[int, dict[str, str]]] = []
            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    _fail(filename, row_number, "row has more values than the header.")
                if any(value is None for value in row.values()):
                    _fail(filename, row_number, "row has fewer values than the header.")

                values = {key: row[key] or "" for key in expected_headers}
                if not any(value.strip() for value in values.values()):
                    continue
                rows.append((row_number, values))
            return rows
    except ImportDataError:
        raise
    except (OSError, UnicodeError, csv.Error) as error:
        raise ImportDataError(
            f"{filename}: could not read the CSV file ({type(error).__name__})."
        ) from error


def _flush_row(
    session: Session, filename: str, row_number: int, record_description: str, record: object
) -> None:
    session.add(record)
    try:
        session.flush()
    except IntegrityError as error:
        raise ImportDataError(
            f"{filename} row {row_number}: {record_description} was rejected by a database constraint."
        ) from error
    except SQLAlchemyError as error:
        raise ImportDataError(
            f"{filename} row {row_number}: database operation failed while saving {record_description}."
        ) from error


def _college_identity(name: str, city: str, state: str) -> tuple[str, str, str]:
    return (_normalize_name(name), _normalize_name(city), _normalize_name(state))


def _load_college_indexes(
    session: Session,
) -> tuple[dict[tuple[str, str, str], College], dict[str, list[College]]]:
    # College identity is normalized name + city + state; names alone resolve CSV references.
    by_identity: dict[tuple[str, str, str], College] = {}
    by_name: dict[str, list[College]] = {}

    for college in session.scalars(select(College)):
        by_identity.setdefault(_college_identity(college.name, college.city, college.state), college)
        by_name.setdefault(_normalize_name(college.name), []).append(college)
    return by_identity, by_name


def _resolve_college(
    name: str, by_name: dict[str, list[College]], filename: str, row_number: int
) -> College:
    matches = by_name.get(_normalize_name(name), [])
    if not matches:
        _fail(filename, row_number, f"college {name!r} was not found.")
    if len(matches) > 1:
        _fail(filename, row_number, f"college name {name!r} is ambiguous; it matches multiple colleges.")
    return matches[0]


def _import_entrance_exams(session: Session, summary: ImportSummary) -> dict[str, EntranceExam]:
    # Reuse existing exams by normalized, case-insensitive name.
    by_name: dict[str, EntranceExam] = {}
    for exam in session.scalars(select(EntranceExam)):
        by_name.setdefault(_normalize_name(exam.name), exam)

    for row_number, row in _load_rows("entrance_exams.csv"):
        name = _required_text(row, "name", "entrance_exams.csv", row_number, "exam name")
        key = _normalize_name(name)
        if key in by_name:
            summary.duplicates["Entrance exams"] += 1
            continue

        exam = EntranceExam(name=name)
        _flush_row(session, "entrance_exams.csv", row_number, f"entrance exam {name!r}", exam)
        by_name[key] = exam
        summary.inserted["Entrance exams"] += 1
    return by_name


def _import_colleges(
    session: Session, summary: ImportSummary
) -> tuple[dict[tuple[str, str, str], College], dict[str, list[College]]]:
    by_identity, by_name = _load_college_indexes(session)

    for row_number, row in _load_rows("colleges.csv"):
        name = _required_text(row, "name", "colleges.csv", row_number, "college name")
        college_context = f"college {name!r}"
        city = _required_text(row, "city", "colleges.csv", row_number, context=college_context)
        state = _required_text(row, "state", "colleges.csv", row_number, context=college_context)
        college_type_value = _required_text(
            row, "college_type", "colleges.csv", row_number, context=college_context
        )
        website = _required_text(
            row, "website", "colleges.csv", row_number, context=college_context
        )
        identity = _college_identity(name, city, state)

        try:
            college_type = CollegeType(college_type_value)
        except ValueError:
            _fail(
                "colleges.csv",
                row_number,
                f"college {name!r} has invalid college_type {college_type_value!r}; "
                "use exactly GOVERNMENT or PRIVATE.",
            )

        if identity in by_identity:
            summary.duplicates["Colleges"] += 1
            continue

        college = College(
            name=name,
            city=city,
            state=state,
            college_type=college_type,
            website=website,
            description=_optional_text(row, "description"),
        )
        _flush_row(
            session,
            "colleges.csv",
            row_number,
            f"college {name!r} in {city!r}, {state!r}",
            college,
        )
        by_identity[identity] = college
        by_name.setdefault(_normalize_name(name), []).append(college)
        summary.inserted["Colleges"] += 1

    return by_identity, by_name


def _parse_integer(
    value: str, filename: str, row_number: int, field_name: str, subject: str
) -> int:
    raw_value = value.strip()
    if not raw_value:
        _fail(filename, row_number, f"{field_name} is required for {subject}.")
    try:
        return int(raw_value)
    except ValueError:
        _fail(filename, row_number, f"{field_name} for {subject} must be an integer.")


def _import_courses(
    session: Session,
    summary: ImportSummary,
    colleges_by_name: dict[str, list[College]],
) -> dict[tuple[int, str], Course]:
    # A course is considered a duplicate when its college and normalized name already exist.
    by_identity: dict[tuple[int, str], Course] = {}
    for course in session.scalars(select(Course)):
        by_identity.setdefault((course.college_id, _normalize_name(course.name)), course)

    for row_number, row in _load_rows("courses.csv"):
        raw_course_name = (row.get("name") or "").strip()
        college_name = _required_text(
            row,
            "college_name",
            "courses.csv",
            row_number,
            context=f"course {raw_course_name!r}" if raw_course_name else None,
        )
        course_name = _required_text(
            row,
            "name",
            "courses.csv",
            row_number,
            "course name",
            context=f"college {college_name!r}",
        )
        subject = f"course {course_name!r} for college {college_name!r}"
        college = _resolve_college(college_name, colleges_by_name, "courses.csv", row_number)
        duration_years = _parse_integer(
            row["duration_years"], "courses.csv", row_number, "duration_years", subject
        )
        if duration_years <= 0:
            _fail("courses.csv", row_number, f"duration_years for {subject} must be positive.")

        identity = (college.id, _normalize_name(course_name))
        if identity in by_identity:
            summary.duplicates["Courses"] += 1
            continue

        course = Course(college_id=college.id, name=course_name, duration_years=duration_years)
        _flush_row(session, "courses.csv", row_number, subject, course)
        by_identity[identity] = course
        summary.inserted["Courses"] += 1

    return by_identity


def _parse_decimal(
    value: str,
    filename: str,
    row_number: int,
    field_name: str,
    subject: str,
    *,
    optional: bool = False,
    maximum: Decimal | None = None,
) -> Decimal | None:
    raw_value = value.strip()
    if not raw_value:
        if optional:
            return None
        _fail(filename, row_number, f"{field_name} is required for {subject}.")

    try:
        number = Decimal(raw_value)
    except InvalidOperation:
        _fail(filename, row_number, f"{field_name} for {subject} must be a valid number.")

    if not number.is_finite() or number < 0:
        _fail(filename, row_number, f"{field_name} for {subject} must be a non-negative number.")
    if maximum is not None and number > maximum:
        _fail(filename, row_number, f"{field_name} for {subject} must be between 0 and {maximum}.")
    return number


def _parse_datetime(value: str, filename: str, row_number: int, subject: str) -> datetime:
    raw_value = value.strip()
    if not raw_value:
        _fail(filename, row_number, f"last_verified_at is required for {subject}.")
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        _fail(filename, row_number, f"last_verified_at for {subject} must be a valid ISO datetime.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(filename, row_number, f"last_verified_at for {subject} must include a timezone.")
    return parsed


def _fee_identity(
    course_id: int,
    academic_year: str,
    tuition_per_year: Decimal,
    total_tuition: Decimal,
    fee_source_url: str,
    verified_at: datetime,
) -> tuple[int, str, Decimal, Decimal, str, datetime]:
    # Exact fee-row identity makes rerunning the same source row idempotent.
    return (
        course_id,
        _normalize_name(academic_year),
        tuition_per_year,
        total_tuition,
        fee_source_url,
        verified_at,
    )


def _import_course_fees(
    session: Session,
    summary: ImportSummary,
    colleges_by_name: dict[str, list[College]],
    courses_by_identity: dict[tuple[int, str], Course],
) -> None:
    known_fees = {
        _fee_identity(
            fee.course_id,
            fee.academic_year,
            fee.tuition_fee_per_year,
            fee.total_tuition_fee,
            fee.fee_source_url,
            fee.last_verified_at,
        )
        for fee in session.scalars(select(CourseFee))
    }

    for row_number, row in _load_rows("course_fees.csv"):
        raw_course_name = (row.get("course_name") or "").strip()
        college_name = _required_text(
            row,
            "college_name",
            "course_fees.csv",
            row_number,
            context=f"course {raw_course_name!r}" if raw_course_name else None,
        )
        course_name = _required_text(
            row,
            "course_name",
            "course_fees.csv",
            row_number,
            context=f"college {college_name!r}",
        )
        subject = f"course {course_name!r} for college {college_name!r}"
        college = _resolve_college(college_name, colleges_by_name, "course_fees.csv", row_number)
        course = courses_by_identity.get((college.id, _normalize_name(course_name)))
        if course is None:
            _fail("course_fees.csv", row_number, f"{subject} was not found.")

        academic_year = _required_text(
            row, "academic_year", "course_fees.csv", row_number, context=subject
        )
        tuition_per_year = _parse_decimal(
            row["tuition_fee_per_year"],
            "course_fees.csv",
            row_number,
            "tuition_fee_per_year",
            subject,
        )
        total_tuition = _parse_decimal(
            row["total_tuition_fee"],
            "course_fees.csv",
            row_number,
            "total_tuition_fee",
            subject,
        )
        assert tuition_per_year is not None and total_tuition is not None
        fee_source_url = _required_text(
            row, "fee_source_url", "course_fees.csv", row_number, context=subject
        )
        verified_at = _parse_datetime(row["last_verified_at"], "course_fees.csv", row_number, subject)

        identity = _fee_identity(
            course.id,
            academic_year,
            tuition_per_year,
            total_tuition,
            fee_source_url,
            verified_at,
        )
        if identity in known_fees:
            summary.duplicates["Course fees"] += 1
            continue

        fee = CourseFee(
            course_id=course.id,
            academic_year=academic_year,
            tuition_fee_per_year=tuition_per_year,
            total_tuition_fee=total_tuition,
            fee_source_url=fee_source_url,
            last_verified_at=verified_at,
        )
        _flush_row(session, "course_fees.csv", row_number, subject, fee)
        known_fees.add(identity)
        summary.inserted["Course fees"] += 1


def _route_identity(
    course_id: int,
    entrance_exam_id: int | None,
    admission_year: int,
    minimum_percentage: Decimal | None,
    required_subjects: str | None,
    other_requirements: str | None,
) -> tuple[int, int | None, int, Decimal | None, str | None, str | None]:
    # Full route identity preserves distinct routes while skipping exact repeated input rows.
    return (
        course_id,
        entrance_exam_id,
        admission_year,
        minimum_percentage,
        _normalize_name(required_subjects) if required_subjects else None,
        _normalize_name(other_requirements) if other_requirements else None,
    )


def _import_admission_routes(
    session: Session,
    summary: ImportSummary,
    exams_by_name: dict[str, EntranceExam],
    colleges_by_name: dict[str, list[College]],
    courses_by_identity: dict[tuple[int, str], Course],
) -> None:
    known_routes = {
        _route_identity(
            route.course_id,
            route.entrance_exam_id,
            route.admission_year,
            route.minimum_percentage,
            route.required_subjects,
            route.other_requirements,
        )
        for route in session.scalars(select(AdmissionRoute))
    }

    for row_number, row in _load_rows("admission_routes.csv"):
        raw_course_name = (row.get("course_name") or "").strip()
        college_name = _required_text(
            row,
            "college_name",
            "admission_routes.csv",
            row_number,
            context=f"course {raw_course_name!r}" if raw_course_name else None,
        )
        course_name = _required_text(
            row,
            "course_name",
            "admission_routes.csv",
            row_number,
            context=f"college {college_name!r}",
        )
        subject = f"course {course_name!r} for college {college_name!r}"
        college = _resolve_college(college_name, colleges_by_name, "admission_routes.csv", row_number)
        course = courses_by_identity.get((college.id, _normalize_name(course_name)))
        if course is None:
            _fail("admission_routes.csv", row_number, f"{subject} was not found.")

        exam_name = _optional_text(row, "entrance_exam_name")
        exam = None
        if exam_name is not None:
            exam = exams_by_name.get(_normalize_name(exam_name))
            if exam is None:
                _fail(
                    "admission_routes.csv",
                    row_number,
                    f"entrance exam {exam_name!r} for {subject} was not found.",
                )

        admission_year = _parse_integer(
            row["admission_year"], "admission_routes.csv", row_number, "admission_year", subject
        )
        minimum_percentage = _parse_decimal(
            row["minimum_percentage"],
            "admission_routes.csv",
            row_number,
            "minimum_percentage",
            subject,
            optional=True,
            maximum=Decimal("100"),
        )
        required_subjects = _optional_text(row, "required_subjects")
        other_requirements = _optional_text(row, "other_requirements")

        identity = _route_identity(
            course.id,
            exam.id if exam is not None else None,
            admission_year,
            minimum_percentage,
            required_subjects,
            other_requirements,
        )
        if identity in known_routes:
            summary.duplicates["Admission routes"] += 1
            continue

        route = AdmissionRoute(
            course_id=course.id,
            entrance_exam_id=exam.id if exam is not None else None,
            admission_year=admission_year,
            minimum_percentage=minimum_percentage,
            required_subjects=required_subjects,
            other_requirements=other_requirements,
        )
        _flush_row(session, "admission_routes.csv", row_number, subject, route)
        known_routes.add(identity)
        summary.inserted["Admission routes"] += 1


def _import_all(session: Session) -> ImportSummary:
    summary = ImportSummary()
    # Import parent records first so child CSV references can resolve to ORM records.
    exams_by_name = _import_entrance_exams(session, summary)
    _, colleges_by_name = _import_colleges(session, summary)
    courses_by_identity = _import_courses(session, summary, colleges_by_name)
    _import_course_fees(session, summary, colleges_by_name, courses_by_identity)
    _import_admission_routes(
        session, summary, exams_by_name, colleges_by_name, courses_by_identity
    )
    return summary


def _print_summary(summary: ImportSummary) -> None:
    print("Import completed successfully.\n")
    for filename, label in SUMMARY_LABELS.items():
        print(f"{label}: {summary.inserted[label]}")

    duplicate_total = sum(summary.duplicates.values())
    print(f"\nDuplicates skipped: {duplicate_total}")
    for filename, label in SUMMARY_LABELS.items():
        count = summary.duplicates[label]
        if count:
            print(f"  {label}: {count}")


def main() -> int:
    session = SessionLocal()
    try:
        # This context commits only if every file imports; any exception rolls back all rows.
        with session.begin():
            summary = _import_all(session)
    except ImportDataError as error:
        print(f"Import failed: {error} All database changes were rolled back.", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "Import failed because of a database operation. All database changes were rolled back.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print("Import failed unexpectedly. All database changes were rolled back.", file=sys.stderr)
        return 1
    finally:
        session.close()

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
