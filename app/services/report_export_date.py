"""Date of report generation in Vietnam, independent of server timezone."""
import re
from datetime import datetime, timedelta, timezone


def export_date():
    return datetime.now(timezone(timedelta(hours=7))).date()


def date_line(day):
    return f"ngày {day.day:02d} tháng {day.month:02d} năm {day.year}"


def stamp_date_text(value, day):
    if not isinstance(value, str):
        return value
    # Only report datelines, not legislation, birth dates, meeting dates or periods.
    if re.fullmatch(r'[\s.…,]*ngày\s*[.\s…\d]*tháng\s*[.\s…\d]*năm\s*[.\s…\d]*', value, re.I):
        start = re.search('ngày', value, re.I).start()
        return value[:start] + date_line(day)
    return value


def stamp_workbook(wb, day=None):
    day = day or export_date()
    for ws in wb:
        # Original administrative and survey pages contain legal/certification dates.
        if ws.title in {'Trang_01','Trang_02','Trang_03','Trang_14'}:
            continue
        for row in ws:
            for cell in row:
                value = cell.value
                if isinstance(value, str) and value.startswith(('Thời điểm:', 'Thời điểm xuất:')):
                    cell.value = 'Thời điểm xuất: ' + day.strftime('%d/%m/%Y')
                elif isinstance(value, str):
                    replacement = stamp_date_text(value, day)
                    if replacement != value:
                        cell.value = replacement
        # The PDF splits this dateline across two separate cells.
        if ws.title == 'Trang_05':
            ws['M9'] = f'…………., ngày {day.day:02d} tháng {day.month:02d}'
            ws['N10'] = f'năm {day.year}'
    return wb
