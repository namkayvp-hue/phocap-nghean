import sys
import hashlib
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

SERVICE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_level_batch_service.py"
)

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

db_before = sha256(DB)

print("=" * 120)
print("KHẢO SÁT PRECOMPLETED / RESOLUTION HIỆN TẠI")
print("CHỈ ĐỌC - KHÔNG SỬA SOURCE - KHÔNG GHI DATABASE")
print("=" * 120)

text = SERVICE.read_text(
    encoding="utf-8-sig",
    errors="replace",
)

lines = text.splitlines()

print()
print("=" * 120)
print("1. CONSTANT / RESOLUTION PATH")
print("=" * 120)

for no, line in enumerate(lines, 1):
    if any(
        k in line
        for k in (
            "RESOLUTION",
            "_load_th_resolution",
            "_resolution_context",
        )
    ):
        if no <= 220:
            print(f"{no:05}: {line}")

print()
print("=" * 120)
print("2. TOÀN BỘ KHỐI _load_th_resolution / _resolution_context")
print("=" * 120)

for no in range(145, min(221, len(lines) + 1)):
    print(f"{no:05}: {lines[no-1]}")

print()
print("=" * 120)
print("3. TOÀN BỘ _precompleted_resolution_status")
print("=" * 120)

start = None
end = None

for i, line in enumerate(lines):
    if line.startswith(
        "def _precompleted_resolution_status("
    ):
        start = i
        continue

    if (
        start is not None
        and i > start
        and line.startswith("def ")
    ):
        end = i
        break

if start is None:
    raise RuntimeError(
        "Không tìm thấy _precompleted_resolution_status."
    )

if end is None:
    end = len(lines)

for no in range(start + 1, end + 1):
    print(f"{no:05}: {lines[no-1]}")

print()
print("=" * 120)
print("4. CÁC FILE RESOLUTION JSON HIỆN CÓ")
print("=" * 120)

json_files = []

for p in ROOT.rglob("*.json"):
    low = str(p).lower()

    if "\\backups\\" in low:
        continue

    name = p.name.lower()

    if (
        "resolution" in name
        or "xu_ly_rieng" in name
        or "precompleted" in name
    ):
        json_files.append(p)

if not json_files:
    print("<KHÔNG TÌM THẤY>")
else:
    for p in sorted(json_files):
        print()
        print("FILE:", p)
        print("SHA :", sha256(p))

        try:
            content = p.read_text(
                encoding="utf-8-sig",
                errors="replace",
            )
        except Exception as exc:
            print("Không đọc được:", exc)
            continue

        print(content[:20000])

db_after = sha256(DB)

print()
print("=" * 120)
print("KIỂM TRA AN TOÀN")
print("=" * 120)

print("DB hash trước:", db_before)
print("DB hash sau  :", db_after)

if db_before != db_after:
    raise RuntimeError(
        "DỪNG: database thay đổi ngoài dự kiến."
    )

print("Database     : KHÔNG THAY ĐỔI")
print("=" * 120)
