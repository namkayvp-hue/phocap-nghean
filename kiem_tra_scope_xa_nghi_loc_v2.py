from __future__ import annotations

import inspect
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from starlette.requests import Request

PROJECT = Path(r"C:\PhoCap")

from app.database import SessionLocal
from app.models import User
from app.permissions import (
    COMMUNE_ROLE_CODE,
    SCHOOL_ROLE_CODE,
    TEACHER_ROLE_CODE,
    PROVINCE_READ_ROLE_CODES,
    normalize_role_code,
    is_province_reader,
)
from app.survey_models import SurveyBatch
from app.routers import surveys


TARGET_USERNAME = "xa_17827"
TARGET_YEAR_ID = 2
TARGET_COMMUNE_ID = 114


def fake_request(auth_user: dict) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/dieu-tra",
        "raw_path": b"/dieu-tra",
        "query_string": b"school_year_id=2&commune_id=114&survey_status=",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
        "auth_user": auth_user,
    }
    return Request(scope)


def main() -> int:
    print("=" * 116)
    print("KIỂM TRA SCOPE XÃ NGHI LỘC V2")
    print("CHỈ ĐỌC - KHÔNG INSERT / UPDATE / DELETE")
    print("=" * 116)

    print("\n1. HẰNG QUYỀN ĐANG CHẠY")
    print("-" * 116)
    print("COMMUNE_ROLE_CODE       =", repr(COMMUNE_ROLE_CODE))
    print("SCHOOL_ROLE_CODE        =", repr(SCHOOL_ROLE_CODE))
    print("TEACHER_ROLE_CODE       =", repr(TEACHER_ROLE_CODE))
    print("PROVINCE_READ_ROLE_CODES=", repr(PROVINCE_READ_ROLE_CODES))

    with SessionLocal() as db:
        user = db.scalar(
            select(User)
            .options(
                selectinload(User.role),
                selectinload(User.commune),
                selectinload(User.school),
            )
            .where(User.username == TARGET_USERNAME)
            .limit(1)
        )

        print("\n2. TÀI KHOẢN XÃ NGHI LỘC")
        print("-" * 116)

        if user is None:
            print("KHÔNG tìm thấy user:", TARGET_USERNAME)
            return 0

        raw_role = str(user.role.code if user.role else "")
        normalized_role = normalize_role_code(raw_role)

        print("user.id            =", user.id)
        print("username           =", user.username)
        print("full_name          =", user.full_name)
        print("role.id            =", getattr(user, "role_id", None))
        print("role.code RAW      =", repr(raw_role))
        print("role.code NORMAL   =", repr(normalized_role))
        print("role.name          =", getattr(user.role, "name", None))
        print("commune_id         =", user.commune_id)
        print("commune.name       =", getattr(user.commune, "name", None))
        print("school_id          =", user.school_id)
        print(
            "NORMAL == COMMUNE? =",
            normalized_role == COMMUNE_ROLE_CODE,
        )
        print(
            "is_province_reader =",
            is_province_reader(normalized_role),
        )

        auth_user = {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role_code": normalized_role,
            "role_name": getattr(user.role, "name", ""),
            "commune_id": user.commune_id,
            "school_id": user.school_id,
            "unit_name": getattr(user.commune, "name", ""),
        }

        print("\n3. TRUY VẤN TRỰC TIẾP BẰNG SQLALCHEMY MODEL")
        print("-" * 116)

        direct = db.scalars(
            select(SurveyBatch).where(
                SurveyBatch.school_year_id == TARGET_YEAR_ID,
                SurveyBatch.commune_id == TARGET_COMMUNE_ID,
            )
        ).all()

        print("Số batch trực tiếp =", len(direct))
        for b in direct:
            print(
                f" - id={b.id} | code={b.code} | "
                f"year={b.school_year_id} | commune={b.commune_id} | "
                f"status={b.status}"
            )

        print("\n4. CHẠY ĐÚNG HÀM tao_bo_loc_dot_theo_nguoi_dung() HIỆN TẠI")
        print("-" * 116)

        request = fake_request(auth_user)

        try:
            filters = surveys.tao_bo_loc_dot_theo_nguoi_dung(request)
            print("Số filter trả về =", len(filters))
            for i, item in enumerate(filters, 1):
                print(f" filter {i}:", str(item))

            final_filters = list(filters)
            final_filters.append(
                SurveyBatch.school_year_id == TARGET_YEAR_ID
            )
            final_filters.append(
                SurveyBatch.commune_id == TARGET_COMMUNE_ID
            )

            stmt = select(SurveyBatch).where(*final_filters)

            print("\nSQL mô phỏng:")
            try:
                print(
                    stmt.compile(
                        db.get_bind(),
                        compile_kwargs={"literal_binds": True},
                    )
                )
            except Exception as exc:
                print("Không compile literal được:", exc)
                print(stmt)

            simulated = db.scalars(stmt).all()
            print("\nKẾT QUẢ SAU BỘ LỌC ROUTER =", len(simulated))
            for b in simulated:
                print(
                    f" - id={b.id} | code={b.code} | "
                    f"year={b.school_year_id} | commune={b.commune_id}"
                )

        except Exception as exc:
            print("LỖI khi chạy helper:", repr(exc))

        print("\n5. SOURCE THỰC TẾ CỦA HÀM PHẠM VI")
        print("-" * 116)
        try:
            print(inspect.getsource(
                surveys.tao_bo_loc_dot_theo_nguoi_dung
            ))
        except Exception as exc:
            print("Không đọc được source helper:", repr(exc))

        print("\n6. SOURCE ĐẦU HÀM danh_sach_dot_dieu_tra")
        print("-" * 116)
        try:
            src = inspect.getsource(
                surveys.danh_sach_dot_dieu_tra
            )
            lines = src.splitlines()
            for line in lines[:100]:
                print(line)
        except Exception as exc:
            print("Không đọc được source route:", repr(exc))

        print("\n7. FILE MODULE ĐANG ĐƯỢC IMPORT")
        print("-" * 116)
        print("surveys module =", inspect.getsourcefile(surveys))
        try:
            import app.permissions as permissions
            print(
                "permissions module =",
                inspect.getsourcefile(permissions),
            )
        except Exception as exc:
            print("permissions module error:", repr(exc))

        print("\n8. KẾT LUẬN TỰ ĐỘNG")
        print("-" * 116)

        if not direct:
            print(
                "BẤT THƯỜNG: SQLAlchemy model không đọc được batch "
                "mà SQLite thô đã thấy."
            )
        else:
            try:
                filters2 = surveys.tao_bo_loc_dot_theo_nguoi_dung(
                    fake_request(auth_user)
                )
                stmt2 = select(func.count(SurveyBatch.id)).where(
                    *filters2,
                    SurveyBatch.school_year_id == TARGET_YEAR_ID,
                    SurveyBatch.commune_id == TARGET_COMMUNE_ID,
                )
                total2 = int(db.scalar(stmt2) or 0)

                if total2 == 1:
                    print(
                        "Helper scope hiện tại trả đúng 1 batch."
                    )
                    print(
                        "=> Lỗi nằm ở phần xử lý danh sách/route/template "
                        "thực tế hoặc tiến trình Uvicorn đang dùng code cũ."
                    )
                else:
                    print(
                        "Helper scope hiện tại làm mất batch; "
                        f"kết quả={total2}."
                    )
                    print(
                        "=> Có thể sửa trực tiếp hàm scope cấp xã."
                    )
            except Exception as exc:
                print(
                    "Không chạy được kết luận helper:",
                    repr(exc),
                )

    print("\nHãy COPY TOÀN BỘ kết quả gửi lại ChatGPT.")
    print("Script chỉ SELECT và đọc source; không sửa database/source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
