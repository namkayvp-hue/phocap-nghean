from __future__ import annotations

import sys
from pathlib import Path
from typing import get_type_hints

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

PROJECT = Path.cwd().resolve()
sys.path.insert(0, str(PROJECT))

from app.database import SessionLocal, get_db
from app.routers.students import (
    chuyen_id,
    danh_sach_hoc_sinh,
    form_them_hoc_sinh,
    router,
)

assert chuyen_id(None) is None
assert chuyen_id("") is None
assert chuyen_id("   ") is None
assert chuyen_id("2") == 2
assert chuyen_id(2) == 2
assert chuyen_id("abc") is None

list_hints = get_type_hints(danh_sach_hoc_sinh)
create_hints = get_type_hints(form_them_hoc_sinh)
for name in ("school_year_id", "commune_id", "school_id", "class_id"):
    if list_hints.get(name) != (str | None):
        raise AssertionError(f"Query {name} cua danh sach chua nhan chuoi rong")
    if create_hints.get(name) != (str | None):
        raise AssertionError(f"Query {name} cua trang them chua nhan chuoi rong")

app = FastAPI()
app.mount(
    "/static",
    StaticFiles(directory=str(PROJECT / "app" / "static")),
    name="static",
)
app.include_router(router)


def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

urls = [
    "/hoc-sinh?q=034400779361&school_year_id=2&commune_id=",
    "/hoc-sinh?q=034400779361&school_year_id=&commune_id=&school_id=&class_id=",
    "/hoc-sinh/them?school_year_id=2&commune_id=&school_id=&class_id=",
]

for url in urls:
    response = client.get(url)
    if response.status_code != 200:
        raise AssertionError(
            f"URL {url} tra ve {response.status_code}: {response.text[:300]}"
        )

print("DA KIEM TRA QUERY RONG: KHONG CON LOI 422")
print("KIEM TRA SUA LOI BO LOC HOC SINH V1 THANH CONG")
