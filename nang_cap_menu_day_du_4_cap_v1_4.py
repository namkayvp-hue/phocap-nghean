from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import sys
import traceback
import zlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(r"C:\PhoCap")
VERSION = "MENU-SO-XUONG-V1.4-DU-4-CAP"
PARTIAL_REL = Path("app/templates/partials/dropdown_menu_v1.html")
MAIN_REL = Path("app/main.py")
DB_REL = Path("data/phocap.db")
ROUTERS_REL = Path("app/routers")
INCLUDE_MARKER = '{% include "partials/dropdown_menu_v1.html" %}'

EXCLUDED_TEMPLATES = {
    "auth/login.html",
    "surveys/field_print.html",
}

# Nội dung partial được nén trong chính bộ cài để người dùng chỉ cần chép 1 tệp .py.
MENU_TEMPLATE_B64 = (
    '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'
)

REQUIRED_MENU_TEXTS = [
    "Tài khoản Phòng ban",
    "Tài khoản Xã/phường",
    "Tài khoản Trường mầm non",
    "Cấp tài khoản đồng loạt",
    "Danh mục Xã/phường",
    "Danh mục Trường",
    "Danh sách trường thuộc xã/phường",
    "Quản lý tài khoản giáo viên",
    "Danh sách đợt điều tra",
    "Khởi tạo năm học toàn tỉnh",
    "Điều hành triển khai toàn tỉnh",
    "Trung tâm dữ liệu lịch sử",
    "Trung tâm phiếu điều tra",
    "Danh sách hộ dân / phiếu được giao",
    "In phiếu điều tra",
    "Xuất Excel điều tra",
    "Nhập Excel cập nhật hộ dân",
    "Trường tham gia và khóa/mở trường",
    "Giao phiếu cho trường",
    "Nhiệm vụ trường / gửi kết quả lên xã",
    "Giao phiếu cho giáo viên",
    "Phân công hàng loạt",
    "Kiểm tra chất lượng dữ liệu",
    "Theo dõi tiến độ",
    "Báo cáo tổng hợp đợt",
    "Chốt / mở số liệu cấp tỉnh",
    "Bảng điều hành địa bàn",
    "Kế thừa dữ liệu năm trước",
    "Đối chiếu giữa các năm học",
    "Xu hướng liên năm",
    "Đối chiếu điều tra với học sinh",
    "Chốt / mở kết quả đối chiếu",
    "Tổng hợp chốt đối chiếu toàn tỉnh",
    "Giám sát tiến độ và nhắc việc",
    "Danh sách học sinh",
    "Thêm học sinh mới",
    "Danh sách đội ngũ",
    "Kiểm tra dữ liệu đội ngũ",
    "Xuất mẫu Excel đội ngũ",
    "Xuất danh sách Excel",
    "Thêm nhân sự",
    "Cấu hình lớp",
    "Trung tâm báo cáo",
    "Báo cáo tổng hợp điều tra",
    "Báo cáo trẻ 3–5 tuổi",
    "Biểu mẫu PCGDMN 2025",
    "Biến động – theo dõi",
    "Báo cáo đối chiếu học sinh",
    "Báo cáo tiến độ – đôn đốc",
]

ROLE_EXPECTATIONS = {
    "ADMIN": {
        "must": ["1. Danh mục", "3. Học sinh", "Giao phiếu cho trường", "Chốt / mở số liệu cấp tỉnh", "Chốt / mở kết quả đối chiếu"],
        "must_not": ["Quản lý tài khoản giáo viên", "Giao phiếu cho giáo viên"],
    },
    "XA": {
        "must": ["1. Danh mục", "Danh sách trường thuộc xã/phường", "Giao phiếu cho trường", "Bảng điều hành địa bàn"],
        "must_not": ["3. Học sinh", "Chốt / mở số liệu cấp tỉnh", "Giao phiếu cho giáo viên", "Kế thừa dữ liệu năm trước"],
    },
    "TRUONG": {
        "must": ["1. Danh mục", "Quản lý tài khoản giáo viên", "Nhiệm vụ trường / gửi kết quả lên xã", "Giao phiếu cho giáo viên", "Thêm nhân sự"],
        "must_not": ["3. Học sinh", "Giao phiếu cho trường", "Chốt / mở số liệu cấp tỉnh", "Bảng điều hành địa bàn"],
    },
    "GIAO_VIEN": {
        "must": ["2. Điều tra hộ dân", "Danh sách hộ dân / phiếu được giao", "Nhập Excel cập nhật hộ dân", "4. Đội ngũ", "5. Báo cáo"],
        "must_not": ["1. Danh mục", "3. Học sinh", "Giao phiếu cho trường", "Giao phiếu cho giáo viên", "Chốt / mở số liệu cấp tỉnh"],
    },
}


def menu_template() -> str:
    return zlib.decompress(base64.b64decode(MENU_TEMPLATE_B64)).decode("utf-8")


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_sha256(directory: Path) -> str | None:
    if not directory.exists():
        return None
    h = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*.py") if p.is_file()):
        h.update(path.relative_to(directory).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update((sha256(path) or "").encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def copy_with_parent(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def inject_include(text: str) -> tuple[str, bool]:
    if INCLUDE_MARKER in text:
        return text, False
    match = re.search(r"<body\b[^>]*>", text, flags=re.IGNORECASE)
    if match is None:
        raise RuntimeError("Khong tim thay the <body> trong template.")
    insert_at = match.end()
    return text[:insert_at] + "\n" + INCLUDE_MARKER + "\n" + text[insert_at:], True


def render_role_checks(template_text: str) -> None:
    from jinja2 import Environment

    env = Environment()
    template = env.from_string(template_text)
    for role, rules in ROLE_EXPECTATIONS.items():
        user = {
            "full_name": "Nguoi dung kiem tra",
            "role_code": role,
            "role_name": role,
            "unit_name": "Don vi kiem tra",
        }
        request = SimpleNamespace(
            scope={"auth_user": user},
            url=SimpleNamespace(path="/"),
        )
        rendered = template.render(nguoi_dung=user, request=request)
        for text in rules["must"]:
            if text not in rendered:
                raise RuntimeError(f"Menu cap {role} thieu: {text}")
        for text in rules["must_not"]:
            if text in rendered:
                raise RuntimeError(f"Menu cap {role} hien sai quyen: {text}")
        if 'id="pc-menu-v14-home-cleanup"' not in rendered:
            raise RuntimeError(f"Menu cap {role} chua xu ly tieu de trung o Trang chu.")


def main() -> int:
    project = PROJECT
    if len(sys.argv) >= 2:
        project = Path(sys.argv[1]).expanduser().resolve()

    templates_dir = project / "app" / "templates"
    partial_path = project / PARTIAL_REL
    main_py = project / MAIN_REL
    db_path = project / DB_REL
    routers_dir = project / ROUTERS_REL

    print("\n" + "=" * 76)
    print("NANG CAP MENU SO XUONG V1.4 - DU 4 CAP SO / XA / TRUONG / GIAO VIEN")
    print("CHI DOI DIEU HUONG / MENU - KHONG DOI ROUTE - KHONG DOI DU LIEU")
    print("=" * 76)

    if not templates_dir.exists():
        raise FileNotFoundError(f"Khong tim thay: {templates_dir}")
    if not main_py.exists():
        raise FileNotFoundError(f"Khong tim thay: {main_py}")
    if not routers_dir.exists():
        raise FileNotFoundError(f"Khong tim thay: {routers_dir}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = project / "exports" / f"backup_menu_so_xuong_v1_4_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    main_hash_before = sha256(main_py)
    db_hash_before = sha256(db_path)
    routers_hash_before = tree_sha256(routers_dir)

    html_files = sorted(templates_dir.rglob("*.html"))
    targets: list[Path] = []
    for file_path in html_files:
        rel = file_path.relative_to(templates_dir).as_posix()
        if rel in EXCLUDED_TEMPLATES or rel.startswith("partials/"):
            continue
        targets.append(file_path)

    print("\nBUOC 1 - SAO LUU AN TOAN CAC TEP GIAO DIEN")
    files_to_backup = [*targets]
    if partial_path.exists():
        files_to_backup.append(partial_path)

    backed_up: list[str] = []
    for source in files_to_backup:
        rel = source.relative_to(project)
        copy_with_parent(source, backup / rel)
        backed_up.append(rel.as_posix())

    print(f"Ban sao an toan: {backup}")
    print("app/main.py, app/routers va data/phocap.db CHI KIEM TRA MA BAM - KHONG GHI DE.")

    changed_files: list[str] = []
    created_files: list[str] = []

    try:
        print("\nBUOC 2 - CAP NHAT MENU V1.4 DU 4 CAP")
        template_text = menu_template()
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        if not partial_path.exists():
            created_files.append(PARTIAL_REL.as_posix())
        partial_path.write_text(template_text, encoding="utf-8")
        changed_files.append(PARTIAL_REL.as_posix())
        print("Da cap nhat: app/templates/partials/dropdown_menu_v1.html")

        print("\nBUOC 3 - DAM BAO MENU CO TREN TAT CA GIAO DIEN CON")
        injected = 0
        already = 0
        for template_path in targets:
            rel = template_path.relative_to(project).as_posix()
            text = template_path.read_text(encoding="utf-8-sig")
            new_text, did_change = inject_include(text)
            if did_change:
                template_path.write_text(new_text, encoding="utf-8")
                changed_files.append(rel)
                injected += 1
            else:
                already += 1
        print(f"Da gan them menu vao {injected} template; {already} template da co menu.")

        print("\nBUOC 4 - KIEM TRA JINJA VA PHAN QUYEN 4 CAP")
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader(str(templates_dir)))
        env.get_template("partials/dropdown_menu_v1.html")

        syntax_errors: list[str] = []
        missing_include: list[str] = []
        for template_path in targets:
            rel_t = template_path.relative_to(templates_dir).as_posix()
            text = template_path.read_text(encoding="utf-8-sig")
            try:
                env.parse(text)
            except Exception as exc:
                syntax_errors.append(f"{rel_t}: {exc}")
            if INCLUDE_MARKER not in text:
                missing_include.append(rel_t)

        if syntax_errors:
            raise RuntimeError("Loi cu phap Jinja:\n" + "\n".join(syntax_errors[:12]))
        if missing_include:
            raise RuntimeError("Template chua co menu:\n" + "\n".join(missing_include[:12]))

        missing_items = [text for text in REQUIRED_MENU_TEXTS if text not in template_text]
        if missing_items:
            raise RuntimeError("Menu V1.4 con thieu chuc nang:\n" + "\n".join(missing_items))

        render_role_checks(template_text)
        print("Menu cap SO: DAT")
        print("Menu cap XA: DAT")
        print("Menu cap TRUONG: DAT")
        print("Menu cap GIAO VIEN: DAT")

        if ".roles," not in template_text:
            raise RuntimeError("Chua an cac o truy cap nhanh o Trang chu.")
        if ".survey-menu-grid," not in template_text:
            raise RuntimeError("Chua an cac o truy cap nhanh o Quan ly dieu tra.")
        if ".quick-access-grid," not in template_text:
            raise RuntimeError("Chua an cac o truy cap nhanh o Quan ly tai khoan.")
        if ".catalog {" not in template_text:
            raise RuntimeError("Chua an cac o chon bao cao da dua len menu.")
        if "body > .admin-header { display: none !important; }" not in template_text:
            raise RuntimeError("Chua xu ly tieu de he thong bi lap o Trang chu.")

        print("\nBUOC 5 - XAC NHAN KHONG DOI ROUTE / DU LIEU / NGHIEP VU")
        if sha256(main_py) != main_hash_before:
            raise RuntimeError("app/main.py da bi thay doi ngoai du kien.")
        if tree_sha256(routers_dir) != routers_hash_before:
            raise RuntimeError("app/routers da bi thay doi ngoai du kien.")
        if sha256(db_path) != db_hash_before:
            raise RuntimeError("data/phocap.db da bi thay doi ngoai du kien.")

        manifest = {
            "version": VERSION,
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "project": str(project),
            "backup": str(backup),
            "changed_files": sorted(set(changed_files)),
            "created_files": sorted(set(created_files)),
            "backed_up": sorted(set(backed_up)),
            "templates_with_menu": len(targets),
            "main_py_sha256_before": main_hash_before,
            "main_py_sha256_after": sha256(main_py),
            "routers_sha256_before": routers_hash_before,
            "routers_sha256_after": tree_sha256(routers_dir),
            "database_sha256_before": db_hash_before,
            "database_sha256_after": sha256(db_path),
        }
        (backup / "MENU_V1_4_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        latest = project / "exports" / "menu_so_xuong_v1_4_backup_moi_nhat.txt"
        latest.write_text(str(backup), encoding="utf-8")

        print("\nJinja: DAT")
        print("app/main.py: KHONG DOI")
        print("app/routers: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Route: KHONG DOI")
        print("Nghiep vu: KHONG DOI")
        print("Luong xu ly: KHONG DOI")
        print(f"So giao dien co menu: {len(targets)}")
        print("O truy cap nhanh trung lap: DA AN")
        print("Tieu de he thong bi lap o Trang chu: DA AN")
        print("Tieu de nghiep vu o cac trang con: GIU NGUYEN")
        print("\n" + "=" * 76)
        print("NANG CAP MENU SO XUONG V1.4 THANH CONG")
        print("=" * 76)
        print(f"Ban sao an toan: {backup}")
        print("Khoi dong lai Uvicorn va nhan Ctrl+F5 tren trinh duyet.")
        return 0

    except Exception:
        print("\nNANG CAP KHONG THANH CONG - DANG TU DONG KHOI PHUC...")
        traceback.print_exc()

        for template_path in targets:
            rel = template_path.relative_to(project)
            saved = backup / rel
            if saved.exists():
                copy_with_parent(saved, template_path)

        saved_partial = backup / PARTIAL_REL
        if saved_partial.exists():
            copy_with_parent(saved_partial, partial_path)
        elif partial_path.exists() and PARTIAL_REL.as_posix() in created_files:
            partial_path.unlink()

        print("DA KHOI PHUC CAC TEP GIAO DIEN CU.")
        print("app/main.py, app/routers VA data/phocap.db KHONG BI GHI DE.")
        print(f"Ban sao an toan: {backup}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
