from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, build_opener, HTTPRedirectHandler

from itsdangerous import TimestampSigner

PROJECT = Path(r"C:\PhoCap")
TARGET_USER_ID = 13359
TARGET_USERNAME = "xa_17827"
TARGET_BATCH_CODE = "DT-17827-20262027-001"
TARGET_URL = (
    "http://127.0.0.1/dieu-tra"
    "?school_year_id=2&commune_id=114&survey_status="
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get_session_config():
    import app.main as main_mod

    app = main_mod.app

    secret = getattr(main_mod, "SESSION_SECRET_KEY", None)
    cookie_name = None
    max_age = None

    for mw in getattr(app, "user_middleware", []):
        cls = getattr(mw, "cls", None)
        kwargs = dict(getattr(mw, "kwargs", {}) or {})

        if getattr(cls, "__name__", "") == "SessionMiddleware":
            if secret is None:
                secret = kwargs.get("secret_key")
            cookie_name = kwargs.get(
                "session_cookie",
                cookie_name,
            )
            max_age = kwargs.get("max_age", max_age)

    if not secret:
        raise RuntimeError(
            "Không lấy được SESSION_SECRET_KEY/secret_key "
            "từ app.main."
        )

    if not cookie_name:
        cookie_name = "phocap_session"

    return app, str(secret), str(cookie_name), max_age


def make_cookie(secret: str) -> str:
    data = base64.b64encode(
        json.dumps({"user_id": TARGET_USER_ID}).encode("utf-8")
    )
    signer = TimestampSigner(secret)
    return signer.sign(data).decode("utf-8")


def summarize_html(label: str, status: int, headers, body: str):
    print()
    print("-" * 118)
    print(label)
    print("-" * 118)
    print("HTTP status       =", status)

    location = None
    try:
        location = headers.get("Location")
    except Exception:
        pass

    print("Location          =", location)
    print("HTML length       =", len(body))
    print(
        "Có batch code?    =",
        TARGET_BATCH_CODE in body,
    )
    print(
        "Có '0 đợt'?       =",
        "0 đợt" in body,
    )
    print(
        "Có '1 đợt'?       =",
        "1 đợt" in body,
    )
    print(
        "Có 'Xã Nghi Lộc'? =",
        "Xã Nghi Lộc" in body,
    )

    count_matches = re.findall(
        r'class=["\'][^"\']*count-badge[^"\']*["\'][^>]*>\s*([^<]+)',
        body,
        flags=re.I,
    )
    if count_matches:
        print(
            "Count badge       =",
            [x.strip() for x in count_matches[:5]],
        )

    if TARGET_BATCH_CODE in body:
        pos = body.find(TARGET_BATCH_CODE)
        start = max(0, pos - 180)
        end = min(len(body), pos + 300)
        snippet = re.sub(r"\s+", " ", body[start:end])
        print("Đoạn chứa batch   =", snippet)

    return {
        "status": status,
        "location": location,
        "has_batch": TARGET_BATCH_CODE in body,
        "has_zero": "0 đợt" in body,
        "has_one": "1 đợt" in body,
        "body": body,
    }


def live_request(cookie_name: str, cookie_value: str):
    opener = build_opener(NoRedirect())

    req = UrlRequest(
        TARGET_URL,
        headers={
            "Cookie": f"{cookie_name}={cookie_value}",
            "User-Agent": "PhoCap-Diagnostic-V7",
            "Accept": "text/html",
        },
        method="GET",
    )

    try:
        with opener.open(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, resp.headers, body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, exc.headers, body


def testclient_request(app, cookie_name: str, cookie_value: str):
    try:
        from fastapi.testclient import TestClient
    except Exception as exc:
        return None, None, f"KHÔNG IMPORT ĐƯỢC TestClient: {exc!r}"

    try:
        client = TestClient(
            app,
            follow_redirects=False,
        )
        response = client.get(
            "/dieu-tra",
            params={
                "school_year_id": "2",
                "commune_id": "114",
                "survey_status": "",
            },
            cookies={
                cookie_name: cookie_value,
            },
        )
        return (
            response.status_code,
            response.headers,
            response.text,
        )
    except Exception as exc:
        return None, None, f"TESTCLIENT ERROR: {exc!r}"


def main() -> int:
    print("=" * 118)
    print("KIỂM TRA HTTP THỰC TẾ XÃ NGHI LỘC V7")
    print("CHỈ ĐỌC - KHÔNG SỬA SOURCE - KHÔNG SỬA DATABASE")
    print("=" * 118)

    print()
    print("Mục tiêu:")
    print(" - Dùng đúng user_id=13359 / xa_17827.")
    print(" - Tạo session cookie hợp lệ bằng secret của chính app.")
    print(" - Gọi Uvicorn thật tại 127.0.0.1.")
    print(" - So sánh với TestClient của cùng app.")
    print(" - Không in secret/cookie ra màn hình.")

    try:
        app, secret, cookie_name, max_age = get_session_config()
    except Exception as exc:
        print()
        print("KHÔNG LẤY ĐƯỢC CẤU HÌNH SESSION:", repr(exc))
        return 1

    cookie_value = make_cookie(secret)

    print()
    print("1. CẤU HÌNH SESSION")
    print("-" * 118)
    print("cookie name =", cookie_name)
    print("max_age     =", max_age)
    print("user_id     =", TARGET_USER_ID)
    print("username    =", TARGET_USERNAME)
    print("secret      = (đã ẩn)")
    print("cookie      = (đã ẩn)")

    print()
    print("2. GỌI UVICORN THẬT 127.0.0.1")
    print("-" * 118)

    live_result = None
    try:
        status, headers, body = live_request(
            cookie_name,
            cookie_value,
        )
        live_result = summarize_html(
            "KẾT QUẢ UVICORN THẬT",
            status,
            headers,
            body,
        )
    except URLError as exc:
        print("KHÔNG KẾT NỐI ĐƯỢC UVICORN:", repr(exc))
        print(
            "Hãy để Uvicorn chạy rồi chạy lại V7. "
            "Không cần dừng server cho kiểm tra này."
        )
    except Exception as exc:
        print("LỖI REQUEST UVICORN:", repr(exc))

    print()
    print("3. GỌI CÙNG APP BẰNG TESTCLIENT")
    print("-" * 118)

    tc_status, tc_headers, tc_body = testclient_request(
        app,
        cookie_name,
        cookie_value,
    )

    tc_result = None
    if tc_status is None:
        print(tc_body)
    else:
        tc_result = summarize_html(
            "KẾT QUẢ TESTCLIENT",
            tc_status,
            tc_headers,
            tc_body,
        )

    print()
    print("4. KẾT LUẬN TỰ ĐỘNG")
    print("-" * 118)

    if live_result is None:
        print(
            "Chưa kiểm tra được tiến trình Uvicorn thật. "
            "Cần để server chạy và chạy lại V7."
        )
    elif live_result["status"] in (301, 302, 303, 307, 308):
        print(
            "Uvicorn thật đang chuyển hướng request."
        )
        print(
            "Location =",
            live_result["location"],
        )
        print(
            "=> Cần xử lý session/middleware/route chuyển hướng."
        )
    elif live_result["has_batch"]:
        print(
            "UVICORN THẬT trả đúng batch Nghi Lộc."
        )
        print(
            "=> Nếu Chrome vẫn hiện 0, vấn đề nằm ở "
            "cookie/session của trình duyệt hoặc Chrome đang "
            "đi vào tiến trình/host khác."
        )
    elif live_result["status"] == 200 and live_result["has_zero"]:
        print(
            "UVICORN THẬT với session xa_17827 vẫn trả 0 đợt."
        )
        if tc_result and tc_result["has_batch"]:
            print(
                "Nhưng TestClient trả đúng batch."
            )
            print(
                "=> Tiến trình Uvicorn đang chạy khác code/process "
                "so với source vừa import."
            )
        elif tc_result and tc_result["has_zero"]:
            print(
                "TestClient cũng trả 0 đợt."
            )
            print(
                "=> Lỗi nằm trong luồng HTTP middleware/request "
                "trước khi đến logic SQL đã kiểm tra."
            )
        else:
            print(
                "=> Dùng kết quả TestClient ở trên để chốt bước sửa."
            )
    else:
        print(
            "Kết quả HTTP không thuộc các mẫu dự kiến; "
            "xem status/Location/HTML ở trên."
        )

    print()
    print("Hãy COPY TOÀN BỘ kết quả V7 gửi lại ChatGPT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
