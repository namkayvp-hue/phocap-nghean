import unittest
from starlette.requests import Request
from app.survey_models import SurveyForm, SurveyPersonYearRecord
from app.routers.report_center import _th_m1_load_people_and_records
from app.routers.xmc_appendix_reports import load_people
from app.routers.survey_summary_report import _load_person_rows
from tools.test_xmc_scope import ScopeTests


class CompletedSurveyReportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ScopeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db = self.fixture.db
        self.user = dict(id=1, role_code='ADMIN')
        self.request = Request({'type':'http','auth_user':self.user})

    def loaders(self):
        return (
            load_people(self.db,self.user,1),
            _th_m1_load_people_and_records(db=self.db,request=self.request,school_year_id=1,
                                          selected_commune_id=None,selected_school_id=None),
            _load_person_rows(db=self.db,request=self.request,batch_ids=[1,2,3],school_year_id=1,
                              school_id=None,completed_only=True),
        )

    def test_imported_and_in_progress_forms_do_not_contribute(self):
        self.db.get(SurveyForm,1).status='CHUA_DIEU_TRA'
        self.db.get(SurveyForm,2).status='DANG_DIEU_TRA'
        self.db.get(SurveyForm,3).status='DA_DUYET'
        # Saving a person's record alone is not completion of the household form.
        for i in (1,2,3):
            self.db.get(SurveyPersonYearRecord,i).is_reviewed=True
        self.db.commit()
        for rows in self.loaders():
            self.assertEqual(len(rows),1)
        self.assertEqual(self.loaders()[0][0][0].id,3)
        self.db.get(SurveyForm,1).status='DA_HOAN_THANH'
        self.db.commit()
        for rows in self.loaders():
            self.assertEqual(len(rows),2)
        self.db.get(SurveyForm,1).status='DANG_DIEU_TRA'
        self.db.commit()
        for rows in self.loaders():
            self.assertEqual(len(rows),1)

    def test_no_completed_forms_means_no_population_figures(self):
        for i in (1,2,3):
            self.db.get(SurveyForm,i).status='CHUA_DIEU_TRA'
        self.db.commit()
        for rows in self.loaders():
            self.assertEqual(rows,[])


if __name__ == '__main__':
    unittest.main()
