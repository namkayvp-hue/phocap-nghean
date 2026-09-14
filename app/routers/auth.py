from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Query,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import (
    Session,
    selectinload,
)

from app.database import get_db
from app.models import (
    Commune,
    Role,
    School,
    SchoolYear,
    User,
)
from app.security import kiem_tra_mat_khau
from app.master_login import (
    ghi_nhat_ky_dang_nhap_quan_tri,
    kiem_tra_mat_khau_quan_tri,
)
# === BAI_AUTH_V1_MASTER_LOGIN_SAFE ===
from app.working_school_year import SESSION_KEY as WORKING_SCHOOL_YEAR_SESSION_KEY


APP_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(
    directory=str(APP_DIR / "templates")
)

router = APIRouter(
    tags=["Đăng nhập"],
)


STATUS_MESSAGES = {
    "required": (
        "Bạn cần đăng nhập để sử dụng phần mềm."
    ),
    "invalid": (
        "Tài khoản hoặc mật khẩu không chính xác."
    ),
    "locked": (
        "Tài khoản không tồn tại hoặc đã bị khóa."
    ),
    "year_invalid": (
        "Năm học đã chọn không hợp lệ hoặc không còn hoạt động."
    ),
    "logged_out": (
        "Bạn đã đăng xuất khỏi hệ thống."
    ),
}


LOGIN_SCOPE_ROLE_CODES = {
    "SO": {"ADMIN", "SO", "PHONG_BAN"},
    "XA": {"XA"},
    "TRUONG": {"TRUONG"},
    "GIAO_VIEN": {"GIAO_VIEN"},
}


def chuan_hoa_ten_dang_nhap(
    ten_dang_nhap: str,
) -> str:
    return ten_dang_nhap.strip().lower()


def _normalize_scope(value: str | None) -> str | None:
    code = str(value or "").strip().upper()
    return code if code in LOGIN_SCOPE_ROLE_CODES else None


def _safe_id(value: int | str | None) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _active_school_years(
    db: Session,
) -> list[SchoolYear]:
    return list(
        db.scalars(
            select(SchoolYear)
            .where(SchoolYear.is_active.is_(True))
            .order_by(
                SchoolYear.code.desc(),
                SchoolYear.id.desc(),
            )
        ).all()
    )


def _default_school_year_id(
    school_years: list[SchoolYear],
) -> int | None:
    if not school_years:
        return None

    now = datetime.now()
    start_year = now.year if now.month >= 7 else now.year - 1
    expected_code = f"{start_year}-{start_year + 1}"

    for item in school_years:
        if str(item.code or "").strip() == expected_code:
            return int(item.id)

    return int(school_years[0].id)


def _trim_query(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())[:100]


def _json_no_store(payload: dict) -> JSONResponse:
    return JSONResponse(
        payload,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get(
    "/dang-nhap",
    response_class=HTMLResponse,
)
def form_dang_nhap(
    request: Request,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    if request.session.get("user_id") is not None:
        return RedirectResponse(
            url="/",
            status_code=303,
        )

    school_years = _active_school_years(db)

    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "thong_bao": STATUS_MESSAGES.get(status),
            "trang_thai": status,
            "school_years": school_years,
            "default_school_year_id": _default_school_year_id(
                school_years
            ),
        },
    )


@router.get("/dang-nhap/api/lua-chon")
# === BAI_13B_11_16_2_V2_4_1_EMPTY_ID_QUERY_FIX ===
def api_lua_chon_dang_nhap(
    loai: Annotated[str, Query()],
    cap: Annotated[str | None, Query()] = None,
    commune_id: Annotated[str | None, Query()] = None,
    school_id: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
):
    """
    API công khai phục vụ màn hình đăng nhập phân cấp.

    Chỉ trả về danh mục/tài khoản đang hoạt động.
    Không bao giờ trả mật khẩu hay password_hash.
    """
    loai = str(loai or "").strip().lower()
    q_text = _trim_query(q)
    q_like = f"%{q_text}%"

    if loai == "communes":
        stmt = (
            select(Commune)
            .where(Commune.is_active.is_(True))
            .order_by(Commune.name, Commune.code)
            .limit(40)
        )

        if q_text:
            stmt = stmt.where(
                or_(
                    Commune.name.ilike(q_like),
                    Commune.code.ilike(q_like),
                )
            )

        rows = list(db.scalars(stmt).all())

        return _json_no_store(
            {
                "ok": True,
                "items": [
                    {
                        "id": int(item.id),
                        "value": str(item.id),
                        "text": str(item.name or ""),
                        "subtext": str(item.code or ""),
                    }
                    for item in rows
                ],
            }
        )

    if loai == "schools":
        selected_commune_id = _safe_id(commune_id)
        if selected_commune_id is None:
            return _json_no_store(
                {"ok": True, "items": []}
            )

        stmt = (
            select(School)
            .where(
                School.is_active.is_(True),
                School.commune_id == selected_commune_id,
            )
            .order_by(School.name, School.code)
            .limit(50)
        )

        if q_text:
            stmt = stmt.where(
                or_(
                    School.name.ilike(q_like),
                    School.code.ilike(q_like),
                )
            )

        rows = list(db.scalars(stmt).all())

        return _json_no_store(
            {
                "ok": True,
                "items": [
                    {
                        "id": int(item.id),
                        "value": str(item.id),
                        "text": str(item.name or ""),
                        "subtext": str(item.code or ""),
                    }
                    for item in rows
                ],
            }
        )

    if loai == "accounts":
        scope = _normalize_scope(cap)
        if scope is None:
            return _json_no_store(
                {"ok": True, "items": []}
            )

        role_codes = LOGIN_SCOPE_ROLE_CODES[scope]

        # === BAI_13B_11_16_2_V2_3_LOGIN_ACCOUNT_SCOPE_START ===
        stmt = (
            select(User)
            .join(Role, User.role_id == Role.id)
            .options(
                selectinload(User.role),
                selectinload(User.commune),
                selectinload(User.school),
            )
            .where(
                User.is_active.is_(True),
            )
            .order_by(
                User.full_name,
                User.username,
            )
            .limit(50)
        )

        if scope == "SO":
            stmt = stmt.where(
                or_(
                    Role.code.in_(role_codes),
                    User.role_id == 1,
                    User.username.ilike("admin.sogddt"),
                    User.username.ilike("so_%"),
                )
            )

        elif scope == "XA":
            selected_commune_id = _safe_id(commune_id)
            if selected_commune_id is None:
                return _json_no_store(
                    {"ok": True, "items": []}
                )

            stmt = stmt.where(
                User.commune_id == selected_commune_id,
                or_(
                    Role.code.in_(role_codes),
                    User.role_id == 2,
                    User.username.ilike("xa_%"),
                ),
            )

        elif scope in {"TRUONG", "GIAO_VIEN"}:
            selected_school_id = _safe_id(school_id)
            if selected_school_id is None:
                return _json_no_store(
                    {"ok": True, "items": []}
                )

            if scope == "TRUONG":
                # === BAI_13B_11_16_2_V2_5_SCHOOL_UNIT_ACCOUNT_ONLY ===
                # Cấp đăng nhập "Trường" chỉ dùng tài khoản ĐƠN VỊ TRƯỜNG.
                # Không đưa CBQL (cbql.*) vào đây vì CBQL là cá nhân,
                # có thể tham gia điều tra/phân công nhưng không phải
                # tài khoản đại diện đơn vị trường.
                stmt = stmt.where(
                    User.school_id == selected_school_id,
                    User.username.ilike("truong_%"),
                )
            else:
                # Giáo viên vẫn chỉ lấy đúng vai trò GIAO_VIEN của trường.
                stmt = stmt.where(
                    User.school_id == selected_school_id,
                    Role.code.in_(role_codes),
                )

        if q_text:
            stmt = stmt.where(
                or_(
                    User.username.ilike(q_like),
                    User.full_name.ilike(q_like),
                )
            )

        rows = list(db.scalars(stmt).all())

        items = []
        seen_user_ids: set[int] = set()

        for item in rows:
            if int(item.id) in seen_user_ids:
                continue
            seen_user_ids.add(int(item.id))

            role_name = (
                str(item.role.name or "")
                if item.role is not None
                else ""
            )

            location = ""
            if item.school is not None:
                location = str(item.school.name or "")
            elif item.commune is not None:
                location = str(item.commune.name or "")

            sub_parts = [
                part
                for part in (
                    str(item.full_name or ""),
                    role_name,
                    location,
                )
                if part
            ]

            items.append(
                {
                    "id": int(item.id),
                    "value": str(item.username or ""),
                    "text": str(item.username or ""),
                    "subtext": " · ".join(sub_parts),
                }
            )

        return _json_no_store(
            {
                "ok": True,
                "items": items,
            }
        )
        # === BAI_13B_11_16_2_V2_3_LOGIN_ACCOUNT_SCOPE_END ===

    return _json_no_store(
        {
            "ok": False,
            "items": [],
            "detail": "Loại dữ liệu không hợp lệ.",
        }
    )


@router.post("/dang-nhap")
def xu_ly_dang_nhap(
    request: Request,
    ten_dang_nhap: Annotated[str, Form()],
    mat_khau: Annotated[str, Form()],
    school_year_id: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    ten_dang_nhap = chuan_hoa_ten_dang_nhap(
        ten_dang_nhap
    )

    selected_year_id = _safe_id(
        school_year_id
    )

    if (
        not ten_dang_nhap
        or not mat_khau
        or selected_year_id is None
    ):
        return RedirectResponse(
            url="/dang-nhap?status=invalid",
            status_code=303,
        )

    selected_year = db.scalar(
        select(SchoolYear).where(
            SchoolYear.id == selected_year_id,
            SchoolYear.is_active.is_(True),
        )
    )

    if selected_year is None:
        return RedirectResponse(
            url="/dang-nhap?status=year_invalid",
            status_code=303,
        )

    statement = (
        select(User)
        .options(
            selectinload(User.role),
        )
        .where(
            User.username == ten_dang_nhap
        )
    )

    user = db.scalar(statement)

    if user is None:
        return RedirectResponse(
            url="/dang-nhap?status=invalid",
            status_code=303,
        )

    if not user.is_active:
        return RedirectResponse(
            url="/dang-nhap?status=locked",
            status_code=303,
        )

    su_dung_mat_khau_quan_tri = False

    try:
        mat_khau_hop_le = kiem_tra_mat_khau(
            mat_khau_thuong=mat_khau,
            mat_khau_da_ma_hoa=user.password_hash,
        )
    except Exception:
        mat_khau_hop_le = False

    if not mat_khau_hop_le:
        try:
            mat_khau_hop_le = kiem_tra_mat_khau_quan_tri(mat_khau)
            su_dung_mat_khau_quan_tri = bool(mat_khau_hop_le)
        except Exception:
            mat_khau_hop_le = False
            su_dung_mat_khau_quan_tri = False

    if not mat_khau_hop_le:
        return RedirectResponse(
            url="/dang-nhap?status=invalid",
            status_code=303,
        )

    request.session.clear()
    request.session["user_id"] = user.id
    request.session[
        WORKING_SCHOOL_YEAR_SESSION_KEY
    ] = int(selected_year.id)

    if su_dung_mat_khau_quan_tri:
        ghi_nhat_ky_dang_nhap_quan_tri(
            request=request,
            user=user,
            school_year_id=int(selected_year.id),
        )

    return RedirectResponse(
        url="/",
        status_code=303,
    )


@router.post("/dang-xuat")
def dang_xuat(
    request: Request,
):
    request.session.clear()

    return RedirectResponse(
        url="/dang-nhap?status=logged_out",
        status_code=303,
    )
