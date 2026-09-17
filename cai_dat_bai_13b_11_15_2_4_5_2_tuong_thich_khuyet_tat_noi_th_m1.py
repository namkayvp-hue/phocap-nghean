from __future__ import annotations

import ast
import os
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
EXPORTS = PROJECT / "exports"
DB = PROJECT / "data" / "phocap.db"

BUILDERS = APP / "pcgd_xmc_report_builders_v1.py"
REPORT_CENTER = APP / "routers" / "report_center.py"
RULES = APP / "services" / "pcgd_business_rules.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = (
    EXPORTS
    / f"backup_bai_13b_11_15_2_4_5_2_{STAMP}"
)
REPORT_FILE = (
    EXPORTS
    / f"bao_cao_bai_13b_11_15_2_4_5_2_{STAMP}.txt"
)

MARKER_BUILDERS_V51 = (
    "# === BAI_13B_11_15_2_4_5_1_"
    "DISABLED_CAPABLE_AND_M2_CLEANUP ==="
)

MARKER_BUILDERS_V52 = (
    "# === BAI_13B_11_15_2_4_5_2_"
    "DISABILITY_LEGACY_COMPAT ==="
)

MARKER_TH_M1_V52 = (
    "# === BAI_13B_11_15_2_4_5_2_"
    "TH_M1_DISABILITY_COMPAT_START ==="
)

TH_M1_PERCENT_CALL = (
    "    _b15245_apply_primary_th_m1_percentages(ws)\n"
)

NEW_BUILDERS_CAN_LEARN = 'def _b152451_disabled_can_learn(\n    person: SurveyPerson,\n    record: SurveyPersonYearRecord | None,\n) -> bool:\n    """\n    Bài 13B-11.15.2.4.5.2 - tương thích dữ liệu cũ.\n\n    Thứ tự ưu tiên:\n    1. disability_can_learn = True  -> Có khả năng học.\n    2. disability_can_learn = False -> Không có khả năng học.\n       Giá trị False tường minh luôn được giữ nguyên.\n    3. disability_can_learn = None và\n       disability_access_education = True\n       -> suy ra Có khả năng học CHỈ KHI LẬP BÁO CÁO.\n\n    Không ghi giá trị suy ra trở lại database.\n    """\n    if (\n        not _is_disabled(person, record)\n        or record is None\n    ):\n        return False\n\n    explicit = getattr(\n        record,\n        "disability_can_learn",\n        None,\n    )\n\n    if explicit is True:\n        return True\n\n    if explicit is False:\n        return False\n\n    return (\n        getattr(\n            record,\n            "disability_access_education",\n            None,\n        )\n        is True\n    )\n'

TH_M1_HELPERS = '\n# === BAI_13B_11_15_2_4_5_2_TH_M1_DISABILITY_COMPAT_START ===\ndef _b152452_th_m1_can_learn(\n    person,\n    record,\n) -> bool:\n    """\n    Tương thích dữ liệu khuyết tật cũ cho TH_M1.\n\n    Không sửa DB:\n    - True  -> Có khả năng học.\n    - False -> Không có khả năng học.\n    - None + access=True -> suy ra Có chỉ trong báo cáo.\n    """\n    if (\n        not _th_m1_is_disabled(\n            person,\n            record,\n        )\n        or record is None\n    ):\n        return False\n\n    explicit = getattr(\n        record,\n        "disability_can_learn",\n        None,\n    )\n\n    if explicit is True:\n        return True\n\n    if explicit is False:\n        return False\n\n    return (\n        getattr(\n            record,\n            "disability_access_education",\n            None,\n        )\n        is True\n    )\n\n\ndef _b152452_th_m1_access(\n    person,\n    record,\n) -> bool:\n    return bool(\n        _b152452_th_m1_can_learn(\n            person,\n            record,\n        )\n        and record is not None\n        and getattr(\n            record,\n            "disability_access_education",\n            None,\n        )\n        is True\n    )\n\n\ndef _b152452_apply_th_m1_disability(\n    ws,\n    people,\n    reference_year: int,\n) -> None:\n    """\n    Điền đúng các dòng khuyết tật của TH_M1:\n    - Dòng 10: Có khả năng học tập.\n    - Dòng 11: Được tiếp cận giáo dục.\n    - F44: số trẻ KT có khả năng HT được tiếp cận GD.\n\n    G44 được helper Bài 15.2.4.5 tính tiếp theo công thức:\n        G44 = F44 / (K10 + P10) * 100\n    """\n\n    age_columns = {\n        6: "F",\n        7: "G",\n        8: "H",\n        9: "I",\n        10: "J",\n        11: "L",\n        12: "M",\n        13: "N",\n        14: "O",\n    }\n\n    capable_by_age = {\n        age: 0\n        for age in age_columns\n    }\n\n    access_by_age = {\n        age: 0\n        for age in age_columns\n    }\n\n    for person, record in people:\n        birth = getattr(\n            person,\n            "date_of_birth",\n            None,\n        )\n\n        birth_year = getattr(\n            birth,\n            "year",\n            None,\n        )\n\n        if birth_year is None:\n            continue\n\n        try:\n            age = int(reference_year) - int(birth_year)\n        except (TypeError, ValueError):\n            continue\n\n        if age not in age_columns:\n            continue\n\n        if _b152452_th_m1_can_learn(\n            person,\n            record,\n        ):\n            capable_by_age[age] += 1\n\n            if _b152452_th_m1_access(\n                person,\n                record,\n            ):\n                access_by_age[age] += 1\n\n    for age, column in age_columns.items():\n        capable = capable_by_age[age]\n        access = access_by_age[age]\n\n        ws[f"{column}10"] = (\n            capable\n            if capable > 0\n            else None\n        )\n\n        ws[f"{column}11"] = (\n            access\n            if capable > 0\n            else None\n        )\n\n    capable_6_10 = sum(\n        capable_by_age[age]\n        for age in range(6, 11)\n    )\n\n    access_6_10 = sum(\n        access_by_age[age]\n        for age in range(6, 11)\n    )\n\n    capable_11_14 = sum(\n        capable_by_age[age]\n        for age in range(11, 15)\n    )\n\n    access_11_14 = sum(\n        access_by_age[age]\n        for age in range(11, 15)\n    )\n\n    ws["K10"] = (\n        capable_6_10\n        if capable_6_10 > 0\n        else None\n    )\n\n    ws["K11"] = (\n        access_6_10\n        if capable_6_10 > 0\n        else None\n    )\n\n    ws["P10"] = (\n        capable_11_14\n        if capable_11_14 > 0\n        else None\n    )\n\n    ws["P11"] = (\n        access_11_14\n        if capable_11_14 > 0\n        else None\n    )\n\n    capable_total = (\n        capable_6_10\n        + capable_11_14\n    )\n\n    access_total = (\n        access_6_10\n        + access_11_14\n    )\n\n    # F44 là tử số. Nếu có mẫu số nhưng access=0,\n    # phải ghi 0 để G44 ra 0%, không được để trống.\n    ws["F44"] = (\n        access_total\n        if capable_total > 0\n        else None\n    )\n# === BAI_13B_11_15_2_4_5_2_TH_M1_DISABILITY_COMPAT_END ===\n\n\n'


def read_text(path: Path) -> str:
    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(path: Path, text: str) -> None:
    path.write_text(
        text,
        encoding="utf-8",
    )


def function_node(source: str, name: str):
    tree = ast.parse(source)
    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name == name
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm {name}; "
            f"hiện có {len(matches)}."
        )

    return matches[0]


def function_span(
    source: str,
    name: str,
) -> tuple[int, int]:
    node = function_node(source, name)
    lines = source.splitlines(keepends=True)
    offsets = [0]

    for line in lines:
        offsets.append(
            offsets[-1] + len(line)
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
    new_function: str,
) -> str:
    start, end = function_span(
        source,
        name,
    )

    patched = (
        source[:start]
        + new_function.rstrip()
        + "\n\n"
        + source[end:].lstrip("\n")
    )

    ast.parse(patched)
    return patched


def call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id

    if isinstance(node.func, ast.Attribute):
        return node.func.attr

    return ""


def source_segment(
    source: str,
    node: ast.AST,
) -> str:
    return (
        ast.get_source_segment(
            source,
            node,
        )
        or ""
    ).strip()


def find_th_m1_metrics_args(
    source: str,
) -> tuple[str, str]:
    """
    Lấy chính đối số đang truyền vào _th_m1_build_metrics(...),
    không đoán tên biến people trong source hiện tại.
    """
    fn = function_node(
        source,
        "_build_primary_th_m1_workbook",
    )

    calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and call_name(node) == "_th_m1_build_metrics"
    ]

    if len(calls) != 1:
        raise RuntimeError(
            "Trong _build_primary_th_m1_workbook "
            "phải có đúng 1 lời gọi _th_m1_build_metrics; "
            f"hiện có {len(calls)}."
        )

    call = calls[0]
    people_expr = ""
    year_expr = ""

    if call.args:
        people_expr = source_segment(
            source,
            call.args[0],
        )

    if len(call.args) >= 2:
        year_expr = source_segment(
            source,
            call.args[1],
        )

    keyword_map = {
        item.arg: item.value
        for item in call.keywords
        if item.arg
    }

    if not people_expr:
        for key in (
            "people",
            "pairs",
            "rows",
            "items",
        ):
            if key in keyword_map:
                people_expr = source_segment(
                    source,
                    keyword_map[key],
                )
                break

    if not year_expr:
        for key in (
            "reference_year",
            "year",
        ):
            if key in keyword_map:
                year_expr = source_segment(
                    source,
                    keyword_map[key],
                )
                break

    if (
        not year_expr
        and "reference_year" in get_function(
            source,
            "_build_primary_th_m1_workbook",
        )
    ):
        year_expr = "reference_year"

    if not people_expr:
        raise RuntimeError(
            "Không xác định được danh sách đối tượng "
            "dùng bởi _th_m1_build_metrics."
        )

    if not year_expr:
        raise RuntimeError(
            "Không xác định được năm tham chiếu "
            "dùng bởi _th_m1_build_metrics."
        )

    return people_expr, year_expr


def patch_builders(
    source: str,
) -> tuple[str, list[str]]:
    notes = []

    if MARKER_BUILDERS_V51 not in source:
        raise RuntimeError(
            "Chưa thấy nền Bài 15.2.4.5.1 "
            "trong pcgd_xmc_report_builders_v1.py."
        )

    old_function = get_function(
        source,
        "_b152451_disabled_can_learn",
    )

    if (
        "if explicit is False"
        in old_function
        and "disability_access_education"
        in old_function
    ):
        notes.append(
            "Helper tương thích dữ liệu cũ đã có."
        )
    else:
        source = replace_function(
            source,
            "_b152451_disabled_can_learn",
            NEW_BUILDERS_CAN_LEARN,
        )
        notes.append(
            "Đã nâng helper Có khả năng HT "
            "sang chế độ tương thích dữ liệu cũ."
        )

    if MARKER_BUILDERS_V52 not in source:
        target = get_function(
            source,
            "_b152451_disabled_access",
        )
        pos = source.find(target)

        if pos < 0:
            raise RuntimeError(
                "Không xác định được vị trí "
                "để ghi marker V5.2."
            )

        source = (
            source[:pos]
            + MARKER_BUILDERS_V52
            + "\n"
            + source[pos:]
        )

    ast.parse(source)
    return source, notes


def patch_report_center(
    source: str,
) -> tuple[str, list[str]]:
    notes = []

    function_node(
        source,
        "_th_m1_is_disabled",
    )

    function_node(
        source,
        "_build_primary_th_m1_workbook",
    )

    if (
        "_b15245_apply_primary_th_m1_percentages"
        not in source
    ):
        raise RuntimeError(
            "Chưa thấy helper tỷ lệ TH_M1 "
            "của Bài 15.2.4.5."
        )

    people_expr, year_expr = find_th_m1_metrics_args(
        source
    )

    if MARKER_TH_M1_V52 not in source:
        anchor = "def _build_primary_th_m1_workbook("

        if source.count(anchor) != 1:
            raise RuntimeError(
                "Không tìm thấy đúng 1 vị trí "
                "def _build_primary_th_m1_workbook("
            )

        source = source.replace(
            anchor,
            TH_M1_HELPERS + anchor,
            1,
        )
        notes.append(
            "Đã thêm helper khuyết tật tương thích cho TH_M1."
        )
    else:
        notes.append(
            "Helper TH_M1 V5.2 đã tồn tại."
        )

    fn = get_function(
        source,
        "_build_primary_th_m1_workbook",
    )

    compatibility_call = (
        "    _b152452_apply_th_m1_disability(\n"
        "        ws,\n"
        f"        {people_expr},\n"
        f"        {year_expr},\n"
        "    )\n"
    )

    if (
        "_b152452_apply_th_m1_disability("
        not in fn
    ):
        if fn.count(TH_M1_PERCENT_CALL) != 1:
            raise RuntimeError(
                "Builder TH_M1 cần đúng 1 lời gọi "
                "_b15245_apply_primary_th_m1_percentages(ws)."
            )

        fn = fn.replace(
            TH_M1_PERCENT_CALL,
            compatibility_call
            + TH_M1_PERCENT_CALL,
            1,
        )

        source = replace_function(
            source,
            "_build_primary_th_m1_workbook",
            fn,
        )

        notes.append(
            "Đã nối dòng 10/11 + F44 "
            "trước khi tính G44."
        )
    else:
        notes.append(
            "Lời gọi TH_M1 V5.2 đã tồn tại."
        )

    ast.parse(source)
    return source, notes


def db_state() -> dict:
    if not DB.exists():
        return {"exists": False}

    conn = sqlite3.connect(str(DB))

    try:
        columns = [
            str(row[1])
            for row in conn.execute(
                "PRAGMA table_info("
                "survey_person_year_records"
                ")"
            ).fetchall()
        ]

        count = int(
            conn.execute(
                "SELECT COUNT(*) "
                "FROM survey_person_year_records"
            ).fetchone()[0]
        )

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

        legacy = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM survey_person_year_records
                WHERE disability_can_learn IS NULL
                  AND disability_access_education = 1
                """
            ).fetchone()[0]
        )

        false_access = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM survey_person_year_records
                WHERE disability_can_learn = 0
                  AND disability_access_education = 1
                """
            ).fetchone()[0]
        )

        explicit_true = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM survey_person_year_records
                WHERE disability_can_learn = 1
                """
            ).fetchone()[0]
        )

        return {
            "exists": True,
            "columns": columns,
            "count": count,
            "integrity": integrity,
            "fk_count": fk_count,
            "legacy": legacy,
            "false_access": false_access,
            "explicit_true": explicit_true,
        }

    finally:
        conn.close()


def backup_database() -> None:
    if not DB.exists():
        return

    source = sqlite3.connect(str(DB))
    target = sqlite3.connect(
        str(BACKUP_DIR / "phocap.db")
    )

    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def restore_source() -> None:
    for name, target in (
        (
            "pcgd_xmc_report_builders_v1.py",
            BUILDERS,
        ),
        (
            "report_center.py",
            REPORT_CENTER,
        ),
    ):
        backup = BACKUP_DIR / name
        if backup.exists():
            shutil.copy2(
                backup,
                target,
            )


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def verify_source(
    builders: str,
    report_center: str,
) -> None:
    for token in (
        "def _b152451_disabled_can_learn(",
        "if explicit is False:",
        '"disability_access_education"',
        MARKER_BUILDERS_V52,
        "def _b152451_disabled_access(",
    ):
        if token not in builders:
            raise RuntimeError(
                "Verifier builders thiếu: "
                + token
            )

    for token in (
        MARKER_TH_M1_V52,
        "def _b152452_th_m1_can_learn(",
        "def _b152452_th_m1_access(",
        "def _b152452_apply_th_m1_disability(",
        'ws["K10"]',
        'ws["P10"]',
        'ws["F44"]',
        "_b152452_apply_th_m1_disability(",
        "_b15245_apply_primary_th_m1_percentages(ws)",
    ):
        if token not in report_center:
            raise RuntimeError(
                "Verifier report_center thiếu: "
                + token
            )

    fn = get_function(
        report_center,
        "_build_primary_th_m1_workbook",
    )

    compat_pos = fn.find(
        "_b152452_apply_th_m1_disability("
    )

    percent_pos = fn.find(
        "_b15245_apply_primary_th_m1_percentages(ws)"
    )

    if (
        compat_pos < 0
        or percent_pos < 0
        or compat_pos >= percent_pos
    ):
        raise RuntimeError(
            "Thứ tự TH_M1 sai: phải điền "
            "dòng 10/11/F44 trước khi tính G44."
        )


def main() -> None:
    print("=" * 144)
    print(
        "BÀI 13B-11.15.2.4.5.2 - "
        "TƯƠNG THÍCH DỮ LIỆU KHUYẾT TẬT "
        "+ NỐI TH_M1"
    )
    print("=" * 144)
    print()
    print("SẼ LÀM:")
    print(
        " - can_learn=True: dùng Có."
    )
    print(
        " - can_learn=False: giữ Không tuyệt đối."
    )
    print(
        " - can_learn=None + access=True: "
        "suy ra Có CHỈ TRONG BÁO CÁO."
    )
    print(
        " - TH_02 / THCS_M1 / THCS_TK "
        "tự hưởng quy tắc tương thích."
    )
    print(
        " - TH_M1: điền dòng 10, dòng 11, "
        "F44 và tính G44 theo mẫu."
    )
    print()
    print("KHÔNG LÀM:")
    print(" - Không UPDATE dữ liệu cũ.")
    print(" - Không ALTER TABLE.")
    print(" - Không sửa menu/route/template.")
    print(" - Không tự kết luận Đạt/Không đạt.")
    print()

    for required in (
        BUILDERS,
        REPORT_CENTER,
        RULES,
    ):
        if not required.exists():
            raise SystemExit(
                f"Không tìm thấy: {required}"
            )

    before = db_state()

    if before.get("exists"):
        if before["integrity"] != "ok":
            raise SystemExit(
                "Database integrity_check "
                "không phải ok."
            )

        if before["fk_count"] != 0:
            raise SystemExit(
                "Database có lỗi foreign key."
            )

        columns = set(before["columns"])
        needed = {
            "disability_can_learn",
            "disability_access_education",
        }

        missing = sorted(
            needed - columns
        )

        if missing:
            raise SystemExit(
                "DỪNG AN TOÀN: DB thiếu field: "
                + ", ".join(missing)
            )

    rules_text = read_text(RULES)

    if "def safe_percent(" not in rules_text:
        raise SystemExit(
            "Thiếu safe_percent trong "
            "pcgd_business_rules.py."
        )

    old_builders = read_text(BUILDERS)
    old_report_center = read_text(REPORT_CENTER)

    ast.parse(old_builders)
    ast.parse(old_report_center)

    if MARKER_BUILDERS_V51 not in old_builders:
        raise SystemExit(
            "Chưa thấy Bài 15.2.4.5.1 "
            "trong builders."
        )

    if (
        "_b15245_apply_primary_th_m1_percentages"
        not in old_report_center
    ):
        raise SystemExit(
            "Chưa thấy nền Bài 15.2.4.5 "
            "trong report_center.py."
        )

    new_builders, builder_notes = patch_builders(
        old_builders
    )

    new_report_center, report_notes = patch_report_center(
        old_report_center
    )

    ast.parse(new_builders)
    ast.parse(new_report_center)

    verify_source(
        new_builders,
        new_report_center,
    )

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    shutil.copy2(
        BUILDERS,
        BACKUP_DIR
        / "pcgd_xmc_report_builders_v1.py",
    )

    shutil.copy2(
        REPORT_CENTER,
        BACKUP_DIR
        / "report_center.py",
    )

    shutil.copy2(
        RULES,
        BACKUP_DIR
        / "pcgd_business_rules.py",
    )

    backup_database()

    try:
        if new_builders != old_builders:
            write_text(
                BUILDERS,
                new_builders,
            )

        if new_report_center != old_report_center:
            write_text(
                REPORT_CENTER,
                new_report_center,
            )

        for path in (
            BUILDERS,
            REPORT_CENTER,
            RULES,
        ):
            py_compile.compile(
                str(path),
                doraise=True,
            )

        installed_builders = read_text(BUILDERS)
        installed_report_center = read_text(REPORT_CENTER)

        ast.parse(installed_builders)
        ast.parse(installed_report_center)

        verify_source(
            installed_builders,
            installed_report_center,
        )

        after = db_state()

        if before != after:
            raise RuntimeError(
                "Database/schema/count hoặc "
                "các giá trị nguồn khuyết tật "
                "đã thay đổi ngoài dự kiến."
            )

        clear_cache()

    except Exception:
        restore_source()
        clear_cache()
        raise

    report = []
    report.append("=" * 144 + "\n")
    report.append(
        "BÀI 13B-11.15.2.4.5.2 "
        "- BÁO CÁO CÀI ĐẶT\n"
    )
    report.append("=" * 144 + "\n\n")

    report.append("QUY TẮC TƯƠNG THÍCH:\n")
    report.append(
        " - can_learn=True  -> Có khả năng học.\n"
    )
    report.append(
        " - can_learn=False -> Không có khả năng học; "
        "không suy ngược từ access.\n"
    )
    report.append(
        " - can_learn=None + access=True -> "
        "suy ra Có CHỈ TRONG BÁO CÁO.\n"
    )
    report.append(
        " - Không ghi giá trị suy ra vào DB.\n\n"
    )

    report.append("TH_M1:\n")
    report.append(
        " - Dòng 10: Có khả năng HT theo tuổi 6-14.\n"
    )
    report.append(
        " - Dòng 11: Tiếp cận GD trong nhóm có khả năng HT.\n"
    )
    report.append(
        " - K10/P10: tổng Có khả năng HT nhóm 6-10 / 11-14.\n"
    )
    report.append(
        " - F44: số trẻ KT có khả năng HT được tiếp cận GD.\n"
    )
    report.append(
        " - G44 = F44/(K10+P10)*100.\n"
    )
    report.append(
        " - Có mẫu số nhưng access=0 -> F44=0, G44=0%.\n"
    )
    report.append(
        " - Không có mẫu số -> G44 để trống.\n\n"
    )

    report.append("SOURCE:\n")
    for note in builder_notes:
        report.append(
            f" - Builders: {note}\n"
        )
    for note in report_notes:
        report.append(
            f" - TH_M1: {note}\n"
        )

    if before.get("exists"):
        report.append(
            "\nTHỐNG KÊ DỮ LIỆU TRƯỚC CÀI - CHỈ ĐỌC:\n"
        )
        report.append(
            " - can_learn=NULL + access=True: "
            f"{before['legacy']}\n"
        )
        report.append(
            " - can_learn=False + access=True "
            "(mâu thuẫn cần rà soát sau): "
            f"{before['false_access']}\n"
        )
        report.append(
            " - can_learn=True: "
            f"{before['explicit_true']}\n"
        )

    report.append("\nAN TOÀN:\n")
    report.append(" - Database không thay đổi.\n")
    report.append(" - Số bản ghi không thay đổi.\n")
    report.append(" - Schema không thay đổi.\n")
    report.append(" - integrity_check = ok.\n")
    report.append(" - foreign_key_check = 0.\n")
    report.append(" - Không sửa menu/route/template.\n")
    report.append(" - Không tự đánh giá Đạt/Không đạt.\n")
    report.append(
        f" - Backup: {BACKUP_DIR}\n"
    )

    REPORT_FILE.write_text(
        "".join(report),
        encoding="utf-8",
    )

    print("CÀI ĐẶT THÀNH CÔNG.")

    if before.get("exists"):
        print()
        print("Dữ liệu tương thích phát hiện:")
        print(
            " - can_learn=NULL + access=True:",
            before["legacy"],
        )
        print(
            " - can_learn=False + access=True:",
            before["false_access"],
        )

    print()
    print("Database: KHÔNG THAY ĐỔI.")
    print("Menu/route/template: KHÔNG THAY ĐỔI.")
    print(f"Backup: {BACKUP_DIR}")
    print(f"Báo cáo: {REPORT_FILE}")
    print()
    print("=" * 144)
    print(
        "BÀI 13B-11.15.2.4.5.2 THÀNH CÔNG"
    )
    print("=" * 144)


if __name__ == "__main__":
    main()
