from __future__ import annotations

import inspect

from app.main import app
from app.routers import surveys


def info(endpoint):
    if endpoint is None:
        return "(none)", "(none)", "(none)"
    try:
        source = inspect.getsourcefile(endpoint) or "(không rõ)"
    except Exception:
        source = "(không rõ)"
    return (
        getattr(endpoint, "__module__", ""),
        getattr(endpoint, "__name__", ""),
        source,
    )


def main() -> int:
    print("=" * 118)
    print("KIỂM TRA ROUTE ĐIỀU TRA V4 - CHỐT")
    print("CHỈ ĐỌC - KHÔNG SỬA SOURCE - KHÔNG SỬA DATABASE")
    print("=" * 118)

    print("\n1. ROUTER TRỰC TIẾP TRONG app.routers.surveys")
    print("-" * 118)
    print("surveys module =", inspect.getsourcefile(surveys))
    print("router object  =", surveys.router)
    print("router prefix  =", getattr(surveys.router, "prefix", None))
    print("router routes  =", len(getattr(surveys.router, "routes", [])))

    direct_matches = []
    for i, route in enumerate(getattr(surveys.router, "routes", [])):
        path = getattr(route, "path", None)
        methods = sorted(getattr(route, "methods", None) or [])
        endpoint = getattr(route, "endpoint", None)
        module, name, source = info(endpoint)

        if path in ("", "/", "/dieu-tra", "/dieu-tra/") or name == "danh_sach_dot_dieu_tra":
            direct_matches.append((i, path, methods, module, name, source, endpoint))
            print(
                f"{i:03d} | path={path!r} | methods={methods} | "
                f"{module}.{name} | {source}"
            )

    if not direct_matches:
        print("KHÔNG tìm thấy route danh_sach_dot_dieu_tra trong surveys.router.")

    print("\n2. TOÀN BỘ app.routes CÓ CHỮ 'dieu-tra'")
    print("-" * 118)

    app_matches = []
    for i, route in enumerate(app.routes):
        path = str(getattr(route, "path", "") or "")
        if "dieu-tra" not in path:
            continue

        methods = sorted(getattr(route, "methods", None) or [])
        endpoint = getattr(route, "endpoint", None)
        module, name, source = info(endpoint)

        app_matches.append((i, path, methods, module, name, source, endpoint))

        print(
            f"{i:03d} | path={path!r} | methods={methods} | "
            f"{module}.{name} | {source}"
        )

    print("\nTổng route app có chữ dieu-tra =", len(app_matches))

    print("\n3. CÁC ROUTE GỐC GẦN /dieu-tra")
    print("-" * 118)

    root_like = [
        item
        for item in app_matches
        if item[1].rstrip("/") == "/dieu-tra"
    ]

    if not root_like:
        print("KHÔNG có route app nào mà path.rstrip('/') == '/dieu-tra'.")
    else:
        for item in root_like:
            i, path, methods, module, name, source, endpoint = item
            print(
                f"{i:03d} | {path!r} | {methods} | "
                f"{module}.{name} | SAME_FUNCTION="
                f"{endpoint is surveys.danh_sach_dot_dieu_tra}"
            )

    print("\n4. KIỂM TRA THỦ CÔNG include_router TRONG MỘT APP MỚI")
    print("-" * 118)

    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(surveys.router)

    test_matches = []
    for i, route in enumerate(test_app.routes):
        path = str(getattr(route, "path", "") or "")
        if "dieu-tra" not in path:
            continue

        endpoint = getattr(route, "endpoint", None)
        methods = sorted(getattr(route, "methods", None) or [])
        module, name, source = info(endpoint)
        test_matches.append((path, methods, module, name, endpoint))

        if path.rstrip("/") == "/dieu-tra":
            print(
                f"TEST APP | path={path!r} | methods={methods} | "
                f"{module}.{name} | SAME_FUNCTION="
                f"{endpoint is surveys.danh_sach_dot_dieu_tra}"
            )

    print("Tổng route test_app có chữ dieu-tra =", len(test_matches))

    print("\n5. ĐỊNH DANH ĐỐI TƯỢNG app")
    print("-" * 118)
    print("type(app) =", type(app))
    print("id(app)   =", id(app))
    print("app module source =", inspect.getsourcefile(inspect.getmodule(app.__class__)))
    print("app.routes total  =", len(app.routes))

    print("\n6. KẾT LUẬN TỰ ĐỘNG")
    print("-" * 118)

    direct_root = [
        item for item in direct_matches
        if str(item[1] or "").rstrip("/") in ("", "/dieu-tra")
        and "GET" in item[2]
        and item[6] is surveys.danh_sach_dot_dieu_tra
    ]

    app_root = [
        item for item in root_like
        if "GET" in item[2]
    ]

    test_root = [
        item for item in test_matches
        if item[0].rstrip("/") == "/dieu-tra"
        and "GET" in item[1]
    ]

    if direct_root and test_root and not app_root:
        print("CHỐT: surveys.router HOÀN TOÀN ĐÚNG và include vào app mới hoạt động.")
        print("Nhưng app.main.app không chứa route gốc Điều tra.")
        print("=> Lỗi nằm trong app/main.py hoặc cơ chế tạo/ghép app thực tế.")
    elif app_root:
        print("CHỐT: app.main.app CÓ route gốc Điều tra.")
        print("=> Kiểm tra V3 trước đã bỏ sót biến thể path.")
        print("=> Cần sửa phần route thực tế đang render danh sách, không sửa main.")
    elif not direct_root:
        print("CHỐT: surveys.router bản đang import KHÔNG chứa route gốc danh sách.")
        print("=> Cần sửa chính surveys.py/router registration.")
    else:
        print("Kết quả đặc biệt; dùng chi tiết mục 1-5 để sửa chính xác.")

    print("\nHãy COPY TOÀN BỘ kết quả V4 gửi lại ChatGPT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
