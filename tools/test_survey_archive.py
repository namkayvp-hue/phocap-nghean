import json
import sqlite3
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import survey_archive_service as service
from app.routers import survey_archive as routes
from app.access_control import AccessControlMiddleware


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "test.db"
        self.con = sqlite3.connect(self.path)
        self.addCleanup(self.con.close)
        self.con.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE communes(id INTEGER PRIMARY KEY,code TEXT,name TEXT);
            CREATE TABLE school_years(id INTEGER PRIMARY KEY,code TEXT);
            CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,full_name TEXT,password_hash TEXT);
            CREATE TABLE survey_batches(id INTEGER PRIMARY KEY,code TEXT,commune_id INTEGER REFERENCES communes(id),school_year_id INTEGER REFERENCES school_years(id));
            CREATE TABLE households(id INTEGER PRIMARY KEY,commune_id INTEGER REFERENCES communes(id),code TEXT,head_name TEXT);
            CREATE TABLE survey_people(id INTEGER PRIMARY KEY,household_id INTEGER REFERENCES households(id),code TEXT,full_name TEXT,is_active INTEGER);
            CREATE TABLE survey_forms(id INTEGER PRIMARY KEY,survey_batch_id INTEGER REFERENCES survey_batches(id),household_id INTEGER REFERENCES households(id),status TEXT);
            CREATE TABLE survey_person_year_records(id INTEGER PRIMARY KEY,survey_form_id INTEGER REFERENCES survey_forms(id),survey_person_id INTEGER REFERENCES survey_people(id),school_year_id INTEGER REFERENCES school_years(id),learning_status TEXT,is_literacy_target INTEGER,literacy_status TEXT,disability_support_details TEXT,extra_future_field TEXT);
            CREATE TABLE survey_form_investigators(id INTEGER PRIMARY KEY,survey_form_id INTEGER REFERENCES survey_forms(id),user_id INTEGER REFERENCES users(id));
            CREATE TABLE survey_person_year_disability_types(id INTEGER PRIMARY KEY,survey_person_year_record_id INTEGER REFERENCES survey_person_year_records(id),disability_type_code TEXT);
            INSERT INTO communes VALUES (1,'A','Commune A'),(2,'B','Commune B');
            INSERT INTO school_years VALUES (1,'2026-2027');
            INSERT INTO users VALUES (1,'teacher','Teacher','SECRET_NOT_EXPORTED');
            INSERT INTO survey_batches VALUES (1,'B1',1,1),(2,'B2',2,1);
            INSERT INTO households VALUES (1,1,'H1','Household A'),(2,2,'H2','Household B');
            INSERT INTO survey_people VALUES (1,1,'P1','Person A',0),(2,2,'P2','Person B',1);
            INSERT INTO survey_forms VALUES (1,1,1,'DA_HOAN_THANH'),(2,2,2,'DA_HOAN_THANH');
            INSERT INTO survey_person_year_records VALUES (1,1,1,1,'KHONG_THUOC_DIEN',1,'MU_CHU','Support','future value'),(2,2,2,1,'DANG_HOC',NULL,NULL,NULL,NULL);
            INSERT INTO survey_form_investigators VALUES (1,1,1);
            INSERT INTO survey_person_year_disability_types VALUES (1,1,'VAN_DONG');
        """)
        self.content, self.manifest = service.build_archive(self.con, 1, [1], {})

    def test_full_round_trip_scope_and_credentials(self):
        manifest, data = service.read_archive(self.content)
        self.assertEqual(set(data['households']), {1})
        self.assertEqual(data['survey_people'][1]['is_active'], 0)
        self.assertEqual(data['survey_person_year_records'][1]['extra_future_field'], 'future value')
        self.assertNotIn('password_hash', data['users'][1])
        with ZipFile(BytesIO(self.content)) as archive:
            self.assertFalse(any(b'SECRET_NOT_EXPORTED' in archive.read(name) for name in archive.namelist()))
        plan = service.restore_plan(self.con, manifest, data, [1])
        self.assertFalse(plan['conflicts'])
        self.assertEqual(plan['total_new'], 0)
        for table in ['survey_person_year_disability_types','survey_form_investigators','survey_person_year_records','survey_forms','survey_people','households','survey_batches']:
            self.con.execute(f'DELETE FROM {table} WHERE id=1')
        self.con.commit()
        self.con.execute('BEGIN IMMEDIATE')
        plan = service.restore_plan(self.con, manifest, data, [1])
        self.assertEqual(service.insert_missing(self.con, plan), 7)
        self.con.commit()
        self.assertFalse(self.con.execute('PRAGMA foreign_key_check').fetchall())
        again, _ = service.build_archive(self.con, 1, [1], {})
        self.assertEqual(service.read_archive(again)[1], data)

    def test_incomplete_and_corrupt_and_scope(self):
        self.con.execute("UPDATE survey_forms SET status='DANG_DIEU_TRA' WHERE id=1")
        with self.assertRaises(ValueError):
            service.build_archive(self.con, 1, [1], {})
        manifest, data = service.read_archive(self.content)
        with self.assertRaises(ValueError):
            service.restore_plan(self.con, manifest, data, [2])
        output = BytesIO()
        with ZipFile(BytesIO(self.content)) as source, ZipFile(output, 'w', ZIP_DEFLATED) as target:
            for name in source.namelist():
                target.writestr(name, b'[]' if name == 'tables/households.json' else source.read(name))
        with self.assertRaises(ValueError):
            service.read_archive(output.getvalue())

    def test_conflict_never_overwrites(self):
        manifest, data = service.read_archive(self.content)
        self.con.execute("UPDATE households SET head_name='Changed' WHERE id=1")
        self.con.commit()
        plan = service.restore_plan(self.con, manifest, data, [1])
        self.assertTrue(plan['conflicts'])
        with self.assertRaises(ValueError):
            service.insert_missing(self.con, plan)
        self.assertEqual(self.con.execute('SELECT head_name FROM households WHERE id=1').fetchone()[0], 'Changed')

    def test_routes_permissions_and_confirm(self):
        actor = {'id': 1, 'role_code': 'XA', 'commune_id': 1}
        app = FastAPI()
        app.include_router(routes.router)

        @app.middleware('http')
        async def auth(request, call_next):
            request.scope['auth_user'] = actor
            return await call_next(request)

        with patch.object(routes, 'DATABASE_PATH', self.path), TestClient(app) as client:
            self.assertEqual(client.get('/dieu-tra/luu-tru').status_code, 200)
            forbidden = client.post('/dieu-tra/luu-tru/xuat', data={'school_year_id': 1, 'commune_ids': 2})
            self.assertEqual(forbidden.status_code, 400)
            good = client.post('/dieu-tra/luu-tru/xuat', data={'school_year_id': 1, 'commune_ids': 1})
            self.assertEqual(good.status_code, 200)
            self.con.execute('DELETE FROM survey_person_year_disability_types')
            self.con.commit()
            preview = client.post('/dieu-tra/luu-tru/xem-truoc', files={'file': ('archive.zip', good.content)})
            self.assertEqual(preview.context['preview']['new'], 1)
            token = preview.context['token']
            actor['id'] = 2
            self.assertEqual(client.post('/dieu-tra/luu-tru/nhap', data={'token': token}).status_code, 400)
            actor['id'] = 1
            restored = client.post('/dieu-tra/luu-tru/nhap', data={'token': token})
            self.assertEqual(restored.status_code, 200)
            self.assertEqual(self.con.execute('SELECT count(*) FROM survey_person_year_disability_types').fetchone()[0], 1)
            actor['role_code'] = 'GIAO_VIEN'
            self.assertEqual(client.get('/dieu-tra/luu-tru', follow_redirects=False).status_code, 303)
        for role in ['XA','ADMIN','SO']:
            self.assertTrue(AccessControlMiddleware._co_quyen_theo_thao_tac(path='/dieu-tra/luu-tru/nhap',method='POST',role_code=role))
            self.assertTrue(AccessControlMiddleware._co_quyen_dieu_tra(db=None,path='/dieu-tra/luu-tru',auth_user={'role_code': role}))


if __name__ == '__main__':
    unittest.main()
