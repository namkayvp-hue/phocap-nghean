from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
APP_DIR = PROJECT / "app"

VANILLA_CODE = r"""
import inspect
from fastapi import FastAPI, APIRouter
from fastapi.applications import FastAPI as FastAPIClass
from fastapi.routing import APIRouter as APIRouterClass

print("FastAPI.include_router module=", FastAPIClass.include_router.__module__)
print("FastAPI.include_router qualname=", FastAPIClass.include_router.__qualname__)
print("FastAPI.include_router source=", inspect.getsourcefile(FastAPIClass.include_router))
print("APIRouter.include_router module=", APIRouterClass.include_router.__module__)
print("APIRouter.include_router qualname=", APIRouterClass.include_router.__qualname__)
print("APIRouter.include_router source=", inspect.getsourcefile(APIRouterClass.include_router))

r = APIRouter(prefix="/probe")
@r.get("")
def probe():
    return {"ok": True}

print("router.routes before=", [(x.path, sorted(x.methods or [])) for x in r.routes])

a = FastAPI()
a.include_router(r)
print("FastAPI.include_router probe=", [(x.path, sorted(getattr(x, "methods", None) or [])) for x in a.routes if "probe" in str(getattr(x, "path", ""))])

b = FastAPI()
b.router.include_router(r)
print("app.router.include_router probe=", [(x.path, sorted(getattr(x, "methods", None) or [])) for x in b.routes if "probe" in str(getattr(x, "path", ""))])
"""

AFTER_MAIN_CODE = r"""
import inspect
from fastapi import FastAPI
from fastapi.applications import FastAPI as FastAPIClass
from fastapi.routing import APIRouter as APIRouterClass

fast_before = FastAPIClass.include_router
api_before = APIRouterClass.include_router

print("BEFORE FastAPI id=", id(fast_before))
print("BEFORE APIRouter id=", id(api_before))
print("BEFORE FastAPI source=", inspect.getsourcefile(fast_before))
print("BEFORE APIRouter source=", inspect.getsourcefile(api_before))

import app.main
from app.routers import surveys

print("AFTER FastAPI id=", id(FastAPIClass.include_router))
print("AFTER APIRouter id=", id(APIRouterClass.include_router))
print("FastAPI changed=", FastAPIClass.include_router is not fast_before)
print("APIRouter changed=", APIRouterClass.include_router is not api_before)
print("AFTER FastAPI module=", FastAPIClass.include_router.__module__)
print("AFTER FastAPI qualname=", FastAPIClass.include_router.__qualname__)
print("AFTER FastAPI source=", inspect.getsourcefile(FastAPIClass.include_router))
print("AFTER APIRouter module=", APIRouterClass.include_router.__module__)
print("AFTER APIRouter qualname=", APIRouterClass.include_router.__qualname__)
print("AFTER APIRouter source=", inspect.getsourcefile(APIRouterClass.include_router))

print("surveys.router type=", type(surveys.router))
print("surveys.router prefix=", getattr(surveys.router, "prefix", None))
print("surveys.router route count=", len(surveys.router.routes))
print("surveys root=", [(x.path, sorted(x.methods or []), getattr(x.endpoint, "__name__", "")) for x in surveys.router.routes if str(x.path).rstrip("/") == "/dieu-tra"])

a = FastAPI()
a.include_router(surveys.router)
print("FastAPI.include_router dieu-tra count=", len([x for x in a.routes if "dieu-tra" in str(getattr(x, "path", ""))]))

b = FastAPI()
b.router.include_router(surveys.router)
print("app.router.include_router dieu-tra count=", len([x for x in b.routes if "dieu-tra" in str(getattr(x, "path", ""))]))

print("main app dieu-tra routes=", [(x.path, sorted(getattr(x, "methods", None) or []), getattr(getattr(x, "endpoint", None), "__module__", ""), getattr(getattr(x, "endpoint", None), "__name__", "")) for x in app.main.app.routes if "dieu-tra" in str(getattr(x, "path", ""))])
"""


def run_probe(title: str, source: str) -> None:
    print()
    print("=" * 118)
    print(title)
    print("=" * 118)
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=PROJECT,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print("--- STDERR ---")
        print(result.stderr.rstrip())
    print("RETURN_CODE=", result.returncode)


def static_scan() -> None:
    print()
    print("=" * 118)
    print(r"3. QUÉT SOURCE C:\PhoCap\app TÌM CAN THIỆP include_router / routes")
    print("=" * 118)
    needles = (
        "FastAPI.include_router",
        "APIRouter.include_router",
        ".include_router =",
        "include_router=",
        ".routes.clear(",
        ".routes =",
        "router.routes",
        "app.routes",
        "FastAPI =",
        "APIRouter =",
    )
    hits = []
    for path in sorted(APP_DIR.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(n in line for n in needles):
                hits.append((path, lineno, line.strip()))
    if not hits:
        print("Không tìm thấy dòng source khả nghi theo bộ từ khóa.")
        return
    for path, lineno, line in hits:
        print(f"{path.relative_to(PROJECT)}:{lineno}: {line}")
    print("Tổng dòng khả nghi=", len(hits))


def package_versions() -> None:
    print()
    print("=" * 118)
    print("4. PHIÊN BẢN FASTAPI / STARLETTE")
    print("=" * 118)
    import fastapi, starlette
    print("fastapi=", getattr(fastapi, "__version__", "?"))
    print("starlette=", getattr(starlette, "__version__", "?"))
    print("python=", sys.version.replace("\n", " "))


def main() -> int:
    print("=" * 118)
    print("KIỂM TRA FASTAPI include_router V5")
    print("CHỈ ĐỌC - KHÔNG SỬA SOURCE - KHÔNG SỬA DATABASE")
    print("=" * 118)
    run_probe("1. TIẾN TRÌNH SẠCH - CHỈ IMPORT FASTAPI", VANILLA_CODE)
    run_probe("2. SO SÁNH TRƯỚC / SAU KHI IMPORT app.main", AFTER_MAIN_CODE)
    static_scan()
    package_versions()
    print()
    print("=" * 118)
    print("5. HƯỚNG ĐỌC KẾT QUẢ")
    print("=" * 118)
    print("A. Sạch thêm /probe được nhưng sau app.main không thêm được => dự án can thiệp include_router toàn cục.")
    print("B. FastAPI.include_router hỏng nhưng app.router.include_router chạy => FastAPI.include_router bị thay.")
    print("C. Cả hai hỏng sau app.main => APIRouter.include_router hoặc route structure bị can thiệp.")
    print("D. Ngay tiến trình sạch không thêm được /probe => môi trường FastAPI có vấn đề.")
    print()
    print("Hãy COPY TOÀN BỘ kết quả V5 gửi lại ChatGPT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
