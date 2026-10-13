"""Exercise destructive paths only against a temporary SQLite database."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.database import Base, get_db
from app.models import Commune, School, SchoolYear
from app.staff_models import StaffMember, StaffYearRecord
from app.routers import staff_bulk_delete as module


class StaffDeleteTests(unittest.TestCase):
    def setUp(self):
        guard = patch('app.database.SessionLocal', side_effect=AssertionError('Production database is forbidden in tests'))
        guard.start()
        self.addCleanup(guard.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = create_engine('sqlite:///' + str(Path(self.tmp.name) / 'test.db'), connect_args={'check_same_thread': False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add(Commune(id=1, code='C1', name='Commune'))
            for i in (1, 2):
                db.add(School(id=i, code=f'S{i}', name=f'School {i}', commune_id=1))
                db.add(SchoolYear(id=i, code=f'Y{i}', name=f'Year {i}'))
            for i in range(1, 5):
                db.add(StaffMember(id=i, code=f'T{i}', full_name=f'Teacher {i}'))
            db.flush()
            db.add_all([
                StaffYearRecord(id=1, staff_member_id=1, school_id=1, school_year_id=1),
                StaffYearRecord(id=2, staff_member_id=2, school_id=1, school_year_id=1, is_active=False),
                StaffYearRecord(id=3, staff_member_id=3, school_id=1, school_year_id=1, position_group='CBQL'),
                StaffYearRecord(id=4, staff_member_id=4, school_id=2, school_year_id=1),
                StaffYearRecord(id=5, staff_member_id=1, school_id=1, school_year_id=2),
            ])
            db.commit()
        self.user = dict(id=1, role_code='TRUONG', school_id=1)
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key='test-only')
        @app.middleware('http')
        async def auth(request, call_next):
            request.scope['auth_user'] = self.user
            return await call_next(request)
        def db_dependency():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = db_dependency
        app.include_router(module.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.backups = Path(self.tmp.name) / 'backups'
        patcher = patch.object(module, 'BACKUP_DIR', self.backups)
        patcher.start()
        self.addCleanup(patcher.stop)

    def ids(self):
        with Session(self.engine) as db:
            return set(db.scalars(select(StaffYearRecord.id)))

    def preview(self, **kwargs):
        params = dict(school_id=1, school_year_id=1, group='GIAO_VIEN', **kwargs)
        response = self.client.get('/doi-ngu/xoa-danh-sach', params=params)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('School 1', response.text)
        params.update(token=re.search(r'name="token" value="([^"]+)"', response.text).group(1), confirmation='XOA')
        return params

    def execute(self, data):
        return self.client.post('/doi-ngu/xoa-danh-sach', data=data, follow_redirects=False)

    def test_delete_preserves_other_years_schools_members_and_backups(self):
        data = self.preview()
        self.assertEqual(self.ids(), {1, 2, 3, 4, 5})
        response = self.execute(data)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(self.ids(), {3, 4, 5})
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(StaffMember)).all()), 4)
        backup = json.loads(next(self.backups.glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual({r['id'] for r in backup['records']}, {1, 2})
        self.assertEqual(self.execute(data).status_code, 403)

    def test_all_staff_option(self):
        response = self.client.get('/doi-ngu/xoa-danh-sach', params=dict(school_id=1,school_year_id=1,group='ALL'))
        token = re.search(r'name="token" value="([^"]+)"', response.text).group(1)
        self.assertEqual(self.execute(dict(school_id=1,school_year_id=1,group='ALL',token=token,confirmation='XOA')).status_code,303)
        self.assertEqual(self.ids(), {4,5})

    def test_readonly_and_cross_school_denied(self):
        for role in ('PHONG_BAN', 'XA', 'GIAO_VIEN'):
            self.user['role_code'] = role
            self.assertEqual(self.client.get('/doi-ngu/xoa-danh-sach?school_id=1&school_year_id=1').status_code,403)
        self.user['role_code'] = 'TRUONG'
        self.assertEqual(self.client.get('/doi-ngu/xoa-danh-sach?school_id=2&school_year_id=1').status_code,403)
        data = self.preview()
        self.user['role_code'] = 'PHONG_BAN'
        self.assertEqual(self.execute(data).status_code,403)
        self.assertEqual(len(self.ids()),5)

    def test_forged_scope_token_and_confirmation_denied(self):
        data = self.preview()
        for changes in (dict(token='bad'),dict(school_id=2),dict(group='ALL'),dict(school_year_id=2)):
            self.assertEqual(self.execute({**data,**changes}).status_code,403)
        self.assertEqual(self.execute({**data,'confirmation':''}).status_code,400)
        self.assertEqual(len(self.ids()),5)

    def test_stale_preview_denied(self):
        data = self.preview()
        with Session(self.engine) as db:
            db.get(StaffYearRecord,1).notes = 'Changed after preview'
            db.commit()
        self.assertEqual(self.execute(data).status_code,409)
        self.assertEqual(len(self.ids()),5)

    def test_failed_backup_does_not_delete(self):
        data = self.preview()
        with patch.object(module.os, 'fsync', side_effect=OSError('full disk')):
            response = self.execute(data)
            self.assertEqual(response.status_code,503)
            self.assertIn('không thể tạo bản sao lưu', response.text)
            self.assertIn('Xác nhận xóa', response.text)
        self.assertEqual(len(self.ids()),5)

    def test_backup_permission_failure_can_be_retried(self):
        data = self.preview()
        with patch.object(Path, 'mkdir', side_effect=PermissionError('read-only application directory')):
            with self.assertLogs(module.logger, level='ERROR') as captured:
                response = self.execute(data)
            self.assertEqual(response.status_code,503)
            self.assertIn('quyền ghi', response.text)
            self.assertIn('failed at backup', captured.output[0])
        self.assertEqual(len(self.ids()),5)
        self.assertEqual(self.execute(data).status_code,303)
        self.assertEqual(self.ids(),{3,4,5})

    def test_scope_required_and_admin_supported(self):
        self.user['role_code'] = 'ADMIN'
        self.assertEqual(self.client.get('/doi-ngu/xoa-danh-sach?school_year_id=1').status_code,422)
        self.assertEqual(self.client.get('/doi-ngu/xoa-danh-sach?school_id=0&school_year_id=1').status_code,400)
        self.assertEqual(self.client.get('/doi-ngu/xoa-danh-sach?school_id=1&school_year_id=999').status_code,400)
        self.assertEqual(self.execute(self.preview()).status_code,303)


if __name__ == '__main__':
    unittest.main()
