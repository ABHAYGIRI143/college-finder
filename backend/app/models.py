from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLAlchemyEnum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class CollegeType(str, Enum):
    GOVERNMENT = "GOVERNMENT"
    PRIVATE = "PRIVATE"


class College(Base):
    __tablename__ = "colleges"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    college_type: Mapped[CollegeType] = mapped_column(
        SQLAlchemyEnum(CollegeType, name="college_type", native_enum=True),
        nullable=False,
        index=True,
    )
    website: Mapped[str] = mapped_column(String(2048), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    courses: Mapped[list["Course"]] = relationship(
        back_populates="college", cascade="all, delete-orphan"
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(
        ForeignKey("colleges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_years: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    college: Mapped[College] = relationship(back_populates="courses")
    fees: Mapped[list["CourseFee"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    admission_routes: Mapped[list["AdmissionRoute"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class CourseFee(Base):
    __tablename__ = "course_fees"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    tuition_fee_per_year: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_tuition_fee: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    fee_source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    course: Mapped[Course] = relationship(back_populates="fees")


class EntranceExam(Base):
    __tablename__ = "entrance_exams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    admission_routes: Mapped[list["AdmissionRoute"]] = relationship(
        back_populates="entrance_exam"
    )


class AdmissionRoute(Base):
    __tablename__ = "admission_routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entrance_exam_id: Mapped[int | None] = mapped_column(
        ForeignKey("entrance_exams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    minimum_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    required_subjects: Mapped[str | None] = mapped_column(Text, nullable=True)
    admission_year: Mapped[int] = mapped_column(nullable=False, index=True)
    other_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)

    course: Mapped[Course] = relationship(back_populates="admission_routes")
    entrance_exam: Mapped[EntranceExam | None] = relationship(
        back_populates="admission_routes"
    )
