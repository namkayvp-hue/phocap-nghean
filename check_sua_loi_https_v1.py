"""Kiem tra sua loi vo giao dien khi chay sau proxy HTTPS (cong 443).

Loi goc: template dung url_for('static', ...) sinh URL tuyet doi theo
request.url.scheme. Uvicorn chi tin X-Forwarded-Proto khi IP goi den nam
trong danh sach forwarded-allow-ips (mac dinh chi 127.0.0.1), nen khi
chay trong Docker sau Nginx Proxy Manager, scheme van la http. Trang
HTTPS nhan link http:// -> trinh duyet chan mixed content -> mat CSS.

Chay: "C:\\PhoCap\\.venv\\Scripts\\python.exe" check_sua_loi_https_v1.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

PROJECT = Path.cwd().resolve()
sys.path.insert(0, str(PROJECT))

from app.main import app

TEMPLATES = PROJECT / "app" / "templates"


# --- 1. Template khong duoc sinh URL tuyet doi cho tep tinh ---------------

mau_url_for_static = re.compile(r"url_for\(\s*['\"]static['\"]")

template_loi = [
    str(tep.relative_to(PROJECT))
    for tep in TEMPLATES.rglob("*.html")
    if mau_url_for_static.search(tep.read_text(encoding="utf-8"))
]

if template_loi:
    raise AssertionError(
        "Cac template sau con dung url_for('static', ...) nen sinh URL "
        "tuyet doi http:// va vo giao dien khi chay HTTPS:\n  "
        + "\n  ".join(template_loi)
    )

print(f"DA KIEM TRA {len(list(TEMPLATES.rglob('*.html')))} TEMPLATE: "
      "khong con url_for('static')")


# --- 2. Trang thuc te khong duoc chua URL http:// khi dung sau proxy -----

# Bao ProxyHeadersMiddleware tin moi IP, giong cau hinh
# FORWARDED_ALLOW_IPS trong docker-compose.yml.
client = TestClient(ProxyHeadersMiddleware(app, trusted_hosts="*"))

cac_trang = ["/dang-nhap", "/"]

for duong_dan in cac_trang:
    phan_hoi = client.get(
        duong_dan,
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": "203.0.113.9",
        },
        follow_redirects=True,
    )
    if phan_hoi.status_code != 200:
        raise AssertionError(
            f"Trang {duong_dan} tra ve {phan_hoi.status_code}: "
            f"{phan_hoi.text[:300]}"
        )

    url_http = re.findall(
        r"(?:href|src|action)\s*=\s*[\"']http://[^\"']+",
        phan_hoi.text,
    )
    if url_http:
        raise AssertionError(
            f"Trang {duong_dan} con URL http:// se bi chan khi chay HTTPS:\n  "
            + "\n  ".join(url_http)
        )

    if "/static/css/style.css" not in phan_hoi.text:
        raise AssertionError(
            f"Trang {duong_dan} khong nap duoc bang kieu /static/css/style.css"
        )

print(f"DA KIEM TRA {len(cac_trang)} TRANG SAU PROXY HTTPS: "
      "khong con URL http://")


# --- 3. docker-compose.yml phai tin proxy de scheme la https -------------

noi_dung_compose = (PROJECT / "docker-compose.yml").read_text(encoding="utf-8")

if "FORWARDED_ALLOW_IPS" not in noi_dung_compose:
    raise AssertionError(
        "docker-compose.yml chua khai bao FORWARDED_ALLOW_IPS, uvicorn se bo "
        "qua X-Forwarded-Proto cua proxy va giu nguyen scheme http"
    )

print("DA KIEM TRA docker-compose.yml: co FORWARDED_ALLOW_IPS")
print("KIEM TRA SUA LOI HTTPS V1 THANH CONG")
