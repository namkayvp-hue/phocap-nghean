from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
CONFIG_PATH = PROJECT_DIR / "data" / "master_login_config.json"
AUDIT_PATH = PROJECT_DIR / "data" / "master_login_audit.jsonl"


def _load_config() -> dict[str, Any]:
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": False}
    return raw if isinstance(raw, dict) else {"enabled": False}


def kiem_tra_mat_khau_quan_tri(mat_khau: str) -> bool:
    """
    Mật khẩu quản trị dự phòng chỉ là phương thức xác thực phụ.
    Nó KHÔNG thay đổi password_hash thật của bất kỳ tài khoản nào.
    Tài khoản bị khóa vẫn bị chặn bởi router đăng nhập trước khi vào đây.
    """
    cfg = _load_config()
    if not bool(cfg.get("enabled", False)):
        return False

    if not mat_khau:
        return False

    try:
        iterations = int(cfg.get("iterations") or 0)
        salt = base64.b64decode(str(cfg.get("salt_b64") or ""))
        expected = base64.b64decode(str(cfg.get("digest_b64") or ""))
        if iterations < 100_000 or not salt or not expected:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", mat_khau.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def ghi_nhat_ky_dang_nhap_quan_tri(
    *,
    request,
    user,
    school_year_id: int | None,
) -> None:
    """Ghi audit mỗi lần dùng mật khẩu quản trị dự phòng. Không ghi mật khẩu."""
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        client_ip = ""
        if getattr(request, "client", None) is not None:
            client_ip = str(getattr(request.client, "host", "") or "")

        user_agent = ""
        try:
            user_agent = str(request.headers.get("user-agent", "") or "")[:500]
        except Exception:
            pass

        role_code = ""
        try:
            if getattr(user, "role", None) is not None:
                role_code = str(getattr(user.role, "code", "") or "")
        except Exception:
            pass

        payload = {
            "event": "MASTER_LOGIN_SUCCESS",
            "at": datetime.now().isoformat(timespec="seconds"),
            "user_id": int(getattr(user, "id", 0) or 0),
            "username": str(getattr(user, "username", "") or ""),
            "full_name": str(getattr(user, "full_name", "") or ""),
            "role_code": role_code,
            "commune_id": getattr(user, "commune_id", None),
            "school_id": getattr(user, "school_id", None),
            "school_year_id": school_year_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
        }
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Audit không được làm hỏng đăng nhập hợp lệ.
        pass
