# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment


API_MARK = "BAI_13B_11_17_V1_DASHBOARD_DAT_CHUAN_START"
UI_MARK = "BAI_13B_11_17_V1_DASHBOARD_UI_START"

API_CODE = '\n# === BAI_13B_11_17_V1_DASHBOARD_DAT_CHUAN_START ===\nfrom fastapi import Request as _PCGDDashboardRequest\nfrom fastapi.responses import JSONResponse as _PCGDDashboardJSONResponse\n\n@router.get("/{batch_id}/dashboard-dat-chuan-data")\ndef _dashboard_dat_chuan_data_v1(\n    batch_id: int,\n    request: _PCGDDashboardRequest,\n):\n    """\n    Dashboard 2.4.3:\n    - Lộ trình PCGDMN trẻ 3-5 tuổi: lấy từ JSON đã sinh từ file lộ trình.\n    - Trẻ 5 tuổi: so sánh 2 chỉ tiêu trẻ em theo NĐ 20/2014/NĐ-CP.\n    - Không tự kết luận xã đạt chuẩn toàn diện khi chưa đủ điều kiện GV/CSVC.\n    - Không ghi dữ liệu, chỉ đọc.\n    """\n    import json\n    import sqlite3\n    import unicodedata\n    from pathlib import Path\n\n    project_root = Path(__file__).resolve().parents[2]\n    db_path = project_root / "data" / "phocap.db"\n    roadmap_path = (\n        project_root\n        / "app"\n        / "data"\n        / "pcgd_recognition_roadmap_2026_2030.json"\n    )\n\n    def _norm(value):\n        text = str(value or "").strip().lower()\n        text = unicodedata.normalize("NFD", text)\n        text = "".join(\n            ch for ch in text\n            if unicodedata.category(ch) != "Mn"\n        )\n        return " ".join(text.split())\n\n    def _year(value):\n        try:\n            y = int(str(value).strip())\n        except Exception:\n            return None\n        return y if 2026 <= y <= 2030 else None\n\n    if not db_path.is_file():\n        return _PCGDDashboardJSONResponse(\n            {\n                "ok": False,\n                "message": "Không tìm thấy database.",\n            },\n            status_code=500,\n        )\n\n    con = sqlite3.connect(str(db_path))\n    con.row_factory = sqlite3.Row\n\n    try:\n        batch = con.execute(\n            """\n            SELECT\n                sb.id,\n                sb.school_year_id,\n                sb.commune_id,\n                sy.code AS school_year_code\n            FROM survey_batches sb\n            JOIN school_years sy\n              ON sy.id = sb.school_year_id\n            WHERE sb.id = ?\n            """,\n            (batch_id,),\n        ).fetchone()\n\n        if batch is None:\n            return _PCGDDashboardJSONResponse(\n                {\n                    "ok": False,\n                    "message": "Không tìm thấy đợt điều tra.",\n                },\n                status_code=404,\n            )\n\n        school_year_id = int(batch["school_year_id"])\n        school_year_code = str(\n            batch["school_year_code"] or ""\n        )\n\n        try:\n            start_year = int(\n                school_year_code.split("-")[0]\n            )\n        except Exception:\n            start_year = 2026\n\n        user_id = request.session.get("user_id")\n        viewer_commune_id = None\n        viewer_school_id = None\n\n        if user_id:\n            viewer = con.execute(\n                """\n                SELECT commune_id, school_id\n                FROM users\n                WHERE id = ?\n                """,\n                (user_id,),\n            ).fetchone()\n            if viewer is not None:\n                viewer_commune_id = viewer["commune_id"]\n                viewer_school_id = viewer["school_id"]\n\n        commune_rows = con.execute(\n            """\n            SELECT\n                id,\n                code,\n                name,\n                is_special_difficulty_area\n            FROM communes\n            WHERE is_active = 1\n            ORDER BY name\n            """\n        ).fetchall()\n\n        communes = []\n        by_norm_name = {}\n        by_code = {}\n\n        for row in commune_rows:\n            item = {\n                "id": int(row["id"]),\n                "code": str(row["code"] or ""),\n                "name": str(row["name"] or ""),\n                "is_special": bool(\n                    row["is_special_difficulty_area"]\n                ),\n            }\n            communes.append(item)\n            by_norm_name[_norm(item["name"])] = item\n            by_code[item["code"]] = item\n\n        # ------------------------------------------------------------\n        # Đọc lộ trình 3-5 tuổi theo cách linh hoạt.\n        # Hỗ trợ cả cấu trúc danh sách bản ghi và cấu trúc nhóm theo năm.\n        # ------------------------------------------------------------\n        roadmap = {}\n        roadmap_warning = None\n\n        if roadmap_path.is_file():\n            try:\n                raw_roadmap = json.loads(\n                    roadmap_path.read_text(\n                        encoding="utf-8-sig"\n                    )\n                )\n\n                def _match_commune(value):\n                    s = str(value or "").strip()\n                    if not s:\n                        return None\n                    if s in by_code:\n                        return by_code[s]\n                    return by_norm_name.get(_norm(s))\n\n                def _walk(obj, inherited_year=None):\n                    if isinstance(obj, dict):\n                        local_year = inherited_year\n\n                        for k, v in obj.items():\n                            kn = _norm(k)\n                            if (\n                                "year" in kn\n                                or kn in {\n                                    "nam",\n                                    "nam dat",\n                                    "nam dat chuan",\n                                    "nam dang ky",\n                                    "nam lo trinh",\n                                }\n                            ):\n                                y = _year(v)\n                                if y:\n                                    local_year = y\n\n                        found = []\n                        for k, v in obj.items():\n                            kn = _norm(k)\n                            if any(\n                                token in kn\n                                for token in (\n                                    "commune",\n                                    "xa",\n                                    "phuong",\n                                    "don vi",\n                                    "unit",\n                                    "name",\n                                    "code",\n                                    "ma",\n                                )\n                            ):\n                                c = _match_commune(v)\n                                if c is not None:\n                                    found.append(c)\n\n                        if local_year:\n                            for c in found:\n                                roadmap[c["id"]] = int(\n                                    local_year\n                                )\n\n                        for k, v in obj.items():\n                            key_year = _year(k)\n                            _walk(\n                                v,\n                                key_year or local_year,\n                            )\n\n                    elif isinstance(obj, list):\n                        for item in obj:\n                            _walk(item, inherited_year)\n\n                    elif isinstance(obj, str):\n                        if inherited_year:\n                            c = _match_commune(obj)\n                            if c is not None:\n                                roadmap[c["id"]] = int(\n                                    inherited_year\n                                )\n\n                _walk(raw_roadmap)\n\n                if len(roadmap) < len(communes):\n                    roadmap_warning = (\n                        "Đã đọc được lộ trình cho "\n                        f"{len(roadmap)}/{len(communes)} xã/phường."\n                    )\n            except Exception as exc:\n                roadmap_warning = (\n                    "Không đọc được file lộ trình: "\n                    + str(exc)\n                )\n        else:\n            roadmap_warning = (\n                "Chưa tìm thấy app/data/"\n                "pcgd_recognition_roadmap_2026_2030.json"\n            )\n\n        # ------------------------------------------------------------\n        # Tiến độ phiếu theo xã.\n        # ------------------------------------------------------------\n        progress_rows = con.execute(\n            """\n            SELECT\n                sb.commune_id,\n                COUNT(sf.id) AS form_total,\n                SUM(\n                    CASE\n                        WHEN sf.status = \'DA_HOAN_THANH\'\n                        THEN 1 ELSE 0\n                    END\n                ) AS completed_total\n            FROM survey_batches sb\n            LEFT JOIN survey_forms sf\n              ON sf.survey_batch_id = sb.id\n            WHERE sb.school_year_id = ?\n            GROUP BY sb.commune_id\n            """,\n            (school_year_id,),\n        ).fetchall()\n\n        progress = {\n            int(r["commune_id"]): {\n                "forms": int(r["form_total"] or 0),\n                "completed": int(\n                    r["completed_total"] or 0\n                ),\n            }\n            for r in progress_rows\n        }\n\n        # ------------------------------------------------------------\n        # Dữ liệu đối tượng theo năm học.\n        # Không suy diễn "đạt chuẩn toàn diện".\n        # Chỉ tính các chỉ báo trẻ em có nguồn trực tiếp trong CSDL.\n        # ------------------------------------------------------------\n        people_rows = con.execute(\n            """\n            SELECT DISTINCT\n                sb.commune_id,\n                p.id AS person_id,\n                p.date_of_birth,\n                p.residency_status,\n                pyr.learning_status,\n                pyr.completed_preschool_5,\n                pyr.completed_preschool_by_age\n            FROM survey_person_year_records pyr\n            JOIN survey_people p\n              ON p.id = pyr.survey_person_id\n            JOIN survey_forms sf\n              ON sf.id = pyr.survey_form_id\n            JOIN survey_batches sb\n              ON sb.id = sf.survey_batch_id\n            WHERE\n                pyr.school_year_id = ?\n                AND sb.school_year_id = ?\n                AND p.is_active = 1\n            """,\n            (\n                school_year_id,\n                school_year_id,\n            ),\n        ).fetchall()\n\n        metrics = {}\n\n        def _m(cid):\n            if cid not in metrics:\n                metrics[cid] = {\n                    "age_3_5_total": 0,\n                    "age_3_5_attending": 0,\n                    "age_5_total": 0,\n                    "age_5_attending": 0,\n                    "age_5_completed": 0,\n                }\n            return metrics[cid]\n\n        valid_residency = {\n            "THUONG_TRU",\n            "TAM_TRU",\n            "DANG_CU_TRU",\n            "CU_TRU",\n        }\n\n        birth_5 = start_year - 5\n        birth_4 = start_year - 4\n        birth_3 = start_year - 3\n\n        for row in people_rows:\n            dob = str(row["date_of_birth"] or "")\n            if len(dob) < 4:\n                continue\n\n            try:\n                birth_year = int(dob[:4])\n            except Exception:\n                continue\n\n            residence = str(\n                row["residency_status"] or ""\n            ).strip().upper()\n\n            if (\n                residence\n                and residence not in valid_residency\n            ):\n                continue\n\n            cid = int(row["commune_id"])\n            mm = _m(cid)\n\n            attending = (\n                str(\n                    row["learning_status"] or ""\n                ).strip().upper()\n                == "DANG_HOC"\n            )\n\n            completed = bool(\n                row["completed_preschool_by_age"]\n            ) or bool(\n                row["completed_preschool_5"]\n            )\n\n            if birth_year in {\n                birth_3,\n                birth_4,\n                birth_5,\n            }:\n                mm["age_3_5_total"] += 1\n                if attending:\n                    mm["age_3_5_attending"] += 1\n\n            if birth_year == birth_5:\n                mm["age_5_total"] += 1\n                if attending:\n                    mm["age_5_attending"] += 1\n                if completed:\n                    mm["age_5_completed"] += 1\n\n        def _pct(n, d):\n            if not d:\n                return None\n            return round(n * 100.0 / d, 2)\n\n        # ------------------------------------------------------------\n        # Phạm vi xem:\n        # - tài khoản Sở/Admin: commune_id trống -> toàn tỉnh.\n        # - tài khoản Xã/Trường/GV: chỉ xã của tài khoản.\n        # ------------------------------------------------------------\n        scoped_communes = communes\n        if viewer_commune_id:\n            scoped_communes = [\n                c\n                for c in communes\n                if c["id"] == int(viewer_commune_id)\n            ]\n\n        rows = []\n        target_counts = {}\n        summary = {\n            "total_communes": 0,\n            "roadmap_current_year": 0,\n            "survey_complete": 0,\n            "five_child_indicator_pass": 0,\n            "special_difficulty": 0,\n        }\n\n        for c in scoped_communes:\n            cid = c["id"]\n            target_year = roadmap.get(cid)\n            pp = progress.get(\n                cid,\n                {\n                    "forms": 0,\n                    "completed": 0,\n                },\n            )\n            mm = metrics.get(\n                cid,\n                {\n                    "age_3_5_total": 0,\n                    "age_3_5_attending": 0,\n                    "age_5_total": 0,\n                    "age_5_attending": 0,\n                    "age_5_completed": 0,\n                },\n            )\n\n            forms = pp["forms"]\n            completed_forms = pp["completed"]\n            survey_complete = (\n                forms > 0\n                and completed_forms >= forms\n            )\n\n            rate_3_5 = _pct(\n                mm["age_3_5_attending"],\n                mm["age_3_5_total"],\n            )\n            rate_5_attend = _pct(\n                mm["age_5_attending"],\n                mm["age_5_total"],\n            )\n            rate_5_complete = _pct(\n                mm["age_5_completed"],\n                mm["age_5_total"],\n            )\n\n            # NĐ20 - chỉ 2 chỉ tiêu trẻ em đang có nguồn trực tiếp:\n            # - đến lớp: 95%, ĐBKK 90%\n            # - hoàn thành CTGDMN: 85%, ĐBKK 80%\n            # Không dùng 2 chỉ tiêu này để thay thế kết luận đạt chuẩn toàn diện.\n            attend_threshold = (\n                90.0 if c["is_special"] else 95.0\n            )\n            complete_threshold = (\n                80.0 if c["is_special"] else 85.0\n            )\n\n            five_pass = (\n                survey_complete\n                and rate_5_attend is not None\n                and rate_5_complete is not None\n                and rate_5_attend\n                    >= attend_threshold\n                and rate_5_complete\n                    >= complete_threshold\n            )\n\n            if not survey_complete:\n                five_status = "Chưa đủ dữ liệu"\n                five_status_code = "DATA"\n            elif (\n                rate_5_attend is None\n                or rate_5_complete is None\n            ):\n                five_status = "Chưa có đối tượng 5 tuổi"\n                five_status_code = "EMPTY"\n            elif five_pass:\n                five_status = (\n                    "Đạt 2 chỉ tiêu trẻ em NĐ20"\n                )\n                five_status_code = "PASS"\n            else:\n                five_status = (\n                    "Chưa đạt 2 chỉ tiêu trẻ em NĐ20"\n                )\n                five_status_code = "FAIL"\n\n            if target_year is None:\n                roadmap_status = "Chưa có lộ trình"\n                roadmap_code = "NONE"\n            elif target_year < start_year:\n                roadmap_status = (\n                    "Đã quá năm đăng ký - cần rà soát"\n                )\n                roadmap_code = "LATE"\n            elif target_year == start_year:\n                roadmap_status = (\n                    "Năm đăng ký đạt chuẩn"\n                )\n                roadmap_code = "DUE"\n            else:\n                roadmap_status = (\n                    f"Còn {target_year - start_year} năm"\n                )\n                roadmap_code = "ON_TRACK"\n\n            if target_year:\n                target_counts[str(target_year)] = (\n                    target_counts.get(\n                        str(target_year),\n                        0,\n                    )\n                    + 1\n                )\n\n            summary["total_communes"] += 1\n\n            if target_year == start_year:\n                summary[\n                    "roadmap_current_year"\n                ] += 1\n\n            if survey_complete:\n                summary["survey_complete"] += 1\n\n            if five_pass:\n                summary[\n                    "five_child_indicator_pass"\n                ] += 1\n\n            if c["is_special"]:\n                summary["special_difficulty"] += 1\n\n            rows.append(\n                {\n                    "commune_id": cid,\n                    "code": c["code"],\n                    "name": c["name"],\n                    "is_special": c["is_special"],\n                    "target_year_3_5": target_year,\n                    "roadmap_status": roadmap_status,\n                    "roadmap_code": roadmap_code,\n                    "forms": forms,\n                    "completed_forms": completed_forms,\n                    "survey_complete": survey_complete,\n                    "age_3_5_total":\n                        mm["age_3_5_total"],\n                    "age_3_5_attending":\n                        mm["age_3_5_attending"],\n                    "rate_3_5_attending": rate_3_5,\n                    "age_5_total":\n                        mm["age_5_total"],\n                    "age_5_attending":\n                        mm["age_5_attending"],\n                    "rate_5_attending":\n                        rate_5_attend,\n                    "age_5_completed":\n                        mm["age_5_completed"],\n                    "rate_5_completed":\n                        rate_5_complete,\n                    "attend_threshold":\n                        attend_threshold,\n                    "complete_threshold":\n                        complete_threshold,\n                    "five_status": five_status,\n                    "five_status_code":\n                        five_status_code,\n                }\n            )\n\n        rows.sort(\n            key=lambda x: (\n                x["target_year_3_5"]\n                if x["target_year_3_5"]\n                is not None\n                else 9999,\n                x["name"],\n            )\n        )\n\n        return _PCGDDashboardJSONResponse(\n            {\n                "ok": True,\n                "school_year_id": school_year_id,\n                "school_year_code": school_year_code,\n                "analysis_year": start_year,\n                "scope": (\n                    "COMMUNE"\n                    if viewer_commune_id\n                    else "PROVINCE"\n                ),\n                "viewer_commune_id":\n                    viewer_commune_id,\n                "viewer_school_id":\n                    viewer_school_id,\n                "roadmap_loaded":\n                    len(roadmap),\n                "roadmap_warning":\n                    roadmap_warning,\n                "summary": summary,\n                "target_counts": target_counts,\n                "rows": rows,\n                "notes": [\n                    (\n                        "Lộ trình 3-5 tuổi là kế hoạch đăng ký; "\n                        "không tự động đồng nghĩa xã đã đạt chuẩn."\n                    ),\n                    (\n                        "Phần 5 tuổi chỉ đánh giá 2 chỉ tiêu trẻ em "\n                        "có nguồn trực tiếp trong CSDL theo NĐ20; "\n                        "không thay thế kết luận công nhận toàn diện."\n                    ),\n                    (\n                        "Cờ xã đặc biệt khó khăn lấy từ "\n                        "communes.is_special_difficulty_area, "\n                        "không lấy cờ màu trong file lộ trình."\n                    ),\n                ],\n            }\n        )\n    finally:\n        con.close()\n# === BAI_13B_11_17_V1_DASHBOARD_DAT_CHUAN_END ===\n'
DASHBOARD_HTML = '\n<!-- === BAI_13B_11_17_V1_DASHBOARD_UI_START === -->\n<section id="pcgd-recognition-dashboard" class="pcgd-db">\n  <div class="pcgd-db-head">\n    <div>\n      <div class="pcgd-db-kicker">2.4.3 · PHÂN TÍCH PHỔ CẬP</div>\n      <h1>Dashboard lộ trình và xu hướng đạt chuẩn</h1>\n      <p>\n        Đối chiếu lộ trình PCGDMN trẻ 3–5 tuổi với dữ liệu điều tra;\n        đồng thời theo dõi riêng trẻ 5 tuổi theo các chỉ tiêu trẻ em NĐ20.\n      </p>\n    </div>\n    <div class="pcgd-db-tabs">\n      <button type="button" class="pcgd-tab active" data-tab="roadmap">\n        Trẻ 3–5 tuổi · Lộ trình\n      </button>\n      <button type="button" class="pcgd-tab" data-tab="five">\n        Trẻ 5 tuổi · NĐ20\n      </button>\n    </div>\n  </div>\n\n  <div id="pcgd-db-warning" class="pcgd-db-warning" hidden></div>\n\n  <div class="pcgd-db-cards">\n    <article><span>Tổng xã/phường</span><strong id="db-total">–</strong></article>\n    <article><span>Đăng ký đạt năm nay</span><strong id="db-due">–</strong></article>\n    <article><span>Điều tra hoàn thành</span><strong id="db-complete">–</strong></article>\n    <article><span>Đạt 2 chỉ tiêu trẻ 5 tuổi</span><strong id="db-five-pass">–</strong></article>\n    <article><span>Xã ĐBKK</span><strong id="db-special">–</strong></article>\n  </div>\n\n  <div class="pcgd-db-grid">\n    <section class="pcgd-panel">\n      <div class="pcgd-panel-head">\n        <div>\n          <small>KẾ HOẠCH</small>\n          <h2>Phân bố lộ trình 3–5 tuổi</h2>\n        </div>\n        <span id="db-roadmap-loaded" class="pcgd-pill">–</span>\n      </div>\n      <div id="db-roadmap-bars" class="pcgd-bars"></div>\n    </section>\n\n    <section class="pcgd-panel">\n      <div class="pcgd-panel-head">\n        <div>\n          <small>BỘ LỌC</small>\n          <h2>Danh sách xã/phường</h2>\n        </div>\n      </div>\n      <div class="pcgd-filter-row">\n        <input id="db-search" type="search" placeholder="Tìm xã/phường...">\n        <select id="db-year-filter">\n          <option value="">Tất cả năm lộ trình</option>\n          <option value="2026">2026</option>\n          <option value="2027">2027</option>\n          <option value="2028">2028</option>\n          <option value="2029">2029</option>\n          <option value="2030">2030</option>\n          <option value="NONE">Chưa có lộ trình</option>\n        </select>\n        <select id="db-status-filter">\n          <option value="">Tất cả trạng thái</option>\n          <option value="DUE">Năm đăng ký</option>\n          <option value="LATE">Quá năm đăng ký</option>\n          <option value="ON_TRACK">Chưa đến năm đăng ký</option>\n          <option value="PASS">5 tuổi đạt 2 chỉ tiêu</option>\n          <option value="FAIL">5 tuổi chưa đạt 2 chỉ tiêu</option>\n          <option value="DATA">Chưa đủ dữ liệu</option>\n        </select>\n      </div>\n    </section>\n  </div>\n\n  <section class="pcgd-panel pcgd-table-panel">\n    <div class="pcgd-panel-head">\n      <div>\n        <small>THEO DÕI CHI TIẾT</small>\n        <h2 id="db-table-title">Lộ trình 3–5 tuổi và mức sẵn sàng dữ liệu</h2>\n      </div>\n      <span id="db-row-count" class="pcgd-pill">0 xã/phường</span>\n    </div>\n\n    <div class="pcgd-table-wrap">\n      <table class="pcgd-table">\n        <thead id="db-table-head"></thead>\n        <tbody id="db-table-body">\n          <tr><td>Đang tải dashboard...</td></tr>\n        </tbody>\n      </table>\n    </div>\n  </section>\n\n  <div class="pcgd-db-notes">\n    <strong>Nguyên tắc:</strong>\n    <span>\n      Năm đăng ký là lộ trình kế hoạch, không dùng thay cho kết luận đạt chuẩn.\n      Kết quả 5 tuổi ở dashboard này mới phản ánh 2 chỉ tiêu trẻ em có nguồn dữ liệu trực tiếp.\n    </span>\n  </div>\n</section>\n\n<style>\n.pcgd-db{margin:0 0 28px;padding:24px;border:1px solid #d9e7f5;border-radius:20px;background:#f7fbff;color:#17324d;box-shadow:0 10px 30px rgba(23,50,77,.08)}\n.pcgd-db *{box-sizing:border-box}\n.pcgd-db-head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:18px}\n.pcgd-db-kicker,.pcgd-panel-head small{font-size:12px;font-weight:900;letter-spacing:.08em;color:#0b6dc6}\n.pcgd-db-head h1{margin:4px 0 6px;font-size:30px}\n.pcgd-db-head p{margin:0;color:#64778a;max-width:760px;line-height:1.5}\n.pcgd-db-tabs{display:flex;gap:8px;flex-wrap:wrap}\n.pcgd-tab{border:1px solid #c9dceb;background:#fff;color:#24506f;padding:10px 14px;border-radius:999px;font-weight:800;cursor:pointer}\n.pcgd-tab.active{background:#0b6dc6;color:#fff;border-color:#0b6dc6}\n.pcgd-db-warning{padding:10px 12px;margin:0 0 14px;border:1px solid #f1c56d;background:#fff8e8;border-radius:10px;color:#835e12}\n.pcgd-db-cards{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:16px 0}\n.pcgd-db-cards article{background:#fff;border:1px solid #dce9f4;border-radius:14px;padding:14px}\n.pcgd-db-cards span{display:block;font-size:12px;color:#6c7e8e;font-weight:700}\n.pcgd-db-cards strong{display:block;margin-top:5px;font-size:28px;color:#0757a3}\n.pcgd-db-grid{display:grid;grid-template-columns:1.05fr 1fr;gap:14px;margin:14px 0}\n.pcgd-panel{background:#fff;border:1px solid #dce9f4;border-radius:16px;padding:16px}\n.pcgd-panel-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}\n.pcgd-panel-head h2{margin:3px 0 0;font-size:19px}\n.pcgd-pill{display:inline-flex;padding:6px 10px;border-radius:999px;background:#edf6ff;color:#0b5ca8;font-size:12px;font-weight:900}\n.pcgd-bars{display:grid;gap:9px}\n.pcgd-bar-row{display:grid;grid-template-columns:54px 1fr 45px;align-items:center;gap:9px;font-size:13px}\n.pcgd-bar-track{height:11px;border-radius:999px;background:#e8eef5;overflow:hidden}\n.pcgd-bar-fill{height:100%;background:linear-gradient(90deg,#0b6dc6,#5aa9ef);border-radius:999px}\n.pcgd-filter-row{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:10px}\n.pcgd-filter-row input,.pcgd-filter-row select{width:100%;height:42px;border:1px solid #cbd9e5;border-radius:10px;padding:0 11px;background:#fff}\n.pcgd-table-panel{margin-top:14px}\n.pcgd-table-wrap{overflow:auto;border:1px solid #e1eaf2;border-radius:12px}\n.pcgd-table{width:100%;border-collapse:collapse;min-width:1050px;font-size:13px}\n.pcgd-table th{position:sticky;top:0;background:#edf5fc;color:#25445f;text-align:left;padding:11px;border-bottom:1px solid #d7e3ed;white-space:nowrap}\n.pcgd-table td{padding:11px;border-bottom:1px solid #edf1f5;vertical-align:top}\n.pcgd-table tbody tr:hover{background:#f8fbfe}\n.pcgd-status{display:inline-flex;padding:5px 8px;border-radius:999px;font-size:11px;font-weight:900;white-space:nowrap}\n.pcgd-s-DUE{background:#fff0c7;color:#8a6000}.pcgd-s-LATE,.pcgd-s-FAIL{background:#ffe7e5;color:#a61c12}.pcgd-s-ON_TRACK,.pcgd-s-PASS{background:#e3f7e9;color:#18743b}.pcgd-s-DATA,.pcgd-s-EMPTY,.pcgd-s-NONE{background:#edf1f5;color:#5c6b78}\n.pcgd-metric{font-weight:900}.pcgd-muted{color:#7a8b99;font-size:12px}.pcgd-db-notes{margin-top:14px;padding:12px 14px;border-radius:12px;background:#eef7ff;color:#355c7b;line-height:1.5}\n@media(max-width:1000px){.pcgd-db-cards{grid-template-columns:repeat(2,1fr)}.pcgd-db-grid{grid-template-columns:1fr}.pcgd-db-head{flex-direction:column}.pcgd-filter-row{grid-template-columns:1fr}}\n@media(max-width:600px){.pcgd-db{padding:14px}.pcgd-db-cards{grid-template-columns:1fr}.pcgd-db-head h1{font-size:24px}}\n</style>\n\n<script>\n(function(){\n  const root=document.getElementById(\'pcgd-recognition-dashboard\');\n  if(!root) return;\n\n  let DATA=null;\n  let TAB=\'roadmap\';\n\n  const el=id=>document.getElementById(id);\n  const fmt=v=>(v===null||v===undefined)?\'—\':String(v);\n  const pct=v=>(v===null||v===undefined)?\'—\':Number(v).toFixed(2)+\'%\';\n  const badge=(text,code)=>`<span class="pcgd-status pcgd-s-${code||\'DATA\'}">${text}</span>`;\n\n  function endpoint(){\n    return window.location.pathname\n      .replace(/\\/xu-huong-lien-nam\\/?$/,\'/dashboard-dat-chuan-data\');\n  }\n\n  function renderCards(){\n    const s=DATA.summary||{};\n    el(\'db-total\').textContent=fmt(s.total_communes);\n    el(\'db-due\').textContent=fmt(s.roadmap_current_year);\n    el(\'db-complete\').textContent=fmt(s.survey_complete);\n    el(\'db-five-pass\').textContent=fmt(s.five_child_indicator_pass);\n    el(\'db-special\').textContent=fmt(s.special_difficulty);\n    el(\'db-roadmap-loaded\').textContent=`Lộ trình ${fmt(DATA.roadmap_loaded)}/${fmt(s.total_communes)}`;\n  }\n\n  function renderBars(){\n    const wrap=el(\'db-roadmap-bars\');\n    const counts=DATA.target_counts||{};\n    const years=[\'2026\',\'2027\',\'2028\',\'2029\',\'2030\'];\n    const max=Math.max(1,...years.map(y=>Number(counts[y]||0)));\n    wrap.innerHTML=years.map(y=>{\n      const n=Number(counts[y]||0);\n      const width=Math.round(n*100/max);\n      return `<div class="pcgd-bar-row"><strong>${y}</strong><div class="pcgd-bar-track"><div class="pcgd-bar-fill" style="width:${width}%"></div></div><span>${n} xã</span></div>`;\n    }).join(\'\');\n  }\n\n  function filteredRows(){\n    const q=el(\'db-search\').value.trim().toLowerCase();\n    const year=el(\'db-year-filter\').value;\n    const status=el(\'db-status-filter\').value;\n\n    return (DATA.rows||[]).filter(r=>{\n      if(q && !(`${r.name} ${r.code}`.toLowerCase().includes(q))) return false;\n\n      if(year){\n        if(year===\'NONE\'){\n          if(r.target_year_3_5!==null) return false;\n        }else if(String(r.target_year_3_5)!==year){\n          return false;\n        }\n      }\n\n      if(status){\n        const codes=[r.roadmap_code,r.five_status_code];\n        if(!codes.includes(status)) return false;\n      }\n      return true;\n    });\n  }\n\n  function renderTable(){\n    const rows=filteredRows();\n    el(\'db-row-count\').textContent=`${rows.length} xã/phường`;\n\n    if(TAB===\'roadmap\'){\n      el(\'db-table-title\').textContent=\'Lộ trình 3–5 tuổi và mức sẵn sàng dữ liệu\';\n      el(\'db-table-head\').innerHTML=`<tr>\n        <th>Xã/phường</th><th>Năm đăng ký</th><th>Trạng thái lộ trình</th>\n        <th>Tiến độ điều tra</th><th>Trẻ 3–5 trong dữ liệu</th>\n        <th>Đang học</th><th>Tỷ lệ huy động dữ liệu</th><th>Ghi chú</th>\n      </tr>`;\n      el(\'db-table-body\').innerHTML=rows.map(r=>`<tr>\n        <td><strong>${r.name}</strong><div class="pcgd-muted">${r.code}${r.is_special?\' · ĐBKK\':\'\'}</div></td>\n        <td class="pcgd-metric">${fmt(r.target_year_3_5)}</td>\n        <td>${badge(r.roadmap_status,r.roadmap_code)}</td>\n        <td><strong>${r.completed_forms}/${r.forms}</strong><div class="pcgd-muted">${r.survey_complete?\'Hoàn thành\':\'Chưa hoàn thành\'}</div></td>\n        <td>${r.age_3_5_total}</td>\n        <td>${r.age_3_5_attending}</td>\n        <td class="pcgd-metric">${pct(r.rate_3_5_attending)}</td>\n        <td class="pcgd-muted">Chỉ báo trẻ em; chưa thay kết luận chuẩn toàn diện.</td>\n      </tr>`).join(\'\') || \'<tr><td colspan="8">Không có dữ liệu phù hợp.</td></tr>\';\n    }else{\n      el(\'db-table-title\').textContent=\'Trẻ 5 tuổi – so sánh 2 chỉ tiêu trẻ em theo NĐ20\';\n      el(\'db-table-head\').innerHTML=`<tr>\n        <th>Xã/phường</th><th>Nhóm ngưỡng</th><th>Trẻ 5 tuổi</th>\n        <th>Đến lớp</th><th>Ngưỡng đến lớp</th>\n        <th>Hoàn thành CTGDMN</th><th>Ngưỡng hoàn thành</th><th>Đánh giá</th>\n      </tr>`;\n      el(\'db-table-body\').innerHTML=rows.map(r=>`<tr>\n        <td><strong>${r.name}</strong><div class="pcgd-muted">${r.code}</div></td>\n        <td>${r.is_special?badge(\'ĐBKK\',\'DUE\'):badge(\'Thông thường\',\'DATA\')}</td>\n        <td>${r.age_5_total}</td>\n        <td class="pcgd-metric">${r.age_5_attending} · ${pct(r.rate_5_attending)}</td>\n        <td>≥ ${r.attend_threshold}%</td>\n        <td class="pcgd-metric">${r.age_5_completed} · ${pct(r.rate_5_completed)}</td>\n        <td>≥ ${r.complete_threshold}%</td>\n        <td>${badge(r.five_status,r.five_status_code)}</td>\n      </tr>`).join(\'\') || \'<tr><td colspan="8">Không có dữ liệu phù hợp.</td></tr>\';\n    }\n  }\n\n  function render(){\n    renderCards();\n    renderBars();\n    renderTable();\n    if(DATA.roadmap_warning){\n      const w=el(\'pcgd-db-warning\');\n      w.hidden=false;\n      w.textContent=DATA.roadmap_warning;\n    }\n  }\n\n  root.querySelectorAll(\'.pcgd-tab\').forEach(btn=>{\n    btn.addEventListener(\'click\',()=>{\n      root.querySelectorAll(\'.pcgd-tab\').forEach(b=>b.classList.remove(\'active\'));\n      btn.classList.add(\'active\');\n      TAB=btn.dataset.tab;\n      renderTable();\n    });\n  });\n\n  [\'db-search\',\'db-year-filter\',\'db-status-filter\'].forEach(id=>{\n    el(id).addEventListener(\'input\',renderTable);\n    el(id).addEventListener(\'change\',renderTable);\n  });\n\n  fetch(endpoint(),{headers:{\'Accept\':\'application/json\'},cache:\'no-store\'})\n    .then(r=>r.json())\n    .then(data=>{\n      if(!data.ok) throw new Error(data.message||\'Không tải được dashboard.\');\n      DATA=data;\n      render();\n    })\n    .catch(err=>{\n      el(\'db-table-body\').innerHTML=`<tr><td>Lỗi tải dashboard: ${String(err.message||err)}</td></tr>`;\n    });\n})();\n</script>\n<!-- === BAI_13B_11_17_V1_DASHBOARD_UI_END === -->\n'

MENU_OLD = '<a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/xu-huong-lien-nam" role="menuitem">2.4.3. Xu hướng liên năm</a>'
MENU_NEW = '<a href="/dieu-tra" data-batch-template="/dieu-tra/{batch_id}/xu-huong-lien-nam" role="menuitem">2.4.3. Dashboard lộ trình và xu hướng</a>'

TEMPLATE_MARKER = "<h1>Xu hướng phổ cập qua nhiều năm học</h1>"


def db_check(path: Path):
    if not path.is_file():
        return "missing", 0

    con = sqlite3.connect(
        f"file:{path.as_posix()}?mode=ro",
        uri=True,
    )
    try:
        integrity = con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]
        fk = len(
            con.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )
        return str(integrity), int(fk)
    finally:
        con.close()


def main():
    root = Path(r"C:\PhoCap")
    if not (root / "app").is_dir():
        root = Path.cwd()

    trend_py = root / "app" / "routers" / "survey_trends.py"
    trend_html = root / "app" / "templates" / "surveys" / "multi_year_trend.html"
    menu_html = root / "app" / "templates" / "partials" / "dropdown_menu_v1.html"
    roadmap_json = root / "app" / "data" / "pcgd_recognition_roadmap_2026_2030.json"
    db_path = root / "data" / "phocap.db"

    print("=" * 110)
    print("BÀI 13B-11-17 V1 - 2.4.3 DASHBOARD LỘ TRÌNH VÀ XU HƯỚNG ĐẠT CHUẨN")
    print("=" * 110)
    print("Dự án:", root)

    required = [trend_py, trend_html, menu_html, db_path]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        print("DỪNG AN TOÀN: thiếu file bắt buộc:")
        for p in missing:
            print(" -", p)
        return 2

    if not roadmap_json.is_file():
        print("DỪNG AN TOÀN: chưa có file lộ trình:")
        print(" -", roadmap_json)
        return 3

    trend_text = trend_py.read_text(encoding="utf-8")
    tpl_text = trend_html.read_text(encoding="utf-8")
    menu_text = menu_html.read_text(encoding="utf-8")

    if API_MARK in trend_text and UI_MARK in tpl_text:
        print("Dashboard V1 đã có. Không cài lặp.")
        return 0

    if "router = APIRouter" not in trend_text and "APIRouter(" not in trend_text:
        print("DỪNG AN TOÀN: survey_trends.py không có router như dự kiến.")
        return 4

    if TEMPLATE_MARKER not in tpl_text:
        print("DỪNG AN TOÀN: không tìm thấy tiêu đề Xu hướng trong template hiện tại.")
        return 5

    if MENU_OLD not in menu_text and MENU_NEW not in menu_text:
        print("DỪNG AN TOÀN: không tìm thấy đúng menu 2.4.3 hiện tại.")
        return 6

    integrity, fk = db_check(db_path)
    print("Database integrity_check:", integrity)
    print("Database foreign_key_check:", fk, "lỗi")

    if integrity.lower() != "ok" or fk != 0:
        print("DỪNG AN TOÀN: database chưa đạt kiểm tra.")
        return 7

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "exports" / f"backup_truoc_bai_13b_11_17_v1_{stamp}"

    files_to_backup = [trend_py, trend_html, menu_html, db_path, roadmap_json]
    for src in files_to_backup:
        rel = src.relative_to(root)
        dst = backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    print("Đã backup:", backup)

    try:
        # 1) Appended API vào router đã được main.py đăng ký sẵn.
        if API_MARK not in trend_text:
            trend_new = (
                trend_text.rstrip()
                + "\n\n"
                + API_CODE.strip()
                + "\n"
            )
        else:
            trend_new = trend_text

        # 2) Chèn dashboard phía trên trang xu hướng cũ.
        if UI_MARK not in tpl_text:
            tpl_new = tpl_text.replace(
                TEMPLATE_MARKER,
                DASHBOARD_HTML.strip()
                + "\n\n"
                + TEMPLATE_MARKER,
                1,
            )
        else:
            tpl_new = tpl_text

        # 3) Chỉ đổi nhãn menu, giữ nguyên URL/route.
        if MENU_OLD in menu_text:
            menu_new = menu_text.replace(
                MENU_OLD,
                MENU_NEW,
                1,
            )
        else:
            menu_new = menu_text

        trend_py.write_text(
            trend_new,
            encoding="utf-8",
        )
        trend_html.write_text(
            tpl_new,
            encoding="utf-8",
        )
        menu_html.write_text(
            menu_new,
            encoding="utf-8",
        )

        py_compile.compile(
            str(trend_py),
            doraise=True,
        )

        env = Environment()
        env.parse(
            trend_html.read_text(
                encoding="utf-8"
            )
        )
        env.parse(
            menu_html.read_text(
                encoding="utf-8"
            )
        )

        verify_py = trend_py.read_text(
            encoding="utf-8"
        )
        verify_tpl = trend_html.read_text(
            encoding="utf-8"
        )
        verify_menu = menu_html.read_text(
            encoding="utf-8"
        )

        if API_MARK not in verify_py:
            raise RuntimeError(
                "Thiếu API dashboard sau cài."
            )
        if UI_MARK not in verify_tpl:
            raise RuntimeError(
                "Thiếu giao diện dashboard sau cài."
            )
        if "2.4.3. Dashboard lộ trình và xu hướng" not in verify_menu:
            raise RuntimeError(
                "Menu 2.4.3 chưa đổi đúng."
            )

    except Exception as exc:
        print("CÀI LỖI:", exc)
        print("Đang tự khôi phục...")
        for src in files_to_backup:
            rel = src.relative_to(root)
            saved = backup / rel
            if saved.is_file():
                shutil.copy2(saved, src)
        print("ĐÃ KHÔI PHỤC.")
        return 8

    integrity2, fk2 = db_check(db_path)

    report = root / "exports" / f"bao_cao_cai_bai_13b_11_17_v1_{stamp}.txt"
    report.write_text(
        "\n".join(
            [
                "BÁO CÁO CÀI BÀI 13B-11-17 V1",
                f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
                f"Dự án: {root}",
                "",
                "ĐÃ CÀI:",
                "1. 2.4.3 đổi thành Dashboard lộ trình và xu hướng.",
                "2. Tab Trẻ 3-5 tuổi: lộ trình 2026-2030 + tiến độ điều tra + chỉ báo huy động từ dữ liệu.",
                "3. Tab Trẻ 5 tuổi: so sánh 2 chỉ tiêu trẻ em NĐ20.",
                "4. Dùng communes.is_special_difficulty_area để áp ngưỡng ĐBKK.",
                "5. Giữ nguyên phần Xu hướng liên năm cũ phía dưới dashboard.",
                "6. Không thay đổi cấu trúc database.",
                "",
                f"Backup: {backup}",
                f"integrity_check sau cài: {integrity2}",
                f"foreign_key_check sau cài: {fk2} lỗi",
            ]
        ) + "\n",
        encoding="utf-8-sig",
    )

    print()
    print("=" * 110)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-11-17 V1")
    print("=" * 110)
    print("Đã sửa:")
    print(" - app/routers/survey_trends.py")
    print(" - app/templates/surveys/multi_year_trend.html")
    print(" - app/templates/partials/dropdown_menu_v1.html")
    print("Không thay đổi database.")
    print("Backup:", backup)
    print("Báo cáo:", report)
    print()
    print("Khởi động lại Uvicorn, Ctrl+F5, vào 2.4.3 để kiểm tra.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
