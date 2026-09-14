from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from starlette.responses import RedirectResponse


ACCESS_CONTROL_PATCH_VERSION = "13B-3-REPORT-INPUT-V1"

from app.database import SessionLocal
from app.models import User
from app.permissions import (
    ACCOUNT_MANAGEMENT_ROLE_CODES,
    ADMIN_ROLE_CODES,
    COMMUNE_ROLE_CODE,
    DEPARTMENT_ROLE_CODE,
    SCHOOL_ROLE_CODE,
    SURVEY_ROLE_CODES,
    TEACHER_ROLE_CODE,
    can_manage_survey_assignments,
    is_admin_role,
    normalize_role_code,
)


PUBLIC_PATHS = {
    "/dang-nhap",
    "/api/kiem-tra",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}

PUBLIC_PREFIXES = ("/static", "/dang-nhap/api/")

ROLE_RULES = (
    # === SAP_NHAP_TRUONG_DUNG_CHUNG_V9_2_ACCESS ===
    ("/cong-cu-du-lieu", ADMIN_ROLE_CODES),
    ("/tai-khoan", ACCOUNT_MANAGEMENT_ROLE_CODES),
    ("/xa", ADMIN_ROLE_CODES),
    ("/truong", frozenset({*ADMIN_ROLE_CODES, COMMUNE_ROLE_CODE})),
    # === BAI_13B_11_16_1_CLASSROOM_CATALOG_ROLE ===
    ("/lop-hoc", frozenset({*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE, COMMUNE_ROLE_CODE, SCHOOL_ROLE_CODE})),
    ("/hoc-sinh/api", SURVEY_ROLE_CODES),
    ("/hoc-sinh", ADMIN_ROLE_CODES),
    ("/csvc", frozenset({*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE, COMMUNE_ROLE_CODE, SCHOOL_ROLE_CODE})),
    ("/bao-cao", SURVEY_ROLE_CODES),
    ("/doi-ngu", SURVEY_ROLE_CODES),
    ("/dieu-tra", SURVEY_ROLE_CODES),
)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}



# === FIX_SURVEY_WORKING_BATCH_SCOPE_V2_HELPERS_START ===
def _pc_batch_in_account_scope(
    *,
    db,
    auth_user: dict[str, Any],
    batch_id: int,
) -> bool:
    """Kiểm tra một đợt có nằm trong phạm vi thực của tài khoản hay không."""
    role_code = normalize_role_code(auth_user.get("role_code"))

    if role_code in {*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE}:
        exists = db.execute(
            text(
                "SELECT 1 FROM survey_batches "
                "WHERE id = :batch_id LIMIT 1"
            ),
            {"batch_id": int(batch_id)},
        ).scalar()
        return exists is not None

    if role_code == COMMUNE_ROLE_CODE:
        commune_id = auth_user.get("commune_id")
        if commune_id is None:
            return False
        allowed = db.execute(
            text(
                "SELECT 1 FROM survey_batches "
                "WHERE id = :batch_id "
                "AND commune_id = :commune_id "
                "LIMIT 1"
            ),
            {
                "batch_id": int(batch_id),
                "commune_id": int(commune_id),
            },
        ).scalar()
        return allowed is not None

    if role_code == SCHOOL_ROLE_CODE:
        school_id = auth_user.get("school_id")
        if school_id is None:
            return False
        allowed = db.execute(
            text(
                """
                SELECT 1
                FROM survey_forms AS sf
                JOIN survey_form_investigators AS sfi
                    ON sfi.survey_form_id = sf.id
                JOIN users AS assigned_user
                    ON assigned_user.id = sfi.user_id
                WHERE sf.survey_batch_id = :batch_id
                  AND assigned_user.school_id = :school_id
                  AND assigned_user.is_active = 1
                LIMIT 1
                """
            ),
            {
                "batch_id": int(batch_id),
                "school_id": int(school_id),
            },
        ).scalar()
        return allowed is not None

    if role_code == TEACHER_ROLE_CODE:
        user_id = auth_user.get("id")
        if user_id is None:
            return False
        allowed = db.execute(
            text(
                """
                SELECT 1
                FROM survey_forms AS sf
                JOIN survey_form_investigators AS sfi
                    ON sfi.survey_form_id = sf.id
                WHERE sf.survey_batch_id = :batch_id
                  AND sfi.user_id = :user_id
                LIMIT 1
                """
            ),
            {
                "batch_id": int(batch_id),
                "user_id": int(user_id),
            },
        ).scalar()
        if allowed is not None:
            return True

        # === BAI_13B_12_V2_2_ACCESS_BATCH_SCOPE ===
        team_allowed = db.execute(
            text(
                """
                SELECT 1
                FROM survey_investigation_teams AS t
                JOIN survey_investigation_team_members AS tm
                  ON tm.team_id = t.id
                WHERE t.survey_batch_id = :batch_id
                  AND t.status = 'SENT'
                  AND tm.user_id = :user_id
                LIMIT 1
                """
            ),
            {
                "batch_id": int(batch_id),
                "user_id": int(user_id),
            },
        ).scalar()
        return team_allowed is not None

    return False


def _pc_latest_batch_for_account(
    *,
    db,
    auth_user: dict[str, Any],
) -> int | None:
    """
    Tìm đợt làm việc mới nhất đúng phạm vi:
    - Xã: đợt của chính xã.
    - Trường: đợt đã có phiếu giao cho nhân sự của trường.
    - Giáo viên: đợt đã có phiếu giao trực tiếp.
    """
    role_code = normalize_role_code(auth_user.get("role_code"))

    if role_code in {*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE}:
        value = db.execute(
            text(
                """
                SELECT id
                FROM survey_batches
                ORDER BY
                    school_year_id DESC,
                    created_at DESC,
                    id DESC
                LIMIT 1
                """
            )
        ).scalar()
        return int(value) if value is not None else None

    if role_code == COMMUNE_ROLE_CODE:
        commune_id = auth_user.get("commune_id")
        if commune_id is None:
            return None
        value = db.execute(
            text(
                """
                SELECT id
                FROM survey_batches
                WHERE commune_id = :commune_id
                ORDER BY
                    school_year_id DESC,
                    created_at DESC,
                    id DESC
                LIMIT 1
                """
            ),
            {"commune_id": int(commune_id)},
        ).scalar()
        return int(value) if value is not None else None

    if role_code == SCHOOL_ROLE_CODE:
        school_id = auth_user.get("school_id")
        if school_id is None:
            return None
        value = db.execute(
            text(
                """
                SELECT DISTINCT sb.id
                FROM survey_batches AS sb
                JOIN survey_forms AS sf
                    ON sf.survey_batch_id = sb.id
                JOIN survey_form_investigators AS sfi
                    ON sfi.survey_form_id = sf.id
                JOIN users AS assigned_user
                    ON assigned_user.id = sfi.user_id
                WHERE assigned_user.school_id = :school_id
                  AND assigned_user.is_active = 1
                ORDER BY
                    sb.school_year_id DESC,
                    sb.created_at DESC,
                    sb.id DESC
                LIMIT 1
                """
            ),
            {"school_id": int(school_id)},
        ).scalar()
        return int(value) if value is not None else None

    if role_code == TEACHER_ROLE_CODE:
        user_id = auth_user.get("id")
        if user_id is None:
            return None
        value = db.execute(
            text(
                """
                -- === BAI_13B_12_V2_2_ACCESS_LATEST_BATCH ===
                SELECT sb.id
                FROM survey_batches AS sb
                WHERE
                    EXISTS (
                        SELECT 1
                        FROM survey_forms AS sf
                        JOIN survey_form_investigators AS sfi
                          ON sfi.survey_form_id = sf.id
                        WHERE sf.survey_batch_id = sb.id
                          AND sfi.user_id = :user_id
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM survey_investigation_teams AS t
                        JOIN survey_investigation_team_members AS tm
                          ON tm.team_id = t.id
                        WHERE t.survey_batch_id = sb.id
                          AND t.status = 'SENT'
                          AND tm.user_id = :user_id
                    )
                ORDER BY
                    sb.school_year_id DESC,
                    sb.created_at DESC,
                    sb.id DESC
                LIMIT 1
                """
            ),
            {"user_id": int(user_id)},
        ).scalar()
        return int(value) if value is not None else None

    return None


def _pc_resolve_working_batch_id(
    *,
    db,
    auth_user: dict[str, Any],
    path: str,
) -> int | None:
    """
    Nếu URL hiện tại đang ở một đợt hợp lệ thì giữ nguyên đợt đó.
    Nếu URL không có đợt hoặc đang mang batch_id cũ/sai phạm vi,
    dùng đợt mới nhất thuộc đúng phạm vi tài khoản.
    """
    normalized_path = path.rstrip("/") or "/"
    match = re.match(
        r"^/dieu-tra/(?P<batch_id>\d+)(?:/|$)",
        normalized_path,
    )
    if match is not None:
        requested = int(match.group("batch_id"))
        if _pc_batch_in_account_scope(
            db=db,
            auth_user=auth_user,
            batch_id=requested,
        ):
            return requested

    return _pc_latest_batch_for_account(
        db=db,
        auth_user=auth_user,
    )


def _pc_scope_safe_redirect_url(
    *,
    db,
    auth_user: dict[str, Any],
    path: str,
    method: str,
    working_batch_id: int | None,
    query_string: bytes | None,
) -> str | None:
    """
    Sửa mọi link GET/HEAD bị giữ batch_id cũ cho nhóm 2.2–2.5.
    Không bao giờ tự đổi đợt đối với POST/PUT/PATCH/DELETE.
    """
    if method not in SAFE_METHODS:
        return None

    role_code = normalize_role_code(auth_user.get("role_code"))
    if role_code not in {
        COMMUNE_ROLE_CODE,
        SCHOOL_ROLE_CODE,
        TEACHER_ROLE_CODE,
    }:
        return None

    normalized_path = path.rstrip("/") or "/"
    match = re.match(
        r"^/dieu-tra/(?P<batch_id>\d+)(?P<suffix>/.*)?$",
        normalized_path,
    )
    if match is None:
        return None

    requested_batch_id = int(match.group("batch_id"))
    if _pc_batch_in_account_scope(
        db=db,
        auth_user=auth_user,
        batch_id=requested_batch_id,
    ):
        return None

    # Không có đợt thuộc phạm vi: quay về Danh sách đợt thay vì forbidden.
    if working_batch_id is None:
        return "/dieu-tra"

    suffix = match.group("suffix") or ""
    target = f"/dieu-tra/{int(working_batch_id)}{suffix}"

    raw_query = query_string or b""
    if raw_query:
        try:
            query_text = raw_query.decode("latin-1")
        except Exception:
            query_text = ""
        if query_text:
            target = f"{target}?{query_text}"

    return target
# === FIX_SURVEY_WORKING_BATCH_SCOPE_V2_HELPERS_END ===


class AccessControlMiddleware:
    """Kiểm tra đăng nhập, vai trò, thao tác và phạm vi dữ liệu."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")
        method = str(scope.get("method") or "GET").upper()

        if self._la_duong_dan_cong_khai(path):
            await self.app(scope, receive, send)
            return

        session = scope.get("session", {})
        user_id = session.get("user_id")

        if user_id is None:
            await self._chuyen_den_dang_nhap(scope, receive, send)
            return

        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            session.clear()
            await self._chuyen_den_dang_nhap(scope, receive, send)
            return

        with SessionLocal() as db:
            statement = (
                select(User)
                .options(
                    selectinload(User.role),
                    selectinload(User.commune),
                    selectinload(User.school),
                )
                .where(User.id == user_id)
            )
            user = db.scalar(statement)

            if user is None or not user.is_active:
                session.clear()
                response = RedirectResponse(
                    url="/dang-nhap?status=locked",
                    status_code=303,
                )
                await response(scope, receive, send)
                return

            role_code = normalize_role_code(user.role.code)

            if user.school is not None:
                unit_name = user.school.name
            elif user.commune is not None:
                unit_name = user.commune.name
            elif role_code == DEPARTMENT_ROLE_CODE:
                unit_name = "Phòng ban cấp Sở"
            else:
                unit_name = "Toàn tỉnh"

            auth_user: dict[str, Any] = {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "role_code": role_code,
                "role_name": user.role.name,
                "commune_id": user.commune_id,
                "school_id": user.school_id,
                "unit_name": unit_name,
            }
            scope["auth_user"] = auth_user

            # === FIX_SURVEY_WORKING_BATCH_SCOPE_V2_CALL_START ===
            # Xác định đợt làm việc theo đúng phạm vi tài khoản ở MỌI request.
            # Không dùng lại batch_id cũ của tài khoản vừa đăng nhập trước đó.
            working_batch_id = _pc_resolve_working_batch_id(
                db=db,
                auth_user=auth_user,
                path=path,
            )
            scope["menu_survey_batch_id"] = working_batch_id

            # Nếu một link GET/HEAD đang giữ batch_id cũ/sai địa bàn,
            # tự chuyển cùng chức năng sang đợt đúng phạm vi.
            scope_redirect_url = _pc_scope_safe_redirect_url(
                db=db,
                auth_user=auth_user,
                path=path,
                method=method,
                working_batch_id=working_batch_id,
                query_string=scope.get("query_string"),
            )
            if scope_redirect_url is not None:
                response = RedirectResponse(
                    url=scope_redirect_url,
                    status_code=303,
                )
                await response(scope, receive, send)
                return
            # === FIX_SURVEY_WORKING_BATCH_SCOPE_V2_CALL_END ===

            if not self._co_quyen_theo_vai_tro(path=path, role_code=role_code):
                await self._tu_choi_truy_cap(scope, receive, send)
                return

            if not self._co_quyen_theo_thao_tac(
                path=path,
                method=method,
                role_code=role_code,
            ):
                await self._tu_choi_truy_cap(scope, receive, send)
                return

            if path.startswith("/dieu-tra"):
                if not self._co_quyen_dieu_tra(
                    db=db,
                    path=path,
                    auth_user=auth_user,
                ):
                    await self._tu_choi_truy_cap(scope, receive, send)
                    return

                lock_result = self._kiem_tra_khoa_dot_dieu_tra(
                    db=db,
                    path=path,
                    method=method,
                    role_code=role_code,
                    auth_user=auth_user,
                )
                if lock_result is not None:
                    batch_id, redirect_status = lock_result
                    response = RedirectResponse(
                        url=(
                            f"/dieu-tra/{batch_id}/ho-dan"
                            f"?status={redirect_status}"
                        ),
                        status_code=303,
                    )
                    await response(scope, receive, send)
                    return

        await self.app(scope, receive, send)

    @staticmethod
    def _co_quyen_theo_vai_tro(*, path: str, role_code: str) -> bool:
        for path_prefix, allowed_roles in ROLE_RULES:
            if path.startswith(path_prefix):
                return role_code in allowed_roles
        return True

    @staticmethod
    def _co_quyen_theo_thao_tac(
        *,
        path: str,
        method: str,
        role_code: str,
    ) -> bool:
        if path == "/dang-xuat":
            return True

        normalized_path = path.rstrip("/") or "/"

        # === V12_STUDENT_RECONCILIATION_SOURCE_ACTION_START ===
        if normalized_path.startswith("/dieu-tra/nguon-hoc-sinh-doi-chieu"):
            return role_code in {*ADMIN_ROLE_CODES, COMMUNE_ROLE_CODE}
        # === V12_STUDENT_RECONCILIATION_SOURCE_ACTION_END ===

        # === BAI_13B_11_16_1_CLASSROOM_CATALOG_ACTION ===
        # Danh mục lớp: Sở/Xã/Trường được quản lý đúng phạm vi;
        # Phòng ban chỉ xem; Giáo viên không quản trị danh mục.
        if normalized_path.startswith("/lop-hoc"):
            allowed_roles = {
                *ADMIN_ROLE_CODES,
                DEPARTMENT_ROLE_CODE,
                COMMUNE_ROLE_CODE,
                SCHOOL_ROLE_CODE,
            }
            if role_code not in allowed_roles:
                return False
            if method in SAFE_METHODS:
                return True
            return (
                is_admin_role(role_code)
                or role_code in {COMMUNE_ROLE_CODE, SCHOOL_ROLE_CODE}
            )
        # === BAI_13B_11_16_1_CLASSROOM_CATALOG_ACTION_END ===

        # Bài 13B-4 V5.3: mở đúng các thao tác giao phiếu hai cấp.
        # - Xã/phường giao phiếu cho tài khoản đơn vị trường.
        # - Trường giao tiếp các phiếu đã nhận cho giáo viên/CBQL của trường.
        # Các router tiếp tục kiểm tra đúng đợt, đúng xã và đúng trường;
        # lớp middleware chỉ mở đúng phương thức cần thiết, không nới toàn bộ quyền.
        school_assignment_match = re.fullmatch(
            r"/dieu-tra/\d+/giao-phieu-truong(?:/luu)?",
            normalized_path,
        )
        if school_assignment_match is not None:
            if method in SAFE_METHODS:
                return (
                    is_admin_role(role_code)
                    or role_code == COMMUNE_ROLE_CODE
                )
            return (
                normalized_path.endswith("/luu")
                and (
                    is_admin_role(role_code)
                    or role_code == COMMUNE_ROLE_CODE
                )
            )

        teacher_assignment_match = re.fullmatch(
            r"/dieu-tra/\d+/giao-phieu-giao-vien(?:/luu)?",
            normalized_path,
        )
        if teacher_assignment_match is not None:
            if method in SAFE_METHODS:
                return (
                    is_admin_role(role_code)
                    or role_code == SCHOOL_ROLE_CODE
                )
            return (
                normalized_path.endswith("/luu")
                and (
                    is_admin_role(role_code)
                    or role_code == SCHOOL_ROLE_CODE
                )
            )

        legacy_bulk_assignment_match = re.fullmatch(
            r"/dieu-tra/\d+/phan-cong-hang-loat(?:/luu)?",
            normalized_path,
        )
        if legacy_bulk_assignment_match is not None:
            return (
                is_admin_role(role_code)
                or role_code in {COMMUNE_ROLE_CODE, SCHOOL_ROLE_CODE}
            )

        # Bài 13B-4: Sở điều hành toàn tỉnh; Xã phân công/khóa trường;
        # Trường gửi kết quả lên xã.
        if normalized_path.startswith("/dieu-tra/dieu-hanh-trien-khai"):
            if method in SAFE_METHODS:
                return (
                    is_admin_role(role_code)
                    or role_code == DEPARTMENT_ROLE_CODE
                )
            return is_admin_role(role_code)

        if "/phan-cong-truong" in normalized_path:
            if method in SAFE_METHODS:
                return role_code in {
                    *ADMIN_ROLE_CODES,
                    DEPARTMENT_ROLE_CODE,
                    COMMUNE_ROLE_CODE,
                    SCHOOL_ROLE_CODE,
                }
            if normalized_path.endswith("/gui-xa"):
                return role_code == SCHOOL_ROLE_CODE
            return (
                is_admin_role(role_code)
                or role_code == COMMUNE_ROLE_CODE
            )

        if normalized_path.endswith(("/khoa-xa", "/mo-khoa-xa")):
            return (
                is_admin_role(role_code)
                or role_code == COMMUNE_ROLE_CODE
            )

        # === BAI_13B_9_V1A_ACCESS_ACTION_START ===
        is_household_update_center = (
            normalized_path.startswith("/dieu-tra/cap-nhat-ho-dan")
        )
        is_household_update_batch = bool(
            re.match(
                r"^/dieu-tra/\d+/cap-nhat-ho-dan(?:/|$)",
                normalized_path,
            )
        )
        if is_household_update_center or is_household_update_batch:
            allowed_roles = {
                *ADMIN_ROLE_CODES,
                # V2.3: chỉ ADMIN/SO cập nhật tập trung.
                # BAI_13B_12_V2_2_HIDE_UPDATE_XA: bỏ quyền Xã.
                # V2.3: Trường không truy cập cập nhật hộ tập trung.
            }
            if role_code not in allowed_roles:
                return False
            if method in SAFE_METHODS:
                return True
            return (
                role_code in ADMIN_ROLE_CODES
                or role_code == COMMUNE_ROLE_CODE
            )
                # === BAI_13B_12_V2_3_UPDATE_ACCESS_ONLY_SO ===
# === BAI_13B_9_V1A_ACCESS_ACTION_END ===

        # Bài 12D-14A: Sở và xã/phường được cập nhật dữ liệu lịch sử.
        # PHONG_BAN chỉ xem/xuất; Trường và Giáo viên không truy cập.
        if normalized_path.startswith("/dieu-tra/du-lieu-lich-su"):
            allowed_roles = {
                *ADMIN_ROLE_CODES,
                DEPARTMENT_ROLE_CODE,
                COMMUNE_ROLE_CODE,
            }
            if role_code not in allowed_roles:
                return False
            if method in SAFE_METHODS:
                return True
            return (
                role_code in ADMIN_ROLE_CODES
                or role_code == COMMUNE_ROLE_CODE
            )

        # Phân hệ đội ngũ: mọi vai trò nghiệp vụ được xem;
        # ADMIN/SO và tài khoản Trường được nhập, sửa, đồng bộ.
        if normalized_path.startswith("/doi-ngu"):
            if method in SAFE_METHODS:
                return True
            return (
                is_admin_role(role_code)
                or role_code == SCHOOL_ROLE_CODE
            )

        # Bài 13B-5 V1.5: mở xuất/nhập phiếu Excel theo đúng phạm vi.
        # - ADMIN/SO: toàn tỉnh.
        # - Xã/phường: các phiếu thuộc địa bàn của mình.
        # - Trường: các phiếu xã đã giao cho trường.
        # - Giáo viên: các phiếu được phân công trực tiếp.
        # Phạm vi chi tiết tiếp tục được kiểm tra tại _co_quyen_dieu_tra
        # và trong app.household_excel_exchange trước khi đọc/ghi dữ liệu.
        if (
            normalized_path.startswith("/dieu-tra")
            and "/nhap-excel" in normalized_path
        ):
            return role_code in {
                *ADMIN_ROLE_CODES,
                COMMUNE_ROLE_CODE,
                SCHOOL_ROLE_CODE,
                TEACHER_ROLE_CODE,
            }

        # === BAI_13B_12_V2_2_ACCESS_ACTION_START ===
        if normalized_path.startswith(
            "/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/"
        ):
            return role_code == TEACHER_ROLE_CODE
        # === BAI_13B_12_V2_2_ACCESS_ACTION_END ===

        # Phân công điều tra được mở cho ADMIN/SO, Xã/phường và Trường.
        # Phạm vi cụ thể tiếp tục được kiểm tra tại _co_quyen_dieu_tra.
        if (
            normalized_path.startswith("/dieu-tra")
            and "/phan-cong" in normalized_path
        ):
            return can_manage_survey_assignments(role_code)

        # Biểu mẫu sửa đối tượng chỉ dành cho ADMIN/SO và Giáo viên.
        if (
            method in SAFE_METHODS
            and re.search(r"/doi-tuong/\d+/sua$", normalized_path)
        ):
            return (
                is_admin_role(role_code)
                or role_code == TEACHER_ROLE_CODE
            )

        # === BAI_13B_12_V2_4_3_10_ACCESS_POST_CSVC_ALL_LEVELS ===
        # Quyền qua MIDDLEWARE cho dữ liệu CSVC.
        # Phạm vi school_id cụ thể tiếp tục được router kiểm tra.
        if normalized_path.startswith("/csvc"):
            if method in SAFE_METHODS:
                return role_code in {
                    *ADMIN_ROLE_CODES,
                    DEPARTMENT_ROLE_CODE,
                    COMMUNE_ROLE_CODE,
                    SCHOOL_ROLE_CODE,
                }
            return (
                is_admin_role(role_code)
                or role_code in {
                    COMMUNE_ROLE_CODE,
                    SCHOOL_ROLE_CODE,
                }
            )

        # Biểu CSVC cấu trúc dùng chung cho Tiểu học / THCS /
        # trường liên cấp; slug phải kết thúc bằng "csvc".
        is_structured_csvc = bool(
            re.fullmatch(
                r"/bieu-nhap/[a-z0-9-]*csvc",
                normalized_path.lower(),
            )
        )
        if is_structured_csvc:
            if method in SAFE_METHODS:
                return role_code in {
                    *ADMIN_ROLE_CODES,
                    DEPARTMENT_ROLE_CODE,
                    COMMUNE_ROLE_CODE,
                    SCHOOL_ROLE_CODE,
                }
            return (
                is_admin_role(role_code)
                or role_code in {
                    COMMUNE_ROLE_CODE,
                    SCHOOL_ROLE_CODE,
                }
            )

        # === BAI_13B_12_V2_4_4_1_STRUCTURED_STAFF_POST ===
        # Cho phép tài khoản đơn vị Trường/Xã lưu dữ liệu
        # TH-01-GV / THCS-01-GV. Router vẫn khóa đúng school_id.
        is_structured_staff = bool(
            re.fullmatch(
                r"/bieu-nhap/(?:th|thcs)-01-gv",
                normalized_path.lower(),
            )
        )
        if is_structured_staff:
            if method in SAFE_METHODS:
                return role_code in {
                    *ADMIN_ROLE_CODES,
                    DEPARTMENT_ROLE_CODE,
                    COMMUNE_ROLE_CODE,
                    SCHOOL_ROLE_CODE,
                }
            return (
                is_admin_role(role_code)
                or role_code in {
                    COMMUNE_ROLE_CODE,
                    SCHOOL_ROLE_CODE,
                }
            )

        if method in SAFE_METHODS:
            return True

        if is_admin_role(role_code):
            return True

        if role_code == SCHOOL_ROLE_CODE:
            return path.startswith("/tai-khoan")

        if role_code == TEACHER_ROLE_CODE:
            return path.startswith("/dieu-tra")

        # PHONG_BAN và XA chỉ xem hoặc xuất dữ liệu bằng yêu cầu GET.
        return False

    @staticmethod
    def _co_quyen_dieu_tra(*, db, path: str, auth_user: dict[str, Any]) -> bool:
        """
        - ADMIN/SO: toàn tỉnh và được quản trị.
        - PHONG_BAN: toàn tỉnh nhưng chỉ đọc/xuất.
        - XA: đúng xã/phường; được giao phiếu cho trường và khóa/mở trường.
        - TRUONG: các đợt/phiếu đã được xã giao; được phân công tiếp cho giáo viên.
        - GIAO_VIEN: phiếu được phân công trực tiếp, được nhập/cập nhật.
        """

        role_code = normalize_role_code(auth_user.get("role_code"))

        if role_code in {*ADMIN_ROLE_CODES, DEPARTMENT_ROLE_CODE}:
            return True

        normalized_path = path.rstrip("/") or "/"

        # === V12_STUDENT_RECONCILIATION_SOURCE_SCOPE_START ===
        if normalized_path.startswith("/dieu-tra/nguon-hoc-sinh-doi-chieu"):
            return role_code == COMMUNE_ROLE_CODE
        # === V12_STUDENT_RECONCILIATION_SOURCE_SCOPE_END ===

        if normalized_path.startswith("/dieu-tra/dieu-hanh-trien-khai"):
            return role_code in {
                *ADMIN_ROLE_CODES,
                DEPARTMENT_ROLE_CODE,
            }

        if normalized_path == "/dieu-tra":
            return True

        # === BAI_13B_9_V1A_ACCESS_SCOPE_START ===
        if normalized_path.startswith("/dieu-tra/cap-nhat-ho-dan"):
            # V2.3: Xã/Trường/GV đều bị chặn; ADMIN/SO đã qua ở đầu hàm.
            return False
        # V2.3: Cập nhật hộ tập trung chỉ dành cho ADMIN/SO.
        # === BAI_13B_9_V1A_ACCESS_SCOPE_END ===

        # Bài 12D-14A: Trung tâm dữ liệu lịch sử dùng URL chung,
        # không có batch_id. Router tiếp tục lọc đúng xã/phường của tài khoản XA.
        if normalized_path.startswith("/dieu-tra/du-lieu-lich-su"):
            return role_code == COMMUNE_ROLE_CODE

        # Bài 12D-12: Trung tâm phiếu điều tra dùng một URL chung
        # không chứa batch_id. Tài khoản cấp xã chỉ được xem phạm vi
        # xã/phường của chính mình; phạm vi này tiếp tục được lọc tại router.
        if normalized_path.startswith("/dieu-tra/trung-tam-phieu"):
            return role_code == COMMUNE_ROLE_CODE

        # === BAI_13B_12_V2_2_ACCESS_SCOPE_START ===
        if normalized_path.startswith(
            "/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/"
        ):
            if role_code != TEACHER_ROLE_CODE:
                return False

            user_id = auth_user.get("id")
            if user_id is None:
                return False

            # === BAI_13B_12_V2_3_2_EXTRACT_BATCH_ID_START ===
            # Route này có dạng:
            # /dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/<batch_id>
            # /.../<batch_id>/quyen
            # /.../<batch_id>/them
            # Không dùng biến batch_id của các nhánh phía dưới vì tại đây
            # biến đó chưa được gán, gây UnboundLocalError.
            _b13232_prefix = (
                "/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/"
            )
            _b13232_tail = normalized_path[
                len(_b13232_prefix):
            ]
            _b13232_batch_token = (
                _b13232_tail.split("/", 1)[0].strip()
            )
            try:
                _b13232_batch_id = int(
                    _b13232_batch_token
                )
            except (TypeError, ValueError):
                return False

            if _b13232_batch_id <= 0:
                return False
            # === BAI_13B_12_V2_3_2_EXTRACT_BATCH_ID_END ===

            allowed = db.execute(
                text(
                    """
                    SELECT 1
                    FROM survey_investigation_teams AS t
                    JOIN survey_investigation_team_members AS tm
                      ON tm.team_id = t.id
                    WHERE t.survey_batch_id = :batch_id
                      AND t.status = 'SENT'
                      AND tm.user_id = :user_id
                    LIMIT 1
                    """
                ),
                {
                    "batch_id": _b13232_batch_id,
                    "user_id": int(user_id),
                },
            ).scalar()
            return allowed is not None
        # === BAI_13B_12_V2_2_ACCESS_SCOPE_END ===

        # === BAI_13B_10_V1_ACCESS_START ===
        # Đây là bước trước khi xã phân hộ. Trường phải vào được dù
        # chưa có survey_form_investigators trong đợt mới.
        if normalized_path.startswith(
            "/dieu-tra/phan-cong-to-dieu-tra"
        ):
            return role_code in {
                COMMUNE_ROLE_CODE,
                SCHOOL_ROLE_CODE,
            }
        # === BAI_13B_10_V1_ACCESS_END ===

        if normalized_path == "/dieu-tra/them":
            return False

        batch_match = re.match(
            r"^/dieu-tra/(?P<batch_id>\d+)(?:/|$)",
            normalized_path,
        )
        if batch_match is None:
            return False

        batch_id = int(batch_match.group("batch_id"))
        batch_commune_id = db.execute(
            text(
                """
                SELECT commune_id
                FROM survey_batches
                WHERE id = :batch_id
                """
            ),
            {"batch_id": batch_id},
        ).scalar()
        if batch_commune_id is None:
            return False

        # Bài 13B-4 V5.2: cho phép đúng luồng Theo dõi và khóa trường.
        # Kiểm tra bằng đường dẫn đầy đủ thay vì phụ thuộc vào menu hoặc
        # bố cục giao diện. Tài khoản xã chỉ được mở đợt thuộc đúng xã;
        # tài khoản trường chỉ được xem nhiệm vụ của chính trường đã giao.
        school_workflow_path = re.match(
            rf"^/dieu-tra/{batch_id}/phan-cong-truong(?:/|$)",
            normalized_path,
        )
        if school_workflow_path is not None:
            if role_code == COMMUNE_ROLE_CODE:
                commune_id = auth_user.get("commune_id")
                if commune_id is None:
                    return False
                try:
                    return int(batch_commune_id) == int(commune_id)
                except (TypeError, ValueError):
                    return False

            # === BAI_13B_11_8_SCHOOL_WORKFLOW_SCOPE_START ===
            if role_code == SCHOOL_ROLE_CODE:
                school_id = auth_user.get("school_id")
                if school_id is None:
                    return False

                try:
                    school_id_int = int(school_id)
                except (TypeError, ValueError):
                    return False

                school_commune_id = db.execute(
                    text(
                        """
                        SELECT commune_id
                        FROM schools
                        WHERE id = :school_id
                        """
                    ),
                    {"school_id": school_id_int},
                ).scalar()
                if school_commune_id is None:
                    return False

                try:
                    if int(school_commune_id) != int(batch_commune_id):
                        return False
                except (TypeError, ValueError):
                    return False

                assigned = db.execute(
                    text(
                        """
                        SELECT 1
                        FROM survey_school_assignments
                        WHERE survey_batch_id = :batch_id
                          AND school_id = :school_id
                        LIMIT 1
                        """
                    ),
                    {
                        "batch_id": batch_id,
                        "school_id": school_id_int,
                    },
                ).scalar()

                if assigned is not None:
                    return True

                assigned_form = db.execute(
                    text(
                        """
                        SELECT 1
                        FROM survey_forms AS sf
                        JOIN survey_form_investigators AS sfi
                          ON sfi.survey_form_id = sf.id
                        JOIN users AS u
                          ON u.id = sfi.user_id
                        WHERE sf.survey_batch_id = :batch_id
                          AND u.school_id = :school_id
                        LIMIT 1
                        """
                    ),
                    {
                        "batch_id": batch_id,
                        "school_id": school_id_int,
                    },
                ).scalar()

                return assigned_form is not None
            # === BAI_13B_11_8_SCHOOL_WORKFLOW_SCOPE_END ===

            return False

        if role_code == COMMUNE_ROLE_CODE:
            commune_id = auth_user.get("commune_id")
            return (
                commune_id is not None
                and int(batch_commune_id) == int(commune_id)
            )


        # === FIX_HOUSEHOLD_LIST_SCOPE_3_ROLES_V1_START ===
        # Trang danh sách hộ là "cửa vào" của 2.2.1.
        #
        # Router danh_sach_ho_dan() đã tự lọc:
        # - Xã: toàn bộ phiếu đúng xã/phường.
        # - Trường: chỉ phiếu đã giao cho nhân sự thuộc trường.
        # - Giáo viên: chỉ phiếu được giao trực tiếp.
        #
        # Vì vậy middleware chỉ kiểm tra PHẠM VI ĐỊA BÀN cho URL danh sách,
        # còn quyền xem từng hộ cụ thể vẫn tiếp tục bị kiểm tra theo phân công
        # ở các nhánh household_match phía dưới.
        base_household_list = re.fullmatch(
            r"/dieu-tra/\d+/ho-dan",
            normalized_path,
        )
        if (
            base_household_list is not None
            and role_code in {
                SCHOOL_ROLE_CODE,
                TEACHER_ROLE_CODE,
            }
        ):
            school_id = auth_user.get("school_id")
            if school_id is None:
                return False

            school_commune_id = db.execute(
                text(
                    "SELECT commune_id "
                    "FROM schools "
                    "WHERE id = :school_id "
                    "LIMIT 1"
                ),
                {"school_id": int(school_id)},
            ).scalar()

            if school_commune_id is None:
                return False

            return int(batch_commune_id) == int(school_commune_id)
        # === FIX_HOUSEHOLD_LIST_SCOPE_3_ROLES_V1_END ===

        if normalized_path.endswith("/ho-dan/them"):
            return False

        # Báo cáo tiến độ và tệp xuất của Trường/Giáo viên dùng phạm vi
        # toàn trường: chỉ cần đợt có ít nhất một phiếu được phân công
        # cho nhân sự thuộc trường đó.
        is_school_report_path = (
            normalized_path.endswith("/tien-do")
            or "/kiem-tra-du-lieu" in normalized_path
            or "/xuat-excel" in normalized_path
            or "/nhap-excel" in normalized_path
        )
        if is_school_report_path and role_code in {
            SCHOOL_ROLE_CODE,
            TEACHER_ROLE_CODE,
        }:
            if role_code == TEACHER_ROLE_CODE:
                user_id = auth_user.get("id")
                if user_id is None:
                    return False
                allowed = db.execute(
                    text(
                        """
                        SELECT 1
                        FROM survey_forms AS sf
                        JOIN survey_form_investigators AS sfi
                            ON sfi.survey_form_id = sf.id
                        WHERE sf.survey_batch_id = :batch_id
                          AND sfi.user_id = :user_id
                        LIMIT 1
                        """
                    ),
                    {
                        "batch_id": batch_id,
                        "user_id": int(user_id),
                    },
                ).scalar()
                return allowed is not None

            school_id = auth_user.get("school_id")
            if school_id is None:
                return False
            allowed = db.execute(
                text(
                    """
                    SELECT 1
                    FROM survey_school_assignments
                    WHERE survey_batch_id = :batch_id
                      AND school_id = :school_id
                    UNION ALL
                    SELECT 1
                    FROM survey_forms AS sf
                    JOIN survey_form_investigators AS sfi
                        ON sfi.survey_form_id = sf.id
                    JOIN users AS assigned_user
                        ON assigned_user.id = sfi.user_id
                    WHERE sf.survey_batch_id = :batch_id
                      AND assigned_user.school_id = :school_id
                      AND assigned_user.is_active = 1
                    LIMIT 1
                    """
                ),
                {
                    "batch_id": batch_id,
                    "school_id": int(school_id),
                },
            ).scalar()
            return allowed is not None

        household_match = re.match(
            r"^/dieu-tra/(?P<batch_id>\d+)/ho-dan/(?P<household_id>\d+)(?:/|$)",
            normalized_path,
        )

        if household_match is not None:
            household_id = int(household_match.group("household_id"))

            if role_code == TEACHER_ROLE_CODE:
                allowed = db.execute(
                    text(
                        """
                        SELECT 1
                        FROM survey_forms AS sf
                        JOIN survey_form_investigators AS sfi
                            ON sfi.survey_form_id = sf.id
                        WHERE sf.survey_batch_id = :batch_id
                          AND sf.household_id = :household_id
                          AND sfi.user_id = :user_id
                        LIMIT 1
                        """
                    ),
                    {
                        "batch_id": batch_id,
                        "household_id": household_id,
                        "user_id": auth_user.get("id"),
                    },
                ).scalar()
                return allowed is not None

            if role_code == SCHOOL_ROLE_CODE:
                school_id = auth_user.get("school_id")
                if school_id is None:
                    return False
                allowed = db.execute(
                    text(
                        """
                        SELECT 1
                        FROM survey_forms AS sf
                        JOIN survey_form_investigators AS sfi
                            ON sfi.survey_form_id = sf.id
                        JOIN users AS assigned_user
                            ON assigned_user.id = sfi.user_id
                        WHERE sf.survey_batch_id = :batch_id
                          AND sf.household_id = :household_id
                          AND assigned_user.school_id = :school_id
                          AND assigned_user.is_active = 1
                        LIMIT 1
                        """
                    ),
                    {
                        "batch_id": batch_id,
                        "household_id": household_id,
                        "school_id": school_id,
                    },
                ).scalar()
                return allowed is not None

            return False

        if role_code == TEACHER_ROLE_CODE:
            allowed = db.execute(
                text(
                    """
                    SELECT 1
                    FROM survey_forms AS sf
                    JOIN survey_form_investigators AS sfi
                        ON sfi.survey_form_id = sf.id
                    WHERE sf.survey_batch_id = :batch_id
                      AND sfi.user_id = :user_id
                    LIMIT 1
                    """
                ),
                {
                    "batch_id": batch_id,
                    "user_id": auth_user.get("id"),
                },
            ).scalar()
            return allowed is not None

        if role_code == SCHOOL_ROLE_CODE:
            school_id = auth_user.get("school_id")
            if school_id is None:
                return False
            allowed = db.execute(
                text(
                    """
                    SELECT 1
                    FROM survey_school_assignments
                    WHERE survey_batch_id = :batch_id
                      AND school_id = :school_id
                    UNION ALL
                    SELECT 1
                    FROM survey_forms AS sf
                    JOIN survey_form_investigators AS sfi
                        ON sfi.survey_form_id = sf.id
                    JOIN users AS assigned_user
                        ON assigned_user.id = sfi.user_id
                    WHERE sf.survey_batch_id = :batch_id
                      AND assigned_user.school_id = :school_id
                      AND assigned_user.is_active = 1
                    LIMIT 1
                    """
                ),
                {"batch_id": batch_id, "school_id": school_id},
            ).scalar()
            return allowed is not None

        return False

    @staticmethod
    def _kiem_tra_khoa_dot_dieu_tra(
        *,
        db,
        path: str,
        method: str,
        role_code: str,
        auth_user: dict[str, Any],
    ) -> tuple[int, str] | None:
        """
        Chặn thao tác ghi theo thứ tự ưu tiên:
        khóa cấp tỉnh -> khóa cấp xã -> khóa riêng trường.
        """

        if method in SAFE_METHODS:
            return None

        normalized_path = path.rstrip("/") or "/"
        batch_match = re.match(
            r"^/dieu-tra/(?P<batch_id>\d+)(?:/|$)",
            normalized_path,
        )
        if batch_match is None:
            return None

        batch_id = int(batch_match.group("batch_id"))

        # === BAI_13B_9_V1A_ACCESS_LOCK_START ===
        # V1A chỉ tiếp nhận vào vùng chờ, chưa ghi dữ liệu hộ dân.
        # Cho router nhận file để trả trạng thái rõ ràng kể cả khi đợt khóa.
        if normalized_path == (
            f"/dieu-tra/{batch_id}/cap-nhat-ho-dan/gui-file"
        ):
            return None
        # === BAI_13B_9_V1A_ACCESS_LOCK_END ===

        legacy_lock_actions = {
            f"/dieu-tra/{batch_id}/chot-so-lieu/khoa",
            f"/dieu-tra/{batch_id}/chot-so-lieu/mo-khoa",
        }
        if normalized_path in legacy_lock_actions:
            if is_admin_role(role_code):
                return None
            return batch_id, "lock_admin_only"

        is_year_inheritance_action = normalized_path in {
            f"/dieu-tra/{batch_id}/ke-thua-du-lieu",
            f"/dieu-tra/{batch_id}/ke-thua-du-lieu/tao-dot-dich",
        }
        if is_year_inheritance_action:
            if is_admin_role(role_code):
                return None
            return batch_id, "lock_admin_only"

        # Các thao tác quản lý khóa được router kiểm tra chi tiết quyền.
        is_commune_open_action = (
            normalized_path == f"/dieu-tra/{batch_id}/mo-khoa-xa"
        )
        is_commune_lock_action = (
            normalized_path == f"/dieu-tra/{batch_id}/khoa-xa"
        )
        is_school_management_action = (
            f"/dieu-tra/{batch_id}/phan-cong-truong/" in normalized_path
            and not normalized_path.endswith("/gui-xa")
        )

        try:
            state = db.execute(
                text(
                    """
                    SELECT
                        sb.is_locked,
                        COALESCE(state.is_province_locked, 0)
                            AS is_province_locked,
                        COALESCE(
                            state.is_commune_locked,
                            sb.is_locked,
                            0
                        ) AS is_commune_locked
                    FROM survey_batches AS sb
                    LEFT JOIN survey_commune_execution_states AS state
                        ON state.survey_batch_id = sb.id
                    WHERE sb.id = :batch_id
                    """
                ),
                {"batch_id": batch_id},
            ).mappings().first()
        except Exception:
            # Trong lúc chạy bộ cài, bảng mới có thể chưa tồn tại.
            return None

        if state is None:
            return None

        province_locked = bool(state["is_province_locked"])
        commune_locked = bool(state["is_commune_locked"])
        batch_locked = bool(state["is_locked"])

        if is_commune_open_action:
            if province_locked:
                return batch_id, "province_locked"
            return None

        if is_commune_lock_action:
            if province_locked:
                return batch_id, "province_locked"
            return None

        if is_school_management_action:
            if province_locked:
                return batch_id, "province_locked"
            if commune_locked or batch_locked:
                return batch_id, "batch_locked"
            return None

        if province_locked:
            return batch_id, "province_locked"

        if commune_locked or batch_locked:
            return batch_id, "batch_locked"

        if role_code in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}:
            school_id = auth_user.get("school_id")
            if school_id is not None:
                try:
                    school_locked = db.execute(
                        text(
                            """
                            SELECT is_locked
                            FROM survey_school_assignments
                            WHERE survey_batch_id = :batch_id
                              AND school_id = :school_id
                            """
                        ),
                        {
                            "batch_id": batch_id,
                            "school_id": int(school_id),
                        },
                    ).scalar()
                except Exception:
                    school_locked = None

                if bool(school_locked):
                    return batch_id, "school_locked"

        return None


    @staticmethod
    def _la_duong_dan_cong_khai(path: str) -> bool:
        if path in PUBLIC_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)

    @staticmethod
    async def _chuyen_den_dang_nhap(scope, receive, send) -> None:
        response = RedirectResponse(
            url="/dang-nhap?status=required",
            status_code=303,
        )
        await response(scope, receive, send)

    @staticmethod
    async def _tu_choi_truy_cap(scope, receive, send) -> None:
        response = RedirectResponse(
            url="/?status=forbidden",
            status_code=303,
        )
        await response(scope, receive, send)
