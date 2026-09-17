from __future__ import annotations

import py_compile
import re
import shutil
from datetime import datetime
from pathlib import Path

MARK_V23 = "BAI_13B_11_16_2_V2_3_LOGIN_ACCOUNT_SCOPE_START"
MARK_V24 = "BAI_13B_11_16_2_V2_4_EMPTY_ID_QUERY_FIX"

ROUTE_PATTERNS = (
    '@router.get("/api/lua-chon")',
    '@router.get("/dang-nhap/api/lua-chon")',
)


def main() -> int:
    root = Path(r"C:\PhoCap")
    auth_path = root / "app" / "routers" / "auth.py"

    if not auth_path.is_file():
        root = Path.cwd()
        auth_path = root / "app" / "routers" / "auth.py"

    print("=" * 100)
    print("BÀI 13B-11-16.2 V2.4 - SỬA 422 API TÀI KHOẢN SỞ / XÃ")
    print("=" * 100)
    print(f"Dự án: {root}")
    print()

    if not auth_path.is_file():
        print("DỪNG AN TOÀN: không tìm thấy app/routers/auth.py")
        return 2

    text = auth_path.read_text(encoding="utf-8")

    if MARK_V24 in text:
        print("V2.4 đã có trong mã nguồn. Không cài lặp.")
        return 0

    if MARK_V23 not in text:
        print("DỪNG AN TOÀN: chưa thấy dấu V2.3 trong auth.py.")
        print("Không tự sửa trên nền mã nguồn khác.")
        return 3

    route_pos = -1
    route_marker = ""
    for pattern in ROUTE_PATTERNS:
        route_pos = text.find(pattern)
        if route_pos >= 0:
            route_marker = pattern
            break

    if route_pos < 0:
        print("DỪNG AN TOÀN: không tìm thấy route API /api/lua-chon.")
        return 4

    # Chỉ khảo sát vùng đầu của hàm API để không đụng các route khác.
    window_end = min(len(text), route_pos + 3500)
    before = text[route_pos:window_end]

    commune_pattern = re.compile(
        r'(\bcommune_id\s*:\s*)int(\s*\|\s*None)'
    )
    school_pattern = re.compile(
        r'(\bschool_id\s*:\s*)int(\s*\|\s*None)'
    )

    commune_matches = list(commune_pattern.finditer(before))
    school_matches = list(school_pattern.finditer(before))

    print("Kiểm tra chữ ký API:")
    print(f" - commune_id kiểu int|None: {len(commune_matches)} vị trí")
    print(f" - school_id kiểu int|None: {len(school_matches)} vị trí")

    if len(commune_matches) != 1 or len(school_matches) != 1:
        print()
        print("DỪNG AN TOÀN: chữ ký API khác cấu trúc dự kiến.")
        print("Không ghi đè.")
        return 5

    after_window = commune_pattern.sub(
        r'\1str\2',
        before,
        count=1,
    )
    after_window = school_pattern.sub(
        r'\1str\2',
        after_window,
        count=1,
    )

    # Gắn marker ngay sau decorator để lần sau nhận biết đã cài.
    decorator_line_end = after_window.find("\n")
    if decorator_line_end < 0:
        print("DỪNG AN TOÀN: không xác định được dòng decorator.")
        return 6

    after_window = (
        after_window[:decorator_line_end + 1]
        + f"# === {MARK_V24} ===\n"
        + after_window[decorator_line_end + 1:]
    )

    new_text = (
        text[:route_pos]
        + after_window
        + text[window_end:]
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (
        root
        / "exports"
        / f"backup_truoc_bai_13b_11_16_2_v2_4_{stamp}"
    )
    backup_path = (
        backup_dir
        / "app"
        / "routers"
        / "auth.py"
    )
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(auth_path, backup_path)

    try:
        auth_path.write_text(new_text, encoding="utf-8")

        py_compile.compile(
            str(auth_path),
            doraise=True,
        )

        verify = auth_path.read_text(encoding="utf-8")

        if MARK_V24 not in verify:
            raise RuntimeError("Thiếu marker V2.4 sau cài.")

        route_pos2 = verify.find(route_marker)
        check_window = verify[
            route_pos2:min(len(verify), route_pos2 + 3500)
        ]

        if re.search(
            r'\bcommune_id\s*:\s*int\s*\|\s*None',
            check_window,
        ):
            raise RuntimeError("commune_id vẫn còn kiểu int|None.")

        if re.search(
            r'\bschool_id\s*:\s*int\s*\|\s*None',
            check_window,
        ):
            raise RuntimeError("school_id vẫn còn kiểu int|None.")

        if not re.search(
            r'\bcommune_id\s*:\s*str\s*\|\s*None',
            check_window,
        ):
            raise RuntimeError("commune_id chưa chuyển thành str|None.")

        if not re.search(
            r'\bschool_id\s*:\s*str\s*\|\s*None',
            check_window,
        ):
            raise RuntimeError("school_id chưa chuyển thành str|None.")

    except Exception as exc:
        shutil.copy2(backup_path, auth_path)
        print()
        print("CÀI LỖI - ĐÃ TỰ KHÔI PHỤC auth.py.")
        print("Chi tiết:", exc)
        return 7

    report = (
        root
        / "exports"
        / f"bao_cao_dang_nhap_v2_4_{stamp}.txt"
    )
    report.write_text(
        "\n".join(
            [
                "BÁO CÁO BÀI 13B-11-16.2 V2.4",
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                f"Dự án: {root}",
                "",
                "NGUYÊN NHÂN:",
                (
                    "Frontend gửi commune_id= hoặc school_id= "
                    "khi ô chưa dùng."
                ),
                (
                    "FastAPI đang ép hai query này sang int trước "
                    "khi vào hàm, nên trả 422."
                ),
                "",
                "ĐÃ SỬA:",
                (
                    "commune_id và school_id của API đăng nhập "
                    "nhận str|None."
                ),
                (
                    "Bên trong hàm V2.3 vẫn dùng _safe_id() để "
                    "chuyển ID hợp lệ, nên phạm vi dữ liệu không đổi."
                ),
                "Không thay đổi database.",
                "Không thay đổi Trường/Giáo viên.",
                "",
                f"Backup: {backup_dir}",
            ]
        )
        + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 100)
    print("CÀI ĐẶT THÀNH CÔNG V2.4")
    print("=" * 100)
    print("Đã sửa đúng 1 file:")
    print(" - app/routers/auth.py")
    print()
    print("Mục tiêu sau sửa:")
    print(
        " - cap=SO&commune_id=&school_id=&q= "
        "không còn 422."
    )
    print(
        " - cap=XA&commune_id=114&school_id=&q= "
        "không còn 422."
    )
    print(" - Trường/Giáo viên giữ nguyên.")
    print(f"Backup: {backup_dir}")
    print(f"Báo cáo: {report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
