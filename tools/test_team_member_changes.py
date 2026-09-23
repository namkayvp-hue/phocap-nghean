import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Commune, Role, School, SchoolYear, User
from app.survey_models import SurveyBatch
from app.survey_workflow_models import SurveyCommuneExecutionState
from app.routers import survey_team_registration as teams


class TeamMemberTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add_all([Commune(id=1, code="A", name="A"), Role(id=1, code="GIAO_VIEN", name="Teacher"),
                         SchoolYear(id=1, code="2026-2027", name="Year")])
        self.db.flush()
        self.db.add_all([School(id=i, commune_id=1, code=str(i), name=str(i)) for i in range(1, 4)])
        self.db.add(SurveyBatch(id=1, code="B", name="Batch", school_year_id=1, commune_id=1))
        self.db.flush()
        for i in range(1, 8):
            self.db.add(User(id=i, username=f"gv{i}", full_name=f"Teacher {i}", password_hash="unused",
                             role_id=1, school_id=(i-1)%3+1, commune_id=1))
        self.db.commit()
        teams._ensure_schema(self.db)
        teams._ensure_team_schema(self.db)
        for school in range(1, 4):
            self.db.execute(text("INSERT INTO survey_participant_submissions (survey_batch_id,school_id,status,updated_at) VALUES (1,:s,'SENT',CURRENT_TIMESTAMP)"), {"s": school})
        for i in range(1, 8):
            level = ["MN", "TH", "THCS"][(i-1)%3]
            self.db.execute(text("INSERT INTO survey_investigation_participants (survey_batch_id,school_id,user_id,level_code,created_at,updated_at) VALUES (1,:s,:u,:l,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),
                            {"s": (i-1)%3+1, "u": i, "l": level})
        for team in [1, 2]:
            self.db.execute(text("INSERT INTO survey_investigation_teams (id,survey_batch_id,commune_id,team_number,status,generation_code,created_at,updated_at) VALUES (:t,1,1,:t,'DRAFT','test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"t": team})
            for slot, level in enumerate(["MN", "TH", "THCS"], 1):
                self.db.execute(text("INSERT INTO survey_investigation_team_members (team_id,user_id,school_id,level_code,order_number,created_at) VALUES (:t,:u,:s,:l,:s,CURRENT_TIMESTAMP)"),
                                {"t": team, "u": (team-1)*3+slot, "s": slot, "l": level})
        self.db.commit()
        self.actor = {"role_code": "XA", "commune_id": 1, "full_name": "Commune"}
        app = FastAPI()
        app.include_router(teams.router)
        app.dependency_overrides[get_db] = lambda: self.db

        @app.middleware("http")
        async def auth(request, call_next):
            request.scope["auth_user"] = self.actor
            return await call_next(request)

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def change(self, new=4):
        return self.client.post("/dieu-tra/phan-cong-to-dieu-tra/lap-to/dieu-chinh-giao-vien",
            data={"batch_id": 1, "team_id": 1, "old_user_id": 1, "new_user_id": new}, follow_redirects=False)

    def members(self):
        return self.db.execute(text("SELECT team_id,user_id,level_code,order_number FROM survey_investigation_team_members ORDER BY team_id,order_number")).all()

    def test_swap_and_stale_request(self):
        response = self.change()
        self.assertIn("member_changed", response.headers["location"])
        self.assertEqual([row.user_id for row in self.members()], [4, 2, 3, 1, 5, 6])
        self.assertIn("member_stale", self.change().headers["location"])
        self.assertEqual(self.db.execute(text("SELECT count(*) FROM survey_team_generation_logs WHERE action='CHANGE_MEMBER'")).scalar(), 1)

    def test_reserve_and_render(self):
        page = self.client.get("/dieu-tra/phan-cong-to-dieu-tra/lap-to?batch_id=1")
        self.assertEqual(page.status_code, 200)
        self.assertIn('name="new_user_id"', page.text)
        self.assertIn("member_changed", self.change(7).headers["location"])
        self.assertEqual([row.user_id for row in self.members()], [7, 2, 3, 4, 5, 6])
        preview = teams._team_preview_data(self.db, batch_id=1)
        self.assertEqual([p["user_id"] for p in preview["reserve"]], [1])

    def test_invalid_level_scope_and_locked_teams(self):
        before = self.members()
        self.assertIn("member_invalid", self.change(5).headers["location"])
        self.actor["commune_id"] = 99
        self.assertEqual(self.change().headers["location"], "/?status=forbidden")
        self.actor["commune_id"] = 1
        self.actor["role_code"] = "TRUONG"
        self.assertEqual(self.change().headers["location"], "/?status=forbidden")
        self.actor["role_code"] = "XA"
        self.db.execute(text("UPDATE survey_investigation_teams SET status='SENT' WHERE id=2"))
        self.db.commit()
        self.assertIn("member_locked", self.change().headers["location"])
        self.assertEqual(self.members(), before)

    def test_batch_lock_and_rollback(self):
        before = self.members()
        self.db.add(SurveyCommuneExecutionState(survey_batch_id=1, is_province_locked=True))
        self.db.commit()
        self.assertIn("member_locked", self.change().headers["location"])
        self.db.execute(text("UPDATE survey_commune_execution_states SET is_province_locked=0"))
        self.db.commit()
        with patch.object(teams, "_generation_log", side_effect=ValueError("member_invalid")):
            self.assertIn("member_invalid", self.change().headers["location"])
        self.assertEqual(self.members(), before)


if __name__ == "__main__":
    unittest.main()
