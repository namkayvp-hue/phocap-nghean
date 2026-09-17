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

BUILDERS = (
    APP
    / "pcgd_xmc_report_builders_v1.py"
)

REPORT_CENTER = (
    APP
    / "routers"
    / "report_center.py"
)

RULES = (
    APP
    / "services"
    / "pcgd_business_rules.py"
)

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP = (
    EXPORTS
    / (
        "backup_bai_13b_11_15_2_4_5_2_v2_"
        + STAMP
    )
)

REPORT = (
    EXPORTS
    / (
        "bao_cao_bai_13b_11_15_2_4_5_2_v2_"
        + STAMP
        + ".txt"
    )
)

MARK_V51 = (
    "# === BAI_13B_11_15_2_4_5_1_"
    "DISABLED_CAPABLE_AND_M2_CLEANUP ==="
)

MARK_BUILDERS_V2 = (
    "# === BAI_13B_11_15_2_4_5_2_V2_"
    "DISABILITY_LEGACY_COMPAT ==="
)

TH_START = (
    "# === BAI_13B_11_15_2_4_5_2_V2_"
    "TH_M1_SHARED_LOADER_START ==="
)

TH_END = (
    "# === BAI_13B_11_15_2_4_5_2_V2_"
    "TH_M1_SHARED_LOADER_END ==="
)

PERCENT_CALL = (
    "    _b15245_apply_primary_th_m1_percentages(ws)\n"
)

COMPAT_CALL = (
    "    _b152452v2_apply_th_m1_disability(\n"
    "        ws=ws,\n"
    "        db=db,\n"
    "        request=request,\n"
    "        school_year_id=int(school_year.id),\n"
    "        selected_commune_id=selected_commune_id,\n"
    "        selected_school_id=selected_school_id,\n"
    "        reference_year=reference_year,\n"
    "    )\n"
)

NEW_CAN_LEARN = 'def _b152451_disabled_can_learn(\n    person: SurveyPerson,\n    record: SurveyPersonYearRecord | None,\n) -> bool:\n    """\n    Bài 13B-11.15.2.4.5.2 V2 - tương thích dữ liệu cũ.\n\n    Ưu tiên dữ liệu tường minh:\n    - True  -> Có khả năng học.\n    - False -> Không có khả năng học.\n    - None + disability_access_education=True\n      -> suy ra Có CHỈ KHI LẬP BÁO CÁO.\n\n    Không ghi giá trị suy ra trở lại database.\n    """\n    if (\n        not _is_disabled(person, record)\n        or record is None\n    ):\n        return False\n\n    explicit = getattr(\n        record,\n        "disability_can_learn",\n        None,\n    )\n\n    if explicit is True:\n        return True\n\n    if explicit is False:\n        return False\n\n    return (\n        getattr(\n            record,\n            "disability_access_education",\n            None,\n        )\n        is True\n    )\n'
TH_M1_HELPERS = '\n# === BAI_13B_11_15_2_4_5_2_V2_TH_M1_SHARED_LOADER_START ===\ndef _b152452v2_th_m1_can_learn(\n    person,\n    record,\n) -> bool:\n    if (\n        not _th_m1_is_disabled(\n            person,\n            record,\n        )\n        or record is None\n    ):\n        return False\n\n    explicit = getattr(\n        record,\n        "disability_can_learn",\n        None,\n    )\n\n    if explicit is True:\n        return True\n\n    if explicit is False:\n        return False\n\n    return (\n        getattr(\n            record,\n            "disability_access_education",\n            None,\n        )\n        is True\n    )\n\n\ndef _b152452v2_th_m1_access(\n    person,\n    record,\n) -> bool:\n    return bool(\n        _b152452v2_th_m1_can_learn(\n            person,\n            record,\n        )\n        and record is not None\n        and getattr(\n            record,\n            "disability_access_education",\n            None,\n        )\n        is True\n    )\n\n\ndef _b152452v2_birth_year(\n    person,\n) -> int | None:\n    value = getattr(\n        person,\n        "date_of_birth",\n        None,\n    )\n\n    year = getattr(\n        value,\n        "year",\n        None,\n    )\n\n    if year is not None:\n        try:\n            return int(year)\n        except (TypeError, ValueError):\n            return None\n\n    text = str(\n        value or ""\n    ).strip()\n\n    if len(text) >= 4:\n        try:\n            return int(\n                text[:4]\n            )\n        except ValueError:\n            return None\n\n    return None\n\n\ndef _b152452v2_apply_th_m1_disability(\n    *,\n    ws,\n    db,\n    request,\n    school_year_id: int,\n    selected_commune_id: int | None,\n    selected_school_id: int | None,\n    reference_year: int,\n) -> None:\n    """\n    TH_M1 dùng cùng bộ nạp đối tượng/phạm vi với\n    pcgd_xmc_report_builders_v1.py, không phụ thuộc\n    biến cục bộ bên trong _th_m1_build_metrics.\n    """\n    from app.pcgd_xmc_report_builders_v1 import (\n        _load_people_and_records,\n    )\n\n    people = _load_people_and_records(\n        db=db,\n        request=request,\n        school_year_id=int(\n            school_year_id\n        ),\n        selected_commune_id=selected_commune_id,\n        selected_school_id=selected_school_id,\n    )\n\n    age_columns = {\n        6: "F",\n        7: "G",\n        8: "H",\n        9: "I",\n        10: "J",\n        11: "L",\n        12: "M",\n        13: "N",\n        14: "O",\n    }\n\n    capable_by_age = {\n        age: 0\n        for age in age_columns\n    }\n\n    access_by_age = {\n        age: 0\n        for age in age_columns\n    }\n\n    for person, record in people:\n        birth_year = _b152452v2_birth_year(\n            person\n        )\n\n        if birth_year is None:\n            continue\n\n        age = (\n            int(reference_year)\n            - int(birth_year)\n        )\n\n        if age not in age_columns:\n            continue\n\n        if _b152452v2_th_m1_can_learn(\n            person,\n            record,\n        ):\n            capable_by_age[age] += 1\n\n            if _b152452v2_th_m1_access(\n                person,\n                record,\n            ):\n                access_by_age[age] += 1\n\n    for age, column in age_columns.items():\n        capable = capable_by_age[age]\n        access = access_by_age[age]\n\n        ws[f"{column}10"] = (\n            capable\n            if capable > 0\n            else None\n        )\n\n        ws[f"{column}11"] = (\n            access\n            if capable > 0\n            else None\n        )\n\n    capable_6_10 = sum(\n        capable_by_age[age]\n        for age in range(\n            6,\n            11,\n        )\n    )\n\n    access_6_10 = sum(\n        access_by_age[age]\n        for age in range(\n            6,\n            11,\n        )\n    )\n\n    capable_11_14 = sum(\n        capable_by_age[age]\n        for age in range(\n            11,\n            15,\n        )\n    )\n\n    access_11_14 = sum(\n        access_by_age[age]\n        for age in range(\n            11,\n            15,\n        )\n    )\n\n    ws["K10"] = (\n        capable_6_10\n        if capable_6_10 > 0\n        else None\n    )\n\n    ws["K11"] = (\n        access_6_10\n        if capable_6_10 > 0\n        else None\n    )\n\n    ws["P10"] = (\n        capable_11_14\n        if capable_11_14 > 0\n        else None\n    )\n\n    ws["P11"] = (\n        access_11_14\n        if capable_11_14 > 0\n        else None\n    )\n\n    capable_total = (\n        capable_6_10\n        + capable_11_14\n    )\n\n    access_total = (\n        access_6_10\n        + access_11_14\n    )\n\n    # F44 là tử số của công thức mẫu:\n    # G44 = F44 / (K10 + P10) * 100.\n    #\n    # Nếu có mẫu số nhưng không ai tiếp cận -> F44=0,\n    # để tỷ lệ ra đúng 0%.\n    ws["F44"] = (\n        access_total\n        if capable_total > 0\n        else None\n    )\n# === BAI_13B_11_15_2_4_5_2_V2_TH_M1_SHARED_LOADER_END ===\n\n\n'


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
    value: str,
) -> None:
    path.write_text(
        value,
        encoding="utf-8",
    )


def function_node(
    source: str,
    name: str,
):
    tree = ast.parse(source)

    found = [
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

    if len(found) != 1:
        raise RuntimeError(
            f"Phải tìm thấy đúng 1 hàm {name}; "
            f"hiện có {len(found)}."
        )

    return found[0]


def function_span(
    source: str,
    name: str,
) -> tuple[int, int]:
    node = function_node(
        source,
        name,
    )

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
        offsets[
            int(node.lineno) - 1
        ],
        offsets[
            int(node.end_lineno)
        ],
    )


def get_function(
    source: str,
    name: str,
) -> str:
    start, end = function_span(
        source,
        name,
    )

    return source[
        start:end
    ]


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


def remove_marker_block(
    source: str,
    start_marker: str,
    end_marker: str,
) -> str:
    while start_marker in source:
        start = source.find(
            start_marker
        )

        end = source.find(
            end_marker,
            start,
        )

        if end < 0:
            raise RuntimeError(
                "Có marker đầu nhưng thiếu marker cuối: "
                + start_marker
            )

        end += len(
            end_marker
        )

        line_start = (
            source.rfind(
                "\n",
                0,
                start,
            )
            + 1
        )

        line_end = source.find(
            "\n",
            end,
        )

        if line_end < 0:
            line_end = len(source)
        else:
            line_end += 1

        source = (
            source[:line_start]
            + source[line_end:]
        )

    return source


def db_state() -> dict:
    if not DB.exists():
        return {
            "exists": False,
        }

    con = sqlite3.connect(
        str(DB)
    )

    try:
        cols = [
            str(row[1])
            for row in con.execute(
                "PRAGMA table_info("
                "survey_person_year_records"
                ")"
            ).fetchall()
        ]

        count = int(
            con.execute(
                "SELECT COUNT(*) "
                "FROM survey_person_year_records"
            ).fetchone()[0]
        )

        integrity = str(
            con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = len(
            con.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        legacy = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM survey_person_year_records
                WHERE disability_can_learn IS NULL
                  AND disability_access_education = 1
                """
            ).fetchone()[0]
        )

        false_access = int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM survey_person_year_records
                WHERE disability_can_learn = 0
                  AND disability_access_education = 1
                """
            ).fetchone()[0]
        )

        return {
            "exists": True,
            "columns": cols,
            "count": count,
            "integrity": integrity,
            "fk": fk,
            "legacy": legacy,
            "false_access": false_access,
        }

    finally:
        con.close()


def backup_db() -> None:
    if not DB.exists():
        return

    src = sqlite3.connect(
        str(DB)
    )

    dst = sqlite3.connect(
        str(
            BACKUP
            / "phocap.db"
        )
    )

    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def restore_source() -> None:
    pairs = (
        (
            BACKUP
            / "pcgd_xmc_report_builders_v1.py",
            BUILDERS,
        ),
        (
            BACKUP
            / "report_center.py",
            REPORT_CENTER,
        ),
    )

    for source, target in pairs:
        if source.exists():
            shutil.copy2(
                source,
                target,
            )


def clear_cache() -> None:
    for cache in APP.rglob(
        "__pycache__"
    ):
        if cache.is_dir():
            shutil.rmtree(
                cache,
                ignore_errors=True,
            )


def verify_shared_loader_source(
    builders_text: str,
) -> None:
    fn = get_function(
        builders_text,
        "_load_people_and_records",
    )

    required = (
        "db",
        "request",
        "school_year_id",
        "selected_commune_id",
        "selected_school_id",
    )

    node = function_node(
        builders_text,
        "_load_people_and_records",
    )

    arg_names = {
        arg.arg
        for arg in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        )
    }

    missing = [
        name
        for name in required
        if name not in arg_names
    ]

    if missing:
        raise RuntimeError(
            "_load_people_and_records không đúng "
            "signature dự kiến; thiếu: "
            + ", ".join(missing)
        )

    if (
        "SurveyPerson"
        not in fn
        and "SurveyPersonYearRecord"
        not in fn
    ):
        raise RuntimeError(
            "_load_people_and_records không có dấu vết "
            "nguồn đối tượng/năm học như dự kiến."
        )


def patch_builders(
    source: str,
) -> tuple[str, list[str]]:
    notes = []

    if MARK_V51 not in source:
        raise RuntimeError(
            "Chưa thấy nền Bài 15.2.4.5.1 "
            "trong builders."
        )

    verify_shared_loader_source(
        source
    )

    current = get_function(
        source,
        "_b152451_disabled_can_learn",
    )

    if (
        "if explicit is False"
        in current
        and "disability_access_education"
        in current
    ):
        notes.append(
            "Helper tương thích khuyết tật đã có."
        )
    else:
        source = replace_function(
            source,
            "_b152451_disabled_can_learn",
            NEW_CAN_LEARN,
        )

        notes.append(
            "Đã sửa helper khuyết tật "
            "cho dữ liệu cũ."
        )

    if MARK_BUILDERS_V2 not in source:
        anchor_fn = get_function(
            source,
            "_b152451_disabled_access",
        )

        pos = source.find(
            anchor_fn
        )

        if pos < 0:
            raise RuntimeError(
                "Không khóa được vị trí marker "
                "builders V2."
            )

        source = (
            source[:pos]
            + MARK_BUILDERS_V2
            + "\n"
            + source[pos:]
        )

    ast.parse(source)
    return source, notes


def verify_th_m1_context(
    source: str,
) -> None:
    fn = get_function(
        source,
        "_build_primary_th_m1_workbook",
    )

    for token in (
        "db",
        "request",
        "school_year",
        "selected_commune_id",
        "selected_school_id",
        "reference_year",
        PERCENT_CALL.strip(),
    ):
        if token not in fn:
            raise RuntimeError(
                "TH_M1 builder thiếu ngữ cảnh bắt buộc: "
                + token
            )

    # Điểm lỗi của bản trước: không còn yêu cầu
    # _th_m1_build_metrics phải nhận people.
    if (
        fn.count(
            "_b15245_apply_primary_th_m1_percentages(ws)"
        )
        != 1
    ):
        raise RuntimeError(
            "TH_M1 phải có đúng 1 lời gọi "
            "bộ tính tỷ lệ Bài 15.2.4.5."
        )


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

    verify_th_m1_context(
        source
    )

    # Nếu từng thử bản V2 rồi, thay đúng block helper,
    # không chèn trùng.
    source = remove_marker_block(
        source,
        TH_START,
        TH_END,
    )

    anchor = (
        "def _build_primary_th_m1_workbook("
    )

    if source.count(anchor) != 1:
        raise RuntimeError(
            "Không tìm thấy đúng 1 "
            "_build_primary_th_m1_workbook."
        )

    source = source.replace(
        anchor,
        TH_M1_HELPERS
        + anchor,
        1,
    )

    fn = get_function(
        source,
        "_build_primary_th_m1_workbook",
    )

    # Dọn lời gọi V2 nếu đã có từ lần thử trước.
    old_call_start = (
        "    _b152452v2_apply_th_m1_disability(\n"
    )

    if old_call_start in fn:
        start = fn.find(
            old_call_start
        )

        end = fn.find(
            "    )\n",
            start,
        )

        if end < 0:
            raise RuntimeError(
                "Không xác định được cuối lời gọi "
                "TH_M1 V2 cũ."
            )

        end += len(
            "    )\n"
        )

        fn = (
            fn[:start]
            + fn[end:]
        )

    if fn.count(PERCENT_CALL) != 1:
        raise RuntimeError(
            "Không tìm thấy đúng 1 vị trí "
            "trước bộ tính tỷ lệ TH_M1."
        )

    fn = fn.replace(
        PERCENT_CALL,
        COMPAT_CALL
        + PERCENT_CALL,
        1,
    )

    source = replace_function(
        source,
        "_build_primary_th_m1_workbook",
        fn,
    )

    notes.append(
        "Đã nối TH_M1 bằng shared loader "
        "_load_people_and_records."
    )

    ast.parse(source)
    return source, notes


def verify_after(
    builders_text: str,
    report_text: str,
) -> None:
    for token in (
        "def _b152451_disabled_can_learn(",
        "if explicit is False:",
        "disability_access_education",
        MARK_BUILDERS_V2,
    ):
        if token not in builders_text:
            raise RuntimeError(
                "Builders sau cài thiếu: "
                + token
            )

    for token in (
        TH_START,
        TH_END,
        "def _b152452v2_apply_th_m1_disability(",
        "from app.pcgd_xmc_report_builders_v1 import (",
        "_load_people_and_records,",
        'ws["K10"]',
        'ws["P10"]',
        'ws["F44"]',
        "_b152452v2_apply_th_m1_disability(",
        "_b15245_apply_primary_th_m1_percentages(ws)",
    ):
        if token not in report_text:
            raise RuntimeError(
                "TH_M1 sau cài thiếu: "
                + token
            )

    fn = get_function(
        report_text,
        "_build_primary_th_m1_workbook",
    )

    compat = fn.find(
        "_b152452v2_apply_th_m1_disability("
    )

    percent = fn.find(
        "_b15245_apply_primary_th_m1_percentages(ws)"
    )

    if (
        compat < 0
        or percent < 0
        or compat >= percent
    ):
        raise RuntimeError(
            "Sai thứ tự: phải nối nguồn "
            "khuyết tật trước rồi mới tính G44."
        )


def main() -> None:
    print("=" * 146)
    print(
        "BÀI 13B-11.15.2.4.5.2 V2 - "
        "SỬA LỖI AUTO-DETECT + "
        "TƯƠNG THÍCH KHUYẾT TẬT + NỐI TH_M1"
    )
    print("=" * 146)
    print()
    print("SỬA LỖI BẢN TRƯỚC:")
    print(
        " - Không còn cố lấy danh sách people "
        "từ đối số _th_m1_build_metrics."
    )
    print(
        " - TH_M1 dùng trực tiếp shared loader "
        "_load_people_and_records đã có."
    )
    print()
    print("NGHIỆP VỤ:")
    print(
        " - can_learn=True -> Có."
    )
    print(
        " - can_learn=False -> giữ Không."
    )
    print(
        " - can_learn=None + access=True -> "
        "suy ra Có chỉ trong báo cáo."
    )
    print(
        " - TH_M1 điền dòng 10/11, "
        "K10/P10, F44 rồi tính G44."
    )
    print()
    print("AN TOÀN:")
    print(" - Không ALTER TABLE.")
    print(" - Không UPDATE dữ liệu.")
    print(" - Không sửa menu/route/template.")
    print(" - Có backup + rollback.")
    print()

    for path in (
        BUILDERS,
        REPORT_CENTER,
        RULES,
    ):
        if not path.exists():
            raise SystemExit(
                f"Không tìm thấy: {path}"
            )

    before_db = db_state()

    if before_db.get("exists"):
        if before_db["integrity"] != "ok":
            raise SystemExit(
                "Database integrity_check != ok."
            )

        if before_db["fk"] != 0:
            raise SystemExit(
                "Database đang có lỗi foreign key."
            )

        required_cols = {
            "disability_can_learn",
            "disability_access_education",
        }

        missing = (
            required_cols
            - set(before_db["columns"])
        )

        if missing:
            raise SystemExit(
                "DB thiếu cột: "
                + ", ".join(
                    sorted(missing)
                )
            )

    old_builders = read_text(
        BUILDERS
    )

    old_report = read_text(
        REPORT_CENTER
    )

    rules_text = read_text(
        RULES
    )

    ast.parse(old_builders)
    ast.parse(old_report)
    ast.parse(rules_text)

    if (
        "_b15245_apply_primary_th_m1_percentages"
        not in old_report
    ):
        raise SystemExit(
            "Chưa có nền Bài 15.2.4.5 "
            "tính tỷ lệ TH_M1."
        )

    # PRE-FLIGHT HOÀN TOÀN TRƯỚC KHI GHI FILE.
    new_builders, notes_b = patch_builders(
        old_builders
    )

    new_report, notes_r = patch_report_center(
        old_report
    )

    verify_after(
        new_builders,
        new_report,
    )

    ast.parse(new_builders)
    ast.parse(new_report)

    BACKUP.mkdir(
        parents=True,
        exist_ok=False,
    )

    shutil.copy2(
        BUILDERS,
        BACKUP
        / "pcgd_xmc_report_builders_v1.py",
    )

    shutil.copy2(
        REPORT_CENTER,
        BACKUP
        / "report_center.py",
    )

    shutil.copy2(
        RULES,
        BACKUP
        / "pcgd_business_rules.py",
    )

    backup_db()

    try:
        if new_builders != old_builders:
            write_text(
                BUILDERS,
                new_builders,
            )

        if new_report != old_report:
            write_text(
                REPORT_CENTER,
                new_report,
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

        installed_b = read_text(
            BUILDERS
        )

        installed_r = read_text(
            REPORT_CENTER
        )

        ast.parse(installed_b)
        ast.parse(installed_r)

        verify_after(
            installed_b,
            installed_r,
        )

        after_db = db_state()

        if before_db != after_db:
            raise RuntimeError(
                "Database/schema/count/nguồn "
                "khuyết tật thay đổi ngoài dự kiến."
            )

        clear_cache()

    except Exception:
        restore_source()
        clear_cache()
        raise

    lines = [
        "=" * 146 + "\n",
        (
            "BÀI 13B-11.15.2.4.5.2 V2 "
            "- BÁO CÁO CÀI ĐẶT\n"
        ),
        "=" * 146 + "\n\n",
        "SỬA LỖI:\n",
        (
            " - Đã bỏ cơ chế tìm people từ "
            "_th_m1_build_metrics.\n"
        ),
        (
            " - TH_M1 dùng shared loader "
            "_load_people_and_records.\n\n"
        ),
        "NGHIỆP VỤ KHUYẾT TẬT:\n",
        " - True -> Có khả năng HT.\n",
        " - False -> Không có khả năng HT.\n",
        (
            " - None + access=True -> "
            "suy ra Có chỉ trong báo cáo.\n"
        ),
        " - Không ghi suy ra vào DB.\n\n",
        "TH_M1:\n",
        (
            " - Dòng 10: số KT có khả năng HT "
            "theo tuổi 6-14.\n"
        ),
        (
            " - Dòng 11: số được tiếp cận GD "
            "trong nhóm có khả năng HT.\n"
        ),
        " - K10/P10: tổng mẫu số hai nhóm tuổi.\n",
        " - F44: tổng số được tiếp cận GD.\n",
        " - G44=F44/(K10+P10)*100.\n\n",
        "SOURCE:\n",
        *[
            " - Builders: " + item + "\n"
            for item in notes_b
        ],
        *[
            " - TH_M1: " + item + "\n"
            for item in notes_r
        ],
        "\nAN TOÀN:\n",
        " - Database không thay đổi.\n",
        " - Schema không thay đổi.\n",
        " - Số bản ghi không thay đổi.\n",
        " - Không sửa menu/route/template.\n",
        f" - Backup: {BACKUP}\n",
    ]

    if before_db.get("exists"):
        lines.extend(
            [
                "\nDỮ LIỆU TƯƠNG THÍCH - CHỈ ĐỌC:\n",
                (
                    " - can_learn=NULL + access=True: "
                    + str(before_db["legacy"])
                    + "\n"
                ),
                (
                    " - can_learn=False + access=True: "
                    + str(before_db["false_access"])
                    + "\n"
                ),
            ]
        )

    REPORT.write_text(
        "".join(lines),
        encoding="utf-8",
    )

    print()
    print("KIỂM TRA:")
    print(" - py_compile: OK")
    print(" - AST: OK")
    print(
        " - Shared loader TH_M1: OK"
    )
    print(
        " - Database không thay đổi: OK"
    )

    if before_db.get("exists"):
        print()
        print("Dữ liệu tương thích:")
        print(
            " - can_learn=NULL + access=True:",
            before_db["legacy"],
        )
        print(
            " - can_learn=False + access=True:",
            before_db["false_access"],
        )

    print()
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print("=" * 146)
    print(
        "BÀI 13B-11.15.2.4.5.2 V2 THÀNH CÔNG"
    )
    print("=" * 146)


if __name__ == "__main__":
    main()
