from __future__ import annotations

import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
ROUTER = APP / "routers" / "data_tools.py"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_source_bai_13b_10_v3_18b3_{STAMP}"
MARK = "BAI_13B_10_V3_18B3_SAFE_QUERY_INT"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup_source() -> None:
    dst = BACKUP / ROUTER.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROUTER, dst)


def restore_source() -> None:
    src = BACKUP / ROUTER.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, ROUTER)


def patch_router(text: str) -> str:
    if MARK in text:
        return text

    if not re.search(r"(?m)^import re\s*$", text):
        anchor = "import json\n"
        if anchor not in text:
            raise RuntimeError(
                "Không tìm thấy vị trí import json trong data_tools.py."
            )
        text = text.replace(anchor, anchor + "import re\n", 1)

    helper_anchor = "\ndef _auth_user(request: Request)"
    if helper_anchor not in text:
        raise RuntimeError(
            "Không tìm thấy hàm _auth_user để chèn helper."
        )

    helper = (
        "\n# === BAI_13B_10_V3_18B3_SAFE_QUERY_INT ===\n"
        "def _safe_optional_int(value: Any) -> int | None:\n"
        "    if value is None:\n"
        "        return None\n"
        "\n"
        "    text = str(value).strip()\n"
        "    if not text:\n"
        "        return None\n"
        "\n"
        "    if re.fullmatch(r\"\\d+\", text):\n"
        "        return int(text)\n"
        "\n"
        "    return None\n"
    )

    text = text.replace(
        helper_anchor,
        helper + helper_anchor,
        1,
    )

    old_sig = (
        "def survey_cleanup_preview(\n"
        "    request: Request,\n"
        "    school_year_id: int | None = Query(default=None),\n"
        "    batch_id: int | None = Query(default=None),\n"
        "    cleanup_status: str = Query(default=\"\"),\n"
        "    backup_name: str = Query(default=\"\"),\n"
        "):"
    )

    new_sig = (
        "def survey_cleanup_preview(\n"
        "    request: Request,\n"
        "    school_year_id: str | None = Query(default=None),\n"
        "    batch_id: str | None = Query(default=None),\n"
        "    cleanup_status: str = Query(default=\"\"),\n"
        "    backup_name: str = Query(default=\"\"),\n"
        "):"
    )

    if old_sig not in text:
        raise RuntimeError(
            "Không tìm thấy đúng chữ ký route GET của V3.18B/B2."
        )

    text = text.replace(old_sig, new_sig, 1)

    old_body = (
        "    if not _admin_only(request):\n"
        "        return RedirectResponse(\n"
        "            url=\"/?status=forbidden\",\n"
        "            status_code=303,\n"
        "        )\n"
        "\n"
        "    context = _cleanup_page_context(\n"
        "        request,\n"
        "        school_year_id=school_year_id,\n"
        "        batch_id=batch_id,\n"
        "        cleanup_status=cleanup_status,\n"
        "        backup_name=backup_name,\n"
        "    )"
    )

    new_body = (
        "    if not _admin_only(request):\n"
        "        return RedirectResponse(\n"
        "            url=\"/?status=forbidden\",\n"
        "            status_code=303,\n"
        "        )\n"
        "\n"
        "    school_year_id_int = _safe_optional_int(school_year_id)\n"
        "    batch_id_int = _safe_optional_int(batch_id)\n"
        "\n"
        "    context = _cleanup_page_context(\n"
        "        request,\n"
        "        school_year_id=school_year_id_int,\n"
        "        batch_id=batch_id_int,\n"
        "        cleanup_status=cleanup_status,\n"
        "        backup_name=backup_name,\n"
        "    )"
    )

    if old_body not in text:
        raise RuntimeError(
            "Không tìm thấy thân route GET để gắn parse an toàn."
        )

    text = text.replace(old_body, new_body, 1)

    return text


def verify(text: str) -> None:
    required = [
        MARK,
        "import re",
        "def _safe_optional_int",
        "school_year_id: str | None",
        "batch_id: str | None",
        "school_year_id_int = _safe_optional_int(school_year_id)",
        "batch_id_int = _safe_optional_int(batch_id)",
        'CONFIRM_PHRASE = "XOA DU LIEU THU 2026-2027"',
        "def _execute_cleanup",
    ]

    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(
            "Kiểm tra sau cài chưa đạt, thiếu: "
            + " | ".join(missing)
        )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 104)
    print(
        "BÀI 13B-10 V3.18B3 - "
        "SỬA LỖI QUERY int_parsing Ở CÔNG CỤ DỌN DỮ LIỆU"
    )
    print("=" * 104)
    print()
    print("V3.18B3 chỉ sửa route GET xem/kiểm kê.")
    print("KHÔNG sửa database và KHÔNG chạy DELETE.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(f"Không tìm thấy: {ROUTER}")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        before = read_text(ROUTER)
        after = patch_router(before)
        ROUTER.write_text(after, encoding="utf-8")

        verify(read_text(ROUTER))
        clear_cache()

        print()
        print("CÀI ĐẶT BÀI 13B-10 V3.18B3 THÀNH CÔNG")
        print("Khởi động lại Uvicorn và Ctrl+F5.")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE V3.18B2...")
        restore_source()
        clear_cache()
        print("ĐÃ KHÔI PHỤC data_tools.py TRƯỚC V3.18B3.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
