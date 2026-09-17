# -*- coding: utf-8 -*-
r"""
V9.3 - SÁP NHẬP THEO VĂN BẢN + TÌM NHANH XÃ/PHƯỜNG + THÔNG TIN DỮ LIỆU
============================================================================

THAY ĐỔI CHÍNH
--------------
1. Hàng lọc:
   Năm học -> Xã/phường -> Cấp học -> Hiển thị -> Thông tin dữ liệu.
2. Xã/phường có tìm nhanh: gõ từ đầu tên xã/phường.
3. Sau khi lọc:
   - nguồn KHÔNG lấy từ toàn bộ trường trong xã;
   - đích KHÔNG lấy từ toàn bộ trường trong xã;
   - chỉ hiển thị đúng từng nhóm Nguồn -> Đích trong văn bản/phương án.
4. "Thông tin dữ liệu" chỉ là chế độ xem/kiểm tra.
   Thực hiện thật luôn chuyển đồng bộ TẤT CẢ dữ liệu bắt buộc.
5. Backend cũng khóa theo exact plan; không thể lách bằng POST thủ công.
6. Phương án đã hoàn thành không thể chạy lại.
7. QĐ 3805 Nghi Lộc được ghi nhận COMPLETED đúng mapping đã thực hiện.

BẢN CÀI KHÔNG SỬA DATABASE.
"""

from __future__ import annotations

import ast
import base64
import json
import shutil
import sys
import zlib
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
SERVICE = ROOT / "app" / "services" / "school_merger_service.py"
ROUTER = ROOT / "app" / "routers" / "school_merger.py"
TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger.html"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
EXPORTS = ROOT / "exports"

SERVICE_BLOB = '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'
ROUTER_BLOB = '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'
TEMPLATE_BLOB = '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'
SEED_PAYLOAD = json.loads('{"version": 2, "policy": "Chỉ phương án status=APPROVED mới được xem trước/thực hiện. Nguồn và đích lấy đúng theo văn bản; không cho ghép tự do. Sau khi có operation đã commit, trạng thái hiệu lực tự chuyển COMPLETED.", "plans": [{"id": "QD3805-NGHI-LOC-MN-QUAN-HANH", "document_code": "QĐ 3805 – Nghi Lộc", "document_title": "Phương án sáp nhập trường theo văn bản đã thực hiện", "school_year_id": 2, "commune_id": 114, "level_code": "MN", "source_school_ids": [749], "target_school_id": 747, "status": "COMPLETED", "note": "Đã hoàn thành trước khi tích hợp chức năng dùng chung."}, {"id": "QD3805-NGHI-LOC-MN-NGHI-DIEN", "document_code": "QĐ 3805 – Nghi Lộc", "document_title": "Phương án sáp nhập trường theo văn bản đã thực hiện", "school_year_id": 2, "commune_id": 114, "level_code": "MN", "source_school_ids": [750, 751], "target_school_id": 748, "status": "COMPLETED", "note": "Đã hoàn thành trước khi tích hợp chức năng dùng chung."}, {"id": "QD3805-NGHI-LOC-TH-NGHI-DIEN", "document_code": "QĐ 3805 – Nghi Lộc", "document_title": "Phương án sáp nhập trường theo văn bản đã thực hiện", "school_year_id": 2, "commune_id": 114, "level_code": "TH", "source_school_ids": [1181], "target_school_id": 1178, "status": "COMPLETED", "note": "Đã hoàn thành trước khi tích hợp chức năng dùng chung."}, {"id": "QD3805-NGHI-LOC-TH-NGHI-TRUNG", "document_code": "QĐ 3805 – Nghi Lộc", "document_title": "Phương án sáp nhập trường theo văn bản đã thực hiện", "school_year_id": 2, "commune_id": 114, "level_code": "TH", "source_school_ids": [1180], "target_school_id": 1179, "status": "COMPLETED", "note": "Đã hoàn thành trước khi tích hợp chức năng dùng chung."}, {"id": "QD3805-NGHI-LOC-THCS-NGHI-DIEN", "document_code": "QĐ 3805 – Nghi Lộc", "document_title": "Phương án sáp nhập trường theo văn bản đã thực hiện", "school_year_id": 2, "commune_id": 114, "level_code": "THCS", "source_school_ids": [1608], "target_school_id": 1605, "status": "COMPLETED", "note": "Đã hoàn thành trước khi tích hợp chức năng dùng chung."}, {"id": "QD3805-NGHI-LOC-THCS-NGHI-TRUNG", "document_code": "QĐ 3805 – Nghi Lộc", "document_title": "Phương án sáp nhập trường theo văn bản đã thực hiện", "school_year_id": 2, "commune_id": 114, "level_code": "THCS", "source_school_ids": [1607], "target_school_id": 1606, "status": "COMPLETED", "note": "THCS Nghi Hoa sáp nhập vào THCS Nghi Trung; đã hoàn thành."}]}')


def decode_blob(value: str) -> str:
    return zlib.decompress(base64.b64decode(value.encode("ascii"))).decode("utf-8")


def fail(message: str, code: int = 2) -> None:
    print("=" * 110)
    print("DỪNG AN TOÀN V9.3")
    print("=" * 110)
    print(message)
    print("Database KHÔNG bị thay đổi.")
    raise SystemExit(code)


def merge_plan_file() -> tuple[dict, int]:
    PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)

    if PLAN_FILE.exists():
        try:
            current = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(
                f"File phương án hiện có không đọc được; không ghi đè: {exc}"
            )
        if not isinstance(current, dict) or not isinstance(current.get("plans"), list):
            raise RuntimeError(
                "File phương án hiện có không đúng cấu trúc {version, plans:[...]}."
            )
    else:
        current = {
            "version": 2,
            "policy": SEED_PAYLOAD.get("policy", ""),
            "plans": [],
        }

    existing = {
        str(x.get("id")): x
        for x in current.get("plans") or []
        if isinstance(x, dict) and x.get("id")
    }

    # 6 nhóm Nghi Lộc là dữ liệu nền đã xác nhận COMPLETED.
    for seed in SEED_PAYLOAD.get("plans") or []:
        existing[str(seed["id"])] = seed

    current["version"] = max(int(current.get("version") or 1), 2)
    current["policy"] = SEED_PAYLOAD.get("policy", current.get("policy", ""))
    current["updated_at"] = datetime.now().isoformat(timespec="seconds")
    current["plans"] = list(existing.values())

    PLAN_FILE.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return current, len(SEED_PAYLOAD.get("plans") or [])


def main() -> None:
    for p in (SERVICE, ROUTER, TEMPLATE):
        if not p.exists():
            fail(f"Không tìm thấy file cần nâng cấp: {p}")

    old_service = SERVICE.read_text(encoding="utf-8")
    old_router = ROUTER.read_text(encoding="utf-8")
    old_template = TEMPLATE.read_text(encoding="utf-8")

    # Chỉ cài trên nền V9.2 trở lên.
    if "CONFIRM_PHRASE" not in old_service or "build_preview" not in old_service:
        fail("Service sáp nhập hiện tại không phải nền V9.2; dừng để tránh ghi nhầm.")

    new_service = decode_blob(SERVICE_BLOB)
    new_router = decode_blob(ROUTER_BLOB)
    new_template = decode_blob(TEMPLATE_BLOB)

    # Kiểm tra nội dung mới trước khi chạm file thật.
    ast.parse(new_service)
    ast.parse(new_router)
    try:
        from jinja2 import Environment
        Environment().parse(new_template)
        jinja_result = "PASS"
    except ImportError:
        jinja_result = "SKIP - jinja2 không có trong Python installer"

    must_have = [
        "display_mode",
        "data_view",
        "list_merger_plans",
        "Nhóm trường nguồn → trường đích",
    ]
    if not all(x in new_service + new_router + new_template for x in must_have):
        fail("Gói V9.3 thiếu marker bắt buộc.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = EXPORTS / f"backup_sap_nhap_v9_3_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    shutil.copy2(SERVICE, backup_dir / SERVICE.name)
    shutil.copy2(ROUTER, backup_dir / ROUTER.name)
    shutil.copy2(TEMPLATE, backup_dir / TEMPLATE.name)
    if PLAN_FILE.exists():
        shutil.copy2(PLAN_FILE, backup_dir / PLAN_FILE.name)

    try:
        SERVICE.write_text(new_service, encoding="utf-8")
        ROUTER.write_text(new_router, encoding="utf-8")
        TEMPLATE.write_text(new_template, encoding="utf-8")
        payload, seed_count = merge_plan_file()

        # Kiểm tra lại sau khi ghi.
        ast.parse(SERVICE.read_text(encoding="utf-8"))
        ast.parse(ROUTER.read_text(encoding="utf-8"))
        try:
            from jinja2 import Environment
            Environment().parse(TEMPLATE.read_text(encoding="utf-8"))
        except ImportError:
            pass

        loaded = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
        seed_ids = {str(x["id"]) for x in SEED_PAYLOAD.get("plans") or []}
        actual_ids = {
            str(x.get("id"))
            for x in loaded.get("plans") or []
            if isinstance(x, dict)
        }
        if not seed_ids <= actual_ids:
            raise RuntimeError("File phương án thiếu nhóm QĐ 3805 Nghi Lộc.")

    except Exception as exc:
        shutil.copy2(backup_dir / SERVICE.name, SERVICE)
        shutil.copy2(backup_dir / ROUTER.name, ROUTER)
        shutil.copy2(backup_dir / TEMPLATE.name, TEMPLATE)

        old_plan = backup_dir / PLAN_FILE.name
        if old_plan.exists():
            shutil.copy2(old_plan, PLAN_FILE)
        elif PLAN_FILE.exists():
            try:
                PLAN_FILE.unlink()
            except Exception:
                pass

        print("=" * 110)
        print("CÀI V9.3 THẤT BẠI - ĐÃ TỰ KHÔI PHỤC MÃ NGUỒN")
        print("=" * 110)
        print(repr(exc))
        print("Database KHÔNG bị thay đổi.")
        raise SystemExit(5)

    report = backup_dir / "00_KET_QUA_CAI_DAT_V9_3.txt"
    report.write_text(
        "\n".join([
            "V9.3 - SÁP NHẬP THEO VĂN BẢN + TÌM NHANH XÃ/PHƯỜNG",
            "=" * 90,
            "STATUS=SUCCESS",
            "Database=KHÔNG THAY ĐỔI",
            f"Backup={backup_dir}",
            f"Plan file={PLAN_FILE}",
            f"Jinja={jinja_result}",
            f"Seed Nghi Lộc={seed_count} groups COMPLETED",
            "",
            "UI:",
            "- Năm học | Xã/phường | Cấp học | Hiển thị | Thông tin dữ liệu.",
            "- Xã/phường tìm nhanh bằng cách gõ từ đầu.",
            "- Nguồn/đích chỉ lấy từ phương án theo văn bản.",
            "- Không còn chọn trường nguồn/đích tự do.",
            "",
            "Dữ liệu:",
            "- Thông tin dữ liệu chỉ là chế độ xem.",
            "- Thực hiện thật luôn xử lý đồng bộ tất cả dữ liệu bắt buộc.",
            "",
            "Backend:",
            "- Exact plan gate.",
            "- COMPLETED không chạy lại.",
            "- Plan đã commit được nhận diện COMPLETED từ merger history.",
        ]),
        encoding="utf-8",
    )

    result_zip = ROOT / f"ket_qua_cai_dat_sap_nhap_v9_3_{stamp}.zip"
    with zipfile.ZipFile(result_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(report, arcname=report.name)
        zf.write(PLAN_FILE, arcname=PLAN_FILE.name)
        zf.write(backup_dir / SERVICE.name, arcname="TRUOC_V9_3/" + SERVICE.name)
        zf.write(backup_dir / ROUTER.name, arcname="TRUOC_V9_3/" + ROUTER.name)
        zf.write(backup_dir / TEMPLATE.name, arcname="TRUOC_V9_3/" + TEMPLATE.name)

    print("=" * 110)
    print("CÀI ĐẶT V9.3 THÀNH CÔNG")
    print("=" * 110)
    print("Database: KHÔNG THAY ĐỔI")
    print(f"Backup mã nguồn: {backup_dir}")
    print(f"Jinja parse: {jinja_result}")
    print(f"File phương án: {PLAN_FILE}")
    print("Đã khóa nguồn/đích theo văn bản/phương án.")
    print("Đã thêm tìm nhanh Xã/phường bằng cách gõ từ đầu.")
    print("Đã thêm ô Thông tin dữ liệu ở hàng lọc.")
    print("QĐ 3805 Nghi Lộc: 6 nhóm đã ghi nhận COMPLETED.")
    print(f"ZIP kết quả: {result_zip}")


if __name__ == "__main__":
    main()
