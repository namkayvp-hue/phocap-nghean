from __future__ import annotations

from datetime import date

# === BAI_13B_7_V1_DO_TUOI_DIEU_TRA ===
# Người dùng chốt:
# - Phổ cập giáo dục: 0 đến 18 tuổi, tính cả 0 và 18.
# - Xóa mù chữ: 18 đến 60 tuổi, tính cả 18 và 60.
# => Tuổi 18 thuộc CẢ HAI phạm vi.

PCGD_MIN_AGE = 0
PCGD_MAX_AGE = 18
XMC_MIN_AGE = 18
XMC_MAX_AGE = 60


def tinh_tuoi_tai_ngay(ngay_sinh: date | None, ngay_tham_chieu: date) -> int | None:
    if ngay_sinh is None:
        return None
    return (
        ngay_tham_chieu.year
        - ngay_sinh.year
        - ((ngay_tham_chieu.month, ngay_tham_chieu.day) < (ngay_sinh.month, ngay_sinh.day))
    )


def pham_vi_theo_tuoi(tuoi: int | None) -> dict[str, bool]:
    if tuoi is None:
        return {"pho_cap": False, "xoa_mu_chu": False}

    return {
        "pho_cap": PCGD_MIN_AGE <= tuoi <= PCGD_MAX_AGE,
        "xoa_mu_chu": XMC_MIN_AGE <= tuoi <= XMC_MAX_AGE,
    }


def pham_vi_theo_ngay_sinh(
    ngay_sinh: date | None,
    ngay_tham_chieu: date,
) -> dict[str, bool | int | None]:
    tuoi = tinh_tuoi_tai_ngay(ngay_sinh, ngay_tham_chieu)
    scopes = pham_vi_theo_tuoi(tuoi)
    return {
        "tuoi": tuoi,
        **scopes,
    }
