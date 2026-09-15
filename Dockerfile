FROM python:3.12-slim

# Múi giờ Việt Nam cho các mốc thời gian ghi vào cơ sở dữ liệu
ENV TZ=Asia/Ho_Chi_Minh \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài thư viện trước để tận dụng bộ nhớ đệm tầng ảnh khi mã nguồn thay đổi
COPY requirements.docker.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Toàn bộ mã nguồn dự án
COPY . .

# data/ và uploads/ được gắn từ máy chủ khi chạy, chỉ tạo sẵn để chắc chắn có.
# exports/ không gắn từ máy chủ (chỉ tồn tại trong container) nên phải chown
# sẵn cho UID 1000, nếu không container chạy user 1000:1000 sẽ không tạo được
# thư mục này trong /app (thuộc root) và ghi file xuất ra sẽ báo lỗi quyền.
RUN mkdir -p /app/data/backups /app/uploads /app/exports \
    && chown -R 1000:1000 /app/exports

EXPOSE 8000

# --proxy-headers: đọc X-Forwarded-Proto/For do proxy gửi sang, để phần mềm
# biết người dùng đang vào bằng HTTPS. Danh sách IP được tin khai báo bằng
# biến môi trường FORWARDED_ALLOW_IPS trong docker-compose.yml.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
