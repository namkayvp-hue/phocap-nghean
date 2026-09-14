from __future__ import annotations
import json
from pathlib import Path

root = Path.cwd().resolve()
path = root / "data" / "master_login_config.json"
if not path.exists():
    print(f"Không tìm thấy cấu hình: {path}")
    raise SystemExit(1)
raw = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(raw, dict):
    print("Cấu hình không hợp lệ.")
    raise SystemExit(1)
raw["enabled"] = False
path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
print("ĐÃ TẮT mật khẩu quản trị dự phòng. Không cần sửa database.")
