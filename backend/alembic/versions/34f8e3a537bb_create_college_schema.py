"""create college schema

Revision ID: 34f8e3a537bb
Revises: 7940ea356979
Create Date: 2026-10-02 13:38:06.778299

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


college_type = postgresql.ENUM(
    "GOVERNMENT",
    "PRIVATE",
    name="college_type",
    create_type=False,
)


# revision identifiers, used by Alembic.
revision: str = '34f8e3a537bb'
down_revision: Union[str, Sequence[str], None] = '7940ea356979'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    college_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "colleges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=120), nullable=False),
        sa.Column("college_type", college_type, nullable=False),
        sa.Column("website", sa.String(length=2048), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_colleges_city", "colleges", ["city"], unique=False)
    op.create_index("ix_colleges_college_type", "colleges", ["college_type"], unique=False)
    op.create_index("ix_colleges_state", "colleges", ["state"], unique=False)

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("college_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("duration_years", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["college_id"], ["colleges.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_courses_college_id", "courses", ["college_id"], unique=False)

    op.create_table(
        "course_fees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("academic_year", sa.String(length=9), nullable=False),
        sa.Column("tuition_fee_per_year", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_tuition_fee", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("fee_source_url", sa.String(length=2048), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_course_fees_academic_year", "course_fees", ["academic_year"], unique=False)
    op.create_index("ix_course_fees_course_id", "course_fees", ["course_id"], unique=False)

    op.create_table(
        "entrance_exams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "admission_routes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("entrance_exam_id", sa.Integer(), nullable=True),
        sa.Column("minimum_percentage", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("required_subjects", sa.Text(), nullable=True),
        sa.Column("admission_year", sa.Integer(), nullable=False),
        sa.Column("other_requirements", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["entrance_exam_id"], ["entrance_exams.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admission_routes_admission_year", "admission_routes", ["admission_year"], unique=False
    )
    op.create_index(
        "ix_admission_routes_course_id", "admission_routes", ["course_id"], unique=False
    )
    op.create_index(
        "ix_admission_routes_entrance_exam_id",
        "admission_routes",
        ["entrance_exam_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_admission_routes_entrance_exam_id", table_name="admission_routes")
    op.drop_index("ix_admission_routes_course_id", table_name="admission_routes")
    op.drop_index("ix_admission_routes_admission_year", table_name="admission_routes")
    op.drop_table("admission_routes")
    op.drop_index("ix_course_fees_course_id", table_name="course_fees")
    op.drop_index("ix_course_fees_academic_year", table_name="course_fees")
    op.drop_table("course_fees")
    op.drop_index("ix_courses_college_id", table_name="courses")
    op.drop_table("courses")
    op.drop_table("entrance_exams")
    op.drop_index("ix_colleges_state", table_name="colleges")
    op.drop_index("ix_colleges_college_type", table_name="colleges")
    op.drop_index("ix_colleges_city", table_name="colleges")
    op.drop_table("colleges")

    college_type.drop(op.get_bind(), checkfirst=True)
