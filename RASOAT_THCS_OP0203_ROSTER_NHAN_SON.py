# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
ROSTER_DIR = ROOT / "data" / "school_merger_source_rosters"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "RASOAT_THCS_OP0203_ROSTER_NHAN_SON.txt"

EXPECTED_DB_SHA = "1723e12a3d06d8f52b7b899174d5040bc4937ab84564e0f4d51b009586d8ce22"

TERMS = [
    "THCS Kim Đồng",
    "Kim Đồng",
    "Minh Sơn",
    "THCS Lê Hồng Phong",
    "Lê Hồng Phong",
    "Nhân Sơn",
    "Thuần Trung",
]

LIKELY_KEYS = (
    "school", "truong", "trường", "unit", "don_vi", "đơn_vị",
    "commune", "xa", "xã", "ward", "phuong", "phường",
    "code", "ma_", "mã_", "name", "ten", "tên",
    "status", "trang_thai", "trạng_thái",
    "position", "chuc", "chức", "subject", "mon", "môn",
)

def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def normalize(s):
    return str(s or "").strip().lower()

def scalar(v):
    return isinstance(v, (str, int, float, bool)) or v is None

def compact_dict(d):
    out = {}
    for k, v in d.items():
        if not scalar(v):
            continue
        kl = str(k).lower()
        if any(token in kl for token in LIKELY_KEYS):
            out[str(k)] = v
    if not out:
        for k, v in d.items():
            if scalar(v):
                out[str(k)] = v
                if len(out) >= 12:
                    break
    return out

def dict_matches(d):
    text = " | ".join(str(v) for v in d.values() if scalar(v))
    low = text.lower()
    return [t for t in TERMS if t.lower() in low]

def walk_dicts(obj, path="$"):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                yield from walk_dicts(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                yield from walk_dicts(v, f"{path}[{i}]")

def load_json(path: Path):
    for enc in ("utf-8-sig", "utf-8"):
        try:
            with path.open("r", encoding=enc) as f:
                return json.load(f)
        except Exception:
            pass
    return None

def inspect_json(path: Path):
    print("\n" + "=" * 150)
    print("ROSTER_FILE =", path)
    try:
        print("SIZE =", path.stat().st_size)
        print("SHA256 =", sha256_file(path))
    except Exception as e:
        print("FILE_META_ERROR =", repr(e))

    data = load_json(path)
    if data is None:
        print("JSON_LOAD = FAILED")
        return

    print("JSON_LOAD = OK")
    if isinstance(data, dict):
        print("TOP_LEVEL_KEYS =", list(data.keys())[:100])
        for k in (
            "version", "dataset_id", "level_code", "school_year_code",
            "source_file", "source_sheet", "row_count", "school_count",
            "active_status_labels", "status_counts"
        ):
            if k in data:
                print(f"{k} =", data.get(k))
    else:
        print("TOP_LEVEL_TYPE =", type(data).__name__, "LEN =", len(data) if hasattr(data, "__len__") else None)

    matches = []
    grouped = Counter()
    examples = {}

    for path_key, d in walk_dicts(data):
        terms = dict_matches(d)
        if not terms:
            continue
        cd = compact_dict(d)
        sig = json.dumps(cd, ensure_ascii=False, sort_keys=True, default=str)
        grouped[sig] += 1
        examples.setdefault(sig, (path_key, terms, cd))
        if len(matches) < 300:
            matches.append((path_key, terms, cd))

    print("MATCHED_DICT_COUNT =", sum(grouped.values()))
    print("UNIQUE_MATCH_SIGNATURES =", len(grouped))

    print("\nTOP MATCH SIGNATURES")
    for sig, n in grouped.most_common(80):
        p, terms, cd = examples[sig]
        print("-" * 120)
        print("COUNT =", n)
        print("FIRST_PATH =", p)
        print("TERMS =", terms)
        print("DATA =", json.dumps(cd, ensure_ascii=False, sort_keys=True, default=str))

    print("\nFIRST MATCHED DICTS")
    for p, terms, cd in matches[:120]:
        print("-" * 120)
        print("PATH =", p)
        print("TERMS =", terms)
        print("DATA =", json.dumps(cd, ensure_ascii=False, sort_keys=True, default=str))

def search_raw_text_files():
    print("\n" + "=" * 150)
    print("RAW TEXT SEARCH IN ROSTER_DIR")
    print("=" * 150)

    if not ROSTER_DIR.exists():
        print("ROSTER_DIR_NOT_FOUND =", ROSTER_DIR)
        return

    for path in sorted(ROSTER_DIR.glob("*")):
        if not path.is_file():
            continue
        print("\nFILE =", path.name, "| SIZE =", path.stat().st_size)

        if path.suffix.lower() not in {".json", ".txt", ".csv", ".md"}:
            continue

        # Đọc text để biết chính xác file nào chứa thuật ngữ.
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp1258", "cp1252"):
            try:
                text = path.read_text(encoding=enc)
                break
            except Exception:
                pass
        if text is None:
            print("TEXT_READ_FAILED")
            continue

        low = text.lower()
        for term in TERMS:
            cnt = low.count(term.lower())
            if cnt:
                print(f"TERM_COUNT {term!r} =", cnt)

def db_crosscheck():
    conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    try:
        print("\n" + "=" * 150)
        print("DB CROSSCHECK")
        print("=" * 150)

        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("integrity =", integ)
        print("FK =", len(fk))

        rows = conn.execute(
            """
            SELECT id,commune_id,code,name,is_active
            FROM schools
            WHERE commune_id=103
            ORDER BY id
            """
        ).fetchall()
        print("COMMUNE_103_SCHOOLS =", rows)

        for sid in (1710, 1711, 1712, 1465, 1551):
            s = conn.execute(
                "SELECT id,commune_id,code,name,is_active FROM schools WHERE id=?",
                (sid,)
            ).fetchone()
            staff = conn.execute(
                """
                SELECT school_year_id,position_group,COUNT(*)
                FROM staff_year_records
                WHERE school_id=?
                GROUP BY school_year_id,position_group
                ORDER BY school_year_id,position_group
                """,
                (sid,)
            ).fetchall()
            print("SCHOOL =", s)
            print("STAFF =", staff)
    finally:
        conn.close()

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 150)
    print("OP-0203 - RÀ SOÁT SOURCE ROSTER THCS KIM ĐỒNG (MINH SƠN) / LÊ HỒNG PHONG (NHÂN SƠN)")
    print("CHỈ ĐỌC - KHÔNG GHI DATABASE")
    print("=" * 150)

    if not DB.exists():
        print("STOP = Không tìm thấy DB")
        return 2

    sha = sha256_file(DB)
    print("DB_SHA =", sha)
    print("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
    if sha != EXPECTED_DB_SHA:
        print("STOP = DB SHA đã khác nền sau OP-0172.")
        return 1

    db_crosscheck()
    search_raw_text_files()

    if not ROSTER_DIR.exists():
        print("STOP = Không tìm thấy thư mục roster", ROSTER_DIR)
        return 0

    roster_files = sorted(
        p for p in ROSTER_DIR.glob("*.json")
        if p.is_file()
    )
    print("\nJSON_ROSTER_FILES =", [p.name for p in roster_files])

    # Ưu tiên file có THCS trong tên hoặc metadata, nhưng vẫn kiểm tra tất cả.
    for path in roster_files:
        inspect_json(path)

    print("\n" + "=" * 150)
    print("KẾT LUẬN")
    print("=" * 150)
    print("MỤC TIÊU = xác định roster 2025-2026 của THCS Kim Đồng (Minh Sơn) và THCS Lê Hồng Phong (Nhân Sơn).")
    print("Nếu roster chứng minh Nhân Sơn không có school_id hiện hữu trong DB, bước sau phải xử lý MERGE_TO_NEW_NAME đúng QĐ3805; KHÔNG dùng id=1551 của Hưng Nguyên.")
    print("DATABASE = KHÔNG THAY ĐỔI")
    print("=" * 150)
    return 0

if __name__ == "__main__":
    class Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, data):
            for s in self.streams:
                s.write(data)
                s.flush()
        def flush(self):
            for s in self.streams:
                s.flush()

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        old = sys.stdout
        sys.stdout = Tee(old, f)
        try:
            code = main()
        finally:
            sys.stdout = old
    sys.exit(code)
