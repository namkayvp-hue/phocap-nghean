from __future__ import annotations

import base64
import json
import re
import traceback

from itsdangerous import TimestampSigner
from sqlalchemy import event

import app.main as main_mod
import app.database as database
from app.routers import surveys


TARGET_USER_ID = 13359
TARGET_BATCH_CODE = "DT-17827-20262027-001"


def get_session_config():
    app = main_mod.app

    secret = getattr(main_mod, "SESSION_SECRET_KEY", None)
    cookie_name = None

    for mw in getattr(app, "user_middleware", []):
        cls = getattr(mw, "cls", None)
        kwargs = dict(getattr(mw, "kwargs", {}) or {})
        if getattr(cls, "__name__", "") == "SessionMiddleware":
            if secret is None:
                secret = kwargs.get("secret_key")
            cookie_name = kwargs.get(
                "session_cookie",
                cookie_name,
            )

    if not secret:
        raise RuntimeError("Không lấy được session secret.")

    return app, str(secret), str(cookie_name or "phocap_session")


def make_cookie(secret: str) -> str:
    raw = base64.b64encode(
        json.dumps({"user_id": TARGET_USER_ID}).encode("utf-8")
    )
    return TimestampSigner(secret).sign(raw).decode("utf-8")


def short_sql(statement: str) -> str:
    return " ".join(str(statement).split())


def batch_text(item) -> str:
    return (
        f"id={getattr(item, 'id', None)} | "
        f"code={getattr(item, 'code', None)} | "
        f"year={getattr(item, 'school_year_id', None)} | "
        f"commune={getattr(item, 'commune_id', None)} | "
        f"status={getattr(item, 'status', None)}"
    )


def main() -> int:
    print("=" * 118)
    print("KIỂM TRA TRACE HTTP XÃ NGHI LỘC V8")
    print("CHỈ ĐỌC - KHÔNG SỬA SOURCE - KHÔNG SỬA DATABASE")
    print("=" * 118)

    app, secret, cookie_name = get_session_config()
    cookie_value = make_cookie(secret)

    trace = {
        "scope_calls": 0,
        "catalog_calls": 0,
        "template_calls": 0,
        "survey_sql": [],
    }

    original_scope = surveys.tao_bo_loc_dot_theo_nguoi_dung
    original_catalog = surveys.lay_du_lieu_danh_muc
    original_template = surveys.templates.TemplateResponse

    def traced_scope(request):
        trace["scope_calls"] += 1
        user = dict(request.scope.get("auth_user") or {})

        print()
        print(">>> TRACE HELPER tao_bo_loc_dot_theo_nguoi_dung")
        print("auth_user =", user)

        result = original_scope(request)

        print("filter_count =", len(result))
        for i, item in enumerate(result, 1):
            print(f" filter {i} =", item)

        return result

    def traced_catalog(db):
        trace["catalog_calls"] += 1
        years, communes = original_catalog(db)

        print()
        print(">>> TRACE lay_du_lieu_danh_muc")
        print("year_ids =", [x.id for x in years])
        print(
            "commune_114 =",
            [
                (x.id, x.code, x.name)
                for x in communes
                if x.id == 114
            ],
        )
        return years, communes

    def traced_template(*args, **kwargs):
        name = kwargs.get("name")
        if name is None and len(args) >= 2:
            name = args[1]

        context = kwargs.get("context")
        if context is None and len(args) >= 3:
            context = args[2]

        if name == "surveys/index.html":
            trace["template_calls"] += 1

            print()
            print(">>> TRACE TemplateResponse surveys/index.html")

            if isinstance(context, dict):
                print(
                    "selected_school_year_id =",
                    context.get("selected_school_year_id"),
                    type(context.get("selected_school_year_id")).__name__,
                )
                print(
                    "selected_commune_id =",
                    context.get("selected_commune_id"),
                    type(context.get("selected_commune_id")).__name__,
                )
                print(
                    "selected_status =",
                    repr(context.get("selected_status")),
                )

                user = context.get("nguoi_dung")
                print("context nguoi_dung =", user)

                batches = context.get("survey_batches")
                if batches is None:
                    print("survey_batches = NONE/MISSING")
                else:
                    print("survey_batches length =", len(batches))
                    for item in batches[:20]:
                        print(" -", batch_text(item))
            else:
                print("context không phải dict:", type(context))

        return original_template(*args, **kwargs)

    def before_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        text = short_sql(statement)
        low = text.lower()

        if (
            "survey_batches" in low
            or "school_years" in low
            or "communes" in low
        ):
            item = (text, repr(parameters))
            trace["survey_sql"].append(item)

            print()
            print(">>> TRACE SQL")
            print(text)
            print("PARAMS =", parameters)

    surveys.tao_bo_loc_dot_theo_nguoi_dung = traced_scope
    surveys.lay_du_lieu_danh_muc = traced_catalog
    surveys.templates.TemplateResponse = traced_template

    engine = getattr(database, "engine", None)
    if engine is None:
        raise RuntimeError("app.database không có engine.")

    event.listen(
        engine,
        "before_cursor_execute",
        before_cursor_execute,
    )

    try:
        from fastapi.testclient import TestClient

        print()
        print("1. GỬI REQUEST TESTCLIENT")
        print("-" * 118)

        client = TestClient(
            app,
            follow_redirects=False,
        )

        response = client.get(
            "/dieu-tra",
            params={
                "school_year_id": "2",
                "commune_id": "114",
                "survey_status": "",
            },
            cookies={
                cookie_name: cookie_value,
            },
        )

        print()
        print("2. KẾT QUẢ HTTP")
        print("-" * 118)
        print("status =", response.status_code)
        print("location =", response.headers.get("location"))
        print("body length =", len(response.text))
        print(
            "Có batch code =",
            TARGET_BATCH_CODE in response.text,
        )
        print("Có 0 đợt =", "0 đợt" in response.text)
        print("Có 1 đợt =", "1 đợt" in response.text)

        badge = re.findall(
            r'class=["\'][^"\']*count-badge[^"\']*["\'][^>]*>\s*([^<]+)',
            response.text,
            flags=re.I,
        )
        print("count badge =", [x.strip() for x in badge[:5]])

    except Exception:
        print()
        print("REQUEST NÉM LỖI:")
        traceback.print_exc()

    finally:
        try:
            event.remove(
                engine,
                "before_cursor_execute",
                before_cursor_execute,
            )
        except Exception:
            pass

        surveys.tao_bo_loc_dot_theo_nguoi_dung = original_scope
        surveys.lay_du_lieu_danh_muc = original_catalog
        surveys.templates.TemplateResponse = original_template

    print()
    print("3. TÓM TẮT TRACE")
    print("-" * 118)
    print(
        "helper scope được gọi =",
        trace["scope_calls"],
    )
    print(
        "lay_du_lieu_danh_muc được gọi =",
        trace["catalog_calls"],
    )
    print(
        "Template surveys/index được gọi =",
        trace["template_calls"],
    )
    print(
        "Số SQL liên quan danh mục/đợt =",
        len(trace["survey_sql"]),
    )

    print()
    print("4. KẾT LUẬN TỰ ĐỘNG")
    print("-" * 118)

    if trace["scope_calls"] == 0:
        print(
            "CHỐT: Request /dieu-tra KHÔNG chạy qua "
            "danh_sach_dot_dieu_tra hiện tại của surveys.py."
        )
        print(
            "=> Có endpoint/route khác đang bắt request trước."
        )
    elif trace["template_calls"] == 0:
        print(
            "Helper hiện tại có chạy nhưng không render "
            "surveys/index.html qua templates hiện tại."
        )
        print(
            "=> Cần xem trace SQL và route/response trung gian."
        )
    else:
        print(
            "Request đã chạy đúng module surveys.py hiện tại."
        )
        print(
            "=> Dòng TRACE SQL + survey_batches length ở trên "
            "sẽ chỉ chính xác điều kiện làm dữ liệu thành 0."
        )

    print()
    print("Hãy COPY TOÀN BỘ kết quả V8 gửi lại ChatGPT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
