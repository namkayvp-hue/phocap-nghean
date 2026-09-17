from __future__ import annotations

import ast
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import traceback
import zlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(r"C:\PhoCap")
VERSION = "PCGD-XMC-V1.5-MENU-BAO-CAO-4-NHOM"
PARTIAL_REL = Path("app/templates/partials/dropdown_menu_v1.html")
REPORT_ROUTER_REL = Path("app/routers/report_center.py")
MAIN_REL = Path("app/main.py")
DB_REL = Path("data/phocap.db")
ROUTERS_REL = Path("app/routers")
REPORT_TEMPLATE_ROOT_REL = Path("app/report_templates/pcgd_xmc_2025")
INCLUDE_MARKER = '{% include "partials/dropdown_menu_v1.html" %}'
EXCLUDED_TEMPLATES = {"auth/login.html", "surveys/field_print.html"}
REPORT_MARKER_START = "# === PCGD_XMC_REPORT_TYPES_V1_5_START ==="
REPORT_MARKER_END = "# === PCGD_XMC_REPORT_TYPES_V1_5_END ==="

MENU_TEMPLATE_B64 = (
    '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'
    'UyyUE3kil7RN2t8vx8mKS9V405Hf0vx/Uk1YFQ=='
)

REPORT_TYPES_BLOCK = '\n    # === PCGD_XMC_REPORT_TYPES_V1_5_START ===\n    "PCGD_TH_M1_2025": {\n        "title": "TH-M1 – Báo cáo phổ cập giáo dục Tiểu học",\n        "short_title": "Tiểu học – TH-M1",\n        "description": "Biểu TH-M1 năm 2025. Đã tiếp nhận mẫu Excel gốc; bước hiện tại chỉ đăng ký danh mục, chưa tự động điền dữ liệu.",\n        "icon": "📘",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_TH_02_2025": {\n        "title": "TH-02 – Thống kê kết quả PCGD Tiểu học",\n        "short_title": "Tiểu học – TH-02",\n        "description": "Biểu TH-02 năm 2025. Đã tiếp nhận mẫu Excel gốc; chưa thay đổi dữ liệu hoặc luồng nghiệp vụ hiện có.",\n        "icon": "📘",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_TH_01_GV_2025": {\n        "title": "TH-01-GV – Thống kê đội ngũ giáo viên Tiểu học",\n        "short_title": "Tiểu học – TH-01-GV",\n        "description": "Biểu đội ngũ giáo viên Tiểu học năm 2025. Mẫu gốc được lưu nguyên trạng để triển khai ánh xạ dữ liệu ở bước sau.",\n        "icon": "👩\u200d🏫",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_TH_01_CSVC_2025": {\n        "title": "TH-01-CSVC – Thống kê cơ sở vật chất Tiểu học",\n        "short_title": "Tiểu học – TH-01-CSVC",\n        "description": "Biểu cơ sở vật chất Tiểu học năm 2025. Mẫu gốc được lưu nguyên trạng để triển khai tự động điền ở bước sau.",\n        "icon": "🏫",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_THCS_M1_2025": {\n        "title": "THCS-M1 – Báo cáo phổ cập giáo dục THCS",\n        "short_title": "THCS – M1",\n        "description": "Biểu M1 THCS năm 2025. Đã tiếp nhận mẫu Excel gốc; chưa tự động điền dữ liệu.",\n        "icon": "📗",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_THCS_M2_2025": {\n        "title": "THCS-M2 – Tiêu chuẩn phổ cập giáo dục THCS",\n        "short_title": "THCS – M2",\n        "description": "Biểu M2 THCS năm 2025 về tiêu chuẩn PCGD THCS. Mẫu gốc được lưu nguyên trạng.",\n        "icon": "📗",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_THCS_TK_2025": {\n        "title": "THCS-TK – Thống kê kết quả PCGD THCS",\n        "short_title": "THCS – TK",\n        "description": "Biểu thống kê kết quả PCGD THCS năm 2025. Đã tiếp nhận mẫu Excel gốc.",\n        "icon": "📗",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_THCS_M5_2025": {\n        "title": "THCS-M5 – Thống kê đội ngũ giáo viên",\n        "short_title": "THCS – M5",\n        "description": "Biểu đội ngũ giáo viên THCS năm 2025. Mẫu gốc được lưu nguyên trạng.",\n        "icon": "👨\u200d🏫",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_THCS_CSVC_2025": {\n        "title": "THCS-CSVC – Thống kê cơ sở vật chất",\n        "short_title": "THCS – CSVC",\n        "description": "Biểu cơ sở vật chất THCS năm 2025. Mẫu gốc được lưu nguyên trạng.",\n        "icon": "🏫",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_XMC_3_2025": {\n        "title": "XMC-3 – Tổng hợp kết quả xóa mù chữ",\n        "short_title": "XMC – Biểu 3",\n        "description": "Biểu tổng hợp kết quả xóa mù chữ năm 2025. Đã tiếp nhận mẫu Excel gốc.",\n        "icon": "📙",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_CMC_2_2025": {\n        "title": "CMC-2 – Thống kê số người mù chữ",\n        "short_title": "XMC – CMC-2",\n        "description": "Biểu thống kê số người mù chữ năm 2025. Đã tiếp nhận mẫu Excel gốc.",\n        "icon": "📙",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_CMC_1_2025": {\n        "title": "CMC-1 – Tổng hợp chống mù chữ",\n        "short_title": "XMC – CMC-1",\n        "description": "Biểu tổng hợp chống mù chữ năm 2025. Đã tiếp nhận mẫu Excel gốc.",\n        "icon": "📙",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    "PCGD_XMC_4_2025": {\n        "title": "XMC-4 – Thống kê đạt chuẩn xóa mù chữ",\n        "short_title": "XMC – Biểu 4",\n        "description": "Biểu thống kê đạt chuẩn xóa mù chữ năm 2025. Đã tiếp nhận mẫu Excel gốc.",\n        "icon": "📙",\n        "stage": "Đã tiếp nhận mẫu gốc",\n        "stage_class": "next",\n        "lesson": "PCGD & XMC V1.5",\n    },\n    # === PCGD_XMC_REPORT_TYPES_V1_5_END ===\n'

TEMPLATE_FILES = [
    {
        "code": 'PCGD_TH_M1_2025',
        "level": 'TIEU_HOC',
        "title": 'TH-M1 – Phổ cập giáo dục Tiểu học',
        "source_name": '1. PCGD_2025_TH_M1_phường Thành Vinh.xls',
        "target_name": 'PCGD_2025_TH_M1.xls',
        "sha256": 'e5d1df46cb23f84fb8bc8dc7e7300a9e5f75b1a65ec1dfba6e7bbe5ba75a3252',
        "size": 46080,
        "payload_b64": (
            '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'
            'UZgsq3WoLKs0YF40JsMxy7yPzdELvptBYjbhK2Wifpw20DhRpzmhnzHqJtCqJZpMboKhKosQV4Dut/D/B/hflE3ICDjEPID/f8H/khxCRsHBsk'
            'jrDx/xZDNucumr2v7ur0oOLj27qdT0NgMtTuu5fVV3kA73Q1lukt3AnMqKajgvLujzzOjisYMTJ4wq3/zy6e5Hk/UdHnR+OO1WQtflO7O0jW5P'
            'PTH3xOpJhz54Ldr/5Oc71/X980He+T7t1xv9y+MvpT54o83NqgPhzu8cXbJ8Xddt99s3jb4T0mnw2q9a9Li0pd+s54ID2xau1S35ZW/d/pgWL9'
            'R2mbW099qJ34wenrczY+78qvD5b57/V0v2dPPxjWsf1Xp+OK7Xl4F3Zr3c8ubJnM9uqXZvDxuQ8cOtP5ZE35j/9t7M9O6bu+Zop+06tODC9+v/'
            '6HjSv33iqT1Nfk18s+msVR8+eaTPH0Hbv3u6uPm55uuvGu+7zfY+ut19VsHHw41BCd8cbPPGrO8vf/pk+f4rc3fOnZT+9Jnuh02+Q37N/M7nkz'
            'NTBk5h6XBQJYnX2k/XfXuI/rDOcBNGC6qKy8cmJdLt9Hkfjzia7P7CjzMOTDs3udf5o4GNxietnZ+TtGYyuR4zpTQy5HLIncs9Tji57tNOf/PH'
            'Bxsy/tr60h/XF31r9F+60enojZzM06XXx2ccnDL15Iw31zXSDpww+vk1Ey+/U7C/57k1bT9sFrK28+7kV7x1My/12N97a/th507qz3ftcDltaP'
            'SUdS+PKfgsfMkbQdfS8z751b/3Zy2GbJ23/qRp19HkM2/0ODxlW/ytDuqKFovyyr4eump90s0nDsxfX7zxguHsO+/98ekjRqmiI5951X8afHuR'
            'nz1XXVo8qjjJapsP563Di6soQtzP5LseNeqzrk9eVTP/UouifTEdhu48vXXfbyRneXD2iZXnV1z+7NbNaS0++sr34rJuHk/GL3f2eLH4w8SZ79'
            '6bFL8uZP0XnUPfjy+/fsLvm9sTAk++Pcfnqy4fjO01Oeri/Blb3rli/PSdphcjfoy/8vSe6BEZL3Xq/90nD2JvdLjTtLEr21LZ+e7nR537GA5e'
            '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'
            'tGnaK9HLpu6beP27CyFnY6dMNx47dXF1yrWZ2gljeuZtaRV5r3F8t2HPPEzwe+uZL5oXdLgd2PUzr/z2adtiSlJ6XG/9yvDqX/qWqG6OeLYkeX'
            '3hgmciQtUbDy3t+M7Gsn7Ne3uO3PTDH+1PVXU8f2bkW6/07XOxenizkS90CBqw89bFF/cfHlE49IOykhk9nnhQdWpLQtWV3ivm93VJnlCS2eni'
            'gazs5PW3lj15wffmxbTNVb9Nurg17CXVGzl3Izsc+eBfr8z4otG+4uZH9oTFP73hPgTswpHzE871H9HtTv9vvhk4Kr3l81+fm5pY03Xt2a3TLy'
            'V2Oqv/tbrHgrUeCXt/1hGlQ6DHufkrdtOZ8ww3e9j6EMgNWqRHcX4Qk+96JNl3+oOpNdrKyk/26l9ufGXm2S0XVNO/bu6Rnhnd6/u7HlvjtYkv'
            'FNa9VrZv8esnfYpSrjYr3RisbX37lTFLD4967/u5Wb39u8+61GbY9iFT51a2uOs3/OVuMfmNo3vHJDZbUuXZpOvC5Wdf7PNH7daWa+b1+zpyzV'
            'vZH+w72/nBuMkrf1rGTHo/+sBQ/cSLJOjVnktNux61DJ41PCncf/BfvbLHXpqhiVl9/My1qGUb89SnBu7de+wroeoMm0Bsj2rFi8IYV6pAOsyz'
            'mg3LiAZ9UkHpsMnqFgrW/iBKqkk6hrEsn7K2RjRSHVIQWJZLLo8NiZ7dNE7cfWIaMhgUXaA3VZFlWj18xNe0ZgNttoRGmbkHNOpFD2h0Yy3hyY'
            'PPxcGEJNUQcnQGId1m0rumuMvCLJzm6fC7F05k0kPVHm746Xz+0J6ZBUiPQ3pT3E5FSi2xONGIXkImbZjnoOSw2pe/l2cack/HbWOB+2xmE6vv'
            'McL37zJjrej5xIn+VIfneZV4ySkPTm97wqlbK3zS0uMtjNqg+pLEuKpOMPgQuqVuadphOKdqAMvw9xAycOKdRv7zCyPcecj9ly45hRWV9FfFh1'
            'qLAPICDlzU+1XkkIs259+OAGfb5EzI98wf1MgwRsUyKpWa1bBOwxgGvuvUesCes/WOVuXCuDJurDvrwXqyOhVxpaWsikUx1pnVsi5UEaUwtJAF'
            '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'
            'ZO'
        ),
    },
    {
        "code": 'PCGD_TH_02_2025',
        "level": 'TIEU_HOC',
        "title": 'TH-02 – Thống kê kết quả PCGD Tiểu học',
        "source_name": '2. PCGD_2025_TH-02_phường Thành Vinh.xls',
        "target_name": 'PCGD_2025_TH_02.xls',
        "sha256": '37a528264bf837cf0d7f2460b0e678c8b9c07510a43f1c2c9bc81ee932b26a48',
        "size": 32768,
        "payload_b64": (
            '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'
        ),
    },
    {
        "code": 'PCGD_TH_01_GV_2025',
        "level": 'TIEU_HOC',
        "title": 'TH-01-GV – Thống kê đội ngũ giáo viên',
        "source_name": '3. PCGD_2025_TH-01_GV_phường Thành Vinh.xls',
        "target_name": 'PCGD_2025_TH_01_GV.xls',
        "sha256": '2d674aa0c43b21f2e7f9bfa051088f22dee1696be80ccc7d9906980926c06810',
        "size": 38912,
        "payload_b64": (
            'eNrtfQlcVcXb/5xzL3DuBpd9v1wBFRWR1V1BcEFFREVzV2QRBIEQXH5pkssvLTPUslDTTEmzXNLUckXNTMXS1NTU3Ct3swWt7P6fmbPcc85dgN'
            '7f+/983vdlDnfumWfmWeY7z8yZOXfO4eTXrldXf+x3DclCV6RAf5tUyFFEo+DTh0/oEeSbTPiU/+4NH1Nj+B8VVAw0pKMDSm9/wukCopEjg9A1'
            '+N6iPAAxQtfhMxIVIxVC/UomjRlQNq0w1/j/ISQSGzIobEM1OF4XOKPQCqC6Il9imRuJ3Um8mZTbQ+IukIND9aiS0Pac3w6lE0i510gcTGJnhC'
            'XuJDzfEUoU8kNfwjeDKijCSDtQ3VAJykMZqIDkfmI39127uV9Cj2LQHtpWLsXn0tZyaV4ybc0q+7zIDq/IKnqNLDdCzEsh2oVKh7yJKBtNQkaU'
            'Ct9T4HsgKgJaBirkOOgGcwjW15PjUQM5JO1GW8feNNM6flhbQ2v0SKRtDaovh6rBHB4N5KBQLN/S9eZQNZCDRt4NrodrgzjCKQq1bZBVygZzXE'
            'IN5XhErpkNrXlsgzk6N7jN4xtQj5YoF6S3FXToqCTSD/LQONInjCgF4vEoF5XKe2ID6qCudx0MygDkAB6FgkODQ8JDQiLHtOg0MoxPjGxhUDaB'
            'GUqAJH/EwOysUdJCwcgJBZoLRURK5UAal2oOVQmWl5JJ44q2A6SiERqD6S2NvGYuOTKMU8wTglsHk9yEMcAagVrAAaxiPimTjCMehaOOUmWsbV'
            'J9xDSRyvh4s4i2qBWgb1bK81swW3DGoLWAPxUCNoTAEQmTASOg9KExGHWC89bIWo5B2QVVQbPYYBsBLZyNstAoOwLi0fvQZCIBEfCxp12eb1D2'
            'Ruvg3K4IW5ZYCnserYd+QY2BYi2BbM1onMdaZb8ELyMYvoOt5iaQ2KDMRx+gGFtKxwCTPZXmfEuF0jxe3UtoA4xhVtTJ4bCl1no5qfp4OOzV+Q'
            'X0IVDsGmGv5tZKWTfAOgYM+ghmRAg6hEGpRhth9EG4g4RchastDr+ZjDC15BdB1cZG+n8PnUKWdFe+/CccWbncBn2zDfp8G/RlNuirbNA32KB/'
            '1EB7ltqgf9hA+Wx5Nxvl3WzY42bDHrd6y//YBv2zBpbfboO+0wZ9mw36Prv2uFvQNxK6B09/w9X1Lc1bGh4HT4Gek7M/aH8Qb48XT/9V6p/eNv'
            'zEh6efQWkIlfvw5X0ldCyWpfuZ6UardJlefwv72fYNMMsZC6d+fPlAG+3L8PQVrq5eGi8N3y8MIvksDiw+QTbsMZr1ZiD0sVDfJjbKO5D+Dq32'
            'xNWVUTJK5NiG0J1t0IUbUCelchQ8/bzleIJXGfLygpxHOEJKns4u4P3MekV2IrE90vLD5XQ2WI5jzuTcx6K8sw05tA17EG/PI2tyLO105OlW8Q'
            'E7r8rxp1n6PWv4Gy3wdODpX9qgy/SqbZRX22hHDcxPCP2StfKW9dLaKK+zKd8e3VK+ziZ9A0uX6dWT82CL8rb8ypb/WLRXHX7owvu/TK8tPzfT'
            'KVcGWaNjYdboeldk0V8s9aps4KawQXe2QXeqq5/aGAf0UD7BmGDUC/SNpLz+r2426B426N1ldGUd5ZU26JRAn854oOmM+E58EXI81+PEDKYzmi'
            'Gh68ntKh2HG2kDbkqrJLTsHGwNPzG25Hetk9/BLr9bnfyOdvnd6+R3ssvvUSc/Y5ffs05+lV1+rzr4a1Ls4+9dJ799/H3q5LePv2+d/Pbx96uT'
            '3z7+/nXy28c/QMKPLPijY+zjH1gnv338DXXy28c/qE5++/gb6+S3j3+TOvnt4x9cBz87GtrmD6mT3z7+oXXy28e/aZ389vFvVie/ffyb18lvH/'
            '8wgR/P0lYgR5OYH9NMR74ymfkXyPhbEIR4/j9mIAv+x48fC/xOHG3mzJkm/sYJI6ZxN1ZUYhp3Y0UtpnHB0p6Wgj3W8MD8VVVVFvbEx8db2ENo'
            'MnsITWYPoQn2hMnsaUVGJZ20PkSTZVuES9oCVj0WWH7xUNwWcv7WEl9QiOrO1KsvRdTBb4q3z9+mDn75WCrHKlLASs5v2c5REr+Lj59s6bc1lf'
            '+Nfieve7Sk7cT9gNdjKqfstF2MtB9mW7a96e4KEf9UGX8sGemEsqYagZ+v+9atWwV+Rkzj8FCJaRweajGNw8OyLeJkbRFfrzHgP9fnWsvsaWvT'
            'D50BI2oGkyZjaEeKWZtEOFnpOJLOxFXA0pnbSzq+CSFRx5eX7UDKSibMNst2bEDZ3g0o28dm2SU0LC7wMjU6sqmxtbFbZmZ2YWnUYiYZLRZJoJ'
            'QGkw66QSRcEo0AiRF1Q5lwZKNC8jMfIhsltMhJmZ1z+W6tyQGfs2s+E9bgKtcQbakh2I6GaLMGh+ycv25+a6HBTa4hxlJDMzsaYswaHLNz7t+/'
            'b6HBXa4h1lJDSzsaYs0anLJzTI9rLDR4yDXEWWqIsKMhzqyByc65cO2xhQZPuYa2lhqi7Whoa9agys65/vA7Cw1eWEOsfV8KAg2x9fClmpS95x'
            '5YaPCWa7DiSyF2NIh9qSblyfGNFhp85Bqs+FJzOxrEvlSTcvHiRQsNvnINVnyplR0NYl+qSTH9UGmhwU+uwYovtbGjQexLNSmffPGjhQZ/uQYr'
            'vhRjR4PYl2pSvrj6iYWGAKyhrX1fMoKGtvXwpeiY5Qd/YDVwWxCxhkC5Biu+FGpHg9iXomN+3TLHQoNBrsGKL4XZ0SD2peiYo0ePWmgIkmuw4k'
            'vhdjSIfSk6xnQhx0KDUa7Bii9F2tEg9qXomIUfXLTQ0ESuwYovxdrRIPal6JgPTi6UadAivL8DCV7UWSY70ORk03MQGrH8rIW8ELO8aEt5TWTy'
            'xH6C0P0ZURbyQs3yYizlNZXJE3sFu+iRy2tqlhdrKa+FTJ7YB0BGNbKQ18wsL85SXmuZPHGLI9S95HMLec3N8tpayouSyRO3L0LFG3vJ5DGw1I'
            'VZW2JG1mImViqL8jcpUCKst7IEGQ4mduHrwJ3jhfESWg/LXQ1CSRkFmWUFGaV5RYWLmelSWbSXSYPY7U6ZqAziDLAtDxWBjXiSzMvGE2JeNl4s'
            'OCJnco4XGRRYLU4xkpRKklpCu8CSVw025WZn5huTsgsKFjP/kpnkbVKDSbkAVCbKh26RBGcFcIgNkjsIbxCeaTsKBrEpRpJSSVJLaE9Y8+oR6j'
            'G1uCCjMKO0qGSaMT17auliJlFmVpxJj3qgqaiYoFRIkCpCJWgamJgOJk6FNJ6T8jjhGi+hVTANhw7Xq6gIGrKtrCH9TErUC4QUyZoSr5t5MXhd'
            'vYR2hgEC/CQ5OyMrr3C8McrCPIXepELJYAZ2izwwbzyYxXZ6ghP4Uvf0CSaMjHkAwHIjxHKjLeW6WpEbbUOuKf6jmjuc3DZiuTGWct2syI2xIZ'
            'e91NFEbqRYbqxF51C4W5EbKzQML3cJrQZ0YOTqXVhcBo1dLGtsD6hFb+Auhk5RKvE8vE7n2wav4/95V9ADjtA9U/IK87OzuL7QU2aHD3TPFFKP'
            'fLJnS9wbaCTukrxmvG7Hfq0FNKF3pGaXlZZkFFgMSFQAcOC9h7h+JWQAkAwmsHoXBpNs7IHgNOXItJgJlsnBg0Eq6QgTOSkIYbePxW6fWlSavZ'
            'gZJ6uUGtwes5SCenwbQFBqqhHgxEt4M5xsipGkVJLUEloDYzRcOvqXlZIWLZEp9QTR/UltLdtUPLyx44J5jKAkowklGU0oyWiCjVDDwA5elZ5X'
            'WgAVj5L5pgtowXs/SwGnbAtfb4qhwCLaERFFpbjZZHMGhS8RgbFjwVYg8RzTUdS9WcP5FHYJV1jlaxF6LqOkEHcedpjrKMNJY9Ki50B4Cfgc33'
            '+sDW/4byEzFC0UcVeQX9hcoXwGGkfqOAi4ppGzfsR/8wD7ieD3aXA2mVTDXEK8yxZGSnQdsU8y4AdtyO0TLjIR7cRfwCUR4qPychIjfFJdXQ1f'
            '5aiy0oQqY3Kwa6EaKJ8DhwkXzIF0jYnwmTiZrLxyTlw5qxDKYL4a4DeZKlElpE2VwAtyYSRAMTkmFFNTA3Q8MsCnEj45ID6nEi1duhRBARRTmU'
            'NumMXAp5J8gBYDvEAYqXfm7vxyjxOhseTZjLmoM4rtSX5xotIBk1MGtiXy0R2IXakLBrwvGdPyKCOO0TVA0wiY5kGJQrSM8YGP9Ckm/nsNo4eP'
            '9MmnBdBbKTg2UeRb6Q1+zvMcoBj4wIVoOo3+QscdhwOtF7mHB6Ylo5OGVEgaUV90DGI9dd7Qm2xr7oVywbReMIwegI5nREPg7BjQjdD4yeiMAQ'
            '9lHxnSkLhMd3TTkEQcrjc6aBgMZ8moBig6RPVDHxrKUEeSmQxXw0jwktbAOgTfsEpPd8TGlKAt1GWCFHh9UuIA/GNar7xrRcbJeXcK4Tw193oh'
            'OQfI0+8UahCVjFZzyJaKuEEdFh4N5HHgsGcB7DYE7KvgqoQrDx0Ba3iuKzxXGlxOrWc6YfvOcromQXsCvolcYxlhopOL9mNSMrphKCYtfJqUhR'
            'E5FT00AHd36A+FROgFQyb0QRB3FDAsAF1GAkMb6EAXgVnPInEPSudyvoLjq8Q/SqG+RdBDqRRIriZOlCsqKiuEZ2Fl6ANDIedrueiAgT/DlSxm'
            'q5UGTRIBLY+dUoWoIUhBYY5iKPWYlNbgUhFgI2YqBGTTYf7aHZByYm1lQdBD7aG+3FcSpKEV05MHpalw7bdQF4m5uPUHgUoGkW30hwjSuegEgA'
            'KO0C0Von7p2CW6O7ElCmG+KeSnpoLMvrnXMoF9KNStylBK2mMzZCtIDlxC0iMS7xXm4uTtiQwezO+UGTNz7wP7oBQHLLSWAz4QURh5jNxqIihT'
            'BFhpHY0QLGcuFZBoiBhn7CG90GbqEul3KVyfShR6kEzLNNBRRnSsM5TJdFlvYx3ra9iEjqRn4yzsdd2gWDOcyTpSKZAvkzNXCjfMRE7iVTJFjo'
            'Eey5a5xl1VOpB8BTWRzCgj4YMv4KIuGSVNRkuTMdgFkqA3sMmp6AaYp8V9MBmdJhOlZPSDATvMMQM+98ctfgAlkSokA0yppNAPhm7wPRgASwWX'
            'NKKh6BB0JSwEQ4qhdUNUGIxu94n5uIHCSRV/4aqRBU5UBist6C/Y4/kxBCvOhbqzLTeEOGIu22+Tybi2hWKLJXJZGj5Lz43uSdAuuIjAk4TuGz'
            'KI+RloIsHHZla0OUtP/cpZOgS1oLAmnaURuKffJ2aocJ8zptwx9ssocibnA8oy8GyhpKxwvIrnTCHXoRQYrfLwHDYt3ZhYUJZtHJQ/DS4UU1sh'
            'ylrljQQ5s0uYD7FbiA+5e7hiZx8PuExDh4nHDoDzDKF6rBoPeSFsy3EDBgc3D8v0C/FnE+oDXtQTLspa/NM3rBNOwPfH8D0F6jEfFv39oddfg+'
            '918N0KFu0/w3ffdjDNgXFkMMxP/GGqFtYBoQfwncl4wUe6WYY894iWMks0S2WX3LS+CiXensiQbQm3v3fZjycAATS7SWhEUlFhaXZh6Zj0acXZ'
            'k0ZFTJ1Y8NGi46mHIvU9apP/mn2rdZ8VWxOYprdnHVl45L3p1V9WhnodPb913eA/a1O+SU9cb/QqCL8QU7uy042SvUFO2w+9vWJdn82PE1uF3v'
            'XvNarqSrv+FzYOmf+Sn0/njCqXt3/dtW9PWLuXy3vPXzaw6oUfisenbO2ysKIkqGLtN3+0p4/HTW5W/qzc+UTZgEs+d+cvan/jaNK5W4odWwKH'
            'dnlw6+nbodcrPtkV3zb1oz5JzOxt1YvP3Fv/tOdRr8SIY581/y1ibav5q08MO5j+1HfLT6Oz407Frf/e+FizwO3QFu38MV+PN/q2/mF/p5Xz71'
            '38dljBnssLty6c3nZ0TeoBk8fY3+J/cj9dM3PETBpPjhQyvKq+Xfcj3iHYFtoJb1UcU5JdMKlNBI7nvP71hEOR2pcfzt07+9SMAd8c8mk6uU1V'
            'RVKbNTPQtbCZucH+F/3vXux/xFG9m5mz9mHtB13+3vTq02tv/Gj0WrbB8dD1pPjjudcmd9k/c9bRuWvXNWVGTC3+95oXLm4fsyft1JrOJ6L8q5'
            'J3RL7p5jLvQv89AzclZp06qv+mT4+LseNCZ65b9PyYc0Fvr/S92jbl9G9eA8+1G7vp9fVHTdsORdas7H9g5ubwWz2Uhe3eSMm7OW71+jY3Bu2t'
            'WJ+94Yzh5PZPn377jLJW0fxpS71mw9kr3O6f0tzsidltRHG/jMKM8dkl2EO0Nf3Uh4z6hGszVk+puNAuc3dYj3Fbj2/a/TtKWuHX7ci736y6eO'
            '7WjdntvrricXZ5X92w8BVOuleyT0TM2/loevg6//XfJQccDi+4dsTzh9tTfY5+8pr7ld5fThowI+RsxdyN2y8bv93e6myTh+GXR38WOqHLq72e'
            '++l0bYvrPe62aqam21s3fs3dyJkauKJO9mV7g4XxUdjse8NOvOrfzmO/9x/x2klFBQ//CBl9Xbf77y93XOiXeG/tzbCvv4x5JW5Nt8VTbozonb'
            'rXQ513u+rkCJeq2JMJSW2eZXq5fffr6z8tyem8tKDDnwcGfrM4Ltxw4mGXZ79+v/zKki/aFXbtvX7Kgs+M4fefbM8ffOVQXnXi4p6BpgO5j46W'
            'XXF3q2ryXvjhwJkL586cVHvj9cJ3A31vKF8Yu+qVwDM/Z7bY9k6fHsrIBZ/HLb3m8aCfT/+KOX0NgxMXplYXJbYacXbCtsXGxX+MfsWt+IUp0U'
            '2o33seq9q/u/j7dcWVfVY70sdePha3Izy27YpvPRJrerxV8tDn1EKXX+bcy5qzKvnKmuTkT0/9/OEfX2++9/36d985OO+Ybse/LyeYPCfP7db+'
            '8jeTHueOTB2+ud2dE3u/2e+Y9tnCuzv/OPHitl/XUWHM2KoO3qfHZ+7feyXfY6jijZllTx5s/9fFOE3Rkyujb+w5lxak2dztM9Mffi9G/pTo0X'
            'qP460nX/jtG100seyu1+jZJdMn6a5sePDbndZQKqrp7VLdqImxO3e/enZphWqNU+rU3QOCPtmh/rGvR3rSsFETXlH1vfX+8L4nM79wQmkJr4T2'
            '7tLh60dKh7TDo7offdv9YUX3KI/R/x7YbOynuwYHpu+8tv+PM7+1C3T9ZPaijI1TKfeP2659MjX4auiSQFPMozv+Fec2j36n64xpf/y68/T4r1'
            'NX/T2wZuOoYZOdwl5L2b0z/sVntbVjps589sehiz9euTlo8/W582f+8stbRS+abox6kHH4eNqev38/vPytNqNn1p5dFd9lytQrN3ILDvYKPXBw'
            '9+z+e/4Mf8mh45MbUfvfPhzW8/OtCVFPJn/64Ph5+vvKkDsH72d2muPSYf0CzdT8389f77jgaYrbkZqdNz6nDVE9a32nOF7dsez4vEe5S3s+OP'
            'q05vPLvX46HzfFu2rIrD+3aW+++enIyZkFp/b0GtBywJxB4V3KXu8XNfmjB65Nhox8Pbm6cqz77S7B33cN/qpiwZfnW66tOkX1NraZ5N0tebvn'
            '8jUvf991zabBtY8+fm3OEXqA01PX94f4FK2u7D7/+C2m6RntkyaLP371ZvFXCvdz3m7RgRnH9rw4b27xhUu3towOub2zW8alvPj3fvm8Z0nv9y'
            'NWvTwvyv1C5unCBYtr5gYujm378apXWrwR9vhB1O1ZQVF/qgacq3B6ozClNmnWxtJVrZUuCSP79TlOD5iSc2nR8RFvD/ut04rTqoPDsxP+bN27'
            'f/K/3t+3OeyFG1cGTD6ya1PP05cXbvxoZNqJ2vbPdx3k1Mpvn6o2KP2BYVlVbWTn8Lvv3J1dPFNfaJrZ5tLylbc+fOtuVeLsqR92yd/33LlOtV'
            'k3vpiRGBZ4rMPhlxMfXnb4taoYzT6WGjT8+WkVx8c92bAy6+3qgz0C8vxfj3naYdHPkT19Cx7l7ytxm3+wLHTPAtX52rsZ64rmrtt2c97cp9O2'
            'Dxk0/vTIzsrFx3+esCbg5W3/rjl14tvH2iG7zhWEzBgyWp+2w7tJRkrOkvOTK3JbOw6u+PVowKwfjKufm9w0/Dtnr3Nv/tljw7dD0fboVluefz'
            'x299mf/csiqZD2A5u8kvTmus5nX713J2t09vvtHE5vQOd7hLccW3l7x/Vdz0+bUDbtg3dCTnup1lwqcOsYvevl+T5zP12fGvcvg5/3ibIXKge+'
            'ulI9d6VLn/zea8qejQqPWJ6/ZcRZx2XL+nQb9HDtjXY7/dOiqWMd/1Z+9exR3NF3J8/57lGw34Hj2xIe//XS/gVbs0Z+aXB73lDcuuNnfqHdxz'
            '0YsLh0+va/onWxZ/3e++zsjgT99yNKJla8WftaQOjl1OiVKcXGE5/4h7T85mnTsOmbPL/a/d1fj8dmH82peJARsHJqZscbta5vDF0zeBClnV9+'
            'Ln5752VNXqqtrKpofbeoKspza/6+tDNxb7wesuzw+p/C3n/7x+LWt5oGzhj8RfWnLb/VUnGJA2MPPr/W7yPf9A+XLx0V8uOWj++unLg2ePy8H7'
            'aOH77hvV3vjzj8ka/XxLFNl76V/9jxwx7zup2ucV7Vt3bDzR3ew3du7R+2W6ncs2DVmrsr1zTxObN0ybAzHjfKfIcsG7Xgu72ZH1fHrH9nXW+f'
            'DVdGfjpq/ogLIStOH7ha1TH+/MYhrbX9vP7sE5j37NDLTy8q/eMdf/7pwIirvm8mrnN7cdpVpm33pL3NW2QnLX/wt8La5UN3qmLVDrxrlmJ3Do'
            'ovH+wFX34F5CYA/dQHIz3m1M6awhQVnd6lX9Ts8ryTG88o5tyM07WNDx1w775uUzgT8XLGvsq83W+9c9Q9M/r7qNwNfkzH228+v+zAxE/vLUwY'
            '6JU6/0KnrC1jZy0sanffc/yivmH9moUODIuIervEuXmfJStOvpL+tHxT+zWvD7kZvOb9bl/uPplcWzbj3Z+XU9MPh+4dp3/hLPJdmrbMtO1Ze7'
            '/549sEeY36e0C3SRfmOoS990XN1ZDlG1KUx0bs2vX5FcRXnaJbI9szQmmwMj+UC5BPkUQ71yjJhEnOKJ9yiLZP0/YnIHJJ8uu/OXxL25oNyGXI'
            'nUC0mV1Vb5dI6+tANsY6wDEKBOnJ4zPLGT18pHfJFgBtgYyGC7PvjNFL3hmjoX0kOzmzBiI0txC0FCNYZLF302lYILqQc1eytUoP1frrg5+/6T'
            'cuLX4Mobck9FYknkUo5chsQFMa35ELp16CnANKD24P/2xSeg6JmwmlT8Y3F52HCedX41uI6P2QI/5VkKybisj9hhRYhKbBAqsDeY64foFSGhSX'
            'UJhacYQCK1RomSaWySJbsobSFGJfHEKhbuS3l/90YF9pYv6Wh6SMwiL8A+ZfjJmBlAUfUCn3KFC1ikn6LyPA6jY5IXSPeoqVZFEKmlIolLQD7Z'
            'hFUXDuotSD3zmJE4xCRakpDa2ldbQz7aJAapxLK2jCRjvRDK3CgjCFwpk0sFJKykENMp1oJ4UTFGTwPniNBSPS6nSElyNRyJkXRTtQjspyJ2UC'
            'o0xALpjKGBWMUSmRCTqcgUnPMmGllCPlRDGMm4pGrqAOuWVRUM4dW6UMRtlZVBajgCqDfCdaZa4VTewGvUivcFW40e60B+1Je9HePNmH9qX8KH'
            '8qgAqkDXQQbaSb0MF0CB1KN6Wa0c3pMLoF3dIJ0Zz5AjK0miZKKGdaqQx2oZEyS6lwcMS5fJ4LraddaeRgrrmZ2dEDSjhiExGgyTShGVdoHUaB'
            'VJxhIIxp4qgw60JcTRi9EgYARqGhTSZo9oT2yEhxmypVcMSCpy3TsPti8R5zCtKjIR01134uRZdDfxkKnZ7ywfKyBL+C4AIOSVGI4u7E82M4eY'
            '+I+XU9/yw48X2ifo5OoZFJqcMjI+Mieicl1V/LP+VDVvloisIez9qtYn+waQxsWIyHPdQfpaKeqDfqjnrAGf4VpRsMbfUN/1X+5P+kg5aTX+DY'
            'cJDifBYfSu4RyHoMzt1RNsoBG/DGFnzvexCkS8kGF3zHcNJ/tAE05MdYuMLgAZtmbac0CoQ9lnLibFdwATo8nAuXMqEf/gOH5l68hsd8uv5cs2'
            'Bs1Tf2msbwfzqsRsFwHRmO+GssvhJ7aR1nHxh7NZ7/ptAKphl8bEv5fKz56WA8e8dvZ3zt/mDyBr0Z5IcFPDQkkqs6TmNdi73NaRoGht6ifAbW'
            'GxOV5rQGjt6O5rQWRjJxfhMYBC4yidyo5yysRtinHRmunzdBi8lQUU11IjTKCo0mtEFITFMQWq6knJLQdhNaAuVCaA6ENkchpjkS2jZJOScrNM'
            'YKTWWFprZC01ihaa3QdFZozlZoLlZoeis0Vys0N0ILl9DcrdA8rNA8rdC8rNC8WZyRmOZDaElcG6USmi+hDZTQ/KzQ/K3QAghtioQWSGgzJTSD'
            'lXJBMtoz7k0Vo8jzdhRegoHvjeLoNFyHcdiHOpPr5/h/dARy0gxwfaeINDV51jgbDiPJo4gF7TkLKMECvHbNJCu+fbACpMACvEU3q8FHZ3IYQY'
            'of6UXj4OjCHV25Q0U04g4ympRhUxQaRmj7EN4JREOKPRy4fEeYwSg5uxXQe3I4OkPKYL5oSKkEvvocBk5GEEhzFGQbIYXPlMRCXALfeRhNeiyb'
            'otEY0lf3kZQCjYW5lZLLc0AjSZ9lU46QUgspJ0hphBQDKa2QUkFKJ6TUkHIWUhpIuQgpLaT0QkoHKVch5Qx2unEoKoFnNHe4cfnucO5O8t3IQ2'
            'OjRYcvV8YPzj1IGS2k/LncQC7XAPo8BX1BkPISUkZIeXO4OBD0RgNyz0iKhml1FFfSATDrTnbPsiklpGIInw+5MzXS4tBxJZ1RPOnlbMoFUr5C'
            'Sg8pPyHlClN3fyHlBqkAIeUOs/JAIeUBfAYh5QmpICHlBSmjkPKGVBMh5QOpYCHlCzJDhJQfpEKFlD+kmgqpAEg1E1KBkGrOoe1A0B1J3lC3F9'
            'UQn+wBn0fxPcgwh2OGxHoSe5DYh8QBJDaSOJjEoSRuRuIwErckcTiJI0gcSeIoEkeTOIbEsSSOI3FbErcjcXsSdyBxRxJ3InFnEnchcVcSx5M4'
            'AcflCQlG9CKtJj2oJ6kPrjteeueShyjZFI16oSTOe2CJAKleXK9yAmTYvL3Qkk6ASx6RMoGggtP+QGXIQ5Y4DEgIg/Z3NDkgCpP3KL0hGy6vMK'
            'PQkcetEVVNV/vqsbwcyFKhfLwRISGfIAtxNXuOYL1EXR2XkEdQxpT+HJ2NJ5IYcsv7snQSP4o3n6OECYTXh4woTuAlvbg6+El0+nO1DiC1DoQy'
            'PpAykMcPHsXnkXafwL35ASPJcEiiBIwPQ5DsyI1gDEGSpSs43Fi6UqCL8WQkeD6KZ/FkRHgmAZ46xPB4YtAYFrTybqQCDIkTueoDaCgzIY+Hoj'
            'zROmjgNHLQ+HgCcW4fzmweNIYFTdDJgsZIQGMkoLHwP4pnQVNxoDEENBUBrRMHjkoATSUBTSWAppKAprIKmsoMGlgZhq0Tg6biPC3e7GnQNwRP'
            '40DzIJSudkGTwmUGjeFAUwmgqThPi5d4mkoCmsoOaGoOND0BTU1A68yBoxZAU0tAUwugqSWgqa2CphZ5WmcATSMFTc2B1lHkLZ24cwBt7Dizp/'
            'F0C9DiLEDjvU4MmloATc2BxutkQVNLQFPbAU3DgeZBQNMQ0Lpw4GgE0DQS0DQCaBoJaBqroGlEntYdQNNKQdNIuicZu8qTzJ5WzXoa64E2uifn'
            'mbY8Tc+BphFA00i6pw8HmkYCmsYKaPyYpuVA8yGgaQloXTlwtAJoWgloWgE0rQQ0rVXQtCJPi0/AvwtJQNNyntZVVPEuZtDKWU9Dou5k6Wnt69'
            'U9tQJoWs7TeJ0saFoJaFo7oOk40AIIaDoCWjx3SdVJLqk6ySVVJ4FLZ/WSqhPB1QfgcpbCpePg6iOCItl8CTCyPhZKKD1s+FgPux2T9zGdAJeO'
            'g4vX6c9VTQyXzsp1k++YzhxcRgKXM4ErgYPLWQKXswQuZwlczlbhcpZ1SRcpXM5cl0wyj2PcOYErgfUu9kqaZMO7EuxeMXm4nAW4nLkumSQZx5'
            'wlcDlL4NJL4HLh4AomcLkQuLpxcLlI4HKRwOUigcvFKlwuIrgGA1x6KVwuLFwJg4jpwQSudDNckllZug3vShPBxUjiCUQmC5eLAJcLC5eg05+r'
            'mhguFzvepefgCiVw6QlciRxAegJXL4CJzVNyALEpMVx6q3DpRZ0xEuByksKl5zojC0JkgjlmpxZZoqtkhA3vCrMxdiHEVpKFSy/Apec6I6/Tn6'
            'uoGC69jUksrjZetg5jH0oEua7kFoAjLKLwBoEOoleduSLF3zrUFE/haTJvT6TZYgpZMaWJK6aoVoiKKSXFYI7GF1NWK0XFHCTFvJCaL+ZQ7cAV'
            '88fLCqFYKFlmOOFmwGS8zMBPfTkakR8sM37HTzJVIxGnk8AZQThVPCebzfDZCS+w2c8k2So+O20qyVZLudV8dnkvkq2RZmsE3f8i2VpptlbI9i'
            'HZznw22zI6GCTZgs6CmkQo6Cm3woXPfsQaqZdm60UQ42xXabarLNtNmu0my3aXZrvz2WPLiG4PabaHwB1Osj2l2Z5CdhjJ9pJme8nazlua7S3j'
            '9pFm+wjZPUi2rzTbV1YxP2m2n6zl/aXZ/rKWD5BmB8iEB0qzA2XZBmm2QebtQdLsICG7I8k2SrONMrdy4LP3kTd1+6FkycEOC+5kWAjj7ge5k2'
            'FBfqi4kmpwzBbcKOoOTp5A7vjjFL6DNYK8xw1Lwe+pHWFxqMhwg98h3FvoeXgcIQMEdkfnaj25TYAHd/wqYPy2pWEJ+8Ab8Au8+8oO1nxPojic'
            'U+xpR7GnhWIXs2IXQbGnoBh3Rk/ogikIm+AJJvSzaoIXMSGCM8HLjgleMhM82FEPm+BXHSCY4CUxwQvaNoU0oTc04XDJYSQqfWAE7y860uDoD6'
            'qwcXjGMRR1J8a1JBfUofU4WLm+IrkD4BgIBy/XF+QOIe+TwHJ9Qe6QehwsYH4A0XPkztA+MmeiIcUeDkDB1zkVGiQcOo4H64vj9PnVWx/W4C+q'
            'B6sB3ztIFw5WA55SDiZvOcMa8IxpcD0OVkOATIMPUNSSNmEPN1I60KJ0oJ3SBovSBjulg2SlMcVcWofOgS9U+sMshZ4FMxUDeg91pbpTJ1EfKk'
            '442nCHSeEDE6xpaDbMV3yIXxSjceDo+MA/uhihHeU/xDQhtHAJLdgKLcQKLdQKrakVWjMrtOZWaGFWaC1kNNzyuB5DyFQS42UEBHn/Yb3FaMUf'
            'jcQfe3DeYqy3P54DJNtT+P8BFFv8pNuVdkM7HPEqIIGjDIHPq4wePuJyA8FfYAVAXidE/nsHnOkqweyLzC1oyBbcO3ONMGPDv7YYye8kBjgU5J'
            'cf/AsA/m3Cl6QdyeYWBygXxG1gCSRpI8eng0NJnr/XIn6HJc3tg1SQX4QMJJ8hdzwdyF03JfltxI18++H/LUR4WLlq7ncbDbkF40AuXvyeEiV5'
            'LQNFXi+AyD43B3Lgb3YTDv41SEnmLri8NxkSjVAXd7I3i/3/EioYqz3JtxcZm1XQmf1Jw/qRYYR9yI9PU1xdKfIbgw+h+5LhzYjGM97wEW/uof'
            'BrXxTdEffzYoPC3yZE7uFZ20tzde6qx0/75+o/XMSgVs23XYgk75ll34tLcQ6h5DY7YYNGcnt/sBPhOznTESLeMA+x27bf4Pbz3VSyb0/GZYR/'
            'Koms07CO8pyk+IrCSxRxwBP9UfEB6bmicftGY2gMjaExNIbG0BgaQ2NoDI2hMTSGxvCP1//02RNnV0T465e8Bev/8Keb8Pq/hlvrU9y6H+/1TO'
            'PW/UMR+1/JxnLrfbx+9+LuB+D7AFO59f167j7A7WdI+J+N/BN9tr4NelYn3lGZnntt96LC8cb8QxuMny+6trsyz1g4/vAHxvF5h1bjF9wd2lCI'
            'tHpWh4GT8VxRSf6k3Ozs0knm/xTRGBpDY2gMjaExNIbG0BgaQ2NoDI2hMfxfCfx7o/h/i4j3OOC9D07cOh8/MKXm1tBabh2Pd9C7cGt9vOfBjV'
            'vv82/k8uLuC+CnNPGzmfiJTPwcJn76MpBbk+N9HUbEPpePn6AM4db2+BlJ/GQkfh4S7//D+0bwfj68iw9vqMMbtPCuNvwENb4fgZ8nxU+R4mdH'
            '8TZivBkLbwDDW6bak/sbJhPeM40f8sLPLOFHcPATJfgBiQQuH+/Pxjuv8YY0vHkGb7rpxd3fwPnP4IO//zeGgeR/7uA3wvQg/4wJ/xOfhgQv5E'
            'DxsrAfGRn2XlI1m93T+j0n88tdniP/LyUfjSN25DfYf90QTYnrU1++U8+z3w5oEPk/HBPJ//mYRv7TTY7wP1zM/wDKVgjDr2Li+k999ZMNsXpe'
            'f3fQkElsYP8dVsPsaf8P6t9NpP//Aa1pjpo='
        ),
    },
    {
        "code": 'PCGD_TH_01_CSVC_2025',
        "level": 'TIEU_HOC',
        "title": 'TH-01-CSVC – Thống kê cơ sở vật chất',
        "source_name": '4. PCGD_2025_TH-01-CSVC_phường Thành Vinh.xls',
        "target_name": 'PCGD_2025_TH_01_CSVC.xls',
        "sha256": 'ef1cfd30847872bb8add78fed65f7e0e043bcef9fbc5f399297b0fc38e38c2e2',
        "size": 37888,
        "payload_b64": (
            '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'
        ),
    },
    {
        "code": 'PCGD_THCS_M1_2025',
        "level": 'THCS',
        "title": 'THCS-M1 – Phổ cập giáo dục THCS',
        "source_name": '1. PCGD_M1_THCS_2025_phường_Thành Vinh.xls',
        "target_name": 'PCGD_2025_THCS_M1.xls',
        "sha256": 'b1f5d6d4e684ba63b4dfc59813b151c9051acff7675f11d89ee5b83dba400203',
        "size": 51200,
        "payload_b64": (
            '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'
            'htPre6jJdQ3QU5bzQ1bjh6zWD1mdH7J6P2QNfsga/ZDl/ZA1+SFr9kPW4odsgB+ygX7IBvkhG+xDtr1C1oq+piarQ6x4NPWY4SnChXTP/CG15t'
            'f7zB9aa36Dz/xhteY3+swfXmt+3mf+iFrzm3zmj6wl/8k83/zbas3vm/+oWvP75j+61vy++Y+pNb9v/mNrze+b/7ha8mdk+ua/Xq35ffNvrzW/'
            'b/7ja83vm39Hrfl9859Qa37f/CfK8hOP/MIRy3v++rXm981/Uq35ffPfoNb8vvlvWGt+3/w3qjW/b/6Txfx0xLGaGJzS/BRzvv2e051/oSJ/Cj'
            'Lkyv/vmcQj/08//STmNzJs1qxZTtdtVl6O4Y1YkxRjN2LNUowtnvY0Fu1R44Pm37hxo4c9WVlZHvYwTGYPYgp7EBPtUR6Lm/hx3E71Q7apH7Jp'
            'fsg2E2VdXHsfO6TLfIcUerb90e+lvqPM31zmu1qJXfxt9f2MWvI7s3znz6wlvzL2K7lqIeNVK+NV6ZctZf0kK2uKZz87ueK/sZ8o695K1nbSfu'
            'sqx1nF+Wi71vK4cY9n2zuvr/YRN9rI+imn0k+dzpMefOzYscODD4bJ+EBMwQdiXuPGXYr2ybqtOPbfFzfa+uizTRWy7bz6cRAc/biZfF9FhvYo'
            'pqbcqNLxpJ3RVVlPgzvIAgfUzOk9yHRDWZ1KkPaU7e6HbA8/ZHv6IdvLD9k8P2R7+yGb74dsHz9k75Y5mm/ZAj8OJEP80HuvH3qH+uFnw/zQW+'
            'RDNlohOwElWOdSJk70lVjhK3GKr8SpvhKn+Uqc7ivxAV+JM3wlzvSV+KCvxFm+Eqt8JT7kK3G2NFHZvHP8aN55vkpZ4KuUR/1wuMf8kF3oh+zj'
            'ks4vXH3xLrvID9kn/JBd7Ifsk34EiiV+yC71Q/YpP+x92g/ZZ/yQXeaH7Ek/ZN/1KrtUE0qs9CpkRnoDR1NHp6Ki4rLK5kv47mSJRAOnszsDYa'
            'ydDue6DhjCOEgnCJZFpJiU4URqgvcrA4hRVzz6/OWfnHr6m8OsTlpCiLKEDM8SEn2UkOEuQV88+q8vPvQoIVRZQqZnCQ19lJDpLsFQPPrGjRse'
            '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'
        ),
    },
    {
        "code": 'PCGD_THCS_M2_2025',
        "level": 'THCS',
        "title": 'THCS-M2 – Tiêu chuẩn PCGD THCS',
        "source_name": '2. PCGD_M2_THCS_2025_phường_Thành Vinh.xls',
        "target_name": 'PCGD_2025_THCS_M2.xls',
        "sha256": '1fca61adb85230d08cbeb2a2bc1b3c9d1a795a7ab9a2731e2168e145c6a37d88',
        "size": 49664,
        "payload_b64": (
            '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'
            'UzbHzZhZ7DXz6zN/xdAnIkc2KH9bbnuytMtvrvenfhZz41jSz7ck2zfV6xX36NbrBb7XZ27dFR/V8Zv2SbIJWypmnXuw+nWbY8rEoOM7G/4R9H'
            'XjqUtP9j6Y9tpt090B2ZGnI1dfUT+zmu5waJP11PSfBqvdmtze3+yLqQ8uXehdsOfyjM0zxkYNqOx4QOM08I/4u45nK8f1HUfjJU8Sgb9WXFh1'
            'B39DKAryGX8kJb04u2BEcBA+Tvz0pyGHQqw/ejxp74TTZV3OHHL1Gxm8YmZS8PIyVOU/Ltfb45LH/Uudjppb7pZN/PrxqzVx7zZ8/Lpqzh21ct'
            'Fa80PXk+JP5FaNjNs/bvyxSV+v8pP1HT1s8vIxl7al7+l8ennzk6EeK5K3h8x1sJtysdOerhsSs04fU5xp3/pSxCDfcas+G57+s9eCL9yuRaWc'
            '/UPZ9efogRs+XX1Ms+VQSOUXnQ6M2xh4q7W0MHpOSt7NQUtXB9/otnfm6uy151Sntn33+sJbSiyh+e/NU06Aq2ns9x1KcrOHZgfzjqkZhRmDs4'
            'txhFhXploeUisSqsqWjpp5MTpzt3/rQZtPbNj9EiUtcW959KszX176+daNCdE/XnU6v7iDTe/AJRY207JPBk3Z8WRs4CqP1b8me34fWFB11Pn2'
            'vdGux7Z+4ni13Q8jupT5nJ85af22y+oL2xqfr/848PKAnb5D4j5u2/Pu2VcB11vfb9zAko4RN77jmaGnf4KStcmLKQ0Gxodisx/07lDkEa3Y53'
            'J3XK8He7/Num/v9pnkvnPDbwt8una9mdzuXFCTR8Utu44saTyrW7CZ5detg83ev7/U3/0ryv3FGa9MdcvF76bY7jwTFNDlqaTNZ8rtKKlDWfib'
            'mPBm4c3G3Hm0Zcr7DRdYHby+K31P9ydxnnYXpxxueXncb4/Hjrz0amKrp7Iuyhu74g8d3L/7+b2Go05ttx4+MW7mp99Hrf176ZxjL49Mdj0Y5r'
            'Cj1/jMP4dWjp7o2+/ZwMzDpwPufnL3SM7SzhenKKaWBbexXx3n+ekxxZiyFWeu9vYv6vbd9BWdrZKOj2kfud03YmREQKOJC6Y2uHVFvqzU66Xb'
            't2dbfNCg7FPv+lUf7Uo/Ne7dkR8/t9ka57Ks+JNv6v98etyInTsrcjeveXXzgPrS1rRG8xvtXviBzVfFzj9v2N74YfuVnSSnhskapu78JXbd4p'
            'NnPPPLz2y0vbx+SP663Cqbt30bLxl14vfMqkj/8+l9DoyKTd20bNLPXzmlDzgw32NbmxMXNrYM2Ld5/EblyL4r1q5In5DY/voxy12dNxREuqw6'
            'qc5s82rJkz47z60p/HHuHf8pkwN3nVNmKk+UfqtcmnmkGeqcMM13alzTDk9cbepPWzxlFtXwSgt5omyP9PuUiuKMLacCCg6M+yPgXtGvy3M9fJ'
            'L6PKUbDMpu9/Tp4ZmzW114a/HV+Wh10dU9Tce8++vB66LBwQOWxGmy9+3okX3s4dKYkFtXNH/+cfXquKq3f9y3e5z+wezCvdNdGry7/FP6vr/f'
            'fmq35iPHOytH//1w3aiN6XvfPloXP+79e6f2nThdMfFVu4mTRpV32ts2cLwk9s8b1P4lreJbHZ6VUP/uyNWFJ07RqkpFaZX7L1FVjra9j5jtiY'
            '7b/t3LxBZzD3/7/FDI5vL+R3InDF9FqdbutbZ6tWr4tStLOqX+5jOxY78x0V0Kmn4Xl6re6zD/eM6UJovaOn3vYBZz5Ey3/d/Kj8w4G+d3eHP+'
            'fOumjgWBe1cdzldfj2j3pfU3CccnvUyWfrBwp2z8uiaXSr4cbdOm/6rCKkcP+Q6zZbbPylKahF9J6jbVe/7xFtNW5z0p801yOXZlul1qv77JT0'
            'rKA57/6hM4scPtmYfes1kVP9H6xsgx83/09jjmt/C7kkc+R1KyPk5dVH+ag8v2ttdPHb7i4ijrcrNe6L3xoxaWfbQ6/4lk2s+7/pYfmLf7p07S'
            'T+vvXDTnGeqyP2XnofmvQrZc3xG9PHNi/94589v2GHn51mG3ep/kDZz0ssURp8+X2R+5cuNvW3Obeb2ifmoXL6u/7kFGz4FxCSO/WXvf1Sp3dl'
            'r6lkXer6ZuStz+kWT75E6jts8ZneM/Q5G+6jXaU/jrHpvuPy5sb3dv2CDaTrZ1nCK443JPy1MZ0ld91retv3nI/F3KR6M/H35inMvOo9f2Nd+e'
            '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'
        ),
    },
    {
        "code": 'PCGD_THCS_TK_2025',
        "level": 'THCS',
        "title": 'THCS-TK – Thống kê kết quả PCGD THCS',
        "source_name": '3. PCGD_THCS_2025_TK_phường_Thành Vinh.xls',
        "target_name": 'PCGD_2025_THCS_TK.xls',
        "sha256": '958569a4e428c58d42665926af1b1730fd5516b09a56003c42948da4f8647da0',
        "size": 33280,
        "payload_b64": (
            'eNrtPQdYFEfbs3t33B71DpAq5wmoqIB0jSUgoIIioqLRWBGOEqoIli8aiOWzxChiYkSNxiBq7CVqYkWNGhUTe4ldNIndGPOhJnr/O7N7d3t7Bc'
            'n3/f///M/PLDu7887b5p13Zmf2ZoeTPypuLN/scRMJwttIhF5rZMiKB6PgjNQm5AjyNRp8q72+DaemMfyfCjIGKtJKgpI7nJBeQjSyYhC6CddN'
            '4v0QI3QLzqGoAMkQ6l04ZkTf4gl5mar/gRBNdEihsA7V4Hhd4I5CSwCqQO5EM0cSO5F4I8HbTeIukIND9bBCX63fDqKjCN7HJPYmsT3CHHcQmp'
            '8IJBh5oO/hyqAyiqWUUF1RIcpCKSiHy6UgdzdtLldkMZe2wPkLPWfaVK5OK9oUZ0u5X/NyKy3pbCL3CU8rYW4gXy6cDlQy5OUiNRqDVCgRruPg'
            '2g/lAywF5XEUdIMpdBq8IcWTBlKwtaopMWcDXEpNiXn7ma83rEtDy/vEoLbelELWYArnBlJQKEznB29KIWsgBY1cG1wORYMo/CkKRTRIK3GDKa'
            '6ghlI8Ic/OhpY8rMEUnRtc55ENKEcblAncI3Qy7KgY0g6y0CjSJlQoAeIMlImKhO20AWWwfuMyKMVNkQQ8Cnn7evv4+/gEjWjdaaifNjG0tVLc'
            'HEY3TQ3yh/RTpw0zRPJGUuSlRwoMMuQDaYzVCoriLcQScONQ24OlQhAageFtVFrJXHKoHydYC/AO8Ca5USOANBC1hgNI+XSGRAKKSOSPOhoKY3'
            'UzlEdU44mMjNSziEBtwfp6oVp6I2IjylC0AuxP+YAOPnAEwUBCBVZaq/JGneA+AJnKUYq7oCqoFjNkQ6CG1SgNDbPAIBKthCrjMQiE05J0Yb5S'
            'HI9Wwb1FFuY0MWY2Gq2GdkGNALQ2ADalNM5jtbKMoeXhDVdvk7lRJFaKs9FXKNSc0BFAZEmkPt9YoGGeVtyHaA30YSbECc1hTqxpPEPxkXBYKv'
            'P7aC1ALCphqeSmsEwrYNoGDFoHoykEDeIGPF9x+EOjgoGodspUrWqE//fAKWQMd9Lif82BxYvNwDeagc80A19kBr7MDHyNGfi6BuqzwAx8bQP5'
            's/jOZvCdzejjbEYf5zfmv9kM/NsG4m8zA99hBr7VDHyvRX2aGMHXE7iLFv6JQvGZzWc2Wju46uDp6fua7Wum1cdNC39m6J/uZvzEQws/i5IQKn'
            'XT4nsawLEaLLypHq4yCRfI9TLSn61fpZ7PSLj10OI3M1O/Ui18iULhYuNio20XKh5/1g6sfZqb0cdbLzcFoc268vqYwUdk3g5z/GcKBSNmxMiq'
            'na4fQCb6AVr7uuqiIVxkBs4Gx3fRE44/B5dr0cziU3IGrIPEMrEe7mHEh32jBvo/N4QjLfyJGfhJQ7k2ZvS3hScxgV8xhQ/2+V6Iz8EvmsJ3NI'
            'LbmeFvb1YfS3Ym9qGgvKbsj7AVTMDlANfZh32hAu76nFIwiBHAoVy/wiTRJFyuQEb1C/o8N9SHBzeQy9OHxTeod57+xnCWj7GfmCivh1F5GTP1'
            'Ym0GLjMD5/ktxSDGvD8b2dnQPykz/iw3I1dhBl8i5M/Zx8GMXAczfOyJfzoa+aejGX3s67WPIX9bi+VqbgSnzMBZfIUZfIW59mLQP0xknNFEhv'
            '/ePh89b3bk1iSmM5pkAJeTftOO6/eIDG4QKyYwdTpxPW4obEyvqJdeYpHesV56K4v0TvXSSy3SO9dLz1ikb1IvvcwivUs99DUJlu3vWi+9Zfu7'
            '1Utv2f7u9dJbtr9HvfSW7e9ZL71l+zc1oEdG9CGhlu3vVS+9Zfsr66W3bP9m9dJbtr+qXnrL9m9eL71l+3vXQ08eNBbofeqlt2x/33rpLdu/Rb'
            '30lu3fsl56y/ZvVS+9Zfv76ejxeHgJstLw6TFMc+QHjZ5+toC+NbGQlv7lJGRE//TpUx29lIOVlJRotK9KGD6Me5Ui48O4VynWfBgXjPVpo9PH'
            'lD0wfVVVlZE+kZGRRvoQmEAfAhPoQ2A6ffwE+rQlvZKdYXmIJOO68DeoC5j1GNny8GN+XQjpAwx8QcQrO/NGbSmwHnpNpGX6dvXQC/tSoa2CdL'
            'YS0hvXc7CB30VGjjX225qK/0a/E5Y9xKDu+O1AK0dTSlmou1DDdqg2rnvN/SU8+vEC+jDS0+lwNTU6em3Zt2zZoqNn+DDOHjI+jLOHNR/G2cO4'
            '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'
            'uZ7tPEj0SUnx80fb/nE53Cb/+fXhtbsvJDWz2dj1W81Ljw+Cfo12Dthtdef5YY+9w/Nzi++7DJ9SOHGM3fU1j/64FwBYwS3uFtkNyw3bseujcw'
            'vKZJXSxPG7+jb7erv1L72ck2MGD3tvlqzXnZXv9jqZeliKkqJm+cZ3eevHJ2JJ0qFhsUcXOj0uiw12Hv7Pfi1HfrNzgFfyjpv7Xp79o72X4usp'
            '81LWj6ecNkeseD7e+4bvfC9N6JN7nmUXNg7//O1JE14+23Em48fEZa/71awfNnis1O/jhF07Ij94VVc3YnzJq5cHL/9y/Xb/jbemzSz5/ffP8j'
            '/Q1A57lHLoeNLu1/86tPizdsNL6s4ti+wybvz12sycAz189x/YNaXP7j/9P5R0fF4bvG/hIb/u322JCn4+9ptHxy/S1yp87h14mNppqsNbq2fb'
            'jM/+18VbHWe/SHA8UrOj9jtaGdy9zn2c1Y3ti47PeJK5oPujoy9qvrva49eL4eNcqwZO/nOr7e1Pvxk6NjXn1O4efdv0ndrfv0vx3N7BY9c9Uj'
            'QfOHRuXHXFSKe7Xbyvve39Q9ns7y+2WVF1iopXtRvj2jVuW5PFldOvvV25YUDdk80fTz1C95W+UKwc6Ja/vCJ25vE7TIuzts+bl2/+6HbBDyKn'
            'C66OIV4px3Z/MGNawaUrdzYN97m7o2vKlazIL3//rnth/MrAZdNnBDtdSj2TN7u8ZppXeVjE5mWzWn/i9/RR8N3JzYL/lPW9UCb9JC+hLmby+q'
            'JlAWKHqKG9ex6n+45LvzLv+JCFg//otOSM7MC76qg/A+L7xP1j5d6Nfu/XXu879sjODd3PXJ2zft3QpBN1HUa/3V/a1mOvrK5Z8iPloqq6oM7+'
            '9z+/P6WgRJ6nKWl3ZfHSO2s/u18VPWX82i7Ze9+50KkurfbwpGg/r2NvHZoe/fiq5FlVAZpyLLHZu6MnlB0f9XzN0rSF1Qe6Nc3ynBv64q15vw'
            'V1d895kr230HHmgWLf3bNlF+vup6zKn7Zq6+0Z015M2Dawf8aZoZ3F5cd/e6+y6fSt/6w5deL8U9uBOy/k+EwaOFyetN21eUpC+vyLY8syA6wG'
            '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'
        ),
    },
    {
        "code": 'PCGD_THCS_M5_2025',
        "level": 'THCS',
        "title": 'THCS-M5 – Thống kê đội ngũ giáo viên',
        "source_name": '4. PCGD_THCS_M5_2025_phường_Thành Vinh.xls',
        "target_name": 'PCGD_2025_THCS_M5.xls',
        "sha256": '026a412dbdd94d8ec07f73322e64df2273f9a8af4f8292868b0f9d5bbb75a11f',
        "size": 41472,
        "payload_b64": (
            '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'
        ),
    },
    {
        "code": 'PCGD_THCS_CSVC_2025',
        "level": 'THCS',
        "title": 'THCS-CSVC – Thống kê cơ sở vật chất',
        "source_name": '5. PCGD_THCS_2025_CSVC_phuong_Thành Vinh.xls',
        "target_name": 'PCGD_2025_THCS_CSVC.xls',
        "sha256": '03f7e5c43717542de2461913eee5b54d5b87bd97d49da823065acda2c6809f77',
        "size": 37888,
        "payload_b64": (
            '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'
            'wP+/AJYnCw0='
        ),
    },
    {
        "code": 'PCGD_XMC_3_2025',
        "level": 'XOA_MU_CHU',
        "title": 'XMC-3 – Tổng hợp kết quả xóa mù chữ',
        "source_name": '1. PCGD_XMC_3_phường_Thành Vinh.xls',
        "target_name": 'PCGD_2025_XMC_3.xls',
        "sha256": 'd04437ee3e8666c1a508e95fb42adb3b453984f2b74c03343576ca57189c4ba9',
        "size": 43008,
        "payload_b64": (
            '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'
            'D+PSzC/1/vSubM'
        ),
    },
    {
        "code": 'PCGD_CMC_2_2025',
        "level": 'XOA_MU_CHU',
        "title": 'CMC-2 – Thống kê số người mù chữ',
        "source_name": '2. PCGD_CMC_2_phường_Thành Vinh.xls',
        "target_name": 'PCGD_2025_CMC_2.xls',
        "sha256": 'd83e06ebdc96c24d18295713b17645df586c486f4d245d1c55b807a55c8540b7',
        "size": 51712,
        "payload_b64": (
            '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'
            'R7jvoPNeD/P2zYS4M='
        ),
    },
    {
        "code": 'PCGD_CMC_1_2025',
        "level": 'XOA_MU_CHU',
        "title": 'CMC-1 – Tổng hợp chống mù chữ',
        "source_name": '3. PCGD_CMC_1_phường_Thành Vinh.xls',
        "target_name": 'PCGD_2025_CMC_1.xls',
        "sha256": '108339cb12f38b6a37cd80f647731be690a8a19bf1e61f1b043bee1754317694',
        "size": 35328,
        "payload_b64": (
            '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'
            's27tWBB0fNO5Ueq7UV0+tt6eeHHmL53lb684zEzfFnyz5ONJNh0HbyqsdfSwOGi2zvZlaWpw5O2U3nO8l11s9+7mES9KfVNcKm/PtUsbNLDzi5'
            'KywB+/9gkq7/Zw/tnJNpsSyq3vTZiy7Atvj0q/FYdKnvucT815L22l17sOLhWd7lafu+3iyPS83yz88fSJK0pnbR71Qvbu9SO/W5xeevTLdPkH'
            'XodXLn6Jep5MPXx22auwfXcPxq7PLh88IG9Zp74Tbj0459bs/RFDZ/7S7rzTh+vsz9++97utuc3S/jFfdklgvLY9zeo3ND5xwvatT1yt8hdlZO'
            '5b6f1qzu7kilmyinfSJ1YsnpQXME+Zuek1Olb49TGbPl+s6Gr3eMww2o7ZP00Z2n19U8vqLPmrt3Z08to7ctkR5+eTPhx7aZrL4Qt3TrStyB90'
            '54TcbeoIt85PN1YpRn/V6erXarvl7aabn11SmHSueFrIun9vdV4V9+D8L2mrjlLuPtu+ndN5auGP+67+sljzYcWFsbGD0s/e61uwYXu3irgnvS'
            '7e7jVjn+0rz4JRb+W7e2Zt9t3W+snGbYcfj/xDU9pv3/MhJx7nXhvfNPb4XLv482mhkR9vH5QeuuhgaPWNzSM6xT24HPlx/rPPhqcGPKt0+/T3'
            '5PRSedvLc+N2b77/0yHH4T6nfMt3ba06be4ccqfzpUmrK7+cYz3Fq+vQqIyflixMrOqjONNtedmcBUMm/LvvpLj3jxQs7h73XofomtSW2xIjMk'
            'MX7xu/vFel0+AtD786mno8z+NR4JPpZQuPW1tkR646t3RG+/F7Ns/9ZPiRoVEKi9K9o7J6jtt9aMfV0EEHztCbc4f8s1Ohnerqk7cPy73V8rOt'
            '8r/sdDF9yzaX2zVfHOuevityYxOqeliot/pVSdrYwVPajj8SdTXkzoj3yu0LYyxGu926M0epKv/u8pa+ocn39p7Y+SDkwKPA3o/eqPcXu9fc9B'
            'w2tk/mjG+KC9fsWRGY//TDa28u9nVLzpu98EjCO3PCp77vMLvZ2o+OKG3uHLjU4+VP75zsmtfl0Pxg3zNX78Q9/uSG2tth3AcLNz/fdm84CPjC'
            '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'
            'ta/YXzj+Pp/x9KAlkR'
        ),
    },
    {
        "code": 'PCGD_XMC_4_2025',
        "level": 'XOA_MU_CHU',
        "title": 'XMC-4 – Thống kê đạt chuẩn xóa mù chữ',
        "source_name": '4. TK_DATCHUAN_XMC_4_phường_Thành Vinh.xls',
        "target_name": 'PCGD_2025_XMC_4.xls',
        "sha256": '498ff35e84810a789f93a7d1f05214aaebe2b4f602858ffdd93f0c01b9c65a51',
        "size": 34304,
        "payload_b64": (
            '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'
        ),
    },
]

NEW_REPORT_CODES = [item["code"] for item in TEMPLATE_FILES]
EXISTING_REPORT_CODES = [
    "TONG_HOP_DIEU_TRA",
    "PCGDMN_MAU_2025",
    "BIEN_DONG_THEO_DOI",
    "DOI_CHIEU_HOC_SINH",
    "TIEN_DO_CHOT",
]
REQUIRED_MENU_TEXTS = [
    "PHỔ CẬP GIÁO DỤC VÀ XÓA MÙ CHỮ",
    "5.2. Báo cáo Mầm non",
    "5.3. Báo cáo Tiểu học",
    "5.4. Báo cáo THCS",
    "5.5. Báo cáo Xóa mù chữ",
    "TH-M1 – Phổ cập giáo dục Tiểu học",
    "TH-02 – Kết quả PCGD Tiểu học",
    "TH-01-GV – Đội ngũ giáo viên",
    "TH-01-CSVC – Cơ sở vật chất",
    "THCS-M1 – Phổ cập giáo dục THCS",
    "THCS-M2 – Tiêu chuẩn PCGD THCS",
    "THCS-TK – Thống kê kết quả",
    "THCS-M5 – Đội ngũ giáo viên",
    "THCS-CSVC – Cơ sở vật chất",
    "XMC-3 – Tổng hợp kết quả xóa mù chữ",
    "CMC-2 – Thống kê số người mù chữ",
    "CMC-1 – Tổng hợp chống mù chữ",
    "XMC-4 – Thống kê đạt chuẩn xóa mù chữ",
]


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_with_parent(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def menu_template() -> str:
    return zlib.decompress(base64.b64decode(MENU_TEMPLATE_B64)).decode("utf-8")


def decoded_template(item: dict) -> bytes:
    return zlib.decompress(base64.b64decode(item["payload_b64"]))


def strip_new_report_block(text: str) -> str:
    pattern = re.compile(
        r"\n?\s*" + re.escape(REPORT_MARKER_START) + r".*?" + re.escape(REPORT_MARKER_END) + r"\s*\n?",
        flags=re.DOTALL,
    )
    return pattern.sub("\n", text, count=1)


def insert_report_types(text: str) -> str:
    base = strip_new_report_block(text)
    report_pos = base.find("REPORT_TYPES:")
    status_pos = base.find("\nSTATUS_LABELS =", report_pos)
    if report_pos < 0 or status_pos < 0:
        raise RuntimeError("Khong tim thay khoi REPORT_TYPES/STATUS_LABELS trong report_center.py")
    close_pos = base.rfind("\n}", report_pos, status_pos)
    if close_pos < 0:
        raise RuntimeError("Khong tim thay dau dong cua REPORT_TYPES.")
    return base[:close_pos] + REPORT_TYPES_BLOCK + base[close_pos:]


def route_signatures(routers_dir: Path) -> list[tuple[str, str, str, str]]:
    result = []
    for path in sorted(routers_dir.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except SyntaxError as exc:
            raise RuntimeError(f"Loi cu phap router truoc/sau cai dat: {path.name}: {exc}") from exc
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                    continue
                owner = deco.func.value
                if not isinstance(owner, ast.Name) or owner.id != "router":
                    continue
                method = deco.func.attr.lower()
                if method not in {"get", "post", "put", "delete", "patch", "options", "head"}:
                    continue
                route_path = ""
                if deco.args and isinstance(deco.args[0], ast.Constant) and isinstance(deco.args[0].value, str):
                    route_path = deco.args[0].value
                result.append((path.name, method, route_path, node.name))
    return sorted(result)


def tree_hash_excluding_report_center(routers_dir: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(routers_dir.glob("*.py")):
        if path.name == "report_center.py":
            continue
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        h.update((sha256(path) or "").encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def inject_include(text: str) -> tuple[str, bool]:
    if INCLUDE_MARKER in text:
        return text, False
    match = re.search(r"<body\b[^>]*>", text, flags=re.IGNORECASE)
    if match is None:
        raise RuntimeError("Khong tim thay the <body> trong template.")
    pos = match.end()
    return text[:pos] + "\n" + INCLUDE_MARKER + "\n" + text[pos:], True


def render_role_checks(template_text: str) -> None:
    from jinja2 import Environment
    env = Environment()
    template = env.from_string(template_text)
    roles = ["ADMIN", "XA", "TRUONG", "GIAO_VIEN"]
    for role in roles:
        user = {"full_name":"Nguoi dung kiem tra", "role_code":role, "role_name":role, "unit_name":"Don vi kiem tra"}
        request = SimpleNamespace(scope={"auth_user":user}, url=SimpleNamespace(path="/bao-cao"))
        rendered = template.render(nguoi_dung=user, request=request)
        for required in ["5.2. Báo cáo Mầm non", "5.3. Báo cáo Tiểu học", "5.4. Báo cáo THCS", "5.5. Báo cáo Xóa mù chữ"]:
            if required not in rendered:
                raise RuntimeError(f"Menu cap {role} thieu: {required}")
    admin = template.render(nguoi_dung={"full_name":"A","role_code":"ADMIN","role_name":"ADMIN","unit_name":"Toan tinh"}, request=SimpleNamespace(scope={"auth_user":{"full_name":"A","role_code":"ADMIN","role_name":"ADMIN","unit_name":"Toan tinh"}}, url=SimpleNamespace(path="/bao-cao")))
    if "5.6. Giám sát cấp tỉnh" not in admin:
        raise RuntimeError("Menu cap So thieu 5.6 Giam sat cap tinh.")


def main() -> int:
    project = PROJECT if len(sys.argv) < 2 else Path(sys.argv[1]).expanduser().resolve()
    templates_dir = project / "app" / "templates"
    partial = project / PARTIAL_REL
    report_router = project / REPORT_ROUTER_REL
    main_py = project / MAIN_REL
    db_path = project / DB_REL
    routers_dir = project / ROUTERS_REL
    report_template_root = project / REPORT_TEMPLATE_ROOT_REL

    print("\n" + "="*78)
    print("PCGD & XMC V1.5 - MO RONG MENU BAO CAO MAM NON / TIEU HOC / THCS / XOA MU CHU")
    print("GIU NGUYEN CHUC NANG CU - KHONG DOI ROUTE - KHONG DOI DU LIEU - KHONG DOI LUONG NGHIEP VU")
    print("="*78)

    for required in [templates_dir, report_router, main_py, routers_dir]:
        if not required.exists():
            raise FileNotFoundError(f"Khong tim thay: {required}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = project / "exports" / f"backup_pcgd_xmc_v1_5_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    main_hash_before = sha256(main_py)
    db_hash_before = sha256(db_path)
    route_before = route_signatures(routers_dir)
    other_routers_hash_before = tree_hash_excluding_report_center(routers_dir)
    report_before = report_router.read_text(encoding="utf-8-sig")
    report_base_before = strip_new_report_block(report_before)

    html_files = sorted(templates_dir.rglob("*.html"))
    targets=[]
    for p in html_files:
        rel=p.relative_to(templates_dir).as_posix()
        if rel in EXCLUDED_TEMPLATES or rel.startswith("partials/"):
            continue
        targets.append(p)

    files_to_backup=[report_router]
    if partial.exists(): files_to_backup.append(partial)
    for p in targets:
        text=p.read_text(encoding="utf-8-sig")
        if INCLUDE_MARKER not in text:
            files_to_backup.append(p)
    if report_template_root.exists():
        for p in report_template_root.rglob("*"):
            if p.is_file(): files_to_backup.append(p)

    backed=[]
    for src in files_to_backup:
        rel=src.relative_to(project)
        copy_with_parent(src, backup/rel)
        backed.append(rel.as_posix())

    changed=[]
    created=[]

    try:
        print("\nBUOC 1 - CAP NHAT MENU V1.5 VA NHAN DIEN PCGD & XMC")
        menu_text=menu_template()
        partial.parent.mkdir(parents=True, exist_ok=True)
        if not partial.exists(): created.append(PARTIAL_REL.as_posix())
        partial.write_text(menu_text, encoding="utf-8")
        changed.append(PARTIAL_REL.as_posix())
        print("Da cap nhat menu dung chung cho So / Xa / Truong / Giao vien.")

        print("\nBUOC 2 - DAM BAO MENU CO TREN CAC GIAO DIEN CON")
        injected=0
        for p in targets:
            text=p.read_text(encoding="utf-8-sig")
            new_text,did=inject_include(text)
            if did:
                p.write_text(new_text, encoding="utf-8")
                changed.append(p.relative_to(project).as_posix())
                injected += 1
        print(f"Da gan them menu vao {injected} giao dien con chua co menu.")

        print("\nBUOC 3 - DANG KY 13 BIEU MOI TRONG TRUNG TAM BAO CAO HIEN CO")
        report_after=insert_report_types(report_before)
        report_router.write_text(report_after, encoding="utf-8")
        changed.append(REPORT_ROUTER_REL.as_posix())
        print("Chi bo sung REPORT_TYPES; khong them, xoa hoac doi route.")

        print("\nBUOC 4 - LUU NGUYEN TRANG 13 MAU EXCEL GOC")
        report_template_root.mkdir(parents=True, exist_ok=True)
        catalog=[]
        for item in TEMPLATE_FILES:
            level_dir = {"TIEU_HOC":"tieu_hoc", "THCS":"thcs", "XOA_MU_CHU":"xoa_mu_chu"}[item["level"]]
            dest = report_template_root / level_dir / item["target_name"]
            existed=dest.exists()
            if existed and dest not in files_to_backup:
                copy_with_parent(dest, backup/dest.relative_to(project))
                backed.append(dest.relative_to(project).as_posix())
            raw=decoded_template(item)
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise RuntimeError(f"Sai ma bam payload mau: {item['source_name']}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            rel=dest.relative_to(project).as_posix()
            changed.append(rel)
            if not existed: created.append(rel)
            catalog.append({k:item[k] for k in ["code","level","title","source_name","target_name","sha256","size"]})
            print(f"Da luu: {item['code']}")

        catalog_path=report_template_root/"DANH_MUC_13_BIEU_2025.json"
        catalog_existed=catalog_path.exists()
        catalog_path.write_text(json.dumps({"version":VERSION,"templates":catalog}, ensure_ascii=False, indent=2), encoding="utf-8")
        changed.append(catalog_path.relative_to(project).as_posix())
        if not catalog_existed: created.append(catalog_path.relative_to(project).as_posix())

        note_path=report_template_root/"README_V1_5.txt"
        note_existed=note_path.exists()
        note_path.write_text(
            "PCGD & XMC V1.5\n"
            "- 13 tep .xls trong thu muc nay la ban sao NGUYEN TRANG cua cac mau nguoi dung cung cap.\n"
            "- V1.5 chi dang ky danh muc va menu bao cao.\n"
            "- Chua tu dong dien so lieu vao 13 bieu moi.\n"
            "- Khong thay doi route cu, co so du lieu cu hay luong nghiep vu da chot.\n",
            encoding="utf-8",
        )
        changed.append(note_path.relative_to(project).as_posix())
        if not note_existed: created.append(note_path.relative_to(project).as_posix())

        print("\nBUOC 5 - KIEM TRA AN TOAN")
        from jinja2 import Environment, FileSystemLoader
        env=Environment(loader=FileSystemLoader(str(templates_dir)))
        env.get_template("partials/dropdown_menu_v1.html")
        render_role_checks(menu_text)
        for item in REQUIRED_MENU_TEXTS:
            if item not in menu_text:
                raise RuntimeError(f"Menu V1.5 thieu: {item}")

        for p in targets:
            rel=p.relative_to(templates_dir).as_posix()
            text=p.read_text(encoding="utf-8-sig")
            env.parse(text)
            if INCLUDE_MARKER not in text:
                raise RuntimeError(f"Giao dien chua co menu: {rel}")

        subprocess.run([str(project/".venv/Scripts/python.exe"), "-m", "py_compile", str(report_router)], cwd=project, check=True) if (project/".venv/Scripts/python.exe").exists() else compile(report_router.read_text(encoding="utf-8-sig"), str(report_router), "exec")

        report_after_now=report_router.read_text(encoding="utf-8-sig")
        for code in EXISTING_REPORT_CODES + NEW_REPORT_CODES:
            if f'"{code}"' not in report_after_now:
                raise RuntimeError(f"REPORT_TYPES thieu: {code}")

        # Sau khi bo khoi V1.5, phan con lai cua report_center.py phai giong nguyen ban truoc cai dat.
        if strip_new_report_block(report_after_now) != report_base_before:
            raise RuntimeError("report_center.py bi thay doi ngoai khoi REPORT_TYPES V1.5.")

        if route_signatures(routers_dir) != route_before:
            raise RuntimeError("Phat hien route bi thay doi - tu choi cai dat.")
        if tree_hash_excluding_report_center(routers_dir) != other_routers_hash_before:
            raise RuntimeError("Router khac report_center.py bi thay doi.")
        if sha256(main_py) != main_hash_before:
            raise RuntimeError("app/main.py bi thay doi.")
        if sha256(db_path) != db_hash_before:
            raise RuntimeError("data/phocap.db bi thay doi.")

        for item in TEMPLATE_FILES:
            level_dir={"TIEU_HOC":"tieu_hoc", "THCS":"thcs", "XOA_MU_CHU":"xoa_mu_chu"}[item["level"]]
            dest=report_template_root/level_dir/item["target_name"]
            if sha256(dest) != item["sha256"]:
                raise RuntimeError(f"Mau Excel khong con nguyen trang: {item['code']}")

        manifest={
            "version":VERSION,
            "installed_at":datetime.now().isoformat(timespec="seconds"),
            "project":str(project),
            "backup":str(backup),
            "changed_files":sorted(set(changed)),
            "created_files":sorted(set(created)),
            "backed_up":sorted(set(backed)),
            "new_report_codes":NEW_REPORT_CODES,
            "route_count":len(route_before),
            "main_sha256_before":main_hash_before,
            "main_sha256_after":sha256(main_py),
            "db_sha256_before":db_hash_before,
            "db_sha256_after":sha256(db_path),
        }
        (backup/"PCGD_XMC_V1_5_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (project/"exports"/"pcgd_xmc_v1_5_backup_moi_nhat.txt").write_text(str(backup), encoding="utf-8")

        print("\nMenu cap SO: DAT")
        print("Menu cap XA: DAT")
        print("Menu cap TRUONG: DAT")
        print("Menu cap GIAO VIEN: DAT")
        print("13 mau Excel goc: DA LUU NGUYEN TRANG")
        print("app/main.py: KHONG DOI")
        print("Route: KHONG DOI")
        print("data/phocap.db: KHONG DOI")
        print("Luong nghiep vu cu: KHONG DOI")
        print("Chuc nang cu: GIU NGUYEN")
        print("\n" + "="*78)
        print("NANG CAP PCGD & XMC V1.5 THANH CONG")
        print("="*78)
        print(f"Ban sao an toan: {backup}")
        return 0

    except Exception:
        print("\nCAI DAT KHONG THANH CONG - DANG TU DONG KHOI PHUC...")
        traceback.print_exc()
        for rel in sorted(set(changed), reverse=True):
            current=project/rel
            saved=backup/rel
            if saved.exists():
                copy_with_parent(saved,current)
            elif rel in created and current.exists():
                if current.is_file(): current.unlink()
        print("DA KHOI PHUC CAC TEP BI TAC DONG.")
        print("app/main.py va data/phocap.db KHONG BI GHI DE.")
        print(f"Ban sao an toan: {backup}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
