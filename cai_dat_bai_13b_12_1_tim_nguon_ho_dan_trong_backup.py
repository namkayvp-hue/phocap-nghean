from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
EXPORTS = PROJECT / "exports"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"bao_cao_bai_13b_12_1_tim_nguon_ho_dan_trong_backup_{STAMP}.txt"

DB_EXTS = {".db", ".sqlite", ".sqlite3"}
SKIP_PARTS = {".venv", "__pycache__", "node_modules"}

TABLES = (
    "school_years",
    "survey_batches",
    "households",
    "survey_people",
    "survey_forms",
    "survey_person_year_records",
    "historical_datasets",
    "historical_households",
    "historical_people",
)


def emit(lines: list[str], text: str = "") -> None:
    print(text)
    lines.append(text)


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def count_table(conn: sqlite3.Connection, name: str) -> int | None:
    if not table_exists(conn, name):
        return None
    return int(conn.execute(f"SELECT COUNT(*) FROM {qident(name)}").fetchone()[0])


def list_school_years(conn: sqlite3.Connection) -> list[tuple]:
    if not table_exists(conn, "school_years"):
        return []
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(school_years)").fetchall()
    }
    wanted = [c for c in ("id", "code", "name", "start_date", "end_date", "is_active") if c in cols]
    if not wanted:
        return []
    sql = "SELECT " + ", ".join(qident(c) for c in wanted) + " FROM school_years ORDER BY id"
    return [tuple(r) for r in conn.execute(sql).fetchall()]


def survey_batches_by_year(conn: sqlite3.Connection) -> list[tuple]:
    if not table_exists(conn, "survey_batches"):
        return []
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(survey_batches)").fetchall()
    }
    if not {"school_year_id", "id"}.issubset(cols):
        return []
    status_expr = "status" if "status" in cols else "NULL"
    sql = f"""
        SELECT school_year_id, {status_expr}, COUNT(*)
        FROM survey_batches
        GROUP BY school_year_id, {status_expr}
        ORDER BY school_year_id, {status_expr}
    """
    return [tuple(r) for r in conn.execute(sql).fetchall()]


def forms_by_batch_year(conn: sqlite3.Connection) -> list[tuple]:
    if not (table_exists(conn, "survey_forms") and table_exists(conn, "survey_batches")):
        return []
    sf_cols = {r[1] for r in conn.execute("PRAGMA table_info(survey_forms)").fetchall()}
    sb_cols = {r[1] for r in conn.execute("PRAGMA table_info(survey_batches)").fetchall()}
    if not {"survey_batch_id", "id"}.issubset(sf_cols) or not {"id", "school_year_id"}.issubset(sb_cols):
        return []
    sql = """
        SELECT sb.school_year_id, COUNT(sf.id)
        FROM survey_forms sf
        JOIN survey_batches sb ON sb.id = sf.survey_batch_id
        GROUP BY sb.school_year_id
        ORDER BY sb.school_year_id
    """
    return [tuple(r) for r in conn.execute(sql).fetchall()]


def year_records_by_year(conn: sqlite3.Connection) -> list[tuple]:
    if not table_exists(conn, "survey_person_year_records"):
        return []
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(survey_person_year_records)").fetchall()
    }
    if "school_year_id" not in cols:
        return []
    sql = """
        SELECT school_year_id, COUNT(*)
        FROM survey_person_year_records
        GROUP BY school_year_id
        ORDER BY school_year_id
    """
    return [tuple(r) for r in conn.execute(sql).fetchall()]


def historical_by_year(conn: sqlite3.Connection) -> list[tuple]:
    if not table_exists(conn, "historical_datasets"):
        return []
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(historical_datasets)").fetchall()
    }
    if "school_year_id" not in cols:
        return []
    sql = """
        SELECT school_year_id, COUNT(*)
        FROM historical_datasets
        GROUP BY school_year_id
        ORDER BY school_year_id
    """
    return [tuple(r) for r in conn.execute(sql).fetchall()]


def scan_candidates() -> list[Path]:
    found: list[Path] = []
    for p in PROJECT.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in DB_EXTS:
            continue
        rel_parts = {part.lower() for part in p.relative_to(PROJECT).parts}
        if rel_parts.intersection(SKIP_PARTS):
            continue
        found.append(p.resolve())

    # Loại trùng đường dẫn, ưu tiên file mới hơn trong báo cáo.
    unique = {str(p).lower(): p for p in found}
    return sorted(
        unique.values(),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )


def inspect_db(path: Path) -> dict:
    result = {
        "path": path,
        "size": path.stat().st_size,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime),
        "ok": False,
        "error": "",
        "integrity": "",
        "counts": {},
        "years": [],
        "batches_by_year": [],
        "forms_by_year": [],
        "year_records_by_year": [],
        "historical_by_year": [],
    }

    try:
        uri = path.as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            result["integrity"] = conn.execute("PRAGMA quick_check").fetchone()[0]
            for table in TABLES:
                result["counts"][table] = count_table(conn, table)
            result["years"] = list_school_years(conn)
            result["batches_by_year"] = survey_batches_by_year(conn)
            result["forms_by_year"] = forms_by_batch_year(conn)
            result["year_records_by_year"] = year_records_by_year(conn)
            result["historical_by_year"] = historical_by_year(conn)
            result["ok"] = True
        finally:
            conn.close()
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"

    return result


def source_score(info: dict) -> int:
    c = info["counts"]
    score = 0
    for name, weight in (
        ("households", 10),
        ("survey_people", 10),
        ("survey_forms", 8),
        ("survey_person_year_records", 8),
        ("historical_households", 6),
        ("historical_people", 6),
        ("historical_datasets", 4),
    ):
        n = c.get(name)
        if isinstance(n, int) and n > 0:
            score += weight
    return score


def main() -> int:
    lines: list[str] = []

    emit(lines, "=" * 108)
    emit(lines, "BÀI 13B-12.1 - TÌM NGUỒN HỘ DÂN TRONG DATABASE / BACKUP CŨ")
    emit(lines, "=" * 108)
    emit(lines)
    emit(lines, "MỤC TIÊU:")
    emit(lines, " - Quét các tệp SQLite trong C:\\PhoCap và các thư mục backup/exports.")
    emit(lines, " - Tìm database nào còn households / survey_people / survey_forms / dữ liệu lịch sử.")
    emit(lines, " - Xác định có nguồn năm trước để chuyển sang đợt 2026-2027 hay không.")
    emit(lines)
    emit(lines, "AN TOÀN:")
    emit(lines, " - Chỉ mở database ở chế độ READ-ONLY.")
    emit(lines, " - KHÔNG INSERT / UPDATE / DELETE.")
    emit(lines, " - KHÔNG sửa source.")
    emit(lines, " - KHÔNG khôi phục database tự động.")
    emit(lines)

    candidates = scan_candidates()
    emit(lines, f"Tổng số tệp SQLite tìm thấy: {len(candidates)}")

    infos = []
    for idx, path in enumerate(candidates, start=1):
        emit(lines)
        emit(lines, "-" * 108)
        emit(lines, f"[{idx}/{len(candidates)}] {path}")
        try:
            info = inspect_db(path)
        except Exception as exc:
            emit(lines, f"LỖI KHẢO SÁT: {type(exc).__name__}: {exc}")
            continue

        infos.append(info)

        emit(lines, f"Dung lượng: {info['size']:,} bytes")
        emit(lines, f"Sửa lần cuối: {info['mtime'].strftime('%Y-%m-%d %H:%M:%S')}")

        if not info["ok"]:
            emit(lines, f"Không đọc được SQLite: {info['error']}")
            continue

        emit(lines, f"quick_check: {info['integrity']}")
        emit(lines, f"Điểm nguồn hộ dân: {source_score(info)}")

        for table in TABLES:
            n = info["counts"].get(table)
            if n is not None:
                emit(lines, f"  {table}: {n}")

        if info["years"]:
            emit(lines, "  school_years:")
            for row in info["years"]:
                emit(lines, "    " + repr(row))

        if info["batches_by_year"]:
            emit(lines, "  survey_batches theo năm/trạng thái:")
            for row in info["batches_by_year"]:
                emit(lines, "    " + repr(row))

        if info["forms_by_year"]:
            emit(lines, "  survey_forms theo năm:")
            for row in info["forms_by_year"]:
                emit(lines, "    " + repr(row))

        if info["year_records_by_year"]:
            emit(lines, "  survey_person_year_records theo năm:")
            for row in info["year_records_by_year"]:
                emit(lines, "    " + repr(row))

        if info["historical_by_year"]:
            emit(lines, "  historical_datasets theo năm:")
            for row in info["historical_by_year"]:
                emit(lines, "    " + repr(row))

    emit(lines)
    emit(lines, "=" * 108)
    emit(lines, "XẾP HẠNG NGUỒN CÓ THỂ DÙNG")
    emit(lines, "=" * 108)

    usable = [x for x in infos if x["ok"] and source_score(x) > 0]
    usable.sort(
        key=lambda x: (
            source_score(x),
            x["counts"].get("households") or 0,
            x["counts"].get("survey_people") or 0,
            x["mtime"],
        ),
        reverse=True,
    )

    if not usable:
        emit(lines, "KHÔNG TÌM THẤY database/backup nào có dữ liệu hộ dân.")
        emit(lines, "=> Bước tiếp theo phải là nhập dữ liệu nền từ Excel/nguồn cũ, không thể chuyển năm từ DB.")
    else:
        for i, info in enumerate(usable[:20], start=1):
            c = info["counts"]
            emit(
                lines,
                f"{i:02d}. score={source_score(info):02d} | "
                f"households={c.get('households')} | "
                f"people={c.get('survey_people')} | "
                f"forms={c.get('survey_forms')} | "
                f"year_records={c.get('survey_person_year_records')} | "
                f"historical_households={c.get('historical_households')} | "
                f"{info['path']}"
            )

    emit(lines)
    emit(lines, "=" * 108)
    emit(lines, "KẾT LUẬN BÀI 13B-12.1")
    emit(lines, "=" * 108)
    emit(lines, "Khảo sát hoàn tất. Không có database hoặc source nào bị thay đổi.")
    emit(lines, "Hãy gửi tệp báo cáo này để chốt nguồn dữ liệu cho Bài 13B-12.2.")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print("Báo cáo đã lưu:")
    print(REPORT)
    print()
    print("BÀI 13B-12.1 HOÀN THÀNH - CHỈ ĐỌC, KHÔNG THAY ĐỔI DỮ LIỆU")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
