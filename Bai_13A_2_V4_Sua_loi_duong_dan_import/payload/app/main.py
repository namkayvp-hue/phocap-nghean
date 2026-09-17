from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware

from app.access_control import AccessControlMiddleware
from app.routers.auth import router as auth_router
from app.routers.communes import router as communes_router
from app.routers.schools import router as schools_router
from app.routers.students import router as students_router
from app.routers.surveys import router as surveys_router
from app.routers.survey_comparisons import router as survey_comparisons_router
from app.routers.survey_dashboard import router as survey_dashboard_router
from app.routers.province_year_start import router as province_year_start_router
from app.routers.survey_trends import router as survey_trends_router
from app.routers.survey_exchange import router as survey_exchange_router
from app.routers.survey_print import router as survey_print_router
from app.routers.historical_data import router as historical_data_router
from app.routers.student_survey_comparison import router as student_survey_comparison_router
from app.routers.comparison_province_dashboard import router as comparison_province_dashboard_router
from app.routers.comparison_followup_dashboard import router as comparison_followup_dashboard_router
from app.routers.report_center import router as report_center_router
from app.routers.survey_summary_report import router as survey_summary_report_router
from app.routers.users import router as users_router


BASE_DIR = Path(__file__).resolve().parent


SESSION_SECRET_KEY = (
    "phocap-mamnon-session-"
    "development-key-2026"
)


middleware = [
    Middleware(
        SessionMiddleware,
        secret_key=SESSION_SECRET_KEY,
        session_cookie="phocap_session",
        max_age=8 * 60 * 60,
        same_site="lax",
        https_only=False,
    ),
    Middleware(
        AccessControlMiddleware,
    ),
]


app = FastAPI(
    title=(
        "Phần mềm Quản lý "
        "Phổ cập Giáo dục Mầm non"
    ),
    description=(
        "Hệ thống quản lý dữ liệu theo các cấp "
        "ADMIN - Phòng ban - Xã - Trường - Giáo viên"
    ),
    version="1.0.0",
    middleware=middleware,
)


app.mount(
    "/static",
    StaticFiles(
        directory=str(BASE_DIR / "static")
    ),
    name="static",
)


templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)


app.include_router(auth_router)
app.include_router(communes_router)
app.include_router(schools_router)
app.include_router(students_router)
app.include_router(surveys_router)
app.include_router(survey_comparisons_router)
app.include_router(survey_dashboard_router)
app.include_router(province_year_start_router)
app.include_router(survey_trends_router)
app.include_router(survey_exchange_router)
app.include_router(survey_print_router)
app.include_router(historical_data_router)

# === BAI 12D-15 V7: BAT DAU ===
# Dang ky truc tiep cac APIRoute da co day du prefix /dieu-tra.
# Cach nay tranh phu thuoc vao thu tu include_router cua cac router cha/con.
for _student_survey_route in student_survey_comparison_router.routes:
    _route_exists = any(
        getattr(_existing_route, "path", None)
        == getattr(_student_survey_route, "path", None)
        and getattr(_existing_route, "methods", None)
        == getattr(_student_survey_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _route_exists:
        app.router.routes.append(_student_survey_route)
# === BAI 12D-15 V7: KET THUC ===
app.include_router(comparison_province_dashboard_router)
app.include_router(comparison_followup_dashboard_router)
app.include_router(report_center_router)

# === BAI 13A-2 V2: BAT DAU ===
# Dang ky truc tiep cac route bao cao da co day du prefix /bao-cao.
# Cach nay on dinh tren du an hien tai va khong phu thuoc vao include_router.
for _survey_summary_route in survey_summary_report_router.routes:
    _route_exists = any(
        getattr(_existing_route, "path", None)
        == getattr(_survey_summary_route, "path", None)
        and getattr(_existing_route, "methods", None)
        == getattr(_survey_summary_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _route_exists:
        app.router.routes.append(_survey_summary_route)
# === BAI 13A-2 V2: KET THUC ===

app.include_router(users_router)


@app.get("/", response_class=HTMLResponse)
def trang_chu(
    request: Request,
    status: str | None = None,
):
    nguoi_dung = request.scope.get("auth_user")

    thong_bao = None

    if status == "forbidden":
        thong_bao = (
            "Tài khoản của bạn không có quyền "
            "truy cập chức năng vừa chọn."
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "ten_phan_mem": (
                "PHẦN MỀM QUẢN LÝ "
                "PHỔ CẬP GIÁO DỤC MẦM NON"
            ),
            "phien_ban": "1.0.0",
            "nguoi_dung": nguoi_dung,
            "thong_bao": thong_bao,
        },
    )


@app.get("/api/kiem-tra")
def kiem_tra_he_thong() -> dict[str, str]:
    return {
        "trang_thai": "hoat_dong",
        "thong_bao": (
            "Phần mềm Phổ cập Giáo dục "
            "Mầm non đang hoạt động"
        ),
    }
