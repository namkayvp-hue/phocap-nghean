from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
DB = PROJECT / "data" / "phocap.db"
TARGET_YEAR = "2026-2027"
TARGET_COMMUNE_CODE = "17827"
TARGET_COMMUNE_TEXT = "NGHI LỘC"


def qi(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def cols(con, table: str) -> set[str]:
    return {
        str(r[1])
        for r in con.execute(
            f"PRAGMA table_info({qi(table)})"
        ).fetchall()
    }


def table_exists(con, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def pick(row, name, default=""):
    try:
        return row[name]
    except Exception:
        return default


def main() -> int:
    print('=' * 108)
    print('KIỂM TRA ĐỢT 2026-2027 CỦA XÃ NGHI LỘC - BÀI 13B-11 V1')
    print('CHỈ ĐỌC - KHÔNG INSERT / UPDATE / DELETE')
    print('=' * 108)

    if not DB.exists():
        print('Không tìm thấy database:', DB)
        return 1

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    try:
        con.execute('PRAGMA query_only=ON')

        print('\n1. NĂM HỌC')
        print('-' * 108)
        year = con.execute(
            "SELECT * FROM school_years WHERE code=? LIMIT 1",
            (TARGET_YEAR,),
        ).fetchone()

        if year is None:
            print('KHÔNG tìm thấy năm học', TARGET_YEAR)
            return 0

        year_id = int(year['id'])
        print(f"{TARGET_YEAR}: id={year_id}")

        print('\n2. XÃ/PHƯỜNG CÓ MÃ 17827 HOẶC TÊN NGHI LỘC')
        print('-' * 108)
        commune_columns = cols(con, 'communes')
        active_expr = 'is_active' if 'is_active' in commune_columns else '1 AS is_active'
        rows = con.execute(
            f"""
            SELECT id, code, name, {active_expr}
            FROM communes
            WHERE code = ?
               OR UPPER(name) LIKE '%NGHI L%'
            ORDER BY id
            """,
            (TARGET_COMMUNE_CODE,),
        ).fetchall()

        if not rows:
            print('KHÔNG tìm thấy xã Nghi Lộc / mã 17827.')
            return 0

        commune_ids = []
        for r in rows:
            cid = int(r['id'])
            commune_ids.append(cid)
            print(
                f"id={cid} | code={r['code']} | name={r['name']} | "
                f"is_active={r['is_active']}"
            )

        print('\n3. ĐỢT ĐIỀU TRA 2026-2027 GẮN VỚI CÁC BẢN GHI NÀY')
        print('-' * 108)
        marks = ','.join('?' for _ in commune_ids)
        batches = con.execute(
            f"""
            SELECT id, code, name, school_year_id, commune_id, status
            FROM survey_batches
            WHERE school_year_id = ?
              AND commune_id IN ({marks})
            ORDER BY commune_id, id
            """,
            (year_id, *commune_ids),
        ).fetchall()

        if not batches:
            print('KHÔNG có SurveyBatch 2026-2027 cho các commune_id trên.')
        else:
            for b in batches:
                print(
                    f"batch_id={b['id']} | code={b['code']} | "
                    f"commune_id={b['commune_id']} | status={b['status']} | "
                    f"name={b['name']}"
                )

        print('\n4. TÀI KHOẢN GẮN VỚI CÁC commune_id CỦA NGHI LỘC')
        print('-' * 108)
        if not table_exists(con, 'users'):
            print('Không có bảng users.')
        else:
            ucols = cols(con, 'users')
            select_cols = [c for c in (
                'id', 'username', 'full_name', 'role_id',
                'role_code', 'commune_id', 'school_id', 'is_active'
            ) if c in ucols]

            if 'commune_id' not in ucols:
                print('Bảng users không có cột commune_id.')
            else:
                user_rows = con.execute(
                    f"""
                    SELECT {', '.join(qi(c) for c in select_cols)}
                    FROM users
                    WHERE commune_id IN ({marks})
                    ORDER BY commune_id, id
                    """,
                    tuple(commune_ids),
                ).fetchall()

                if not user_rows:
                    print('Không có tài khoản nào gắn với các commune_id trên.')
                else:
                    for u in user_rows:
                        parts = []
                        for c in select_cols:
                            parts.append(f"{c}={u[c]}")
                        print(' | '.join(parts))

        print('\n5. KIỂM TRA TRỰC TIẾP commune_id=114 (THEO URL ẢNH CẤP XÃ)')
        print('-' * 108)
        c114 = con.execute(
            "SELECT id, code, name, is_active FROM communes WHERE id=114 LIMIT 1"
        ).fetchone()
        if c114:
            print(
                f"commune id=114 -> code={c114['code']} | "
                f"name={c114['name']} | is_active={c114['is_active']}"
            )
        else:
            print('Không có communes.id=114')

        b114 = con.execute(
            """
            SELECT id, code, name, school_year_id, commune_id, status
            FROM survey_batches
            WHERE school_year_id=? AND commune_id=114
            ORDER BY id
            """,
            (year_id,),
        ).fetchall()

        if b114:
            for b in b114:
                print(
                    f"BATCH commune_id=114 -> id={b['id']} | "
                    f"code={b['code']} | status={b['status']}"
                )
        else:
            print('KHÔNG có batch 2026-2027 với commune_id=114.')

        print('\n6. ĐỐI CHIẾU 130 ĐỢT TOÀN TỈNH')
        print('-' * 108)
        batch_total = con.execute(
            "SELECT COUNT(*) FROM survey_batches WHERE school_year_id=?",
            (year_id,),
        ).fetchone()[0]
        active_total = con.execute(
            "SELECT COUNT(*) FROM communes WHERE is_active=1"
        ).fetchone()[0]
        missing = con.execute(
            """
            SELECT c.id, c.code, c.name
            FROM communes c
            WHERE c.is_active=1
              AND NOT EXISTS (
                  SELECT 1
                  FROM survey_batches sb
                  WHERE sb.school_year_id=?
                    AND sb.commune_id=c.id
              )
            ORDER BY c.id
            """,
            (year_id,),
        ).fetchall()

        print('Xã/phường active :', active_total)
        print('SurveyBatch năm   :', batch_total)
        print('Active chưa có đợt:', len(missing))
        for r in missing[:20]:
            print(f" - id={r['id']} | {r['code']} | {r['name']}")

        print('\n7. KẾT LUẬN TỰ ĐỘNG')
        print('-' * 108)
        batch_ids_for_communes = {int(b['commune_id']) for b in batches}

        if 114 in batch_ids_for_communes:
            print('DATABASE CÓ đợt 2026-2027 cho commune_id=114.')
            print('=> Nếu tài khoản xã vẫn thấy 0, lỗi nằm ở lớp scope/auth/filter đang chạy, không phải dữ liệu khởi tạo.')
        else:
            print('DATABASE KHÔNG có đợt 2026-2027 cho commune_id=114.')
            print('=> Nếu tài khoản Xã Nghi Lộc đang dùng commune_id=114 thì liên kết xã/tài khoản hoặc dữ liệu tạo đợt đang lệch ID.')

        print('\nHãy copy toàn bộ kết quả này gửi lại ChatGPT.')
        print('Script mở database mode=ro và không có lệnh ghi dữ liệu.')

    finally:
        con.close()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
