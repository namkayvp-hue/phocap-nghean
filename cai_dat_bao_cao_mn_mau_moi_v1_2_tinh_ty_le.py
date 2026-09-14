from __future__ import annotations

import ast
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
ROUTER = APP / "routers" / "mn_official_reports.py"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_bao_cao_mn_ty_le_v1_2_{STAMP}"
)

MARKER = "BAO_CAO_MN_MAU_MOI_V1_2_TINH_TY_LE"
FIELD = "attends_two_sessions_per_day"


def read_text(path: Path) -> str:
    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_file(path: Path) -> None:
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore_file(path: Path) -> None:
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def db_check() -> tuple[str, int, set[str]]:
    if not DB.exists():
        raise RuntimeError(f"Không tìm thấy database: {DB}")

    conn = sqlite3.connect(DB)
    try:
        integrity = str(
            conn.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk = len(
            conn.execute("PRAGMA foreign_key_check").fetchall()
        )
        columns = {
            str(row[1])
            for row in conn.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }
        return integrity, fk, columns
    finally:
        conn.close()


def find_function_span(
    source: str,
    function_name: str,
) -> tuple[int, int]:
    tree = ast.parse(source)
    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name == function_name
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm {function_name}; "
            f"hiện có {len(matches)}."
        )

    node = matches[0]
    lines = source.splitlines(keepends=True)

    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    start = starts[node.lineno - 1]
    end = starts[node.end_lineno]
    return start, end


def get_function(
    source: str,
    function_name: str,
) -> str:
    start, end = find_function_span(
        source,
        function_name,
    )
    return source[start:end]


def replace_function(
    source: str,
    function_name: str,
    new_block: str,
) -> str:
    start, end = find_function_span(
        source,
        function_name,
    )
    return (
        source[:start]
        + new_block.rstrip()
        + "\n\n"
        + source[end:].lstrip("\n")
    )


def patch_query_function(block: str) -> str:
    if FIELD in block:
        return block

    anchor = "            spr.completed_preschool_5,\n"

    if anchor not in block:
        raise RuntimeError(
            "Không tìm thấy dòng spr.completed_preschool_5 "
            "trong _query_te_people."
        )

    return block.replace(
        anchor,
        anchor
        + f"            spr.{FIELD},\n",
        1,
    )


def patch_metrics_function(block: str) -> str:
    if '"two_sessions"' not in block:
        anchor = (
            '        "moved_out", "moved_in", "completed5",\n'
        )

        if anchor not in block:
            raise RuntimeError(
                "Không tìm thấy metric_names chuẩn trong _te_metrics."
            )

        block = block.replace(
            anchor,
            '        "moved_out", "moved_in", '
            '"completed5", "two_sessions",\n',
            1,
        )

    logic = (
        f'        if attending and '
        f'_as_bool(row.get("{FIELD}")) is True:\n'
        f'            metrics["two_sessions"][age] += 1\n\n'
    )

    if logic not in block:
        anchor = (
            '        if _as_bool(row.get("completed_preschool_5")) '
            'is True:\n'
        )

        if anchor not in block:
            raise RuntimeError(
                "Không tìm thấy vị trí chèn two_sessions "
                "trong _te_metrics."
            )

        block = block.replace(
            anchor,
            logic + anchor,
            1,
        )

    return block


def patch_fill_function(block: str) -> str:
    if MARKER in block:
        return block

    anchor = "    out = io.BytesIO()\n"

    if anchor not in block:
        raise RuntimeError(
            "Không tìm thấy vị trí ghi workbook "
            "trong _fill_te_workbook."
        )

    addition = r'''
    # === BAO_CAO_MN_MAU_MOI_V1_2_TINH_TY_LE START ===
    # 1) Học 2 buổi/ngày: đã có dữ liệu cấu trúc trong hồ sơ năm học.
    two_sessions = metrics.get("two_sessions", {})
    for age, col in age_cols.items():
        ws[f"{col}21"] = int(two_sessions.get(age, 0) or 0)
    ws["M21"] = _sum_0_5(two_sessions)

    # 2) Các hàng tỷ lệ của bảng chính.
    # Hàng 16 dùng kiểu tỷ lệ thập phân vì mẫu Excel gốc
    # đã định dạng hàng này theo dạng phần trăm.
    for col in ("F", "G", "H", "I", "J", "K", "L"):
        ws[f"{col}16"] = (
            f'=IFERROR(IF({col}12="","",{col}13/{col}12),"")'
        )
        ws[f"{col}22"] = (
            f'=IFERROR(IF({col}13="","",{col}21/{col}13*100),"")'
        )

    ws["M16"] = '=IFERROR(IF(M12="","",M13/M12),"")'
    ws["M22"] = '=IFERROR(IF(M13="","",M21/M13*100),"")'

    # Hoàn thành CT GDMN chỉ áp dụng các cột có số liệu,
    # không ghi đè các ô "x" của mẫu.
    for col in ("J", "K", "L"):
        ws[f"{col}28"] = (
            f'=IFERROR(IF({col}26="","",{col}27/{col}26*100),"")'
        )
    ws["M28"] = '=IFERROR(IF(M26="","",M27/M26*100),"")'

    # 3) Bảng TIÊU CHÍ phía dưới.
    # 5 tuổi đến trường.
    ws["E35"] = "=K13"
    ws["F35"] = '=IFERROR(IF(K12="","",E35/K12*100),"")'

    # 5 tuổi khuyết tật được tiếp cận giáo dục.
    # Khi hàng 9/11 chưa có dữ liệu cấu trúc, tỷ lệ tự để trống.
    ws["E36"] = '=IF(K11="","",K11)'
    ws["F36"] = '=IFERROR(IF(K9="","",E36/K9*100),"")'

    # 5 tuổi học 2 buổi/ngày.
    ws["E37"] = "=K21"
    ws["F37"] = '=IFERROR(IF(K13="","",E37/K13*100),"")'

    # 5 tuổi hoàn thành CT GDMN theo độ tuổi.
    ws["E38"] = '=IF(K27="","",K27)'
    ws["F38"] = '=IFERROR(IF(K26="","",E38/K26*100),"")'

    # Trẻ 3,4 tuổi đến trường.
    ws["E40"] = "=SUM(I13:J13)"
    ws["F40"] = (
        '=IFERROR(IF(SUM(I12:J12)=0,"",'
        'E40/SUM(I12:J12)*100),"")'
    )

    # Trẻ 3,4 tuổi học 2 buổi/ngày.
    ws["E41"] = "=SUM(I21:J21)"
    ws["F41"] = (
        '=IFERROR(IF(SUM(I13:J13)=0,"",'
        'E41/SUM(I13:J13)*100),"")'
    )

    # Trẻ 3,4 tuổi hoàn thành CT GDMN theo độ tuổi.
    # SUM bỏ qua các ô "x" của mẫu và chỉ cộng ô số.
    ws["E42"] = "=SUM(I27:J27)"
    ws["F42"] = (
        '=IFERROR(IF(SUM(I26:J26)=0,"",'
        'E42/SUM(I26:J26)*100),"")'
    )

    # Yêu cầu Excel tự tính công thức khi mở file.
    try:
        wb.calculation.calcMode = "auto"
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
    except Exception:
        pass
    # === BAO_CAO_MN_MAU_MOI_V1_2_TINH_TY_LE END ===

'''

    return block.replace(
        anchor,
        addition + anchor,
        1,
    )


def patch_warning(source: str) -> str:
    old = (
        "Hiện CSDL điều tra chưa có trường cấu trúc đủ chắc chắn cho: "
        "khuyết tật/có khả năng học tập/tiếp cận giáo dục; "
        "số phải huy động; học 2 buổi/ngày; tử vong; "
        "một số chỉ tiêu hoàn thành chương trình 3–4 tuổi. "
        "Các ô này được giữ trống, không tự suy đoán thành 0."
    )

    new = (
        "Hệ thống đã có dữ liệu cấu trúc cho học 2 buổi/ngày. "
        "Các chỉ tiêu còn chưa đủ nguồn chắc chắn như "
        "khả năng học tập/tiếp cận giáo dục của trẻ khuyết tật, "
        "số phải huy động, tử vong và dữ liệu làm căn cứ hoàn thành "
        "chương trình theo năm trước vẫn được giữ trống, "
        "không tự suy đoán thành 0."
    )

    if old in source:
        source = source.replace(old, new, 1)

    return source


def patch_source(source: str) -> str:
    if MARKER in source:
        print(
            " - V1.2 đã có trong source; "
            "không chèn lặp."
        )
        return source

    required = (
        "def _query_te_people(",
        "def _te_metrics(",
        "def _fill_te_workbook(",
        'wb["Thống kê trẻ em từ 0 đến 5 tuổi"]',
    )

    for item in required:
        if item not in source:
            raise RuntimeError(
                "mn_official_reports.py không đúng nền dự kiến. "
                f"Thiếu: {item}"
            )

    query = get_function(
        source,
        "_query_te_people",
    )
    query = patch_query_function(query)
    source = replace_function(
        source,
        "_query_te_people",
        query,
    )

    metrics = get_function(
        source,
        "_te_metrics",
    )
    metrics = patch_metrics_function(metrics)
    source = replace_function(
        source,
        "_te_metrics",
        metrics,
    )

    fill = get_function(
        source,
        "_fill_te_workbook",
    )
    fill = patch_fill_function(fill)
    source = replace_function(
        source,
        "_fill_te_workbook",
        fill,
    )

    source = patch_warning(source)

    ast.parse(source)
    return source


def verify_source(source: str) -> None:
    ast.parse(source)

    checks = (
        MARKER,
        f"spr.{FIELD}",
        '"two_sessions"',
        'ws["M22"]',
        'ws["F35"]',
        'ws["F37"]',
        'ws["F38"]',
        'ws["F40"]',
        'ws["F41"]',
        'ws["F42"]',
        'ws[f"{col}16"]',
        'ws[f"{col}22"]',
        'ws[f"{col}28"]',
    )

    for item in checks:
        if item not in source:
            raise RuntimeError(
                f"Kiểm tra source sau cài thiếu: {item}"
            )


def main() -> int:
    print("=" * 116)
    print(
        "BÁO CÁO MẦM NON MẪU MỚI V1.2 - "
        "TÍNH CÁC TỶ LỆ TRONG MN-01-TE"
    )
    print("=" * 116)
    print()
    print("SỬA:")
    print(" - Điền số trẻ học 2 buổi/ngày từ dữ liệu năm học.")
    print(" - Tự tính Tỉ lệ huy động khi có Số trẻ phải huy động.")
    print(" - Tự tính Tỉ lệ trẻ học 2 buổi/ngày.")
    print(" - Tự tính Tỉ lệ hoàn thành Chương trình GDMN.")
    print(" - Tự tính các tỷ lệ trong bảng Tiêu chí cuối biểu.")
    print()
    print("NGUYÊN TẮC:")
    print(" - Không suy đoán mẫu số chưa có dữ liệu.")
    print(" - Mẫu số trống/0 thì tỷ lệ để trống, không ghi 0 giả.")
    print(" - Không sửa mẫu Excel gốc.")
    print(" - Không sửa database.")
    print()

    if not ROUTER.exists():
        raise RuntimeError(
            f"Không tìm thấy: {ROUTER}"
        )

    integrity, fk_count, columns = db_check()

    print(f"integrity_check trước cài: {integrity}")
    print(f"foreign_key_check trước cài: {fk_count} lỗi")

    if integrity.lower() != "ok" or fk_count != 0:
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn trước cài."
        )

    if FIELD not in columns:
        raise RuntimeError(
            "Database chưa có trường "
            f"'{FIELD}'. "
            "Hãy chạy Bài 13B-11.13.3.5 "
            "bổ sung Học 2 buổi/ngày trước."
        )

    original = read_text(ROUTER)

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )
    backup_file(ROUTER)

    print(f"Backup source: {BACKUP}")

    try:
        patched = patch_source(original)
        verify_source(patched)

        write_text(ROUTER, patched)

        subprocess.run(
            [
                sys.executable,
                "-m",
                "py_compile",
                str(ROUTER),
            ],
            cwd=PROJECT,
            check=True,
        )

        verify_source(read_text(ROUTER))
        clear_cache()

        integrity_after, fk_after, _ = db_check()

        if (
            integrity_after.lower() != "ok"
            or fk_after != 0
        ):
            raise RuntimeError(
                "Database không đạt kiểm tra sau cài."
            )

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Python compile: ĐẠT")
        print(" - Học 2 buổi/ngày vào query báo cáo: ĐẠT")
        print(" - Metric two_sessions: ĐẠT")
        print(" - Công thức tỷ lệ bảng chính: ĐẠT")
        print(" - Công thức tỷ lệ bảng Tiêu chí: ĐẠT")
        print(" - Database: KHÔNG THAY ĐỔI")
        print(" - Mẫu Excel: KHÔNG THAY ĐỔI")
        print(f" - integrity_check: {integrity_after}")
        print(f" - foreign_key_check: {fk_after} lỗi")
        print()
        print("=" * 116)
        print(
            "CÀI ĐẶT BÁO CÁO MẦM NON V1.2 THÀNH CÔNG"
        )
        print("=" * 116)
        print(f"Backup: {BACKUP}")
        print()
        print("SAU KHI CÀI:")
        print(" 1. Khởi động lại Uvicorn.")
        print(" 2. Ctrl+F5 trình duyệt.")
        print(" 3. Xuất lại MN-01-TE.")
        print(
            " 4. Các tỷ lệ có đủ tử số/mẫu số "
            "sẽ tự tính."
        )
        print(
            " 5. Tỷ lệ cần 'Số trẻ phải huy động' "
            "hoặc dữ liệu khuyết tật còn thiếu "
            "sẽ tiếp tục để trống cho đến khi "
            "bổ sung nguồn dữ liệu."
        )

        return 0

    except Exception:
        traceback.print_exc()
        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC SOURCE..."
        )
        restore_file(ROUTER)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print(f"Backup: {BACKUP}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
