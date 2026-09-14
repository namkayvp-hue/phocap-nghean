from __future__ import annotations

import inspect
import sys
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from sqlalchemy import func, select, text
from starlette.requests import Request

from app.database import SessionLocal
from app.models import Role, School, User
from app.routers import surveys
from app.survey_models import SurveyBatch, SurveyForm, SurveyFormInvestigator


TARGET_USERNAME = "truong_40413507"  # THCS Hải Hòa
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
    print("KIỂM TRA BÀI 13B-10 V3.8 - PHẠM VI PHIẾU TẠI TRƯỜNG")
    print("CHỈ ĐỌC - KHÔNG SỬA DATABASE / SOURCE")

    db = SessionLocal()
    try:
        section("1. TÀI KHOẢN THCS HẢI HÒA")

        row = db.execute(
            select(
                User.id,
                User.username,
                User.full_name,
                User.school_id,
                User.commune_id,
                User.is_active,
                Role.code.label("role_code"),
                Role.name.label("role_name"),
                School.name.label("school_name"),
            )
            .join(Role, Role.id == User.role_id)
            .outerjoin(School, School.id == User.school_id)
            .where(User.username == TARGET_USERNAME)
        ).mappings().first()

        if row is None:
            raise RuntimeError(
                f"Không tìm thấy tài khoản {TARGET_USERNAME}"
            )

        for key, value in row.items():
            print(f"{key}: {value}")

        auth_user = {
            "id": int(row["id"]),
            "username": row["username"],
            "full_name": row["full_name"],
            "role_code": row["role_code"],
            "role_name": row["role_name"],
            "school_id": row["school_id"],
            "commune_id": row["commune_id"],
        }
        request = make_request(auth_user)

        section("2. SOURCE THỰC TẾ ĐANG CHẠY - HÀM LỌC ĐỢT")
        print(inspect.getsource(surveys.tao_bo_loc_dot_theo_nguoi_dung))

        section("3. SOURCE THỰC TẾ ĐANG CHẠY - HÀM LỌC PHIẾU")
        print(inspect.getsource(surveys.tao_bo_loc_phieu_theo_nguoi_dung))

        section("4. SOURCE THỰC TẾ ĐANG CHẠY - ROUTE DANH SÁCH HỘ")
        route_source = inspect.getsource(surveys.danh_sach_ho_dan)
        print(route_source[:12000])
        if len(route_source) > 12000:
            print("\n...[đã rút gọn phần cuối route]...")

        section("5. KIỂM TRA ĐỢT #3 BẰNG ĐÚNG ORM FILTER CỦA APP")
        batch_filters = surveys.tao_bo_loc_dot_theo_nguoi_dung(request)
        print(f"Số biểu thức filter đợt: {len(batch_filters)}")
        for idx, expr in enumerate(batch_filters, start=1):
            print(f"filter_dot_{idx}: {expr}")

        batch_count = db.scalar(
            select(func.count(SurveyBatch.id))
            .where(
                SurveyBatch.id == TARGET_BATCH_ID,
                *batch_filters,
            )
        )
        print(f"ORM batch_count: {int(batch_count or 0)}")

        section("6. KIỂM TRA PHIẾU ĐỢT #3 BẰNG ĐÚNG ORM FILTER CỦA APP")
        form_filters = surveys.tao_bo_loc_phieu_theo_nguoi_dung(request)
        print(f"Số biểu thức filter phiếu: {len(form_filters)}")
        for idx, expr in enumerate(form_filters, start=1):
            print(f"filter_phieu_{idx}: {expr}")

        orm_form_count = db.scalar(
            select(func.count(SurveyForm.id))
            .where(
                SurveyForm.survey_batch_id == TARGET_BATCH_ID,
                *form_filters,
            )
        )
        print(f"ORM form_count: {int(orm_form_count or 0)}")

        section("7. KIỂM TRA PHIẾU BẰNG SQL TRỰC TIẾP")
        direct_count = db.execute(
            text(
                """
                SELECT COUNT(DISTINCT sf.id)
                FROM survey_forms AS sf
                JOIN survey_form_investigators AS sfi
                    ON sfi.survey_form_id = sf.id
                JOIN users AS u
                    ON u.id = sfi.user_id
                WHERE sf.survey_batch_id = :batch_id
                  AND u.school_id = :school_id
                  AND u.is_active = 1
                """
            ),
            {
                "batch_id": TARGET_BATCH_ID,
                "school_id": int(row["school_id"]),
            },
        ).scalar_one()

        print(f"RAW SQL form_count: {int(direct_count or 0)}")

        section("8. LIỆT KÊ 5 PHIẾU VÀ 3 GV TRONG TỔ")
        rows = db.execute(
            text(
                """
                SELECT
                    sf.id AS form_id,
                    sf.form_number,
                    sfi.order_number,
                    sfi.user_id,
                    u.username,
                    u.full_name,
                    u.school_id,
                    u.is_active
                FROM survey_forms AS sf
                JOIN survey_form_investigators AS sfi
                    ON sfi.survey_form_id = sf.id
                JOIN users AS u
                    ON u.id = sfi.user_id
                WHERE sf.survey_batch_id = :batch_id
                  AND u.school_id = :school_id
                ORDER BY sf.id, sfi.order_number, sfi.id
                """
            ),
            {
                "batch_id": TARGET_BATCH_ID,
                "school_id": int(row["school_id"]),
            },
        ).mappings().all()

        if not rows:
            print("(không có)")
        else:
            for item in rows:
                print(
                    " | ".join(
                        f"{key}={item[key]}"
                        for key in item.keys()
                    )
                )

        section("9. KIỂM TRA RELATIONSHIP SurveyFormInvestigator.user")
        try:
            rel = inspect.getsource(SurveyFormInvestigator)
            print(rel[:10000])
        except Exception as exc:
            print(f"Không đọc được source class: {exc}")
            mapper = SurveyFormInvestigator.__mapper__
            print("Relationships:")
            for rel in mapper.relationships:
                print(
                    f"- {rel.key}: target={rel.mapper.class_.__name__}, "
                    f"local_remote_pairs={rel.local_remote_pairs}"
                )

        section("10. KẾT LUẬN TỰ ĐỘNG")
        orm_value = int(orm_form_count or 0)
        raw_value = int(direct_count or 0)
        batch_value = int(batch_count or 0)

        print(f"batch_count ORM = {batch_value}")
        print(f"form_count ORM = {orm_value}")
        print(f"form_count RAW SQL = {raw_value}")

        if batch_value == 1 and orm_value == raw_value and raw_value > 0:
            print(
                "=> Bộ lọc ORM đúng. Nếu giao diện vẫn 0, "
                "route danh_sach_ho_dan đang thêm điều kiện khác hoặc "
                "server chưa nạp đúng source."
            )
        elif batch_value == 1 and raw_value > 0 and orm_value == 0:
            print(
                "=> ĐÃ XÁC ĐỊNH: lỗi nằm trong "
                "tao_bo_loc_phieu_theo_nguoi_dung() / relationship ORM."
            )
        elif raw_value == 0:
            print(
                "=> Dữ liệu phân công trực tiếp hiện không còn phiếu cho trường; "
                "cần kiểm tra database."
            )
        else:
            print(
                "=> Kết quả khác dự kiến. Gửi toàn bộ output này để sửa đúng source."
            )

        print()
        print("HOÀN TẤT - KHÔNG CÓ THAO TÁC GHI DỮ LIỆU.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
