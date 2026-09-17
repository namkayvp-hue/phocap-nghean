# -*- coding: utf-8 -*-
"""
TRUY VẾT PHƯƠNG ÁN QĐ3805 CHO THCS MẬU ĐÔN - CHỈ ĐỌC FILE

Mục tiêu:
- Tìm QD3805-OP-0108
- Tìm "Mậu Đôn", mã 40422510, school_id 1578
- Tìm plan_id dạng PA2026-... đi cùng phương án
- Quét các file văn bản / CSV / JSON / PY / SQL / HTML / YAML...
- Quét cả nội dung XML trong XLSX/XLSM/ZIP nếu có.
- KHÔNG sửa bất kỳ file nào.
- KHÔNG mở DB để ghi.
"""

from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
TERMS = [
    "QD3805-OP-0108",
    "Mậu Đôn",
    "Mau Don",
    "40422510",
    "1578",
]
TEXT_EXTS = {
    ".txt", ".csv", ".json", ".py", ".sql", ".html", ".htm",
    ".js", ".ts", ".css", ".md", ".yaml", ".yml", ".ini", ".cfg",
    ".log", ".xml", ".ps1", ".bat", ".cmd"
}
ZIP_EXTS = {".xlsx", ".xlsm", ".zip"}
SKIP_DIR_NAMES = {
    ".venv", "__pycache__", ".git", "node_modules"
}
MAX_FILE_SIZE = 50 * 1024 * 1024
PLAN_RE = re.compile(r"PA2026-[A-Fa-f0-9]{6,}")

def should_skip_path(p: Path) -> bool:
    lower_parts = [x.lower() for x in p.parts]
    if any(x.lower() in SKIP_DIR_NAMES for x in p.parts):
        return True
    # Bỏ các thư mục backup nặng; nhưng vẫn quét file tên plan ở thư mục gốc/installer hiện tại.
    if any(("backup" in x or "sao_luu" in x or "saoluu" in x) for x in lower_parts):
        return True
    return False

def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1258", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            pass
    return data.decode("utf-8", errors="replace")

def context_lines(text: str, term: str, radius: int = 3):
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if term.lower() in line.lower():
            start = max(0, i-radius)
            end = min(len(lines), i+radius+1)
            out.append((i+1, lines[start:end]))
    return out

def scan_text_file(path: Path):
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return []
        data = path.read_bytes()
        text = decode_bytes(data)
    except Exception:
        return []

    hits = []
    for term in TERMS:
        if term.lower() in text.lower():
            contexts = context_lines(text, term, 4)
            hits.append((term, contexts[:10], sorted(set(PLAN_RE.findall(text)))))
    return hits

def scan_zip_file(path: Path):
    hits = []
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return hits
        with zipfile.ZipFile(path, "r") as z:
            for name in z.namelist():
                low = name.lower()
                if not low.endswith((".xml", ".txt", ".csv", ".json", ".rels")):
                    continue
                try:
                    data = z.read(name)
                    text = decode_bytes(data)
                except Exception:
                    continue
                for term in TERMS:
                    if term.lower() in text.lower():
                        contexts = context_lines(text, term, 4)
                        hits.append((name, term, contexts[:10], sorted(set(PLAN_RE.findall(text)))))
    except Exception:
        pass
    return hits

def main():
    print("=" * 150)
    print("TRUY VẾT PHƯƠNG ÁN THCS MẬU ĐÔN - TÌM OFFICIAL PLAN_ID - CHỈ ĐỌC")
    print("=" * 150)
    print("ROOT =", ROOT)

    if not ROOT.exists():
        print("DỪNG: không tìm thấy C:\\PhoCap")
        sys.exit(2)

    scanned = 0
    matched_files = 0
    found_plan_ids = set()

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if should_skip_path(path):
            continue

        ext = path.suffix.lower()
        if ext not in TEXT_EXTS and ext not in ZIP_EXTS:
            continue

        scanned += 1

        if ext in TEXT_EXTS:
            hits = scan_text_file(path)
            if hits:
                matched_files += 1
                print("\n" + "#" * 150)
                print("FILE =", path)
                print("#" * 150)
                for term, contexts, plan_ids in hits:
                    print("\nTERM =", term)
                    if plan_ids:
                        print("PLAN_IDS TRONG FILE =", plan_ids)
                        found_plan_ids.update(plan_ids)
                    for line_no, block in contexts:
                        print(f"\n  MATCH AROUND LINE {line_no}")
                        for x in block:
                            print("   ", x[:1000])

        elif ext in ZIP_EXTS:
            hits = scan_zip_file(path)
            if hits:
                matched_files += 1
                print("\n" + "#" * 150)
                print("ARCHIVE =", path)
                print("#" * 150)
                for inner, term, contexts, plan_ids in hits:
                    print("\nINNER =", inner)
                    print("TERM =", term)
                    if plan_ids:
                        print("PLAN_IDS TRONG INNER =", plan_ids)
                        found_plan_ids.update(plan_ids)
                    for line_no, block in contexts:
                        print(f"\n  MATCH AROUND LINE {line_no}")
                        for x in block:
                            print("   ", x[:1000])

    print("\n" + "=" * 150)
    print("TỔNG KẾT")
    print("=" * 150)
    print("FILES SCANNED =", scanned)
    print("MATCHED FILES =", matched_files)
    print("PLAN_IDS PHÁT HIỆN =", sorted(found_plan_ids))

    if found_plan_ids:
        print("\nCÓ PLAN_ID ĐỂ ĐỐI CHIẾU.")
    else:
        print("\nCHƯA TÌM THẤY PLAN_ID. KHÔNG ĐƯỢC COMMIT.")

    print("\nKHÔNG SỬA FILE.")
    print("KHÔNG GHI DATABASE.")
    print("KHÔNG SÁP NHẬP.")

if __name__ == "__main__":
    main()
