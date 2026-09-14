from pathlib import Path
from jinja2 import Environment

ROOT = Path(r"C:\PhoCap")
router_path = ROOT / "app" / "routers" / "surveys.py"
template_path = ROOT / "app" / "templates" / "surveys" / "form_status.html"

router_text = router_path.read_text(encoding="utf-8")
template_text = template_path.read_text(encoding="utf-8")

compile(router_text, str(router_path), "exec")
Environment().parse(template_text)

assert 'can_confirm_commune = role_code in {"SO", "XA"}' in router_text
assert "if can_confirm_commune:" in router_text
assert "Bạn chỉ có quyền xem trạng thái này." in template_text
assert "{% if can_confirm_commune %}" in template_text

print("OK PYTHON: app\\routers\\surveys.py")
print("OK HTML:   app\\templates\\surveys\\form_status.html")
print("BÀI 11B-7A.2 ĐÃ SẴN SÀNG.")
print("Không có dữ liệu nào được thêm, sửa hoặc xóa.")
