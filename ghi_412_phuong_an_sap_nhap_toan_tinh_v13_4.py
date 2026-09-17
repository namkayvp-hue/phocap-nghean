# -*- coding: utf-8 -*-
r"""
V13.4 - GHI 412 PHƯƠNG ÁN SÁP NHẬP TOÀN TỈNH ĐÃ DRY-RUN PASS
==============================================================

NGUỒN KHÓA:
- Báo cáo V13.3.1 đã xác nhận:
    Candidate: 421
    Existing QĐ3805: 6
    Blocked: 3
    READY: 412
    Importer proposed: 412
    Importer errors: 0
    Importer warnings: 0
- Lỗi return=1 của V13.3.1 chỉ phát sinh ở lệnh print Unicode của console
  sau khi report dry-run đã được ghi hoàn chỉnh.

V13.4 CHỈ GHI SỔ PHƯƠNG ÁN JSON:
- KHÔNG sửa database.
- KHÔNG thực hiện sáp nhập.
- KHÔNG đổi tên trường.
- 412 plan được ghi ở trạng thái APPROVED.
- 6 QĐ3805 COMPLETED giữ nguyên.

AN TOÀN:
- mặc định DRY-RUN;
- kiểm tra DB integrity/FK;
- kiểm tra đúng 6 QĐ3805 COMPLETED;
- kiểm tra school source/target còn tồn tại/active/đúng commune;
- kiểm tra không overlap với plan APPROVED/COMPLETED hiện có;
- backup school_merger_approved_plans.json trước APPLY;
- ghi file tạm rồi atomic replace;
- hậu kiểm JSON + 412 exact plan;
- nếu lỗi sau khi ghi: tự restore plan JSON;
- DB không bị ghi.

CHẠY KIỂM TRA:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\ghi_412_phuong_an_sap_nhap_toan_tinh_v13_4.py

GHI THẬT:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\ghi_412_phuong_an_sap_nhap_toan_tinh_v13_4.py --apply --confirm "GHI 412 PHUONG AN SAP NHAP TOAN TINH"
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import shutil
import sqlite3
import sys
import zlib
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"
BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"

CONFIRM = "GHI 412 PHUONG AN SAP NHAP TOAN TINH"
EXPECTED_NEW = 412
EXPECTED_QD3805 = 6
EXPECTED_YEAR_ID = 2
EXPECTED_YEAR_CODE = "2026-2027"

PROPOSED_SHA256 = "5bcb9352816b7e878bd99d79fb53716d0ea80ac18ae367938b7ca6cb43bdea62"
PROPOSED_ZLIB_B64 = """eNrtnU/PZcdx3r/Ki1klwB2hu6u6qkte9d9IQEQKJu2NYRDMcMAhTA4FcqTYMLwQvAiyNLIWFErLQIANaaWBViPoe8w3yTln5MSIbp/UG7AR9EFT1CV47zt3Lu/80FX11NNVf/X3Tz775Ml3n/xleuq2//3gvafNVNNCqjZU9+T25JMvn/34i+cvX3307MtPnm8/+N5/+Iv333v6Qfzh0/e+tz18+H587+mH33/ve//2R1999urz42c//fHb1//t5cPXb7750cPLF29/+6sfPbz68s1/f/nw6u3r//ryxcO/2/75X7aX3v3cv/+37/HJx6/2t9ie+vrZiy+//Pyjv3v+8Vcf7Z/V3Z48+/KLL3788vm//uvnz3/y/PN//YA/eG//NV/++Ktnzz/64y/97JOvn3z3r0L469uTVx9/9enzV//7hSffDdsbfP3q41c/3n7mSfzhD//8/b+sZXuLl18eH+C9F29+/cWD3T/x/3i48x/0nb/9/Ou/3X782VfPt0/8yUcfv9p+kTOOnhp5avBDa74L/rtI/+ZH/tPfPfnu3//xI+5fvYWP3m/t+/n78T9+VN7Pf/GD+t6HH33/Bz98/88/fPIPtycf/+hHX335k/O3/l8/88j3/vGPPvm/fep//ZH/p0/98ecf/eePv3r52ctP9z+Bv/6H25/gRo0iRHCIUS6Fm5j7uIkCN7dwG4RbDTZFTIGzT9c63fA+bqDADRZuo3CjmJOFiIbttXDzt0D3iWMFcbiI+/aJsztxCME1LIUhlBmIs1riHN3g/hkHmjPOL+IGEQdMUGOoBmy+FnF8FzcMCtxo4TYIN/YVS+WQMF4MN7l/uhkFbrxwG4RbwiAZbKs5mWvhFm5g7xOnUUTCIm4Ace5grlaxqRI0cXMw59TUsdw/5Vg0UVUWdMOgYwtkcuBExl8OOu5ARxrt1yzqvn3q4GCuFpGSI2KrMzAHWuIs3CfOAmqIW+2GUcRlrhmS5NgsXIw46hDnNcStjsMA4vBdAQGxOcHk7BSCHKqJo/upnGVNxWqXBDyKOGqZXXA5UfHXIo5thzhVD39JwAOI84cEvB1x3hkWKFOccV5NnHSiqmi6XHapwKOIC0xcXDJW5qhWH0GcvVmBDnWqc26JwaOoy5iKMCJYny9GHW7U+Q51qnxuCcIDqGM6LJnSwBUDFHEK0xKTljtv7p903qhOuqUHD2Mu1WyjFMzVtqsxZzvMac45t9TgAcwFszNXKteAzRTgKfpewaiZs3Tz9r4m7K1GoXNLEx5x1oWj3xqtAw9i0Uzh0uSgP+tChznVWbdU4WHMececLNuynXhXY046zFkNc8uMPoI53plzBlDABgdCUzDHeubw5o3v5HWaLr9b/Ygx3H34vacOJUkVcBD8lNx9+L1u19WZ2/bQ6UuA05SxbjUmRqGXP3iaoOVsavUiOCl8+YNuQ8y4Xg9WcynCrQbFCPLk6FDkINZiSNnNIaCIvpjtiHZWddqt9sQY5rZAW7iGGH0S42VK5k4CbTCdGMuqG9VLKh5F3RZjnUCJmTH7mifl7iTGor1tD71AixolBZZ6N0I1PozrJRVPzaC3cYqqNqh9696ZTqDVHHmw1LthzGGQaDl6i4wXY852FGOnUe9gqXdjmNuSuxaNoRicmJynZK6f3GGnJbu9oJpfsrS7UdRtyZ1vDV3IMRLRpNz1kzs02MnrvOZCIiwBZSB5ZUvtYoyuBJsvRx577pGnyu6WjDKAPDpsnlgbJpfYhDaFdEdqnyfSfekOSSPd4fI+jWDu8Nv55r0hJHQ2TsEc6ZnDDnMa3xOuKnYEc4cfAKJNTDaA5yniK7GeudBhTjWdbjVkhzFHHksWqlFMuxhzbDrMafI5XJXEGOY+/N7TrYQAxigowlMy11dOjO20xYxRUbeqiGHUBVdiq1ZKBrocdZ1umFF5PHHdFRtFXf7gafaQXXGM3tVJuTvR60Jn6AQGjV7nVwU7grxj7EQkMcHB7i+ewnxCqK8mbCez0/T+/er9j9CI393cQRQIjgyHKcY5Bf0tis5B51XnHK1zbhxzbGooRqJr8WLMSedmrGoCAK1zbgxze++frUeTsHnDUzLXrSXE31fqxGuUOlrq8DDmooi3vtqSyFyMOTId5jSaCS2P0yjmditxS65sAdaBm5W6k+rV42176MzZQa8xO9EyO43A710TttpWG4sRP0c5oR96QnTz1BlAoRrYSaspNow7psB7bpf8HDNiH8Od37jrWIpVjTFajbEx3G0pXqqYYt5/72Sn5O6kReE6xk7jVALKalEMo67Z7Fps0KjS5aijHnWa3I6XbDeKuq20kBAbUpYkJJNy1y8tepMUtxc0NjteRe0I8o6dE6EGs98VgzrHlpOgXjrhoZPZqS7F8qpkhzFnIyYq1Xlv5GrMdRpjoBGMeVWxY5jbBeMaynbUlWApTsncSV7ne4Ynr1noxKuGHUZd2wcpbqldBFMuRx30qNPY7HiZO0dQd5idGlZTHDZfaYqR7EFtdvLYy+k0al1YFeww5jyR8a0YSIWuxhzftkz1Pneqsy4s88kY7vYIux1yPgJXjG1K7k4iLHV6sYY0el1Y9pNx1GUAUwMT2OtR1+tNqK5hh6XVjaIuf/CUrIk2Sww8xy67O9ydqMQudFRip8rulnoykLwYxVupiXOW65EHnYuKHlT53VJQRpDnDkN7EyiMIZlJFBSnH6BInWF2Gq04LA/AMOZSCgZdcy4HuRpz2GFO04cNa07xGOa2imIr9lIzzQef6pTMnVQUoVfHqq6LyVLthlFHLkHxjIYmGWL3GOq4R51m5Y4szW4UdftFimg8GydQJ+nGusdUE75XTai6FLIUlIHkSbYFOVKuaK5HHvYUFNTUFLI8TyPIO0aLeW9NrcFiynP0x/Tr7VhuvrMAxQdNp0KWcjeMO4PWFM5Sm8jFuAuuw5xGs5Ol2Y1hbqsqAGOKrUn2k551/arCgrttD52C1qrkYlnWp2HoYSu5QgouQrkcetijThVkl2A8irp9GwBAsY0lN2mTcndSVnQirdWFWmuWgjcCvWMdgMPSYIPPVZ4jv1OvA/Cd4Tvekwq6ZX8aBl2rNsZGtrXkrwZd5wKPauKTNUu7GwPdltoxpURIrTQTp4Sun9o5R7ftoSPeOVVz1pql3g1jL9VQrbjEpdHl2OMedqLCbol3I7A71rSn4jLXVLJzc4xA0a9pF9+Z5okq6JaEMgw641qiRpTjJL3ZR0AHHeicCrqloIyBbrc/CdrsjAChnxK6foAF0wmwYIIKu+W6G4ZdCsmwQZ+o4uWwox52qnLCLtFuFHa7DaX4fVU2SagyKXh9vZikoxeTqPRiu7x3A9Cz5rioXYKwrw1D8G4G8raPrc3vSO6LdyQqxdguxXgQdlukFRFgdAg8h4Lyp9j1J7bz/eNOVCNkrV1OlAHYyVHL2pyCEWsb5SlmZou6lqXO0CdSTaSwbmV3Y6A7dlOQtBCi8cFPCd3JSXe/lBVWBVi3Auww6GzAirJldWUO49NjoIPblrJ2wFPJxW61ZUeBtw+lSI1AuEmMs6J3shWls5die0F35q2u7JCiwu7pHXAMNltuodo5igqrzu/Y3ojvOz6JVcKxW53ZcehVlzJSTNIMXg497mBnVNitenYcdiWaBmxdsr5cDjvoYKfqzrplCRh42qHJjott0NzlsPMd7HT53TIFDMJut3wWHzBClcKTnnYn8ymgNz8bdOAtW8A48FxIYaMuRWMvCF5vMAqo8jtY0vE48La8Dm320mpJ1wOvt6dCdW3WwpKPx4EnIVveB0GFK4LXG2kMKisULPl4GHj5g6eWCRzW0KTBrOidXJ61vcuzRnWlDJaAPBK+lHJIFGKp7C8In+kNhLK6kLu0vCHwmV1UIUtOIHJIWOdAz+jdKfe5I9Jht0SVcdjZkHOuVQLXdDXsyHRMUSonHixJZRB2+1CoVsiEDMFJnhO7k9E8rjcQSrXP3eKSVMaBxz5tf7HLdZaW2WPA4x54KhEZ102LYeBtxYXn0DAZDMxhVvROiotO52x7QQff0vOGwHfs2HahJkpkvUuTFBegv+bTMQqISs3DpeaNw874jFUwJCnXw65z40JUbTNcOt447GxF04QNYDWXw852sFNZ33GZQAdht5UWVWqomWtFynNidzI/oNc0A50/BZd0PBC84gB85SrFXA886IGnEo9xGUHHgReZTGTfmvF4PfBcDzxdYbG6FsPAyx88Dc1zktYimGnPvL6YwvZ+mre9oCov/JKQh8B3LARFjNHWUBDsJPZ39UZQCvfHRFFQnXl+CcjjsLM27vodGT9LefEI7PhGoTOuR7UWdPtmFnpj0NvHCdi61RYIaAjnRO8kzyPp5HmkA28JyAPBc4ESoC1hjinvjwOvN5KRVFZQvyTkAeD5Q0EuCUqOOTnJUzQuvFpAhs62MlCtjbJ+ySnDoEu2pozbH4QUuhp02IFOJR77JaWMgW6LsDkZQ+x9THOYUrxawRNz3/4pRiUc+2X/HAadK+KRJCSL9WrQYQc61dgKWrrdKOjyB0/Z+Ii12dSAJsXuZDRZTzJGq0NvCSgj0DumbHPe6okCIYlMoZ949ZBtwPvqCXhVn4JWDTsMuhh8dSZGW6BdDDoPHehUmR0tE9QY6PbBAdFW2H7nQuSnhK6f2dleOaGqYWnVsKOg2zK7iAaS5WDtHJPd72B3ltlhL7NTdWV5ZXYD0RNIYQu1PtXCF0QPeuipTj1ezbER6Pl32ywyQ0BTJMwBnnrtNtD9eQGgG7LNK78bA90xCq9G47lFw3lK6E7yu/tHnejkE16NsWHQsYPaLDZvJqlkHwFdZ5OFVV3n4VVUjIJuy+xyE9daJF+zmRS7s8yut8nCqqajhNWpGGF7cnw4AbyPxoILGeeYFOBYm9uFjt0u6Nx2YTmMvw3snuQ3v36w2xf35hfbd/j29b88/P6f3vzy4dn27Ivte334+g/fPLz8/T9+8fDis42Olw8vNmBePLx9/fOHV1/94Z/fvv7Zy08f/ubFm2+e/dnD85effvby+fYmv/3d/tRvtleeff7l9sxP3r7+6f62v3r24jtP7nNuQ8GAjkLNdDXO2dwC2w7rKoNfWLrNVVjfJ145j5lMY9vKnKyfjNQVd9seeiPsdSMRwtKKBmUURzaLDEUi0Mafn5W/k+lDvqORe68q38OqpIbAd+zd9a5VV4WMJJ4DPfXi3RDuF/AhqOzUYZkMx2FXOVGsACFhvhx2roOdSjeSVUUNwm53VDNvx13yBW2bE7uzRI96OZ6qfJeV4w0Dbx+KwLFxiNIapVnR6+d4RvC25XPcS/RUZghZjsMRBMIxTLzmao3Ppng/h24JRh9xQyfiquRyWfOvxmHXQHy0raYm9nLY8S3IfedhEJXdVVZnehB6+wX17BBbZI4lzone2Thxe9seXG+muKrClSWsjKOvFJ8QkrOSr0eflR54KjlZlrQypNQIh6In4t1+c9jkSaSVoG/c4S10ZtkH1Sj77c9koTcGve3MQ1MSObbNTRJx/wS9k5Ew0lnQBiIq8Ja8MgA8d1ynkxwwO9rS6TRFbevU1+kc3q8vHGpaZ84uJ9gI6N5NsmefydtcLE1R2Tr1SBgH99M7B6yCbukpY6DbPf7siFMh06qfErqTosL0VrMZ3Vm3qtlR2OUPnrbmuQTjEYJMCt6JQ4U68zk8GRV6q54dUVS8u0rHDowU71uYo2+hvkrn3P2GrXMao4Bz67wbAR0dC5/FY3B1q2ZxjjHipIcudKBT5Xaw3Ckjgqw9ZtcLAaVqdofKFCHW6gsK6BQUqpMOlnQyArrjpLPomGxrNdIU0zmc/qRD7kgnXgXduqk+RCh+N043x4joU5E6R3zViyfB3Xe7B1VP1q2dp6Ow2+/57Ds6vBNPjebE7sT+6To1rFH1ZN1aPzkOvPzB0wQ+WQKbfCyzondyY106hgBvdPAtyfga1ykPySaEuO8G8aXwJKyrNZuwJY8B7+s2wetYX56/IQetf9cJTjaBRDGcroae79wrwqDCbsmF47BzbGzO0dQa6+Ww6wxKQJVgiKs1Mgi7/TpbIIqGC3o3aaA985i62/bQmVtgVeNV3dq1OpA+5yAhITY/y4SYx9AXeuCpbKZr2+pA8EwwCWJzLoQLgsc98FS9krVrdRx4+0TpYNDFIlLnMP3dQ+/MB8O37aFz9HlW1bdr6epQAglrILHFO8MXJJC7TiyVy34tXh0D37HlvEbvoQEy8SQ3i9RbzoPtaHpWVeX61TwZiJ0xW40L2YKhy2HXmVxgdafdapsMwm6vMghStCbmNMnkAqffb257Ydayymu/Vk0PBC8CWWAhFHbXA68n6LGuvF1djGHgbcWFA8kchEOJNCt6/eKCTGdeBqnWTru1dnoMfIcRlVkMkYfo0yQtNNK30PwtdGajBa/q3q7l0wPRq5RbllwzgVwOPdjQ6zhSvaqVQauVMQi9fSerK6Z5W8QTzYneycQMh7ftodPPAKejb/UzxtGXPCYwphpK6Xr0+R54KiM+rTbGMPD2SsPXaCUWQuZZ0etXGmw6px4blW+FVhtjKHypRRuyoVLtFeHDHny6kLuaGUPgO0ZVFce1WiOFBOdATz2rKoC7hc5N3wAqhYVWQ2McehFjdcVXjFkuh16nxAVduF3tjEHY7TbRGKDYrcJIxc6J3UmR4Tv33kCprax2xjjwMhkhMRXI+euB15NVdHoyLz15GHj7bV/OWw0XQmtAs6J3UmA4f9seOjZR1o2v4iUrjyQQpRiHrRhI7ooE0k6g9AhUmfZ4SctDCDz2vmAynAiarTLJKHD13hfuLPjjoPLH8xKWx2HHEtmws9nXfDXsWDrYqaQVXpLyIOy2UqO6IFxasTGnObE7GSyEnUaaQVUjjZecPA68aBv4ZsXjLDfAHwOe64GnqzCWmDwMvK3CKElaDq1uf9dZ0Tu5iGa3Gtf3LuN63S1wXrryCALfDQZ3mUyyYpIxc1S4+sng3FH32KuuBfFSlQdht3umwGWTxNXcwpzYnUTc3tVvQ6rzLixVeRh4W8T11priwSXEMit6JxG3Yx3YXlDdSQtLzhsC37FU0oWGCURs9XPoKla9VJKpE2x1Ewdk9TEGYuddaWSAzSRL6x+DHXWwUzVwZZ12g7DbN4cTUcwWW3Q4J3b9HM/1djc7qwNvtS/GgZeBq3WFrZnEFf8o8DpiitMNqJfVwBgG3lZcGMcpVYiZIsyK3snV745BdHtB5RCV1cQYAt9x/9YjiSsBmkxy/1a/bo3J3pg6fgFS9c9kiciD0NsCrs85xIw5epfnRO/EI9qbYQu66VKyZORh4O0OPVOcpNSIkGdF7+wSmuldQtPYVcAsKXkIfHKY8yg5ZPRVJjGH7geW1iV1X0Vm1XwpMEvN+9YWEbn/j4uI3nFuqQinUgtZeznOO0kl647XJR9ehfMti6XGxldTEjmYk/OTLBZ7N51Ue4/ALL1yUCJxLKDxLlQqlqReD7zu3U6jAm/plcPA2/VK8oaZbJplVOUd9M4uOPXKJ1XtDmbplSPh84VIAmawNV4Qvp5wxKpp+GCW8XoIfPxH26tYbxPHNIlsxHqx3HeEcl3tvoTyQdjtmV6sUPxGXq5+TuxOMr3eNHxQTcMHs4TyYeDtO7dSs84lhhKnRe8k2AJ1gq2qMw12CeUD4IMj1mbTqCFkFj9FmgfqUOvY3lxHQnQMKvCWVD4GvC3aBijSGtvtS05TgneyAaQzPWF7QYfdUq5HYbfF2tosF04+cMJJwTvb/9FR9MiqFD27pOQB6OExuCMABDINOOIULWlUz+1w4X6C55Tn3ZKRh0HnYhaBra5o7K8Gne9Ap5JS7JKPx0C3Ww7RZa6MTeawHKJ+YoeV3nY30QXYJRwPwy47MTHjdtgVvhx2vZJCVGYYu4TjUdjtJUXeSjsibxBgUvBOSorO3ujtBZ16t6TjEegdA2LQZozUAgeaQkRB9XwYMHCDzpYPMKqehV27LMeAt4VaBKnWVpOpmCnBOwu11Au1qvPOrW7FKOy2UMskdkMPAvOs4J2F2nDbHroSnsqa4pZ6PEI9PoZ1VNOQHBqT5nDkQdB3y0KnU6Y79JZuPAy6KAEp+JYSx6tB19GNWXfSLd14DHT7SqPUGrQth27GTgndyZSO3r1NKzrslnI8DDsMTkrBIERXw85K6GGn8ru7pRyPwm6/ql5yRsqxNk+TgndSV7iO+5NUc4nALfV4REl7rKzcaolQmvXo51hZieqNlU6kI9/poFu68Rjo9gZt9SZS2v6fw5TQnWV3nbPOGZUZBZZ8Nwq7Xb5LJrkMIBFpUvDOwiz0wqyqYQHLbjwCPXv43AuRR1cryhzgWb0Pim8udNS7oCotYEnGY8DbB+1C9Ta34gPPCd5ZqMVeqCUVdks0HoXdFmoDWFubzaEKTgreWajtDTt1qn4FLA1vhJhyjKQSpuA4MAc7RYsWRB9qzRZqO1fKVDsqAZaUMga8fUVlICtATDHglOCdTRY3vVCr6lnAElOGYSceYog5FUF/NexM6GGnKyyWBW8UdluGB1hjqYS5ljwpeGcZHt22h9BL81THHi4xb8TYiuNmWc0GfE5izCQTGfU3yzrB1llViodLxhsD3Z7i1RyEExsyeUroTvwBvnfFx+uwW2rKMOyoILhEQttfV8OuNwPU6obP4jLhDcDuWBpTfCCXpSVDbQbq1Ctjeg48p1ucgEtDGYLcIaG47YjLIIx5RuROStneeiwHKl+AX6XEAOiOGWScoTWbhMRN4UbRjyDrNMiUVhS/MrohyO3TxxxLkwZCIc6I3MmkT+goxeBUkp1f+dyIMuKw3RnbckLLIU+yD0ttu5POWBQR1TAeWtCNgM4dY8eaicGHHMXOsQnL6XW6jutJd1GW1oWKYdABs1CuLjSoV4NOOtCpPE+0atcx0G3hlautzmOyJDAldP2szvSsdkZXStDq/w/DrjZg9KaA9/5y2PkedipHO63+/wjs4Oi/YpMKVEpOc2AH6hDrzM25js3OqSRiXj3YMeDtYxZrrIHQpWRhSvBOzrvQuTxmdJOMeV2kGIXdviWl+SaOK7EPk4LX9zt57Iwd86hytPOSUIZs6Dkc7U0KSRGPnOZYz6OvZjsdCqs779Y1imHQbazlkoWanWNPxWOg60xut6qigpduNwa6/bYiZe8j1YwIU0J3YgDAzu1shzrsloQy4rbiOwcAG2JbEzqZY46x2gIA25kG9j55oPMTh1XLjgFvO++ayxyFKZH1U4J30pHlTkdWVU6E5T0ZBd0+BgVLyJIrMsyKXb+SxdBxoKDuimxYlewI9I5ZsjmYEkt20iaZvxP0gbazLEC3pSKsSnYAdP64KUa+xFBbsy1O4UDx6pti4O4fdaDrUoRlBhgGHXNwEjF7l/LVoHMd6FSaXVh17Bjo9rmKLWURCdLmqGP9I+6JQW98MajcdmFZAUZht48vDmwaG0aaw1nsH7OBzHc2fW4vqNzFsgSUEegdRs9YkAxJglymKCi804fZcAPXGWGsGz8hyw4wBry9U2EClea5BBunBO/sSnZvx6yuUyFLuxuB3dEgy5JbbGLJ4xRdWW8fgZ3vYacLs6svO0K3o3cOlAYpcg0wh7UdSb/os7clQBdiVzU7DLqMAH7L7zw2czXo6Aad2XZgVIKxrHp2DHh7bhcZoUKspuKU4J25ULjnQtFgh2aNoRiGXbFRSvYNyhyXFh+FHfWwQxV2S0IZhV3+4Kmx+w4og5wAJgXvZJCn79gBSDVgDM2qZkegd4xqN+Cs9fs4xTRFZxZFbwfoZHdWVNAtD8oY6PbsrnjhaKWURFNCdxJmpecxFl2YXUXFKOy2MBt9TpQiVu/KpOCdhNnOXortBY0tAO3K8AaiV10rbTv1CuR8QfR6GZ7K8Il2tclG9CveLeNxsnGXc3Z2ivWyXp3hYWdKO6pWU6BdZcUw6NiCCzGJ5Dnuyz4COnNfvkOrO+lWWTEMOltacQ6CTZmuBh11TjqVgGKXtX0MdHstKwgs1mSeYwmKf0Qti73dT96osFvm9mHYsU/MrUkItV0NO9+TULxTYbcMAcOwC9kgpSQuzdGXfRR2vfUAqCsnlnI3CrtdPqHmDbJ3Ceuk4J01yDpDx8irlDu3LAEj1qG8W3JHbIP1DK5NIRmT+hYZwv04i05VVLglnwyDLrtkMrbMlvBq0N2Psgiq3M4t+WQYdMa5FCgIoElXg64jFIPKceeWfDIMuhTDbnwiiNCuBp3thFdVOeHWXYox0O372jlwxlKtBDcldGdVrO+JJzrslmY3DDtnfeMSpOboL4ddTyomlVTslmY37rRLwBQ5YMjhctj1TO2eVdgtzW4UdvmD7Z+5kQsUbTGTgnem2VFPs1MFWlhuu4Ho5ZSbjdVxiO5y6DnqGT1J5UGBJaKMQO+Y2W4sE3GqgZqdAjz1zHbsNCkQVaEWVmExDLragjSfJBoPF4MOww1ROuCRCrxVWgwDD2sFatEl4nK10+5+jEWd9QlWYTEGunez7iK1iuIL0JzYnWd30MvuVGYAXN2KgejVaoGycVFKuBx6RL2allTdWVw9i4HosXNi2dXAjBc89aSHnureLK7yYoT77lgZgJalbvE2U5hj0KJ+ZUBnRQqoVqRshcmC7luA7kl+8+sHu31xb36xfYdvX//Lw+//6c0vH55tz77YvteHr//wzcPL3//jFw8vPtvgePnwYuPlxcPb1z9/ePXVH/757eufvfz04W9evPnm2Z89PH/56Wcvn29v8tvf7U/9Znvl2edfbs/85O3rn+5v+6tnL77z5C7lYr0BQrPVMng1yjuLMURVQPvlLh1ztB4DpzACB6aGaUroTnpz3FGpHatUar8aJCOwO7bt5WZi5so21TlWY+i37YX7JQwEVUT3q4IZA93uQwCOkc125ImdErqzs67nQ2Addqt6GYZdEudcQkqO+XLY9VxXrOrJ+dUaGYXd7kEIYFKzDaHJpOCdSIXcm/hDKvsLraJihFTo/ogeF9oK2eKNTJHfkXuMVBh6tyV1hQUt+8uIU+8YoJxaLsYZYR+maI/4RwxQDr2xBEHVHKEVbIdh56REdh5zjfly2PUudKhWnyGvQDsKuy3Q7jE2m9I8hDYpeGc5HvYCrcqJwEvBG4AeH84rMr4U25pYmcLgzHrnVfA3DJ0he0HVseA1mmAEeMfWPdNa5obcopki1PIjtu6FznlndeIxrwxvFHb7bSJrcatq2UtKk4J3Emptr6a1quKClxNhBHr+sL+YXFEChQRzhFqvDrVyXz9GUcnHYZUWY6DbB+0FsK4AN2/LlNCdhVnphVkddmtY/DDscknSSjQBk1wOO+php5p3FlZRMQq7fTNLqqY5ihWqnxS8s+yuJ6RYlZASVsdiBHq4Z3cRAZKjYEuaomPBqM/uOqP2dObmsKxQY6DbwyyZsh12EIBhSuj6YRZMp00GRtWvCEtEGYXdfnOSK0cXLFHLk4J3toUq3LaH3kUiUd3cDUtJGWFMORa0BGdz244+wzTHcAz9ghbuNCxY1bCQpaQMg468iCnF+FTj1aDzHehUkVZWe3YMdFuCtyU70bCTxlSnhO4kweu1KkDXqpAl3w3DrkXbjDSXpV0PO9OrK1SGY1ny3SjsdsOx8zEjeU/TnncndYXgVldIbzaGTk6RpeGNqGuPIfLCxBBLDQ3m0PD0Q+Q7lhTUeY5laXjDoDPGZ8vGlWbpatB1FgPplnnLusw4BrqjPwvelJS2L3nOk+4swaNeXaErZ5dwPAy7GKMNHnzEwpfDzvewU/VmZenFo7Db6opQE6ItHDzJpOCd1RV7v0K6/QqNG8qbJR2P4A+OMSk51Gpq8rHOEW1B7w3obEQTq4JuScdjoNs3e2+nnSmxwHbwTQndSayFzlkHoDvrloY3Crst1pYiKaWMxJAmBa8fa7lnwWNVmufNmqo8AD08wizFmkPwzglOUV2gOsxu/0U3J/cLDKeavujNkvDGgLd3aVPiVGyqdY78DvWh1kBnNJRBXYa3RLxh2JUQTeBmvTR/Neyw06U1ICrslog3Crt9WoXk2LBJTTFOCl4/w/O2Yzz2Kv3YmyXkjUDP7Rke+BJqsIhEU/jd0ekzPLtleK6T4Wkcx94uBW8MeHvjosaMrTR0LUwJXjfUir3vOBarKivsUvBGQbfPqmitWk7Wco6TYtcPtOg6OR46VWlhlwF0AHpAe6D1JcdIaHGSfhmQOtAS3RzdP/McBRV4Sz4eA97uPCYbo8mW4hwOAVBPYBRnO4FWB93yfQ6DDtiQT7hBB/Vq0JkOdCoZxa5uxSjotuzORVfEpewgmkmxO8vusJfdORV6q18xAD1rj05ZDKVwi5JSm0JHsVbdKmPgG3f8AQy6ULvE43HoUavRMkWJnq+GHt7P8Bh1+t0Sjgdht6V4iNYEKuyy4JzY9XO8zh4LUd3t8W7JxuOwo9yoNRQPs552few43CR0ygtWlRduicfD0Nt3zFPJrYCvLthZ4TspMLgzPwBZd+4t+XgkfB5DAKrOWH9F+CjctgfpEahK+NzSkUcQaI7VtM6Ij9YlLDxFB2P72Oo6w+KNO7cc2XoVektNHoTecfhBMey9gdJsnhO+k8NPxG1nX29lKKpWhnq35L0hAB6bBqhALAGSj6bMgZ961QCb+61bNiq7ilt25HHYIZTkJHIig1fDrjOsjK0u01uK8jjsfBYXuTovPl3utPM3NqFz4uk0lqUqD0Jv366CsmVDATMkmBO9kysYtlPdGp1hBZa4Nw48CjWikPOhuOuBRz3wVLUtLGFvGHj7KBUqNVKKvs4irDxmxco+uML29plZ3UIzD0tdGUmgI2/E5AbFtisSCDuBPfeUqJobsIx7Q5obx8TGWiJlQecsTOIlUI9sZHf/Cho71XQLXF6CcdhJS4KhpgoZLocd3tj5DnoqZQ9XuTEIvb3OrTFzbs3lSSQWqx/caNh1yg1WXUPD1cUdBt6W7BkftvOOKTO6WdE7GTYAnVrX6yaZ4ao0RsJna+MWTWhN4Irwhdv20JP5WKW24Ko0hhDo3i06237jZqmkOIfWYp3+ngZ07miopqzgauQOkViOVWcp25hqLiW0Sewroq80TKfKUCV7flUZQ7ALh3+A03bgSS4tTdLUCHr/AN+401BjXT/NrzpjEHr79aBaS/aQfbBhTvT6Ba6TjlFeOVfKrxpjGHhbjcHW1easLYHrrOid7Cbg3loC1p16yyc6pLyw7+7icrK5ZYFJ0LNWX17YG0OnmQG6c2+Z9sahV12UBjFywHg19NyW67lOrud0p94y7Q1Cb8v1fAESTFlimBS9k80YnZV72wsqWYVWfTsMvH2eo4tM5AQc4azo9XM9CJ1mBqPKPUCrwh0JX+FmfA1gwJjrwcfYW8yCqj4GrSp3JHwGEIpkH11zVzz5uAefyrxCq4k2Ys7eYZuyLpEJBFulO8coW7VryvnORiCvyvV4mfVGQHfcSQvBGxeqrSBT3MAFr5+fjJ3ZyaocLyzoBkDnjpEXXEJINQUuc8wTdeqJFw6lc9KplLywCosx0H34vae1Wi45JwkOpoTuREzxncYZeN1Zt7K6UdhtFUUUg6ly4Ux2UvBOqlnX0fGUPpWw7FEjcrvDlOeFTWMvAcoc0+L1S6h86IRZlRk5rIbZGOj2XY/g0Dq2wbsyJXRnPYveNu+gapaF1Swbgd0xrds3xmJtjjHPgZ1+pTKZzlmnGqsiq1E2Brq9QWuN+EQO2xx7vEG/1xZ6XjzQefFkzbYYhd3eIcsgUm1KMulpd1pSeNPrUehOvCWiDEBPDjeUj9ZzpeqjTFHLitoMRfY+dWRVdaysruww6Op23MVkEuUCV4PuvvGTdCPzZOl2Y6DbcjuB5DJsD9abKaE7WcPiO2tYVN1YWUb3YdCl6mx0JlANdDXoqAOdSrGTJROPgm6fAp8jCxssYQ7nidhHrV/xvQHwKsuTLNVuBHp43OvxyUhKodg8hc1YUJ3ZdbaKkmqpKJnlPhkGneEY2TGK8+Fq0PkOdKCCbknFY6Db18XnaIOYIGmO/Xp/At3JXDLseIqNylNMZknFw7CzPhfOScTMsTD+Mdj1ZGKDQYXdUuxGYbeVFIlcMmgkt2InBe9kHllv44B3RoXeklBGoHcYAYSDYR+SNzzFzG0BvVjMnexOB92SUIZBV5ilQuEg2V4NOum0xXRBdjntxkC35XYbc1tJkSJRwimhO8vteiWF9yrslmY3Crs9twvY8l7MErhJwevndsbvs2ad3x96I4+dplFGdskpIyA8bpDFHAtRTJjiHHWt+gYZ4X3jHaEqy7NLTBkGXY0pSc0Fk5OLQQed0gJEBd2SUsZAt1sCQkrgqHCWOCV0ZwstQm+iu0o4tquiHYXdluVh2f58sjcQU5gUvBMFDzu7VDxaFXqrwBiIXowSPaKg4XpB9EwPPVVZ4ZY1YAR6dIjHW2XLpTpT5lgML6TP8Dp+FFAJKm7VssOgI1NSE1dqKJeDDjrQqUxQbtWy3wZ0T/KbXz/Y7Yt784vtO3z7+l8efv9Pb3758Gx79sX2vT58/YdvHl7+/h+/eHjx2QbHy4cXGy8vHt6+/vnDq6/+8M9vX//s5acPf/PizTfP/uzh+ctPP3v5fHuT3/5uf+o32yvPPv9ye+Ynb1//dH/bXz178Z0n/yflx73wXGpy5IrPzk9Buf5euIPe3gIl56uOGXG4uj/elYw1G1eYs0mTgneytaBXx5Bqki251Z8bgd4xWs9zA/LZJi5zFNBe7zMNHScCq6BbxfMw6HLcJzkiSG3tYtBB54KuU2nUsMrmMdDt5mbAWoMYNs1MCd3JHIzOFNHtBVWAhVU4D8Mucsjgq4nk6HLYuR52Kn0aVuk8CrutpJACYNBSqXZW8E7Gr4C92d5GKqtbSUWwZrCM4O/YPiqZTYkSxbY5uiNB733p2BB0Nzpg2RCGQedaKoYzMed2NejoRp2x3aRayUKw5rCMAW9L8kzJUVIzGKyfEryTJI87LmfQ+V9gXSMahd2W5Nkt1za5lkSThtnzJC/08juVmoJLTRmBnnk3tjs3a/cUD+ewmar3AJHp9IONSjfGpaUMg64GtCaHEinx1aDrOF+MqjmLS0kZd9LVnJx3ITHFq0FHHehUBQUu+WQMdPseoOaaobJB59yU0J0N7e41K0SH3RJQxmFXTfZErsVYLoddb5e36ELsqmNHYbcvtEUXDJmQA9Kk4J3Niu+tn/I69Jb/6dtB76//J+wkQE4="""


def clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def load_proposed() -> list[dict[str, Any]]:
    raw = zlib.decompress(
        base64.b64decode(PROPOSED_ZLIB_B64.encode("ascii"))
    )
    if hashlib.sha256(raw).hexdigest() != PROPOSED_SHA256:
        raise RuntimeError("Payload 412 phương án sai SHA256.")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list) or len(data) != EXPECTED_NEW:
        raise RuntimeError(
            f"Payload phải có đúng {EXPECTED_NEW} phương án; "
            f"hiện={len(data) if isinstance(data, list) else 'INVALID'}"
        )
    return data


def signature(plan: dict[str, Any]) -> tuple:
    return (
        int(plan.get("school_year_id") or 0),
        int(plan.get("commune_id") or 0),
        str(plan.get("level_code") or "").upper(),
        tuple(sorted(int(x) for x in plan.get("source_school_ids") or [])),
        int(plan.get("target_school_id") or 0),
    )


def involved(plan: dict[str, Any]) -> set[int]:
    ids = {
        int(plan.get("target_school_id") or 0),
        *[int(x) for x in plan.get("source_school_ids") or []],
    }
    ids.discard(0)
    return ids


def db_connect() -> sqlite3.Connection:
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def db_state() -> tuple[int, int]:
    st = DB_PATH.stat()
    return st.st_size, st.st_mtime_ns


def validate_db() -> tuple[str, int]:
    with db_connect() as con:
        integrity = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
    if integrity.lower() != "ok" or fk:
        raise RuntimeError(
            f"Database không an toàn: integrity={integrity}, FK={len(fk)}"
        )
    return integrity, len(fk)


def validate_qd3805(plans: list[dict[str, Any]]) -> None:
    qd = [
        p for p in plans
        if (
            str(p.get("id") or "").startswith("QD3805-")
            or "3805" in str(p.get("document_code") or "")
        )
    ]
    if len(qd) != EXPECTED_QD3805:
        raise RuntimeError(
            f"Phải còn đúng {EXPECTED_QD3805} phương án QĐ3805; hiện={len(qd)}"
        )
    bad = [
        str(p.get("id") or "")
        for p in qd
        if str(p.get("status") or "").upper() != "COMPLETED"
    ]
    if bad:
        raise RuntimeError(
            "QĐ3805 chưa COMPLETED: " + ", ".join(bad)
        )


def validate_proposed_content(proposed: list[dict[str, Any]]) -> None:
    sigs = [signature(p) for p in proposed]
    if len(set(sigs)) != EXPECTED_NEW:
        raise RuntimeError("412 phương án có exact signature bị trùng.")

    seen: dict[int, str] = {}
    for p in proposed:
        if int(p.get("school_year_id") or 0) != EXPECTED_YEAR_ID:
            raise RuntimeError(
                f"Plan {p.get('id')} không thuộc school_year_id=2."
            )
        if str(p.get("status") or "").upper() != "APPROVED":
            raise RuntimeError(
                f"Plan {p.get('id')} không ở trạng thái APPROVED."
            )
        level = str(p.get("level_code") or "").upper()
        if level not in {"MN", "TH", "THCS", "THPT"}:
            raise RuntimeError(
                f"Plan {p.get('id')} có level không hợp lệ: {level}"
            )
        ids = involved(p)
        if len(ids) != len(p.get("source_school_ids") or []) + 1:
            raise RuntimeError(
                f"Plan {p.get('id')} source/target bị trùng."
            )
        for sid in ids:
            if sid in seen:
                raise RuntimeError(
                    f"school_id={sid} nằm trong 2 proposed plan: "
                    f"{seen[sid]} và {p.get('id')}"
                )
            seen[sid] = str(p.get("id") or "")


def validate_current_schools(
    con: sqlite3.Connection,
    proposed: list[dict[str, Any]],
    existing_exact: set[tuple],
) -> None:
    total = len(proposed)
    for idx, p in enumerate(proposed, start=1):
        if idx == 1 or idx % 50 == 0 or idx == total:
            print(
                f"Kiểm tra trường nguồn/đích: {idx}/{total}...",
                flush=True,
            )

        sig = signature(p)
        if sig in existing_exact:
            continue

        ids = sorted(involved(p))
        rows = con.execute(
            f"SELECT id,commune_id,is_active FROM schools "
            f"WHERE id IN ({','.join('?' for _ in ids)})",
            ids,
        ).fetchall()
        by_id = {int(r["id"]): r for r in rows}

        missing = [sid for sid in ids if sid not in by_id]
        if missing:
            raise RuntimeError(
                f"Plan {p.get('id')} thiếu school_id={missing}."
            )

        commune_id = int(p.get("commune_id") or 0)
        wrong_commune = [
            sid for sid in ids
            if int(by_id[sid]["commune_id"] or 0) != commune_id
        ]
        if wrong_commune:
            raise RuntimeError(
                f"Plan {p.get('id')} có trường sai commune: {wrong_commune}"
            )

        inactive = [
            sid for sid in ids
            if int(by_id[sid]["is_active"] or 0) != 1
        ]
        if inactive:
            raise RuntimeError(
                f"Plan {p.get('id')} có trường inactive trước khi ghi: {inactive}"
            )


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    print("=" * 126)
    print("V13.4 - GHI 412 PHƯƠNG ÁN SÁP NHẬP TOÀN TỈNH")
    print("=" * 126)
    print("Database: CHỈ ĐỌC")
    print(
        "Plan JSON: "
        + ("SẼ GHI nếu toàn bộ gate PASS" if args.apply else "DRY-RUN, KHÔNG GHI")
    )

    for p in (DB_PATH, PLAN_FILE):
        if not p.exists():
            raise RuntimeError(f"Không tìm thấy: {p}")

    proposed = load_proposed()
    validate_proposed_content(proposed)

    db_before = db_state()
    integrity_before, fk_before = validate_db()

    payload = json.loads(
        PLAN_FILE.read_text(encoding="utf-8")
    )
    existing = [
        p for p in payload.get("plans") or []
        if isinstance(p, dict)
    ]

    validate_qd3805(existing)

    existing_sig = {
        signature(p): p
        for p in existing
    }

    exact_already = []
    missing = []
    for p in proposed:
        old = existing_sig.get(signature(p))
        if old is None:
            missing.append(p)
        else:
            status = str(old.get("status") or "").upper()
            if status not in {"APPROVED", "COMPLETED"}:
                raise RuntimeError(
                    f"Exact plan đã có nhưng status={status}: {old.get('id')}"
                )
            exact_already.append(p)

    # Chặn overlap với bất kỳ APPROVED/COMPLETED hiện có nhưng không exact.
    for p in missing:
        p_ids = involved(p)
        for old in existing:
            old_status = str(old.get("status") or "").upper()
            if old_status not in {"APPROVED", "COMPLETED"}:
                continue
            if int(old.get("school_year_id") or 0) != EXPECTED_YEAR_ID:
                continue
            overlap = p_ids & involved(old)
            if overlap:
                raise RuntimeError(
                    f"Plan mới {p.get('id')} xung đột plan hiện có "
                    f"{old.get('id')}; school_id={sorted(overlap)}"
                )

    with db_connect() as con:
        yr = con.execute(
            "SELECT id,code FROM school_years WHERE id=?",
            (EXPECTED_YEAR_ID,),
        ).fetchone()
        if not yr or clean(yr["code"]) != EXPECTED_YEAR_CODE:
            raise RuntimeError(
                "school_year_id=2 không còn là 2026-2027."
            )
        validate_current_schools(
            con,
            proposed,
            set(existing_sig),
        )

    print()
    print(f"412 proposed khóa: {len(proposed)}")
    print(f"Exact đã có sẵn: {len(exact_already)}")
    print(f"Cần ghi mới: {len(missing)}")
    print(f"DB integrity: {integrity_before}")
    print(f"DB FK errors: {fk_before}")

    if not args.apply:
        print()
        print("V13.4 DRY-RUN PASS - CHƯA GHI PLAN JSON.")
        print(
            'Ghi thật bằng: --apply --confirm "'
            + CONFIRM
            + '"'
        )
        return 0

    if args.confirm.strip() != CONFIRM:
        raise RuntimeError(
            "Sai câu xác nhận. Không ghi plan JSON."
        )

    if not missing:
        print()
        print("412/412 exact plan đã có trong registry. Không cần ghi thêm.")
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = (
        BACKUP_DIR
        / f"school_merger_approved_plans_truoc_v13_4_{stamp}.json"
    )
    shutil.copy2(PLAN_FILE, backup)
    original_bytes = backup.read_bytes()
    plan_changed = False

    report_dir = EXPORT_DIR / f"v13_4_ghi_412_phuong_an_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=False)

    try:
        now = datetime.now().isoformat(timespec="seconds")
        to_add = []

        for p in missing:
            item = dict(p)
            # Giữ ID/dữ liệu đã được dry-run xác nhận; cập nhật thời điểm ghi thật.
            item["created_at"] = now
            item["approved_at"] = now
            item["updated_at"] = now
            to_add.append(item)

        payload["version"] = max(
            int(payload.get("version") or 1),
            3,
        )
        payload["policy"] = (
            "Sổ phương án sáp nhập toàn tỉnh: chỉ nạp từ nguồn đã kiểm tra; "
            "không ghép nguồn/đích tự do. Chỉ APPROVED được thực hiện; "
            "COMPLETED không chạy lại."
        )
        payload.setdefault("plans", []).extend(to_add)
        payload["updated_at"] = now

        tmp = PLAN_FILE.with_suffix(".json.v13_4.tmp")
        tmp.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        json.loads(tmp.read_text(encoding="utf-8"))
        tmp.replace(PLAN_FILE)
        plan_changed = True

        # Hậu kiểm.
        after_payload = json.loads(
            PLAN_FILE.read_text(encoding="utf-8")
        )
        after_plans = [
            p for p in after_payload.get("plans") or []
            if isinstance(p, dict)
        ]
        validate_qd3805(after_plans)

        after_sig = {
            signature(p): p
            for p in after_plans
        }

        missing_after = [
            p.get("id")
            for p in proposed
            if signature(p) not in after_sig
        ]
        if missing_after:
            raise RuntimeError(
                f"Hậu kiểm còn thiếu {len(missing_after)} plan."
            )

        bad_status = [
            after_sig[signature(p)].get("id")
            for p in proposed
            if str(
                after_sig[signature(p)].get("status") or ""
            ).upper()
            not in {"APPROVED", "COMPLETED"}
        ]
        if bad_status:
            raise RuntimeError(
                "Hậu kiểm có plan status sai: "
                + ", ".join(map(str, bad_status[:20]))
            )

        integrity_after, fk_after = validate_db()
        db_after = db_state()

        if db_after != db_before:
            raise RuntimeError(
                "DB file state thay đổi ngoài dự kiến trong V13.4."
            )

        rows = []
        for p in to_add:
            rows.append({
                "id": p.get("id"),
                "commune_id": p.get("commune_id"),
                "level_code": p.get("level_code"),
                "source_school_ids": ",".join(
                    str(x)
                    for x in p.get("source_school_ids") or []
                ),
                "target_school_id": p.get("target_school_id"),
                "status": p.get("status"),
            })

        write_csv(
            report_dir / "720_412_PLAN_DA_GHI.csv",
            [
                "id",
                "commune_id",
                "level_code",
                "source_school_ids",
                "target_school_id",
                "status",
            ],
            rows,
        )

        summary = f"""V13.4 - GHI 412 PHƯƠNG ÁN SÁP NHẬP TOÀN TỈNH
======================================================================

STATUS=SUCCESS

Dry-run V13.3.1 proposed: 412
Exact plan đã có trước V13.4: {len(exact_already)}
Plan mới đã ghi: {len(to_add)}
Tổng exact 412 sau V13.4: 412

QĐ3805 COMPLETED: 6
Database: KHÔNG THAY ĐỔI
DB integrity: {integrity_after}
DB FK errors: {fk_after}

Plan JSON:
{PLAN_FILE}

Backup:
{backup}

BƯỚC SAU:
- 412 plan ở trạng thái APPROVED, có thể hiển thị trong giao diện.
- Chưa thực hiện sáp nhập dữ liệu.
- 3 nhóm cross-level vẫn bị chặn và xử lý riêng.
"""
        (report_dir / "00_TONG_QUAN_V13_4.txt").write_text(
            summary,
            encoding="utf-8",
        )

        zip_path = (
            ROOT
            / f"ket_qua_v13_4_ghi_412_phuong_an_{stamp}.zip"
        )
        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for p in sorted(report_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 126)
        print("V13.4 THÀNH CÔNG")
        print("=" * 126)
        print(f"Đã ghi mới: {len(to_add)}")
        print("Exact 412/412: PASS")
        print("QĐ3805 COMPLETED: 6")
        print("Database: KHÔNG THAY ĐỔI")
        print(f"DB integrity: {integrity_after}")
        print(f"DB FK errors: {fk_after}")
        print(f"Backup plan JSON: {backup}")
        print(f"ZIP kết quả: {zip_path}")
        return 0

    except Exception:
        if plan_changed and backup.exists():
            PLAN_FILE.write_bytes(original_bytes)
            print(
                "Đã tự khôi phục school_merger_approved_plans.json "
                "từ backup."
            )
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("=" * 126)
        print("V13.4 DỪNG AN TOÀN")
        print("=" * 126)
        print(repr(exc))
        print("Database: KHÔNG THAY ĐỔI")
        raise SystemExit(2)
