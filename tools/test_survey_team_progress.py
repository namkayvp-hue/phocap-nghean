"""Team reporting regressions on an isolated, in-memory database."""
import unittest
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Commune, Role, School, SchoolYear, User
from app.survey_models import Household, SurveyBatch, SurveyForm, SurveyFormInvestigator
from app.routers import surveys
from app.routers.survey_team_registration import TEAM_SCHEMA_SQL
from app.services.survey_team_progress import build_team_progress


class TeamProgressTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.addCleanup(self.db.close)
        for sql in TEAM_SCHEMA_SQL[:3]:
            self.db.execute(text(sql))
        self.db.add_all([
            Role(id=1, code="GIAO_VIEN", name="GV"),
            SchoolYear(id=1, code="2026-2027", name="Year"),
            Commune(id=1, code="C1", name="Commune 1"),
            Commune(id=2, code="C2", name="Commune 2"),
        ])
        for i in range(1, 5):
            self.db.add(School(id=i, code=f"S{i}", name=f"School {i}", commune_id=1))
            self.db.add(User(id=i, username=f"u{i}", full_name=f"Teacher {i}", password_hash="unused", role_id=1, school_id=i))
        for i in range(1, 4):
            self.db.add(SurveyBatch(id=i, code=f"B{i}", name=f"Batch {i}", school_year_id=1, commune_id=2 if i == 3 else 1))
        self.db.flush()
        for team_id, batch_id, status in ((1, 1, "SENT"), (2, 1, "SENT"), (3, 1, "SENT"), (4, 1, "DRAFT"), (5, 2, "SENT"), (6, 3, "SENT")):
            self.db.execute(text("""INSERT INTO survey_investigation_teams
                (id,survey_batch_id,commune_id,team_number,status,generation_code,created_at,updated_at)
                VALUES (:id,:batch,:commune,:id,:status,'test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""),
                {"id": team_id, "batch": batch_id, "commune": 2 if batch_id == 3 else 1, "status": status})
            for user_id in ([1, 2, 3] if team_id == 1 else [4]):
                self.db.execute(text("""INSERT INTO survey_investigation_team_members
                    (team_id,user_id,school_id,level_code,order_number,created_at)
                    VALUES (:team,:user,:user,:level,:user,CURRENT_TIMESTAMP)"""),
                    {"team": team_id, "user": user_id, "level": {1: "MN", 2: "TH", 3: "THCS", 4: "MN"}[user_id]})
        statuses = ["DA_HOAN_THANH"] * 4 + ["DANG_DIEU_TRA", "CAN_BO_SUNG"] + ["CHUA_DIEU_TRA"] * 4
        for i in range(1, 16):
            batch_id = 2 if i == 14 else 3 if i == 15 else 1
            team_id = 1 if i <= 10 else 2 if i <= 12 else 4 if i == 13 else 5 if i == 14 else 6
            self.db.add(Household(id=i, code=f"H{i}", commune_id=2 if i == 15 else 1,
                                  head_name="Head", address="Address", hamlet_name="Hamlet A"))
            self.db.flush()
            self.db.add(SurveyForm(id=i, survey_batch_id=batch_id, household_id=i, form_number=f"F{i}",
                                   head_name_snapshot="Head", address_snapshot="Address",
                                   status=statuses[i-1] if i <= 10 else "DA_HOAN_THANH"))
            self.db.flush()
            # Only the representative has legacy individual assignments.
            self.db.add(SurveyFormInvestigator(survey_form_id=i, user_id=1 if i <= 10 else 4, is_primary=True))
            self.db.execute(text("""INSERT INTO survey_investigation_team_forms
                (team_id,survey_form_id,assignment_order,created_at)
                VALUES (:team,:form,:form,CURRENT_TIMESTAMP)"""), {"team": team_id, "form": i})
        self.db.commit()
        self.user = {"id": 1, "role_code": "ADMIN", "commune_id": 1, "school_id": 1}
        app = FastAPI()

        @app.middleware("http")
        async def auth(request, call_next):
            request.scope["auth_user"] = self.user
            return await call_next(request)

        app.dependency_overrides[get_db] = lambda: self.db
        app.include_router(surveys.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def report(self, **user):
        return build_team_progress(db=self.db, batch_id=1, commune_id=1,
                                   user={**self.user, **user}, status_codes=surveys.FORM_STATUS_LABELS)

    def test_shared_progress_without_multiplying_by_members(self):
        rows = self.report()
        self.assertEqual([row["team_number"] for row in rows], [1, 2, 3])
        team = rows[0]
        self.assertEqual(len(team["members"]), 3)
        self.assertEqual(team["total"], 10)
        self.assertEqual(team["counts"]["DA_HOAN_THANH"], 4)
        self.assertEqual(team["counts"]["CAN_BO_SUNG"], 1)
        self.assertEqual(team["progress_percent"], 40)
        self.assertEqual(rows[1]["progress_percent"], 100)
        self.assertEqual(rows[2]["total"], 0)
        self.assertEqual(rows[2]["progress_percent"], 0)
        # A second member becomes an editor/assignee; the same form still counts once.
        self.db.add(SurveyFormInvestigator(survey_form_id=1, user_id=2, order_number=2))
        self.db.commit()
        self.assertEqual(self.report()[0], team)
        self.db.get(SurveyForm, 5).status = "DA_HOAN_THANH"
        self.db.commit()
        self.assertEqual(self.report()[0]["progress_percent"], 50)

    def test_school_and_teacher_share_their_teams_only(self):
        for role in ("TRUONG", "GIAO_VIEN"):
            for school in (1, 2, 3):
                with self.subTest(role=role, school=school):
                    rows = self.report(role_code=role, school_id=school)
                    self.assertEqual([r["team_number"] for r in rows], [1])
                    self.assertEqual(rows[0]["progress_percent"], 40)
            self.assertEqual([r["team_number"] for r in self.report(role_code=role, school_id=4)], [2, 3])
            self.assertEqual(self.report(role_code=role, school_id=None), [])
            self.assertEqual(self.report(role_code=role, school_id=999), [])

    def test_commune_province_and_unknown_roles(self):
        for role in ("ADMIN", "SO", "PHONG_BAN", "XA"):
            self.assertEqual(len(self.report(role_code=role)), 3)
        self.assertEqual(self.report(role_code="XA", commune_id=2), [])
        self.assertEqual(self.report(role_code="XA", commune_id=None), [])
        self.assertEqual(self.report(role_code="UNKNOWN"), [])

    def test_no_team_tables_legacy_database_is_read_only(self):
        for name in ("survey_investigation_team_forms", "survey_investigation_team_members", "survey_investigation_teams"):
            self.db.execute(text(f"DROP TABLE {name}"))
        self.db.commit()
        self.assertEqual(self.report(), [])
        self.assertIsNone(self.db.execute(text("SELECT name FROM sqlite_master WHERE name='survey_investigation_teams'")).scalar())

    def test_page_uses_team_report_and_collapses_individual_reference(self):
        response = self.client.get("/dieu-tra/1/tien-do")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Tiến độ theo tổ được phân công", response.text)
        self.assertIn("40%", response.text)
        self.assertIn('Teacher 2', response.text)
        self.assertIn('<details class="panel panel-wide report-panel">', response.text)
        self.assertNotIn("Khối lượng và tiến độ của người điều tra", response.text)

    def test_excel_matches_team_report_and_preserves_existing_sheets(self):
        response = self.client.get("/dieu-tra/1/tien-do/xuat-excel")
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(BytesIO(response.content))
        self.assertEqual(wb.sheetnames, ["Tong quan", "Theo dia ban", "Theo truong", "Theo to dieu tra", "Theo nguoi dieu tra"])
        ws = wb["Theo to dieu tra"]
        self.assertEqual([ws.cell(5, c).value for c in (2, 5, 6, 7, 8, 9, 10)], ["Tổ 1", 10, 4, 1, 4, 1, "40%"])
        self.assertIn("Teacher 2 (TH)", ws.cell(5, 4).value)
        self.assertEqual(ws.cell(6, 10).value, "100%")
        self.assertEqual(ws.cell(7, 10).value, "0%")


if __name__ == "__main__":
    unittest.main()
