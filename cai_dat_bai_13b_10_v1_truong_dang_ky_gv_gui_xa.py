from __future__ import annotations

import base64
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import traceback
import zlib
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"

MAIN = APP / "main.py"
ACCESS = APP / "access_control.py"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_10_v1_{STAMP}"

MARK_MAIN = "survey_team_registration_router"
MARK_ACCESS = "BAI_13B_10_V1_ACCESS"
MARK_MENU = "BAI_13B_10_V1_MENU"

PAYLOAD = {'app/routers/survey_team_registration.py': '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', 'app/templates/survey_teams/school_participants.html': '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', 'app/templates/survey_teams/commune_submissions.html': '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'}

SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS survey_investigation_participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_batch_id INTEGER NOT NULL,
        school_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        level_code VARCHAR(20) NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE(survey_batch_id, user_id),
        FOREIGN KEY(survey_batch_id) REFERENCES survey_batches(id),
        FOREIGN KEY(school_id) REFERENCES schools(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS survey_participant_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_batch_id INTEGER NOT NULL,
        school_id INTEGER NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
        sent_at DATETIME NULL,
        sent_by_user_id INTEGER NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE(survey_batch_id, school_id),
        FOREIGN KEY(survey_batch_id) REFERENCES survey_batches(id),
        FOREIGN KEY(school_id) REFERENCES schools(id),
        FOREIGN KEY(sent_by_user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS survey_team_registration_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_batch_id INTEGER NOT NULL,
        school_id INTEGER NOT NULL,
        action VARCHAR(30) NOT NULL,
        actor_user_id INTEGER NULL,
        actor_name_snapshot VARCHAR(200) NULL,
        participant_count INTEGER NOT NULL DEFAULT 0,
        notes TEXT NULL,
        created_at DATETIME NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS
        ix_survey_investigation_participants_batch_school
    ON survey_investigation_participants(survey_batch_id, school_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS
        ix_survey_participant_submissions_batch
    ON survey_participant_submissions(survey_batch_id, status)
    """,
]


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def database_path() -> Path:
    sys.path.insert(0, str(PROJECT))
    old_cwd = Path.cwd()
    os.chdir(PROJECT)
    try:
        from app.database import DATABASE_PATH
        return Path(DATABASE_PATH)
    finally:
        os.chdir(old_cwd)
        try:
            sys.path.remove(str(PROJECT))
        except ValueError:
            pass


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)
    elif path.exists() and str(path.relative_to(PROJECT)) in PAYLOAD:
        path.unlink()


def write_payload() -> None:
    for rel, encoded in PAYLOAD.items():
        path = PROJECT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        content = zlib.decompress(base64.b64decode(encoded)).decode("utf-8")
        path.write_text(content, encoding="utf-8")


def patch_main(text_value: str) -> str:
    if MARK_MAIN in text_value:
        return text_value

    import_anchor = "from app.routers.surveys import router as surveys_router\n"
    include_anchor = "app.include_router(surveys_router)\n"
    if import_anchor not in text_value or include_anchor not in text_value:
        raise RuntimeError(
            "app/main.py không có điểm nạp surveys_router như dự kiến."
        )

    text_value = text_value.replace(
        import_anchor,
        import_anchor
        + "from app.routers.survey_team_registration import router as survey_team_registration_router\n",
        1,
    )
    text_value = text_value.replace(
        include_anchor,
        include_anchor + "app.include_router(survey_team_registration_router)\n",
        1,
    )
    return text_value


def patch_access(text_value: str) -> str:
    if MARK_ACCESS in text_value:
        return text_value

    func_pos = text_value.find("def _co_quyen_dieu_tra")
    if func_pos < 0:
        raise RuntimeError(
            "Không tìm thấy _co_quyen_dieu_tra trong access_control.py."
        )

    anchor = '        if normalized_path == "/dieu-tra/them":\n'
    pos = text_value.find(anchor, func_pos)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy điểm trước batch_match trong _co_quyen_dieu_tra."
        )

    block = """        # === BAI_13B_10_V1_ACCESS_START ===
        # Đây là bước trước khi xã phân hộ. Trường phải vào được dù
        # chưa có survey_form_investigators trong đợt mới.
        if normalized_path.startswith(
            "/dieu-tra/phan-cong-to-dieu-tra"
        ):
            return role_code in {
                COMMUNE_ROLE_CODE,
                SCHOOL_ROLE_CODE,
            }
        # === BAI_13B_10_V1_ACCESS_END ===

"""
    return text_value[:pos] + block + text_value[pos:]


def patch_menu(text_value: str) -> str:
    if MARK_MENU in text_value:
        return text_value

    anchor_text = "2.2.7. Phân công hàng loạt"
    pos = text_value.find(anchor_text)
    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy '2.2.7. Phân công hàng loạt' trong menu."
        )

    close_pos = text_value.find("</a>", pos)
    if close_pos < 0:
        raise RuntimeError("Không tìm thấy </a> sau mục 2.2.7.")
    close_pos += len("</a>")

    block = """
                    {# === BAI_13B_10_V1_MENU_START === #}
                    {% if menu_role == 'TRUONG' %}
                    <a
                        href="/dieu-tra/phan-cong-to-dieu-tra/giao-vien-tham-gia"
                        role="menuitem"
                    >
                        2.2.8. Giáo viên tham gia điều tra
                    </a>
                    {% elif menu_role == 'XA' %}
                    <a
                        href="/dieu-tra/phan-cong-to-dieu-tra/danh-sach-truong"
                        role="menuitem"
                    >
                        2.2.8. GV trường gửi về xã/phường
                    </a>
                    {% endif %}
                    {# === BAI_13B_10_V1_MENU_END === #}
"""
    return text_value[:close_pos] + "\n" + block + text_value[close_pos:]


def migrate_db(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("PRAGMA foreign_keys=ON")
        for statement in SCHEMA_SQL:
            con.execute(statement)
        con.commit()
    finally:
        con.close()


def verify_db(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        names = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for name in (
            "survey_investigation_participants",
            "survey_participant_submissions",
            "survey_team_registration_logs",
        ):
            if name not in names:
                raise RuntimeError(f"Database chưa có bảng {name}.")
    finally:
        con.close()


def verify_source() -> None:
    main = read_text(MAIN)
    access = read_text(ACCESS)
    menu = read_text(MENU)

    for marker, text_value in [
        (MARK_MAIN, main),
        ("app.include_router(survey_team_registration_router)", main),
        (MARK_ACCESS, access),
        ("/dieu-tra/phan-cong-to-dieu-tra", access),
        (MARK_MENU, menu),
        ("2.2.8. Giáo viên tham gia điều tra", menu),
        ("2.2.8. GV trường gửi về xã/phường", menu),
    ]:
        if marker not in text_value:
            raise RuntimeError(f"Kiểm tra source chưa đạt: {marker}")

    router = APP / "routers" / "survey_team_registration.py"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(MAIN),
            str(ACCESS),
            str(router),
        ],
        cwd=PROJECT,
        check=True,
    )

    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(APP / "templates")))
    env.get_template("partials/dropdown_menu_v1.html")
    env.get_template("survey_teams/school_participants.html")
    env.get_template("survey_teams/commune_submissions.html")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-10 V1 - TRƯỜNG ĐĂNG KÝ GIÁO VIÊN THAM GIA VÀ GỬI XÃ/PHƯỜNG")
    print("=" * 108)
    print("")
    print("BƯỚC 1 CỦA QUY TRÌNH TỔ ĐIỀU TRA 3 CẤP:")
    print(" - Trường chọn giáo viên đang hoạt động.")
    print(" - Lưu bản nháp.")
    print(" - Gửi danh sách về Xã/Phường.")
    print(" - Xã xem tổng hợp MN / TH / THCS của các trường đã gửi.")
    print(" - Có Thu hồi để chỉnh sửa trước khi V2 tạo tổ.")
    print("")
    print("V1 CHƯA GHÉP TỔ VÀ CHƯA CHIA HỘ.")
    print("Không thay đổi dữ liệu hộ dân hoặc phân công cũ.")
    print("")

    for path in (MAIN, ACCESS, MENU):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    db_path = database_path()

    BACKUP.mkdir(parents=True, exist_ok=False)
    source_paths = [MAIN, ACCESS, MENU] + [PROJECT / rel for rel in PAYLOAD]
    for path in source_paths:
        backup_file(path)

    db_backup = BACKUP / "database" / db_path.name
    db_backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, db_backup)

    try:
        write_payload()

        MAIN.write_text(patch_main(read_text(MAIN)), encoding="utf-8")
        ACCESS.write_text(patch_access(read_text(ACCESS)), encoding="utf-8")
        MENU.write_text(patch_menu(read_text(MENU)), encoding="utf-8")

        migrate_db(db_path)
        verify_db(db_path)
        verify_source()
        clear_cache()

        print("")
        print("CAI DAT BAI 13B-10 V1 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("TRƯỜNG: 2 -> 2.2 -> 2.2.8 Giáo viên tham gia điều tra")
        print("XÃ: 2 -> 2.2 -> 2.2.8 GV trường gửi về xã/phường")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        for path in source_paths:
            restore_file(path)
        if db_backup.exists():
            shutil.copy2(db_backup, db_path)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE VÀ DATABASE VỀ TRƯỚC V1.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
