# -*- coding: utf-8 -*-
r"""
V9.4.2 CHÍNH THỨC - KHÓA ĐÚNG XÃ/PHƯỜNG CỦA QĐ 3805
=======================================================

Kết quả DRY-RUN đã xác nhận:
- 6 plan QĐ 3805: commune_id = 114
- Tất cả source/target thật trong schools: commune_id = 114
- 114 = Xã Nghi Lộc
- 8 = Xã Tiền Phong, không thuộc QĐ 3805
- 0 mismatch giữa plan và database

Bản này an toàn hơn bản vá link cũ:
1. Backend trang /phuong-an tự suy ra commune_id duy nhất từ các plan QĐ 3805.
2. Nếu URL thiếu/sai commune_id, backend 303 về đúng commune_id.
3. Ô Xã/phường ở trang QĐ 3805 trở thành READ-ONLY.
4. Không thể gõ/chọn xã khác trên trang này.
5. Không sửa database.
6. Không sửa school_merger_approved_plans.json.
7. Kiểm tra SHA256 đúng nền V9.4.1 trước khi ghi.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import shutil
import sys
import zlib
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
ROUTER = ROOT / "app" / "routers" / "school_merger.py"
MAIN_TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger.html"
PLANS_TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger_plans.html"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
EXPORTS = ROOT / "exports"

EXPECTED = {
    str(ROUTER): '71e4fe426a72e9f5542bcb5656b97362244f1b4842895ab7748d7ba4b5a30fe8',
    str(MAIN_TEMPLATE): '028f861052df601e0a2c8331b8df1594d4f613be9f1bdf0ae28d427c88fdc124',
    str(PLANS_TEMPLATE): '378b8cc658e0b4c4b8da04ffb0b1d26965ad6fa4417334b885b69914749d10dd',
}

BLOBS = {
    str(ROUTER): 'eNrtPWtvHFmV3/0rLjUS6WbbbU8ys2KMalnjODiM4xinJ4Asq1WurnbXprqqUw+PG2NpZ0daBCMkRiwfVmi0Y6JRNEA0w7ISwi3Ehw75H80v2XPuvVV1X9XuztMBW4pdde+5r3PP+55b6cZRn7Tb3SzNYq/dJn5/EMUpccIwSp3Uj8JkYaGLMAMn7QX+fg6wDa8L/Dm5H/ipd43BpcOBHx7kYKvhkLfvOknqDPyiYvvmTpSlXtwgN6K43yDfzbx42CA73v3MS1KpTTP2kgHMxEvy1hutW5s7vBDbdPzYc9O8RG6cev1BAEspJ/UdP/w352qLlXv5Ap3BoDnw4r6fJLjsHNhP2k6n74ftOApgrBAm6wT+Dz363najjlc2T7z40He9pJm4vSgK2n0vPvDiNi/Oe6wtEPhZu7114+bOrfb2xs7qnfUGLdveXN1qr25v79y+u65XrK1ura1vSuV36Di36DDrcRzFrBjmEkeHXj4+LDNkFfuZH3Tag9g79L33WZHrhK4X6KAdL/BSqYt2J3a6Kav1jjw3y6tZ0YGXStCwI1HcYXWBn6SAq34/C71EKBLhKZbNdWITjtqh58R6MS/hTXtQEQFR0bLEOTSupr6wsAAob1+/uUNsStY1YAcf9rZdR8KLgkOvVm8OnNgLU/5nIc1pB5oo1FRjtAjj2kka1/Kul4hVNLLqMGhMqR/aF5zA6AI2p+sf2daSG4UHi2622MkWA9/LlhJnsBj24FcaZ1BlsWWlzkFi71p3xqcDEvYmZ48GJI2ffDkZfQIge3R5m+t3gWzWNm7fXFu/AwOycWqW1SBWa3L2WUrcydkD/PXZgPQmo5+5Vr3BYW5tIdStydnDPpB+WFa0NmhzfzL6MFMbtTbW7tBa/CuUbrdYKfyt05ldv3kHKPsHhrk5QaBMb9B78uWTU2Di8akwDU7pHQR+/PPxA9LJhpPRj1Pyt3//BXFhXp+QFH7/3iU9mOqPhZZAjQOk8LJpLxp/GgI4/O7xCb5B1qD1T8jjj6H1Bxm5h718GMJkACMhaW2M/2vr26R1c4vwChzsoyZ5t+fL4+Lb2aO0QbzwwA89EmTj/wvJ0WT0iATjP8M4jz+ejH4Bq9ufjP6bpHQm9LEzGX0BFA59ZFBw9kUKPAzlLnToRbDC8aOwR5Lxqdv7BswOOj2AwgikdZz6TsA4oblwfbW12r57c/1701A9+iU0hkk/ABIq8S5MQEC760ZZmCa04fhTH4aOAFhAL8jebpehFqbrk/Dgr58LyA+cBMQ51m9ORr/SyC5Js47H+9/AKpL4sM4lQB+I3aAPdQJwFh96QzYW26Y0dsrqCDAVY+11AZXhAd2XATmcjD5DxJ26fMupqL3TWm29d+d8nknjyRnSJBDNqV8OeX1n9Qal9S0oH5TlXLRfn59a127f2t5cbwlNVWrlcFRHbIpwk9HDIV/bQsfrkraTpb12BkqpFjNlu5Jr3TpZ/BfS8d10F0RXA5X33grtOPbAPAhpVd4IdFw08Jog9YEc8h6tOolicnxSjkVVZxQGQ/Ng+yC0pSEkdVszaNuaPv86m0UBAvK1mEDidL22H6a1QyfIvBVcEx0YisiPyFYUemz4NB6yB/riHaWw6Si/aTNclGXVm1DgD2r1Ai6fM3SPTerE77K2XpB4tHOuLF1vAHq/NRx4TEuTu9gtfa6vqN3Rdsr026jk2GSSFarxdnF36FLoG8AUe5VkQbpSFsNKdvdoVRfWwRbkh4R3VowOJlwfQBWMlYuFtVEQPwFNkNJZgpnYYYVYAn3ysYs25XyaIKm9sFND6Lq44aw6Xy/8cuCVqve236lRNc/XIhPmnnEbHTf1Dz1YRgjbUKsd0SUf4dRoT7iII0YtSGgUGKilQXtg0wII3omw0BXTljOwXcvvWHvSkrCSDre7vMersVs2g5I0+JLvd659ffntdhC597xObiTh2o0LtCyL/r37TvOt5lWySL77+OcEO6Dy4yfEHf+B9EHiplSjfOSQfRQTjz9Gk+CBi5LuD06T9rAJYmxIyvFQmKHoSf3J2V9QBYx+S/6ZoKkEzUGQ0KaFkuk5cWcRmQ210u+hIMmGABeBdm5KE6X2G2yI2d7jzOR3YJMTr6BXeOQ1uH90DrCFtKtyKxgl27SY7Wm5GKukW4mz+WBNpwOkWNB4CTwrq1LLOQrBq8g8cesp2flozMEodbrtgRfSF2Lb5E19+0sR1/ETWMowl1RA6ZQC4C8bN1+vLJZQfReSqRlE78PYEjVyhu+WnH98BIRZcoZihZ2wOdKODZN0UqeN3sPLn6Zqw5gmOnAOUAeEKIVrvHtZ7TBN+TXuFJTOBBDNisBtsAD8w32kgq4qQQLvELwoZAiKEqizuIXOt7XdF+uo0cWqc4Qa6rijtqLoZNP4HhIo8FeSAAbUKYAxlmZJVe2+497LBu3Q6UtVlcYAk2O27o7VCgkq4xUlqSxFlXq7QvCDFhfQX4yZv/PxEvBU3bSUnbn0L0YT1UDRF8xSkH2aUgPZcJTLbmBcfC/B69zewp9yC/hsxf3GlekMLkLUZSJQGhTMVjzxQXKpWi5S85lrkrCSMW7Lrw1FruXrtMtHGaSkdrt8RD4vsZH/iIu1xZcSTLIxdNKRNsa8Z6X8RonArR2OKi5fjgsYKzzIIr/dycBDXjGYw8LmWiJ5A7AQdaDVOTVBlRzdYI0VwrRWNFqdAk0Z0qIcWatpNM7MbKb2KGCdG6lCj5QMoAchhCKPJOMax6ogC31yFNxEHiVoSRl8FTKpoEGdgVEIesDUWiQVa4WYKUcAzxkEYfNnAZCP3YswPgcwUlBEgMvHKSEV9SjC5uOI0KqWEveDiXPcETECxykp7Ppxvz3oxU6CCzbFBymkJOkBUHoXUSMJfboFYoEAKSgAABPeBBgeS4N6ObhWC/y+n9pvvs038WRBtxmoucdGn9NqEEwGTipzmQwGXz43GkqLASd3Ac0GAWlqldfxUzZv7Fmug7X3WWjzBVoNl6bB3KZBsdmcxnVZaCJ0tgWyUSByk/DMEcLj4GaXuYwEPK2ipVV07uqOKduumB+53YHIkgeuVxofCmKnWyByrR+6QdbBMAZz0u0bDnC9aHHM4psuzGk8nWM4qVPW7SW2kzbfdamaz7hgfc7G+WZKIqG0hgRo8/FMTWwo2WFlW9zy4o1ZHF6361HEcuID6+MrIBpY3FP2krUZM4MXJRSU0IhiKbPy6KFxDkiDTLIVA+TdHEtDWnw9qBzleWNggPGbTC9WJ3IzjCrn5orSTq4+p4vUT4NpfbD6czoB22JaH7Ta3AWgydCSlpobJFEWu14urv0OmjE03Kh0ocPR/nb3FNa0UidGaisA9dloEEIXJwKFNBMv5eK/VuxqA8VlBYy8UTNBsu2YCZRifRokxfI0AB2HDURgBbSGpjxQ+Q/u2LwKB0bRMiWUoIMLI/spHA+hGwHaYMFqm5gU605mcP4KThS5UnRqkArRiSoP+2l5nlNQOCiVyQqMgFhagQxtyGB4/i7NiWTZ953QQZ2XH77PYt3zTaBGOdrtNrm6vMxBvnbvfWDKhB4kgSEsnV0VB/zNPBsgz0ipCecHdEA7FgfGH6R1m7mUKW7lkpxDQrex2Uv7gSUaHNRjsQ1OTN5/MeO6amYwS0R4LgyNhX9lyQmMCUHo5Pk3bXpua4vZN3WK63ySMINpCFb9JvQoCq+EJgDVuOyzqZzT3ajZWuhelQxaSBNTbFYBpYHrilBtNegb5Ns+HjenPGkh7Y0fuT3y3s4mntxcXcJfzTeJ+9fPy2P78f+GpDP+Ezzi0c2H9EDnZ2GZzsHOVVTT9pwVyh5kBZAhAmyA5MQOdhlaYoajXf0oU83MqmVxYFtL3+SGLhh++36n44VAYyJRXlu+lrszEoNT97PwX7hvBGVJ5oK4TATLU2snuyPmfBl2ziUerGPJGVSIySfkcPwpOaTnaSm5nznkHqZ+9DHpgFjyKCA8vIPYT4dLN95tEjH/IJiMPgJ6SDABJHwMrYESylO6A0o7oM2H49+ETUt1W168uKkWNFqgRBmpMS3qXJ4tz+oDli1m9gQFWTZHDFrib9sQQdSpyq4KqCksZRsjanVd3A4iMLqtpSOvT3O83HkkLwsozit8bZp8qQsEVeRWwemC1gxnkrMy5DQxWwmpxMDMY6tG9HRozUDnkRRos6c2op7Pq5CKQnCsiqPEpSuQKkLq4sJhxSIwyzvRkFJXqKTNzCQjty7k+FFCfmjWlxMUChGP5Ww07M0i9qaKvvnF34wisFIMGkSh8eStMoiEONVBZ5B8c0i/mSSgFjS2dRRQ1bctasxE0Lbc2gET5+zhkFo6D5tkY/xgmNs7weTs1DcqXss8VKE2xRxMlh95+PhDzKM8eyBqUUUCV7yKnPdWbv6LsUMmcYHqpaRqIWiYO4iVW64yol2wg2CrF4xgl48NSb+DLOGpTG0GktitOJPjhlCfOUEe6OMx6BqfM0/i46m0zDmsS454GTcrYnN5VxiZU3r/Cus+jyqWHJyPJ8Y49mniU8wDIXmamGxH3RrL+b9ga4FhRPpoqPXGvwM7jVPVvR7NJpVgUftCl+RofOoyIpRNKmVyuxYVYmnU5jnuFpX7GD8uJJki+HLZhaiQUCptsCUgYorkLKYhN97TM5xed2tw9uQDXfy9RKOPb4itndlWeNRXl5cpf4iEoJJUnZ1CvrX8TqUVmPYyd7HnUytgViuQd39pBb50K7CYR9cPYScGMVDsechlB/40jXo2UGSzashLQ/TSEL00RDXrsMUsgxTzh+e3ScEX5/GhX7nMMr00JC+AIUl3HqOBmmUoGYJ8E+9nzpC7FRi7k/bU4GfwHfYCaukJUpqecQ89Mc6YT0QxWL+F14LAoXnypSPanSzA2JmMfgsjcdrjAUGcmBBINEyroUYXy7hleJDh7bGGHMp85PY0Q1daFAoONe0E1yinnumL7Vpr419n0sLYUtmsOdb5+vgVNQReIcdy1ycCplHYTreZzsW65HPye3ecHpyQX6rDe2p/dKWY+2T0P/JFrjIQO+iNPx9oeBevaAlyAm+EwUr3x6fREviyZ38E3wPdlA4lNd+8F6rRgPiX0CDUzYACIca8JPEFpby05zDx9kuf3e8IxmeuxA9NdbF0deBBf9Yn39dkYfl6T73waFht4hkY2Cq0Mi26VLIXTclWuj9mLeyVt9CfUh9K93XY7TAgFOnCuZLafq5+nFVHzqAnuQ6MYntqfgW7SzRg8xJY2Fb5Xc2Czy8g6Tf7888sNNldJOIkCHzJMBeVYSqsufkpd14KnoOSz7H+lKzJCobWhYB0vPouuyTPD1Rd1LugZcg/UdMOKHh26/ltWVoI7LJO//hReMkVr4Wv9nIIZGFaqKOAw5iHYkWd++0NCbxrfVPZp2P+cKICflXYqGMlagH20JUregthv47LZwXO+qq0X+W3LdTeyr06PueemTZCnpzMcy3UnsUD72OmtnevCIVX9oQeK0Kn15avFc7mG2Tx+f1Ab3hhGq9Lvzc5+/UW2Rx/QpbI1sbk7HfbZHvjyRdPPgUSHH+wRVob67fJ3cf/sUW+hZDPeR5yahWY6EhOi848QV4xre21SrYy3GipgDRdcHna/KZXERZ9o7yeD848eGDFJX323Rd6lT738cV7+u5k9NARTy0ZhtVPA2CEs/qzASJNaM2MgVGOIH0c9eaHsVfwWLWWJU5nDRGbY7MrplskpktBhhtHdVHE667yeUJeYM4ZxX2VCBeFvoap6RJfvyp05Yp2VejEdJw5jZbhXxXpcg0NAmYg3auw8PtZmDLNvioTPPkykwNvehRla2P8wXbT0nOIy26EiNe9yehP0DDDzyTRaNj2xvin5Pp7P5iM/rMlx+fIthbZOMroR3l40AfnIhwOG5P9pImxbOVAmBn9bI407DeMgUYaQVLiRUogREyu9phazkc5QjkgdSsh7US0YKblMxuNyPmT72ZPvDvHihREvS08N/SbSTiW+NKoSOG0BcKkyhM5o7wohaK+vCRgOE4tmHkpyDLK5vOqXPoBOZoVf1HPV2c6CJVuyMwISq/IzAiLd2Smg+IlmRdw/Dr7Ce9FPimd8SjzJRyq6nfrhHt1GrdqN+ikdxNcfk1OLjBB8rtw0rsAxy+84R/xrojhVpspDGK6raYEVk6mnRxX5ALx42NZd2unzBqdnSfkL0huTXlj01buCRl8/W3QvA/8PL2Pnq6SLcx5px/9o9+++/74AT2uYGdXWLJWfo2SvrfUwy6lND/veoZYs/kLobVXmcIk8pBdwVG6pLarWEoT1HYFTxmFcGUUcdbAJHKoLbPpHOH03FrID4e129NSRFCLn1dFBl8TjpMMJk36zsuT5sjaedzyIkJp83tZJ1OCaPM4U6X7VIS2qIszT5Cq2soc9DxY8tBL5zUzuY80zcacyc57lYbohUxYewFWWJkPPD2hwnBV9rWVQ5IceYZMEANOTmbX3pryNnzyvKaKy2pN8/etOuYW/e9cUNHPA2zPeIpynhooolTPRxP0suG8OoCFoy5VwN+bCpC+f3CpATSUPIsC0P8fi0v5fyn/n0b+l4cBz0cBHEXOUwWc+f/Acm7I+ULrglcg4SWxUPXf2Lw2wuFVfTPhGaXGBRAalZib5ZzWiMTnIV3yI8B5ZMv/A0+pT/0=',
    str(MAIN_TEMPLATE): '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',
    str(PLANS_TEMPLATE): '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',
}


def decode(value: str) -> bytes:
    return zlib.decompress(base64.b64decode(value.encode("ascii")))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str, code: int = 2) -> None:
    print("=" * 112)
    print("DỪNG AN TOÀN V9.4.2")
    print("=" * 112)
    print(message)
    print("Database KHÔNG bị thay đổi.")
    print("File phương án KHÔNG bị thay đổi.")
    raise SystemExit(code)


def main() -> None:
    for path in (ROUTER, MAIN_TEMPLATE, PLANS_TEMPLATE, PLAN_FILE):
        if not path.exists():
            fail(f"Không tìm thấy: {path}")

    mismatches = []
    for path_text, expected_hash in EXPECTED.items():
        path = Path(path_text)
        actual = sha(path)
        if actual != expected_hash:
            mismatches.append(
                f"{path}\n  expected={expected_hash}\n  actual  ={actual}"
            )
    if mismatches:
        fail(
            "Mã nguồn hiện tại không còn đúng nền V9.4.1. Không vá đoán.\n\n"
            + "\n\n".join(mismatches),
            3,
        )

    plan_before = PLAN_FILE.read_bytes()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = EXPORTS / f"backup_sap_nhap_v9_4_2_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for path in (ROUTER, MAIN_TEMPLATE, PLANS_TEMPLATE):
        shutil.copy2(path, backup_dir / path.name)

    try:
        ROUTER.write_bytes(decode(BLOBS[str(ROUTER)]))
        MAIN_TEMPLATE.write_bytes(decode(BLOBS[str(MAIN_TEMPLATE)]))
        PLANS_TEMPLATE.write_bytes(decode(BLOBS[str(PLANS_TEMPLATE)]))

        ast.parse(ROUTER.read_text(encoding="utf-8"))

        try:
            from jinja2 import Environment
            env = Environment()
            env.parse(MAIN_TEMPLATE.read_text(encoding="utf-8"))
            env.parse(PLANS_TEMPLATE.read_text(encoding="utf-8"))
            jinja_status = "PASS"
        except ImportError:
            jinja_status = "SKIP - jinja2 không có trong Python installer"

        router_text = ROUTER.read_text(encoding="utf-8")
        plans_text = PLANS_TEMPLATE.read_text(encoding="utf-8")

        checks = {
            "backend canonical commune": "_qd3805_locked_commune_id" in router_text,
            "redirect wrong commune": "requested_commune_id != locked_commune_id" in router_text,
            "readonly commune": "Xã/phường theo QĐ 3805" in plans_text and "readonly" in plans_text,
            "remove commune autocomplete": "plan-commune-search" not in plans_text,
            "marker": "V9.4.2-QD3805-COMMUNE-LOCK" in plans_text,
        }
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            raise RuntimeError("Thiếu marker sau cài: " + ", ".join(failed))

        if PLAN_FILE.read_bytes() != plan_before:
            raise RuntimeError("File phương án đã thay đổi ngoài dự kiến.")

    except Exception as exc:
        for path in (ROUTER, MAIN_TEMPLATE, PLANS_TEMPLATE):
            shutil.copy2(backup_dir / path.name, path)
        print("=" * 112)
        print("CÀI V9.4.2 THẤT BẠI - ĐÃ TỰ KHÔI PHỤC")
        print("=" * 112)
        print(repr(exc))
        print("Database KHÔNG bị thay đổi.")
        print("File phương án KHÔNG bị thay đổi.")
        raise SystemExit(5)

    report = backup_dir / "00_KET_QUA_CAI_DAT_V9_4_2.txt"
    report.write_text(
        "\n".join([
            "V9.4.2 - KHÓA ĐÚNG XÃ/PHƯỜNG QĐ 3805",
            "=" * 90,
            "STATUS=SUCCESS",
            "Database=KHÔNG THAY ĐỔI",
            "File phương án=KHÔNG THAY ĐỔI",
            f"Backup={backup_dir}",
            f"Jinja={jinja_status}",
            "",
            "Đã bổ sung:",
            "- Backend canonical commune_id từ plan QĐ 3805.",
            "- URL sai/thiếu commune tự redirect về đúng xã.",
            "- Xã/phường trên trang QĐ 3805 là read-only.",
            "- Không còn tìm/chọn xã khác ở trang QĐ 3805.",
        ]),
        encoding="utf-8",
    )

    print("=" * 112)
    print("CÀI ĐẶT V9.4.2 THÀNH CÔNG")
    print("=" * 112)
    print("Database: KHÔNG THAY ĐỔI")
    print("File phương án: KHÔNG THAY ĐỔI")
    print(f"Backup mã nguồn: {backup_dir}")
    print(f"Jinja parse: {jinja_status}")
    print("Trang QĐ 3805 đã khóa đúng xã/phường của văn bản.")
    print("URL sai/thiếu commune_id sẽ tự chuyển về đúng commune_id.")
    print("Ô Xã/phường trên trang QĐ 3805 đã chuyển sang chỉ đọc.")


if __name__ == "__main__":
    main()
