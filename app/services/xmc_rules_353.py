"""Rules for the new appendices only: ND 353/2026, Articles 21, 23–25.

Legacy grade_3/5 indicators remain usable under the data transition provision;
new stage/primary completion evidence also qualifies. No legacy rows are changed.
"""
from datetime import date

EFFECTIVE_DATE = date(2026, 11, 1)
LEGAL_BASIS = "Nghị định 353/2026/NĐ-CP, Điều 21, 23–25 (hiệu lực 01/11/2026)"


def personal_levels(record, evidence):
    g1 = getattr(record, "completed_grade_3", None)
    g2 = getattr(record, "completed_grade_5", None)
    g1 = g1 if isinstance(g1, bool) else None
    g2 = g2 if isinstance(g2, bool) else None
    primary = getattr(record, "completed_primary_program", None)
    if evidence.get("completed_stage2") is True or primary is True:
        g1 = g2 = True
    elif evidence.get("completed_stage1") is True:
        g1 = True
    if evidence.get("relapsed") is True:
        return False, False, False
    conflict = (g2 is True and g1 is False) or (
        evidence.get("illiterate") is True and (g1 is True or g2 is True))
    if conflict:
        return None, None, True
    if g2 is True:
        g1 = True
    if evidence.get("illiterate") is True:
        g1 = g2 = False
    return g1, g2, False


def commune_level(items, special):
    if special is None or any(x["age"] is None for x in items):
        return "Chưa đủ dữ liệu"
    upper = 35 if special else 60
    group = [x for x in items if 15 <= x["age"] <= upper]
    if not group:
        return "Chưa đủ dữ liệu"
    # Compare integer counts before display rounding (89.995% is below 90%).
    outcomes = {}
    for level in (1, 2):
        values = [x[f"g{level}"] for x in group]
        outcomes[level] = None if None in values else sum(v is True for v in values) * 100 >= 90 * len(group)
    if outcomes[2] is True:
        return 2
    if outcomes[1] is True:
        return 1
    if outcomes[1] is None or outcomes[2] is None:
        return "Chưa đủ dữ liệu"
    return "Chưa đạt"
