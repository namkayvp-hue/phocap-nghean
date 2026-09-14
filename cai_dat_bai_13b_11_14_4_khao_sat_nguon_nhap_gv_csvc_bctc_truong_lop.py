from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

REPORT_TXT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_14_4_khao_sat_nguon_nhap_{STAMP}.txt"
)

MATRIX_CSV = (
    EXPORTS
    / f"ma_tran_bai_13b_11_14_4_nguon_nhap_{STAMP}.csv"
)

SOURCE_EXTENSIONS = {
    ".py",
    ".html",
    ".htm",
    ".js",
    ".css",
    ".json",
    ".txt",
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "exports",
    "backup",
    "backups",
}

BACKUP_NAME_HINTS = (
    "backup",
    "bak",
    "old",
    "copy",
    "restore",
    "truoc_sua",
    "trước_sửa",
    "sao_luu",
    "sao-luu",
)


GROUPS = {
    "TRUONG_LOP": {
        "label": "Trường / cơ sở / điểm trường / nhóm lớp",
        "table_keywords": (
            "school",
            "campus",
            "site",
            "class",
            "group",
            "lop",
            "truong",
            "diem",
            "facility",
        ),
        "column_keywords": (
            "school_id",
            "school_level",
            "school_type",
            "class_id",
            "class_name",
            "class_type",
            "campus",
            "site",
            "point",
            "single",
            "combined",
            "ghep",
            "don",
            "independent",
            "co_so",
            "diem_truong",
            "so_lop",
            "student_count",
            "children_count",
        ),
        "source_keywords": (
            "lớp đơn",
            "lớp ghép",
            "điểm trường",
            "cơ sở độc lập",
            "nhóm/lớp",
            "class_config",
            "school_class",
            "classes",
            "schools",
        ),
        "expected": (
            "Danh mục trường/cơ sở",
            "Điểm trường",
            "Nhóm/lớp",
            "Lớp đơn/lớp ghép",
            "Số trẻ/lớp",
            "Trường/cơ sở độc lập",
        ),
    },

    "GV": {
        "label": "Đội ngũ / Giáo viên / CBQL / Nhân viên",
        "table_keywords": (
            "staff",
            "teacher",
            "employee",
            "personnel",
            "workforce",
            "can_bo",
            "giao_vien",
            "nhan_vien",
        ),
        "column_keywords": (
            "position",
            "job",
            "role",
            "title",
            "employment",
            "contract",
            "qualification",
            "degree",
            "professional",
            "standard",
            "assessment",
            "rating",
            "policy",
            "allowance",
            "benefit",
            "salary",
            "teaching_level",
            "subject",
            "class_id",
            "school_id",
            "status",
        ),
        "source_keywords": (
            "đội ngũ",
            "giáo viên",
            "nhân viên",
            "cán bộ quản lý",
            "hợp đồng",
            "trình độ",
            "chuẩn nghề nghiệp",
            "chế độ chính sách",
            "staff",
            "teacher",
            "qualification",
            "professional standard",
        ),
        "expected": (
            "Danh sách CBQL/GV/NV",
            "Loại hợp đồng",
            "Chức vụ/vị trí việc làm",
            "Trình độ đào tạo",
            "Môn/nhiệm vụ",
            "Lớp phụ trách",
            "Chuẩn nghề nghiệp",
            "Chế độ/chính sách",
            "Trạng thái công tác",
        ),
    },

    "CSVC": {
        "label": "Cơ sở vật chất / Thiết bị dạy học",
        "table_keywords": (
            "facility",
            "infrastructure",
            "room",
            "equipment",
            "device",
            "asset",
            "cs_vc",
            "csvc",
            "tbdh",
            "kitchen",
            "toilet",
            "water",
            "playground",
        ),
        "column_keywords": (
            "room",
            "classroom",
            "permanent",
            "semi",
            "temporary",
            "equipment",
            "device",
            "toilet",
            "water",
            "kitchen",
            "playground",
            "yard",
            "sanitation",
            "clean_water",
            "school_id",
            "school_year_id",
            "quantity",
            "status",
            "standard",
        ),
        "source_keywords": (
            "cơ sở vật chất",
            "csvc",
            "tbdh",
            "thiết bị dạy học",
            "phòng học",
            "phòng chức năng",
            "kiên cố",
            "bán kiên cố",
            "nước sạch",
            "vệ sinh",
            "bếp ăn",
            "sân chơi",
            "đồ dùng",
            "đồ chơi",
        ),
        "expected": (
            "Phòng học",
            "Loại phòng học",
            "Kiên cố/bán kiên cố/tạm",
            "Phòng chức năng",
            "Thiết bị/đồ dùng/đồ chơi",
            "Nhà vệ sinh",
            "Nước sạch",
            "Bếp ăn",
            "Sân chơi",
            "Tình trạng/đạt chuẩn từng hạng mục",
        ),
    },

    "BCTC": {
        "label": "Báo cáo tài chính / Kinh phí / Chính sách",
        "table_keywords": (
            "finance",
            "financial",
            "fund",
            "budget",
            "expense",
            "cost",
            "money",
            "payment",
            "policy",
            "allowance",
            "tai_chinh",
            "kinh_phi",
        ),
        "column_keywords": (
            "amount",
            "money",
            "budget",
            "fund",
            "funding",
            "source",
            "policy",
            "code",
            "indicator",
            "item",
            "description",
            "school_id",
            "commune_id",
            "school_year_id",
            "note",
        ),
        "source_keywords": (
            "tài chính",
            "báo cáo tài chính",
            "kinh phí",
            "nguồn kinh phí",
            "dự toán",
            "quyết toán",
            "ngân sách",
            "hỗ trợ",
            "financial",
            "finance",
            "budget",
        ),
        "expected": (
            "Năm học",
            "Đơn vị",
            "Mã chỉ tiêu",
            "Nhóm chỉ tiêu",
            "Nội dung",
            "Nguồn kinh phí",
            "Số tiền",
            "Ghi chú/chứng từ",
        ),
    },

    "DTKT": {
        "label": "Đối tượng khuyết tật",
        "table_keywords": (
            "disability",
            "khuyet_tat",
        ),
        "column_keywords": (
            "disability_status",
            "disability_type",
            "disability_level",
            "disability_certificate",
            "inclusive_education",
            "disability_support",
            "support_details",
            "disability_can_learn",
            "disability_access_education",
        ),
        "source_keywords": (
            "khuyết tật",
            "dạng tật",
            "mức độ khuyết tật",
            "khả năng học tập",
            "tiếp cận giáo dục",
            "giáo dục hòa nhập",
        ),
        "expected": (
            "Tình trạng khuyết tật",
            "8 dạng tật chuẩn hóa",
            "Mức độ khuyết tật",
            "Có khả năng học tập",
            "Được tiếp cận giáo dục",
            "Giáo dục hòa nhập",
            "Hỗ trợ khuyết tật",
        ),
    },

    "SO_PC": {
        "label": "Sổ phổ cập / dữ liệu liên năm",
        "table_keywords": (
            "survey_person_year",
            "historical",
            "household",
            "survey_people",
            "survey_person_events",
        ),
        "column_keywords": (
            "school_year_id",
            "school_id",
            "class_id",
            "school_name_reported",
            "class_name_reported",
            "guardian",
            "residency",
            "event_type",
            "event_date",
            "origin_location",
            "destination_location",
            "disability",
        ),
        "source_keywords": (
            "sổ phổ cập",
            "sổ theo dõi",
            "liên năm",
            "năm học",
            "chuyển đến",
            "chuyển đi",
            "tử vong",
            "cha mẹ",
            "người đỡ đầu",
        ),
        "expected": (
            "Thông tin hộ",
            "Cha/mẹ/người đỡ đầu",
            "Dữ liệu trường/lớp từng năm",
            "Cư trú",
            "Chuyển đến",
            "Chuyển đi",
            "Tử vong",
            "Khuyết tật",
            "Lịch sử liên năm",
        ),
    },
}


def normalize(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower(),
    )


def is_backup_like(path: Path) -> bool:
    name = normalize(path.name)

    return any(
        hint in name
        for hint in BACKUP_NAME_HINTS
    )


def list_tables(
    conn: sqlite3.Connection,
) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]


def table_columns(
    conn: sqlite3.Connection,
    table: str,
) -> list[tuple]:
    return conn.execute(
        f'PRAGMA table_info("{table}")'
    ).fetchall()


def table_row_count(
    conn: sqlite3.Connection,
    table: str,
) -> int:
    try:
        return int(
            conn.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]
        )
    except Exception:
        return -1


def scan_source_files() -> list[Path]:
    results = []

    for path in PROJECT.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue

        parts_lower = {
            part.lower()
            for part in path.parts
        }

        if parts_lower & SKIP_DIR_NAMES:
            continue

        if is_backup_like(path):
            continue

        results.append(path)

    return sorted(results)


def read_source_safely(
    path: Path,
) -> str:
    try:
        return path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )
    except Exception:
        return ""


def detect_routes(
    source_files: list[Path],
) -> list[dict]:
    results = []

    route_pattern = re.compile(
        r'@(?:router|app)\.'
        r'(get|post|put|patch|delete)'
        r'\(\s*["\']([^"\']+)["\']',
        flags=re.IGNORECASE,
    )

    for path in source_files:
        if path.suffix.lower() != ".py":
            continue

        text = read_source_safely(path)

        for match in route_pattern.finditer(text):
            results.append(
                {
                    "method": match.group(1).upper(),
                    "route": match.group(2),
                    "file": str(
                        path.relative_to(PROJECT)
                    ),
                }
            )

    return results


def detect_templates(
    source_files: list[Path],
) -> list[Path]:
    return [
        path
        for path in source_files
        if path.suffix.lower()
        in {".html", ".htm"}
    ]


def keyword_hits(
    text: str,
    keywords: tuple[str, ...],
) -> list[str]:
    low = normalize(text)

    hits = []

    for keyword in keywords:
        if normalize(keyword) in low:
            hits.append(keyword)

    return hits


def score_db_candidate(
    table: str,
    columns: list[str],
    group: dict,
) -> tuple[int, list[str]]:
    score = 0
    reasons = []

    table_low = normalize(table)

    for keyword in group["table_keywords"]:
        if normalize(keyword) in table_low:
            score += 4
            reasons.append(
                f"table:{keyword}"
            )

    column_low = [
        normalize(col)
        for col in columns
    ]

    for keyword in group["column_keywords"]:
        key = normalize(keyword)

        if any(
            key in col
            for col in column_low
        ):
            score += 1
            reasons.append(
                f"col:{keyword}"
            )

    return score, reasons


def infer_status(
    db_candidates: list[dict],
    source_candidates: list[dict],
) -> str:
    has_db = bool(db_candidates)
    has_source = bool(source_candidates)

    if has_db and has_source:
        return "CÓ DB + CÓ SOURCE/UI"
    if has_db:
        return "CÓ DB - CẦN KIỂM TRA UI"
    if has_source:
        return "CÓ SOURCE/UI - CHƯA THẤY DB RÕ"
    return "CHƯA THẤY NGUỒN"


def find_excel_files() -> list[Path]:
    results = []

    allowed = {
        ".xlsx",
        ".xlsm",
        ".xls",
    }

    for root_name in (
        "Mau_goc",
        "documents",
        "uploads",
        "payload",
        "data",
    ):
        root = PROJECT / root_name

        if not root.exists():
            continue

        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower()
                in allowed
            ):
                results.append(path)

    return sorted(
        set(results)
    )


def line(
    report: list[str],
    text: str = "",
) -> None:
    report.append(text)


def main() -> int:
    print(
        "=" * 126
    )
    print(
        "BÀI 13B-11.14.4 - "
        "KHẢO SÁT TOÀN BỘ NGUỒN NHẬP "
        "GV + CSVC + BCTC + TRƯỜNG/LỚP HIỆN CÓ"
    )
    print(
        "=" * 126
    )
    print()
    print(
        "NGUYÊN TẮC:"
    )
    print(
        " - CHỈ ĐỌC database và source."
    )
    print(
        " - Không ALTER/INSERT/UPDATE/DELETE database."
    )
    print(
        " - Không sửa source/template."
    )
    print(
        " - Không tạo chức năng mới trong bài khảo sát."
    )
    print()
    print(
        "MỤC TIÊU:"
    )
    print(
        " - Xác định nguồn nhập Trường/Lớp."
    )
    print(
        " - Xác định nguồn nhập Đội ngũ/GV."
    )
    print(
        " - Xác định nguồn nhập CSVC/TBDH."
    )
    print(
        " - Xác định nguồn nhập BCTC/Tài chính."
    )
    print(
        " - Kiểm tra ĐTKT và Sổ PC để tránh tạo trùng."
    )
    print(
        " - Lập ma trận CÓ DB / CÓ SOURCE / CÒN THIẾU."
    )
    print()

    if not PROJECT.exists():
        raise RuntimeError(
            f"Không tìm thấy project: {PROJECT}"
        )

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    EXPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = []

    line(
        report,
        "=" * 126,
    )
    line(
        report,
        "BÁO CÁO BÀI 13B-11.14.4 - "
        "KHẢO SÁT NGUỒN NHẬP GV + CSVC + BCTC + TRƯỜNG/LỚP",
    )
    line(
        report,
        "=" * 126,
    )
    line(
        report,
        f"Thời điểm: {datetime.now():%d/%m/%Y %H:%M:%S}",
    )
    line(
        report,
        f"Project: {PROJECT}",
    )
    line(
        report,
        f"Database: {DB}",
    )
    line(
        report,
    )

    conn = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_rows = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        tables = list_tables(
            conn
        )

        line(
            report,
            "I. KIỂM TRA AN TOÀN DATABASE",
        )
        line(
            report,
            "-" * 90,
        )
        line(
            report,
            f"integrity_check: {integrity}",
        )
        line(
            report,
            f"foreign_key_check: {len(fk_rows)} lỗi",
        )
        line(
            report,
            f"Tổng số bảng: {len(tables)}",
        )
        line(
            report,
        )

        if (
            integrity.lower() != "ok"
            or fk_rows
        ):
            raise RuntimeError(
                "Database không đạt kiểm tra an toàn."
            )

        table_meta = {}

        for table in tables:
            cols_info = table_columns(
                conn,
                table,
            )

            cols = [
                str(row[1])
                for row in cols_info
            ]

            table_meta[table] = {
                "columns": cols,
                "count": table_row_count(
                    conn,
                    table,
                ),
            }

    finally:
        conn.close()

    source_files = scan_source_files()
    routes = detect_routes(
        source_files
    )
    templates = detect_templates(
        source_files
    )
    excel_files = find_excel_files()

    line(
        report,
        "II. QUÉT SOURCE / TEMPLATE / ROUTE",
    )
    line(
        report,
        "-" * 90,
    )
    line(
        report,
        f"File source/template được quét: {len(source_files)}",
    )
    line(
        report,
        f"Route phát hiện: {len(routes)}",
    )
    line(
        report,
        f"Template HTML phát hiện: {len(templates)}",
    )
    line(
        report,
        f"File Excel tìm thấy trong các thư mục dự án: {len(excel_files)}",
    )

    if excel_files:
        for path in excel_files[:30]:
            line(
                report,
                "  - "
                + str(
                    path.relative_to(PROJECT)
                ),
            )

        if len(excel_files) > 30:
            line(
                report,
                f"  ... còn {len(excel_files) - 30} file",
            )
    else:
        line(
            report,
            "  - Chưa tìm thấy file Excel trong "
            "Mau_goc/documents/uploads/payload/data.",
        )

    line(
        report,
    )

    matrix_rows = []

    for group_code, group in GROUPS.items():
        db_candidates = []

        for table, meta in table_meta.items():
            score, reasons = score_db_candidate(
                table,
                meta["columns"],
                group,
            )

            if score >= 3:
                db_candidates.append(
                    {
                        "table": table,
                        "score": score,
                        "reasons": reasons,
                        "count": meta["count"],
                        "columns": meta["columns"],
                    }
                )

        db_candidates.sort(
            key=lambda item: (
                -item["score"],
                item["table"],
            )
        )

        source_candidates = []

        for path in source_files:
            text = read_source_safely(
                path
            )

            hits = keyword_hits(
                text,
                group["source_keywords"],
            )

            if hits:
                source_candidates.append(
                    {
                        "file": str(
                            path.relative_to(PROJECT)
                        ),
                        "hits": hits,
                    }
                )

        source_candidates.sort(
            key=lambda item: (
                -len(item["hits"]),
                item["file"],
            )
        )

        related_routes = []

        route_text = " ".join(
            group["source_keywords"]
        )

        for route in routes:
            combined = normalize(
                route["route"]
                + " "
                + route["file"]
            )

            if any(
                normalize(k) in combined
                for k in (
                    group["table_keywords"]
                    + group["source_keywords"]
                )
            ):
                related_routes.append(
                    route
                )

        status = infer_status(
            db_candidates,
            source_candidates,
        )

        line(
            report,
            "III."
            + str(
                list(GROUPS.keys()).index(
                    group_code
                )
                + 1
            )
            + " "
            + group["label"].upper(),
        )
        line(
            report,
            "-" * 90,
        )
        line(
            report,
            f"Kết luận sơ bộ: {status}",
        )
        line(
            report,
            "Các nguồn dữ liệu cần có:",
        )

        for item in group["expected"]:
            line(
                report,
                f"  - {item}",
            )

        line(
            report,
        )
        line(
            report,
            "Bảng DB liên quan mạnh nhất:",
        )

        if db_candidates:
            for item in db_candidates[:12]:
                line(
                    report,
                    f"  - {item['table']} "
                    f"(score={item['score']}, "
                    f"rows={item['count']})",
                )
                line(
                    report,
                    "    Cột: "
                    + ", ".join(
                        item["columns"][:40]
                    ),
                )
                if len(item["columns"]) > 40:
                    line(
                        report,
                        "    ...",
                    )
        else:
            line(
                report,
                "  - Chưa thấy bảng DB phù hợp rõ ràng.",
            )

        line(
            report,
        )
        line(
            report,
            "Source/template liên quan mạnh nhất:",
        )

        if source_candidates:
            for item in source_candidates[:15]:
                line(
                    report,
                    f"  - {item['file']}",
                )
                line(
                    report,
                    "    Từ khóa: "
                    + ", ".join(
                        item["hits"][:15]
                    ),
                )
        else:
            line(
                report,
                "  - Chưa thấy source/template rõ ràng.",
            )

        line(
            report,
        )
        line(
            report,
            "Route liên quan:",
        )

        if related_routes:
            seen = set()

            for item in related_routes[:20]:
                key = (
                    item["method"],
                    item["route"],
                    item["file"],
                )

                if key in seen:
                    continue

                seen.add(
                    key
                )

                line(
                    report,
                    f"  - {item['method']} "
                    f"{item['route']} "
                    f":: {item['file']}",
                )
        else:
            line(
                report,
                "  - Chưa phát hiện route theo từ khóa.",
            )

        line(
            report,
        )

        matrix_rows.append(
            {
                "nhom": group_code,
                "ten_nhom": group["label"],
                "trang_thai_so_bo": status,
                "bang_db_hang_dau": (
                    "; ".join(
                        item["table"]
                        for item
                        in db_candidates[:8]
                    )
                ),
                "source_hang_dau": (
                    "; ".join(
                        item["file"]
                        for item
                        in source_candidates[:8]
                    )
                ),
                "so_bang_db_lien_quan": len(
                    db_candidates
                ),
                "so_source_lien_quan": len(
                    source_candidates
                ),
                "so_route_lien_quan": len(
                    related_routes
                ),
                "nguon_can_co": " | ".join(
                    group["expected"]
                ),
            }
        )

    # ------------------------------------------------------------
    # IV. KIỂM TRA CÁC CẤU TRÚC QUAN TRỌNG CỤ THỂ
    # ------------------------------------------------------------
    line(
        report,
        "IV. KIỂM TRA CÁC TRƯỜNG/BẢNG CỤ THỂ QUAN TRỌNG",
    )
    line(
        report,
        "-" * 90,
    )

    def exact_table(name: str):
        return table_meta.get(name)

    exact_checks = [
        (
            "survey_person_year_records",
            (
                "disability_status",
                "disability_type",
                "disability_level",
                "disability_can_learn",
                "disability_access_education",
                "inclusive_education",
                "disability_support",
                "support_details",
                "attends_two_sessions_per_day",
            ),
        ),
        (
            "survey_people",
            (
                "residency_status",
                "guardian_name_reported",
            ),
        ),
        (
            "survey_person_events",
            (
                "event_type",
                "event_date",
                "origin_location",
                "destination_location",
                "school_year_id",
            ),
        ),
    ]

    for table, expected_cols in exact_checks:
        meta = exact_table(
            table
        )

        line(
            report,
            f"[{table}]",
        )

        if not meta:
            line(
                report,
                "  - KHÔNG CÓ BẢNG",
            )
            continue

        cols = set(
            meta["columns"]
        )

        line(
            report,
            f"  - Số bản ghi: {meta['count']}",
        )

        for col in expected_cols:
            line(
                report,
                f"  - {col}: "
                + (
                    "CÓ"
                    if col in cols
                    else "THIẾU"
                ),
            )

    line(
        report,
    )

    # ------------------------------------------------------------
    # V. TÌM CÁC BẢNG CÓ KHÓA NĂM HỌC + ĐƠN VỊ
    # ------------------------------------------------------------
    line(
        report,
        "V. BẢNG CÓ KHẢ NĂNG LÀ NGUỒN NHẬP THEO NĂM HỌC/ĐƠN VỊ",
    )
    line(
        report,
        "-" * 90,
    )

    year_unit_candidates = []

    for table, meta in table_meta.items():
        cols = set(
            meta["columns"]
        )

        has_year = (
            "school_year_id" in cols
            or "year_id" in cols
            or "school_year" in cols
        )

        has_unit = bool(
            {
                "school_id",
                "commune_id",
                "unit_id",
                "organization_id",
            }
            & cols
        )

        if has_year and has_unit:
            year_unit_candidates.append(
                (
                    table,
                    meta["count"],
                    sorted(
                        {
                            "school_year_id",
                            "year_id",
                            "school_year",
                            "school_id",
                            "commune_id",
                            "unit_id",
                            "organization_id",
                        }
                        & cols
                    ),
                )
            )

    if year_unit_candidates:
        for table, count, keys in sorted(
            year_unit_candidates
        ):
            line(
                report,
                f"  - {table}: rows={count}; "
                f"keys={', '.join(keys)}",
            )
    else:
        line(
            report,
            "  - Chưa có bảng rõ ràng dùng đồng thời năm học + đơn vị.",
        )

    line(
        report,
    )

    # ------------------------------------------------------------
    # VI. NHẬN ĐỊNH VÀ LỘ TRÌNH
    # ------------------------------------------------------------
    line(
        report,
        "VI. NGUYÊN TẮC THIẾT KẾ SAU KHẢO SÁT",
    )
    line(
        report,
        "-" * 90,
    )
    line(
        report,
        "1. Không tạo màn nhập mới nếu nguồn tương đương đã có.",
    )
    line(
        report,
        "2. Nếu có DB nhưng chưa có UI -> bổ sung UI vào chức năng hiện có.",
    )
    line(
        report,
        "3. Nếu có UI/source nhưng DB chưa đủ -> chuẩn hóa schema trước.",
    )
    line(
        report,
        "4. GV/CSVC/BCTC đều phải lưu theo Năm học + Đơn vị.",
    )
    line(
        report,
        "5. Tỷ lệ, GV/lớp, phòng/lớp, trẻ/lớp và Đạt/Không đạt "
        "phải là dữ liệu tự tính.",
    )
    line(
        report,
        "6. BCTC ưu tiên mô hình dòng chi tiết: "
        "mã chỉ tiêu + năm học + đơn vị + nguồn + số tiền.",
    )
    line(
        report,
        "7. ĐTKT dùng dữ liệu cấu trúc, không suy từ ghi chú.",
    )
    line(
        report,
        "8. Sổ PC lấy dữ liệu liên năm; không nhập lại một bộ sổ riêng.",
    )
    line(
        report,
    )

    line(
        report,
        "VII. ĐỀ XUẤT BÀI TIẾP THEO SAU KHI ĐỌC KẾT QUẢ",
    )
    line(
        report,
        "-" * 90,
    )
    line(
        report,
        " - 13B-11.14.5: Chuẩn hóa schema còn thiếu cho Trường/Lớp + GV + CSVC + BCTC.",
    )
    line(
        report,
        " - 13B-11.14.6: Hoàn thiện giao diện nhập Trường/Lớp.",
    )
    line(
        report,
        " - 13B-11.14.7: Hoàn thiện giao diện nhập Đội ngũ/GV.",
    )
    line(
        report,
        " - 13B-11.14.8: Hoàn thiện giao diện nhập CSVC/TBDH.",
    )
    line(
        report,
        " - 13B-11.14.9: Hoàn thiện giao diện nhập BCTC/Tài chính.",
    )
    line(
        report,
        " - Sau đó mới nối chính xác từng nguồn vào 7 sheet báo cáo.",
    )
    line(
        report,
    )

    line(
        report,
        "VIII. CAM KẾT KHẢO SÁT",
    )
    line(
        report,
        "-" * 90,
    )
    line(
        report,
        " - Không thay đổi database.",
    )
    line(
        report,
        " - Không thay đổi source/template.",
    )
    line(
        report,
        " - Không tự tạo dữ liệu.",
    )
    line(
        report,
        " - Chỉ tạo hai file báo cáo trong exports.",
    )

    REPORT_TXT.write_text(
        "\n".join(report),
        encoding="utf-8-sig",
    )

    with MATRIX_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "nhom",
                "ten_nhom",
                "trang_thai_so_bo",
                "bang_db_hang_dau",
                "source_hang_dau",
                "so_bang_db_lien_quan",
                "so_source_lien_quan",
                "so_route_lien_quan",
                "nguon_can_co",
            ],
        )

        writer.writeheader()
        writer.writerows(
            matrix_rows
        )

    print(
        "KHẢO SÁT HOÀN THÀNH."
    )
    print()
    print(
        "Báo cáo TXT:"
    )
    print(
        REPORT_TXT
    )
    print()
    print(
        "Ma trận CSV:"
    )
    print(
        MATRIX_CSV
    )
    print()
    print(
        "Database/source: KHÔNG THAY ĐỔI."
    )
    print(
        "integrity_check:",
        integrity,
    )
    print(
        "foreign_key_check:",
        len(fk_rows),
        "lỗi",
    )
    print()
    print(
        "=" * 126
    )
    print(
        "BÀI 13B-11.14.4 KHẢO SÁT THÀNH CÔNG"
    )
    print(
        "=" * 126
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )
    except Exception:
        traceback.print_exc()
        print()
        print(
            "KHẢO SÁT GẶP LỖI."
        )
        print(
            "Bài này chỉ đọc nên database/source "
            "không bị thay đổi."
        )
        raise
