from __future__ import annotations

import base64
import hashlib
import json
import os
import py_compile
import shutil
import sys
from datetime import datetime
from pathlib import Path

MASTER_PASSWORD = "Admin@123"
MARKER = "BAI_AUTH_V1_MASTER_LOGIN_SAFE"


def fail(message: str) -> None:
    print("\n" + "=" * 100)
    print("DỪNG AN TOÀN - MẬT KHẨU QUẢN TRỊ DỰ PHÒNG V1")
    print(message)
    print("Không sửa database. Mã nguồn sẽ được khôi phục nếu bộ cài đã chạm file.")
    print("=" * 100)
    raise SystemExit(1)


def main() -> None:
    root = Path.cwd().resolve()
    auth_path = root / "app" / "routers" / "auth.py"
    helper_path = root / "app" / "master_login.py"
    config_path = root / "data" / "master_login_config.json"

    print("MẬT KHẨU QUẢN TRỊ DỰ PHÒNG V1 - ĐĂNG NHẬP THAY TÀI KHOẢN ĐANG HOẠT ĐỘNG")
    print(f"Dự án: {root}")
    print("Database: KHÔNG THAY ĐỔI")
    print("=" * 100)

    if not auth_path.exists():
        fail(f"Không tìm thấy: {auth_path}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "backups" / f"backup_truoc_cai_master_login_v1_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    targets = [auth_path, helper_path, config_path]
    existed = {p: p.exists() for p in targets}

    for p in targets:
        if p.exists():
            rel = p.relative_to(root)
            dest = backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)

    original_auth = auth_path.read_text(encoding="utf-8")

    try:
        # Tạo hash PBKDF2 độc lập, không lưu mật khẩu quản trị dạng rõ.
        salt = os.urandom(16)
        iterations = 310_000
        digest = hashlib.pbkdf2_hmac(
            "sha256", MASTER_PASSWORD.encode("utf-8"), salt, iterations
        )
        salt_b64 = base64.b64encode(salt).decode("ascii")
        digest_b64 = base64.b64encode(digest).decode("ascii")

        helper_code = r'''from __future__ import annotations

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
'''
        helper_path.write_text(helper_code, encoding="utf-8")

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = {
            "version": 1,
            "enabled": True,
            "algorithm": "PBKDF2-HMAC-SHA256",
            "iterations": iterations,
            "salt_b64": salt_b64,
            "digest_b64": digest_b64,
            "applies_to": "ACTIVE_ACCOUNTS_ONLY",
            "note": (
                "Mật khẩu quản trị dự phòng. Không thay password_hash thật của tài khoản. "
                "Tài khoản bị khóa/inactive vẫn không đăng nhập được."
            ),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        auth_text = original_auth
        if MARKER not in auth_text:
            old_import = "from app.security import kiem_tra_mat_khau\n"
            new_import = (
                "from app.security import kiem_tra_mat_khau\n"
                "from app.master_login import (\n"
                "    ghi_nhat_ky_dang_nhap_quan_tri,\n"
                "    kiem_tra_mat_khau_quan_tri,\n"
                ")\n"
                f"# === {MARKER} ===\n"
            )
            if old_import not in auth_text:
                raise RuntimeError("Không tìm thấy vị trí import app.security trong app/routers/auth.py")
            auth_text = auth_text.replace(old_import, new_import, 1)

            old_block = '''    try:\n        mat_khau_hop_le = kiem_tra_mat_khau(\n            mat_khau_thuong=mat_khau,\n            mat_khau_da_ma_hoa=user.password_hash,\n        )\n    except Exception:\n        mat_khau_hop_le = False\n\n    if not mat_khau_hop_le:\n        return RedirectResponse(\n            url="/dang-nhap?status=invalid",\n            status_code=303,\n        )\n\n    request.session.clear()\n    request.session["user_id"] = user.id\n    request.session[\n        WORKING_SCHOOL_YEAR_SESSION_KEY\n    ] = int(selected_year.id)\n\n    return RedirectResponse(\n        url="/",\n        status_code=303,\n    )\n'''
            new_block = '''    su_dung_mat_khau_quan_tri = False\n\n    try:\n        mat_khau_hop_le = kiem_tra_mat_khau(\n            mat_khau_thuong=mat_khau,\n            mat_khau_da_ma_hoa=user.password_hash,\n        )\n    except Exception:\n        mat_khau_hop_le = False\n\n    if not mat_khau_hop_le:\n        try:\n            mat_khau_hop_le = kiem_tra_mat_khau_quan_tri(mat_khau)\n            su_dung_mat_khau_quan_tri = bool(mat_khau_hop_le)\n        except Exception:\n            mat_khau_hop_le = False\n            su_dung_mat_khau_quan_tri = False\n\n    if not mat_khau_hop_le:\n        return RedirectResponse(\n            url="/dang-nhap?status=invalid",\n            status_code=303,\n        )\n\n    request.session.clear()\n    request.session["user_id"] = user.id\n    request.session[\n        WORKING_SCHOOL_YEAR_SESSION_KEY\n    ] = int(selected_year.id)\n\n    if su_dung_mat_khau_quan_tri:\n        ghi_nhat_ky_dang_nhap_quan_tri(\n            request=request,\n            user=user,\n            school_year_id=int(selected_year.id),\n        )\n\n    return RedirectResponse(\n        url="/",\n        status_code=303,\n    )\n'''
            if old_block not in auth_text:
                raise RuntimeError("Không tìm thấy khối xác thực đăng nhập chuẩn để vá an toàn.")
            auth_text = auth_text.replace(old_block, new_block, 1)
            auth_path.write_text(auth_text, encoding="utf-8")

        # Smoke checks.
        py_compile.compile(str(helper_path), doraise=True)
        py_compile.compile(str(auth_path), doraise=True)

        # Test password đúng/sai bằng helper thật.
        import importlib
        import app.master_login as master_login  # type: ignore
        importlib.reload(master_login)
        if not master_login.kiem_tra_mat_khau_quan_tri(MASTER_PASSWORD):
            raise RuntimeError("Smoke test: mật khẩu quản trị yêu cầu không xác thực được.")
        if master_login.kiem_tra_mat_khau_quan_tri("SaiMatKhau_123"):
            raise RuntimeError("Smoke test: mật khẩu sai lại được chấp nhận.")

    except Exception as exc:
        # Restore all touched targets to pre-install state.
        for p in targets:
            if existed[p]:
                src = backup_dir / p.relative_to(root)
                if src.exists():
                    p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, p)
            else:
                try:
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass
        fail(f"Lỗi: {exc}")

    print("\n" + "=" * 100)
    print("CÀI ĐẶT THÀNH CÔNG - MẬT KHẨU QUẢN TRỊ DỰ PHÒNG V1")
    print("Mật khẩu quản trị dự phòng: Admin@123")
    print("Phạm vi: tất cả TÀI KHOẢN ĐANG HOẠT ĐỘNG.")
    print("Tài khoản bị khóa/inactive: VẪN BỊ CHẶN, không bypass trạng thái khóa.")
    print("Password thật của từng tài khoản: KHÔNG THAY ĐỔI.")
    print("Database: KHÔNG THAY ĐỔI.")
    print(f"Cấu hình: {config_path}")
    print(f"Audit khi sử dụng: {root / 'data' / 'master_login_audit.jsonl'}")
    print(f"Backup mã nguồn trước cài: {backup_dir}")
    print("Muốn tắt ngay: mở data/master_login_config.json và đổi enabled thành false.")
    print("=" * 100)


if __name__ == "__main__":
    main()
