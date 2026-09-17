from __future__ import annotations

from starlette.requests import Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import User
from app.permissions import normalize_role_code
from app.routers import surveys
from app.survey_models import SurveyBatch


TARGET_USERNAME = "xa_17827"
TARGET_YEAR_ID = 2
TARGET_COMMUNE_ID = 114


def make_request(auth_user: dict) -> Request:
    query = (
        "school_year_id=2&commune_id=114&survey_status="
    ).encode("utf-8")

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/dieu-tra",
        "raw_path": b"/dieu-tra",
        "query_string": query,
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
        "root_path": "",
        "auth_user": auth_user,
    }
    return Request(scope)


def batch_desc(item) -> str:
    return (
        f"id={item.id} | code={item.code} | "
        f"year={item.school_year_id} | "
        f"commune={item.commune_id} | "
        f"status={item.status}"
    )


def main() -> int:
    print("=" * 118)
    print("KIỂM TRA CONTEXT DANH SÁCH ĐỢT XÃ NGHI LỘC V6")
    print("CHỈ ĐỌC - KHÔNG INSERT / UPDATE / DELETE - KHÔNG SỬA SOURCE")
    print("=" * 118)

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

        if user is None:
            print("KHÔNG tìm thấy user:", TARGET_USERNAME)
            return 0

        role_code = normalize_role_code(
            user.role.code if user.role else ""
        )

        auth_user = {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role_code": role_code,
            "role_name": getattr(user.role, "name", ""),
            "commune_id": user.commune_id,
            "school_id": user.school_id,
            "unit_name": getattr(user.commune, "name", ""),
        }

        print("\n1. AUTH_USER DÙNG CHO ROUTE")
        print("-" * 118)
        for key, value in auth_user.items():
            print(f"{key:12} = {value!r}")

        print("\n2. SQL TRỰC TIẾP")
        print("-" * 118)
        direct = db.scalars(
            select(SurveyBatch).where(
                SurveyBatch.school_year_id == TARGET_YEAR_ID,
                SurveyBatch.commune_id == TARGET_COMMUNE_ID,
            )
        ).all()

        print("Số batch SQL trực tiếp =", len(direct))
        for item in direct:
            print(" -", batch_desc(item))

        print("\n3. DỮ LIỆU DANH MỤC MÀ ROUTE NHẬN")
        print("-" * 118)
        school_years, communes = surveys.lay_du_lieu_danh_muc(db)

        print(
            "school_year ids =",
            [item.id for item in school_years],
        )
        print(
            "Có year_id=2? =",
            TARGET_YEAR_ID in {item.id for item in school_years},
        )

        nghi_loc = [
            item
            for item in communes
            if item.id == TARGET_COMMUNE_ID
        ]
        print("Có commune_id=114? =", bool(nghi_loc))
        for item in nghi_loc:
            print(
                f" - id={item.id} | code={item.code} | "
                f"name={item.name}"
            )

        print("\n4. HELPER SCOPE")
        print("-" * 118)
        request = make_request(auth_user)

        filters = surveys.tao_bo_loc_dot_theo_nguoi_dung(
            request
        )
        print("Số filter helper =", len(filters))
        for i, f in enumerate(filters, 1):
            print(f" filter {i}: {f}")

        helper_stmt = select(SurveyBatch).where(
            *filters,
            SurveyBatch.school_year_id == TARGET_YEAR_ID,
            SurveyBatch.commune_id == TARGET_COMMUNE_ID,
        )
        helper_rows = db.scalars(helper_stmt).all()
        print(
            "Kết quả helper + year + commune =",
            len(helper_rows),
        )
        for item in helper_rows:
            print(" -", batch_desc(item))

        print("\n5. GỌI TRỰC TIẾP HÀM danh_sach_dot_dieu_tra()")
        print("-" * 118)

        try:
            response = surveys.danh_sach_dot_dieu_tra(
                request=request,
                school_year_id=TARGET_YEAR_ID,
                commune_id=TARGET_COMMUNE_ID,
                survey_status="",
                status=None,
                db=db,
            )
        except Exception as exc:
            print("ROUTE NÉM LỖI:", repr(exc))
            return 0

        print("response type =", type(response))

        context = getattr(response, "context", None)
        template = getattr(response, "template", None)

        if template is not None:
            print(
                "template =",
                getattr(template, "name", repr(template)),
            )
        else:
            print("template = (không đọc được)")

        if not isinstance(context, dict):
            print("Không lấy được response.context dạng dict.")
            return 0

        print("\n6. CONTEXT THỰC TẾ GỬI SANG TEMPLATE")
        print("-" * 118)

        print(
            "selected_school_year_id =",
            context.get("selected_school_year_id"),
        )
        print(
            "selected_commune_id     =",
            context.get("selected_commune_id"),
        )
        print(
            "selected_status         =",
            repr(context.get("selected_status")),
        )
        print(
            "empty_scope_message     =",
            repr(context.get("empty_scope_message")),
        )

        context_user = context.get("nguoi_dung") or {}
        print("context user =", context_user)

        batches = context.get("survey_batches")
        if batches is None:
            print("survey_batches = MISSING/NONE")
            batch_count = -1
        else:
            batch_count = len(batches)
            print("survey_batches length =", batch_count)
            for item in batches:
                print(" -", batch_desc(item))

        print("\n7. THỬ ROUTE KHÔNG TRUYỀN BỘ LỌC NĂM/XÃ")
        print("-" * 118)

        response_all = surveys.danh_sach_dot_dieu_tra(
            request=make_request(auth_user),
            school_year_id=None,
            commune_id=None,
            survey_status="",
            status=None,
            db=db,
        )
        context_all = getattr(response_all, "context", {}) or {}
        batches_all = context_all.get("survey_batches") or []

        print(
            "survey_batches không truyền filter =",
            len(batches_all),
        )
        for item in batches_all[:20]:
            print(" -", batch_desc(item))

        print("\n8. KẾT LUẬN TỰ ĐỘNG")
        print("-" * 118)

        if batch_count == 1:
            print(
                "CHỐT: Chính hàm danh_sach_dot_dieu_tra() "
                "trả đúng 1 batch cho Xã Nghi Lộc."
            )
            print(
                "=> Ảnh trình duyệt 0 đợt không đến từ kết quả "
                "của hàm này."
            )
            print(
                "=> Bước sau sẽ kiểm tra request HTTP thực tế/"
                "session/endpoint được trình duyệt gọi."
            )
        elif batch_count == 0:
            print(
                "CHỐT: Hàm danh_sach_dot_dieu_tra() trực tiếp "
                "đang trả 0 batch."
            )
            print(
                "=> Lỗi nằm trong logic route/danh mục/filter "
                "và có thể sửa trực tiếp surveys.py."
            )
        else:
            print(
                "Kết quả context bất thường; dùng chi tiết "
                "ở các mục trên để xử lý."
            )

    print("\nHãy COPY TOÀN BỘ kết quả V6 gửi lại ChatGPT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
