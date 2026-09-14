from pathlib import Path

ROOT = Path(r"C:\PhoCap")
path = ROOT / "app" / "routers" / "surveys.py"
text = path.read_text(encoding="utf-8")

compile(text, str(path), "exec")

start = text.find("def hien_thi_trang_cap_nhat_phieu(")
end = text.find("\n\n@router.get(", start)
assert start >= 0 and end > start

helper = text[start:end]
assert 'can_confirm_commune = role_code in {"SO", "XA"}' in helper
assert '"can_confirm_commune": can_confirm_commune' in helper
assert '"nguoi_dung": nguoi_dung' in helper

print("OK PYTHON: app\\routers\\surveys.py")
print("OK QUYỀN: Sở và Xã nhận đúng quyền xác nhận xã/phường.")
print("BÀI 11B-7A.3 ĐÃ SẴN SÀNG.")
print("Không có dữ liệu nào được thêm, sửa hoặc xóa.")
