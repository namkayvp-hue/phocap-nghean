from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal
from app.survey_models import Household, SurveyPerson


HOUSEHOLD_CODE = "HO-16681-000001"
TARGET_CODES = {"DT-00000004", "DT-00000005"}


def main() -> None:
    with SessionLocal() as db:
        household = db.scalar(
            select(Household).where(Household.code == HOUSEHOLD_CODE)
        )

        if household is None:
            print(f"Không tìm thấy hộ {HOUSEHOLD_CODE}.")
            return

        people = db.scalars(
            select(SurveyPerson).where(
                SurveyPerson.household_id == household.id,
                SurveyPerson.code.in_(TARGET_CODES),
                SurveyPerson.is_active.is_(True),
            )
        ).all()

        changed = 0

        for person in people:
            is_incomplete = (
                person.date_of_birth is None
                or not person.gender
                or not person.ethnic_group
                or not person.relationship_to_head
            )

            if not is_incomplete:
                print(
                    f"Bỏ qua {person.code} - {person.full_name}: "
                    "bản ghi đã có đủ thông tin bắt buộc."
                )
                continue

            person.is_active = False
            person.student_id = None
            changed += 1

            print(
                f"Đã ẩn bản ghi thử nghiệm chưa đầy đủ: "
                f"{person.code} - {person.full_name}."
            )

        if changed:
            db.commit()
            print(f"Hoàn tất: đã xử lý {changed} bản ghi.")
        else:
            db.rollback()
            print("Không có bản ghi nào cần xử lý.")


if __name__ == "__main__":
    main()
