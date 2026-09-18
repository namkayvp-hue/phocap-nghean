import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware

# === BAI_13B_11_15_2_4_8_1_WORKING_YEAR_IMPORT ===
from app.working_school_year import WorkingSchoolYearMiddleware

from app.access_control import AccessControlMiddleware
from app.routers.auth import router as auth_router
from app.routers.communes import router as communes_router
from app.routers.schools import router as schools_router
# === BAI_13B_10_V3_18A_DATA_TOOLS_IMPORT ===
from app.routers.data_tools import router as data_tools_router
# === SAP_NHAP_TRUONG_DUNG_CHUNG_V9_2_IMPORT ===
from app.routers.school_merger import router as school_merger_router
# === SAP_NHAP_TRUONG_V4_5_FUTURE_IMPORT ===
from app.routers.school_merger_future import router as school_merger_future_router
# === SCHOOL_MERGER_LEVEL_BATCH_IMPORT ===
from app.routers.school_merger_level_batch import router as school_merger_level_batch_router
# === V13_1_SCHOOL_RENAME_IMPORT ===
from app.routers.school_rename import router as school_rename_router
# === BAI_13B_7_V1_THPT_ROUTER_IMPORT ===
from app.routers.thpt_reference import router as thpt_reference_router
from app.routers.students import router as students_router
# === BAI_13B_11_16_1_CLASSROOM_CATALOG_IMPORT ===
from app.routers.classrooms import router as classrooms_router
from app.routers.surveys import router as surveys_router
# === BAI_13B_11_PROVINCE_BATCH_ADMIN_ROUTER_IMPORT ===
from app.routers.survey_batch_admin_v13b11 import router as survey_batch_admin_v13b11_router
from app.routers.survey_team_registration import router as survey_team_registration_router
from app.routers.commune_area_excel import router as commune_area_excel_router
from app.routers.survey_comparisons import router as survey_comparisons_router
from app.routers.survey_dashboard import router as survey_dashboard_router
from app.routers.province_year_start import router as province_year_start_router
from app.routers.survey_trends import router as survey_trends_router
from app.routers.survey_exchange import router as survey_exchange_router
from app.routers.survey_print import router as survey_print_router
from app.routers.household_updates import router as household_updates_router  # BAI_13B_9_V1A_HOUSEHOLD_UPDATE_ROUTER
from app.routers.historical_data import router as historical_data_router
from app.routers.student_survey_comparison import router as student_survey_comparison_router
# === V12_STUDENT_RECONCILIATION_SOURCE_IMPORT ===
from app.routers.student_reconciliation_source import router as student_reconciliation_source_router
from app.routers.comparison_province_dashboard import router as comparison_province_dashboard_router
from app.routers.comparison_followup_dashboard import router as comparison_followup_dashboard_router
from app.routers.report_center import router as report_center_router
from app.routers.survey_summary_report import router as survey_summary_report_router
from app.routers.pcgdmn_template_report import router as pcgdmn_template_report_router
from app.routers.staff_management import router as staff_management_router
from app.routers.report_inputs import router as report_inputs_router
from app.routers.users import router as users_router
from app.routers.survey_school_workflow import router as survey_school_workflow_router


from app.routers.mn_official_reports import (
    router as mn_official_reports_router,
    install_mn_official_report_redirects,
)

BASE_DIR = Path(__file__).resolve().parent


SESSION_SECRET_KEY = os.environ.get(
    "PHOCAP_SESSION_SECRET_KEY",
    "phocap-mamnon-session-development-key-2026",
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
    # === BAI_13B_11_15_2_4_8_1_WORKING_YEAR_MIDDLEWARE_START ===
    Middleware(WorkingSchoolYearMiddleware),
    # === BAI_13B_11_15_2_4_8_1_WORKING_YEAR_MIDDLEWARE_END ===
    Middleware(
        AccessControlMiddleware,
    ),
]


app = FastAPI(
    title=(
        "Pháº§n má»m Quáº£n lÃ½ "
        "Phá»• cáº­p GiÃ¡o dá»¥c Máº§m non"
    ),
    description=(
        "Há»‡ thá»‘ng quáº£n lÃ½ dá»¯ liá»‡u theo cÃ¡c cáº¥p "
        "ADMIN - PhÃ²ng ban - XÃ£ - TrÆ°á»ng - GiÃ¡o viÃªn"
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
# === BAI_13B_10_V3_18A_DATA_TOOLS_INCLUDE ===
app.include_router(data_tools_router)
# === SAP_NHAP_TRUONG_DUNG_CHUNG_V9_2_INCLUDE ===
app.include_router(school_merger_router)
# === SAP_NHAP_TRUONG_V4_5_FUTURE_INCLUDE ===
app.include_router(school_merger_future_router)
# === SCHOOL_MERGER_LEVEL_BATCH_INCLUDE ===
app.include_router(school_merger_level_batch_router)
# === V13_1_SCHOOL_RENAME_INCLUDE ===
app.include_router(school_rename_router)
# === BAI_13B_7_V1_THPT_ROUTER_INCLUDE ===
app.include_router(thpt_reference_router)
app.include_router(students_router)
# === BAI_13B_11_16_1_CLASSROOM_CATALOG_INCLUDE ===
app.include_router(classrooms_router)
app.include_router(surveys_router)
# === BAI_13B_11_PROVINCE_BATCH_ADMIN_ROUTER_INCLUDE ===
app.include_router(survey_batch_admin_v13b11_router)
app.include_router(survey_team_registration_router)
app.include_router(commune_area_excel_router)
app.include_router(survey_comparisons_router)
app.include_router(survey_dashboard_router)
app.include_router(province_year_start_router)
app.include_router(survey_trends_router)
app.include_router(survey_exchange_router)
app.include_router(survey_print_router)
app.include_router(household_updates_router)
app.include_router(historical_data_router)

# === V12_STUDENT_RECONCILIATION_SOURCE_INCLUDE_START ===
for _v12_source_route in student_reconciliation_source_router.routes:
    _route_exists = any(
        getattr(_existing_route, "path", None) == getattr(_v12_source_route, "path", None)
        and getattr(_existing_route, "methods", None) == getattr(_v12_source_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _route_exists:
        app.router.routes.append(_v12_source_route)
# === V12_STUDENT_RECONCILIATION_SOURCE_INCLUDE_END ===

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

# === BAO_CAO_MN_MAU_MOI_V1_MAIN ===
app.include_router(mn_official_reports_router)
install_mn_official_report_redirects(app)

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

# === BAI 13A-3 V3: BAT DAU ===
# ÄÄƒng kÃ½ trá»±c tiáº¿p route xuáº¥t bá»™ biá»ƒu máº«u PCGDMN 2025.
for _pcgdmn_template_route in pcgdmn_template_report_router.routes:
    _route_exists = any(
        getattr(_existing_route, "path", None)
        == getattr(_pcgdmn_template_route, "path", None)
        and getattr(_existing_route, "methods", None)
        == getattr(_pcgdmn_template_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _route_exists:
        app.router.routes.append(_pcgdmn_template_route)
# === BAI 13A-3 V3: KET THUC ===

# === BAI 13B-1 V3: BAT DAU ===
# Dang ky truc tiep cac route quan ly doi ngu da co day du prefix /doi-ngu.
# Cach nay tranh phu thuoc vao co che include_router tren moi truong Windows
# va dong thoi khong tao route trung neu ma nguon da duoc nap lai.
for _staff_management_route in staff_management_router.routes:
    _route_exists = any(
        getattr(_existing_route, "path", None)
        == getattr(_staff_management_route, "path", None)
        and getattr(_existing_route, "methods", None)
        == getattr(_staff_management_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _route_exists:
        app.router.routes.append(_staff_management_route)
# === BAI 13B-1 V3: KET THUC ===

# === BAI 13B-3 V1: BAT DAU ===
# Dá»¯ liá»‡u Ä‘áº§u vÃ o phá»¥c vá»¥ MN-01-GV, MN-01-CSVC vÃ  BC-TÃ i chÃ­nh.
for _report_inputs_route in report_inputs_router.routes:
    _route_exists = any(
        getattr(_existing_route, "path", None)
        == getattr(_report_inputs_route, "path", None)
        and getattr(_existing_route, "methods", None)
        == getattr(_report_inputs_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _route_exists:
        app.router.routes.append(_report_inputs_route)
# === BAI 13B-3 V1: KET THUC ===

# === SUA LOI TAI KHOAN XA/TRUONG V2: BAT DAU ===
# Dang ky truc tiep cac route quan ly tai khoan da co day du prefix /tai-khoan.
# Du an hien tai da tung gap truong hop include_router khong dua route vao app
# trong moi truong Windows, vi vay dung cung co che on dinh nhu cac phan he moi.
for _users_route in users_router.routes:
    _route_exists = any(
        getattr(_existing_route, "path", None)
        == getattr(_users_route, "path", None)
        and getattr(_existing_route, "methods", None)
        == getattr(_users_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _route_exists:
        app.router.routes.append(_users_route)
# === SUA LOI TAI KHOAN XA/TRUONG V2: KET THUC ===

# === BAI 13B-4 V2: BAT DAU ===
# Dang ky truc tiep quy trinh So -> Xa -> Truong.
for _survey_school_workflow_route in survey_school_workflow_router.routes:
    _route_exists = any(
        getattr(_existing_route, "path", None)
        == getattr(_survey_school_workflow_route, "path", None)
        and getattr(_existing_route, "methods", None)
        == getattr(_survey_school_workflow_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _route_exists:
        app.router.routes.append(_survey_school_workflow_route)
# === BAI 13B-4 V2: KET THUC ===




# === BAO_CAO_TRE_3_5_TUOI_V2_START ===
# Dang ky TRUC TIEP cac APIRoute da co san trong router bao cao tre 3-5 tuoi.
# Giu nguyen duong dan, du lieu va luong nghiep vu.
# Cach dang ky nay dong nhat voi cac phan he hien tai cua du an.
from app.routers.preschool_3_5_report import (
    router as preschool_3_5_report_router,
)

for _preschool_3_5_route in preschool_3_5_report_router.routes:
    _preschool_3_5_exists = any(
        getattr(_existing_route, "path", None)
        == getattr(_preschool_3_5_route, "path", None)
        and getattr(_existing_route, "methods", None)
        == getattr(_preschool_3_5_route, "methods", None)
        for _existing_route in app.router.routes
    )
    if not _preschool_3_5_exists:
        app.router.routes.append(_preschool_3_5_route)
# === BAO_CAO_TRE_3_5_TUOI_V2_END ===

@app.get("/", response_class=HTMLResponse)
def trang_chu(
    request: Request,
    status: str | None = None,
):
    nguoi_dung = request.scope.get("auth_user")

    # === GV_MOBILE_V18B_ROOT_REDIRECT_START ===
    # Chá»‰ Ã¡p dá»¥ng cho tÃ i khoáº£n giÃ¡o viÃªn trÃªn thiáº¿t bá»‹ di Ä‘á»™ng.
    # KhÃ´ng thay Ä‘á»•i giao diá»‡n/luá»“ng cá»§a ADMIN, Sá»ž, XÃƒ, TRÆ¯á»œNG hoáº·c mÃ¡y tÃ­nh.
    role_code = str(
        (nguoi_dung or {}).get("role_code") or ""
    ).strip().upper()

    user_agent = str(
        request.headers.get("user-agent") or ""
    ).lower()

    mobile_tokens = (
        "iphone",
        "ipad",
        "ipod",
        "android",
        "mobile",
        "windows phone",
    )
    is_mobile_device = any(
        token in user_agent
        for token in mobile_tokens
    )

    if role_code == "GIAO_VIEN" and is_mobile_device:
        return RedirectResponse(
            url="/dieu-tra",
            status_code=303,
        )
    # === GV_MOBILE_V18B_ROOT_REDIRECT_END ===

    thong_bao = None

    if status == "forbidden":
        thong_bao = (
            "TÃ i khoáº£n cá»§a báº¡n khÃ´ng cÃ³ quyá»n "
            "truy cáº­p chá»©c nÄƒng vá»«a chá»n."
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "ten_phan_mem": (
                "PHáº¦N Má»€M QUáº¢N LÃ "
                "PHá»” Cáº¬P GIÃO Dá»¤C Máº¦M NON"
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
            "Pháº§n má»m Phá»• cáº­p GiÃ¡o dá»¥c "
            "Máº§m non Ä‘ang hoáº¡t Ä‘á»™ng"
        ),
    }

# === BATCH18_NETWORK_CURRENT_START ===
from app.routers import network_current as _network_current
app.include_router(_network_current.router)
# === BATCH18_NETWORK_CURRENT_END ===



