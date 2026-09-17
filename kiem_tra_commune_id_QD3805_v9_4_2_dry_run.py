# -*- coding: utf-8 -*-
r"""
DRY-RUN V9.4.2 - KIỂM TRA commune_id CỦA QĐ 3805
=================================================

MỤC TIÊU
--------
Chỉ đọc:
- C:\PhoCap\data\phocap.db
- C:\PhoCap\data\school_merger_approved_plans.json
- mã nguồn service/router/template sáp nhập hiện tại

Không sửa database.
Không sửa file phương án.
Không sửa mã nguồn.

Kiểm tra:
1. commune_id khai báo trong 6 nhóm QĐ 3805.
2. commune_id THỰC TẾ hiện tại của từng trường nguồn/đích trong bảng schools.
3. ID hiện tại của xã/phường có tên "Nghi Lộc" trong bảng communes.
4. commune_id=8 trên URL hiện là đơn vị nào.
5. Mã nguồn hiện tại có thực sự lọc plan theo commune_id hay đang bỏ qua bộ lọc.
6. Kết luận có nên vá mặc định xã hay phải sửa logic lọc trước.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_commune_id_QD3805_v9_4_2_dry_run.py

KẾT QUẢ
-------
    C:\PhoCap\dry_run_commune_id_QD3805_v9_4_2_<timestamp>.zip
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"

SERVICE = ROOT / "app" / "services" / "school_merger_service.py"
ROUTER = ROOT / "app" / "routers" / "school_merger.py"
MAIN_TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger.html"
PLANS_TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger_plans.html"

# Giá trị nhìn thấy trên URL trong ảnh người dùng vừa gửi.
OBSERVED_URL_COMMUNE_ID = 8


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [
        str(r[1])
        for r in con.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    ]


def normalize(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        ch for ch in text
        if unicodedata.category(ch) != "Mn"
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def find_name_col(cols: set[str]) -> str | None:
    for candidate in (
        "name", "commune_name", "school_name", "ten", "ten_xa", "ten_truong"
    ):
        if candidate in cols:
            return candidate
    return None


def find_code_col(cols: set[str]) -> str | None:
    for candidate in ("code", "school_code", "commune_code", "ma", "ma_truong"):
        if candidate in cols:
            return candidate
    return None


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def extract_function(text: str, function_name: str, max_lines: int = 180) -> str:
    """
    Lấy đoạn function theo thụt lề đơn giản, chỉ dùng để báo cáo mã nguồn.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^def\s+{re.escape(function_name)}\s*\(", line):
            start = i
            break
    if start is None:
        return f"[Không tìm thấy function {function_name}]"

    out = []
    for j in range(start, min(len(lines), start + max_lines)):
        line = lines[j]
        if j > start and re.match(r"^def\s+\w+\s*\(", line):
            break
        out.append(line)
    return "\n".join(out)


def load_qd3805_plans() -> tuple[dict, list[dict]]:
    if not PLAN_FILE.exists():
        raise AuditAbort(f"Không tìm thấy file phương án: {PLAN_FILE}")

    try:
        payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AuditAbort(f"Không đọc được JSON phương án: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("plans"), list):
        raise AuditAbort("File phương án không đúng cấu trúc {version, plans:[...]}.")

    plans = []
    for raw in payload["plans"]:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or "")
        doc = str(raw.get("document_code") or "")
        if pid.startswith("QD3805-") or "3805" in doc:
            item = dict(raw)
            try:
                item["school_year_id"] = (
                    int(item["school_year_id"])
                    if item.get("school_year_id") is not None else None
                )
            except (TypeError, ValueError):
                pass
            try:
                item["commune_id"] = (
                    int(item["commune_id"])
                    if item.get("commune_id") is not None else None
                )
            except (TypeError, ValueError):
                pass
            try:
                item["target_school_id"] = int(item["target_school_id"])
            except (TypeError, ValueError, KeyError):
                pass

            src = []
            for value in item.get("source_school_ids") or []:
                try:
                    src.append(int(value))
                except (TypeError, ValueError):
                    pass
            item["source_school_ids"] = src
            plans.append(item)

    if not plans:
        raise AuditAbort("Không tìm thấy nhóm QĐ 3805 trong file phương án.")

    return payload, plans


def commune_rows(con: sqlite3.Connection) -> tuple[list[dict], dict[int, dict]]:
    if not table_exists(con, "communes"):
        raise AuditAbort("Database không có bảng communes.")

    cols = set(columns(con, "communes"))
    name_col = find_name_col(cols)
    code_col = find_code_col(cols)

    if "id" not in cols or name_col is None:
        raise AuditAbort(
            f"Không xác định được id/name của communes. Columns={sorted(cols)}"
        )

    select = [f"{qident('id')} AS id", f"{qident(name_col)} AS name"]
    if code_col:
        select.append(f"{qident(code_col)} AS code")
    if "is_active" in cols:
        select.append(f"{qident('is_active')} AS is_active")

    rows = con.execute(
        "SELECT " + ",".join(select) + " FROM communes ORDER BY id"
    ).fetchall()

    out = []
    by_id = {}
    for r in rows:
        d = {
            "id": int(r["id"]),
            "name": str(r["name"] or ""),
            "code": str(r["code"] or "") if "code" in r.keys() else "",
            "is_active": r["is_active"] if "is_active" in r.keys() else "",
            "normalized_name": normalize(r["name"]),
        }
        out.append(d)
        by_id[d["id"]] = d
    return out, by_id


def school_rows(
    con: sqlite3.Connection,
    school_ids: list[int],
    communes_by_id: dict[int, dict],
) -> list[dict]:
    if not table_exists(con, "schools"):
        raise AuditAbort("Database không có bảng schools.")

    cols = set(columns(con, "schools"))
    name_col = find_name_col(cols)
    code_col = find_code_col(cols)

    if "id" not in cols or "commune_id" not in cols or name_col is None:
        raise AuditAbort(
            f"Không xác định được id/name/commune_id của schools. Columns={sorted(cols)}"
        )

    select = [
        f"{qident('id')} AS id",
        f"{qident(name_col)} AS name",
        f"{qident('commune_id')} AS commune_id",
    ]
    if code_col:
        select.append(f"{qident(code_col)} AS code")
    if "is_active" in cols:
        select.append(f"{qident('is_active')} AS is_active")

    if not school_ids:
        return []

    marks = ",".join("?" for _ in school_ids)
    rows = con.execute(
        "SELECT " + ",".join(select)
        + f" FROM schools WHERE id IN ({marks}) ORDER BY id",
        school_ids,
    ).fetchall()

    out = []
    for r in rows:
        cid = int(r["commune_id"]) if r["commune_id"] is not None else None
        c = communes_by_id.get(cid or -1, {})
        out.append({
            "school_id": int(r["id"]),
            "school_name": str(r["name"] or ""),
            "school_code": str(r["code"] or "") if "code" in r.keys() else "",
            "school_is_active": r["is_active"] if "is_active" in r.keys() else "",
            "actual_commune_id": cid,
            "actual_commune_name": c.get("name", ""),
            "actual_commune_code": c.get("code", ""),
        })
    return out


def main() -> None:
    print("=" * 116)
    print("DRY-RUN V9.4.2 - KIỂM TRA commune_id QĐ 3805")
    print("=" * 116)
    print("Chế độ: CHỈ ĐỌC - KHÔNG SỬA DATABASE / JSON / MÃ NGUỒN")

    for p in (DB_PATH, PLAN_FILE, SERVICE, ROUTER):
        if not p.exists():
            raise AuditAbort(f"Không tìm thấy: {p}")

    payload, plans = load_qd3805_plans()

    con = connect_ro(DB_PATH)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"dry_run_commune_id_QD3805_v9_4_2_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise AuditAbort(f"integrity_check={integrity}")

        communes, communes_by_id = commune_rows(con)

        # Tất cả school_id xuất hiện trong QĐ 3805.
        all_school_ids = set()
        for p in plans:
            all_school_ids.update(p.get("source_school_ids") or [])
            target = p.get("target_school_id")
            if isinstance(target, int):
                all_school_ids.add(target)

        schools = school_rows(
            con,
            sorted(all_school_ids),
            communes_by_id,
        )
        school_by_id = {x["school_id"]: x for x in schools}

        # Report plans.
        plan_rows = []
        for p in plans:
            plan_rows.append({
                "plan_id": p.get("id", ""),
                "document_code": p.get("document_code", ""),
                "school_year_id": p.get("school_year_id", ""),
                "plan_commune_id": p.get("commune_id", ""),
                "plan_commune_name": communes_by_id.get(
                    p.get("commune_id") if isinstance(p.get("commune_id"), int) else -1,
                    {},
                ).get("name", ""),
                "level_code": p.get("level_code", ""),
                "source_school_ids": ",".join(
                    str(x) for x in p.get("source_school_ids") or []
                ),
                "target_school_id": p.get("target_school_id", ""),
                "status": p.get("status", ""),
            })

        # Report school actual commune.
        school_report = []
        for p in plans:
            for role, sid in (
                [("TARGET", p.get("target_school_id"))]
                + [("SOURCE", x) for x in p.get("source_school_ids") or []]
            ):
                if not isinstance(sid, int):
                    continue
                s = school_by_id.get(sid)
                school_report.append({
                    "plan_id": p.get("id", ""),
                    "role": role,
                    "school_id": sid,
                    "school_name": s.get("school_name", "") if s else "",
                    "school_code": s.get("school_code", "") if s else "",
                    "school_is_active": s.get("school_is_active", "") if s else "",
                    "plan_commune_id": p.get("commune_id", ""),
                    "plan_commune_name": communes_by_id.get(
                        p.get("commune_id") if isinstance(p.get("commune_id"), int) else -1,
                        {},
                    ).get("name", ""),
                    "actual_commune_id": s.get("actual_commune_id", "") if s else "",
                    "actual_commune_name": s.get("actual_commune_name", "") if s else "",
                    "plan_vs_actual": (
                        "MATCH"
                        if s
                        and isinstance(p.get("commune_id"), int)
                        and p["commune_id"] == s.get("actual_commune_id")
                        else "MISMATCH"
                    ),
                })

        # Detect Nghi Lộc candidates.
        nghi_loc_rows = [
            c for c in communes
            if "nghi loc" in c["normalized_name"]
        ]

        observed_commune = communes_by_id.get(OBSERVED_URL_COMMUNE_ID)

        plan_commune_ids = {
            int(p["commune_id"])
            for p in plans
            if isinstance(p.get("commune_id"), int)
        }
        actual_commune_ids = {
            int(x["actual_commune_id"])
            for x in schools
            if x.get("actual_commune_id") is not None
        }
        mismatch_rows = [
            x for x in school_report
            if x["plan_vs_actual"] == "MISMATCH"
        ]

        # Inspect code.
        service_text = SERVICE.read_text(encoding="utf-8")
        router_text = ROUTER.read_text(encoding="utf-8")

        list_func = extract_function(service_text, "list_merger_plans")
        all_func = extract_function(service_text, "_all_merger_plans")
        context_func = extract_function(router_text, "_plan_page_context")

        filter_signals = {
            "service_has_commune_filter": (
                "commune_id" in list_func
                and (
                    "actual_commune_id" in list_func
                    or "plan_commune_id" in list_func
                    or "raw.get(\"commune_id\")" in list_func
                    or "raw.get('commune_id')" in list_func
                )
            ),
            "service_mentions_single_document_lock": (
                "SINGLE_DOCUMENT_LOCK" in service_text
            ),
            "service_list_func_uses_fixed_ids": (
                "SINGLE_DOCUMENT_PLAN_IDS" in list_func
                or "fixed_ids" in list_func
            ),
            "router_plan_context_passes_commune_id": (
                "commune_id=commune_id" in context_func
                or "commune_id = commune_id" in context_func
            ),
        }

        # Simulate simple expected filter by actual target commune and plan commune.
        observed_matches_plan_field = [
            p for p in plans
            if p.get("commune_id") == OBSERVED_URL_COMMUNE_ID
        ]
        observed_matches_target_actual = []
        for p in plans:
            sid = p.get("target_school_id")
            s = school_by_id.get(sid) if isinstance(sid, int) else None
            if s and s.get("actual_commune_id") == OBSERVED_URL_COMMUNE_ID:
                observed_matches_target_actual.append(p)

        # Gate / conclusion.
        blockers = []
        warnings = []

        if len(plan_commune_ids) != 1:
            blockers.append(
                "Các nhóm QĐ 3805 không có một plan_commune_id duy nhất."
            )

        if mismatch_rows:
            warnings.append(
                f"Có {len(mismatch_rows)} dòng trường có plan_commune_id khác "
                "commune_id thực tế hiện tại."
            )

        if observed_commune is None:
            warnings.append(
                f"commune_id={OBSERVED_URL_COMMUNE_ID} không tồn tại trong bảng communes."
            )

        # If observed ID matches neither plan nor actual target but UI still shows all,
        # then the filter is definitely being bypassed/ignored somewhere.
        observed_should_match_nothing = (
            len(observed_matches_plan_field) == 0
            and len(observed_matches_target_actual) == 0
        )

        if observed_should_match_nothing:
            warnings.append(
                f"commune_id={OBSERVED_URL_COMMUNE_ID} không khớp plan_commune_id "
                "và cũng không khớp commune_id thực tế của target QĐ 3805. "
                "Nếu giao diện vẫn hiển thị 6 nhóm thì logic lọc commune đang bị bỏ qua."
            )

        if filter_signals["service_list_func_uses_fixed_ids"]:
            warnings.append(
                "list_merger_plans có dấu hiệu lấy fixed QĐ3805 IDs; cần kiểm tra "
                "thứ tự áp dụng bộ lọc commune."
            )

        # Patch default link is safe only when unique current Nghi Lộc and current
        # target schools all use same commune id and plan data agrees.
        nghi_loc_ids = {x["id"] for x in nghi_loc_rows}
        safe_default_id = None
        if (
            len(actual_commune_ids) == 1
            and len(plan_commune_ids) == 1
            and actual_commune_ids == plan_commune_ids
            and len(nghi_loc_ids) == 1
            and actual_commune_ids == nghi_loc_ids
        ):
            safe_default_id = next(iter(actual_commune_ids))

        gate_rows = [
            {
                "check": "integrity_check",
                "result": "PASS",
                "detail": str(integrity),
            },
            {
                "check": "qd3805_plan_count",
                "result": "PASS" if len(plans) == 6 else "REVIEW",
                "detail": str(len(plans)),
            },
            {
                "check": "unique_plan_commune_id",
                "result": "PASS" if len(plan_commune_ids) == 1 else "REVIEW",
                "detail": ",".join(map(str, sorted(plan_commune_ids))),
            },
            {
                "check": "unique_actual_school_commune_id",
                "result": "PASS" if len(actual_commune_ids) == 1 else "REVIEW",
                "detail": ",".join(map(str, sorted(actual_commune_ids))),
            },
            {
                "check": "plan_vs_actual_school_commune",
                "result": "PASS" if not mismatch_rows else "REVIEW",
                "detail": f"mismatch_rows={len(mismatch_rows)}",
            },
            {
                "check": "nghi_loc_commune_candidates",
                "result": "PASS" if len(nghi_loc_rows) == 1 else "REVIEW",
                "detail": " | ".join(
                    f"{x['id']}:{x['name']}" for x in nghi_loc_rows
                ),
            },
            {
                "check": "observed_url_commune_id_8",
                "result": "INFO",
                "detail": (
                    f"{OBSERVED_URL_COMMUNE_ID}:"
                    + (
                        f"{observed_commune['name']}"
                        if observed_commune else "<NOT_FOUND>"
                    )
                ),
            },
            {
                "check": "commune_8_should_match_qd3805",
                "result": (
                    "YES"
                    if not observed_should_match_nothing
                    else "NO"
                ),
                "detail": (
                    f"plan_field_matches={len(observed_matches_plan_field)}; "
                    f"target_actual_matches={len(observed_matches_target_actual)}"
                ),
            },
            {
                "check": "service_commune_filter_signal",
                "result": (
                    "PASS"
                    if filter_signals["service_has_commune_filter"]
                    else "REVIEW"
                ),
                "detail": json.dumps(
                    filter_signals,
                    ensure_ascii=False,
                ),
            },
            {
                "check": "safe_to_patch_default_commune_only",
                "result": "YES" if safe_default_id is not None else "NO",
                "detail": (
                    str(safe_default_id)
                    if safe_default_id is not None
                    else "Cần sửa/hiểu logic lọc trước, chưa vá link mặc định."
                ),
            },
        ]

        write_csv(
            out_dir / "300_QD3805_PLAN_COMMUNE.csv",
            [
                "plan_id", "document_code", "school_year_id",
                "plan_commune_id", "plan_commune_name",
                "level_code", "source_school_ids",
                "target_school_id", "status",
            ],
            plan_rows,
        )
        write_csv(
            out_dir / "301_QD3805_SCHOOL_COMMUNE_REALITY.csv",
            [
                "plan_id", "role", "school_id",
                "school_name", "school_code", "school_is_active",
                "plan_commune_id", "plan_commune_name",
                "actual_commune_id", "actual_commune_name",
                "plan_vs_actual",
            ],
            school_report,
        )
        write_csv(
            out_dir / "302_COMMUNES_NGHI_LOC_AND_ID8.csv",
            [
                "kind", "id", "name", "code", "is_active",
                "normalized_name",
            ],
            (
                [
                    {
                        "kind": "NGHI_LOC_CANDIDATE",
                        **x,
                    }
                    for x in nghi_loc_rows
                ]
                + (
                    [{
                        "kind": "OBSERVED_URL_ID_8",
                        **observed_commune,
                    }]
                    if observed_commune else
                    [{
                        "kind": "OBSERVED_URL_ID_8",
                        "id": OBSERVED_URL_COMMUNE_ID,
                        "name": "<NOT_FOUND>",
                        "code": "",
                        "is_active": "",
                        "normalized_name": "",
                    }]
                )
            ),
        )
        write_csv(
            out_dir / "303_GATE_V9_4_2.csv",
            ["check", "result", "detail"],
            gate_rows,
        )

        evidence = out_dir / "304_MA_NGUON_LOC_COMMUNE.txt"
        evidence.write_text(
            "\n".join([
                "BẰNG CHỨNG MÃ NGUỒN - KHÔNG SỬA FILE",
                "=" * 100,
                "",
                "=== service: _all_merger_plans ===",
                all_func,
                "",
                "",
                "=== service: list_merger_plans ===",
                list_func,
                "",
                "",
                "=== router: _plan_page_context ===",
                context_func,
                "",
                "",
                "=== Signals ===",
                json.dumps(filter_signals, ensure_ascii=False, indent=2),
            ]),
            encoding="utf-8",
        )

        summary = out_dir / "00_TONG_QUAN_V9_4_2.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write("DRY-RUN V9.4.2 - KIỂM TRA commune_id QĐ 3805\n")
            f.write("=" * 116 + "\n")
            f.write("CHỈ ĐỌC - KHÔNG SỬA DATABASE / JSON / MÃ NGUỒN\n\n")

            f.write(f"Số nhóm QĐ 3805: {len(plans)}\n")
            f.write(
                "plan_commune_id: "
                + ",".join(map(str, sorted(plan_commune_ids)))
                + "\n"
            )
            f.write(
                "commune_id thực tế của các trường QĐ 3805: "
                + ",".join(map(str, sorted(actual_commune_ids)))
                + "\n"
            )
            f.write(
                "Xã/phường tên Nghi Lộc trong communes: "
                + (
                    " | ".join(f"{x['id']}:{x['name']}" for x in nghi_loc_rows)
                    if nghi_loc_rows else "<KHÔNG TÌM THẤY>"
                )
                + "\n"
            )
            f.write(
                f"commune_id={OBSERVED_URL_COMMUNE_ID} trên URL: "
                + (
                    observed_commune["name"]
                    if observed_commune else "<KHÔNG TỒN TẠI>"
                )
                + "\n\n"
            )

            f.write(
                f"ID 8 match plan commune field: {len(observed_matches_plan_field)} plan\n"
            )
            f.write(
                f"ID 8 match target actual commune: {len(observed_matches_target_actual)} plan\n"
            )
            f.write(
                f"Plan-vs-actual mismatch rows: {len(mismatch_rows)}\n\n"
            )

            f.write("TÍN HIỆU TỪ MÃ NGUỒN\n")
            for k, v in filter_signals.items():
                f.write(f"- {k}: {v}\n")

            f.write("\nCẢNH BÁO / NHẬN ĐỊNH\n")
            if not warnings:
                f.write("- Không có cảnh báo.\n")
            else:
                for w in warnings:
                    f.write("- " + w + "\n")

            f.write("\nKẾT LUẬN\n")
            if safe_default_id is not None:
                f.write(
                    f"SAFE_TO_PATCH_DEFAULT_COMMUNE_ONLY = YES ({safe_default_id})\n"
                )
                f.write(
                    "Có thể chỉ sửa link mặc định sang đúng commune_id này.\n"
                )
            else:
                f.write("SAFE_TO_PATCH_DEFAULT_COMMUNE_ONLY = NO\n")
                f.write(
                    "Chưa nên chạy bản vá link mặc định. Cần sửa/hiểu logic lọc "
                    "commune_id trước.\n"
                )

        zip_path = ROOT / f"dry_run_commune_id_QD3805_v9_4_2_{ts}.zip"
        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 116)
        print("HOÀN THÀNH DRY-RUN V9.4.2")
        print("=" * 116)
        print(f"Số nhóm QĐ 3805: {len(plans)}")
        print(
            "plan_commune_id: "
            + ",".join(map(str, sorted(plan_commune_ids)))
        )
        print(
            "commune_id thực tế các trường: "
            + ",".join(map(str, sorted(actual_commune_ids)))
        )
        print(
            "Nghi Lộc candidate: "
            + (
                " | ".join(f"{x['id']}:{x['name']}" for x in nghi_loc_rows)
                if nghi_loc_rows else "<KHÔNG TÌM THẤY>"
            )
        )
        print(
            f"commune_id={OBSERVED_URL_COMMUNE_ID}: "
            + (
                observed_commune["name"]
                if observed_commune else "<KHÔNG TỒN TẠI>"
            )
        )
        print(
            "SAFE_TO_PATCH_DEFAULT_COMMUNE_ONLY: "
            + (
                f"YES ({safe_default_id})"
                if safe_default_id is not None else "NO"
            )
        )
        print(f"ZIP: {zip_path}")
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")

    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except AuditAbort as exc:
        print()
        print("=" * 116)
        print("ĐÃ DỪNG DRY-RUN V9.4.2")
        print("=" * 116)
        print(str(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as exc:
        print()
        print("=" * 116)
        print("LỖI SQLITE TRONG DRY-RUN V9.4.2")
        print("=" * 116)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as exc:
        print()
        print("=" * 116)
        print("LỖI KHÔNG DỰ KIẾN TRONG DRY-RUN V9.4.2")
        print("=" * 116)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(4)
