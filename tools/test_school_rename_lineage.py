import json
import re
import shutil
import sqlite3
import subprocess
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import school_rename as routes
from app.services.school_rename_lineage import school_rename_lineage


class RenameLineageTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:", check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.addCleanup(self.con.close)
        self.con.executescript("""
            CREATE TABLE communes (id INTEGER PRIMARY KEY,name TEXT,is_active INTEGER);
            CREATE TABLE schools (id INTEGER PRIMARY KEY,code TEXT,name TEXT,commune_id INTEGER,is_active INTEGER);
            CREATE TABLE school_years (id INTEGER PRIMARY KEY,code TEXT,name TEXT,is_active INTEGER);
            CREATE TABLE school_merger_operations (id INTEGER PRIMARY KEY,school_year_id INTEGER,target_school_id INTEGER,source_school_ids_json TEXT,summary_json TEXT,created_at TEXT);
            CREATE TABLE school_name_histories (id INTEGER PRIMARY KEY,school_id INTEGER,effective_school_year_id INTEGER,old_name TEXT,new_name TEXT,changed_at TEXT);
            INSERT INTO communes VALUES (1,'Commune A',1),(2,'Commune B',1);
            INSERT INTO school_years VALUES (9,'2025-2026','Previous',0),(2,'2026-2027','Current',1),(1,'2027-2028','Next',0);
            INSERT INTO schools VALUES (10,'T10','New target name',1,1),(11,'S11','Source A',1,0),(12,'S12','Source B',2,0),(20,'T20','Unmerged school',1,1),(30,'T30','Other commune',2,1);
            INSERT INTO school_merger_operations VALUES (1,2,10,'[11,12]','{}','2026-09-01');
            INSERT INTO school_name_histories VALUES (1,10,2,'Original target','New target name','2026-10-01');
        """)
        self.schools = [dict(r) for r in self.con.execute("SELECT s.*,c.name AS commune_name FROM schools s JOIN communes c ON c.id=s.commune_id WHERE s.is_active=1 AND s.commune_id=1")]
        self.schools[0]["levels"] = ["MN"]
        self.schools[1]["levels"] = ["TH", "THCS"]
        self.user = {"id": 1, "role_code": "ADMIN"}
        app = FastAPI()

        @app.middleware("http")
        async def auth(request, call_next):
            request.scope["auth_user"] = self.user
            return await call_next(request)

        app.include_router(routes.router)
        stack = self.enterContext(ExitStack())
        self.client = stack.enter_context(TestClient(app))
        stack.enter_context(patch.object(routes, "_connect", return_value=self.con))
        stack.enter_context(patch.object(routes, "list_school_years", return_value=[dict(r) for r in self.con.execute("SELECT * FROM school_years")]))
        stack.enter_context(patch.object(routes, "list_communes", return_value=[dict(r) for r in self.con.execute("SELECT * FROM communes")]))
        stack.enter_context(patch.object(routes, "list_schools", side_effect=lambda **kwargs: [
            s for s in self.schools if kwargs["commune_id"] == 1
            and (not kwargs.get("level_code") or kwargs["level_code"] in s["levels"])
        ]))

    def lineage(self, year=2):
        return school_rename_lineage(self.con, schools=self.schools, school_year_id=year)

    def test_original_target_included_with_inactive_and_cross_commune_sources(self):
        before = list(self.con.iterdump())
        result = self.lineage()[0]
        self.assertEqual([s["id"] for s in result["before_schools"]], [10, 11, 12])
        self.assertEqual([s["name"] for s in result["before_schools"]], ["Original target", "Source A", "Source B"])
        self.assertEqual(result["merged_name"], "Original target")
        self.assertEqual(result["current_name"], "New target name")
        self.assertEqual(result["before_schools"][2]["commune_name"], "Commune B")
        self.assertEqual(list(self.con.iterdump()), before)

    def test_snapshot_names_take_precedence_and_future_year_excluded(self):
        summary = {"target_school_old_name": "Before merger", "target_school_name": "After merger", "source_school_names": ["Old A", "Old B"]}
        self.con.execute("UPDATE school_merger_operations SET summary_json=? WHERE id=1", (json.dumps(summary),))
        self.con.execute("INSERT INTO school_merger_operations VALUES (2,1,20,'[30]','{}','2027-09-01')")
        rows = self.lineage()
        self.assertEqual(rows[0]["before_schools"][0]["name"], "Before merger")
        self.assertEqual(rows[0]["before_schools"][1]["name"], "Old A")
        self.assertEqual(rows[0]["merged_name"], "After merger")
        self.assertFalse(rows[1]["has_merger"])
        self.assertFalse(self.lineage(year=9)[0]["has_merger"])
        self.assertTrue(self.lineage(year=1)[1]["has_merger"])

    def test_nested_mergers_deduplicate_and_ignore_rename_only_entries(self):
        self.con.execute("INSERT INTO school_merger_operations VALUES (2,9,11,'[30]','{}','2025-09-01')")
        self.con.execute("INSERT INTO school_merger_operations VALUES (3,2,10,'[11]','{}','2026-09-02')")
        self.con.execute("INSERT INTO school_merger_operations VALUES (4,2,20,'[]','{}','2026-09-02')")
        self.assertEqual({s["id"] for s in self.lineage()[0]["before_schools"]}, {10, 11, 12, 30})
        self.assertEqual(len(self.lineage()[0]["before_schools"]), 4)
        self.assertFalse(self.lineage()[1]["has_merger"])

    def test_missing_and_invalid_history_keeps_regular_rename_available(self):
        self.con.execute("UPDATE school_merger_operations SET source_school_ids_json='bad',summary_json='bad'")
        self.assertFalse(self.lineage()[0]["has_merger"])
        self.con.execute("DROP TABLE school_merger_operations")
        self.con.execute("DROP TABLE school_name_histories")
        self.assertEqual(len(self.lineage()), 2)
        self.assertFalse(self.lineage()[0]["has_merger"])

    def test_page_shows_mapping_after_commune_then_three_column_rename(self):
        response = self.client.get('/cong-cu-du-lieu/doi-ten-truong?school_year_id=2&commune_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Original target', response.text)
        self.assertIn('Source A', response.text)
        self.assertIn('school_id=10#rename-form', response.text)
        self.assertNotIn('school_id=11#rename-form', response.text)
        selected = self.client.get('/cong-cu-du-lieu/doi-ten-truong?school_year_id=2&commune_id=1&school_id=10')
        self.assertEqual(selected.status_code, 200)
        self.assertIn('id="rename-form"', selected.text)
        self.assertIn('name="school_id" value="10"', selected.text)
        self.assertIn('name="new_name"', selected.text)

    def test_school_account_cannot_expose_other_targets(self):
        self.user = {"id": 10, "role_code": "TRUONG", "school_id": 10}
        response = self.client.get('/cong-cu-du-lieu/doi-ten-truong?school_year_id=2&commune_id=2&school_id=30')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["school_id"] for r in response.context["school_lineage"]], [10])
        self.assertEqual(response.context["selected_school_id"], 10)
        self.user["role_code"] = "XA"
        self.assertEqual(self.client.get('/cong-cu-du-lieu/doi-ten-truong', follow_redirects=False).status_code, 303)

    def test_level_filters_schools_and_lineage_and_clears_stale_selection(self):
        for level, ids in (("MN", [10]), ("TH", [20]), ("THCS", [20]), ("THPT", []), ("", [10,20])):
            with self.subTest(level=level):
                response = self.client.get('/cong-cu-du-lieu/doi-ten-truong', params={
                    'school_year_id':2, 'commune_id':1, 'school_id':10, 'level_code':level,
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual([r['school_id'] for r in response.context['school_lineage']], ids)
                self.assertEqual(response.context['selected_school_id'], 10 if 10 in ids else None)
                self.assertEqual(response.context['selected_level_code'], level)

    def test_preview_preserves_level_filter(self):
        response = self.client.post('/cong-cu-du-lieu/doi-ten-truong/xem-truoc', data={
            'school_year_id':2, 'commune_id':1, 'school_id':20, 'level_code':'THCS', 'new_name':'Updated school',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_level_code'], 'THCS')
        self.assertEqual([r['school_id'] for r in response.context['school_lineage']], [20])
        self.assertIn('name="level_code" value="THCS"', response.text)

    @unittest.skipUnless(shutil.which("node"), "Node unavailable")
    def test_picker_loads_commune_automatically_and_old_name_selects_target(self):
        with patch.object(routes, 'list_communes', return_value=[
            {'id':1,'name':'Commune A','is_active':1},
            {'id':2,'name':'Phường Thành Vinh','is_active':1},
            {'id':3,'name':'Xã Thanh Phong','is_active':1},
            {'id':4,'name':'Xã Minh Thanh','is_active':1},
        ]):
            response = self.client.get('/cong-cu-du-lieu/doi-ten-truong?school_year_id=2&commune_id=1')
        script = re.findall(r'<script>(.*?)</script>', response.text, re.S)[-1]
        harness = r'''
const assert=require('node:assert/strict');
class Element {
 constructor(){this.value='';this.listeners={};this.children=[];this.classList={add(){},remove(){}};this.submitted=0;this.nodes={}}
 set innerHTML(v){this.children=[]} appendChild(v){this.children.push(v)}
 addEventListener(n,f){this.listeners[n]=f} requestSubmit(){this.submitted++} contains(){return false}
 querySelector(s){return this.nodes[s]||(this.nodes[s]=new Element())}
}
const nodes={};const document={getElementById(id){return nodes[id]||(nodes[id]=new Element())},createElement(){return new Element()},addEventListener(){}};
'''
        checks = r'''
nodes['school-search'].value='Source A';nodes['school-search'].listeners.input();
assert.equal(nodes['school-list'].children.length,1);
nodes['school-list'].children[0].listeners.mousedown({preventDefault(){}});
assert.equal(nodes['school-id'].value,10);
assert.equal(nodes['select-form'].submitted,1);
nodes['commune-search'].value='Commune A';nodes['commune-search'].listeners.input();
nodes['commune-list'].children[0].listeners.mousedown({preventDefault(){}});
assert.equal(nodes['commune-id'].value,1);assert.equal(nodes['school-id'].value,'');
assert.equal(nodes['select-form'].submitted,2);
nodes['commune-search'].value='thanh';nodes['commune-search'].listeners.input();
assert.deepEqual(nodes['commune-list'].children.map(c=>c.textContent),['Phường Thành Vinh','Xã Thanh Phong']);
nodes['commune-search'].value='phuong thanh';nodes['commune-search'].listeners.input();
assert.equal(nodes['commune-list'].children.length,1);
nodes['commune-list'].children[0].listeners.mousedown({preventDefault(){}});
assert.equal(nodes['commune-id'].value,2);
nodes['school-id'].value=10;nodes['level-code'].listeners.change();
assert.equal(nodes['school-id'].value,'');assert.equal(nodes['select-form'].submitted,4);
'''
        result = subprocess.run([shutil.which('node'), '-'], input=harness+script+checks, encoding='utf-8', capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
