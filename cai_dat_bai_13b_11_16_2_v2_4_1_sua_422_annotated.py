from __future__ import annotations

import py_compile
import re
import shutil
from datetime import datetime
from pathlib import Path

MARK_V23 = "BAI_13B_11_16_2_V2_3_LOGIN_ACCOUNT_SCOPE_START"
MARK_V241 = "BAI_13B_11_16_2_V2_4_1_EMPTY_ID_QUERY_FIX"

ROUTE_MARKERS = (
    '@router.get("/dang-nhap/api/lua-chon")',
    '@router.get("/api/lua-chon")',
)


def main() -> int:
    root = Path(r"C:\PhoCap")
    auth_path = root / "app" / "routers" / "auth.py"

    if not auth_path.is_file():
        root = Path.cwd()
        auth_path = root / "app" / "routers" / "auth.py"

    print("=" * 100)
    print("BÀI 13B-11-16.2 V2.4.1 - SỬA 422 API SỞ/XÃ (ANNOTATED)")
    print("=" * 100)
    print(f"Dự án: {root}")
    print()

    if not auth_path.is_file():
        print("DỪNG AN TOÀN: không tìm thấy app/routers/auth.py")
        return 2

    text = auth_path.read_text(encoding="utf-8")

    if MARK_V241 in text:
        print("V2.4.1 đã có trong mã nguồn. Không cài lặp.")
        return 0

    if MARK_V23 not in text:
        print("DỪNG AN TOÀN: chưa thấy dấu V2.3 trong auth.py.")
        print("Không sửa trên nền mã nguồn khác.")
        return 3

    route_pos = -1
    route_marker = None

    for marker in ROUTE_MARKERS:
        pos = text.find(marker)
        if pos >= 0:
            route_pos = pos
            route_marker = marker
            break

    if route_pos < 0:
        print("DỪNG AN TOÀN: không tìm thấy route API đăng nhập.")
        return 4

    # Chỉ thao tác trong vùng đầu của route API.
    window_end = min(len(text), route_pos + 5000)
    window = text[route_pos:window_end]

    # Hỗ trợ đúng dạng hiện tại:
    # commune_id: Annotated[int | None, Query()] = None
    # school_id: Annotated[int | None, Query()] = None
    patterns = {
        "commune_id": re.compile(
            r'(\bcommune_id\s*:\s*Annotated\[\s*)int(\s*\|\s*None\s*,\s*Query\(\)\s*\])'
        ),
        "school_id": re.compile(
            r'(\bschool_id\s*:\s*Annotated\[\s*)int(\s*\|\s*None\s*,\s*Query\(\)\s*\])'
        ),
    }

    counts = {
        name: len(list(pattern.finditer(window)))
        for name, pattern in patterns.items()
    }

    print("Kiểm tra chữ ký API hiện tại:")
    print(f" - commune_id Annotated[int|None, Query()]: {counts['commune_id']} vị trí")
    print(f" - school_id Annotated[int|None, Query()]: {counts['school_id']} vị trí")

    if counts["commune_id"] != 1 or counts["school_id"] != 1:
        print()
        print("DỪNG AN TOÀN: chữ ký API vẫn khác cấu trúc dự kiến.")
        print("Không ghi đè.")
        return 5

    new_window = patterns["commune_id"].sub(
        r'\1str\2',
        window,
        count=1,
    )
    new_window = patterns["school_id"].sub(
        r'\1str\2',
        new_window,
        count=1,
    )

    # Gắn marker ngay sau decorator route.
    first_newline = new_window.find("\n")
    if first_newline < 0:
        print("DỪNG AN TOÀN: không xác định được decorator.")
        return 6

    new_window = (
        new_window[:first_newline + 1]
        + f"# === {MARK_V241} ===\n"
        + new_window[first_newline + 1:]
    )

    new_text = (
        text[:route_pos]
        + new_window
        + text[window_end:]
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (
        root
        / "exports"
        / f"backup_truoc_bai_13b_11_16_2_v2_4_1_{stamp}"
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
        py_compile.compile(str(auth_path), doraise=True)

        verify = auth_path.read_text(encoding="utf-8")

        if MARK_V241 not in verify:
            raise RuntimeError("Thiếu marker V2.4.1 sau cài.")

        route_pos2 = verify.find(route_marker)
        verify_window = verify[
            route_pos2:min(len(verify), route_pos2 + 5000)
        ]

        if re.search(
            r'\bcommune_id\s*:\s*Annotated\[\s*int\s*\|\s*None\s*,\s*Query\(\)\s*\]',
            verify_window,
        ):
            raise RuntimeError("commune_id vẫn còn Annotated[int|None].")

        if re.search(
            r'\bschool_id\s*:\s*Annotated\[\s*int\s*\|\s*None\s*,\s*Query\(\)\s*\]',
            verify_window,
        ):
            raise RuntimeError("school_id vẫn còn Annotated[int|None].")

        if not re.search(
            r'\bcommune_id\s*:\s*Annotated\[\s*str\s*\|\s*None\s*,\s*Query\(\)\s*\]',
            verify_window,
        ):
            raise RuntimeError("commune_id chưa chuyển thành Annotated[str|None].")

        if not re.search(
            r'\bschool_id\s*:\s*Annotated\[\s*str\s*\|\s*None\s*,\s*Query\(\)\s*\]',
            verify_window,
        ):
            raise RuntimeError("school_id chưa chuyển thành Annotated[str|None].")

    except Exception as exc:
        shutil.copy2(backup_path, auth_path)
        print()
        print("CÀI LỖI - ĐÃ TỰ KHÔI PHỤC auth.py.")
        print("Chi tiết:", exc)
        return 7

    report = (
        root
        / "exports"
        / f"bao_cao_dang_nhap_v2_4_1_{stamp}.txt"
    )

    report.write_text(
        "\n".join(
            [
                "BÁO CÁO BÀI 13B-11-16.2 V2.4.1",
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                f"Dự án: {root}",
                "",
                "NGUYÊN NHÂN:",
                (
                    "V2.4 tìm dạng commune_id: int|None, "
                    "nhưng mã nguồn thực tế dùng "
                    "Annotated[int|None, Query()]."
                ),
                "",
                "ĐÃ SỬA:",
                (
                    "commune_id: Annotated[int|None, Query()] "
                    "-> Annotated[str|None, Query()]"
                ),
                (
                    "school_id: Annotated[int|None, Query()] "
                    "-> Annotated[str|None, Query()]"
                ),
                (
                    "Hàm _safe_id() của V2.3 vẫn chuyển chuỗi số "
                    "thành ID hợp lệ bên trong backend."
                ),
                "Không thay đổi database.",
                "Không thay đổi luồng Trường/Giáo viên.",
                "",
                f"Backup: {backup_dir}",
            ]
        ) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 100)
    print("CÀI ĐẶT THÀNH CÔNG V2.4.1")
    print("=" * 100)
    print("Đã sửa đúng 1 file:")
    print(" - app/routers/auth.py")
    print()
    print("Sau khi khởi động lại, các request sau phải trả 200 OK:")
    print(
        " - /dang-nhap/api/lua-chon?"
        "loai=accounts&cap=SO&commune_id=&school_id=&q="
    )
    print(
        " - /dang-nhap/api/lua-chon?"
        "loai=accounts&cap=XA&commune_id=114&school_id=&q="
    )
    print()
    print(f"Backup: {backup_dir}")
    print(f"Báo cáo: {report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
