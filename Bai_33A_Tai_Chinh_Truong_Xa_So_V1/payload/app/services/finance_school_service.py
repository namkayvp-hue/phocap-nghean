from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import School
from app.report_input_catalog import FINANCE_ITEMS
from app.report_input_models import SchoolFinanceReportValue


AVERAGE_ITEM_CODES = frozenset({"F03"})
WEIGHTED_PERCENT_ITEM_CODES = frozenset({"F02"})


@dataclass(frozen=True)
class FinanceDisplayValue:
    amount: Decimal | None
    note: str | None = None


def _norm(value: Any) -> str:
    import unicodedata

    text = " ".join(str(value or "").strip().upper().split())
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def is_preschool_school(school: School) -> bool:
    text = _norm(f"{getattr(school, 'name', '')} {getattr(school, 'code', '')}")
    words = set(text.split())
    return (
        "MAM NON" in text
        or "MAU GIAO" in text
        or "NHA TRE" in text
        or "NHOM TRE" in text
        or "LOP MAM NON" in text
        or "GDMN" in words
        or "MN" in words
    )


def finance_school_ids_for_scope(
    db: Session,
    *,
    commune_id: int | None = None,
    school_id: int | None = None,
    explicit_school_ids: Iterable[int] | None = None,
) -> list[int]:
    if explicit_school_ids is not None:
        requested = sorted({int(x) for x in explicit_school_ids if int(x) > 0})
        if not requested:
            return []
        schools = list(
            db.scalars(
                select(School).where(
                    School.id.in_(requested),
                    School.is_active.is_(True),
                )
            ).all()
        )
        return sorted(int(s.id) for s in schools if is_preschool_school(s))

    if school_id is not None:
        school = db.get(School, int(school_id))
        if school is None or not school.is_active:
            return []
        return [int(school.id)] if is_preschool_school(school) else []

    stmt = select(School).where(School.is_active.is_(True))
    if commune_id is not None:
        stmt = stmt.where(School.commune_id == int(commune_id))
    schools = list(db.scalars(stmt.order_by(School.name.asc(), School.id.asc())).all())
    return [int(s.id) for s in schools if is_preschool_school(s)]


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _average(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def load_finance_values(
    db: Session,
    *,
    report_year: int,
    commune_id: int | None = None,
    school_id: int | None = None,
    explicit_school_ids: Iterable[int] | None = None,
) -> tuple[dict[str, FinanceDisplayValue], int, int]:
    school_ids = finance_school_ids_for_scope(
        db,
        commune_id=commune_id,
        school_id=school_id,
        explicit_school_ids=explicit_school_ids,
    )
    total_school_count = len(school_ids)
    if not school_ids:
        return {}, total_school_count, 0

    rows = list(
        db.scalars(
            select(SchoolFinanceReportValue).where(
                SchoolFinanceReportValue.school_id.in_(school_ids),
                SchoolFinanceReportValue.report_year == int(report_year),
            )
        ).all()
    )
    data_school_count = len({int(row.school_id) for row in rows})

    if school_id is not None and len(school_ids) == 1:
        return (
            {
                row.item_code: FinanceDisplayValue(
                    amount=_decimal(row.amount),
                    note=row.note,
                )
                for row in rows
            },
            total_school_count,
            data_school_count,
        )

    by_school: dict[int, dict[str, Decimal]] = {}
    for row in rows:
        amount = _decimal(row.amount)
        if amount is None:
            continue
        by_school.setdefault(int(row.school_id), {})[row.item_code] = amount

    result: dict[str, FinanceDisplayValue] = {}
    for item in FINANCE_ITEMS:
        code = item["code"]
        values = [items[code] for items in by_school.values() if code in items]
        amount: Decimal | None

        if code in WEIGHTED_PERCENT_ITEM_CODES:
            weighted_num = Decimal("0")
            weighted_den = Decimal("0")
            for items in by_school.values():
                ratio = items.get(code)
                weight = items.get("F01_1")
                if ratio is not None and weight is not None and weight > 0:
                    weighted_num += ratio * weight
                    weighted_den += weight
            amount = (
                weighted_num / weighted_den
                if weighted_den > 0
                else _average(values)
            )
        elif code in AVERAGE_ITEM_CODES:
            amount = _average(values)
        else:
            amount = sum(values, Decimal("0")) if values else None

        if amount is not None:
            result[code] = FinanceDisplayValue(
                amount=amount,
                note=f"Tổng hợp từ {data_school_count}/{total_school_count} trường có dữ liệu",
            )

    return result, total_school_count, data_school_count


def fill_finance_worksheet(
    db: Session,
    ws: Any,
    *,
    start_year: int,
    commune_id: int | None = None,
    school_id: int | None = None,
    explicit_school_ids: Iterable[int] | None = None,
) -> dict[str, Any]:
    # Chỉ xóa vùng số liệu, giữ nguyên khung mẫu, merge, font, border và vùng in.
    for row in range(10, 40):
        for col in range(4, 10):
            ws.cell(row, col).value = None

    years = list(range(int(start_year), int(start_year) + 5))
    for offset, year in enumerate(years, start=5):
        ws.cell(8, offset).value = year

    values_by_year: dict[int, dict[str, FinanceDisplayValue]] = {}
    total_school_count = 0
    data_school_ids: set[int] = set()

    # Tải school ids một lần để scope ổn định giữa 5 năm.
    scoped_school_ids = finance_school_ids_for_scope(
        db,
        commune_id=commune_id,
        school_id=school_id,
        explicit_school_ids=explicit_school_ids,
    )
    total_school_count = len(scoped_school_ids)

    for year in years:
        values, _total, data_count = load_finance_values(
            db,
            report_year=year,
            school_id=school_id if school_id is not None else None,
            explicit_school_ids=scoped_school_ids,
        )
        values_by_year[year] = values
        if data_count:
            # chỉ dùng để trạng thái; số trường có dữ liệu chi tiết được tính dưới đây
            pass

    if scoped_school_ids:
        rows = list(
            db.scalars(
                select(SchoolFinanceReportValue).where(
                    SchoolFinanceReportValue.school_id.in_(scoped_school_ids),
                    SchoolFinanceReportValue.report_year.in_(years),
                )
            ).all()
        )
        data_school_ids = {int(row.school_id) for row in rows}

    any_data = False
    for item in FINANCE_ITEMS:
        code = item["code"]
        template_row = int(item["template_row"])
        yearly_amounts: list[Decimal] = []
        for col, year in enumerate(years, start=5):
            value = values_by_year.get(year, {}).get(code)
            amount = _decimal(value.amount) if value is not None else None
            if amount is not None:
                any_data = True
                yearly_amounts.append(amount)
                ws.cell(template_row, col).value = float(amount)
        if yearly_amounts:
            if code in WEIGHTED_PERCENT_ITEM_CODES or code in AVERAGE_ITEM_CODES:
                total = _average(yearly_amounts)
            else:
                total = sum(yearly_amounts, Decimal("0"))
            if total is not None:
                ws.cell(template_row, 4).value = float(total)

    if not any_data:
        ws["D10"] = (
            "CHƯA NHẬP DỮ LIỆU TÀI CHÍNH "
            f"CHO GIAI ĐOẠN {years[0]}-{years[-1]}"
        )

    return {
        "years": years,
        "total_school_count": total_school_count,
        "data_school_count": len(data_school_ids),
        "has_data": any_data,
    }
