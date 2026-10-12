import unittest
from datetime import date
from io import BytesIO
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Commune, School, SchoolYear, User, Role
from app.survey_models import Household, SurveyBatch, SurveyForm, SurveyPerson, SurveyPersonYearRecord, SurveyFormInvestigator
from app.survey_workflow_models import SurveyCommuneExecutionState
from app.xmc_models import XmcEvidence
from app.routers.xmc_appendix_reports import router, load_people
from app.routers.report_center import router as center_router
from app.access_control import AccessControlMiddleware


class ScopeTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add_all([Role(id=1,code="GIAO_VIEN",name="GV"), SchoolYear(id=1,code="2026-2027",name="Year"),
                         SchoolYear(id=2,code="2025-2026",name="Previous",is_active=False)])
        for i in (1,2,3):
            cid = 1 if i < 3 else 2
            if i != 2:
                self.db.add(Commune(id=cid,code=f"C{cid}",name=f"Commune {cid}"))
                self.db.add(School(id=cid,commune_id=cid,code=f"S{cid}",name=f"School {cid}"))
            self.db.add(User(id=i,username=f"u{i}",password_hash="unused",full_name=f"User {i}",role_id=1,school_id=cid))
            self.db.add(Household(id=i,code=f"H{i}",commune_id=cid,head_name="Head",address="Address"))
            self.db.add(SurveyBatch(id=i,code=f"B{i}",name=f"Batch {i}",school_year_id=1,commune_id=cid))
            self.db.flush()
            self.db.add(SurveyForm(id=i,survey_batch_id=i,household_id=i,form_number=f"F{i}",head_name_snapshot="H",address_snapshot="A"))
            self.db.add(SurveyPerson(id=i,code=f"P{i}",household_id=i,full_name=f"Person {i}",date_of_birth=date(2000,1,1),gender="NU",ethnic_group="Kinh"))
            self.db.flush()
            self.db.add(SurveyFormInvestigator(survey_form_id=i,user_id=i))
            self.db.add(SurveyPersonYearRecord(id=i,survey_form_id=i,survey_person_id=i,school_year_id=1,
                                             completed_grade_3=False,completed_grade_5=False))
        self.db.commit()
        self.user = dict(id=1,role_code="GIAO_VIEN",school_id=1,commune_id=1)
        app = FastAPI()
        @app.middleware("http")
        async def auth(request, call_next):
            request.scope["auth_user"] = self.user
            request.scope["session"] = {"xmc_csrf":"test-token"}
            return await call_next(request)
        app.dependency_overrides[get_db] = lambda:self.db
        app.include_router(router)
        app.include_router(center_router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_each_scope(self):
        for role, expected in (("ADMIN",{1,2,3}),("PHONG_BAN",{1,2,3}),("XA",{1,2}),
                               ("TRUONG",{1,2}),("GIAO_VIEN",{1})):
            user = dict(self.user, role_code=role)
            self.assertEqual({p.id for p,_ in load_people(self.db,user,1)},expected)
        self.assertEqual(load_people(self.db,self.user,2),[])

    def test_export_rejects_forged_scope_and_missing_scope(self):
        path = "/bao-cao/xoa-mu-chu/phu-luc/02/tong-hop"
        self.assertEqual(self.client.get(path+"?commune_id=2&school_year_id=1").status_code,403)
        self.assertEqual(self.client.get(path+"?school_id=2&school_year_id=1").status_code,403)
        self.assertEqual(self.client.get(path+"?school_year_id=999").status_code,422)
        response = self.client.get(path+"?school_year_id=1")
        self.assertEqual(response.status_code,200)
        wb = load_workbook(BytesIO(response.content))
        names = [c.value for row in wb["Trang_18"] for c in row]
        self.assertIn("Person 1",names)
        self.assertNotIn("Person 2",names)
        self.user = dict(role_code="TRUONG")
        self.assertEqual(self.client.get(path+"?school_year_id=1").status_code,403)

    def test_save_scope_validation_and_locks(self):
        path = "/bao-cao/xoa-mu-chu/du-lieu-bo-sung/"
        data = dict(csrf="test-token",enrolled1="true",recognized1="true")
        self.assertEqual(self.client.post(path+"2",data=data,follow_redirects=False).status_code,403)
        self.assertEqual(self.client.post(path+"1",data={**data,"csrf":"bad"},follow_redirects=False).status_code,403)
        self.assertEqual(self.client.post(path+"1",data={**data,"enrolled1":"false"},follow_redirects=False).status_code,422)
        self.db.get(SurveyPersonYearRecord,1).completed_grade_3 = True
        self.db.commit()
        self.assertEqual(self.client.post(path+"1",data=data,follow_redirects=False).status_code,303)
        self.assertEqual(self.db.get(XmcEvidence,1).data["recognized1"],True)
        self.db.add(SurveyCommuneExecutionState(survey_batch_id=1,is_province_locked=True))
        self.db.commit()
        self.assertEqual(self.client.post(path+"1",data=data,follow_redirects=False).status_code,409)
        self.user["role_code"] = "PHONG_BAN"
        self.assertEqual(self.client.post(path+"1",data=data,follow_redirects=False).status_code,403)
        self.assertFalse(AccessControlMiddleware._co_quyen_theo_thao_tac(path=path+"1",method="POST",role_code="PHONG_BAN"))
        self.assertTrue(AccessControlMiddleware._co_quyen_theo_thao_tac(path=path+"1",method="POST",role_code="GIAO_VIEN"))

    def test_readonly_evidence_page(self):
        self.user["role_code"] = "PHONG_BAN"
        response = self.client.get("/bao-cao/xoa-mu-chu/du-lieu-bo-sung?school_year_id=1")
        self.assertEqual(response.status_code,200)
        self.assertIn("fieldset disabled",response.text)

    def test_centers_expose_new_forms_for_all_roles(self):
        for role in ("ADMIN", "SO", "PHONG_BAN", "XA", "TRUONG", "GIAO_VIEN"):
            with self.subTest(role=role):
                self.user["role_code"] = role
                response = self.client.get("/bao-cao/xoa-mu-chu?school_year_id=1")
                self.assertEqual(response.status_code,200)
                self.assertIn("/phu-luc/09/tong-hop?school_year_id=1",response.text)
                self.assertIn("Dữ liệu bổ sung XMC",response.text)
                for old in ("PCGD_XMC_3_2025", "PCGD_CMC_2_2025", "PCGD_CMC_1_2025", "PCGD_XMC_4_2025"):
                    self.assertNotIn("report_type=" + old, response.text)
                self.assertLess(response.text.index('id="b134-level-filter"'),response.text.index('id="phu-luc-2026"'))

    def test_stage_completion_can_qualify_without_changing_old_record(self):
        response = self.client.post("/bao-cao/xoa-mu-chu/du-lieu-bo-sung/1", data={
            "csrf": "test-token", "completed_stage2": "true", "enrolled2": "true", "recognized2": "true"
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertFalse(self.db.get(SurveyPersonYearRecord, 1).completed_grade_5)
        self.assertTrue(self.db.get(XmcEvidence, 1).data["completed_stage2"])

    def test_deduplicate_across_batches(self):
        self.db.add(SurveyForm(id=4,survey_batch_id=2,household_id=1,form_number="F4",head_name_snapshot="H",address_snapshot="A"))
        self.db.flush()
        self.db.add(SurveyPersonYearRecord(id=4,survey_form_id=4,survey_person_id=1,school_year_id=1,
                                         is_reviewed=True,completed_grade_3=True))
        self.db.commit()
        rows = load_people(self.db,dict(self.user,role_code="ADMIN"),1)
        self.assertEqual(len(rows),3)
        self.assertEqual(next(r.id for p,r in rows if p.id == 1),4)


if __name__ == "__main__":
    unittest.main()
