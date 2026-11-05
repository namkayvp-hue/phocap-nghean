"""Cross-commune selection regression tests; all data access is mocked."""
import re
import shutil
import subprocess
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import school_merger_future as routes


BASE = "/cong-cu-du-lieu/sap-nhap-truong/phat-sinh"


class CrossCommuneTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.role = "ADMIN"
        app = FastAPI()

        @app.middleware("http")
        async def auth(request, call_next):
            request.scope["auth_user"] = {"role_code": self.role}
            return await call_next(request)

        app.include_router(routes.router)
        self.client = self.stack.enter_context(TestClient(app))
        self.stack.enter_context(patch.object(routes, "list_school_years", return_value=[
            {"id": 2, "code": "2026-2027", "is_active": 1},
        ]))
        self.stack.enter_context(patch.object(routes, "list_communes", return_value=[
            {"id": 10, "name": "Xã A"}, {"id": 20, "name": "Xã B"},
        ]))
        self.stack.enter_context(patch.object(routes, "list_future_executions", return_value=[]))
        self.schools = self.stack.enter_context(patch.object(routes, "list_schools", side_effect=
            lambda year_id, commune_id, level_code, include_inactive: [
                {"id": commune_id * 10, "code": f"S{commune_id}", "name": f"School {commune_id}",
                 "commune_name": "Xã A" if commune_id == 10 else "Xã B", "levels": [level_code]},
            ]))
        self.execute = self.stack.enter_context(patch.object(routes, "execute_future_merge"))

    def tearDown(self):
        self.execute.assert_not_called()

    def page(self, **params):
        response = self.client.get(BASE, params={"school_year_id": 2, "commune_id": 10, **params})
        self.assertEqual(response.status_code, 200)
        return response

    def test_each_level_loads_independent_source_and_target_communes(self):
        for level in ("MN", "TH", "THCS", "THPT"):
            with self.subTest(level=level):
                self.schools.reset_mock()
                page = self.page(target_commune_id=20, level_code=level)
                self.assertEqual(page.context["schools"][0]["id"], 100)
                self.assertEqual(page.context["target_schools"][0]["id"], 200)
                self.schools.assert_any_call(year_id=2, commune_id=10, level_code=level, include_inactive=False)
                self.schools.assert_any_call(year_id=2, commune_id=20, level_code=level, include_inactive=False)
                self.assertEqual(self.schools.call_count, 2)

    def test_legacy_url_and_blank_target_keep_same_commune(self):
        for params in ({}, {"target_commune_id": ""}, {"target_commune_id": 10}):
            with self.subTest(params=params):
                self.schools.reset_mock()
                page = self.page(**params)
                self.assertEqual(page.context["schools"], page.context["target_schools"])
                self.assertEqual(page.context["selected_target_commune_id"], 10)
                self.schools.assert_called_once()

    def test_invalid_scope_does_not_load_all_schools(self):
        for params in ({"commune_id": ""}, {"commune_id": 999}, {"target_commune_id": 999}, {"target_commune_id": "bad"}):
            with self.subTest(params=params):
                self.schools.reset_mock()
                page = self.page(**params)
                self.assertEqual(page.context["target_schools"], [])
                self.assertIn('card disabled-box', page.text)
                for call in self.schools.call_args_list:
                    self.assertIsNotNone(call.kwargs["commune_id"])

    def preview_data(self):
        return {"school_year_id": "2", "commune_id": "10", "target_commune_id": "20",
                "level_code": "TH", "target_school_id": "200", "source_school_ids": ["100"]}

    def test_preview_keeps_cross_commune_ids_and_safety_controls(self):
        preview = {
            "school_year": {"id": 2, "code": "2026-2027"}, "level_code": "TH",
            "source_schools": [{"id": 100, "name": "Source", "commune_id": 10, "commune_name": "Xã A"}],
            "target_school": {"id": 200, "name": "Target", "commune_id": 20, "commune_name": "Xã B"},
            "summary": {}, "source_audit": {"fingerprint": "audit", "school_checks": []},
            "impact_state_fingerprint": "impact", "safe_for_execution": True,
        }
        with patch.object(routes, "build_future_preview", return_value=preview) as build:
            response = self.client.post(BASE + "/xem-truoc", data=self.preview_data())
        self.assertEqual(response.status_code, 200)
        build.assert_called_once_with(school_year_id=2, level_code="TH", target_school_id=200, source_ids=[100])
        self.assertIn('commune_id=10&target_commune_id=20', response.text)
        self.assertIn('name="expected_impact_state_fingerprint" value="impact"', response.text)
        self.assertIn('name="expected_source_audit_fingerprint" value="audit"', response.text)
        self.assertIn('id="exec-btn" class="btn primary" type="submit" disabled', response.text)

    def test_preview_error_and_missing_selection_preserve_filters(self):
        with patch.object(routes, "build_future_preview", side_effect=ValueError("Test error")):
            response = self.client.post(BASE + "/xem-truoc", data=self.preview_data())
        self.assertEqual(response.status_code, 409)
        self.assertIn('school_year_id=2&level_code=TH&commune_id=10&target_commune_id=20', response.text)
        data = self.preview_data()
        data.pop("target_school_id")
        response = self.client.post(BASE + "/xem-truoc", data=data, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn("target_commune_id=20", response.headers["location"])

    def test_non_admin_cannot_load_or_preview(self):
        self.role = "XA"
        with patch.object(routes, "build_future_preview") as build:
            for method, path, kwargs in (("get", BASE, {}), ("post", BASE + "/xem-truoc", {"data": self.preview_data()})):
                response = getattr(self.client, method)(path, follow_redirects=False, **kwargs)
                self.assertEqual(response.status_code, 303)
            build.assert_not_called()
        self.schools.assert_not_called()

    @unittest.skipUnless(shutil.which("node"), "Node required for browser-script regression")
    def test_browser_selects_cross_commune_schools_and_blocks_stale_scope(self):
        for target_commune in (10, 20):
            with self.subTest(target_commune=target_commune):
                html = self.page(target_commune_id=target_commune).text
                script = re.findall(r"<script>(.*?)</script>", html, re.S)[-1]
                harness = r'''
const assert=require('node:assert/strict');
class Element {
  constructor(){this.value='';this.children=[];this.listeners={};this.nodes={};this.classList={add(){},remove(){}}}
  set innerHTML(v){this.html=v;this.children=[];this.nodes={}}
  get innerHTML(){return this.html||''}
  appendChild(v){this.children.push(v)}
  querySelector(s){return this.nodes[s]||(this.nodes[s]=new Element())}
  addEventListener(t,f){this.listeners[t]=f}
}
const elements={};
const document={getElementById(id){return elements[id]||(elements[id]=new Element())},createElement(){return new Element()},addEventListener(){}};
let alerts=[];function alert(v){alerts.push(v)}
'''
                assertions = r'''
const src=elements['source-search'],tar=elements['target-search'];
src.value='School 10';src.oninput();
assert.equal(elements['source-results'].children.length,1);
elements['source-results'].children[0].onclick();
assert.equal(elements['hidden-sources'].children[0].value,100);
tar.value='School TARGET_COMMUNE';tar.oninput();
assert.equal(elements['target-results'].children.length,1);
elements['target-results'].children[0].onclick();
if(TARGET_COMMUNE===10){assert.equal(elements['target-id'].value,'');assert.equal(alerts.length,1)}
else {
  assert.equal(elements['target-id'].value,200);
  let prevented=false;const event={preventDefault(){prevented=true}};
  elements['merge-form'].onsubmit(event);assert.equal(prevented,false);
  elements['reload-form'].listeners.change();
  elements['merge-form'].onsubmit(event);assert.equal(prevented,true);
  assert.equal(elements['scope-changed'].hidden,false);
  src.value='School 20';src.oninput();assert.equal(elements['source-results'].children.length,0);
  tar.value='School 10';tar.oninput();assert.equal(elements['target-results'].children.length,0);
}
'''.replace("TARGET_COMMUNE", str(target_commune))
                result = subprocess.run([shutil.which("node"), "-"], input=harness + script + assertions,
                                        encoding="utf-8", capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
