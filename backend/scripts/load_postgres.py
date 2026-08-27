"""Nạp corpus pháp luật từ file JSON vào PostgreSQL.

Schema do Alembic quản lý, nên chạy ``alembic upgrade head`` trước script này.
Logic ghi dữ liệu nằm ở ``src.services.legal.importer`` để API admin dùng lại
đúng một đường.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.config import get_settings  # noqa: E402
from src.core.database import get_session_factory  # noqa: E402
from src.services.legal.catalog import sync_law_catalog  # noqa: E402
from src.services.legal.importer import (  # noqa: E402
    CorpusValidationError,
    import_records,
    validate_records,
)


def _default_dataset() -> Path:
    return (BACKEND_ROOT / get_settings().legal_assistant.corpus.data_path).resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        type=Path,
        default=_default_dataset(),
        help="File JSON corpus (mặc định lấy theo legal_assistant.corpus.data_path)",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Ghi đè connection string; mặc định lấy từ config/env",
    )
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Xóa toàn bộ record cũ trước khi nạp",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    path = args.file.resolve()
    if not path.exists():
        print(f"Không tìm thấy file corpus: {path}", file=sys.stderr)
        return 1

    try:
        records = validate_records(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, CorpusValidationError) as exc:
        print(f"Dataset không hợp lệ: {exc}", file=sys.stderr)
        return 1

    database_url = args.database_url or get_settings().legal_assistant.postgres.database_url

    def progress(done: int, total: int) -> None:
        print(f"Đã nạp {done}/{total} record")

    try:
        result = await import_records(
            records,
            database_url=database_url,
            batch_size=args.batch_size,
            truncate=args.truncate,
            progress=progress,
        )
    except CorpusValidationError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1

    async with get_session_factory()() as session:
        laws = await sync_law_catalog(session)

    print(
        f"Hoàn tất: {result.total_in_table} record thuộc {result.laws} văn bản; "
        f"đồng bộ danh mục {laws} văn bản."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
