from __future__ import annotations

import hashlib
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment


ALLOWED_AUTH_HASHES = {
    "b2ded4751bcfe13e731e5bcff0a61b396b67fab077619e60a4a911fe48f18f47",
    "5e36b107b858f55e19eeccc2a3020183f8442694aaf8d7a515e74a2b4ea3c44e",
}

EXPECTED_LOGIN_HASH = (
    "2a4b60cceba0e32bcf8062a301b95f7b21156cfa2a581a61693617c0be72270f"
)

AUTH_START = '''        role_codes = LOGIN_SCOPE_ROLE_CODES[scope]

'''

AUTH_END = '''    return _json_no_store(
        {
            "ok": False,
            "items": [],
            "detail": "Loại dữ liệu không hợp lệ.",
        }
    )
'''

AUTH_REPLACEMENT = '''        role_codes = LOGIN_SCOPE_ROLE_CODES[scope]

        # === BAI_13B_11_16_2_V2_3_LOGIN_ACCOUNT_SCOPE_START ===
        stmt = (
            select(User)
            .join(Role, User.role_id == Role.id)
            .options(
                selectinload(User.role),
                selectinload(User.commune),
                selectinload(User.school),
            )
            .where(
                User.is_active.is_(True),
            )
            .order_by(
                User.full_name,
                User.username,
            )
            .limit(50)
        )

        if scope == "SO":
            stmt = stmt.where(
                or_(
                    Role.code.in_(role_codes),
                    User.role_id == 1,
                    User.username.ilike("admin.sogddt"),
                    User.username.ilike("so_%"),
                )
            )

        elif scope == "XA":
            selected_commune_id = _safe_id(commune_id)
            if selected_commune_id is None:
                return _json_no_store(
                    {"ok": True, "items": []}
                )

            stmt = stmt.where(
                User.commune_id == selected_commune_id,
                or_(
                    Role.code.in_(role_codes),
                    User.role_id == 2,
                    User.username.ilike("xa_%"),
                ),
            )

        elif scope in {"TRUONG", "GIAO_VIEN"}:
            selected_school_id = _safe_id(school_id)
            if selected_school_id is None:
                return _json_no_store(
                    {"ok": True, "items": []}
                )

            stmt = stmt.where(
                User.school_id == selected_school_id,
                Role.code.in_(role_codes),
            )

        if q_text:
            stmt = stmt.where(
                or_(
                    User.username.ilike(q_like),
                    User.full_name.ilike(q_like),
                )
            )

        rows = list(db.scalars(stmt).all())

        items = []
        seen_user_ids: set[int] = set()

        for item in rows:
            if int(item.id) in seen_user_ids:
                continue
            seen_user_ids.add(int(item.id))

            role_name = (
                str(item.role.name or "")
                if item.role is not None
                else ""
            )

            location = ""
            if item.school is not None:
                location = str(item.school.name or "")
            elif item.commune is not None:
                location = str(item.commune.name or "")

            sub_parts = [
                part
                for part in (
                    str(item.full_name or ""),
                    role_name,
                    location,
                )
                if part
            ]

            items.append(
                {
                    "id": int(item.id),
                    "value": str(item.username or ""),
                    "text": str(item.username or ""),
                    "subtext": " · ".join(sub_parts),
                }
            )

        return _json_no_store(
            {
                "ok": True,
                "items": items,
            }
        )
        # === BAI_13B_11_16_2_V2_3_LOGIN_ACCOUNT_SCOPE_END ===

'''

LOGIN_OLD_SO_AUTO = '''                if (
                    items.length === 1
                    && !query
                ) {
                    selectAccount(items[0]);
                    return;
                }

                renderList(
'''

LOGIN_NEW_SO_AUTO = '''                if (!query) {
                    const adminAccount =
                        currentScope === "SO"
                        ? items.find(
                            function (item) {
                                return String(
                                    item.value || ""
                                ).toLowerCase()
                                    === "admin.sogddt";
                            }
                        )
                        : null;

                    if (adminAccount) {
                        selectAccount(adminAccount);
                        return;
                    }

                    if (items.length === 1) {
                        selectAccount(items[0]);
                        return;
                    }
                }

                renderList(
'''

LOGIN_OLD_SUBMIT = '''            form.addEventListener(
                "submit",
                function (event) {
                    if (!scope.value) {
                        event.preventDefault();
                        alert(
                            "Hãy chọn cấp đăng nhập."
                        );
                        scope.focus();
                        return;
                    }

                    if (
                        (
                            scope.value === "XA"
                            || scope.value === "TRUONG"
                            || scope.value === "GIAO_VIEN"
                        )
                        && !communeId.value
                    ) {
                        event.preventDefault();
                        alert(
                            "Hãy chọn xã/phường trong danh sách gợi ý."
                        );
                        communeInput.focus();
                        return;
                    }

                    if (
                        (
                            scope.value === "TRUONG"
                            || scope.value === "GIAO_VIEN"
                        )
                        && !schoolId.value
                    ) {
                        event.preventDefault();
                        alert(
                            "Hãy chọn trường trong danh sách gợi ý."
                        );
                        schoolInput.focus();
                        return;
                    }

                    if (!username.value) {
                        event.preventDefault();
                        alert(
                            "Hãy chọn tài khoản trong danh sách gợi ý."
                        );
                        accountInput.focus();
                        return;
                    }

                    saveRemembered();
                }
            );
'''

LOGIN_NEW_SUBMIT = '''            async function resolveTypedAccount() {
                const typed =
                    String(accountInput.value || "")
                    .trim();

                if (!typed) {
                    return false;
                }

                const currentScope = scope.value;

                const data =
                    await api({
                        loai: "accounts",
                        cap: currentScope,
                        commune_id: communeId.value || "",
                        school_id: schoolId.value || "",
                        q: typed
                    });

                const items = data.items || [];
                const typedLower = typed.toLowerCase();

                const exact = items.find(
                    function (item) {
                        return String(
                            item.value || ""
                        ).trim().toLowerCase()
                            === typedLower;
                    }
                );

                if (exact) {
                    selectAccount(exact);
                    return true;
                }

                if (items.length === 1) {
                    selectAccount(items[0]);
                    return true;
                }

                return false;
            }

            form.addEventListener(
                "submit",
                async function (event) {
                    event.preventDefault();

                    if (!scope.value) {
                        alert(
                            "Hãy chọn cấp đăng nhập."
                        );
                        scope.focus();
                        return;
                    }

                    if (
                        (
                            scope.value === "XA"
                            || scope.value === "TRUONG"
                            || scope.value === "GIAO_VIEN"
                        )
                        && !communeId.value
                    ) {
                        alert(
                            "Hãy chọn xã/phường trong danh sách gợi ý."
                        );
                        communeInput.focus();
                        return;
                    }

                    if (
                        (
                            scope.value === "TRUONG"
                            || scope.value === "GIAO_VIEN"
                        )
                        && !schoolId.value
                    ) {
                        alert(
                            "Hãy chọn trường trong danh sách gợi ý."
                        );
                        schoolInput.focus();
                        return;
                    }

                    if (!username.value) {
                        const resolved =
                            await resolveTypedAccount();

                        if (!resolved) {
                            alert(
                                "Hãy chọn tài khoản trong danh sách gợi ý."
                            );
                            accountInput.focus();
                            return;
                        }
                    }

                    saveRemembered();

                    HTMLFormElement.prototype.submit.call(
                        form
                    );
                }
            );
'''

MARK_AUTH = "BAI_13B_11_16_2_V2_3_LOGIN_ACCOUNT_SCOPE_START"
MARK_LOGIN = "async function resolveTypedAccount()"


def normalized_sha256(path: Path) -> str:
    raw = path.read_bytes()
    normalized = (
        raw.replace(b"\r\n", b"\n")
        .replace(b"\r", b"\n")
    )
    return hashlib.sha256(normalized).hexdigest()


def db_check(path: Path) -> tuple[str, int]:
    if not path.is_file():
        return "missing", 0

    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )
        fk_count = len(
            list(
                conn.execute(
                    "PRAGMA foreign_key_check"
                )
            )
        )
        return integrity, fk_count
    finally:
        conn.close()


def replace_between(
    text: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(
            "Không tìm thấy điểm bắt đầu khối tài khoản."
        )

    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(
            "Không tìm thấy điểm kết thúc khối tài khoản."
        )

    return text[:start] + replacement + text[end:]


def main() -> int:
    root = Path(r"C:\PhoCap")
    auth_path = root / "app" / "routers" / "auth.py"
    login_path = root / "app" / "templates" / "auth" / "login.html"
    db_path = root / "data" / "phocap.db"

    if not auth_path.is_file():
        root = Path.cwd()
        auth_path = root / "app" / "routers" / "auth.py"
        login_path = root / "app" / "templates" / "auth" / "login.html"
        db_path = root / "data" / "phocap.db"

    print(
        "BÀI 13B-11-16.2 V2.3 - "
        "CHỐT SỞ/XÃ + TỰ NHẬN TÀI KHOẢN ĐÃ GÕ"
    )
    print("=" * 100)
    print(f"Dự án: {root}")

    for path in (auth_path, login_path):
        if not path.is_file():
            print("DỪNG AN TOÀN: thiếu file " + str(path))
            return 2

    auth_text = auth_path.read_text(encoding="utf-8")
    login_text = login_path.read_text(encoding="utf-8")

    if MARK_AUTH in auth_text and MARK_LOGIN in login_text:
        print()
        print("V2.3 đã có trong mã nguồn. Không cài lặp.")
        return 0

    auth_hash = normalized_sha256(auth_path)
    login_hash = normalized_sha256(login_path)

    print(f"app/routers/auth.py: {auth_hash}")
    print(f"app/templates/auth/login.html: {login_hash}")

    if auth_hash not in ALLOWED_AUTH_HASHES:
        print()
        print(
            "DỪNG AN TOÀN: auth.py đã khác V2/V2.2 "
            "mà bộ cài này hỗ trợ."
        )
        return 3

    if login_hash != EXPECTED_LOGIN_HASH:
        print()
        print(
            "DỪNG AN TOÀN: login.html đã khác bản V2 "
            "đang được sửa."
        )
        return 4

    integrity, fk_count = db_check(db_path)
    print(f"Database integrity_check: {integrity}")
    print(f"Database foreign_key_check: {fk_count} lỗi")

    if (
        db_path.is_file()
        and (
            integrity.lower() != "ok"
            or fk_count != 0
        )
    ):
        print()
        print("DỪNG AN TOÀN: database chưa đạt kiểm tra.")
        return 5

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (
        root
        / "exports"
        / (
            "backup_truoc_bai_13b_11_16_2_v2_3_"
            + stamp
        )
    )

    backup_auth = (
        backup_dir
        / "app"
        / "routers"
        / "auth.py"
    )
    backup_login = (
        backup_dir
        / "app"
        / "templates"
        / "auth"
        / "login.html"
    )

    backup_auth.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    backup_login.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(auth_path, backup_auth)
    shutil.copy2(login_path, backup_login)

    if db_path.is_file():
        backup_db = (
            backup_dir
            / "data"
            / "phocap.db"
        )
        backup_db.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.copy2(db_path, backup_db)

    print()
    print(f"Đã backup: {backup_dir}")

    try:
        auth_new = replace_between(
            auth_text,
            AUTH_START,
            AUTH_END,
            AUTH_REPLACEMENT,
        )

        if login_text.count(LOGIN_OLD_SO_AUTO) != 1:
            raise RuntimeError(
                "Không tìm thấy đúng 1 khối tự chọn tài khoản."
            )

        login_new = login_text.replace(
            LOGIN_OLD_SO_AUTO,
            LOGIN_NEW_SO_AUTO,
            1,
        )

        if login_new.count(LOGIN_OLD_SUBMIT) != 1:
            raise RuntimeError(
                "Không tìm thấy đúng 1 khối submit đăng nhập."
            )

        login_new = login_new.replace(
            LOGIN_OLD_SUBMIT,
            LOGIN_NEW_SUBMIT,
            1,
        )

        auth_path.write_text(
            auth_new,
            encoding="utf-8",
        )
        login_path.write_text(
            login_new,
            encoding="utf-8",
        )

        py_compile.compile(
            str(auth_path),
            doraise=True,
        )

        Environment().parse(
            login_path.read_text(
                encoding="utf-8"
            )
        )

        if MARK_AUTH not in auth_path.read_text(encoding="utf-8"):
            raise RuntimeError("Thiếu marker backend V2.3.")

        if MARK_LOGIN not in login_path.read_text(encoding="utf-8"):
            raise RuntimeError("Thiếu marker frontend V2.3.")

    except Exception as exc:
        shutil.copy2(backup_auth, auth_path)
        shutil.copy2(backup_login, login_path)

        print()
        print(
            "CÀI ĐẶT LỖI - "
            "ĐÃ TỰ KHÔI PHỤC auth.py và login.html"
        )
        print(f"Lỗi: {exc}")
        return 6

    integrity_after, fk_after = db_check(db_path)

    report_path = (
        root
        / "exports"
        / (
            "bao_cao_dang_nhap_v2_3_"
            + stamp
            + ".txt"
        )
    )

    report_lines = [
        "BÁO CÁO BÀI 13B-11-16.2 V2.3",
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Dự án: {root}",
        "",
        "ĐÃ CHỐT:",
        (
            "1. Sở/Quản trị: hỗ trợ role code hiện tại + "
            "role_id lịch sử + admin.sogddt."
        ),
        (
            "2. Khi mở cấp Sở, nếu có admin.sogddt thì "
            "tự chọn ngay."
        ),
        (
            "3. Xã/phường: hỗ trợ role code XA + role_id=2 "
            "+ username xa_*, nhưng vẫn bắt buộc đúng commune_id."
        ),
        (
            "4. Nếu xã chỉ có một tài khoản thì tự chọn ngay "
            "sau khi chọn xã."
        ),
        (
            "5. Nếu trình duyệt tự điền đúng username, bấm Đăng nhập "
            "không còn bắt buộc nhấp lại gợi ý."
        ),
        (
            "6. Trường/Giáo viên giữ nguyên phạm vi đang chạy đúng."
        ),
        "7. Không thay đổi cấu trúc database.",
        "",
        f"Backup: {backup_dir}",
        (
            "Database integrity_check sau cài: "
            f"{integrity_after}"
        ),
        (
            "Database foreign_key_check sau cài: "
            f"{fk_after} lỗi"
        ),
    ]

    report_path.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 100)
    print("CÀI ĐẶT THÀNH CÔNG")
    print("=" * 100)
    print("Đã sửa đúng 2 file:")
    print(" - app/routers/auth.py")
    print(" - app/templates/auth/login.html")
    print("Không thay đổi cấu trúc database.")
    print(f"Báo cáo: {report_path}")
    print()
    print("Khởi động lại Uvicorn và kiểm tra:")
    print("1. Sở/Quản trị: admin.sogddt phải tự hiện/chọn.")
    print("2. Xã/phường: chọn xã -> tài khoản xa_* phải tự hiện/chọn.")
    print("3. Trường/Giáo viên: giữ nguyên như V2.1.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
