# -*- coding: utf-8 -*-

import inspect
import sys
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
sys.path.insert(0, str(ROOT))

from app.services import school_merger_service as merger

print("=" * 120)
print("KIEM TRA CHU KY ENGINE _apply_merge - CHI DOC")
print("=" * 120)

print("SIGNATURE:")
print(inspect.signature(merger._apply_merge))

print()
print("SOURCE:")
print("-" * 120)

src = inspect.getsource(merger._apply_merge)

# Chỉ in tối đa 260 dòng đầu để đủ xem tham số và logic chính.
for i, line in enumerate(src.splitlines(), start=1):
    print(f"{i:04d}: {line}")

    if i >= 260:
        print("... DA CAT TAI 260 DONG ...")
        break

print()
print("=" * 120)
print("CHI DOC - KHONG SUA DATABASE")
print("=" * 120)
