from pathlib import Path
import hashlib
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")

SOURCE = ROOT / "dry_run_tong_cuoi_5_MN_READY.py"
TARGET = ROOT / "dry_run_tong_cuoi_5_MN_READY_sau_KEEP_Luong_Minh.py"

LOCK = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_level_lock.json"
)

EXPECTED_LOCK_SHA = (
    "ad310048a4c5b239404e0902cc04fda1"
    "d73474d11a739a2ca009d2727e4390c3"
)

OLD_RESOLUTION = (
    "bf991e2ebb10a5952f07ca81caa24ead"
    "e98bca5f9e44beded54ae17c68fc373a"
)

NEW_RESOLUTION = (
    "22ca7931ec40408ced25a3bde14a9672c"
    "04e12a760a077a44bb9d65b709b1163"
)

OLD_FP = (
    "30995a02ca8fd39d9bc6aea92de01cef"
    "85a912d0644a7d9bf409e80c615c712a"
)

NEW_FP = (
    "3ff70145c42c255075bb1430ea4bc4fde"
    "8da38521f7cb344b51349a75875cd60"
)


def sha256(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


print("=" * 120)
print("TAO DRY-RUN TONG CUOI MN SAU KHI LUONG MINH = GIU NGUYEN")
print("KHONG SUA DATABASE")
print("=" * 120)

if not SOURCE.exists():
    raise RuntimeError(
        "Không tìm thấy script dry-run đã PASS trước: "
        + str(SOURCE)
    )

lock_sha = sha256(LOCK)

print(
    "Level lock SHA =",
    lock_sha,
)

if lock_sha != EXPECTED_LOCK_SHA:
    raise RuntimeError(
        "DỪNG: Level lock không đúng nền mới."
    )


text = SOURCE.read_text(
    encoding="utf-8-sig"
)


if text.count(OLD_RESOLUTION) != 1:
    raise RuntimeError(
        "DỪNG: không tìm thấy đúng 1 Resolution SHA cũ "
        "trong script dry-run."
    )


if text.count(OLD_FP) < 1:
    raise RuntimeError(
        "DỪNG: không tìm thấy fingerprint cũ "
        "trong script dry-run."
    )


text = text.replace(
    OLD_RESOLUTION,
    NEW_RESOLUTION,
)

text = text.replace(
    OLD_FP,
    NEW_FP,
)


# KPI nền cũng đã đổi từ KEEP 51 -> 52.
old_kpi = '''{
            "KEEP": 51,
            "DONE": 184,
            "READY": 5,
            "BLOCK": 0,
        }'''

new_kpi = '''{
            "KEEP": 52,
            "DONE": 184,
            "READY": 5,
            "BLOCK": 0,
        }'''


if old_kpi not in text:
    # Thử dạng indent khác của script cũ.
    old_kpi = '''{
    "KEEP": 51,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}'''

    new_kpi = '''{
    "KEEP": 52,
    "DONE": 184,
    "READY": 5,
    "BLOCK": 0,
}'''


if old_kpi not in text:
    raise RuntimeError(
        "DỪNG: không tìm thấy KPI 51/184/5/0 "
        "trong dry-run cũ."
    )


text = text.replace(
    old_kpi,
    new_kpi,
    1,
)


# Thêm khóa SHA của level lock ngay đầu script mới.
guard = f'''
# ============================================================
# KHOA LEVEL LOCK SAU KHI LUONG MINH = GIU NGUYEN
# ============================================================

_LEVEL_LOCK_AFTER_KEEP = Path(
    r"C:\\PhoCap\\data\\school_merger_registry\\qd3805_level_lock.json"
)

_EXPECTED_LEVEL_LOCK_AFTER_KEEP = (
    "{EXPECTED_LOCK_SHA}"
)

def _sha_lock_after_keep(path):
    _h = hashlib.sha256()
    with path.open("rb") as _f:
        for _b in iter(lambda: _f.read(1024 * 1024), b""):
            _h.update(_b)
    return _h.hexdigest()

if (
    _sha_lock_after_keep(_LEVEL_LOCK_AFTER_KEEP)
    != _EXPECTED_LEVEL_LOCK_AFTER_KEEP
):
    raise RuntimeError(
        "DUNG: qd3805_level_lock.json khong dung nen "
        "sau khi Luong Minh = GIU NGUYEN."
    )

'''


anchor = 'ROOT = Path(r"C:\\PhoCap")'

pos = text.find(anchor)

if pos < 0:
    raise RuntimeError(
        "DỪNG: không tìm thấy ROOT trong script cũ."
    )

end = text.find("\n", pos)

text = (
    text[:end + 1]
    + guard
    + text[end + 1:]
)


TARGET.write_text(
    text,
    encoding="utf-8",
)


print(
    "Đã tạo:",
    TARGET,
)

print(
    "Resolution SHA mới =",
    NEW_RESOLUTION,
)

print(
    "Batch FP mới       =",
    NEW_FP,
)

print(
    "KPI mới            = KEEP52 / DONE184 / READY5 / BLOCK0"
)

print()
print(
    "Bắt đầu chạy dry-run..."
)

print("=" * 120)
