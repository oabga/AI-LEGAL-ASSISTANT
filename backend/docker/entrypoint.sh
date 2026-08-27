#!/bin/sh
# Chạy migration trước khi khởi động app.
#
# `alembic upgrade head` là idempotent nên chạy mỗi lần container start là an
# toàn, và tránh được tình trạng image mới nhưng schema cũ. Chỉ một replica
# backend nên không cần lock phân tán.
set -e

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

exec "$@"
