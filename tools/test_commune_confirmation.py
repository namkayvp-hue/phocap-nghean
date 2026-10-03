import unittest
import re
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request
from app.database import Base
from app.models import Commune, SchoolYear
from app.survey_models import Household, SurveyBatch, SurveyForm
from app.survey_workflow_models import SurveyCommuneExecutionState
from app.routers.surveys import confirm_commune_form, hien_thi_trang_cap_nhat_phieu
from app.access_control import AccessControlMiddleware


class CommuneConfirmationTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add_all([Commune(id=1,code='X',name='Commune'),SchoolYear(id=1,code='2026-2027',name='Year')])
        self.db.flush()
        self.db.add_all([Household(id=1,code='H',commune_id=1,head_name='Head',address='Address'),
                         SurveyBatch(id=1,code='B',name='Batch',school_year_id=1,commune_id=1)])
        self.db.flush()
        self.form = SurveyForm(id=1,survey_batch_id=1,household_id=1,form_number='F',status='DA_HOAN_THANH',
                               head_name_snapshot='Head', address_snapshot='Address',
                               household_confirmed_at=datetime(2026,1,1), notes='Keep this')
        self.db.add(self.form)
        self.db.commit()

    def request(self,role='XA',commune=1):
        return Request({'type':'http','path':'/dieu-tra/1/ho-dan/1/phieu','headers':[],
                        'auth_user':{'role_code':role,'commune_id':commune}})

    def confirm(self,enabled=True,**kwargs):
        return confirm_commune_form(1,1,self.request(**kwargs),enabled,self.db)

    def test_confirm_unconfirm_and_ui(self):
        page=hien_thi_trang_cap_nhat_phieu(request=self.request(),survey_form=self.form,active_people_count=0)
        self.assertIn(b'form="commune-confirmation-form"',page.body)
        self.assertIn(b'id="commune-confirmation-form"',page.body)
        checkbox = re.search(rb'<input[^>]*name="commune_confirmed"[^>]*>', page.body).group()
        self.assertNotIn(b'disabled', checkbox)
        status = re.search(rb'<select[^>]*name="form_status"[^>]*>', page.body).group()
        self.assertIn(b'disabled', status)
        self.assertEqual(self.confirm().status_code,303)
        stamp=self.form.commune_confirmed_at
        self.assertIsNotNone(stamp)
        self.confirm()
        self.assertEqual(self.form.commune_confirmed_at,stamp)
        self.confirm(False)
        self.assertIsNone(self.form.commune_confirmed_at)
        self.assertEqual(self.form.notes,'Keep this')
        self.assertEqual(self.form.status,'DA_HOAN_THANH')
        self.assertEqual(self.form.household_confirmed_at,datetime(2026,1,1))

    def test_scope_roles_and_lock(self):
        for args in [{'commune':2},{'role':'GIAO_VIEN'},{'role':'TRUONG'}]:
            self.assertIn('forbidden',self.confirm(**args).headers['location'])
            self.assertIsNone(self.form.commune_confirmed_at)
        self.db.add(SurveyCommuneExecutionState(survey_batch_id=1,is_province_locked=True))
        self.db.commit()
        self.assertEqual(self.confirm().status_code,400)
        self.assertIsNone(self.form.commune_confirmed_at)

    def test_incomplete_and_permission(self):
        self.form.status='CHUA_DIEU_TRA'
        self.db.commit()
        self.assertEqual(self.confirm().status_code,400)
        self.assertIsNone(self.form.commune_confirmed_at)
        for role,expected in [('XA',True),('ADMIN',True),('TRUONG',False),('GIAO_VIEN',False)]:
            self.assertEqual(AccessControlMiddleware._co_quyen_theo_thao_tac(
                path='/dieu-tra/1/ho-dan/1/phieu/xac-nhan-xa',method='POST',role_code=role),expected)


if __name__=='__main__':
    unittest.main()
