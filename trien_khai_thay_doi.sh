#!/usr/bin/env bash
# Trien khai len server 192.168.1.24: chi day len cac tep thay doi so voi lan
# trien khai truoc (them moi / sua / xoa), khong dung tar toan bo nhu truoc.
#
# Dua vao git de biet chinh xac tep nao thay doi:
#   - Lan dau chay script nay (chua co nhan "da-trien-khai-server-24") thi day
#     toan bo ma nguon dang duoc git theo doi (khong dinh kem data/, .env,
#     uploads/ vi nhung thu do khong nam trong git).
#   - Tu lan thu hai, chi day len phan chenh lech giua nhan do va HEAD hien tai.
#
# Chay bang Git Bash: bash trien_khai_thay_doi.sh

set -euo pipefail

KEY="$HOME/.ssh/vantai_deploy"
SERVER="sonnh@192.168.1.24"
REMOTE_DIR="/home/sonnh/data/phocap"
TAG="da-trien-khai-server-24"

cd "$(dirname "$0")"

if [ -n "$(git status --porcelain)" ]; then
    echo "Con thay doi chua commit trong repo. Hay commit truoc khi trien khai:"
    git status --short
    exit 1
fi

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1; then
    BASELINE="$TAG"
    echo "So sanh voi lan trien khai truoc (nhan '$TAG' = $(git rev-parse --short "$TAG"))"
else
    BASELINE=""
    echo "Chua co nhan '$TAG' -- day toan bo ma nguon dang duoc git theo doi (lan dau dung script nay)."
fi

TMP_LIST=$(mktemp)
TMP_DEL=$(mktemp)
trap 'rm -f "$TMP_LIST" "$TMP_DEL" phocap_delta.tar.gz' EXIT

if [ -n "$BASELINE" ]; then
    git diff --name-status "$BASELINE" HEAD | while IFS=$'\t' read -r status path _rest; do
        case "$status" in
            D) echo "$path" >> "$TMP_DEL" ;;
            *) echo "$path" >> "$TMP_LIST" ;;
        esac
    done
else
    git ls-tree -r --name-only HEAD > "$TMP_LIST"
fi

N_UP=$(wc -l < "$TMP_LIST" | tr -d ' ')
N_DEL=$(wc -l < "$TMP_DEL" | tr -d ' ')

if [ "$N_UP" -eq 0 ] && [ "$N_DEL" -eq 0 ]; then
    echo "Khong co gi thay doi so voi lan trien khai truoc. Khong can lam gi them."
    exit 0
fi

echo "Se day len $N_UP tep, xoa $N_DEL tep tren server:"
[ "$N_UP" -gt 0 ] && sed 's/^/  + /' "$TMP_LIST"
[ "$N_DEL" -gt 0 ] && sed 's/^/  - /' "$TMP_DEL"

if [ "$N_UP" -gt 0 ]; then
    tar -czf phocap_delta.tar.gz -T "$TMP_LIST"
    scp -i "$KEY" phocap_delta.tar.gz "${SERVER}:${REMOTE_DIR}/"
    ssh -i "$KEY" "$SERVER" "cd '$REMOTE_DIR' && tar -xzf phocap_delta.tar.gz && rm -f phocap_delta.tar.gz"
fi

if [ "$N_DEL" -gt 0 ]; then
    while IFS= read -r path; do
        [ -n "$path" ] && ssh -i "$KEY" "$SERVER" "rm -f '${REMOTE_DIR}/${path}'"
    done < "$TMP_DEL"
fi

echo "Dang build lai anh Docker va khoi dong lai container..."
ssh -i "$KEY" "$SERVER" "cd '$REMOTE_DIR' && docker compose up -d --build"

git tag -f "$TAG" HEAD
echo "Xong. Nhan '$TAG' da chuyen toi commit $(git rev-parse --short HEAD)."
echo "Neu ban cap nhat lan nay co tep nang cap CSDL (app/upgrade_*.py), nho chay tay:"
echo "    ssh -i \"$KEY\" $SERVER \"docker exec phocap python -m app.upgrade_<ten_bai>\""
