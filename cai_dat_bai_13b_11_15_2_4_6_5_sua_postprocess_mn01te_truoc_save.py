from __future__ import annotations

import ast
import os
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"

ROUTER = APP / "routers" / "mn_official_reports.py"
SERVICE = APP / "services" / "mn_report_v246.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = (
    EXPORTS
    / f"backup_bai_13b_11_15_2_4_6_5_{STAMP}"
)

REPORT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_15_2_4_6_5_{STAMP}.txt"
)

OLD_START = (
    "# === BAI_13B_11_15_2_4_6_"
    "OFFICIAL_FILL ==="
)

NEW_START = (
    "# === BAI_13B_11_15_2_4_6_5_"
    "POSTPROCESS_BEFORE_SAVE_START ==="
)

NEW_END = (
    "# === BAI_13B_11_15_2_4_6_5_"
    "POSTPROCESS_BEFORE_SAVE_END ==="
)


def read_text(
    path: Path,
) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(
    path: Path,
    text: str,
) -> None:
    path.write_text(
        text,
        encoding="utf-8",
    )


def function_span(
    source: str,
    name: str,
) -> tuple[int, int]:
    tree = ast.parse(source)

    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name == name
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Cần đúng 1 hàm {name}; "
            f"tìm thấy {len(matches)}."
        )

    node = matches[0]
    lines = source.splitlines(
        keepends=True
    )

    offsets = [0]

    for line in lines:
        offsets.append(
            offsets[-1]
            + len(line)
        )

    return (
        offsets[int(node.lineno) - 1],
        offsets[int(node.end_lineno)],
    )


def get_function(
    source: str,
    name: str,
) -> str:
    start, end = function_span(
        source,
        name,
    )

    return source[start:end]


def replace_function(
    source: str,
    name: str,
    replacement: str,
) -> str:
    start, end = function_span(
        source,
        name,
    )

    result = (
        source[:start]
        + replacement.rstrip()
        + "\n\n"
        + source[end:].lstrip("\n")
    )

    ast.parse(result)
    return result


def db_state() -> dict:
    if not DB.exists():
        return {
            "exists": False,
        }

    conn = sqlite3.connect(
        str(DB)
    )

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_count = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        count = int(
            conn.execute(
                "SELECT COUNT(*) "
                "FROM survey_person_year_records"
            ).fetchone()[0]
        )

        schema = [
            str(row[1])
            for row in conn.execute(
                "PRAGMA table_info("
                "survey_person_year_records"
                ")"
            ).fetchall()
        ]

        return {
            "exists": True,
            "integrity": integrity,
            "fk_count": fk_count,
            "count": count,
            "schema": schema,
        }

    finally:
        conn.close()


def locate_dead_block(
    fn: str,
) -> tuple[int, int] | None:
    """
    Tìm khối Bài 4.6 đã bị chèn sau return.

    Khối bắt đầu bằng OLD_START và chạy đến
    apply_formula_contract(wb).
    """
    start = fn.find(OLD_START)

    if start < 0:
        return None

    line_start = (
        fn.rfind(
            "\n",
            0,
            start,
        )
        + 1
    )

    call = "    apply_formula_contract(wb)\n"

    end = fn.find(
        call,
        start,
    )

    if end < 0:
        raise RuntimeError(
            "Có marker Bài 4.6 nhưng không tìm thấy "
            "apply_formula_contract(wb)."
        )

    end += len(call)

    return (
        line_start,
        end,
    )


def build_live_block(
    dead_block: str,
) -> str:
    """
    Giữ nguyên nghiệp vụ đã cài ở Bài 4.6,
    chỉ đổi marker để xác nhận nó đã được chuyển
    sang vị trí chạy thật trước save/return.
    """
    body = dead_block

    # Bỏ marker cũ đầu block nếu có.
    lines = body.splitlines()

    if lines and OLD_START in lines[0]:
        lines = lines[1:]

    body = "\n".join(lines).strip("\n")

    return (
        "    "
        + NEW_START
        + "\n"
        + body
        + "\n"
        + "    "
        + NEW_END
        + "\n"
    )


def patch_router(
    source: str,
) -> tuple[str, list[str]]:
    notes: list[str] = []

    ast.parse(source)

    fn = get_function(
        source,
        "_fill_te_workbook",
    )

    save_anchor = (
        "    out = io.BytesIO()\n"
        "    wb.save(out)\n"
        "    return out.getvalue()\n"
    )

    if save_anchor not in fn:
        raise RuntimeError(
            "Không tìm thấy đúng cụm "
            "out = io.BytesIO() / wb.save(out) / return."
        )

    if NEW_START in fn:
        live_pos = fn.find(
            NEW_START
        )

        save_pos = fn.find(
            "    out = io.BytesIO()\n"
        )

        if (
            live_pos < 0
            or live_pos >= save_pos
        ):
            raise RuntimeError(
                "Marker 4.6.5 đã có nhưng không nằm "
                "trước wb.save(out)."
            )

        notes.append(
            "Khối post-processing 4.6.5 đã ở đúng "
            "trước save/return."
        )

        return (
            source,
            notes,
        )

    dead_span = locate_dead_block(
        fn
    )

    if dead_span is None:
        raise RuntimeError(
            "Không tìm thấy khối Bài 4.6 cần di chuyển. "
            "Dừng để không sửa nhầm phiên bản."
        )

    dead_start, dead_end = dead_span

    return_pos = fn.find(
        "    return out.getvalue()\n"
    )

    if return_pos < 0:
        raise RuntimeError(
            "Không tìm thấy return out.getvalue()."
        )

    if dead_start < return_pos:
        raise RuntimeError(
            "Khối Bài 4.6 hiện không nằm sau return; "
            "không áp dụng bản sửa này."
        )

    dead_block = fn[
        dead_start:dead_end
    ]

    live_block = build_live_block(
        dead_block
    )

    # 1. Xóa khối chết sau return.
    fn_without_dead = (
        fn[:dead_start]
        + fn[dead_end:]
    )

    # 2. Chèn nguyên nội dung đó trước khi serialize/save.
    if save_anchor not in fn_without_dead:
        raise RuntimeError(
            "Sau khi bỏ khối chết không còn save anchor."
        )

    fn_fixed = fn_without_dead.replace(
        save_anchor,
        live_block
        + "\n"
        + save_anchor,
        1,
    )

    # Verifier thứ tự.
    pos_live = fn_fixed.find(
        NEW_START
    )

    pos_apply = fn_fixed.find(
        "apply_formula_contract(wb)"
    )

    pos_save = fn_fixed.find(
        "wb.save(out)"
    )

    pos_return = fn_fixed.find(
        "return out.getvalue()"
    )

    if not (
        0 <= pos_live
        < pos_apply
        < pos_save
        < pos_return
    ):
        raise RuntimeError(
            "Thứ tự thực thi sau patch không đúng: "
            "postprocess -> save -> return."
        )

    source = replace_function(
        source,
        "_fill_te_workbook",
        fn_fixed,
    )

    notes.append(
        "Đã chuyển khối Bài 4.6 từ sau return "
        "lên trước wb.save(out)."
    )

    notes.append(
        "apply_formula_contract(wb) giờ được chạy thật "
        "trước khi file Excel được tạo bytes."
    )

    return (
        source,
        notes,
    )


def verify(
    source: str,
) -> None:
    ast.parse(source)

    fn = get_function(
        source,
        "_fill_te_workbook",
    )

    required = (
        NEW_START,
        NEW_END,
        "apply_formula_contract(wb)",
        "wb.save(out)",
        "return out.getvalue()",
    )

    for token in required:
        if token not in fn:
            raise RuntimeError(
                "Verifier thiếu: "
                + token
            )

    if OLD_START in fn:
        raise RuntimeError(
            "Vẫn còn marker khối chết Bài 4.6 "
            "trong _fill_te_workbook."
        )

    positions = {
        "start": fn.find(
            NEW_START
        ),
        "apply": fn.find(
            "apply_formula_contract(wb)"
        ),
        "save": fn.find(
            "wb.save(out)"
        ),
        "return": fn.find(
            "return out.getvalue()"
        ),
    }

    if not (
        positions["start"]
        < positions["apply"]
        < positions["save"]
        < positions["return"]
    ):
        raise RuntimeError(
            "Verifier thứ tự thất bại: "
            + str(positions)
        )


def main() -> None:
    print("=" * 142)
    print(
        "BÀI 13B-11.15.2.4.6.5 - "
        "SỬA VỊ TRÍ POST-PROCESSING MN-01-TE "
        "TRƯỚC SAVE/RETURN"
    )
    print("=" * 142)
    print()

    print("NGUYÊN NHÂN ĐÃ XÁC ĐỊNH:")
    print(
        " - Khối Bài 4.6 của MN-01-TE bị chèn "
        "sau `return out.getvalue()`."
    )
    print(
        " - Vì vậy apply_formula_contract(wb) "
        "không bao giờ chạy."
    )
    print(
        " - Các bài 4.6.1 -> 4.6.4 sửa đúng helper "
        "nhưng helper không được gọi ở MN-01-TE."
    )
    print()

    print("SẼ SỬA:")
    print(
        " - Giữ nguyên toàn bộ nghiệp vụ đã cài."
    )
    print(
        " - Chỉ chuyển post-processing lên trước "
        "`wb.save(out)`."
    )
    print(
        " - Thứ tự mới: điền dữ liệu -> công thức/format "
        "-> save -> return."
    )
    print()

    print("KHÔNG LÀM:")
    print(
        " - Không sửa database."
    )
    print(
        " - Không đổi công thức tính."
    )
    print(
        " - Không đổi template Excel."
    )
    print(
        " - Không đổi menu/route."
    )
    print()

    for path in (
        ROUTER,
        SERVICE,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    router_old = read_text(
        ROUTER
    )

    service_text = read_text(
        SERVICE
    )

    ast.parse(
        router_old
    )

    ast.parse(
        service_text
    )

    # Bắt buộc đã có các bài định dạng trước.
    for token in (
        "def apply_formula_contract(",
        "def _v2461_percent_format(",
        "cell.number_format = r'0\\%'",
        "def _v2464_format_percent_table_by_header(",
    ):
        if token not in service_text:
            raise RuntimeError(
                "Service Mầm non chưa đủ nền 4.6.1-4.6.4. "
                "Thiếu: "
                + token
            )

    router_new, notes = patch_router(
        router_old
    )

    verify(
        router_new
    )

    before = db_state()

    if before.get(
        "exists"
    ):
        if (
            before.get(
                "integrity"
            )
            != "ok"
        ):
            raise RuntimeError(
                "Database integrity_check != ok."
            )

        if (
            before.get(
                "fk_count"
            )
            != 0
        ):
            raise RuntimeError(
                "Database đang có lỗi foreign key."
            )

    # Chỉ backup sau khi preflight hoàn tất.
    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    shutil.copy2(
        ROUTER,
        BACKUP / ROUTER.name,
    )

    shutil.copy2(
        SERVICE,
        BACKUP / SERVICE.name,
    )

    try:
        if router_new != router_old:
            write_text(
                ROUTER,
                router_new,
            )

        py_compile.compile(
            str(ROUTER),
            doraise=True,
        )

        py_compile.compile(
            str(SERVICE),
            doraise=True,
        )

        installed = read_text(
            ROUTER
        )

        verify(
            installed
        )

        after = db_state()

        if before != after:
            raise RuntimeError(
                "Database/schema/count thay đổi "
                "ngoài dự kiến."
            )

        for cache in APP.rglob(
            "__pycache__"
        ):
            if cache.is_dir():
                shutil.rmtree(
                    cache,
                    ignore_errors=True,
                )

    except Exception:
        shutil.copy2(
            BACKUP / ROUTER.name,
            ROUTER,
        )

        for cache in APP.rglob(
            "__pycache__"
        ):
            if cache.is_dir():
                shutil.rmtree(
                    cache,
                    ignore_errors=True,
                )

        raise

    lines = [
        "=" * 142,
        "BÀI 13B-11.15.2.4.6.5 - KẾT QUẢ",
        "=" * 142,
        "",
        "NGUYÊN NHÂN:",
        " - Post-processing MN-01-TE nằm sau return nên không chạy.",
        "",
        "ĐÃ SỬA:",
    ]

    for note in notes:
        lines.append(
            " - " + note
        )

    lines.extend(
        (
            "",
            "THỨ TỰ SAU SỬA:",
            " - Điền số liệu.",
            " - Điền nguồn khuyết tật.",
            " - apply_formula_contract(wb).",
            " - Định dạng tỷ lệ 100% / 0% / 50%.",
            " - wb.save(out).",
            " - return out.getvalue().",
            "",
            "AN TOÀN:",
            " - Database không thay đổi.",
            " - Công thức nghiệp vụ không thay đổi.",
            " - Template không thay đổi.",
            " - Menu/route không thay đổi.",
            f" - Backup: {BACKUP}",
            "",
        )
    )

    REPORT.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )

    print("KIỂM TRA:")
    print(
        " - AST: OK"
    )
    print(
        " - py_compile router/service: OK"
    )
    print(
        " - Thứ tự postprocess < save < return: OK"
    )
    print(
        " - Database invariant: OK"
    )
    print()
    print(
        "Backup:",
        BACKUP,
    )
    print(
        "Báo cáo:",
        REPORT,
    )
    print()
    print("=" * 142)
    print(
        "BÀI 13B-11.15.2.4.6.5 THÀNH CÔNG"
    )
    print("=" * 142)


if __name__ == "__main__":
    main()
