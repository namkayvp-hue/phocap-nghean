from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Commune


# Thư mục app
APP_DIR = Path(__file__).resolve().parent.parent

# Thư mục chứa giao diện HTML
templates = Jinja2Templates(
    directory=str(APP_DIR / "templates")
)

# Nhóm đường dẫn quản lý xã
router = APIRouter(
    prefix="/xa",
    tags=["Danh mục xã"],
)


STATUS_MESSAGES = {
    "created": "Đã thêm xã mới thành công.",
    "updated": "Đã cập nhật thông tin xã thành công.",
    "locked": "Đã khóa xã thành công.",
    "unlocked": "Đã mở lại xã thành công.",
    "duplicate": "Mã xã đã tồn tại trong hệ thống.",
    "invalid": "Mã xã và tên xã không được để trống.",
}


def chuan_hoa_ma_xa(ma_xa: str) -> str:
    """
    Xóa khoảng trắng và chuyển mã xã thành chữ in hoa.
    """

    return ma_xa.strip().upper()


def chuan_hoa_ten_xa(ten_xa: str) -> str:
    """
    Xóa khoảng trắng thừa trong tên xã.
    """

    return " ".join(ten_xa.strip().split())


@router.get("", response_class=HTMLResponse)
def danh_sach_xa(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
):
    """
    Hiển thị toàn bộ danh mục xã.
    """

    statement = select(Commune).order_by(
        Commune.name.asc()
    )

    danh_sach = db.scalars(statement).all()

    return templates.TemplateResponse(
        request=request,
        name="communes/list.html",
        context={
            "danh_sach_xa": danh_sach,
            "thong_bao": STATUS_MESSAGES.get(status),
            "trang_thai": status,
        },
    )


@router.post("/them")
def them_xa(
    ma_xa: Annotated[str, Form()],
    ten_xa: Annotated[str, Form()],
    is_special_difficulty_area: Annotated[bool, Form()] = False,
    db: Session = Depends(get_db),
):
    """
    Nhận dữ liệu từ biểu mẫu và thêm một xã mới.
    """

    ma_xa = chuan_hoa_ma_xa(ma_xa)
    ten_xa = chuan_hoa_ten_xa(ten_xa)

    if not ma_xa or not ten_xa:
        return RedirectResponse(
            url="/xa?status=invalid",
            status_code=303,
        )

    if len(ma_xa) > 30 or len(ten_xa) > 200:
        return RedirectResponse(
            url="/xa?status=invalid",
            status_code=303,
        )

    statement = select(Commune).where(
        Commune.code == ma_xa
    )

    xa_da_co = db.scalar(statement)

    if xa_da_co is not None:
        return RedirectResponse(
            url="/xa?status=duplicate",
            status_code=303,
        )

    xa_moi = Commune(
        code=ma_xa,
        name=ten_xa,
        is_active=True,
        is_special_difficulty_area=bool(is_special_difficulty_area),
    )

    db.add(xa_moi)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        return RedirectResponse(
            url="/xa?status=duplicate",
            status_code=303,
        )

    return RedirectResponse(
        url="/xa?status=created",
        status_code=303,
    )


@router.get(
    "/{commune_id}/sua",
    response_class=HTMLResponse,
)
def form_sua_xa(
    commune_id: int,
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
):
    """
    Hiển thị biểu mẫu sửa một xã.
    """

    xa = db.get(Commune, commune_id)

    if xa is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy xã.",
        )

    return templates.TemplateResponse(
        request=request,
        name="communes/edit.html",
        context={
            "xa": xa,
            "thong_bao": STATUS_MESSAGES.get(status),
        },
    )


@router.post("/{commune_id}/sua")
def cap_nhat_xa(
    commune_id: int,
    ma_xa: Annotated[str, Form()],
    ten_xa: Annotated[str, Form()],
    is_special_difficulty_area: Annotated[bool, Form()] = False,
    db: Session = Depends(get_db),
):
    """
    Cập nhật mã và tên xã.
    """

    xa = db.get(Commune, commune_id)

    if xa is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy xã.",
        )

    ma_xa = chuan_hoa_ma_xa(ma_xa)
    ten_xa = chuan_hoa_ten_xa(ten_xa)

    if not ma_xa or not ten_xa:
        return RedirectResponse(
            url=f"/xa/{commune_id}/sua?status=invalid",
            status_code=303,
        )

    statement = select(Commune).where(
        Commune.code == ma_xa,
        Commune.id != commune_id,
    )

    xa_trung_ma = db.scalar(statement)

    if xa_trung_ma is not None:
        return RedirectResponse(
            url=f"/xa/{commune_id}/sua?status=duplicate",
            status_code=303,
        )

    xa.code = ma_xa
    xa.name = ten_xa
    xa.is_special_difficulty_area = bool(is_special_difficulty_area)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        return RedirectResponse(
            url=f"/xa/{commune_id}/sua?status=duplicate",
            status_code=303,
        )

    return RedirectResponse(
        url="/xa?status=updated",
        status_code=303,
    )


@router.post("/{commune_id}/khoa-mo")
def khoa_hoac_mo_xa(
    commune_id: int,
    db: Session = Depends(get_db),
):
    """
    Khóa một xã đang hoạt động hoặc mở lại xã đã khóa.
    """

    xa = db.get(Commune, commune_id)

    if xa is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy xã.",
        )

    xa.is_active = not xa.is_active
    db.commit()

    status = (
        "unlocked"
        if xa.is_active
        else "locked"
    )

    return RedirectResponse(
        url=f"/xa?status={status}",
        status_code=303,
    )