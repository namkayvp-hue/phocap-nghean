from __future__ import annotations

import inspect
import sys
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from sqlalchemy import and_, func, select, text
from starlette.requests import Request

from app.database import SessionLocal
from app.models import Role, School, User
from app.permissions import (
    SCHOOL_ROLE_CODE,
    TEACHER_ROLE_CODE,
    normalize_role_code,
)
from app.routers import surveys
from app.survey_models import (
    Household,
    SurveyBatch,
    SurveyForm,
    SurveyFormInvestigator,
)

TARGET_USERNAME = "truong_40413507"
TARGET_BATCH_ID = 3


def section(title: str) -> None:
    print()
    print("=" * 118)
    print(title)
    print("=" * 118)


def make_request(auth_user: dict) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": f"/dieu-tra/{TARGET_BATCH_ID}/ho-dan",
        "raw_path": f"/dieu-tra/{TARGET_BATCH_ID}/ho-dan".encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
        "scheme": "http",
        "root_path": "",
        "http_version": "1.1",
        "auth_user": auth_user,
    }
    return Request(scope)


def main() -> None:
    print("KIỂM TRA BÀI 13B-10 V3.9 - NORMALIZE ROLE + ROUTE DANH SÁCH HỘ")
    print("CHỈ ĐỌC - KHÔNG SỬA DATABASE / SOURCE")

    db = SessionLocal()
    try:
        row = db.execute(
            select(
                User.id,
                User.username,
                User.full_name,
                User.school_id,
                User.commune_id,
                User.is_active,
                Role.code.label("raw_role_code"),
                Role.name.label("role_name"),
                School.name.label("school_name"),
            )
            .join(Role, Role.id == User.role_id)
            .outerjoin(School, School.id == User.school_id)
            .where(User.username == TARGET_USERNAME)
        ).mappings().first()

        if row is None:
            raise RuntimeError(f"Không tìm thấy {TARGET_USERNAME}")

        raw_role = str(row["raw_role_code"] or "")
        normalized_role = normalize_role_code(raw_role)

        section("1. ROLE THỰC TẾ VÀ ROLE SAU NORMALIZE")
        print(f"username={row['username']}")
        print(f"school={row['school_name']}")
        print(f"school_id={row['school_id']}")
        print(f"commune_id={row['commune_id']}")
        print(f"raw_role_code={raw_role!r}")
        print(f"normalize_role_code(raw)={normalized_role!r}")
        print(f"SCHOOL_ROLE_CODE={SCHOOL_ROLE_CODE!r}")
        print(f"TEACHER_ROLE_CODE={TEACHER_ROLE_CODE!r}")
        print(
            "normalized_is_school=",
            normalized_role == SCHOOL_ROLE_CODE,
        )

        auth_user = {
            "id": int(row["id"]),
            "username": row["username"],
            "full_name": row["full_name"],
            "role_code": normalized_role,
            "role_name": row["role_name"],
            "school_id": row["school_id"],
            "commune_id": row["commune_id"],
            "unit_name": row["school_name"],
        }
        request = make_request(auth_user)

        section("2. AUTH_USER GIẢ LẬP ĐÚNG NHƯ MIDDLEWARE")
        print(auth_user)

        section("3. BỘ LỌC ĐỢT - SAU NORMALIZE")
        batch_filters = surveys.tao_bo_loc_dot_theo_nguoi_dung(request)
        for i, expr in enumerate(batch_filters, start=1):
            print(f"filter_dot_{i}: {expr}")

        batch_count = db.scalar(
            select(func.count(SurveyBatch.id)).where(
                SurveyBatch.id == TARGET_BATCH_ID,
                *batch_filters,
            )
        )
        print(f"batch_count_orm={int(batch_count or 0)}")

        section("4. BỘ LỌC PHIẾU - SAU NORMALIZE")
        form_filters = surveys.tao_bo_loc_phieu_theo_nguoi_dung(request)
        for i, expr in enumerate(form_filters, start=1):
            print(f"filter_phieu_{i}: {expr}")

        form_count = db.scalar(
            select(func.count(SurveyForm.id)).where(
                SurveyForm.survey_batch_id == TARGET_BATCH_ID,
                *form_filters,
            )
        )
        print(f"form_count_orm={int(form_count or 0)}")

        section("5. REPLICATE ĐÚNG BASE FILTER CỦA danh_sach_ho_dan")
        filters = [
            SurveyForm.survey_batch_id == TARGET_BATCH_ID,
            *form_filters,
        ]

        total_records = db.scalar(
            select(func.count(SurveyForm.id))
            .join(
                Household,
                Household.id == SurveyForm.household_id,
            )
            .where(*filters)
        )
        print(f"route_total_records={int(total_records or 0)}")

        forms = db.scalars(
            select(SurveyForm)
            .join(
                Household,
                Household.id == SurveyForm.household_id,
            )
            .where(*filters)
            .order_by(SurveyForm.id.asc())
        ).all()

        print(f"route_forms_len={len(forms)}")
        for form in forms:
            print(
                f"form_id={form.id} | form_number={form.form_number} | "
                f"household_id={form.household_id}"
            )

        section("6. KIỂM TRA school_teacher_assignment TRONG ROUTE")
        school_id = int(row["school_id"])
        school_teacher_assignment = SurveyForm.investigators.any(
            SurveyFormInvestigator.user.has(
                and_(
                    User.school_id == school_id,
                    User.role.has(code=TEACHER_ROLE_CODE),
                )
            )
        )

        assigned_count = db.scalar(
            select(func.count(SurveyForm.id)).where(
                SurveyForm.survey_batch_id == TARGET_BATCH_ID,
                *form_filters,
                school_teacher_assignment,
            )
        )
        print(f"assigned_count_nested_role_code={int(assigned_count or 0)}")

        section("7. SO SÁNH school_teacher_assignment BẰNG SQL TRỰC TIẾP")
        raw_teacher_count = db.execute(
            text(
                """
                SELECT COUNT(DISTINCT sf.id)
                FROM survey_forms sf
                JOIN survey_form_investigators sfi
                  ON sfi.survey_form_id = sf.id
                JOIN users u
                  ON u.id = sfi.user_id
                JOIN roles r
                  ON r.id = u.role_id
                WHERE sf.survey_batch_id = :batch_id
                  AND u.school_id = :school_id
                """
            ),
            {
                "batch_id": TARGET_BATCH_ID,
                "school_id": school_id,
            },
        ).scalar_one()
        print(f"raw_school_count={int(raw_teacher_count or 0)}")

        role_rows = db.execute(
            text(
                """
                SELECT DISTINCT
                    r.code AS raw_role_code,
                    r.name AS role_name,
                    COUNT(*) AS assignment_rows
                FROM survey_forms sf
                JOIN survey_form_investigators sfi
                  ON sfi.survey_form_id = sf.id
                JOIN users u
                  ON u.id = sfi.user_id
                JOIN roles r
                  ON r.id = u.role_id
                WHERE sf.survey_batch_id = :batch_id
                  AND u.school_id = :school_id
                GROUP BY r.code, r.name
                """
            ),
            {
                "batch_id": TARGET_BATCH_ID,
                "school_id": school_id,
            },
        ).mappings().all()

        print("Raw role code của GV được phân công:")
        for rr in role_rows:
            print(dict(rr))

        section("8. SOURCE HAI HÀM LỌC")
        print(inspect.getsource(surveys.tao_bo_loc_dot_theo_nguoi_dung))
        print(inspect.getsource(surveys.tao_bo_loc_phieu_theo_nguoi_dung))

        section("9. KẾT LUẬN TỰ ĐỘNG")
        b = int(batch_count or 0)
        f = int(form_count or 0)
        t = int(total_records or 0)
        a = int(assigned_count or 0)
        raw = int(raw_teacher_count or 0)

        print(
            f"batch={b} | form_scope={f} | route_total={t} | "
            f"assigned_nested={a} | raw_school={raw}"
        )

        if b == 1 and f == 5 and t == 5:
            print(
                "=> Bộ lọc đợt và phiếu ĐÚNG sau normalize. "
                "Nếu giao diện vẫn 0 thì server đang chạy source khác/cũ "
                "hoặc có tiến trình Uvicorn chưa được khởi động lại đúng."
            )
        elif b == 1 and f == 0 and raw == 5:
            print(
                "=> Lỗi nằm trong tao_bo_loc_phieu_theo_nguoi_dung() "
                "hoặc relationship ORM."
            )
        elif b == 1 and f == 5 and a == 0 and raw == 5:
            print(
                "=> Base list phải có 5 phiếu; riêng school_teacher_assignment "
                "bị sai vì so sánh User.role.has(code=TEACHER_ROLE_CODE) "
                "với role code lưu thô trong DB."
            )
        elif b == 0:
            print(
                "=> Bộ lọc đợt vẫn sai trong source đang nạp; "
                "cần xem filter_dot ở trên."
            )
        else:
            print(
                "=> Kết quả khác dự kiến. Gửi toàn bộ mục 1-9 để sửa đúng."
            )

        print()
        print("HOÀN TẤT - KHÔNG GHI DỮ LIỆU.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
