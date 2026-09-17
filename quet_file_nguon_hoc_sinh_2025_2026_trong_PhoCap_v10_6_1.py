# -*- coding: utf-8 -*-
r"""
DRY-RUN V10.6.1 - QUÉT FILE NGUỒN HỌC SINH 2025-2026 TRONG C:\PhoCap
====================================================================

MỤC TIÊU
--------
Sau V10.5:
- Không có historical_people / students / student_enrollments trong backup.
- Nhưng có 14 lớp 2025-2026.
- Cần tìm file nguồn học sinh 2025-2026 từng được dùng/import.

V10.6 quét CHỈ ĐỌC toàn bộ C:\PhoCap, bỏ qua .venv và cache:
- .xlsx
- .xls
- .csv
- .txt
- .zip
- .json
- .db/.sqlite/.sqlite3 (chỉ ghi nhận metadata, không sửa)

Với XLSX:
- dùng openpyxl nếu có;
- đọc tên sheet, 10 dòng đầu, tìm các tiêu đề như:
  Họ tên, Mã học sinh, Ngày sinh, Lớp, Trường, Năm học...
- tìm chuỗi 2025-2026.

Với CSV/TXT/JSON:
- đọc phần đầu, tìm từ khóa học sinh + 2025-2026.

Với ZIP:
- liệt kê tên file bên trong, tìm file có tên liên quan học sinh/2025-2026.

KHÔNG sửa/xóa/mở ghi bất kỳ file nào.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\quet_file_nguon_hoc_sinh_2025_2026_trong_PhoCap_v10_6.py
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
SKIP_DIR_NAMES = {
    ".venv", "__pycache__", ".git", ".pytest_cache",
    "node_modules", ".mypy_cache"
}

SCAN_EXTS = {
    ".xlsx", ".xls", ".csv", ".txt", ".json", ".zip",
    ".db", ".sqlite", ".sqlite3"
}

NAME_KEYWORDS = (
    "hoc sinh", "học sinh", "student", "students",
    "danh sach hoc sinh", "danh sách học sinh",
    "du lieu hoc sinh", "dữ liệu học sinh",
    "2025 2026", "2025-2026", "2025_2026",
    "baseline", "doi chieu", "đối chiếu"
)

HEADER_KEYWORDS = (
    "họ tên", "ho ten", "tên học sinh", "ten hoc sinh",
    "mã học sinh", "ma hoc sinh", "student id", "student_id",
    "ngày sinh", "ngay sinh",
    "lớp", "lop", "class",
    "trường", "truong", "school",
    "năm học", "nam hoc", "school year", "school_year"
)


def normalize(s) -> str:
    text = "" if s is None else str(s)
    text = text.lower()
    trans = str.maketrans({
        "á":"a","à":"a","ả":"a","ã":"a","ạ":"a",
        "ă":"a","ắ":"a","ằ":"a","ẳ":"a","ẵ":"a","ặ":"a",
        "â":"a","ấ":"a","ầ":"a","ẩ":"a","ẫ":"a","ậ":"a",
        "é":"e","è":"e","ẻ":"e","ẽ":"e","ẹ":"e",
        "ê":"e","ế":"e","ề":"e","ể":"e","ễ":"e","ệ":"e",
        "í":"i","ì":"i","ỉ":"i","ĩ":"i","ị":"i",
        "ó":"o","ò":"o","ỏ":"o","õ":"o","ọ":"o",
        "ô":"o","ố":"o","ồ":"o","ổ":"o","ỗ":"o","ộ":"o",
        "ơ":"o","ớ":"o","ờ":"o","ở":"o","ỡ":"o","ợ":"o",
        "ú":"u","ù":"u","ủ":"u","ũ":"u","ụ":"u",
        "ư":"u","ứ":"u","ừ":"u","ử":"u","ữ":"u","ự":"u",
        "ý":"y","ỳ":"y","ỷ":"y","ỹ":"y","ỵ":"y",
        "đ":"d"
    })
    text = text.translate(trans)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def has_student_keyword(text: str) -> bool:
    n = normalize(text)
    checks = (
        "hoc sinh", "student", "student id",
        "ma hoc sinh", "ten hoc sinh"
    )
    return any(x in n for x in checks)


def has_year_2025_2026(text: str) -> bool:
    return bool(
        re.search(r"2025\D{0,5}2026", str(text), flags=re.I)
    )


def filename_score(path: Path) -> int:
    n = normalize(path.name)
    score = 0
    if "hoc sinh" in n or "student" in n:
        score += 5
    if "2025 2026" in n:
        score += 4
    if "doi chieu" in n:
        score += 2
    if "baseline" in n:
        score += 2
    return score


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    """Ghi CSV UTF-8 BOM để mở tốt bằng Excel trên Windows."""
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=headers,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def safe_read_text(path: Path, max_bytes: int = 2_000_000) -> str:
    data = path.read_bytes()[:max_bytes]
    for enc in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return ""


def inspect_xlsx(path: Path) -> dict:
    result = {
        "content_status": "NOT_READ",
        "sheet_names": "",
        "sheet_count": "",
        "header_hits": "",
        "student_keyword": "NO",
        "mentions_2025_2026": "NO",
        "sample": "",
        "row_estimate": "",
    }

    try:
        from openpyxl import load_workbook
    except Exception:
        result["content_status"] = "OPENPYXL_UNAVAILABLE"
        return result

    try:
        wb = load_workbook(
            path,
            read_only=True,
            data_only=True,
        )
        result["content_status"] = "OK"
        result["sheet_names"] = " | ".join(wb.sheetnames[:30])
        result["sheet_count"] = len(wb.sheetnames)

        samples = []
        hits = []
        any_student = False
        any_year = False
        total_rows_est = 0

        for ws in wb.worksheets[:15]:
            try:
                total_rows_est += int(ws.max_row or 0)
            except Exception:
                pass

            for row_idx, row in enumerate(
                ws.iter_rows(min_row=1, max_row=min(ws.max_row or 1, 12), values_only=True),
                start=1
            ):
                vals = ["" if v is None else str(v) for v in row[:40]]
                line = " | ".join(vals)
                if line.strip():
                    samples.append(f"[{ws.title}!{row_idx}] {line[:500]}")

                nline = normalize(line)
                for kw in HEADER_KEYWORDS:
                    nkw = normalize(kw)
                    if nkw and nkw in nline:
                        hits.append(f"{ws.title}:{kw}")

                if has_student_keyword(line):
                    any_student = True
                if has_year_2025_2026(line):
                    any_year = True

        result["header_hits"] = " | ".join(sorted(set(hits))[:50])
        result["student_keyword"] = "YES" if any_student else "NO"
        result["mentions_2025_2026"] = "YES" if any_year else "NO"
        result["sample"] = "\n".join(samples[:20])
        result["row_estimate"] = total_rows_est
        wb.close()
    except Exception as exc:
        result["content_status"] = f"ERROR:{type(exc).__name__}:{exc}"

    return result


def inspect_text_like(path: Path) -> dict:
    result = {
        "content_status": "OK",
        "sheet_names": "",
        "sheet_count": "",
        "header_hits": "",
        "student_keyword": "NO",
        "mentions_2025_2026": "NO",
        "sample": "",
        "row_estimate": "",
    }
    try:
        text = safe_read_text(path)
        result["student_keyword"] = "YES" if has_student_keyword(text) else "NO"
        result["mentions_2025_2026"] = "YES" if has_year_2025_2026(text) else "NO"

        hits = []
        ntext = normalize(text[:200000])
        for kw in HEADER_KEYWORDS:
            if normalize(kw) in ntext:
                hits.append(kw)
        result["header_hits"] = " | ".join(sorted(set(hits)))
        result["sample"] = text[:3000].replace("\x00", "")
        result["row_estimate"] = text.count("\n") + 1 if text else 0
    except Exception as exc:
        result["content_status"] = f"ERROR:{type(exc).__name__}:{exc}"
    return result


def inspect_zip(path: Path) -> dict:
    result = {
        "content_status": "OK",
        "sheet_names": "",
        "sheet_count": "",
        "header_hits": "",
        "student_keyword": "NO",
        "mentions_2025_2026": "NO",
        "sample": "",
        "row_estimate": "",
    }
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            joined = "\n".join(names)
            result["student_keyword"] = "YES" if has_student_keyword(joined) else "NO"
            result["mentions_2025_2026"] = "YES" if has_year_2025_2026(joined) else "NO"
            result["sample"] = "\n".join(names[:100])
            result["row_estimate"] = len(names)
    except Exception as exc:
        result["content_status"] = f"ERROR:{type(exc).__name__}:{exc}"
    return result


def inspect_file(path: Path) -> dict:
    row = {
        "path": str(path),
        "name": path.name,
        "extension": path.suffix.lower(),
        "size_mb": round(path.stat().st_size / (1024 * 1024), 3),
        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(
            sep=" ", timespec="seconds"
        ),
        "filename_score": filename_score(path),
        "content_status": "NOT_APPLICABLE",
        "sheet_names": "",
        "sheet_count": "",
        "header_hits": "",
        "student_keyword": "NO",
        "mentions_2025_2026": "NO",
        "sample": "",
        "row_estimate": "",
        "candidate_score": 0,
    }

    ext = path.suffix.lower()

    if ext == ".xlsx":
        extra = inspect_xlsx(path)
        row.update(extra)
    elif ext in {".csv", ".txt", ".json"}:
        extra = inspect_text_like(path)
        row.update(extra)
    elif ext == ".zip":
        extra = inspect_zip(path)
        row.update(extra)
    elif ext == ".xls":
        row["content_status"] = "BINARY_XLS_NOT_PARSED"
    elif ext in {".db", ".sqlite", ".sqlite3"}:
        row["content_status"] = "DATABASE_METADATA_ONLY"

    score = int(row["filename_score"])
    if row["student_keyword"] == "YES":
        score += 5
    if row["mentions_2025_2026"] == "YES":
        score += 4
    if row["header_hits"]:
        score += 3
    if ext in {".xlsx", ".xls", ".csv"}:
        score += 1

    row["candidate_score"] = score
    return row


def main() -> None:
    print("=" * 124)
    print("DRY-RUN V10.6 - QUÉT FILE NGUỒN HỌC SINH 2025-2026 TRONG C:\\PhoCap")
    print("=" * 124)
    print("Chế độ: CHỈ ĐỌC")

    if not ROOT.exists():
        print(f"Không tìm thấy {ROOT}")
        sys.exit(2)

    candidates = []

    for current_root, dirs, files in os.walk(ROOT):
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIR_NAMES
        ]

        for name in files:
            path = Path(current_root) / name
            if path.suffix.lower() not in SCAN_EXTS:
                continue
            candidates.append(path)

    candidates.sort(
        key=lambda p: (
            filename_score(p),
            p.stat().st_mtime
        ),
        reverse=True
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"dry_run_tim_file_nguon_hoc_sinh_2025_2026_v10_6_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    results = []

    for i, path in enumerate(candidates, start=1):
        print(f"[{i}/{len(candidates)}] {path}")
        results.append(inspect_file(path))

    ranked = sorted(
        results,
        key=lambda r: (
            int(r["candidate_score"]),
            r["modified"]
        ),
        reverse=True,
    )

    strong = [
        r for r in ranked
        if int(r["candidate_score"]) >= 7
    ]

    top = ranked[:50]

    headers = [
        "path", "name", "extension",
        "size_mb", "modified",
        "filename_score", "candidate_score",
        "content_status",
        "student_keyword", "mentions_2025_2026",
        "sheet_count", "sheet_names",
        "header_hits", "row_estimate", "sample",
    ]

    write_csv(
        out_dir / "480_ALL_SCANNED_FILES.csv",
        headers,
        ranked,
    )
    write_csv(
        out_dir / "481_STRONG_CANDIDATES.csv",
        headers,
        strong,
    )
    write_csv(
        out_dir / "482_TOP_50_CANDIDATES.csv",
        headers,
        top,
    )

    source_found = bool(strong)

    gate_rows = [
        {
            "check": "files_scanned",
            "result": "INFO",
            "detail": str(len(results)),
        },
        {
            "check": "strong_candidates",
            "result": "FOUND" if strong else "NO_DATA",
            "detail": str(len(strong)),
        },
        {
            "check": "SOURCE_FILE_2025_2026_CANDIDATE_FOUND",
            "result": "YES" if source_found else "NO",
            "detail": (
                strong[0]["path"]
                if strong
                else "Không tìm thấy ứng viên mạnh trong C:\\PhoCap."
            ),
        },
        {
            "check": "NEXT_STEP",
            "result": (
                "INSPECT_TOP_CANDIDATE"
                if source_found
                else "ASK_FOR_SOURCE_FILE"
            ),
            "detail": (
                "Chưa import. Cần kiểm tra cấu trúc file ứng viên trước."
                if source_found
                else "Cần cung cấp file nguồn học sinh 2025-2026."
            ),
        },
    ]

    write_csv(
        out_dir / "483_GATE_V10_6.csv",
        ["check", "result", "detail"],
        gate_rows,
    )

    summary = out_dir / "00_TONG_QUAN_V10_6.txt"
    with summary.open("w", encoding="utf-8") as f:
        f.write(
            "DRY-RUN V10.6 - TÌM FILE NGUỒN HỌC SINH 2025-2026 TRONG C:\\PhoCap\n"
        )
        f.write("=" * 124 + "\n")
        f.write("CHỈ ĐỌC - KHÔNG IMPORT\n\n")
        f.write(f"Files scanned: {len(results)}\n")
        f.write(f"Strong candidates: {len(strong)}\n\n")

        if strong:
            f.write("ỨNG VIÊN MẠNH NHẤT\n")
            for r in strong[:10]:
                f.write(
                    f"- score={r['candidate_score']} | "
                    f"{r['path']} | "
                    f"student={r['student_keyword']} | "
                    f"2025-2026={r['mentions_2025_2026']} | "
                    f"headers={r['header_hits']}\n"
                )
            f.write("\nSOURCE_FILE_2025_2026_CANDIDATE_FOUND = YES\n")
            f.write("NEXT_STEP = INSPECT_TOP_CANDIDATE\n")
        else:
            f.write("SOURCE_FILE_2025_2026_CANDIDATE_FOUND = NO\n")
            f.write("NEXT_STEP = ASK_FOR_SOURCE_FILE\n")

    zip_path = ROOT / f"dry_run_tim_file_nguon_hoc_sinh_2025_2026_v10_6_{ts}.zip"
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        for p in sorted(out_dir.iterdir()):
            zf.write(p, arcname=p.name)

    print()
    print("=" * 124)
    print("HOÀN THÀNH DRY-RUN V10.6.1")
    print("=" * 124)
    print(f"Files scanned: {len(results)}")
    print(f"Strong candidates: {len(strong)}")
    print(
        "SOURCE_FILE_2025_2026_CANDIDATE_FOUND: "
        + ("YES" if source_found else "NO")
    )
    if strong:
        print(f"Ứng viên mạnh nhất: {strong[0]['path']}")
        print(f"Score: {strong[0]['candidate_score']}")
    print(f"ZIP: {zip_path}")
    print("Không có file/database nào bị thay đổi.")


if __name__ == "__main__":
    main()
