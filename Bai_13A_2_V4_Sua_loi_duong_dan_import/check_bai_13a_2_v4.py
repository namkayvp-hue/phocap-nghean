from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_DIR = Path(
    os.environ.get("PHOCAP_PROJECT_DIR", r"C:\PhoCap")
).resolve()
project_text = str(PROJECT_DIR)
if project_text not in sys.path:
    sys.path.insert(0, project_text)

from sqlalchemy import select
from starlette.requests import Request

from app.database import SessionLocal
from app.main import app
from app.models import SchoolYear
from app.routers.survey_summary_report import build_report_data


def main() -> None:
    route_map = {
        (
            getattr(route, "path", ""),
            tuple(sorted(getattr(route, "methods", set()) or set())),
        )
        for route in app.router.routes
    }
    required_routes = {
        ("/bao-cao/tong-hop-dieu-tra", ("GET",)),
        ("/bao-cao/tong-hop-dieu-tra/xuat-excel", ("GET",)),
    }
    missing_routes = sorted(required_routes - route_map)
    if missing_routes:
        raise RuntimeError(
            "Thiếu route: "
            + ", ".join(path for path, _methods in missing_routes)
        )

    template_path = (
        PROJECT_DIR
        / "app"
        / "templates"
        / "reports"
        / "survey_summary_report.html"
    )
    if not template_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy giao diện: {template_path}")

    template_text = template_path.read_text(encoding="utf-8")
    required_template_markers = {
        "Bài 13A-2",
        "Báo cáo tổng hợp kết quả điều tra",
        "Xuất Excel",
    }
    missing_markers = sorted(
        marker
        for marker in required_template_markers
        if marker not in template_text
    )
    if missing_markers:
        raise RuntimeError(
            "Giao diện thiếu nội dung: " + ", ".join(missing_markers)
        )

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/bao-cao/tong-hop-dieu-tra",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 12345),
        "app": app,
        "auth_user": {
            "id": 0,
            "username": "checker",
            "full_name": "Kiểm tra Bài 13A-2 V4",
            "role_code": "ADMIN",
            "role_name": "Quản trị hệ thống",
            "commune_id": None,
            "school_id": None,
            "unit_name": "Toàn tỉnh",
        },
    }
    request = Request(scope)

    with SessionLocal() as db:
        year = db.scalar(
            select(SchoolYear).order_by(
                SchoolYear.code.desc(),
                SchoolYear.id.desc(),
            )
        )
        if year is None:
            raise RuntimeError("Chưa có năm học để kiểm tra.")

        data = build_report_data(
            db=db,
            request=request,
            school_year_id=year.id,
            commune_id=None,
            school_id=None,
            data_state="",
            q="",
        )

    required_keys = {
        "summary",
        "commune_rows",
        "school_rows",
        "person_rows",
        "reference_date",
        "is_official",
    }
    missing_keys = sorted(required_keys - set(data))
    if missing_keys:
        raise RuntimeError(
            "Thiếu dữ liệu báo cáo: " + ", ".join(missing_keys)
        )

    summary = data["summary"]
    required_summary_keys = {
        "batches",
        "forms",
        "households",
        "people",
        "year_records",
        "missing_personal_id",
    }
    missing_summary_keys = sorted(required_summary_keys - set(summary))
    if missing_summary_keys:
        raise RuntimeError(
            "Thiếu chỉ tiêu tổng hợp: "
            + ", ".join(missing_summary_keys)
        )

    print("KIỂM TRA BÀI 13A-2 V4 THÀNH CÔNG")
    print(f"Năm học: {year.code}")
    print(f"Số đợt: {summary['batches']}")
    print(f"Số phiếu: {summary['forms']}")
    print(f"Số hộ: {summary['households']}")
    print(f"Số đối tượng: {summary['people']}")
    print(f"Số xã/phường: {len(data['commune_rows'])}")
    print(f"Số trường ghi nhận: {len(data['school_rows'])}")


if __name__ == "__main__":
    main()
