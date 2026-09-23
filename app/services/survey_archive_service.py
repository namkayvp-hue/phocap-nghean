"""Versioned, scoped survey archives; restore missing rows without overwriting."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

FORMAT = "PHOCAP_SURVEY_ARCHIVE_V1"
MAX_ARCHIVE = 100 * 1024 * 1024
MAX_EXPANDED = 500 * 1024 * 1024
USER_COLUMNS = {"id", "username", "full_name", "school_id", "commune_id"}
SCOPES = {
    "survey_batch_id": "survey_batches", "survey_form_id": "survey_forms",
    "team_id": "survey_investigation_teams", "survey_person_year_record_id": "survey_person_year_records",
    "job_id": "survey_household_import_jobs", "survey_person_id": "survey_people",
    "household_id": "households", "area_id": "survey_commune_areas",
}


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def schema(con):
    result = {}
    for name, in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        result[name] = {
            "columns": [r[1] for r in con.execute(f"PRAGMA table_info({quote(name)})")],
            "foreign_keys": [{"column": r[3], "table": r[2], "target": r[4]} for r in con.execute(f"PRAGMA foreign_key_list({quote(name)})")],
        }
    for name, info in result.items():
        if name.startswith("survey_"):
            known = {fk["column"] for fk in info["foreign_keys"]}
            inferred = {**SCOPES, "school_id": "schools", "school_year_id": "school_years",
                        "commune_id": "communes", "actor_user_id": "users"}
            for column, parent in inferred.items():
                if column in info["columns"] and column not in known and parent in result:
                    info["foreign_keys"].append(dict(column=column, table=parent, target="id"))
    return result


def core_tables(metadata):
    return {name for name in metadata if name.startswith("survey_") or name == "households"}


def fetch_ids(con, table, column, ids):
    ids = sorted(set(ids))
    for start in range(0, len(ids), 500):
        chunk = ids[start:start+500]
        sql = f"SELECT * FROM {quote(table)} WHERE {quote(column)} IN ({','.join('?' for _ in chunk)})"
        cursor = con.execute(sql, chunk)
        keys = [d[0] for d in cursor.description]
        for row in cursor:
            yield dict(zip(keys, row))


def in_scope(table, row, data, communes, year):
    if table == "survey_batches":
        return row.get("commune_id") in communes and row.get("school_year_id") == year
    if table == "households":
        return row.get("commune_id") in communes
    if row.get("commune_id") is not None and row["commune_id"] not in communes:
        return False
    if row.get("school_year_id") is not None and row["school_year_id"] != year:
        return False
    linked = table in {"survey_commune_areas", "survey_file_exchange_logs"} and row.get("commune_id") in communes and row.get("school_year_id") == year
    for column, parent in SCOPES.items():
        value = row.get(column)
        if value is not None:
            if value not in data.get(parent, {}):
                return False
            linked = True
    return linked


def collect(con, year, commune_ids):
    metadata = schema(con)
    actual_communes = {r["id"] for r in fetch_ids(con, "communes", "id", commune_ids)}
    if not commune_ids or actual_communes != set(commune_ids):
        raise ValueError("Phạm vi xã không hợp lệ.")
    core = core_tables(metadata)
    data = {name: {} for name in core}
    for row in fetch_ids(con, "survey_batches", "commune_id", commune_ids):
        if row["school_year_id"] == year:
            data["survey_batches"][row["id"]] = row
    if not data["survey_batches"]:
        raise ValueError("Phạm vi đã chọn chưa có đợt điều tra trong năm học này.")
    # A finalized archive contains complete forms, including inactive people and all fields.
    for row in fetch_ids(con, "survey_forms", "survey_batch_id", data["survey_batches"]):
        data["survey_forms"][row["id"]] = row
    if not data["survey_forms"] or any(r["status"] != "DA_HOAN_THANH" for r in data["survey_forms"].values()):
        raise ValueError("Chỉ xuất lưu trữ sau khi tất cả phiếu trong phạm vi đã hoàn thành. Hãy kiểm tra tiến độ điều tra.")
    for row in fetch_ids(con, "households", "id", [r["household_id"] for r in data["survey_forms"].values()]):
        if row["commune_id"] not in commune_ids:
            raise ValueError("Phiếu có hộ nằm ngoài phạm vi xã; cần kiểm tra dữ liệu trước khi xuất.")
        data["households"][row["id"]] = row
    for row in fetch_ids(con, "survey_people", "household_id", data["households"]):
        data["survey_people"][row["id"]] = row
    if "survey_commune_areas" in metadata:
        for row in fetch_ids(con, "survey_commune_areas", "commune_id", commune_ids):
            if row["school_year_id"] == year:
                data["survey_commune_areas"][row["id"]] = row
    if "survey_file_exchange_logs" in metadata:
        for row in fetch_ids(con, "survey_file_exchange_logs", "commune_id", commune_ids):
            if row.get("survey_batch_id") is None and row.get("school_year_id") == year:
                data["survey_file_exchange_logs"][row["id"]] = row
    # Select descendants by every applicable scope column, not by year alone.
    for _ in range(len(core)):
        added = 0
        for table in sorted(core - {"survey_batches", "survey_forms", "households", "survey_people", "survey_commune_areas"}):
            for column, parent in SCOPES.items():
                if column not in metadata[table]["columns"]:
                    continue
                for row in fetch_ids(con, table, column, data.get(parent, {})):
                    if row["id"] not in data[table] and in_scope(table, row, data, commune_ids, year):
                        data[table][row["id"]] = row
                        added += 1
                break
        if not added:
            break
    # Include all referenced catalog records. Login credentials are never archived.
    for _ in range(len(metadata)):
        added = 0
        for table, rows in list(data.items()):
            if table == "users":
                continue
            for fk in metadata[table]["foreign_keys"]:
                parent = fk["table"]
                values = {r[fk["column"]] for r in rows.values() if r.get(fk["column"]) is not None}
                missing = values - set(data.get(parent, {}))
                if parent in core:
                    if missing:
                        raise ValueError(f"Liên kết dữ liệu {table} → {parent} không đầy đủ trong phạm vi xuất.")
                    continue
                for row in fetch_ids(con, parent, fk["target"] or "id", missing):
                    if parent == "users":
                        row = {k: v for k, v in row.items() if k in USER_COLUMNS}
                    data.setdefault(parent, {})[row["id"]] = row
                    added += 1
                if missing - set(data.get(parent, {})):
                    raise ValueError(f"Thiếu dữ liệu tham chiếu tại {parent}.")
        if not added:
            break
    return metadata, data


def build_archive(con, year, commune_ids, actor):
    metadata, data = collect(con, year, commune_ids)
    output = BytesIO()
    manifest = dict(format=FORMAT, created_at=datetime.now(timezone.utc).isoformat(),
                    school_year_id=year, commune_ids=sorted(commune_ids), actor=actor,
                    restore_mode="missing_rows_same_ids", tables={})
    expanded_size = 0
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, rows in sorted(data.items()):
            if not rows:
                continue
            content = json.dumps(list(rows.values()), ensure_ascii=False, default=str).encode("utf-8")
            expanded_size += len(content)
            if expanded_size > MAX_EXPANDED - 1024 * 1024:
                raise ValueError("Phạm vi lưu trữ quá lớn. Hãy chọn ít xã hơn và xuất thành nhiều gói.")
            manifest["tables"][name] = dict(count=len(rows), sha256=hashlib.sha256(content).hexdigest(),
                columns=list(next(iter(rows.values()))), foreign_keys=metadata[name]["foreign_keys"],
                kind="data" if name in core_tables(metadata) else "reference")
            archive.writestr(f"tables/{name}.json", content)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("HUONG_DAN.txt", "Gói lưu trữ đầy đủ dữ liệu điều tra theo năm học và xã.\n"
            "Gồm hộ, đối tượng, phiếu, thông tin học tập, xóa mù, khuyết tật, biến động, phân công và nhật ký.\n"
            "Giữ nguyên ID để khôi phục các bản ghi bị thiếu trên hệ thống có cùng danh mục tham chiếu.\n"
            "Nhập lại tại mục 2.6, xem trước rồi xác nhận. Không ghi đè bản ghi đang khác dữ liệu.\n"
            "Không dùng để chuyển sang năm học mới. Không chứa mật khẩu hoặc các file Excel nguồn đã tải lên.\n")
    if output.tell() > MAX_ARCHIVE:
        raise ValueError("Gói lưu trữ vượt 100 MB. Hãy chọn ít xã hơn và xuất thành nhiều gói.")
    return output.getvalue(), manifest


def read_archive(content):
    if len(content) > MAX_ARCHIVE:
        raise ValueError("Gói lưu trữ vượt quá 100 MB.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(i.file_size for i in archive.infolist()) > MAX_EXPANDED:
                raise ValueError("Gói lưu trữ có dung lượng giải nén quá lớn.")
            if len(archive.namelist()) != len(set(archive.namelist())):
                raise ValueError("Gói có tên file trùng lặp.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != FORMAT:
                raise ValueError("Không đúng định dạng lưu trữ điều tra của phần mềm.")
            data = {}
            for table, info in manifest["tables"].items():
                raw = archive.read(f"tables/{table}.json")
                if hashlib.sha256(raw).hexdigest() != info["sha256"]:
                    raise ValueError("File dữ liệu bị thay đổi hoặc hỏng: " + table)
                rows = json.loads(raw)
                if not isinstance(rows, list) or len(rows) != info["count"]:
                    raise ValueError("Số bản ghi không khớp: " + table)
                data[table] = {}
                for row in rows:
                    if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] <= 0 or row["id"] in data[table]:
                        raise ValueError("Mã bản ghi không hợp lệ: " + table)
                    data[table][row["id"]] = row
            return manifest, data
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Không đọc được gói lưu trữ. Hãy chọn file ZIP do mục 2.6 xuất ra.") from exc


def restore_plan(con, manifest, data, allowed_communes=None):
    metadata = schema(con)
    core = core_tables(metadata)
    communes = manifest.get("commune_ids")
    year = manifest.get("school_year_id")
    if not isinstance(communes, list) or not communes or any(type(i) is not int for i in communes) or type(year) is not int:
        raise ValueError("Phạm vi lưu trữ không hợp lệ.")
    if allowed_communes is not None and not set(communes) <= set(allowed_communes):
        raise ValueError("Gói lưu trữ chứa dữ liệu ngoài xã được phân quyền.")
    if not data.get("survey_batches") or not data.get("survey_forms"):
        raise ValueError("Gói không có đợt hoặc phiếu điều tra.")
    referenced_households = {r.get("household_id") for r in data["survey_forms"].values()}
    conflicts, missing, same = [], {}, 0
    for table, rows in data.items():
        if table not in metadata:
            raise ValueError("Phiên bản phần mềm chưa hỗ trợ bảng: " + table)
        if table not in core and manifest["tables"][table].get("kind") != "reference":
            raise ValueError("Bảng dữ liệu không được phép khôi phục: " + table)
        current = {r["id"]: r for r in fetch_ids(con, table, "id", rows)}
        for ident, row in rows.items():
            if set(row) - set(metadata[table]["columns"]):
                raise ValueError("Cấu trúc dữ liệu không tương thích tại " + table)
            if table in core:
                if set(row) != set(metadata[table]["columns"]):
                    raise ValueError("Thiếu trường dữ liệu tại " + table)
                if not in_scope(table, row, data, communes, year):
                    raise ValueError("Có bản ghi ngoài phạm vi lưu trữ: " + table)
                if table == "households" and ident not in referenced_households:
                    raise ValueError("Gói chứa hộ ngoài các phiếu đã chọn.")
                for fk in metadata[table]["foreign_keys"]:
                    value = row.get(fk["column"])
                    if value is not None and value not in data.get(fk["table"], {}):
                        raise ValueError("Thiếu liên kết dữ liệu: " + table)
            old = current.get(ident)
            if table not in core:
                # References must already exist with the same identity; never restore accounts/catalogs.
                keys = [k for k in ("id", "code", "username", "school_id", "school_year_id") if k in row]
                if old is None or any(old.get(k) != row[k] for k in keys):
                    conflicts.append(f"{table} #{ident}: thiếu hoặc khác danh mục tham chiếu")
            elif old is None:
                missing.setdefault(table, []).append(row)
            elif old != row:
                conflicts.append(f"{table} #{ident}: dữ liệu hiện tại khác bản lưu trữ")
            else:
                same += 1
    # Require all known survey descendant tables in the archive schema before inserting.
    return dict(missing=missing, same=same, conflicts=conflicts, total_new=sum(map(len, missing.values())))


def insert_missing(con, plan):
    if plan["conflicts"]:
        raise ValueError("Có xung đột; chưa thể khôi phục. Dữ liệu hiện tại được giữ nguyên.")
    metadata = schema(con)
    pending = dict(plan["missing"])
    inserted = 0
    while pending:
        ready = [t for t in pending if not any(f["table"] in pending and f["table"] != t for f in metadata[t]["foreign_keys"])]
        if not ready:
            raise ValueError("Không xác định được thứ tự khôi phục liên kết dữ liệu.")
        for table in ready:
            for row in pending.pop(table):
                columns = list(row)
                con.execute(f"INSERT INTO {quote(table)} ({','.join(map(quote, columns))}) VALUES ({','.join('?' for _ in columns)})", [row[k] for k in columns])
                inserted += 1
    return inserted
