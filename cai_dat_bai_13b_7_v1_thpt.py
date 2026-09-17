from __future__ import annotations

import base64
import gzip
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
MAIN = APP / "main.py"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"

PAYLOAD = {'app/thpt_reference_models.py': 'H4sIAAqDgWoC/72Xz2/jRBTH7/krRj4lknGbIi4r5dB26YKACtHCZbWyJvZLPKo9447H7VrivuJGxQmtECzRCokfWlZwig8cstr/w/8Jb8Y/4ibuEpDZXBJ7nj/vO/Nmnr+ZSRER152lKpXguoRFsZCKUM6FoooJngwGMx3jUwWKRVBH1NfVcHIZ0tALIMrqgCMhQqDcJidCApvzjyCzyYdcwRykTc6UZHxuk885u0zhGPMoSRlXmzRHyKgmfkLjGHybRObb9USYRsiXEJZKAxZXajDAQYF0SpNG8BH+HgwGXkiThJx/8On5mRegxM9gBhK4B0MdMLo3IPixLMt836c8IFGRP/eICmhEvIAVy79SouTr34v8Oz43IBIWy+cZUUX+C5mxEPCJ5TMcC3XQU0a8Iv+JkrMi/94ZGOxRsVzgOF/9kJFXN0X+racRv8XkysRr9ZHwIUycUiO5Wv1akvk8LfJveJkWxeRPOOZdPmOGexGs/kSut/qDPF4t9uKgVqlkkb/Uc0h1MhuvBd69CBiZllKqPHj1QpGpiSKeiKKUg8t8x9BPzdSj1aI1/Vc3+tJIMjIqcoVTAeoWsxnzGA3dxNxEHD6ln1/grNnqZ04uEKycZuHND9fF6oXAaaR35YRYKohVjZB1zRKrHexSOU9M9NDc1p/N/bUeMekqYAZU4n7ywbI7xzuGtLKJlV66RhgqKiHlA63YUflzVE6L+feqbfwQxTxCqbc287A5H7FkEZWZewHZ5FymYBOaKsG4JyECrsy9kUFuTqFJgDPeTlCeu+HB/sgmPA1DvW6TExommIFxHx5vk3eGvvsvoHr5doT+E9Vgt3dZe6HJl+RUcNhO0pRp3aSGVdETh/nWaF3IRoIpR3N7reRWoblpSVqPotynci1nqk/GXXqapnkrW8VU2JKxHLqBYXzK1Y57yYcZTUM12d9cx1ELm6jUx43VJ5jDdd/YcgspOpu5RnY/QiPKKcb1uqhA8f3VKzITqQrclOO+cv8HPERxKDKAXktlNqsUIuqzXGtoDBJrB30twRqcQMT6ZirQRgSbel/HQKTSg9076XsdnXTUJklxvaO0Lkgaa0vou3RdjNojvqHv1pOsQx0urtfNVfCSesfwxluh3X/nkvqQNEpClqiHlnZND/RAY/qsR1pb20GupU2pd+HGIk5xEJKJtfVq92jiIWxi0TDU5QpBwTtCxgHlrSghfTyo02zSkd4xMq1Gecud3g7sMqfnpdtTDB1UUOQ3jIz398bjvfFBZTNP2o7Rw5CvjDVEI/o1+fj1iyL/8fQBGs/8aYxODURFsds2Uml/VoeUHhLNmqEPx/uHYxtzHh44jjNyyBdo9q7QxqITTjN0psp4W5RV8dAmviQJQ0ddAufopRc72T6zSv27Pm3a8B2/YfnaJbnb7FWIzeC35fZK6W+md3qbbhutrY6Np63cwxPr+PDs+PD++532p3XWuv1Pc/z+UzPZdoy9G563bXXudHvbS9Bye2WRGk7HP9at1rXZscomaI0GfwPg+nLf5g8AAA==', 'app/survey_age_scope.py': 'H4sIAAqDgWoC/32SQWvbMBTH7/oUj+ySFCckDLJi6kKadF0OTctIR2AModlOLKglY8thoe2H6GGHHQZtx45lg52aHHbw2PfwN5kkO46TJvNBtt/7/5+k33vjkPuA8TgWcehiDNQPeCiAMMYFEZSzCKGx0jhEuIL67lKh/hF6AZZlwVGnj1svj/Ar/K6Fe2d4eHHWx73+8QUevu0ohdQNJn9/pouvFJzkiU3A9tLFrTBlog7n8vsz2On8MYAJTe45OOniu21CE/7cpvPfDFr7IGIpogaI5JF5SvxNpqfJncw1dJVR8ouAnzzp0j9M5cnd7eY2t8wre7up7NYhDLVEb+XJzy82dNP5A7zp9CHw0vm9D1PaQOi8e9LDp/0B7pwcgwXNPNAZ5YHWPhqddkuKZaBQtJsIIccdg6DMwyLmFAtCMZuQWVUtOJJxUwOGaxhw5hqg48IjPrY96sZZtgb1Q6BM5CoTgXzoGIoiQKNSRj2hK/vMdBCV/quFYGOjxswlYZGsr0pvJqrVTafPmfCenbzhkFkNDmB10zWhDihJTdeu5aQC5Z9KTp7LNbGqWszS5TULh9rifSRCAz5yfvmhAKLEO1lcVQKPY5sEFRNek8tI0q584gT7sTxxvAzeoDKvq6JIybw2GQdWtqt8lwfEWBnX9iiPTMlaGpzMebMNSEEua+OOGUJb2pspDLSFnrSt6OYo9bGs/87ts4ZnjYxsHriR9G7vZG0HXJWTdNRrRW5vL6u2JPIPogVoycMEAAA=', 'app/routers/thpt_reference.py': 'H4sIAAqDgWoC/+VXS2/jNhC+61cQAhaQAFtOA7QHAyq6aBfdFn1snfRQBAZBS5TNRCJlkkJiZPe/d0iRkiwrGzfIYRfVIZGG3ww5w28eLqSoEMZFoxtJMUasqoXUiHAuNNFMcBUEhcEURGlSMw94++GXlWg0lTP0E60pz9UM/dVQeZihFd03VOkjtURSVYMxqryB99e//7ZywmOoplVdwt5867G/Mn5LLq9bOVUtXO1LUmY7Wh08rGh4NkNC4hlStKSZHgMTISsPvqJKgXseyngpSO58JXWd5ESTDVHU47dU43zTr+tdrbGkBZWUZxRXIqdl59z1+w/XP0uS05UHzKzsKtsJUXbCIAikDSJK+4BGNVhlD2m40LIRfDs3O4UzpMlWpTeh+Zp3+4brONA+LmBlFKkoZxKcE/KQhnDoRQcN4yC4+vPv1Y/v8D/v3q5AM7y8uPx2Dn++C+FYP7TnSsDrKITN/fXhrCRKpcPLi4OcFignfIerJsPmfFGA4JEtD5aeEDMr3S+R0sZhy5YIdElT6tRsUpEHXFK+1bv0m8uLuMXnm6W/K1ByXIva2wBIvLSoO3q4FzI3fqAwuRWMR/sE9mF1FCeqLpmOYnDZQIFkEAbKNYDbg1qpZUE0cUlxh0nudyCawiTKfuMDJRJnQAWUpmgQ34ENUdusioa0mzS5NfxR8VBV5lTizeFzJzCbJ0RlkVN0TrPCh2jZuzwIRPfufOxA5oGMOhaY57kzsJLd0agI3zy6jT+9Cd2VnmmGk+osM32E/A1bfZMOJVM6yjdgkZREQtC9m3HScAasBHaQsuy4oaHolbjVB3XGde94Z+Y4Fo44pvYkmWj4JIcSlsfxVGifCcFTfHrS//7K0EXQi1q/bO6+wC3VVJNODaxi6/oX4KPSTd5S+nW9dHa/AD9Lxu9o/hWQ9LxkF0XBMtZlHWZ5whSG6SP6Q3D6mVSfCI9rOzDKcNS1usR3Q9+weudch0rlsEGZx5SeNHR1ZHHc6pOdrsqwx2aCa/qg08ejk4Z82wiG84Zvw6XfCCImato2VdLoHW4UleNyFu5BwRW70Yo7EKy7t/G6aCTMIuZCAPPkVYRA9YrIA2AeT+7IbYIt7QExLImnNxq22X8MtrIJrM+hkelWOoF3TPfwI+Ifwz/1n+41Hg8xCxgtF2ZKmSuS7cJ2agEZtpOLkQ1Gl9ceUtD8e9uLbnKW6RswDWPq5hZScr3+6uaXM4YQ27n/50OIFPem104PH3bmGFarm059VEZYDsxnoAfVeZTFxkO/OHB6hDIOjFBGNEKdVmGvc7oyyLXurYAqbODQjazndmE9mYN3O8EG6Wc+B5k3cMTm4IvzC9oi+ohMD/E51nXMiSb5H9IneNW2+AyDje6Q0K4kzCb64At/WcQ+NV14mLJBWw6aZMvQdXAWYa1xII/932415m0/MHa4gWzcq4aDV4c/ko4ZT+/xtNbJylNUtnDD5TYoLmKO1P8CxUkU2DMRAAA=', 'app/templates/schools/thpt_reference.html': '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'}
RECORDS_B64 = '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'
SOURCE_NAME = "Thong_ke_mang_luoi_lop_HS_GV_THPT.xlsx"
SOURCE_YEAR = "2025-2026"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_7_v1_thpt_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

NEW_FILES = list(PAYLOAD.keys())
PATCH_FILES = [
    "app/main.py",
    "app/templates/partials/dropdown_menu_v1.html",
]
ALL_FILES = PATCH_FILES + NEW_FILES


def read(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup_files() -> list[dict]:
    BACKUP.mkdir(parents=True, exist_ok=False)
    manifest = []
    for rel in ALL_FILES:
        src = PROJECT / rel
        existed = src.exists()
        manifest.append({"path": rel, "existed": existed})
        if existed:
            dst = BACKUP / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def restore_files(manifest: list[dict]) -> None:
    for item in reversed(manifest):
        target = PROJECT / item["path"]
        if item["existed"]:
            src = BACKUP / item["path"]
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        elif target.exists() and target.is_file():
            target.unlink()


def write_new_files() -> None:
    for rel, encoded in PAYLOAD.items():
        target = PROJECT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gzip.decompress(base64.b64decode(encoded)))


def patch_main(text: str) -> str:
    import_marker = "BAI_13B_7_V1_THPT_ROUTER_IMPORT"
    include_marker = "BAI_13B_7_V1_THPT_ROUTER_INCLUDE"

    if import_marker not in text:
        anchor = "from app.routers.schools import router as schools_router"
        if anchor not in text:
            raise RuntimeError("Không tìm thấy import schools_router trong app/main.py.")
        text = text.replace(
            anchor,
            anchor
            + "\n# === " + import_marker + " ==="
            + "\nfrom app.routers.thpt_reference import router as thpt_reference_router",
            1,
        )

    if include_marker not in text:
        anchor = "app.include_router(schools_router)"
        if anchor not in text:
            raise RuntimeError("Không tìm thấy app.include_router(schools_router).")
        text = text.replace(
            anchor,
            anchor
            + "\n# === " + include_marker + " ==="
            + "\napp.include_router(thpt_reference_router)",
            1,
        )

    return text


def patch_menu(text: str) -> str:
    marker = "BAI_13B_7_V1_MENU_THPT"
    if marker in text:
        return text

    candidates = [
        '<a href="/truong?cap=THCS" role="menuitem">1.2.4. Danh mục trường THCS</a>',
        '<a href="/truong?cap=THCS" role="menuitem">1.2.4. Danh mục trường THCS</a>\n',
    ]
    anchor = next((item for item in candidates if item in text), None)
    if anchor is None:
        raise RuntimeError(
            "Không tìm thấy menu Danh mục trường THCS hiện tại. "
            "Dừng để không chèn nhầm vị trí."
        )

    insertion = (
        anchor.rstrip("\n")
        + "\n                            {# === " + marker + " === #}"
        + '\n                            <a href="/truong-thpt" role="menuitem">1.2.5. Danh mục trường/lớp THPT</a>'
    )
    return text.replace(anchor.rstrip("\n"), insertion, 1)


def create_tables_and_import() -> dict:
    sys.path.insert(0, str(PROJECT))
    old_cwd = Path.cwd()
    try:
        os.chdir(PROJECT)

        from sqlalchemy import delete, select

        from app.database import Base, SessionLocal, engine
        from app.models import School
        import app.thpt_reference_models  # noqa: F401
        from app.thpt_reference_models import (
            THPTGradeReference,
            THPTSchoolReference,
        )

        Base.metadata.create_all(bind=engine)

        records = json.loads(
            gzip.decompress(base64.b64decode(RECORDS_B64)).decode("utf-8")
        )

        db = SessionLocal()
        try:
            stats = {
                "school_total": 0,
                "grade_total": 0,
                "created": 0,
                "updated": 0,
                "linked": 0,
            }

            for data in records:
                code = str(data["school_code"]).strip()
                school = db.scalar(
                    select(THPTSchoolReference).where(
                        THPTSchoolReference.school_year_code == SOURCE_YEAR,
                        THPTSchoolReference.school_code == code,
                    )
                )

                official = db.scalar(
                    select(School).where(School.code == code)
                )

                if school is None:
                    school = THPTSchoolReference(
                        school_year_code=SOURCE_YEAR,
                        school_code=code,
                        school_name=data["school_name"],
                        source_name=SOURCE_NAME,
                        source_row=int(data["source_row"]),
                    )
                    db.add(school)
                    db.flush()
                    stats["created"] += 1
                else:
                    stats["updated"] += 1

                school.school_name = data["school_name"]
                school.official_school_id = official.id if official else None
                school.national_standard = (
                    None
                    if data["national_standard"] is None
                    else bool(data["national_standard"])
                )
                school.total_class_count = int(data["total_class_count"])
                school.total_student_count = int(data["total_student_count"])
                school.new_student_count = int(data["new_student_count"])
                school.staff_total = int(data["staff_total"])
                school.manager_count = int(data["manager_count"])
                school.teacher_count = int(data["teacher_count"])
                school.youth_union_teacher_count = int(data["youth_union_teacher_count"])
                school.employee_count = int(data["employee_count"])
                school.classroom_total = int(data["classroom_total"])
                school.classroom_permanent = int(data["classroom_permanent"])
                school.classroom_semi = int(data["classroom_semi"])
                school.classroom_temporary = int(data["classroom_temporary"])
                school.source_name = SOURCE_NAME
                school.source_row = int(data["source_row"])

                if official is not None:
                    stats["linked"] += 1

                db.execute(
                    delete(THPTGradeReference).where(
                        THPTGradeReference.school_ref_id == school.id
                    )
                )

                grade_specs = [
                    (
                        10,
                        data["grade10_class_count"],
                        data["grade10_student_count"],
                        data["grade10_new_student_count"],
                    ),
                    (
                        11,
                        data["grade11_class_count"],
                        data["grade11_student_count"],
                        None,
                    ),
                    (
                        12,
                        data["grade12_class_count"],
                        data["grade12_student_count"],
                        None,
                    ),
                ]

                for grade, class_count, student_count, new_count in grade_specs:
                    db.add(
                        THPTGradeReference(
                            school_ref_id=school.id,
                            grade=int(grade),
                            class_count=int(class_count or 0),
                            student_count=int(student_count or 0),
                            new_student_count=(
                                int(new_count)
                                if new_count is not None
                                else None
                            ),
                        )
                    )
                    stats["grade_total"] += 1

                stats["school_total"] += 1

            db.commit()

            actual_school = len(
                db.scalars(
                    select(THPTSchoolReference).where(
                        THPTSchoolReference.school_year_code == SOURCE_YEAR
                    )
                ).all()
            )
            actual_grades = len(
                db.scalars(
                    select(THPTGradeReference)
                    .join(THPTSchoolReference)
                    .where(THPTSchoolReference.school_year_code == SOURCE_YEAR)
                ).all()
            )

            if actual_school != 92:
                raise RuntimeError(
                    f"Số trường THPT sau nhập phải là 92, hiện là {actual_school}."
                )
            if actual_grades != 276:
                raise RuntimeError(
                    f"Số bản ghi khối THPT phải là 276, hiện là {actual_grades}."
                )

            return stats
        finally:
            db.close()
    finally:
        os.chdir(old_cwd)


def verify() -> None:
    for rel in [
        "app/thpt_reference_models.py",
        "app/survey_age_scope.py",
        "app/routers/thpt_reference.py",
        "app/main.py",
    ]:
        subprocess.run(
            [sys.executable, "-m", "py_compile", str(PROJECT / rel)],
            cwd=PROJECT,
            check=True,
        )

    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(APP / "templates")))
    env.get_template("schools/thpt_reference.html")
    env.get_template("partials/dropdown_menu_v1.html")

    main_text = read(MAIN)
    menu_text = read(MENU)
    if "BAI_13B_7_V1_THPT_ROUTER_INCLUDE" not in main_text:
        raise RuntimeError("Chưa xác nhận router THPT trong main.py.")
    if "BAI_13B_7_V1_MENU_THPT" not in menu_text:
        raise RuntimeError("Chưa xác nhận menu THPT.")
    if "1.2.5. Danh mục trường/lớp THPT" not in menu_text:
        raise RuntimeError("Menu THPT chưa đúng nhãn.")


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    print("=" * 100)
    print("BÀI 13B-7 V1 - MẠNG LƯỚI TRƯỜNG/LỚP THPT + PHẠM VI ĐỘ TUỔI ĐIỀU TRA")
    print("=" * 100)
    print("")
    print("NGUỒN THPT 2025-2026:")
    print(" - 92 trường/đơn vị")
    print(" - 2.674 lớp")
    print(" - 119.639 học sinh")
    print(" - Khối 10: 869 lớp")
    print(" - Khối 11: 923 lớp")
    print(" - Khối 12: 882 lớp")
    print("")
    print("NGUYÊN TẮC AN TOÀN:")
    print(" - File THPT không có cột xã/phường -> KHÔNG gán bừa trường vào xã.")
    print(" - File chỉ có số lượng lớp theo khối -> KHÔNG sinh lớp giả 10A1/10A2.")
    print(" - Tạo 92 trường tham chiếu + 276 bản ghi khối 10/11/12.")
    print(" - Mã trường nào đã có trong bảng School sẽ tự liên kết official_school_id.")
    print("")
    print("ĐỘ TUỔI:")
    print(" - Phổ cập: 0-18 tuổi, bao gồm tuổi 18.")
    print(" - Xóa mù chữ: 18-60 tuổi, bao gồm tuổi 18 và 60.")
    print(" - Tuổi 18 thuộc cả hai phạm vi.")
    print("")

    if not MAIN.exists() or not MENU.exists():
        raise RuntimeError("Thiếu app/main.py hoặc dropdown_menu_v1.html.")

    main_before = read(MAIN)
    menu_before = read(MENU)

    if "schools_router" not in main_before:
        raise RuntimeError("main.py không có schools_router; dừng để tránh sửa nhầm.")
    if "1.2.4. Danh mục trường THCS" not in menu_before and "BAI_13B_7_V1_MENU_THPT" not in menu_before:
        raise RuntimeError("Menu hiện tại chưa có cấu trúc MN/TH/THCS đã chốt.")

    manifest = backup_files()

    try:
        write_new_files()
        MAIN.write_text(patch_main(main_before), encoding="utf-8")
        MENU.write_text(patch_menu(menu_before), encoding="utf-8")

        stats = create_tables_and_import()
        verify()
        clear_cache()

        print("")
        print("KẾT QUẢ:")
        print(f" - Trường THPT tham chiếu: {stats['school_total']}")
        print(f" - Bản ghi khối 10/11/12: {stats['grade_total']}")
        print(f" - Tạo mới: {stats['created']}")
        print(f" - Cập nhật: {stats['updated']}")
        print(f" - Khớp được với School hiện có theo mã: {stats['linked']}")
        print("")
        print("CAI DAT BAI 13B-7 V1 THPT THANH CONG")
        print("Backup:", BACKUP)
        print("Mở sau khi khởi động lại: http://127.0.0.1/truong-thpt")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC FILE...")
        restore_files(manifest)
        print("ĐÃ KHÔI PHỤC FILE VỀ TRƯỚC BÀI 13B-7 V1.")
        print(
            "Lưu ý: nếu lỗi xảy ra sau bước tạo bảng, các bảng tham chiếu THPT "
            "có thể vẫn tồn tại nhưng không ảnh hưởng bảng School/Classroom hiện có."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
