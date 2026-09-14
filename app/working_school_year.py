from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select

from app.database import get_db
from app.models import SchoolYear


SESSION_KEY = "working_school_year_id"

OPTIONS_PATH = "/nam-hoc-lam-viec/options"
SELECT_PATH = "/nam-hoc-lam-viec/chon"

# Những luồng đặc biệt tự quản lý nhiều năm học hoặc năm nguồn/năm đích.
# Không ép "Năm học làm việc" vào các luồng này.
EXCLUDED_PATH_PARTS = (
    "/static",
    "/dang-nhap",
    "/nam-hoc-lam-viec/",
    "khoi-tao-nam-hoc",
    "doi-chieu-nam-hoc",
    "du-lieu-lich-su",
)


def _db_session():
    generator = get_db()
    db = next(generator)
    return generator, db


def _active_years() -> list[SchoolYear]:
    generator, db = _db_session()

    try:
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
    finally:
        generator.close()


def _active_year_ids() -> set[int]:
    return {
        int(item.id)
        for item in _active_years()
    }


def _default_year_id() -> int | None:
    years = _active_years()

    if not years:
        return None

    return int(years[0].id)


def _safe_positive_int(value: Any) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    return number if number > 0 else None


def _should_skip(path: str) -> bool:
    lowered = str(path or "").lower()

    return any(
        part in lowered
        for part in EXCLUDED_PATH_PARTS
    )


def _replace_year_in_url(
    target: str,
    school_year_id: int,
) -> str:
    target = str(target or "/").strip()

    if (
        not target.startswith("/")
        or target.startswith("//")
    ):
        target = "/"

    parts = urlsplit(target)

    query_items = [
        (key, value)
        for key, value
        in parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
        if key != "school_year_id"
    ]

    query_items.append(
        (
            "school_year_id",
            str(school_year_id),
        )
    )

    return urlunsplit(
        (
            "",
            "",
            parts.path or "/",
            urlencode(
                query_items,
                doseq=True,
            ),
            parts.fragment,
        )
    )


def _inject_year_query(
    scope: dict[str, Any],
    school_year_id: int,
) -> None:
    raw = scope.get(
        "query_string",
        b"",
    )

    text = raw.decode(
        "latin-1",
        errors="ignore",
    )

    items = parse_qsl(
        text,
        keep_blank_values=True,
    )

    if any(
        key == "school_year_id"
        for key, _value in items
    ):
        return

    items.append(
        (
            "school_year_id",
            str(school_year_id),
        )
    )

    scope["query_string"] = urlencode(
        items,
        doseq=True,
    ).encode("latin-1")


class WorkingSchoolYearMiddleware:
    """
    Năm học làm việc dùng chung cho một phiên đăng nhập.

    Lưu ý thứ tự middleware:
    WorkingSchoolYearMiddleware phải được add TRƯỚC SessionMiddleware
    trong mã nguồn main.py để khi Starlette dựng middleware stack,
    SessionMiddleware nằm ngoài và tạo scope["session"] trước.
    """

    def __init__(
        self,
        app,
    ) -> None:
        self.app = app

    async def __call__(
        self,
        scope,
        receive,
        send,
    ) -> None:
        if scope.get("type") != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        path = str(
            scope.get(
                "path",
                "",
            )
            or ""
        )

        session = scope.get(
            "session"
        )

        # Nếu SessionMiddleware chưa chạy thì không can thiệp.
        if not isinstance(
            session,
            dict,
        ):
            await self.app(
                scope,
                receive,
                send,
            )
            return

        request = Request(
            scope,
            receive=receive,
        )

        if path == OPTIONS_PATH:
            if session.get(
                "user_id"
            ) is None:
                response = JSONResponse(
                    {
                        "ok": False,
                        "authenticated": False,
                        "selected_id": None,
                        "years": [],
                    },
                    status_code=401,
                )

                await response(
                    scope,
                    receive,
                    send,
                )
                return

            years = _active_years()
            valid_ids = {
                int(item.id)
                for item in years
            }

            selected = _safe_positive_int(
                session.get(
                    SESSION_KEY
                )
            )

            if selected not in valid_ids:
                selected = (
                    int(years[0].id)
                    if years
                    else None
                )

                if selected is None:
                    session.pop(
                        SESSION_KEY,
                        None,
                    )
                else:
                    session[
                        SESSION_KEY
                    ] = selected

            response = JSONResponse(
                {
                    "ok": True,
                    "authenticated": True,
                    "selected_id": selected,
                    "years": [
                        {
                            "id": int(item.id),
                            "code": str(
                                item.code
                                or ""
                            ),
                            "name": str(
                                getattr(
                                    item,
                                    "name",
                                    "",
                                )
                                or ""
                            ),
                        }
                        for item in years
                    ],
                }
            )

            await response(
                scope,
                receive,
                send,
            )
            return

        if path == SELECT_PATH:
            if session.get(
                "user_id"
            ) is None:
                response = RedirectResponse(
                    "/dang-nhap",
                    status_code=303,
                )

                await response(
                    scope,
                    receive,
                    send,
                )
                return

            selected = _safe_positive_int(
                request.query_params.get(
                    "school_year_id"
                )
            )

            if (
                selected is None
                or selected not in _active_year_ids()
            ):
                response = PlainTextResponse(
                    "Năm học không hợp lệ hoặc đã khóa.",
                    status_code=400,
                )

                await response(
                    scope,
                    receive,
                    send,
                )
                return

            session[
                SESSION_KEY
            ] = selected

            target = _replace_year_in_url(
                request.query_params.get(
                    "next",
                    "/",
                ),
                selected,
            )

            response = RedirectResponse(
                target,
                status_code=303,
            )

            await response(
                scope,
                receive,
                send,
            )
            return

        # Chỉ áp dụng cho tài khoản đã đăng nhập và GET/HEAD.
        if (
            session.get(
                "user_id"
            ) is None
            or scope.get(
                "method"
            ) not in {
                "GET",
                "HEAD",
            }
            or _should_skip(
                path
            )
        ):
            await self.app(
                scope,
                receive,
                send,
            )
            return

        explicit_year = _safe_positive_int(
            request.query_params.get(
                "school_year_id"
            )
        )

        selected = _safe_positive_int(
            session.get(
                SESSION_KEY
            )
        )

        # Nếu người dùng đổi Năm học ở một màn hình cũ,
        # đồng bộ lựa chọn đó thành Năm học làm việc chung.
        if (
            explicit_year is not None
            and explicit_year != selected
        ):
            if explicit_year in _active_year_ids():
                selected = explicit_year
                session[
                    SESSION_KEY
                ] = selected

        if selected is None:
            selected = _default_year_id()

            if selected is not None:
                session[
                    SESSION_KEY
                ] = selected

        # Không có query riêng -> tự đưa Năm học làm việc vào route cũ.
        if (
            selected is not None
            and explicit_year is None
        ):
            _inject_year_query(
                scope,
                selected,
            )

        await self.app(
            scope,
            receive,
            send,
        )
