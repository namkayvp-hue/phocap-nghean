from __future__ import annotations

import hashlib
import py_compile
import shutil
import sys
from datetime import datetime
from pathlib import Path

EXPECTED_BEFORE = {
    "app/routers/student_reconciliation_source.py": "2f08c1bcb11547508dd96f78b9e93ac00bae8114d9e0d30b489c6e01dc82194c",
}
EXPECTED_AFTER = {
    "app/routers/student_reconciliation_source.py": "384339cae03a207b7019eeaa315683135489385745a4de0c03c0d3497cd21ede",
    "app/services/school_name_history.py": "ca1a61ef4da4b9ef7e2ea70d4f6ff212112a5d00bd1943ae74e625d87734349d",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    package_dir = Path(__file__).resolve().parent
    project_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(r"C:\PhoCap")
    payload_dir = package_dir / "payload"

    route_rel = Path("app/routers/student_reconciliation_source.py")
    helper_rel = Path("app/services/school_name_history.py")
    route = project_dir / route_rel
    helper = project_dir / helper_rel

    print("=" * 100)
    print("BAI 32B - INSTALL HISTORICAL SCHOOL NAME RESOLVER")
    print("SOURCE ONLY - NO DATABASE WRITE")
    print("=" * 100)
    print(f"PROJECT = {project_dir}")

    if not route.exists():
        print("STOP: source file not found:", route)
        return 2

    before_sha = sha256(route)
    print("ROUTE_SHA_BEFORE =", before_sha)
    if before_sha != EXPECTED_BEFORE[str(route_rel).replace('\\', '/')]:
        print("STOP: current source SHA does not match the reviewed 32B source.")
        print("NO SOURCE WRITE. NO DATABASE WRITE.")
        return 3

    payload_route = payload_dir / route_rel
    payload_helper = payload_dir / helper_rel
    for p in (payload_route, payload_helper):
        if not p.exists():
            print("STOP: payload missing:", p)
            return 4

    if sha256(payload_route) != EXPECTED_AFTER[str(route_rel).replace('\\', '/')]:
        print("STOP: route payload SHA mismatch.")
        return 5
    if sha256(payload_helper) != EXPECTED_AFTER[str(helper_rel).replace('\\', '/')]:
        print("STOP: helper payload SHA mismatch.")
        return 6

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = project_dir / "backups" / f"source_32b_{stamp}"
    backup_route = backup_root / route_rel
    backup_helper = backup_root / helper_rel
    backup_route.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(route, backup_route)
    helper_existed = helper.exists()
    if helper_existed:
        backup_helper.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(helper, backup_helper)

    print("BACKUP_DIR =", backup_root)

    try:
        route.parent.mkdir(parents=True, exist_ok=True)
        helper.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(payload_route, route)
        shutil.copy2(payload_helper, helper)

        py_compile.compile(str(route), doraise=True)
        py_compile.compile(str(helper), doraise=True)

        route_after = sha256(route)
        helper_after = sha256(helper)
        print("ROUTE_SHA_AFTER =", route_after)
        print("HELPER_SHA_AFTER =", helper_after)

        if route_after != EXPECTED_AFTER[str(route_rel).replace('\\', '/')]:
            raise RuntimeError("route SHA after install mismatch")
        if helper_after != EXPECTED_AFTER[str(helper_rel).replace('\\', '/')]:
            raise RuntimeError("helper SHA after install mismatch")

    except Exception as exc:
        print("INSTALL ERROR =", type(exc).__name__, str(exc))
        print("ROLLBACK SOURCE...")
        shutil.copy2(backup_route, route)
        if helper_existed:
            shutil.copy2(backup_helper, helper)
        elif helper.exists():
            helper.unlink()
        print("ROLLBACK_SOURCE = OK")
        print("DATABASE_WRITE = 0")
        return 7

    print("PY_COMPILE = OK")
    print("DATABASE_WRITE = 0")
    print("INSTALL32B_SUCCESS = YES")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
