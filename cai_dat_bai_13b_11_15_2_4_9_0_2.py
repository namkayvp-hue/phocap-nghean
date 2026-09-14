# -*- coding: utf-8 -*-
"""
BÀI 13B-11.15.2.4.9.0.2
Đối chiếu 51 xã khu vực III (xã đặc biệt khó khăn) với danh mục xã/phường trong phocap.db.

NGUYÊN TẮC AN TOÀN
- CHỈ ĐỌC SQLite, tuyệt đối không UPDATE/INSERT/DELETE.
- Mở database bằng URI mode=ro và bật PRAGMA query_only=ON.
- Không sửa cấu trúc database.
- Tự dò bảng/cột chứa tên xã/phường dựa trên số lượng tên khớp.
- Xuất báo cáo TXT và CSV để kiểm tra trước khi làm bước 4.9.0.3.

Nguồn danh sách:
- QĐ 60/QĐ-BDTTG ngày 29/01/2026, phụ lục tỉnh Nghệ An.
- Danh sách 51 xã đặc biệt khó khăn tỉnh Nghệ An do người dùng cung cấp.
"""

from __future__ import annotations

import csv
import difflib
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


# ============================================================
# 1. DANH SÁCH 51 XÃ KHU VỰC III / ĐẶC BIỆT KHÓ KHĂN
# ============================================================

SPECIAL_COMMUNES: List[str] = [
    "Mường Xén",
    "Hữu Kiệm",
    "Nậm Cắn",
    "Chiêu Lưu",
    "Na Loi",
    "Mường Típ",
    "Na Ngoi",
    "Mỹ Lý",
    "Bắc Lý",
    "Keng Đu",
    "Huồi Tụ",
    "Mường Lống",
    "Tương Dương",
    "Tam Quang",
    "Tam Thái",
    "Lượng Minh",
    "Yên Na",
    "Yên Hòa",
    "Nga My",
    "Hữu Khuông",
    "Nhôn Mai",
    "Con Cuông",
    "Môn Sơn",
    "Châu Khê",
    "Cam Phục",
    "Mậu Thạch",
    "Bình Chuẩn",
    "Anh Sơn Đông",
    "Thành Bình Thọ",
    "Sơn Lâm",
    "Tiên Đồng",
    "Giai Xuân",
    "Nghĩa Hành",
    "Quế Phong",
    "Thông Thụ",
    "Tiền Phong",
    "Mường Quảng",
    "Tri Lễ",
    "Quỳ Châu",
    "Châu Tiến",
    "Hùng Chân",
    "Châu Bình",
    "Quỳ Hợp",
    "Minh Hợp",
    "Châu Lộc",
    "Mường Ham",
    "Tam Hợp",
    "Mường Chọng",
    "Châu Hồng",
    "Nghĩa Thọ",
    "Quỳnh Thắng",
]

EXPECTED_COUNT = 51


# ============================================================
# 2. CHUẨN HÓA TÊN
# ============================================================

ADMIN_PREFIX_RE = re.compile(
    r"^\s*(xã|xa|phường|phuong|thị\s*trấn|thi\s*tran|đặc\s*khu|dac\s*khu)\s+",
    flags=re.IGNORECASE,
)

NON_WORD_RE = re.compile(r"[^0-9a-zA-ZÀ-ỹĐđ]+", flags=re.UNICODE)


def tidy_text(value: object) -> str:
    """Chuẩn hóa khoảng trắng nhưng vẫn giữ nguyên dấu tiếng Việt."""
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def strip_admin_prefix(value: object) -> str:
    """Bỏ tiền tố Xã/Phường/Thị trấn/Đặc khu để so tên địa danh."""
    text = tidy_text(value)
    while True:
        new_text = ADMIN_PREFIX_RE.sub("", text).strip()
        if new_text == text:
            break
        text = new_text
    return text


def accentless(value: object) -> str:
    """Đưa về chữ thường không dấu để phục vụ so sánh an toàn."""
    text = strip_admin_prefix(value).lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def exact_key(value: object) -> str:
    """
    Khóa 'khớp chính xác nghiệp vụ':
    - bỏ tiền tố loại đơn vị,
    - giữ nguyên dấu,
    - không phân biệt hoa/thường,
    - gộp khoảng trắng.
    """
    return strip_admin_prefix(value).casefold()


# ============================================================
# 3. TÌM DATABASE
# ============================================================

def candidate_roots() -> List[Path]:
    roots: List[Path] = []

    # Thư mục đang chạy script
    try:
        roots.append(Path.cwd())
    except Exception:
        pass

    # Thư mục chứa script
    try:
        roots.append(Path(__file__).resolve().parent)
    except Exception:
        pass

    # Đường dẫn dự án chuẩn
    roots.append(Path(r"C:\PhoCap"))

    # Loại trùng
    result: List[Path] = []
    seen = set()
    for root in roots:
        key = str(root).lower()
        if key not in seen:
            seen.add(key)
            result.append(root)
    return result


def find_database() -> Path:
    """
    Ưu tiên phocap.db. Nếu không thấy, dò các file .db/.sqlite/.sqlite3
    trong dự án và chọn file có tên phù hợp nhất.
    """
    direct_names = [
        "phocap.db",
        "database.db",
        "app.db",
        "data.db",
    ]

    for root in candidate_roots():
        if not root.exists():
            continue
        for name in direct_names:
            p = root / name
            if p.is_file():
                return p.resolve()

    found: List[Path] = []
    for root in candidate_roots():
        if not root.exists():
            continue
        try:
            for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
                found.extend(root.rglob(pattern))
        except Exception:
            continue

    # Loại backup càng nhiều càng tốt
    filtered = [
        p for p in found
        if p.is_file()
        and "backup" not in str(p).lower()
        and ".venv" not in str(p).lower()
        and "__pycache__" not in str(p).lower()
    ]

    if not filtered:
        raise FileNotFoundError(
            "Không tìm thấy file SQLite (.db/.sqlite/.sqlite3) trong C:\\PhoCap "
            "hoặc thư mục đang chạy."
        )

    def score_path(p: Path) -> Tuple[int, int]:
        name = p.name.lower()
        score = 0
        if name == "phocap.db":
            score += 1000
        if "phocap" in name:
            score += 500
        if "data" in name or "database" in name:
            score += 100
        # Ưu tiên file gần thư mục gốc hơn
        depth = len(p.parts)
        return (score, -depth)

    filtered.sort(key=score_path, reverse=True)
    return filtered[0].resolve()


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """
    Mở SQLite ở chế độ chỉ đọc thật sự.
    Không thể ghi dữ liệu qua connection này.
    """
    uri = db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 4. DÒ BẢNG/CỘT DANH MỤC XÃ
# ============================================================

TABLE_PRIORITY = {
    "communes": 100,
    "commune": 95,
    "wards": 90,
    "ward": 85,
    "administrative_units": 80,
    "administrative_unit": 75,
    "xa": 70,
    "phuong_xa": 70,
    "don_vi_hanh_chinh": 70,
}

NAME_COLUMN_PRIORITY = {
    "name": 100,
    "ten": 95,
    "ten_xa": 95,
    "commune_name": 95,
    "ward_name": 90,
    "unit_name": 85,
    "full_name": 80,
}

CODE_COLUMN_NAMES = [
    "code",
    "ma",
    "ma_xa",
    "commune_code",
    "ward_code",
    "unit_code",
]

ID_COLUMN_NAMES = [
    "id",
    "commune_id",
    "ward_id",
    "unit_id",
]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def list_user_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(r["name"]) for r in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> List[sqlite3.Row]:
    return conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()


def text_like_columns(columns: Sequence[sqlite3.Row]) -> List[str]:
    result: List[str] = []
    for col in columns:
        name = str(col["name"])
        col_type = (str(col["type"] or "")).upper()

        # SQLite thường không khai báo type chặt. Cho phép TEXT/VARCHAR/CHAR
        # và cả cột không khai báo type.
        if (
            "TEXT" in col_type
            or "CHAR" in col_type
            or "CLOB" in col_type
            or "VARCHAR" in col_type
            or col_type == ""
        ):
            result.append(name)
    return result


def safe_values(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    max_rows: int = 10000,
) -> List[str]:
    sql = (
        f"SELECT {quote_ident(column)} AS v "
        f"FROM {quote_ident(table)} "
        f"WHERE {quote_ident(column)} IS NOT NULL "
        f"LIMIT ?"
    )
    rows = conn.execute(sql, (max_rows,)).fetchall()
    return [tidy_text(r["v"]) for r in rows if tidy_text(r["v"])]


def detect_commune_source(
    conn: sqlite3.Connection,
) -> Tuple[str, str, int, List[Tuple[int, str, str, int]]]:
    """
    Dò bảng và cột tên bằng số lượng 51 tên nguồn khớp.
    Trả về: table, name_column, best_match_count, bảng xếp hạng.
    """
    target_keys = {accentless(x) for x in SPECIAL_COMMUNES}

    candidates: List[Tuple[int, str, str, int]] = []

    for table in list_user_tables(conn):
        try:
            columns = table_columns(conn, table)
            text_cols = text_like_columns(columns)
        except Exception:
            continue

        for col in text_cols:
            try:
                values = safe_values(conn, table, col)
            except Exception:
                continue

            if not values:
                continue

            value_keys = {accentless(v) for v in values if accentless(v)}
            matches = len(target_keys & value_keys)

            table_bonus = TABLE_PRIORITY.get(table.lower(), 0)
            col_bonus = NAME_COLUMN_PRIORITY.get(col.lower(), 0)

            # Match count là tiêu chí chính.
            score = matches * 10000 + table_bonus * 10 + col_bonus

            candidates.append((score, table, col, matches))

    if not candidates:
        raise RuntimeError("Không tìm thấy cột văn bản nào để dò danh mục xã/phường.")

    candidates.sort(reverse=True)
    best_score, best_table, best_col, best_matches = candidates[0]

    if best_matches == 0:
        raise RuntimeError(
            "Đã đọc database nhưng không tìm thấy tên nào trong 51 xã ở các cột văn bản. "
            "Cần xem lại cấu trúc database."
        )

    return best_table, best_col, best_matches, candidates[:10]


def choose_column(
    columns: Sequence[sqlite3.Row],
    preferred_names: Sequence[str],
) -> Optional[str]:
    by_lower = {str(c["name"]).lower(): str(c["name"]) for c in columns}
    for name in preferred_names:
        if name.lower() in by_lower:
            return by_lower[name.lower()]
    return None


def fetch_commune_rows(
    conn: sqlite3.Connection,
    table: str,
    name_col: str,
) -> Tuple[List[Dict[str, object]], Optional[str], Optional[str]]:
    cols = table_columns(conn, table)
    id_col = choose_column(cols, ID_COLUMN_NAMES)
    code_col = choose_column(cols, CODE_COLUMN_NAMES)

    selected = []
    if id_col:
        selected.append(f"{quote_ident(id_col)} AS _id")
    else:
        selected.append("rowid AS _id")

    if code_col:
        selected.append(f"{quote_ident(code_col)} AS _code")
    else:
        selected.append("NULL AS _code")

    selected.append(f"{quote_ident(name_col)} AS _name")

    sql = f"SELECT {', '.join(selected)} FROM {quote_ident(table)}"
    rows = conn.execute(sql).fetchall()

    result: List[Dict[str, object]] = []
    for r in rows:
        name = tidy_text(r["_name"])
        if not name:
            continue
        result.append(
            {
                "id": r["_id"],
                "code": r["_code"],
                "name": name,
            }
        )
    return result, id_col, code_col


# ============================================================
# 5. ĐỐI CHIẾU 51 XÃ
# ============================================================

def build_indexes(rows: Sequence[Dict[str, object]]):
    exact_index: Dict[str, List[Dict[str, object]]] = {}
    norm_index: Dict[str, List[Dict[str, object]]] = {}

    for row in rows:
        name = row["name"]
        ek = exact_key(name)
        nk = accentless(name)

        exact_index.setdefault(ek, []).append(row)
        norm_index.setdefault(nk, []).append(row)

    return exact_index, norm_index


def nearest_suggestions(
    source_name: str,
    db_rows: Sequence[Dict[str, object]],
    limit: int = 3,
) -> List[str]:
    source_key = accentless(source_name)
    if not source_key:
        return []

    scored: List[Tuple[float, str]] = []
    seen = set()

    for row in db_rows:
        db_name = tidy_text(row["name"])
        db_key = accentless(db_name)
        if not db_key or db_name in seen:
            continue
        seen.add(db_name)

        ratio = difflib.SequenceMatcher(None, source_key, db_key).ratio()
        if ratio >= 0.60:
            scored.append((ratio, db_name))

    scored.sort(reverse=True)
    return [f"{name} ({ratio:.0%})" for ratio, name in scored[:limit]]


def compare_names(
    db_rows: Sequence[Dict[str, object]],
) -> List[Dict[str, object]]:
    exact_index, norm_index = build_indexes(db_rows)

    results: List[Dict[str, object]] = []

    for stt, source_name in enumerate(SPECIAL_COMMUNES, start=1):
        ek = exact_key(source_name)
        nk = accentless(source_name)

        exact_hits = exact_index.get(ek, [])
        norm_hits = norm_index.get(nk, [])

        if len(exact_hits) == 1:
            row = exact_hits[0]
            status = "KHỚP CHÍNH XÁC"
            note = ""
        elif len(exact_hits) > 1:
            row = exact_hits[0]
            status = "TRÙNG/AMBIGUOUS"
            note = f"Có {len(exact_hits)} bản ghi cùng tên nghiệp vụ."
        elif len(norm_hits) == 1:
            row = norm_hits[0]
            status = "CẦN CHUẨN HÓA TÊN"
            note = "Tên khớp sau khi bỏ tiền tố/dấu/ký tự phân cách."
        elif len(norm_hits) > 1:
            row = norm_hits[0]
            status = "TRÙNG/AMBIGUOUS"
            note = f"Có {len(norm_hits)} bản ghi khớp sau chuẩn hóa."
        else:
            row = {"id": "", "code": "", "name": ""}
            status = "KHÔNG TÌM THẤY"
            suggestions = nearest_suggestions(source_name, db_rows)
            note = "; ".join(suggestions) if suggestions else "Không có gợi ý gần."

        results.append(
            {
                "stt": stt,
                "source_name": source_name,
                "status": status,
                "db_id": row.get("id", ""),
                "db_code": row.get("code", ""),
                "db_name": row.get("name", ""),
                "note": note,
            }
        )

    return results


# ============================================================
# 6. XUẤT BÁO CÁO
# ============================================================

def output_dir(db_path: Path) -> Path:
    base = db_path.parent
    folder = base / "ket_qua_doi_chieu"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def summarize(results: Sequence[Dict[str, object]]) -> Dict[str, int]:
    summary = {
        "KHỚP CHÍNH XÁC": 0,
        "CẦN CHUẨN HÓA TÊN": 0,
        "KHÔNG TÌM THẤY": 0,
        "TRÙNG/AMBIGUOUS": 0,
    }
    for row in results:
        status = str(row["status"])
        summary[status] = summary.get(status, 0) + 1
    return summary


def write_csv(path: Path, results: Sequence[Dict[str, object]]) -> None:
    fields = [
        "stt",
        "source_name",
        "status",
        "db_id",
        "db_code",
        "db_name",
        "note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)


def write_txt(
    path: Path,
    db_path: Path,
    table: str,
    name_col: str,
    db_row_count: int,
    results: Sequence[Dict[str, object]],
    ranking: Sequence[Tuple[int, str, str, int]],
) -> None:
    summary = summarize(results)
    matched = summary["KHỚP CHÍNH XÁC"] + summary["CẦN CHUẨN HÓA TÊN"]

    lines: List[str] = []
    lines.append("=" * 88)
    lines.append("BÀI 13B-11.15.2.4.9.0.2 - ĐỐI CHIẾU 51 XÃ ĐẶC BIỆT KHÓ KHĂN")
    lines.append("=" * 88)
    lines.append("")
    lines.append("CHẾ ĐỘ: CHỈ ĐỌC DATABASE - KHÔNG UPDATE")
    lines.append(f"Database: {db_path}")
    lines.append(f"Bảng được nhận diện: {table}")
    lines.append(f"Cột tên xã/phường: {name_col}")
    lines.append(f"Số bản ghi có tên trong bảng: {db_row_count}")
    lines.append("")
    lines.append("TÓM TẮT")
    lines.append(f"- Tổng danh sách nguồn: {len(results)}/{EXPECTED_COUNT}")
    lines.append(f"- KHỚP CHÍNH XÁC: {summary['KHỚP CHÍNH XÁC']}")
    lines.append(f"- CẦN CHUẨN HÓA TÊN: {summary['CẦN CHUẨN HÓA TÊN']}")
    lines.append(f"- KHÔNG TÌM THẤY: {summary['KHÔNG TÌM THẤY']}")
    lines.append(f"- TRÙNG/AMBIGUOUS: {summary['TRÙNG/AMBIGUOUS']}")
    lines.append(f"- Xác định được duy nhất: {matched}/{EXPECTED_COUNT}")
    lines.append("")

    if matched == EXPECTED_COUNT and summary["TRÙNG/AMBIGUOUS"] == 0:
        lines.append("KẾT LUẬN: ĐỦ 51/51. Có thể chuẩn bị Bài 4.9.0.3, nhưng script này KHÔNG ghi DB.")
    else:
        lines.append("KẾT LUẬN: CHƯA ĐỦ 51/51. KHÔNG ĐƯỢC chuyển sang bước ghi cờ database.")

    lines.append("")
    lines.append("-" * 88)
    lines.append("CHI TIẾT")
    lines.append("-" * 88)

    for row in results:
        lines.append(
            f"{int(row['stt']):02d}. {row['source_name']} | "
            f"{row['status']} | DB: {row['db_name']} | "
            f"ID: {row['db_id']} | Mã: {row['db_code']}"
        )
        if row["note"]:
            lines.append(f"    Ghi chú: {row['note']}")

    lines.append("")
    lines.append("-" * 88)
    lines.append("TOP 10 CẶP BẢNG/CỘT ĐƯỢC DÒ")
    lines.append("-" * 88)
    for idx, (_, t, c, m) in enumerate(ranking, start=1):
        lines.append(f"{idx:02d}. {t}.{c} -> khớp chuẩn hóa {m}/51")

    path.write_text("\n".join(lines), encoding="utf-8-sig")


# ============================================================
# 7. MAIN
# ============================================================

def validate_source_list() -> None:
    if len(SPECIAL_COMMUNES) != EXPECTED_COUNT:
        raise RuntimeError(
            f"Danh sách nguồn phải có {EXPECTED_COUNT} xã, "
            f"hiện có {len(SPECIAL_COMMUNES)}."
        )

    normed = [accentless(x) for x in SPECIAL_COMMUNES]
    if len(set(normed)) != EXPECTED_COUNT:
        duplicates = sorted({x for x in normed if normed.count(x) > 1})
        raise RuntimeError(
            "Danh sách nguồn có tên trùng sau chuẩn hóa: "
            + ", ".join(duplicates)
        )


def main() -> int:
    print("=" * 88)
    print("BÀI 13B-11.15.2.4.9.0.2")
    print("ĐỐI CHIẾU 51 XÃ ĐẶC BIỆT KHÓ KHĂN - CHỈ ĐỌC DATABASE")
    print("=" * 88)
    print()

    try:
        validate_source_list()

        db_path = find_database()
        print(f"[OK] Tìm thấy database: {db_path}")
        print("[AN TOÀN] Mở SQLite bằng mode=ro + PRAGMA query_only=ON")

        conn = open_readonly(db_path)
        try:
            table, name_col, detected_matches, ranking = detect_commune_source(conn)
            print(f"[OK] Nhận diện bảng: {table}")
            print(f"[OK] Cột tên xã/phường: {name_col}")
            print(f"[INFO] Số tên nguồn khớp sơ bộ: {detected_matches}/51")

            db_rows, id_col, code_col = fetch_commune_rows(conn, table, name_col)
            print(f"[INFO] Số bản ghi có tên đọc được: {len(db_rows)}")
            print(f"[INFO] Cột ID: {id_col or 'rowid'}")
            print(f"[INFO] Cột mã: {code_col or '(không có/không nhận diện)'}")

            results = compare_names(db_rows)
        finally:
            conn.close()

        summary = summarize(results)
        matched = summary["KHỚP CHÍNH XÁC"] + summary["CẦN CHUẨN HÓA TÊN"]

        print()
        print("-" * 88)
        print("KẾT QUẢ")
        print("-" * 88)
        print(f"KHỚP CHÍNH XÁC       : {summary['KHỚP CHÍNH XÁC']}")
        print(f"CẦN CHUẨN HÓA TÊN   : {summary['CẦN CHUẨN HÓA TÊN']}")
        print(f"KHÔNG TÌM THẤY       : {summary['KHÔNG TÌM THẤY']}")
        print(f"TRÙNG/AMBIGUOUS      : {summary['TRÙNG/AMBIGUOUS']}")
        print(f"XÁC ĐỊNH ĐƯỢC        : {matched}/51")
        print()

        for row in results:
            marker = {
                "KHỚP CHÍNH XÁC": "[OK]",
                "CẦN CHUẨN HÓA TÊN": "[CHUAN HOA]",
                "KHÔNG TÌM THẤY": "[THIEU]",
                "TRÙNG/AMBIGUOUS": "[TRUNG]",
            }.get(str(row["status"]), "[?]")

            print(
                f"{marker:12} {int(row['stt']):02d}. "
                f"{row['source_name']} -> {row['db_name'] or '(không có)'}"
            )
            if row["note"]:
                print(f"{'':15}Ghi chú: {row['note']}")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = output_dir(db_path)
        csv_path = out_dir / f"doi_chieu_51_xa_dbkk_{stamp}.csv"
        txt_path = out_dir / f"doi_chieu_51_xa_dbkk_{stamp}.txt"

        write_csv(csv_path, results)
        write_txt(
            txt_path,
            db_path,
            table,
            name_col,
            len(db_rows),
            results,
            ranking,
        )

        print()
        print(f"[ĐÃ XUẤT] {txt_path}")
        print(f"[ĐÃ XUẤT] {csv_path}")
        print()

        if matched == EXPECTED_COUNT and summary["TRÙNG/AMBIGUOUS"] == 0:
            print("=" * 88)
            print("ĐỦ 51/51 - BƯỚC ĐỐI CHIẾU ĐÃ ĐẠT.")
            print("CHƯA CÓ BẤT KỲ THAY ĐỔI NÀO TRONG DATABASE.")
            print("Hãy gửi cho tôi ảnh màn hình kết quả hoặc file TXT vừa tạo để làm Bài 4.9.0.3.")
            print("=" * 88)
            return 0

        print("=" * 88)
        print("CHƯA ĐỦ 51/51 - DỪNG TẠI ĐÂY, KHÔNG GHI DATABASE.")
        print("Hãy gửi cho tôi ảnh màn hình kết quả hoặc file TXT vừa tạo để xử lý các tên chưa khớp.")
        print("=" * 88)
        return 2

    except Exception as exc:
        print()
        print("=" * 88)
        print("[LỖI] Không hoàn thành được bước đối chiếu.")
        print(str(exc))
        print("Database không bị thay đổi.")
        print("=" * 88)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
