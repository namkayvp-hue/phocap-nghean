import sys
import hashlib
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"

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

print("=" * 118)
print("KHẢO SÁT NGUỒN ĐỘI NGŨ MN 2025-2026")
print("CHỈ ĐỌC - KHÔNG SỬA FILE - KHÔNG GHI DATABASE")
print("=" * 118)

# ------------------------------------------------------------------
# 1. Xác định chính xác file service đang dùng
# ------------------------------------------------------------------
import app.services.school_merger_source_audit_service as audit_service

service_file = Path(audit_service.__file__).resolve()

print()
print("SOURCE AUDIT SERVICE:")
print(service_file)

print()
print("=" * 118)
print("CÁC BIẾN PATH / REGISTRY / SOURCE / DATASET TRONG MODULE")
print("=" * 118)

for name in sorted(dir(audit_service)):
    upper = name.upper()

    if not any(
        x in upper
        for x in (
            "PATH",
            "REGISTRY",
            "SOURCE",
            "DATASET",
            "ROSTER",
        )
    ):
        continue

    try:
        value = getattr(audit_service, name)
    except Exception:
        continue

    if isinstance(value, (str, Path, int, float, bool, type(None))):
        print(f"{name} = {value}")

# ------------------------------------------------------------------
# 2. Tìm trong source code các dòng liên quan registry
# ------------------------------------------------------------------
print()
print("=" * 118)
print("DÒNG CODE LIÊN QUAN REGISTRY / SOURCE ROSTER")
print("=" * 118)

text = service_file.read_text(
    encoding="utf-8",
    errors="replace",
)

keywords = (
    "registry",
    "source_roster",
    "dataset",
    "2025-2026",
    "TH_2025_2026",
    "MISSING_SOURCE_ROSTER",
)

for i, line in enumerate(text.splitlines(), 1):
    low = line.lower()

    if any(x.lower() in low for x in keywords):
        print(f"{i:5}: {line}")

# ------------------------------------------------------------------
# 3. Tìm JSON registry có liên quan
#    Bỏ backups để tránh nhầm bản cũ.
# ------------------------------------------------------------------
print()
print("=" * 118)
print("CÁC FILE JSON CÓ KHẢ NĂNG LÀ SOURCE REGISTRY")
print("=" * 118)

json_hits = []

for p in ROOT.rglob("*.json"):
    s = str(p).lower()

    if "\\backups\\" in s:
        continue

    name = p.name.lower()

    if any(
        k in name
        for k in (
            "2025_2026",
            "2025-2026",
            "registry",
            "roster",
            "source",
            "giao_vien",
            "doi_ngu",
        )
    ):
        json_hits.append(p)

for p in sorted(json_hits):
    print(p)

# ------------------------------------------------------------------
# 4. Tìm Excel có khả năng là danh sách đội ngũ MN
# ------------------------------------------------------------------
print()
print("=" * 118)
print("CÁC FILE EXCEL CÓ KHẢ NĂNG LÀ NGUỒN ĐỘI NGŨ MN")
print("=" * 118)

excel_hits = []

for ext in ("*.xlsx", "*.xls"):
    for p in ROOT.rglob(ext):
        s = str(p).lower()

        if "\\backups\\" in s:
            continue

        name = p.name.lower()

        # Không kết luận file nào đúng, chỉ liệt kê ứng viên.
        if any(
            k in name
            for k in (
                "giao_vien",
                "giao vien",
                "giáo viên",
                "doi_ngu",
                "đội ngũ",
                "mam_non",
                "mầm non",
                "mam non",
            )
        ):
            excel_hits.append(p)

if excel_hits:
    for p in sorted(set(excel_hits)):
        print(p)
else:
    print("<CHƯA TÌM THẤY FILE EXCEL ỨNG VIÊN TRONG C:\\PhoCap>")

# ------------------------------------------------------------------
# 5. Tìm chính xác file TH_2025_2026.json đang được audit báo
# ------------------------------------------------------------------
print()
print("=" * 118)
print("TÌM TH_2025_2026.json")
print("=" * 118)

th_hits = list(ROOT.rglob("TH_2025_2026.json"))

if th_hits:
    for p in th_hits:
        if "\\backups\\" not in str(p).lower():
            print(p)
else:
    print("<KHÔNG TÌM THẤY>")

# ------------------------------------------------------------------
# An toàn DB
# ------------------------------------------------------------------
db_after = sha256(DB)

print()
print("=" * 118)
print("KIỂM TRA AN TOÀN")
print("=" * 118)
print("DB hash trước:", db_before)
print("DB hash sau  :", db_after)

if db_before != db_after:
    raise RuntimeError(
        "DỪNG: phocap.db thay đổi ngoài dự kiến."
    )

print("Database     : KHÔNG THAY ĐỔI")
print("=" * 118)
