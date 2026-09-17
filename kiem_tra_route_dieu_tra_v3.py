from __future__ import annotations

import inspect
from pathlib import Path

from app.main import app
import app.database as database
from app.routers import surveys


def endpoint_source(endpoint):
    try:
        return inspect.getsourcefile(endpoint) or "(không rõ)"
    except Exception as exc:
        return f"(lỗi: {exc!r})"


def endpoint_line(endpoint):
    try:
        return inspect.getsourcelines(endpoint)[1]
    except Exception:
        return None


def main() -> int:
    print("=" * 116)
    print("KIỂM TRA ROUTE /dieu-tra V3")
    print("CHỈ ĐỌC - KHÔNG INSERT / UPDATE / DELETE - KHÔNG SỬA SOURCE")
    print("=" * 116)

    print("\n1. DATABASE PATH MÀ ỨNG DỤNG ĐANG DÙNG")
    print("-" * 116)
    print("database module =", inspect.getsourcefile(database))
    print("DATABASE_PATH   =", getattr(database, "DATABASE_PATH", None))

    print("\n2. HÀM CHUẨN TRONG app.routers.surveys")
    print("-" * 116)
    print("module file     =", inspect.getsourcefile(surveys))
    print("function        =", surveys.danh_sach_dot_dieu_tra)
    print("function file   =", endpoint_source(surveys.danh_sach_dot_dieu_tra))
    print("function line   =", endpoint_line(surveys.danh_sach_dot_dieu_tra))
    print("function module =", getattr(
        surveys.danh_sach_dot_dieu_tra,
        "__module__",
        None,
    ))

    print("\n3. TOÀN BỘ ROUTE CÓ PATH /dieu-tra")
    print("-" * 116)

    matches = []

    for index, route in enumerate(app.routes):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        endpoint = getattr(route, "endpoint", None)

        if path != "/dieu-tra":
            continue

        methods_text = ",".join(sorted(methods or []))
        name = getattr(route, "name", "")
        ep_name = getattr(endpoint, "__name__", repr(endpoint))
        ep_module = getattr(endpoint, "__module__", None)
        source = endpoint_source(endpoint) if endpoint else "(không endpoint)"
        line = endpoint_line(endpoint) if endpoint else None

        same = endpoint is surveys.danh_sach_dot_dieu_tra

        matches.append({
            "index": index,
            "methods": methods_text,
            "name": name,
            "ep_name": ep_name,
            "ep_module": ep_module,
            "source": source,
            "line": line,
            "same": same,
        })

        print(
            f"route_index={index} | methods={methods_text} | "
            f"name={name} | endpoint={ep_name}"
        )
        print(f"  module={ep_module}")
        print(f"  source={source}")
        print(f"  line={line}")
        print(f"  SAME_AS_surveys.danh_sach_dot_dieu_tra={same}")

    if not matches:
        print("KHÔNG tìm thấy route /dieu-tra.")
        return 0

    print("\n4. ROUTE GET /dieu-tra MÀ STARLETTE SẼ GẶP TRƯỚC")
    print("-" * 116)

    get_matches = [
        item
        for item in matches
        if "GET" in item["methods"]
    ]

    if not get_matches:
        print("Không có GET /dieu-tra.")
    else:
        first = sorted(get_matches, key=lambda x: x["index"])[0]
        print("FIRST GET route_index =", first["index"])
        print("endpoint              =", first["ep_name"])
        print("module                =", first["ep_module"])
        print("source                =", first["source"])
        print("line                  =", first["line"])
        print(
            "Có đúng surveys.danh_sach_dot_dieu_tra? =",
            first["same"],
        )

    print("\n5. CÁC ROUTE BẮT ĐẦU BẰNG /dieu-tra (20 ROUTE ĐẦU)")
    print("-" * 116)

    count = 0
    for index, route in enumerate(app.routes):
        path = str(getattr(route, "path", "") or "")
        if not path.startswith("/dieu-tra"):
            continue

        methods = ",".join(
            sorted(getattr(route, "methods", None) or [])
        )
        endpoint = getattr(route, "endpoint", None)
        ep_name = getattr(endpoint, "__name__", "")
        source = endpoint_source(endpoint) if endpoint else ""

        print(
            f"{index:03d} | {methods:<18} | {path:<55} | "
            f"{ep_name} | {source}"
        )

        count += 1
        if count >= 20:
            break

    print("\n6. KẾT LUẬN TỰ ĐỘNG")
    print("-" * 116)

    if len(get_matches) == 1 and get_matches[0]["same"]:
        print("Route GET /dieu-tra chỉ có 1 và đúng hàm surveys.danh_sach_dot_dieu_tra.")
        print("=> Khả năng cao tiến trình Uvicorn cũ chưa được dừng/khởi động lại đúng,")
        print("   hoặc vấn đề nằm trong dữ liệu request/session của tiến trình web.")
    elif len(get_matches) > 1:
        print(f"PHÁT HIỆN {len(get_matches)} route GET /dieu-tra.")
        print("=> Có route trùng. Route đăng ký trước có thể đang bắt request.")
    elif get_matches and not get_matches[0]["same"]:
        print("Route GET /dieu-tra đầu tiên KHÔNG phải hàm surveys.danh_sach_dot_dieu_tra.")
        print("=> Đã xác định lỗi route bị endpoint khác bắt trước.")
    else:
        print("Cần đọc thủ công kết quả route ở trên.")

    print("\nHãy COPY TOÀN BỘ mục 1 đến mục 6 gửi lại ChatGPT.")
    print("Script chỉ import ứng dụng và đọc metadata/source; không ghi dữ liệu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
