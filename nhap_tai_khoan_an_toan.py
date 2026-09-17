from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import importlib
import os
import re
import socket
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.database import DATABASE_PATH


PROJECT_DIR = Path(__file__).resolve().parent
EXPORT_ROOT = PROJECT_DIR / "exports"
BACKUP_DIR = PROJECT_DIR / "data" / "backups"
EXPECTED_PLAN_COUNT = 12_397
EXPECTED_HOLD_COUNT = 22
PROGRESS_STEP = 250

PLAN_FILENAME = "14_ke_hoach_nhap_tai_khoan_an_toan.csv"
ERROR_FILENAME = "15_loi_ke_hoach_nhap_tai_khoan.csv"
HOLD_FILENAME = "16_danh_sach_22_ma_giu_lai.csv"
RESULT_FILENAME = "17_ket_qua_nhap_tai_khoan.csv"
MINUTES_FILENAME = "18_bien_ban_nhap_tai_khoan.txt"

REQUIRED_PLAN_COLUMNS = {
    "username",
    "initial_password",
    "full_name",
    "staff_code",
    "role_id",
    "role_code",
    "role_name",
    "commune_id",
    "commune_name",
    "school_id",
    "school_name",
    "is_active",
}

REQUIRED_USER_COLUMNS = {
    "id",
    "username",
    "password_hash",
    "full_name",
    "role_id",
    "commune_id",
    "school_id",
    "is_active",
    "created_at",
}


@dataclass(frozen=True)
class HasherSpec:
    kind: str
    label: str
    module_name: str = ""
    attribute_name: str = ""
    rounds: int = 0
    method: str = ""


@dataclass
class PreflightResult:
    report_dir: Path
    plans: list[dict[str, str]]
    before_user_count: int
    hasher_spec: HasherSpec
    sample_seconds: float
    worker_count: int
    existing_hash_scheme: str


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def normalize_username(value: Any) -> str:
    return re.sub(r"[^a-z0-9._-]+", "", clean_text(value).lower())


def parse_required_int(value: Any, label: str) -> int:
    text = clean_text(value)
    if not text:
        raise ValueError(f"{label} bị để trống.")
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{label} không phải số nguyên: {text}") from exc


def parse_optional_int(value: Any, label: str) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{label} không phải số nguyên: {text}") from exc


def latest_report_dir() -> Path:
    candidates = [
        path
        for path in EXPORT_ROOT.glob("kiem_tra_giao_vien_*")
        if path.is_dir() and (path / PLAN_FILENAME).exists()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"Không tìm thấy thư mục báo cáo có {PLAN_FILENAME} trong {EXPORT_ROOT}."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp bắt buộc: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        headers = list(reader.fieldnames or [])
        return headers, list(reader)


def write_csv(path: Path, headers: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def server_running_on_port(port: int = 8000) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def identify_hash_scheme(hash_value: str) -> str:
    value = clean_text(hash_value)
    if value.startswith(("$2a$", "$2b$", "$2y$")):
        match = re.match(r"^\$2[aby]\$(\d\d)\$", value)
        rounds = match.group(1) if match else "?"
        return f"bcrypt (cost {rounds})"
    if value.startswith("$pbkdf2-sha256$"):
        return "passlib pbkdf2_sha256"
    if value.startswith("$argon2"):
        return "argon2"
    if value.startswith("scrypt:"):
        return "werkzeug scrypt"
    if value.startswith("pbkdf2:"):
        return "werkzeug pbkdf2"
    if re.fullmatch(r"[0-9a-fA-F]{64}", value):
        return "sha256 hex"
    if value:
        return "không xác định"
    return "không có dữ liệu"


def _module_candidates() -> list[str]:
    return [
        "app.security",
        "app.auth",
        "app.routers.auth",
        "app.reset_password",
    ]


def discover_hasher(existing_hash: str) -> HasherSpec:
    # Nạp model trước để tránh lỗi thứ tự mapper trong một số phiên bản dự án.
    try:
        importlib.import_module("app.models")
    except Exception:
        pass

    function_names = (
        "hash_password",
        "get_password_hash",
        "ma_hoa_mat_khau",
        "bam_mat_khau",
        "tao_password_hash",
        "tao_ma_bam_mat_khau",
    )
    context_names = (
        "pwd_context",
        "password_context",
        "crypt_context",
    )

    for module_name in _module_candidates():
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue

        for function_name in function_names:
            function = getattr(module, function_name, None)
            if callable(function):
                try:
                    result = function("KiemTra@2026")
                except Exception:
                    continue
                if isinstance(result, str) and result and result != "KiemTra@2026":
                    return HasherSpec(
                        kind="callable",
                        label=f"{module_name}.{function_name}",
                        module_name=module_name,
                        attribute_name=function_name,
                    )

        for context_name in context_names:
            context = getattr(module, context_name, None)
            if context is None or not callable(getattr(context, "hash", None)):
                continue
            try:
                result = context.hash("KiemTra@2026")
            except Exception:
                continue
            if isinstance(result, str) and result:
                return HasherSpec(
                    kind="context",
                    label=f"{module_name}.{context_name}.hash",
                    module_name=module_name,
                    attribute_name=context_name,
                )

    if existing_hash.startswith(("$2a$", "$2b$", "$2y$")):
        match = re.match(r"^\$2[aby]\$(\d\d)\$", existing_hash)
        rounds = int(match.group(1)) if match else 12
        try:
            import bcrypt  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Mật khẩu hiện tại dùng bcrypt nhưng môi trường chưa có gói bcrypt."
            ) from exc
        return HasherSpec(
            kind="bcrypt",
            label=f"bcrypt trực tiếp, cost={rounds}",
            rounds=rounds,
        )

    if existing_hash.startswith("$pbkdf2-sha256$"):
        try:
            from passlib.hash import pbkdf2_sha256  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Mật khẩu hiện tại dùng passlib pbkdf2_sha256 nhưng môi trường thiếu passlib."
            ) from exc
        return HasherSpec(kind="passlib_pbkdf2", label="passlib.pbkdf2_sha256")

    if existing_hash.startswith("$argon2"):
        try:
            from passlib.hash import argon2  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Mật khẩu hiện tại dùng argon2 nhưng môi trường thiếu thư viện tương ứng."
            ) from exc
        return HasherSpec(kind="passlib_argon2", label="passlib.argon2")

    if existing_hash.startswith("scrypt:"):
        return HasherSpec(kind="werkzeug", label="werkzeug scrypt", method="scrypt")

    if existing_hash.startswith("pbkdf2:"):
        method = existing_hash.split("$", 1)[0]
        return HasherSpec(kind="werkzeug", label=f"werkzeug {method}", method=method)

    if re.fullmatch(r"[0-9a-fA-F]{64}", existing_hash):
        return HasherSpec(
            kind="sha256",
            label="sha256 hex theo hệ thống hiện tại",
        )

    raise RuntimeError(
        "Không xác định được hàm băm mật khẩu tương thích với chức năng đăng nhập. "
        "Chương trình đã dừng trước khi sửa cơ sở dữ liệu."
    )


def hash_one_password(password: str, spec_dict: dict[str, Any]) -> str:
    spec = HasherSpec(**spec_dict)

    if spec.kind == "callable":
        module = importlib.import_module(spec.module_name)
        function = getattr(module, spec.attribute_name)
        result = function(password)
    elif spec.kind == "context":
        module = importlib.import_module(spec.module_name)
        context = getattr(module, spec.attribute_name)
        result = context.hash(password)
    elif spec.kind == "bcrypt":
        import bcrypt

        result = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=spec.rounds),
        ).decode("utf-8")
    elif spec.kind == "passlib_pbkdf2":
        from passlib.hash import pbkdf2_sha256

        result = pbkdf2_sha256.hash(password)
    elif spec.kind == "passlib_argon2":
        from passlib.hash import argon2

        result = argon2.hash(password)
    elif spec.kind == "werkzeug":
        from werkzeug.security import generate_password_hash

        result = generate_password_hash(password, method=spec.method)
    elif spec.kind == "sha256":
        result = hashlib.sha256(password.encode("utf-8")).hexdigest()
    else:
        raise RuntimeError(f"Kiểu hàm băm không được hỗ trợ: {spec.kind}")

    if not isinstance(result, str) or not result or result == password:
        raise RuntimeError("Hàm băm trả về kết quả không hợp lệ.")
    return result


def _try_project_verifier(
    password: str,
    password_hash: str,
    spec: HasherSpec,
) -> bool:
    """Thử đúng hàm xác minh mật khẩu đang dùng trong dự án."""

    verifier_names = (
        "verify_password",
        "verify_password_hash",
        "verify_hashed_password",
        "check_password",
        "check_password_hash",
        "kiem_tra_mat_khau",
        "kiem_tra_password",
        "xac_minh_mat_khau",
        "xac_thuc_mat_khau",
    )
    context_names = (
        "pwd_context",
        "password_context",
        "crypt_context",
        "password_hasher",
    )

    module_names: list[str] = []
    if spec.module_name:
        module_names.append(spec.module_name)
    for module_name in _module_candidates():
        if module_name not in module_names:
            module_names.append(module_name)

    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue

        for context_name in context_names:
            context = getattr(module, context_name, None)
            verify = getattr(context, "verify", None)
            if not callable(verify):
                continue
            try:
                if bool(verify(password, password_hash)):
                    return True
            except Exception:
                pass

        for verifier_name in verifier_names:
            verifier = getattr(module, verifier_name, None)
            if not callable(verifier):
                continue

            # Phần lớn dự án dùng (mật khẩu thường, mã băm).
            # Werkzeug dùng thứ tự ngược lại, vì vậy thử an toàn cả hai.
            attempts = (
                (password_hash, password),
                (password, password_hash),
            ) if verifier_name == "check_password_hash" else (
                (password, password_hash),
                (password_hash, password),
            )

            for first, second in attempts:
                try:
                    if bool(verifier(first, second)):
                        return True
                except Exception:
                    continue

    return False


def verify_own_sample(password: str, password_hash: str, spec: HasherSpec) -> bool:
    """Xác minh mẫu bằng đúng cơ chế của dự án trước khi thử quy tắc chung."""

    try:
        # Ưu tiên tuyệt đối hàm verify/check đang có trong chính dự án.
        # Điều này đặc biệt quan trọng khi mã băm có dạng 64 ký tự hex
        # nhưng dự án dùng salt/secret riêng, không phải SHA-256 thuần.
        if _try_project_verifier(password, password_hash, spec):
            return True

        if spec.kind == "context":
            module = importlib.import_module(spec.module_name)
            context = getattr(module, spec.attribute_name)
            verify = getattr(context, "verify", None)
            if callable(verify) and bool(verify(password, password_hash)):
                return True

        # Một số phiên bản dự án chỉ có hàm hash_password và đăng nhập
        # bằng cách băm lại mật khẩu rồi so sánh. Khi hàm băm mang tính
        # xác định, gọi lại cùng hàm phải cho đúng cùng kết quả.
        if spec.kind == "callable":
            module = importlib.import_module(spec.module_name)
            function = getattr(module, spec.attribute_name)
            second_hash = function(password)
            if (
                isinstance(second_hash, str)
                and second_hash
                and hmac.compare_digest(second_hash, password_hash)
            ):
                return True

        if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
            import bcrypt

            return bcrypt.checkpw(
                password.encode("utf-8"),
                password_hash.encode("utf-8"),
            )
        if password_hash.startswith("$bcrypt-sha256$"):
            from passlib.hash import bcrypt_sha256

            return bool(bcrypt_sha256.verify(password, password_hash))
        if password_hash.startswith("$pbkdf2-sha256$"):
            from passlib.hash import pbkdf2_sha256

            return bool(pbkdf2_sha256.verify(password, password_hash))
        if password_hash.startswith("$argon2"):
            from passlib.hash import argon2

            return bool(argon2.verify(password, password_hash))
        if password_hash.startswith("$5$"):
            from passlib.hash import sha256_crypt

            return bool(sha256_crypt.verify(password, password_hash))
        if password_hash.startswith("$6$"):
            from passlib.hash import sha512_crypt

            return bool(sha512_crypt.verify(password, password_hash))
        if password_hash.startswith(("scrypt:", "pbkdf2:")):
            from werkzeug.security import check_password_hash

            return bool(check_password_hash(password_hash, password))
        if password_hash.startswith(("pbkdf2_sha256$", "argon2$")):
            try:
                from django.contrib.auth.hashers import check_password

                return bool(check_password(password, password_hash))
            except Exception:
                pass
        if re.fullmatch(r"[0-9a-fA-F]{64}", password_hash):
            return hmac.compare_digest(
                hashlib.sha256(password.encode("utf-8")).hexdigest(),
                password_hash,
            )
    except Exception:
        return False
    return False

def estimate_workers() -> int:
    cpu_count = os.cpu_count() or 2
    return max(1, min(4, cpu_count - 1 if cpu_count > 1 else 1))


def validate_password(password: str) -> bool:
    return (
        len(password) >= 12
        and any(char.islower() for char in password)
        and any(char.isupper() for char in password)
        and any(char.isdigit() for char in password)
        and any(not char.isalnum() for char in password)
    )


def database_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(str(DATABASE_PATH), timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def preflight() -> PreflightResult:
    if server_running_on_port(8000):
        raise RuntimeError(
            "Máy chủ đang chạy tại cổng 8000. Hãy dừng Uvicorn bằng Ctrl + C rồi chạy lại."
        )

    database_path = Path(DATABASE_PATH)
    if not database_path.exists():
        raise FileNotFoundError(f"Không tìm thấy cơ sở dữ liệu: {database_path}")

    report_dir = latest_report_dir()
    plan_headers, plans = read_csv(report_dir / PLAN_FILENAME)
    _, error_rows = read_csv(report_dir / ERROR_FILENAME)
    _, hold_rows = read_csv(report_dir / HOLD_FILENAME)

    missing_headers = sorted(REQUIRED_PLAN_COLUMNS - set(plan_headers))
    if missing_headers:
        raise ValueError(
            "Tệp kế hoạch thiếu các cột: " + ", ".join(missing_headers)
        )
    if len(plans) != EXPECTED_PLAN_COUNT:
        raise ValueError(
            f"Tệp kế hoạch có {len(plans)} dòng, phải đúng {EXPECTED_PLAN_COUNT}."
        )
    if error_rows:
        raise ValueError(
            f"Tệp {ERROR_FILENAME} còn {len(error_rows)} lỗi. Không được nhập."
        )
    if len(hold_rows) != EXPECTED_HOLD_COUNT:
        raise ValueError(
            f"Danh sách giữ lại có {len(hold_rows)} mã, phải đúng {EXPECTED_HOLD_COUNT}."
        )

    usernames: list[str] = []
    staff_codes: list[str] = []
    plan_errors: list[str] = []

    for index, row in enumerate(plans, start=2):
        username = normalize_username(row.get("username"))
        staff_code = clean_text(row.get("staff_code"))
        password = clean_text(row.get("initial_password"))
        full_name = clean_text(row.get("full_name"))

        if not username:
            plan_errors.append(f"Dòng {index}: thiếu username")
        if not staff_code:
            plan_errors.append(f"Dòng {index}: thiếu staff_code")
        if not full_name:
            plan_errors.append(f"Dòng {index}: thiếu full_name")
        if not validate_password(password):
            plan_errors.append(f"Dòng {index}: mật khẩu khởi tạo không đạt yêu cầu")

        usernames.append(username)
        staff_codes.append(staff_code)

    duplicate_usernames = sorted(
        username for username in set(usernames) if usernames.count(username) > 1
    )
    duplicate_staff_codes = sorted(
        code for code in set(staff_codes) if staff_codes.count(code) > 1
    )
    if duplicate_usernames:
        plan_errors.append(
            f"Có {len(duplicate_usernames)} username bị lặp trong kế hoạch"
        )
    if duplicate_staff_codes:
        plan_errors.append(
            f"Có {len(duplicate_staff_codes)} mã định danh bị lặp trong kế hoạch"
        )
    if plan_errors:
        preview = "\n".join(f"  - {item}" for item in plan_errors[:20])
        raise ValueError(f"Kế hoạch chưa hợp lệ:\n{preview}")

    connection = database_connection()
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Cơ sở dữ liệu không đạt integrity_check: {integrity}")

        foreign_key_issues = list(connection.execute("PRAGMA foreign_key_check"))
        if foreign_key_issues:
            raise RuntimeError(
                f"Cơ sở dữ liệu đang có {len(foreign_key_issues)} lỗi khóa ngoại."
            )

        user_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(users)")
        }
        missing_user_columns = sorted(REQUIRED_USER_COLUMNS - user_columns)
        if missing_user_columns:
            raise RuntimeError(
                "Bảng users thiếu các cột: " + ", ".join(missing_user_columns)
            )

        before_user_count = int(
            connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        )
        existing_usernames = {
            normalize_username(row[0])
            for row in connection.execute("SELECT username FROM users")
        }
        conflicts = sorted(set(usernames) & existing_usernames)
        if conflicts:
            raise RuntimeError(
                f"Có {len(conflicts)} tên đăng nhập trong kế hoạch đã tồn tại. "
                "Có thể bước nhập đã được chạy trước đó; chương trình dừng để tránh nhập trùng."
            )

        role_map = {
            int(row["id"]): clean_text(row["code"]).upper()
            for row in connection.execute("SELECT id, code FROM roles")
        }
        communes = {
            int(row["id"]): clean_text(row["name"])
            for row in connection.execute("SELECT id, name FROM communes")
        }
        schools = {
            int(row["id"]): {
                "name": clean_text(row["name"]),
                "commune_id": (
                    int(row["commune_id"])
                    if row["commune_id"] is not None
                    else None
                ),
            }
            for row in connection.execute(
                "SELECT id, name, commune_id FROM schools"
            )
        }

        catalog_errors: list[str] = []
        for index, row in enumerate(plans, start=2):
            role_id = parse_required_int(row.get("role_id"), f"Dòng {index} role_id")
            role_code = clean_text(row.get("role_code")).upper()
            commune_id = parse_optional_int(
                row.get("commune_id"), f"Dòng {index} commune_id"
            )
            school_id = parse_required_int(
                row.get("school_id"), f"Dòng {index} school_id"
            )
            is_active = parse_required_int(
                row.get("is_active"), f"Dòng {index} is_active"
            )

            if role_map.get(role_id) != role_code:
                catalog_errors.append(
                    f"Dòng {index}: role_id {role_id} không khớp role_code {role_code}"
                )
            if commune_id is not None and commune_id not in communes:
                catalog_errors.append(
                    f"Dòng {index}: commune_id {commune_id} không tồn tại"
                )
            school = schools.get(school_id)
            if school is None:
                catalog_errors.append(
                    f"Dòng {index}: school_id {school_id} không tồn tại"
                )
            elif school["commune_id"] != commune_id:
                catalog_errors.append(
                    f"Dòng {index}: trường không thuộc đúng xã/phường"
                )
            if is_active != 1:
                catalog_errors.append(f"Dòng {index}: is_active phải bằng 1")

        if catalog_errors:
            preview = "\n".join(f"  - {item}" for item in catalog_errors[:20])
            raise RuntimeError(f"Lỗi danh mục trong kế hoạch:\n{preview}")

        password_row = connection.execute(
            """
            SELECT password_hash
            FROM users
            WHERE password_hash IS NOT NULL AND TRIM(password_hash) <> ''
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
        if password_row is None:
            raise RuntimeError(
                "Không có mật khẩu mẫu trong bảng users để xác định cơ chế đăng nhập."
            )
        existing_hash = clean_text(password_row[0])
    finally:
        connection.close()

    existing_hash_scheme = identify_hash_scheme(existing_hash)
    hasher_spec = discover_hasher(existing_hash)

    sample_password = "KiemTra@2026"
    started = time.perf_counter()
    sample_hash = hash_one_password(sample_password, asdict(hasher_spec))
    sample_seconds = max(time.perf_counter() - started, 0.001)
    if not verify_own_sample(sample_password, sample_hash, hasher_spec):
        raise RuntimeError(
            "Hàm băm đã tìm thấy nhưng không tự xác minh được mật khẩu mẫu. "
            "Chương trình dừng trước khi nhập."
        )

    return PreflightResult(
        report_dir=report_dir,
        plans=plans,
        before_user_count=before_user_count,
        hasher_spec=hasher_spec,
        sample_seconds=sample_seconds,
        worker_count=estimate_workers(),
        existing_hash_scheme=existing_hash_scheme,
    )


def create_database_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = Path(DATABASE_PATH).suffix or ".db"
    backup_path = BACKUP_DIR / f"truoc_nhap_12397_tai_khoan_{timestamp}{suffix}"

    source = sqlite3.connect(str(DATABASE_PATH), timeout=60)
    destination = sqlite3.connect(str(backup_path), timeout=60)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    check = sqlite3.connect(str(backup_path))
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"Bản sao lưu không hợp lệ: {result}")
    finally:
        check.close()

    return backup_path


def hash_all_passwords(
    plans: list[dict[str, str]],
    spec: HasherSpec,
    worker_count: int,
) -> list[str]:
    passwords = [clean_text(row["initial_password"]) for row in plans]
    spec_dict = asdict(spec)
    tasks = ((password, spec_dict) for password in passwords)
    hashes: list[str] = []

    print()
    print("ĐANG MÃ HÓA MẬT KHẨU")
    print("-" * 78)
    print(f"Số tài khoản: {len(passwords)}")
    print(f"Số tiến trình xử lý: {worker_count}")
    print("Trong giai đoạn này cơ sở dữ liệu chưa bị thay đổi.")
    print()

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        for index, password_hash in enumerate(
            executor.map(
                _hash_task,
                tasks,
                chunksize=10,
            ),
            start=1,
        ):
            hashes.append(password_hash)
            if index % PROGRESS_STEP == 0 or index == len(passwords):
                print(f"Đã mã hóa: {index}/{len(passwords)}")

    if len(hashes) != len(plans):
        raise RuntimeError("Số mật khẩu đã mã hóa không khớp số tài khoản.")
    return hashes


def _hash_task(payload: tuple[str, dict[str, Any]]) -> str:
    password, spec_dict = payload
    return hash_one_password(password, spec_dict)


def chunked(values: list[str], size: int = 800) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def import_accounts(
    preflight_result: PreflightResult,
    password_hashes: list[str],
    backup_path: Path,
) -> tuple[int, int]:
    plans = preflight_result.plans
    usernames = [normalize_username(row["username"]) for row in plans]
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    rows_to_insert = []
    for row, password_hash in zip(plans, password_hashes, strict=True):
        rows_to_insert.append(
            (
                normalize_username(row["username"]),
                password_hash,
                clean_text(row["full_name"]),
                parse_required_int(row["role_id"], "role_id"),
                parse_optional_int(row["commune_id"], "commune_id"),
                parse_required_int(row["school_id"], "school_id"),
                1,
                created_at,
            )
        )

    connection = database_connection()
    committed = False
    try:
        connection.execute("BEGIN IMMEDIATE")

        conflicts: list[str] = []
        for username_chunk in chunked(usernames):
            placeholders = ",".join("?" for _ in username_chunk)
            conflicts.extend(
                row[0]
                for row in connection.execute(
                    f"SELECT username FROM users WHERE username IN ({placeholders})",
                    username_chunk,
                )
            )
        if conflicts:
            raise RuntimeError(
                f"Phát hiện {len(conflicts)} username đã tồn tại ngay trước khi nhập."
            )

        before_count = int(
            connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        )
        if before_count != preflight_result.before_user_count:
            raise RuntimeError(
                "Số tài khoản đã thay đổi sau bước kiểm tra. "
                "Chương trình hủy giao dịch để tránh sai lệch."
            )

        connection.executemany(
            """
            INSERT INTO users (
                username,
                password_hash,
                full_name,
                role_id,
                commune_id,
                school_id,
                is_active,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )

        after_count = int(
            connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        )
        if after_count != before_count + EXPECTED_PLAN_COUNT:
            raise RuntimeError(
                f"Số tài khoản sau nhập không đúng: {after_count}; "
                f"dự kiến {before_count + EXPECTED_PLAN_COUNT}."
            )

        inserted_count = 0
        for username_chunk in chunked(usernames):
            placeholders = ",".join("?" for _ in username_chunk)
            inserted_count += int(
                connection.execute(
                    f"SELECT COUNT(*) FROM users WHERE username IN ({placeholders})",
                    username_chunk,
                ).fetchone()[0]
            )
        if inserted_count != EXPECTED_PLAN_COUNT:
            raise RuntimeError(
                f"Chỉ xác minh được {inserted_count}/{EXPECTED_PLAN_COUNT} tài khoản."
            )

        foreign_key_issues = list(connection.execute("PRAGMA foreign_key_check"))
        if foreign_key_issues:
            raise RuntimeError(
                f"Sau khi nhập phát hiện {len(foreign_key_issues)} lỗi khóa ngoại."
            )

        connection.commit()
        committed = True
        return before_count, after_count
    except Exception:
        if not committed:
            connection.rollback()
        raise
    finally:
        connection.close()


def create_result_reports(
    result: PreflightResult,
    backup_path: Path,
    before_count: int,
    after_count: int,
    elapsed_seconds: float,
) -> tuple[Path, Path]:
    result_path = result.report_dir / RESULT_FILENAME
    minutes_path = result.report_dir / MINUTES_FILENAME

    report_rows = []
    for row in result.plans:
        report_rows.append(
            {
                "stt": row.get("stt", ""),
                "username": row.get("username", ""),
                "full_name": row.get("full_name", ""),
                "staff_code": row.get("staff_code", ""),
                "role_code": row.get("role_code", ""),
                "role_name": row.get("role_name", ""),
                "commune_id": row.get("commune_id", ""),
                "commune_name": row.get("commune_name", ""),
                "school_id": row.get("school_id", ""),
                "school_name": row.get("school_name", ""),
                "status": "DA_NHAP_THANH_CONG",
            }
        )

    write_csv(
        result_path,
        [
            "stt",
            "username",
            "full_name",
            "staff_code",
            "role_code",
            "role_name",
            "commune_id",
            "commune_name",
            "school_id",
            "school_name",
            "status",
        ],
        report_rows,
    )

    content = "\n".join(
        [
            "BIÊN BẢN NHẬP TÀI KHOẢN GIÁO VIÊN AN TOÀN",
            "=" * 78,
            f"Thời điểm hoàn thành: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            f"Cơ sở dữ liệu: {DATABASE_PATH}",
            f"Bản sao lưu trước nhập: {backup_path}",
            f"Thư mục báo cáo: {result.report_dir}",
            f"Cơ chế mã hóa mật khẩu: {result.hasher_spec.label}",
            f"Số tài khoản trước nhập: {before_count}",
            f"Số tài khoản đã nhập: {EXPECTED_PLAN_COUNT}",
            f"Số tài khoản sau nhập: {after_count}",
            f"Số mã xung đột giữ lại: {EXPECTED_HOLD_COUNT}",
            f"Thời gian thực hiện: {elapsed_seconds:.1f} giây",
            "Kết quả: THÀNH CÔNG - giao dịch đã COMMIT.",
            "Tệp kết quả không chứa mật khẩu khởi tạo.",
        ]
    )
    minutes_path.write_text(content, encoding="utf-8")
    return result_path, minutes_path


def print_preflight(result: PreflightResult) -> None:
    serial_seconds = result.sample_seconds * EXPECTED_PLAN_COUNT
    parallel_seconds = serial_seconds / max(result.worker_count, 1) * 1.25

    print()
    print("KẾT QUẢ KIỂM TRA TRƯỚC KHI NHẬP")
    print("-" * 78)
    print(f"Thư mục báo cáo: {result.report_dir}")
    print(f"Số tài khoản trong kế hoạch: {len(result.plans)}")
    print(f"Số tài khoản hiện có trong users: {result.before_user_count}")
    print(f"Kiểu mật khẩu hiện có: {result.existing_hash_scheme}")
    print(f"Hàm mã hóa sẽ sử dụng: {result.hasher_spec.label}")
    print(f"Thời gian thử một mật khẩu: {result.sample_seconds:.3f} giây")
    print(f"Số tiến trình dự kiến: {result.worker_count}")
    print(
        "Thời gian mã hóa ước tính: khoảng "
        f"{max(1, round(parallel_seconds / 60))} phút "
        "(có thể nhanh hoặc chậm hơn tùy máy)."
    )
    print()
    print("TRẠNG THÁI: ĐỦ ĐIỀU KIỆN SAO LƯU VÀ NHẬP 12.397 TÀI KHOẢN.")
    print("CHƯA CÓ DỮ LIỆU NÀO ĐƯỢC THAY ĐỔI.")


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(
        description="Kiểm tra, sao lưu và nhập 12.397 tài khoản an toàn."
    )
    parser.add_argument(
        "--thuc-hien",
        action="store_true",
        help="Thực sự sao lưu, mã hóa mật khẩu và nhập tài khoản.",
    )
    args = parser.parse_args()

    print("=" * 78)
    print("BÀI 11B-6A.9B - XÁC MINH ĐÚNG HÀM BĂM CỦA DỰ ÁN")
    print("=" * 78)
    print(
        "Chế độ: "
        + ("THỰC HIỆN NHẬP" if args.thuc_hien else "CHỈ KIỂM TRA, CHƯA NHẬP")
    )

    try:
        result = preflight()
        print_preflight(result)

        if not args.thuc_hien:
            print()
            print("HOÀN TẤT KIỂM TRA: chưa tạo, sửa hoặc xóa tài khoản nào.")
            return 0

        print()
        print("ĐANG TẠO BẢN SAO LƯU CƠ SỞ DỮ LIỆU...")
        backup_path = create_database_backup()
        print(f"Đã tạo bản sao lưu: {backup_path}")

        started = time.perf_counter()
        password_hashes = hash_all_passwords(
            result.plans,
            result.hasher_spec,
            result.worker_count,
        )

        print()
        print("ĐANG MỞ GIAO DỊCH VÀ GHI TÀI KHOẢN...")
        before_count, after_count = import_accounts(
            result,
            password_hashes,
            backup_path,
        )
        elapsed_seconds = time.perf_counter() - started

        result_path, minutes_path = create_result_reports(
            result,
            backup_path,
            before_count,
            after_count,
            elapsed_seconds,
        )

        print()
        print("KẾT QUẢ NHẬP TÀI KHOẢN")
        print("-" * 78)
        print(f"Số tài khoản trước nhập: {before_count}")
        print(f"Số tài khoản đã nhập: {EXPECTED_PLAN_COUNT}")
        print(f"Số tài khoản sau nhập: {after_count}")
        print(f"Số mã xung đột giữ lại: {EXPECTED_HOLD_COUNT}")
        print(f"Bản sao lưu: {backup_path}")
        print(f"Báo cáo kết quả: {result_path}")
        print(f"Biên bản nhập: {minutes_path}")
        print()
        print("THÀNH CÔNG: giao dịch đã COMMIT đủ 12.397 tài khoản.")
        return 0

    except KeyboardInterrupt:
        print()
        print("ĐÃ DỪNG THEO YÊU CẦU. Nếu giao dịch chưa COMMIT thì dữ liệu đã được rollback.")
        return 130
    except Exception as exc:
        print()
        print("KHÔNG THÀNH CÔNG:", exc)
        print("Không tiếp tục chạy lệnh nhập. Nếu đã mở giao dịch, giao dịch đã được rollback.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
