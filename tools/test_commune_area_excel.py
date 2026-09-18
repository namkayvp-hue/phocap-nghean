import unittest
import json
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Commune, SchoolYear
from app.routers import commune_area_excel as areas


def excel(rows):
    book = Workbook()
    book.active.append(areas.HEADERS)
    for row in rows:
        book.active.append(row)
    stream = BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


class AreaExcelTests(unittest.TestCase):
    def test_parser(self):
        data = areas.read_excel(excel([["Thôn", "Thôn 1", 50, "Ghi chú"]]))
        self.assertEqual(data[0]["area_type"], "THON")
        self.assertEqual(data[0]["expected_households"], 50)
        for rows in [[], [["Sai", "A", 1]], [["XOM", "A", -1]],
                     [["XOM", "A", 1.5]], [["XOM", "=1+1", 2]],
                     [["XOM", "A", 1], ["XOM", "a", 2]]]:
            with self.assertRaises(ValueError):
                areas.read_excel(excel(rows))
        with self.assertRaises(ValueError):
            areas.read_excel(b"invalid")

    def test_import_scope_duplicates_and_validation(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        db = Session(engine)
        self.addCleanup(engine.dispose)
        self.addCleanup(db.close)
        db.add_all([Commune(id=1, code="A", name="A"), Commune(id=2, code="B", name="B"),
                    SchoolYear(id=1, code="2026-2027", name="Current"),
                    SchoolYear(id=2, code="2025-2026", name="Closed", is_active=False)])
        db.commit()
        app = FastAPI()
        app.include_router(areas.router)
        app.dependency_overrides[get_db] = lambda: db
        actor = {"role_code": "XA", "commune_id": 1, "unit_name": "A"}

        @app.middleware("http")
        async def auth(request, call_next):
            request.scope["auth_user"] = actor
            return await call_next(request)

        path = "/dieu-tra/phan-cong-to-dieu-tra/dia-ban"
        with TestClient(app) as client:
            sample = client.get(path + "/mau-excel")
            self.assertEqual(len(areas.read_excel(sample.content)), 2)
            response = client.post(path + "/nhap-excel", data={"school_year_id": 1},
                                   files={"file": ("areas.xlsx", excel([["XOM", "Area 1", 10]]))})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(db.execute(text("SELECT count(*) FROM survey_commune_areas")).scalar(), 0)
            data = {"school_year_id": 1, "payload": response.context["payload"], "commune_id": 2}
            for _ in range(2):
                saved = client.post(path + "/nhap-excel/luu", data=data)
                self.assertEqual(saved.status_code, 200)
            records = db.execute(text("SELECT commune_id,expected_households FROM survey_commune_areas")).all()
            self.assertEqual(records, [(1, 10)])
            self.assertEqual(saved.context["skipped"], 1)
            invalid = client.post(path + "/nhap-excel/luu", data={**data, "payload": json.dumps([
                {"area_type": "XOM", "name": "New", "expected_households": 1},
                {"area_type": "BAD", "name": "Invalid", "expected_households": 1}])})
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(db.execute(text("SELECT count(*) FROM survey_commune_areas")).scalar(), 1)
            closed = client.post(path + "/nhap-excel/luu", data={**data, "school_year_id": 2}, follow_redirects=False)
            self.assertEqual(closed.status_code, 303)
            actor["role_code"] = "TRUONG"
            denied = client.post(path + "/nhap-excel/luu", data=data, follow_redirects=False)
            self.assertEqual(denied.status_code, 303)


if __name__ == "__main__":
    unittest.main()
