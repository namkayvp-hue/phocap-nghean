from __future__ import annotations

import base64
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_9_v1b_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

PAYLOAD = {'app/household_import_models.py': 'H4sIAGIig2oC/8VYy07bQBTd5ytGWREpSiktCCFlQQsIWkElyq6qRpPxTTxlPGPmAbjqvp9QddluWFSoe7Logi/Jn/TacR5AgNgRJovE8czcc+7k+M656RodEUq73nkDlBIRxdo4wpTSjjmhla3VuumcgDlwIoLRjNH3fNieSCZ5CFEymrCFE45wQpPsaAOip95D0iR7ykEPTJN8dEaoXpMcwbm7HaKlTTQKs8/iGIImibJPyrX0kcpB8VYLebAOs2Neb/C6Vqtxyawlu9pbCLUM9rLBd7qzlI43NmoEX/V6fX/Q/+mIHFxdKOLE4OpfTFQ4uLpUpCskEI6X+R3MeND/S6QY9L97EuI6Elz/Vi0MUsuiUYpEJCgWpfvYJnXrzSkkNBxxoEOG9Ivu2HyNCDbyBD8J5T7jqhtpLmWT0tdo28Y3YiMiZhJ6DEn7yHiYjDDvtFDcQATKTY01sncEx+ABjHGtMw/gDn+lpfXlxgTAK3Hi4Raq8lKm6bd3mLRT94UK4PwOi3xrOszxkM69CRMdLdWnI4BtiaDeKE2Gh1pLmgAzJblMAizGhOso8grKscgXL8bAx1KzAJE6CUXZ3t4Q8o0caAVzMkoD3Evnpnxms2HcaUOzJ8oqFttQu2ndPs4ml+/K8vLDFKbhjJYLwr0sAodPk1sM7tV8cNqInlBM0rSyZZtarAaszoaZklX+OGFWGCVmLiyWTnoSzJFHRh+nllRCWS1msFZ8hbIVO4Au89K1l+faxJCtrK6VSnHtddkULZ743hZVReNuivWtTXqwu3lQL12SHetBqexXS//AEVhbGHVOzdoQwGXPnH2S+CGzNGLc6ErEafSZpQ79oawO7pTJ8mapOBwYo00lcFyrrhTcYVivXCWQY0dqKdpEtOlB1bA+DiqDjUHHWLqrzDSHrDLLAJ2b4AhHdZfOMvlzV9D1udyEAQ7iFKOwiWbHLeKjUOPe8HEgtPf8uAKc2GiOJ0AVGQ2VOAunEMBIH6PFLaXPyvv+oAJOWg1xClBu3NfLb6cV+lY3/zYUwy4+ben7P8SL49An+FURfv1LYzffv2DEDfp/VC/v+XuD/qXIvF2JRj47JJ63lV+kd575x8RinTScghEuKWYhV2ZayO3Dww+H5Q3k2HA9ZUuFVoEqH3XAFGuS70jg/lqRrXzyRDIlP92RUch0F3fDdz3Vs1XYRu0/q6Yb/VEVAAA=', 'app/routers/household_updates.py': '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', 'app/templates/surveys/household_update_center_v1.html': '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', 'app/templates/surveys/household_import_detail_v1.html': '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', 'app/templates/surveys/household_statistics_v1.html': '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'}

PATCH_SURVEY_MODEL = "app/survey_models.py"
ALL_FILES = list(PAYLOAD) + [PATCH_SURVEY_MODEL]
MARK_REQUIRED = "BAI_13B_9_V1A_HOUSEHOLD_UPDATE_ROUTER"


def _decode(value: str) -> str:
    return gzip.decompress(base64.b64decode(value)).decode("utf-8")


def _read(rel: str) -> str:
    path = PROJECT / rel
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def _db_path() -> Path:
    sys.path.insert(0, str(PROJECT))
    old = Path.cwd()
    try:
        os.chdir(PROJECT)
        from app.database import DATABASE_PATH
        return Path(DATABASE_PATH)
    finally:
        os.chdir(old)
        try:
            sys.path.remove(str(PROJECT))
        except ValueError:
            pass


def _backup(db_path: Path) -> list[dict]:
    BACKUP.mkdir(parents=True, exist_ok=False)
    manifest: list[dict] = []

    for rel in ALL_FILES:
        src = PROJECT / rel
        existed = src.exists()
        manifest.append({"path": rel, "existed": existed})
        if existed:
            dst = BACKUP / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    if db_path.exists():
        dst = BACKUP / "database" / db_path.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path, dst)
        manifest.append({
            "database": True,
            "backup": str(dst.relative_to(BACKUP)),
            "existed": True,
        })

    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def _restore(manifest: list[dict], db_path: Path) -> None:
    for item in reversed(manifest):
        if item.get("database"):
            src = BACKUP / item["backup"]
            if src.exists():
                shutil.copy2(src, db_path)
            continue

        target = PROJECT / item["path"]
        if item["existed"]:
            src = BACKUP / item["path"]
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        elif target.exists() and target.is_file():
            target.unlink()


def _patch_survey_model(text_value: str) -> str:
    if "citizen_id: Mapped[str | None]" in text_value:
        return text_value

    anchor = (
        "    personal_id: Mapped[str | None] = mapped_column(\n"
        "        String(50),\n"
        "        nullable=True,\n"
        "        index=True,\n"
        "    )\n"
    )
    if anchor not in text_value:
        raise RuntimeError(
            "Không tìm thấy trường personal_id để bổ sung Căn cước công dân."
        )

    addition = (
        "\n"
        "    citizen_id: Mapped[str | None] = mapped_column(\n"
        "        String(50),\n"
        "        nullable=True,\n"
        "        index=True,\n"
        "    )\n"
    )
    return text_value.replace(anchor, anchor + addition, 1)


def _migrate_database(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        def columns(table_name: str) -> set[str]:
            return {
                row[1]
                for row in con.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            }

        people_cols = columns("survey_people")
        if "citizen_id" not in people_cols:
            con.execute(
                "ALTER TABLE survey_people "
                "ADD COLUMN citizen_id VARCHAR(50)"
            )
        con.execute(
            "CREATE INDEX IF NOT EXISTS ix_survey_people_citizen_id "
            "ON survey_people(citizen_id)"
        )

        job_cols = columns("survey_household_import_jobs")
        for name in (
            "households_created",
            "households_updated",
            "people_created",
            "people_updated",
        ):
            if name not in job_cols:
                con.execute(
                    "ALTER TABLE survey_household_import_jobs "
                    f"ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0"
                )

        con.commit()
    finally:
        con.close()


def _clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def _verify() -> None:
    main_text = _read("app/main.py")
    if MARK_REQUIRED not in main_text:
        raise RuntimeError(
            "Chưa phát hiện Bài 13B-9 V1A trong app/main.py. "
            "Dừng cài để tránh ghi đè nhầm phiên bản."
        )

    required_markers = {
        "app/routers/household_updates.py": [
            "DA_CAP_NHAT",
            "LOI_DU_LIEU",
            "_process_xlsx_job",
            "tai-mau-xlsx",
            "COMMUNE_MISMATCH",
            "IDENTIFIER_CONFLICT",
        ],
        "app/templates/surveys/household_update_center_v1.html": [
            "BÀI 13B-9 V1B",
            "Xem dữ liệu đã cập nhật",
        ],
        "app/templates/surveys/household_import_detail_v1.html": [
            "V1B:",
            "Thành viên mới",
        ],
    }
    for rel, markers in required_markers.items():
        text_value = _read(rel)
        for marker in markers:
            if marker not in text_value:
                raise RuntimeError(
                    f"Kiểm tra {rel} thiếu marker: {marker}"
                )

    for rel in (
        "app/household_import_models.py",
        "app/routers/household_updates.py",
        "app/survey_models.py",
    ):
        subprocess.run(
            [sys.executable, "-m", "py_compile", str(PROJECT / rel)],
            cwd=PROJECT,
            check=True,
        )

    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(APP / "templates"))
    )
    env.get_template("surveys/household_update_center_v1.html")
    env.get_template("surveys/household_import_detail_v1.html")
    env.get_template("surveys/household_statistics_v1.html")


def main() -> int:
    print("=" * 104)
    print("BÀI 13B-9 V1B - KIỂM TRA NỘI DUNG VÀ CẬP NHẬT CSDL HỘ DÂN")
    print("=" * 104)
    print("")
    print("V1B BỔ SUNG:")
    print(" - File .xlsx đúng mẫu được kiểm tra nội dung và cập nhật thật vào CSDL.")
    print(" - Kiểm tra năm, xã/phường, số phiếu, ngày sinh, trùng định danh/CCCD.")
    print(" - File có lỗi nghiêm trọng: KHÔNG cập nhật nửa chừng.")
    print(" - Nhiều file cùng gửi: ghi lần lượt bằng khóa tiến trình.")
    print(" - Sau thành công có nút 'Xem dữ liệu đã cập nhật'.")
    print(" - Mẫu tải xuống không tô màu, không cố định năm 2025.")
    print("")
    print("LƯU Ý:")
    print(" - .xls vẫn được tiếp nhận/lưu an toàn nhưng chưa ghi CSDL ở V1B.")
    print(" - Bộ đọc .xls chính thức sẽ làm ở V1C, không chạy macro.")
    print("")

    db_path = _db_path()
    manifest = _backup(db_path)

    try:
        for rel, encoded in PAYLOAD.items():
            target = PROJECT / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_decode(encoded), encoding="utf-8")

        survey_model_path = PROJECT / PATCH_SURVEY_MODEL
        survey_model_path.write_text(
            _patch_survey_model(_read(PATCH_SURVEY_MODEL)),
            encoding="utf-8",
        )

        _migrate_database(db_path)
        _clear_cache()
        _verify()

        print("")
        print("CAI DAT BAI 13B-9 V1B THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("Khởi động lại Uvicorn, chọn ĐÚNG đợt của xã rồi gửi file .xlsx.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        _restore(manifest, db_path)
        _clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE + DATABASE VỀ TRƯỚC V1B.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
