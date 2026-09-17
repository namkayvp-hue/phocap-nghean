import traceback

from app.database import SessionLocal
from app.routers.surveys import lay_phan_cong_hien_tai

db = SessionLocal()

try:
    print("=== KIEM TRA LOI PHAN CONG ===")
    rows = lay_phan_cong_hien_tai(db, 3)

    print("TRUY VAN THANH CONG")
    print("SO NGUOI DA PHAN CONG:", len(rows))

except Exception as exc:
    print("LOAI LOI:", type(exc).__name__)
    print("NOI DUNG LOI:", exc)
    print("=== TOAN BO TRACEBACK ===")
    traceback.print_exc()

finally:
    db.close()
