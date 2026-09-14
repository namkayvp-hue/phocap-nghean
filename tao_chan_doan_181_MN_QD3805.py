from pathlib import Path
import shutil

ROOT = Path(r"C:\PhoCap")

SRC = ROOT / "cai_dat_MN_QD3805_tach_3_dac_thu_va_khoa_ma_an_toan.py"
DST = ROOT / "chan_doan_181_MN_QD3805.py"

if not SRC.exists():
    raise SystemExit("Không tìm thấy file nguồn: " + str(SRC))

# Chỉ tạo bản sao chẩn đoán.
shutil.copy2(SRC, DST)

text = DST.read_text(encoding="utf-8")

needle = '''    if int(counts.get("DONE") or 0) != 181:
'''

if needle not in text:
    raise RuntimeError(
        "Không tìm thấy khóa DONE=181 trong bản chẩn đoán. "
        "File cài chính KHÔNG bị thay đổi."
    )

debug = '''    # ============================================================
    # CHẨN ĐOÁN RIÊNG - KHÔNG THAY ĐỔI LOGIC
    # ============================================================
    diagnostic_path = (
        ROOT / "exports" / "chan_doan_181_MN_QD3805.json"
    )
    diagnostic_path.parent.mkdir(parents=True, exist_ok=True)

    diagnostic_payload = {
        "counts": counts,
        "before_preview": before_preview,
        "after_preview": after,
        "expected": {
            "DONE": 181,
            "READY_PLUS_BLOCK": 8,
            "MN_KEEP": 51,
            "MN_CROSS": 0,
            "MN_SAME_SPECIAL": 3,
            "MN_UNRESOLVED": 1,
        },
    }

    diagnostic_path.write_text(
        json.dumps(
            diagnostic_payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 118)
    print("CHẨN ĐOÁN TRƯỚC KHÓA DONE=181")
    print("counts =", json.dumps(counts, ensure_ascii=False))
    print("mn_keep =", after.get("mn_keep"))
    print("mn_cross =", after.get("mn_cross"))
    print("mn_same_special =", after.get("mn_same_special"))
    print("mn_unresolved =", after.get("mn_unresolved"))
    print("FILE CHẨN ĐOÁN =", diagnostic_path)
    print("=" * 118)

'''

text = text.replace(needle, debug + needle, 1)
DST.write_text(text, encoding="utf-8")

print("=" * 118)
print("ĐÃ TẠO BẢN CHẨN ĐOÁN RIÊNG")
print("File gốc GIỮ NGUYÊN :", SRC)
print("File chẩn đoán      :", DST)
print("KHÔNG sửa Excel nguồn.")
print("KHÔNG ghi phocap.db.")
print("=" * 118)
