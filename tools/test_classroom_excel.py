import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Classroom, Commune, School, SchoolYear
from app.report_input_models import SchoolNetworkYearData
from app.routers import classrooms


def excel(*names, header="Tên lớp"):
    book = Workbook()
    book.active.append([header])
    for name in names:
        book.active.append([name])
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


class ExcelTests(unittest.TestCase):
    def test_parser(self):
        self.assertEqual(classrooms.read_class_excel(excel(" 6A ", "6a", "6B")), ["6A", "6B"])
        for data in [b"invalid", excel(), excel("=1+1"), excel("6A", header="Sai"), excel(*map(str, range(201)))]:
            with self.assertRaises(ValueError):
                classrooms.read_class_excel(data)

    def test_preview_confirm_and_scope(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        db = Session(engine)
        self.addCleanup(engine.dispose)
        self.addCleanup(db.close)
        db.add_all([Commune(id=1, code="X", name="X"), SchoolYear(id=1, code="2026-2027", name="Current")])
        db.flush()
        db.add(School(id=1, commune_id=1, code="S", name="School"))
        db.flush()
        db.add_all([
            SchoolNetworkYearData(school_id=1, school_year_id=1, level_code="THCS"),
            Classroom(school_id=1, school_year_id=1, name="6A", is_active=True),
            Classroom(school_id=1, school_year_id=1, name="6B", is_active=False),
        ])
        db.commit()
        app = FastAPI()
        app.include_router(classrooms.router)
        app.dependency_overrides[get_db] = lambda: db
        actor = {"role_code": "TRUONG", "school_id": 1, "unit_name": "School"}

        @app.middleware("http")
        async def auth(request, call_next):
            request.scope["auth_user"] = actor
            return await call_next(request)

        with TestClient(app) as client:
            data = {"school_id": 1, "school_year_id": 1, "cap": "THCS"}
            sample = client.get("/lop-hoc/mau-excel?cap=THCS")
            self.assertEqual(classrooms.read_class_excel(sample.content), ["6A", "6B"])
            response = client.post("/lop-hoc/nhap-excel", data=data, files={"file": ("classes.xlsx", excel("6A", "6B", "6C"))})
            self.assertEqual(response.status_code, 200)
            self.assertIn("Mở lại lớp đã khóa", response.text)
            self.assertEqual(len(db.scalars(select(Classroom)).all()), 2)
            data["ten_lop"] = "6A\n6B\n6C"
            for _ in range(2):
                result = client.post("/lop-hoc/them", data=data, follow_redirects=False)
                self.assertEqual(result.status_code, 303)
            self.assertEqual(len(db.scalars(select(Classroom)).all()), 3)
            self.assertTrue(all(item.is_active for item in db.scalars(select(Classroom))))
            with patch.object(classrooms, "class_catalog_lock_message", return_value="Locked"):
                blocked = client.post("/lop-hoc/them", data=data, follow_redirects=False)
                self.assertIn("survey_locked", blocked.headers["location"])
            actor["school_id"] = 999
            blocked = client.post("/lop-hoc/nhap-excel", data=data, files={"file": ("classes.xlsx", excel("6D"))}, follow_redirects=False)
            self.assertIn("invalid_scope", blocked.headers["location"])
            blocked = client.post("/lop-hoc/them", data=data, follow_redirects=False)
            self.assertIn("invalid_scope", blocked.headers["location"])


if __name__ == "__main__":
    unittest.main()
