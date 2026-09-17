# -*- coding: utf-8 -*-
"""
BÀI 13B-11.15.2.4.9.1A.1
KIỂM THỬ THỰC TẾ - TỰ CHỌN NĂM HỌC CÓ DỮ LIỆU

MỤC TIÊU:
- Gọi đúng exporter thực tế đang dùng trong phần mềm.
- Kiểm thử 2 địa bàn:
    1) Xã Quế Phong - xã đặc biệt khó khăn.
    2) Một xã/phường bình thường có nhiều dữ liệu nhất trong năm học chọn.
- Xuất và kiểm tra 4 biểu mỗi địa bàn:
    MN-02, TH-02, XMC-4, THCS-TK.
- Kiểm tra các ô:
    MN-02   R7
    TH-02   T8
    XMC-4   R8
    THCS-TK F8, G8, R8
- Database ở chế độ query_only; không UPDATE/INSERT/DELETE.
- Không sửa source, menu, route, template.
- Giữ lại 8 file Excel kiểm thử và 1 báo cáo TXT.

NÊN DỪNG UVICORN TRƯỚC KHI CHẠY.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
import sqlite3
import sys
import traceback
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import Any

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
DB_PATH = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = EXPORTS / f"kiem_thu_bai_13b_11_15_2_4_9_1a_1_{STAMP}"
REPORT = OUT_DIR / f"bao_cao_kiem_thu_4_9_1a_1_{STAMP}.txt"

SPECIAL_CODE = "16738"  # Xã Quế Phong
EXPECTED_TOTAL_COMMUNES = 130
EXPECTED_SPECIAL_COMMUNES = 51

REPORTS = (
    {
        "code": "PCGD_MN_02_2025",
        "short": "MN-02",
        "exporter": "mn",
        "cells": ("R7",),
    },
    {
        "code": "PCGD_TH_02_2025",
        "short": "TH-02",
        "exporter": "xmc",
        "cells": ("T8",),
    },
    {
        "code": "PCGD_XMC_4_2025",
        "short": "XMC-4",
        "exporter": "xmc",
        "cells": ("R8",),
    },
    {
        "code": "PCGD_THCS_TK_2025",
        "short": "THCS-TK",
        "exporter": "xmc",
        "cells": ("F8", "G8", "R8"),
    },
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sqlite_state() -> dict[str, Any]:
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        total = int(conn.execute("SELECT COUNT(*) FROM communes").fetchone()[0])
        special = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM communes
                WHERE COALESCE(is_special_difficulty_area, 0) = 1
                """
            ).fetchone()[0]
        )
        return {
            "integrity": integrity,
            "fk_count": fk_count,
            "total": total,
            "special": special,
        }
    finally:
        conn.close()


def make_request():
    from starlette.requests import Request

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "server": ("127.0.0.1", 80),
        "client": ("127.0.0.1", 0),
        "scheme": "http",
        "method": "GET",
        "root_path": "",
        "path": "/kiem-thu-bai-4-9-1a",
        "raw_path": b"/kiem-thu-bai-4-9-1a",
        "query_string": b"",
        "headers": [],
        "auth_user": {
            "id": 0,
            "username": "kiem_thu_4_9_1a",
            "full_name": "Kiểm thử Bài 4.9.1A",
            "role_code": "ADMIN",
            "commune_id": None,
            "school_id": None,
        },
    }
    return Request(scope)


async def response_to_bytes(response) -> bytes:
    body = getattr(response, "body", None)
    if isinstance(body, (bytes, bytearray)) and body:
        return bytes(body)

    iterator = getattr(response, "body_iterator", None)
    if iterator is None:
        raise RuntimeError(
            f"Response {type(response).__name__} không có body/body_iterator."
        )

    chunks: list[bytes] = []
    async for chunk in iterator:
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        chunks.append(bytes(chunk))
    return b"".join(chunks)


def call_exporter(
    func,
    *,
    report_type: str,
    db,
    request,
    school_year,
    commune,
):
    """
    Gọi exporter bằng tên tham số thực tế.
    Nếu source thay chữ ký ngoài các tham số đã biết thì dừng, không đoán.
    """
    values = {
        "report_type": report_type,
        "db": db,
        "request": request,
        "school_year": school_year,
        "selected_commune_id": int(commune.id),
        "selected_school_id": None,
        "scope_label": str(commune.name),
    }

    sig = inspect.signature(func)
    kwargs = {}

    for name, param in sig.parameters.items():
        if name in values:
            kwargs[name] = values[name]
            continue

        if param.default is not inspect.Parameter.empty:
            continue

        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        raise RuntimeError(
            f"Exporter {func.__name__} có tham số bắt buộc chưa biết: {name}. "
            "Dừng để tránh gọi sai source."
        )

    return func(**kwargs)


def normalized_value(value: Any):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if value is None:
        return None
    return " ".join(str(value).strip().split())


def allowed_for(report_short: str, cell: str, value: Any) -> bool:
    v = normalized_value(value)

    status = {"Không đạt", "Chưa đủ dữ liệu"}

    if report_short == "MN-02" and cell == "R7":
        return v in {"Đạt", *status}

    if report_short == "TH-02" and cell == "T8":
        return v in {1, 2, 3, *status}

    if report_short == "XMC-4" and cell == "R8":
        return v in {1, 2, *status}

    if report_short == "THCS-TK":
        if cell == "F8":
            return v in {1, 2, 3, *status}
        if cell == "G8":
            return v in {1, 2, *status}
        if cell == "R8":
            return v in {1, 2, 3, *status}

    return False


def safe_name(value: str) -> str:
    text = str(value or "")
    for old, new in (
        ("\\", "_"),
        ("/", "_"),
        (":", "_"),
        ("*", "_"),
        ("?", "_"),
        ('"', "_"),
        ("<", "_"),
        (">", "_"),
        ("|", "_"),
    ):
        text = text.replace(old, new)
    return "_".join(text.split())[:100] or "dia_ban"


def all_school_years(db):
    from sqlalchemy import select
    from app.models import SchoolYear

    return list(
        db.scalars(
            select(SchoolYear)
            .order_by(SchoolYear.code.desc(), SchoolYear.id.desc())
        ).all()
    )


def choose_year_with_real_data(db):
    """
    Chọn năm học thực tế:
    - Ưu tiên năm mà Quế Phong có dữ liệu
      VÀ ít nhất một xã/phường bình thường cũng có dữ liệu.
    - Trong các năm đạt điều kiện, ưu tiên năm mới hơn.
    - Không dùng cờ is_active để tránh tự rơi vào năm mới chưa có dữ liệu.
    """
    from sqlalchemy import select
    from app.models import Commune

    special = db.scalar(
        select(Commune).where(
            Commune.code == SPECIAL_CODE,
            Commune.is_active.is_(True),
        )
    )
    if special is None:
        raise RuntimeError(
            f"Không tìm thấy xã mã {SPECIAL_CODE} (Quế Phong)."
        )

    normals = list(
        db.scalars(
            select(Commune)
            .where(
                Commune.is_active.is_(True),
                Commune.is_special_difficulty_area == 0,
            )
            .order_by(Commune.name.asc(), Commune.id.asc())
        ).all()
    )
    if not normals:
        raise RuntimeError("Không tìm thấy xã/phường bình thường.")

    years = all_school_years(db)
    if not years:
        raise RuntimeError("Database chưa có năm học.")

    scan = []

    for year in years:
        special_count = commune_data_count(
            db,
            int(special.id),
            int(year.id),
        )

        best_normal = None
        best_normal_count = -1

        for commune in normals:
            count = commune_data_count(
                db,
                int(commune.id),
                int(year.id),
            )
            if count > best_normal_count:
                best_normal = commune
                best_normal_count = count

        scan.append(
            {
                "year": year,
                "special_count": int(special_count),
                "normal": best_normal,
                "normal_count": int(max(best_normal_count, 0)),
            }
        )

    viable = [
        item
        for item in scan
        if item["special_count"] > 0
        and item["normal_count"] > 0
        and item["normal"] is not None
    ]

    if viable:
        # years đã sort mới -> cũ, nên lấy năm đầu tiên đủ dữ liệu.
        return viable[0], scan

    # Không có năm nào đồng thời đủ dữ liệu 2 nhóm.
    # Trả scan để main in bảng và dừng có kiểm soát.
    return None, scan


def commune_data_count(db, commune_id: int, school_year_id: int) -> int:
    """
    Đếm bản ghi năm học trong các phiếu thuộc xã để ưu tiên xã thường có dữ liệu.
    Nếu schema khác dự kiến, caller sẽ fallback an toàn.
    """
    from sqlalchemy import text

    value = db.execute(
        text(
            """
            SELECT COUNT(spr.id)
            FROM survey_person_year_records AS spr
            JOIN survey_forms AS sf
              ON sf.id = spr.survey_form_id
            JOIN survey_batches AS sb
              ON sb.id = sf.survey_batch_id
            WHERE sb.commune_id = :commune_id
              AND spr.school_year_id = :school_year_id
            """
        ),
        {
            "commune_id": int(commune_id),
            "school_year_id": int(school_year_id),
        },
    ).scalar_one()
    return int(value or 0)


def choose_communes(db, school_year):
    from sqlalchemy import select
    from app.models import Commune

    special = db.scalar(
        select(Commune).where(
            Commune.code == SPECIAL_CODE,
            Commune.is_active.is_(True),
        )
    )
    if special is None:
        raise RuntimeError(
            f"Không tìm thấy xã mã {SPECIAL_CODE} (Quế Phong)."
        )

    if int(getattr(special, "is_special_difficulty_area", 0) or 0) != 1:
        raise RuntimeError(
            f"{special.name} / {special.code} không có cờ ĐBKK=1."
        )

    normals = list(
        db.scalars(
            select(Commune)
            .where(
                Commune.is_active.is_(True),
                Commune.is_special_difficulty_area == 0,
            )
            .order_by(Commune.name.asc(), Commune.id.asc())
        ).all()
    )

    if not normals:
        raise RuntimeError("Không tìm thấy xã/phường bình thường.")

    scored: list[tuple[int, str, Any]] = []
    count_query_ok = True

    for item in normals:
        try:
            count = commune_data_count(
                db,
                int(item.id),
                int(school_year.id),
            )
        except Exception:
            count_query_ok = False
            break
        scored.append((count, str(item.name), item))

    if count_query_ok and scored:
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        normal = scored[0][2]
        normal_count = scored[0][0]
    else:
        normal = normals[0]
        normal_count = None

    try:
        special_count = commune_data_count(
            db,
            int(special.id),
            int(school_year.id),
        )
    except Exception:
        special_count = None

    return (
        {
            "kind": "DBKK",
            "commune": special,
            "data_count": special_count,
        },
        {
            "kind": "BINH_THUONG",
            "commune": normal,
            "data_count": normal_count,
        },
    )


def verify_b491_source() -> None:
    mn_path = APP / "pcgd_mn_report_builders_v1.py"
    xmc_path = APP / "pcgd_xmc_report_builders_v1.py"

    mn = mn_path.read_text(encoding="utf-8-sig")
    xmc = xmc_path.read_text(encoding="utf-8-sig")

    required_mn = (
        "BAI_13B_11_15_2_4_9_1_MN_HELPERS_START",
        "def _b491_apply_mn_conclusion(",
        'ws["R7"]',
        "is_special_difficulty_area",
    )
    required_xmc = (
        "BAI_13B_11_15_2_4_9_1_XMC_HELPERS_START",
        "def _b491_apply_xmc_conclusions(",
        'ws["T8"]',
        'ws["F8"]',
        'ws["G8"]',
        'ws["R8"]',
        "is_special_difficulty_area",
    )

    missing = [
        f"MN:{token}" for token in required_mn if token not in mn
    ] + [
        f"XMC:{token}" for token in required_xmc if token not in xmc
    ]

    if missing:
        raise RuntimeError(
            "Source chưa đủ dấu vết Bài 4.9.1 V3: "
            + "; ".join(missing)
        )


def verify_special_helpers(mn_module, xmc_module, db, commune, expected: bool):
    results = {}

    if hasattr(mn_module, "_b491_mn_special_difficult"):
        got = bool(
            mn_module._b491_mn_special_difficult(
                db,
                int(commune.id),
            )
        )
        results["mn_helper"] = got
        if got != expected:
            raise RuntimeError(
                f"MN helper đọc cờ ĐBKK={got}, dự kiến {expected} "
                f"cho {commune.name}."
            )

    if hasattr(xmc_module, "_b491_special_difficult"):
        got = bool(
            xmc_module._b491_special_difficult(
                db,
                int(commune.id),
            )
        )
        results["xmc_helper"] = got
        if got != expected:
            raise RuntimeError(
                f"TH/XMC/THCS helper đọc cờ ĐBKK={got}, dự kiến {expected} "
                f"cho {commune.name}."
            )

    return results


def inspect_workbook(data: bytes, report_short: str, cells: tuple[str, ...]):
    from openpyxl import load_workbook

    if not data.startswith(b"PK"):
        raise RuntimeError(
            f"{report_short}: dữ liệu trả về không phải XLSX hợp lệ."
        )

    wb = load_workbook(BytesIO(data), data_only=False)
    try:
        ws = wb[wb.sheetnames[0]]
        values = {cell: normalized_value(ws[cell].value) for cell in cells}

        invalid = [
            f"{cell}={values[cell]!r}"
            for cell in cells
            if not allowed_for(report_short, cell, values[cell])
        ]

        if invalid:
            raise RuntimeError(
                f"{report_short}: ô kết luận không hợp lệ: "
                + ", ".join(invalid)
            )

        return ws.title, values
    finally:
        wb.close()


def format_cell_values(values: dict[str, Any]) -> str:
    return ", ".join(
        f"{cell}={value!r}"
        for cell, value in values.items()
    )


def run() -> int:
    print("=" * 104)
    print(
        "BÀI 13B-11.15.2.4.9.1A - "
        "KIỂM THỬ THỰC TẾ KẾT LUẬN 4 NHÓM"
    )
    print("=" * 104)
    print()

    if not DB_PATH.exists():
        print(f"[LỖI] Không tìm thấy database: {DB_PATH}")
        return 1

    sys.path.insert(0, str(PROJECT))
    old_cwd = Path.cwd()

    before_hash = sha256_file(DB_PATH)
    before = sqlite_state()
    rows: list[str] = []

    try:
        os.chdir(PROJECT)

        if before["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check trước kiểm thử != ok")
        if before["fk_count"] != 0:
            raise RuntimeError(
                f"foreign_key_check trước kiểm thử có {before['fk_count']} lỗi."
            )
        if before["total"] != EXPECTED_TOTAL_COMMUNES:
            raise RuntimeError(
                f"Tổng communes={before['total']}, "
                f"không phải {EXPECTED_TOTAL_COMMUNES}."
            )
        if before["special"] != EXPECTED_SPECIAL_COMMUNES:
            raise RuntimeError(
                f"Cờ ĐBKK={before['special']}, "
                f"không phải {EXPECTED_SPECIAL_COMMUNES}."
            )

        print(
            f"[1/7] Database: {before['total']} xã/phường; "
            f"ĐBKK={before['special']}; integrity=ok."
        )

        verify_b491_source()
        print("[2/7] Source Bài 4.9.1 V3: ĐỦ marker.")

        from sqlalchemy import text
        from app.database import SessionLocal
        import app.pcgd_mn_report_builders_v1 as mn_builder
        import app.pcgd_xmc_report_builders_v1 as xmc_builder

        if not hasattr(mn_builder, "export_mn_report"):
            raise RuntimeError("Không có export_mn_report.")
        if not hasattr(xmc_builder, "export_additional_report"):
            raise RuntimeError("Không có export_additional_report.")

        request = make_request()
        OUT_DIR.mkdir(parents=True, exist_ok=False)

        db = SessionLocal()
        try:
            # Chặn mọi thao tác ghi trên connection kiểm thử.
            db.execute(text("PRAGMA query_only = ON"))

            chosen, year_scan = choose_year_with_real_data(db)

            print("[3/7] Quét dữ liệu theo năm học:")
            for item in year_scan:
                year = item["year"]
                normal = item["normal"]
                normal_name = (
                    normal.name
                    if normal is not None
                    else "(không có)"
                )
                print(
                    f"      - {year.code} (ID={year.id}): "
                    f"Quế Phong={item['special_count']} | "
                    f"xã thường tốt nhất={normal_name}: "
                    f"{item['normal_count']}"
                )

            if chosen is None:
                raise RuntimeError(
                    "Không có năm học nào đồng thời có dữ liệu "
                    "ở Xã Quế Phong và ít nhất 1 xã/phường bình thường. "
                    "Chưa thể kiểm thử nhánh ngưỡng bằng dữ liệu thực."
                )

            school_year = chosen["year"]

            special_info, _normal_auto = choose_communes(db, school_year)
            normal_info = {
                "kind": "BINH_THUONG",
                "commune": chosen["normal"],
                "data_count": chosen["normal_count"],
            }

            print(
                f"[4/7] Chọn năm học có dữ liệu: "
                f"{school_year.code} (ID={school_year.id})."
            )
            print("      Hai địa bàn:")
            for info in (special_info, normal_info):
                c = info["commune"]
                count_text = (
                    str(info["data_count"])
                    if info["data_count"] is not None
                    else "không xác định"
                )
                print(
                    f"      - {info['kind']}: "
                    f"ID={c.id}, mã={c.code}, {c.name}, "
                    f"bản ghi năm học={count_text}"
                )

            all_tests: list[dict[str, Any]] = []

            for info in (special_info, normal_info):
                commune = info["commune"]
                expected_special = info["kind"] == "DBKK"

                flag_db = bool(
                    int(
                        getattr(
                            commune,
                            "is_special_difficulty_area",
                            0,
                        )
                        or 0
                    )
                )
                if flag_db != expected_special:
                    raise RuntimeError(
                        f"{commune.name}: cờ DB={flag_db}, "
                        f"dự kiến={expected_special}."
                    )

                helper_flags = verify_special_helpers(
                    mn_builder,
                    xmc_builder,
                    db,
                    commune,
                    expected_special,
                )

                commune_dir = (
                    OUT_DIR
                    / f"{info['kind']}_{safe_name(commune.name)}"
                )
                commune_dir.mkdir(parents=True, exist_ok=True)

                for spec in REPORTS:
                    exporter = (
                        mn_builder.export_mn_report
                        if spec["exporter"] == "mn"
                        else xmc_builder.export_additional_report
                    )

                    response = call_exporter(
                        exporter,
                        report_type=spec["code"],
                        db=db,
                        request=request,
                        school_year=school_year,
                        commune=commune,
                    )

                    data = asyncio.run(
                        response_to_bytes(response)
                    )

                    if len(data) < 1000:
                        raise RuntimeError(
                            f"{commune.name} / {spec['short']}: "
                            f"file chỉ có {len(data)} bytes."
                        )

                    xlsx_path = (
                        commune_dir
                        / (
                            f"{spec['short']}_"
                            f"{school_year.code}_"
                            f"{safe_name(commune.name)}.xlsx"
                        )
                    )
                    xlsx_path.write_bytes(data)

                    sheet, values = inspect_workbook(
                        data,
                        spec["short"],
                        spec["cells"],
                    )

                    test = {
                        "kind": info["kind"],
                        "commune_id": int(commune.id),
                        "commune_code": str(commune.code),
                        "commune_name": str(commune.name),
                        "special": expected_special,
                        "data_count": info["data_count"],
                        "report": spec["short"],
                        "sheet": sheet,
                        "values": values,
                        "file": str(xlsx_path),
                        "helper_flags": helper_flags,
                    }
                    all_tests.append(test)

                    print(
                        f"      [OK] {info['kind']} / "
                        f"{spec['short']} / "
                        f"{format_cell_values(values)}"
                    )

            print("[5/7] Đã xuất đủ 8 file Excel kiểm thử.")

            # Báo cáo chi tiết.
            rows.extend(
                [
                    "=" * 104,
                    "BÀI 13B-11.15.2.4.9.1A.1 - KẾT QUẢ KIỂM THỬ THỰC TẾ",
                    "=" * 104,
                    "",
                    f"Năm học: {school_year.code} (ID={school_year.id})",
                    f"Database: {DB_PATH}",
                    f"Địa bàn ĐBKK cố định: {special_info['commune'].name}",
                    f"Địa bàn bình thường: {normal_info['commune'].name}",
                    "",
                ]
            )

            for test in all_tests:
                rows.append(
                    f"[{test['kind']}] "
                    f"{test['commune_name']} "
                    f"(ID={test['commune_id']}, mã={test['commune_code']}) "
                    f"| {test['report']} "
                    f"| {format_cell_values(test['values'])}"
                )
                rows.append(
                    f"    ĐBKK={test['special']} "
                    f"| helper={test['helper_flags']} "
                    f"| sheet={test['sheet']}"
                )
                rows.append(
                    f"    File: {test['file']}"
                )

            rows.extend(
                [
                    "",
                    "QUY TẮC ĐỌC KẾT QUẢ:",
                    " - 'Chưa đủ dữ liệu' = HỢP LỆ khi thiếu chỉ tiêu bắt buộc.",
                    " - Không được tự suy đoán thành Đạt/Mức độ khi thiếu dữ liệu.",
                    " - MN-02: R7 chỉ được Đạt / Không đạt / Chưa đủ dữ liệu.",
                    " - TH-02: T8 chỉ được 1/2/3 / Không đạt / Chưa đủ dữ liệu.",
                    " - XMC-4: R8 chỉ được 1/2 / Không đạt / Chưa đủ dữ liệu.",
                    " - THCS-TK: F8=TH; G8=XMC; R8=THCS theo tập giá trị hợp lệ.",
                    "",
                ]
            )

        finally:
            try:
                db.rollback()
            except Exception:
                pass
            db.close()

        after = sqlite_state()
        after_hash = sha256_file(DB_PATH)

        if after["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check sau kiểm thử != ok")
        if after["fk_count"] != 0:
            raise RuntimeError(
                f"foreign_key_check sau kiểm thử có {after['fk_count']} lỗi."
            )
        if before != after:
            raise RuntimeError(
                f"Trạng thái database trước/sau khác nhau: {before} -> {after}"
            )
        if before_hash != after_hash:
            raise RuntimeError(
                "SHA256 file phocap.db thay đổi trong lúc kiểm thử. "
                "Nếu Uvicorn còn chạy, hãy dừng server rồi kiểm thử lại."
            )

        print(
            "[6/7] Database trước/sau: không thay đổi; "
            "SHA256 giữ nguyên."
        )

        rows.extend(
            [
                "AN TOÀN DATABASE:",
                f" - Trước: {before}",
                f" - Sau  : {after}",
                f" - SHA256 trước: {before_hash}",
                f" - SHA256 sau  : {after_hash}",
                " - Kết luận: KHÔNG THAY ĐỔI DATABASE.",
                "",
                "KẾT LUẬN: BÀI 4.9.1A.1 ĐẠT KIỂM THỬ TRÊN NĂM CÓ DỮ LIỆU.",
            ]
        )

        REPORT.write_text(
            "\n".join(rows),
            encoding="utf-8-sig",
        )

        print(f"[7/7] Báo cáo: {REPORT}")
        print()
        print("=" * 104)
        print("BÀI 4.9.1A.1 - KIỂM THỬ THỰC TẾ HOÀN THÀNH.")
        print(f"Thư mục 8 file Excel: {OUT_DIR}")
        print("Database: KHÔNG THAY ĐỔI.")
        print("=" * 104)
        return 0

    except Exception as exc:
        print()
        print("=" * 104)
        print("[LỖI] BÀI 4.9.1A.1 CHƯA ĐẠT")
        print(str(exc))
        print("=" * 104)

        try:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            error_report = OUT_DIR / f"loi_kiem_thu_4_9_1a_1_{STAMP}.txt"
            error_report.write_text(
                (
                    f"Lỗi: {exc}\n\n"
                    + traceback.format_exc()
                ),
                encoding="utf-8-sig",
            )
            print(f"Chi tiết lỗi: {error_report}")
        except Exception:
            pass

        print(
            "Script kiểm thử không có lệnh UPDATE/INSERT/DELETE "
            "và bật PRAGMA query_only."
        )
        return 1

    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    raise SystemExit(run())
