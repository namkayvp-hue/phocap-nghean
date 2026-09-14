from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = Path(r"C:\PhoCap")

DB = ROOT / "data" / "phocap.db"

SERVICE = (
    ROOT
    / "app"
    / "services"
    / "school_merger_level_batch_service.py"
)

LOCK = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_level_lock.json"
)

ROSTER = (
    ROOT
    / "data"
    / "school_merger_source_rosters"
    / "THCS_2025_2026.json"
)

RESOLUTION = (
    ROOT
    / "data"
    / "school_merger_registry"
    / "qd3805_thcs_resolution.json"
)

HISTORY = (
    ROOT
    / "data"
    / "school_merger_approved_plans.json"
)


EXPECTED = {
    "db":
        "882e4925fd3e39d7e097ce127612c093"
        "852075e608d3f937294135282afec75a",

    "service":
        "9104fb99c78755e9eec86d090659b3a9"
        "22834ff097d7292aa4d4b29e360a27f9",

    "lock":
        "ad310048a4c5b239404e0902cc04fda1"
        "d73474d11a739a2ca009d2727e4390c3",

    "roster":
        "926528e0ae600a6b950b459c6f8ec5c"
        "6810e69d49158d1ff3c9a3d76c0bca657",

    "resolution":
        "d447e7475d1631051a6e7e04ac8d1c81"
        "fcb4b171d7f0d0980b963b1f07bedbc1",

    "history":
        "4e2c5f044c48c57dda40fecc11f4e9f"
        "466f236aacc082f224536b1685cadb1fc",
}


RULES = [
    {
        "operation_id": "QD3805-OP-0025",
        "display_title":
            "THCS Quang Trung + THCS Đội Cung",
        "relation_type":
            "XỬ LÝ RIÊNG – THIẾU DỮ LIỆU ĐỐI CHIẾU ĐÍCH",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Phương án cùng cấp rõ nguồn/đích nhưng THCS Quang Trung "
            "không có dữ liệu đội ngũ 2025-2026 trong snapshot; "
            "không hạ chuẩn source-audit để chạy tự động."
    },

    {
        "operation_id": "QD3805-OP-0108",
        "display_title":
            "PTDT Bán trú THCS Thạch Ngàn – THCS Mậu Đôn",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – TÁCH/GỘP",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "QĐ3805 có nội dung tách THCS Mậu Đôn và hình thành "
            "PTDT Bán trú THCS Thạch Ngàn; không coi là gộp toàn trường thông thường."
    },

    {
        "operation_id": "QD3805-OP-0126",
        "display_title":
            "THCS Diễn Ngọc – nhận điểm Diễn Hoa",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – GỘP TRƯỜNG + TIẾP NHẬN ĐIỂM",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Ngoài THCS Diễn Bích còn có tiếp nhận điểm Diễn Hoa "
            "từ THCS Hoa Quảng; không được chuyển toàn bộ THCS Hoa Quảng."
    },

    {
        "operation_id": "QD3805-OP-0132",
        "display_title":
            "Điểm Diễn Vạn của THCS Vạn Phong -> THCS Diễn Kỷ",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – TÁCH ĐIỂM",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "THCS Vạn Phong được tách về hai trường; "
            "không được chuyển toàn bộ school_id nguồn sang một đích."
    },

    {
        "operation_id": "QD3805-OP-0133",
        "display_title":
            "Điểm Diễn Phong của THCS Vạn Phong -> THCS Diễn Hồng",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – TÁCH ĐIỂM",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "THCS Vạn Phong được tách về hai trường; "
            "không được chạy engine sáp nhập toàn bộ trường."
    },

    {
        "operation_id": "QD3805-OP-0153",
        "display_title":
            "THCS Diễn Hạnh – Hoa Quảng (Diễn Quảng) – Thái Nguyên (Diễn Nguyên)",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – PHẦN CÒN LẠI SAU TÁCH ĐIỂM",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Các tên trong QĐ3805 biểu diễn phần/điểm của trường nguồn "
            "sau điều chuyển; không được suy ra toàn bộ school_id."
    },

    {
        "operation_id": "QD3805-OP-0160",
        "display_title":
            "THCS Liên Đồng – nhận điểm Diễn Thái",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – GỘP TRƯỜNG + TIẾP NHẬN ĐIỂM",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Có THCS Diễn Xuân, Diễn Tháp và đồng thời tiếp nhận "
            "điểm Diễn Thái của THCS Thái Nguyên; phải tách nghiệp vụ."
    },

    {
        "operation_id": "QD3805-OP-0172",
        "display_title":
            "THCS Đại Sơn – Lê Hồng Phong (Mỹ Sơn) – Trù Sơn",
        "relation_type":
            "XỬ LÝ RIÊNG – NGUỒN CHƯA KHÓA CHẮC",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Tên THCS Lê Hồng Phong (Mỹ Sơn) chưa khóa chắc vào "
            "school_id nguồn có dữ liệu 2025-2026; không tự suy đoán."
    },

    {
        "operation_id": "QD3805-OP-0191",
        "display_title":
            "THCS Nguyễn Thái Nhự – Nguyễn Văn Trỗi (Thịnh Sơn)",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – PHẦN CÒN LẠI SAU TÁCH ĐIỂM",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Điểm Hòa Sơn của Nguyễn Văn Trỗi được điều chuyển sang "
            "THCS Văn Hiến; không được chuyển toàn bộ Nguyễn Văn Trỗi."
    },

    {
        "operation_id": "QD3805-OP-0203",
        "display_title":
            "THCS Kim Đồng (Minh Sơn) + Lê Hồng Phong (Nhân Sơn)",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – TẠO/QUY VỀ TRƯỜNG TÊN MỚI",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Nguồn và đích chưa khóa duy nhất theo school_id/code; "
            "không tự động chọn giữa các trường cùng tên."
    },

    {
        "operation_id": "QD3805-OP-0210",
        "display_title":
            "THCS Trần Phú + THCS Thượng Sơn",
        "relation_type":
            "XỬ LÝ RIÊNG – PLAN BỊ LẪN DÒNG ĐẶC THÙ",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "QĐ3805 của OP-0210 chỉ gồm Trần Phú + Thượng Sơn. "
            "THCS Văn Hiến là dòng orphan riêng về tiếp nhận điểm; "
            "không cho plan bị lẫn orphan chạy tự động."
    },

    {
        "operation_id": "QD3805-OP-0399",
        "display_title":
            "THCS Quang Phong + THCS Cắm Muộn -> THCS Mường Quàng",
        "relation_type":
            "XỬ LÝ RIÊNG – ĐÍCH TÊN MỚI",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "QĐ3805 xác định tên đích THCS Mường Quàng nhưng "
            "chưa khóa school_id đích trong database."
    },

    {
        "operation_id": "QD3805-OP-0424",
        "display_title":
            "THCS Tiến Thắng + PTDTBT THCS Bính Thuận -> THCS Châu Tiến",
        "relation_type":
            "XỬ LÝ RIÊNG – ĐÍCH TÊN MỚI",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Tên trường đích THCS Châu Tiến chưa khóa duy nhất theo school_id."
    },

    {
        "operation_id": "QD3805-OP-0434",
        "display_title":
            "PTDTBT THCS Hội Nga + THCS Hạnh Thiết -> THCS Quỳ Châu",
        "relation_type":
            "XỬ LÝ RIÊNG – ĐÍCH TÊN MỚI",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Tên trường đích THCS Quỳ Châu chưa khóa duy nhất theo school_id."
    },

    {
        "operation_id": "QD3805-OP-0451",
        "display_title":
            "THCS Châu Thái + THCS Châu Cường -> THCS Mường Ham",
        "relation_type":
            "XỬ LÝ RIÊNG – ĐÍCH TÊN MỚI",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Tên trường đích THCS Mường Ham chưa khóa duy nhất theo school_id."
    },

    {
        "operation_id": "QD3805-OP-0486",
        "display_title":
            "THCS Quỳnh Hậu tiếp nhận điểm Quỳnh Bá",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – TIẾP NHẬN ĐIỂM",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Chỉ tiếp nhận điểm trường Quỳnh Bá của THCS Bá-Ngọc."
    },

    {
        "operation_id": "QD3805-OP-0489",
        "display_title":
            "Giải thể THCS Bá-Ngọc – tách hai điểm",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – GIẢI THỂ/TÁCH ĐIỂM",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Một trường nguồn được giải thể và chia hai điểm về hai đích; "
            "không thể dùng engine một nguồn -> một đích."
    },

    {
        "operation_id": "QD3805-OP-0490",
        "display_title":
            "THCS Quỳnh Hưng tiếp nhận điểm Quỳnh Ngọc",
        "relation_type":
            "ĐẶC THÙ CÙNG CẤP – TIẾP NHẬN ĐIỂM",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Chỉ tiếp nhận điểm trường Quỳnh Ngọc của THCS Bá-Ngọc."
    },

    {
        "operation_id": "QD3805-OP-0644",
        "display_title":
            "PTDTBT THCS Yên Thắng + PT DTBT Yên Hòa",
        "relation_type":
            "XỬ LÝ RIÊNG – CẦN KHÓA ALIAS NGUỒN",
        "status":
            "CHỜ XỬ LÝ RIÊNG – KHÔNG CHẠY BATCH THUẦN",
        "reason":
            "Tên PT DTBT Yên Hòa trong QĐ3805 chưa được khóa chắc "
            "vào school_id nguồn; không dùng fuzzy-match để ghi DB."
    },
]


EXPECTED_BLOCK_IDS = {
    x["operation_id"]
    for x in RULES
}


if len(RULES) != 19:
    raise RuntimeError(
        "RULES phai dung 19."
    )

if len(EXPECTED_BLOCK_IDS) != 19:
    raise RuntimeError(
        "Operation ID bi trung."
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def fresh_state():
    code = r'''
import json

from app.services import (
    school_merger_level_batch_service
    as svc
)

ctx = svc._registry_level_context(
    "THCS"
)

rows, counts, candidates, meta = svc._state_rows(
    2,
    "THCS",
)

preview = svc.build_level_batch_preview(
    school_year_id=2,
    level_code="THCS",
)

out = {
    "summary":
        svc.registry_level_summary("THCS"),

    "counts":
        counts,

    "candidate_count":
        preview.get("candidate_count"),

    "effective_block_count":
        preview.get("effective_block_count"),

    "ready_for_execution":
        preview.get("ready_for_execution"),

    "registry_unresolved_count":
        preview.get("registry_unresolved_count"),

    "registry_deferred_unresolved_count":
        preview.get(
            "registry_deferred_unresolved_count"
        ),

    "block_ops": sorted(
        str(x.get("qd3805_operation_id") or "")
        for x in rows
        if str(
            x.get("batch_state") or ""
        ).upper() == "BLOCK"
    ),

    "ready_ops": sorted(
        str(x.get("qd3805_operation_id") or "")
        for x in rows
        if str(
            x.get("batch_state") or ""
        ).upper() == "READY"
    ),

    "done_precompleted": sorted(
        str(x.get("qd3805_operation_id") or "")
        for x in rows
        if str(
            x.get("batch_state") or ""
        ).upper() == "DONE"
        and str(
            x.get("qd3805_operation_id") or ""
        ) in {
            "QD3805-OP-0342",
            "QD3805-OP-0343",
        }
    ),

    "special_ops": sorted(
        str(x.get("operation_id") or "")
        for x in (
            ctx.get("special_ops")
            or []
        )
    ),

    "special_orphans":
        ctx.get("special_orphans")
        or [],
}

print(
    "JSON_RESULT="
    + json.dumps(
        out,
        ensure_ascii=False,
        default=str,
    )
)
'''

    env = dict(
        os.environ
    )

    env["PYTHONDONTWRITEBYTECODE"] = "1"

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)

        raise RuntimeError(
            "Fresh-process state FAIL."
        )

    for line in proc.stdout.splitlines():
        if line.startswith(
            "JSON_RESULT="
        ):
            return json.loads(
                line[len("JSON_RESULT="):]
            )

    raise RuntimeError(
        "Khong co JSON_RESULT."
    )


print("=" * 140)
print("THCS - TACH 19 BLOCK KHOI BATCH THUAN")
print("=" * 140)

print(
    "KHONG GHI DATABASE."
)

print(
    "KHONG DANH DAU 19 PHUONG AN LA DONE."
)

print(
    "19 PHUONG AN VAN DUOC GIU DE XU LY RIENG."
)


# ============================================================
# 1. FILE GATE
# ============================================================

print()
print("=" * 140)
print("1. HASH GATE")
print("=" * 140)


before = {
    "db":
        sha256(DB),

    "service":
        sha256(SERVICE),

    "lock":
        sha256(LOCK),

    "roster":
        sha256(ROSTER),

    "resolution":
        sha256(RESOLUTION),

    "history":
        sha256(HISTORY),
}


for key, value in before.items():

    print(
        f"{key:12s} = {value}"
    )

    if value != EXPECTED[key]:
        raise RuntimeError(
            "DUNG: "
            + key
            + " khong dung nen da khoa."
        )


for suffix in (
    "-wal",
    "-journal",
):

    path = Path(
        str(DB) + suffix
    )

    size = (
        path.stat().st_size
        if path.exists()
        else 0
    )

    print(
        path.name,
        "=",
        size,
    )

    if size > 0:
        raise RuntimeError(
            "DUNG: Uvicorn/server chua dung."
        )


# ============================================================
# 2. PRECHECK 19 BLOCK
# ============================================================

print()
print("=" * 140)
print("2. PRECHECK CURRENT STATE")
print("=" * 140)


state_before = fresh_state()


print(
    json.dumps(
        state_before,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)


counts_before = (
    state_before.get("counts")
    or {}
)


if counts_before != {
    "KEEP": 36,
    "DONE": 84,
    "READY": 13,
    "BLOCK": 19,
}:
    raise RuntimeError(
        "DUNG: current THCS counts khong dung "
        "36/84/13/19."
    )


current_block_ids = set(
    state_before.get(
        "block_ops"
    )
    or []
)


if current_block_ids != EXPECTED_BLOCK_IDS:

    print(
        "EXPECTED =",
        sorted(
            EXPECTED_BLOCK_IDS
        ),
    )

    print(
        "CURRENT  =",
        sorted(
            current_block_ids
        ),
    )

    print(
        "MISSING  =",
        sorted(
            EXPECTED_BLOCK_IDS
            - current_block_ids
        ),
    )

    print(
        "EXTRA    =",
        sorted(
            current_block_ids
            - EXPECTED_BLOCK_IDS
        ),
    )

    raise RuntimeError(
        "DUNG: tap 19 BLOCK khong khop tuyet doi."
    )


print()
print(
    "19 BLOCK EXACT MATCH = PASS"
)


# ============================================================
# 3. ĐỌC RESOLUTION HIỆN TẠI
# ============================================================

resolution_payload = json.loads(
    RESOLUTION.read_text(
        encoding="utf-8"
    )
)


if (
    resolution_payload.get(
        "schema"
    )
    != "QD3805_THCS_RESOLUTION_2026"
):
    raise RuntimeError(
        "Sai schema resolution THCS."
    )


if (
    resolution_payload.get(
        "level_code"
    )
    != "THCS"
):
    raise RuntimeError(
        "Sai level_code resolution."
    )


if len(
    resolution_payload.get(
        "precompleted"
    )
    or []
) != 2:
    raise RuntimeError(
        "Mat 2 precompleted Nghi Loc."
    )


deferred = (
    resolution_payload.get(
        "deferred_orphans"
    )
    or []
)


nghi_huong_ok = any(
    isinstance(x, dict)
    and int(
        x.get("stt")
        or 0
    ) == 110
    and str(
        x.get("school_code")
        or ""
    ) == "40413505"
    and bool(
        x.get("confirmed_keep")
    )
    for x in deferred
)


if not nghi_huong_ok:
    raise RuntimeError(
        "Mat quy tac GIU NGUYEN THCS Nghi Huong."
    )


if (
    resolution_payload.get(
        "special_same_level"
    )
    or []
):
    raise RuntimeError(
        "DUNG: special_same_level khong con rong; "
        "khong ghi de tu dong."
    )


# ============================================================
# 4. BACKUP
# ============================================================

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)


BACKUP_DIR = (
    ROOT
    / "backups"
    / (
        "backup_truoc_tach_19_BLOCK_THCS_"
        + stamp
    )
)


BACKUP_DIR.mkdir(
    parents=True,
    exist_ok=False,
)


SERVICE_BACKUP = (
    BACKUP_DIR
    / "school_merger_level_batch_service.py"
)


RESOLUTION_BACKUP = (
    BACKUP_DIR
    / "qd3805_thcs_resolution.json"
)


shutil.copy2(
    SERVICE,
    SERVICE_BACKUP,
)


shutil.copy2(
    RESOLUTION,
    RESOLUTION_BACKUP,
)


print()
print("=" * 140)
print("3. BACKUP")
print("=" * 140)

print(
    "BACKUP DIR =",
    BACKUP_DIR,
)


# ============================================================
# 5. UPDATE RESOLUTION IN MEMORY
# ============================================================

resolution_payload[
    "special_same_level"
] = RULES


# ============================================================
# 6. PATCH SERVICE
# ============================================================

original = SERVICE.read_text(
    encoding="utf-8"
)


if (
    "_qd3805_resolution_special_by_id"
    in original
):
    raise RuntimeError(
        "DUNG: patch 19 BLOCK da co trong service."
    )


tree = ast.parse(
    original,
    filename=str(SERVICE),
)


registry_functions = [
    node
    for node in tree.body
    if isinstance(
        node,
        ast.FunctionDef,
    )
    and node.name
    == "_registry_level_context"
]


if len(
    registry_functions
) != 1:
    raise RuntimeError(
        "Khong tim thay dung "
        "_registry_level_context."
    )


registry_func = (
    registry_functions[0]
)


rename_nodes = []


for node in registry_func.body:

    if not isinstance(
        node,
        ast.Assign,
    ):
        continue

    for target in node.targets:

        if (
            isinstance(
                target,
                ast.Name,
            )
            and target.id
            == "rename_ids"
        ):
            rename_nodes.append(
                node
            )


if len(rename_nodes) != 1:

    raise RuntimeError(
        "Khong tim thay dung "
        "1 assignment rename_ids."
    )


rename_node = (
    rename_nodes[0]
)


INSERT = r'''
    # QD3805 THCS:
    # Các operation được resolution xác nhận phải xử lý riêng
    # không được đưa vào batch sáp nhập toàn trường.
    # Chỉ đổi phân loại trong preview/batch;
    # KHÔNG đánh dấu DONE và KHÔNG ghi database.
    _qd3805_resolution_special_rules = [
        dict(x)
        for x in (
            resolution.get(
                "special_same_level"
            )
            or []
        )
        if isinstance(
            x,
            dict,
        )
    ]

    _qd3805_resolution_special_by_id = {
        str(
            x.get(
                "operation_id"
            )
            or ""
        ):
        x
        for x in _qd3805_resolution_special_rules
        if str(
            x.get(
                "operation_id"
            )
            or ""
        )
    }

    for _qd3805_op in operations:

        _qd3805_op_id = str(
            _qd3805_op.get(
                "operation_id"
            )
            or ""
        )

        _qd3805_rule = (
            _qd3805_resolution_special_by_id.get(
                _qd3805_op_id
            )
        )

        if not _qd3805_rule:
            continue

        _qd3805_op[
            "batch"
        ] = "LIÊN CẤP/ĐẶC THÙ"

        _qd3805_op[
            "relation_type"
        ] = str(
            _qd3805_rule.get(
                "relation_type"
            )
            or "XỬ LÝ RIÊNG"
        )

        _qd3805_op[
            "official_plan"
        ] = str(
            _qd3805_rule.get(
                "display_title"
            )
            or _qd3805_op.get(
                "official_plan"
            )
            or ""
        )

        _qd3805_op[
            "resolution_note"
        ] = str(
            _qd3805_rule.get(
                "reason"
            )
            or ""
        )

        _qd3805_op[
            "resolution_status"
        ] = str(
            _qd3805_rule.get(
                "status"
            )
            or (
                "CHỜ XỬ LÝ RIÊNG – "
                "KHÔNG CHẠY BATCH THUẦN"
            )
        )

'''


lines = original.splitlines(
    keepends=True
)


insert_at = (
    rename_node.end_lineno
)


lines[
    insert_at:insert_at
] = [
    INSERT
]


patched = "".join(
    lines
)


# ============================================================
# 7. STATIC VALIDATION
# ============================================================

print()
print("=" * 140)
print("4. STATIC VALIDATION")
print("=" * 140)


ast.parse(
    patched,
    filename=str(SERVICE),
)


compile(
    patched,
    str(SERVICE),
    "exec",
)


if (
    "_qd3805_resolution_special_by_id"
    not in patched
):
    raise RuntimeError(
        "Patch source FAIL."
    )


print(
    "AST     = PASS"
)

print(
    "COMPILE = PASS"
)


# ============================================================
# 8. WRITE ATOMIC
# ============================================================

service_tmp = (
    SERVICE.with_suffix(
        ".py.thcs19.tmp"
    )
)


resolution_tmp = (
    RESOLUTION.with_suffix(
        ".json.thcs19.tmp"
    )
)


try:

    service_tmp.write_text(
        patched,
        encoding="utf-8",
    )


    resolution_tmp.write_text(
        json.dumps(
            resolution_payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


    # Đọc lại JSON tạm.
    test_resolution = json.loads(
        resolution_tmp.read_text(
            encoding="utf-8"
        )
    )


    test_rules = (
        test_resolution.get(
            "special_same_level"
        )
        or []
    )


    test_ids = {
        str(
            x.get(
                "operation_id"
            )
            or ""
        )
        for x in test_rules
        if isinstance(
            x,
            dict,
        )
    }


    if test_ids != EXPECTED_BLOCK_IDS:
        raise RuntimeError(
            "Resolution 19 rules FAIL."
        )


    os.replace(
        service_tmp,
        SERVICE,
    )


    os.replace(
        resolution_tmp,
        RESOLUTION,
    )


    # ========================================================
    # 9. FRESH VALIDATE
    # ========================================================

    print()
    print("=" * 140)
    print("5. VALIDATE SAU CAI")
    print("=" * 140)


    state_after = fresh_state()


    print(
        json.dumps(
            state_after,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


    counts_after = (
        state_after.get(
            "counts"
        )
        or {}
    )


    if counts_after != {
        "KEEP": 36,
        "DONE": 84,
        "READY": 13,
        "BLOCK": 0,
    }:

        raise RuntimeError(
            "DUNG: counts sau tach 19 "
            "khong bang 36/84/13/0."
        )


    if int(
        state_after.get(
            "candidate_count"
        )
        or 0
    ) != 13:

        raise RuntimeError(
            "DUNG: candidate_count "
            "khong bang 13."
        )


    if int(
        state_after.get(
            "effective_block_count"
        )
        or 0
    ) != 0:

        raise RuntimeError(
            "DUNG: van con effective blocker."
        )


    if (
        state_after.get(
            "ready_for_execution"
        )
        is not True
    ):

        raise RuntimeError(
            "DUNG: THCS chua ready_for_execution."
        )


    if (
        state_after.get(
            "block_ops"
        )
        or []
    ):

        raise RuntimeError(
            "DUNG: van con BLOCK operation."
        )


    special_ids_after = set(
        state_after.get(
            "special_ops"
        )
        or []
    )


    if not EXPECTED_BLOCK_IDS.issubset(
        special_ids_after
    ):

        print(
            "CHUA VAO SPECIAL =",
            sorted(
                EXPECTED_BLOCK_IDS
                - special_ids_after
            ),
        )

        raise RuntimeError(
            "DUNG: co operation bi mat "
            "thay vi chuyen sang XU LY RIENG."
        )


    if (
        state_after.get(
            "done_precompleted"
        )
        != [
            "QD3805-OP-0342",
            "QD3805-OP-0343",
        ]
    ):

        raise RuntimeError(
            "DUNG: 2 Nghi Loc "
            "khong con khoa DONE."
        )


    summary = (
        state_after.get(
            "summary"
        )
        or {}
    )


    if int(
        summary.get(
            "action_count"
        )
        or 0
    ) != 97:

        raise RuntimeError(
            "DUNG: action_count "
            "khong bang 97."
        )


    if int(
        summary.get(
            "keep_count"
        )
        or 0
    ) != 36:

        raise RuntimeError(
            "DUNG: keep_count thay doi."
        )


    # 89 special trước bước này + 19 xử lý riêng.
    if int(
        summary.get(
            "special_count"
        )
        or 0
    ) != 108:

        raise RuntimeError(
            "DUNG: special_count "
            "khong bang 108."
        )


    # Nghi Hương phải còn nguyên.
    special_orphans = (
        state_after.get(
            "special_orphans"
        )
        or []
    )


    nghi_huong_after = any(
        isinstance(
            x,
            dict,
        )
        and int(
            x.get(
                "stt"
            )
            or 0
        ) == 110
        and str(
            x.get(
                "school_code"
            )
            or ""
        ) == "40413505"
        and str(
            x.get(
                "status"
            )
            or ""
        ).startswith(
            "GIỮ NGUYÊN"
        )
        for x in special_orphans
    )


    if not nghi_huong_after:

        raise RuntimeError(
            "DUNG: mat trang thai "
            "GIU NGUYEN Nghi Huong."
        )


    # ========================================================
    # 10. FILE SAFETY
    # ========================================================

    print()
    print("=" * 140)
    print("6. FILE SAFETY")
    print("=" * 140)


    after = {
        "db":
            sha256(DB),

        "lock":
            sha256(LOCK),

        "roster":
            sha256(ROSTER),

        "history":
            sha256(HISTORY),
    }


    for key in (
        "db",
        "lock",
        "roster",
        "history",
    ):

        print(
            key,
            ":",
            before[key],
            "->",
            after[key],
        )

        if after[key] != before[key]:

            raise RuntimeError(
                "DUNG: "
                + key
                + " bi thay doi."
            )


    print(
        "SERVICE NEW SHA    =",
        sha256(SERVICE),
    )


    print(
        "RESOLUTION NEW SHA =",
        sha256(RESOLUTION),
    )


    print(
        "BACKUP DIR         =",
        BACKUP_DIR,
    )


except Exception:

    print()
    print("=" * 140)
    print("LOI - TU KHOI PHUC")
    print("=" * 140)


    shutil.copy2(
        SERVICE_BACKUP,
        SERVICE,
    )


    shutil.copy2(
        RESOLUTION_BACKUP,
        RESOLUTION,
    )


    if service_tmp.exists():
        service_tmp.unlink()


    if resolution_tmp.exists():
        resolution_tmp.unlink()


    print(
        "SERVICE RESTORED =",
        sha256(SERVICE),
    )


    print(
        "RESOLUTION RESTORED =",
        sha256(RESOLUTION),
    )


    print(
        "DATABASE = KHONG TAC DONG"
    )

    raise


finally:

    if service_tmp.exists():
        service_tmp.unlink()

    if resolution_tmp.exists():
        resolution_tmp.unlink()


print()
print("=" * 140)
print("TACH 19 BLOCK THCS: THANH CONG")
print("=" * 140)

print(
    "KEEP              = 36"
)

print(
    "DONE              = 84"
)

print(
    "READY             = 13"
)

print(
    "BLOCK             = 0"
)

print(
    "XU LY RIENG       = 19"
)

print(
    "CANDIDATE         = 13"
)

print(
    "READY_FOR_DRY_RUN = YES"
)

print(
    "DATABASE          = KHONG THAY DOI"
)

print(
    "SAP NHAP THCS     = CHUA CHAY"
)

print()
print(
    "13 READY OPS ="
)

for op in (
    state_after.get(
        "ready_ops"
    )
    or []
):
    print(
        " -",
        op,
    )


print("=" * 140)
