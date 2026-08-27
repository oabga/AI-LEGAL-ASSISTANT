"""Dựng corpus pháp luật SME từ dataset công khai trên Hugging Face.

Nguồn: ``pdt590/vietnamese-legal-documents`` (mirror của thuvienphapluat.vn,
518k văn bản, nội dung markdown). Cả vbpl.vn và thuvienphapluat.vn đều chặn
truy cập tự động (HTTP 403), nên mirror dataset là đường lấy dữ liệu khả thi.

Pipeline:

    law_manifest.json -> resolve doc id trong metadata parquet
                      -> đọc content từ 11 shard parquet
                      -> validate nội dung đúng văn bản đã yêu cầu
                      -> parse thành record cấp Điều
                      -> data/base_data.json

Chạy:

    python corpus/build_corpus.py --out data/base_data.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from corpus.builder import build_records, parse_document

HF_REPO = "pdt590/vietnamese-legal-documents"
METADATA_FILE = "metadata/data-00000-of-00001.parquet"
CONTENT_FILES = [f"content/data-{i:05d}-of-00011.parquet" for i in range(11)]

# Số Điều tối thiểu để coi một văn bản là hợp lệ. Bắt các trường hợp mirror
# trả về nội dung của văn bản khác (đã gặp thực tế với dataset UTS_VLC).
MIN_ARTICLES = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dựng corpus pháp luật SME từ Hugging Face")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "corpus" / "law_manifest.json",
        help="Danh sách văn bản cần thu thập",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "data" / "base_data.json",
        help="File JSON array đầu ra cho load_postgres.py",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "corpus" / "build_report.json",
        help="Báo cáo số Điều thu được theo từng văn bản",
    )
    parser.add_argument(
        "--dictionary",
        type=Path,
        default=PROJECT_ROOT / "corpus" / "law_name_dictionary.json",
        help="Bảng tra law_id -> tên chuẩn (sẽ được cập nhật)",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("law_manifest.json phải là JSON array")
    return entries


def ensure_dataset() -> tuple[str, str]:
    """Tải metadata + content shard về cache và trả về đường dẫn glob."""

    from huggingface_hub import hf_hub_download

    meta_path = hf_hub_download(HF_REPO, METADATA_FILE, repo_type="dataset")
    content_paths = [hf_hub_download(HF_REPO, name, repo_type="dataset") for name in CONTENT_FILES]
    content_glob = str(Path(content_paths[0]).parent / "*.parquet")
    return meta_path, content_glob


def resolve_documents(con, meta_path: str, entries: list[dict]) -> dict[str, dict]:
    """Map law_id -> hàng metadata, ưu tiên đúng loại văn bản và bản mới nhất.

    Một số số hiệu bị dùng lại cho cả Luật và Nghị quyết (ví dụ 91/2015/QH13),
    nên phải lọc theo ``doc_type`` của manifest. Khi mirror chỉ có bản dịch
    tiếng Anh cho số hiệu gốc, manifest có thể trỏ sang văn bản hợp nhất bằng
    ``source_document_number`` / ``source_doc_type``.
    """

    resolved: dict[str, dict] = {}
    for entry in entries:
        law_id = entry["law_id"]
        doc_type = entry["doc_type"]
        lookup_number = entry.get("source_document_number", law_id)
        lookup_type = entry.get("source_doc_type", doc_type)
        pinned_id = entry.get("source_document_id")
        if pinned_id is not None:
            # Số hiệu văn bản hợp nhất (VBHN) được dùng lại mỗi năm, nên chỉ có
            # document id là định danh không nhập nhằng.
            rows = con.sql(
                f"""
                SELECT id, document_number, title, legal_type, issuing_authority, issuance_date, url
                FROM '{meta_path}'
                WHERE id = ?
                """,
                params=[pinned_id],
            ).fetchall()
        else:
            # Bộ luật được mirror lưu dưới legal_type "Luật".
            wanted = {lookup_type, "Luật"} if lookup_type == "Bộ luật" else {lookup_type}
            placeholders = ",".join(f"'{t}'" for t in wanted)
            rows = con.sql(
                f"""
                SELECT id, document_number, title, legal_type, issuing_authority, issuance_date, url
                FROM '{meta_path}'
                WHERE document_number = ? AND legal_type IN ({placeholders})
                """,
                params=[lookup_number],
            ).fetchall()
        if not rows:
            print(f"  [MISS] {law_id} không có trong metadata")
            continue
        # Bản ban hành muộn nhất là bản hợp nhất/mới nhất.
        rows.sort(key=lambda r: _date_key(r[5]), reverse=True)
        row = rows[0]
        resolved[law_id] = {
            "doc_id": row[0],
            "document_number": row[1],
            "title": row[2],
            "legal_type": row[3],
            "issuing_authority": row[4],
            "issuance_date": row[5],
            "url": row[6],
        }
    return resolved


def _date_key(value: str | None) -> tuple[int, int, int]:
    if not value:
        return (0, 0, 0)
    match = re.match(r"(\d{2})/(\d{2})/(\d{4})", value)
    if not match:
        return (0, 0, 0)
    day, month, year = (int(g) for g in match.groups())
    return (year, month, day)


def fetch_contents(con, content_glob: str, doc_ids: list[int]) -> dict[int, str]:
    """Đọc nội dung của các văn bản cần dùng từ toàn bộ shard parquet."""

    if not doc_ids:
        return {}
    id_list = ",".join(str(i) for i in doc_ids)
    rows = con.sql(
        f"SELECT id, content FROM read_parquet('{content_glob}') WHERE id IN ({id_list})"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


# Từ chức năng tiếng Việt xuất hiện trong mọi VBQPPL. Dùng để loại bản dịch
# tiếng Anh mà mirror đôi khi lưu thay cho bản gốc (ví dụ 38/2019/QH14).
VN_MARKERS = ("Điều", "khoản", "quy định", "Chính phủ", "Quốc hội")


def validate(law_id: str, content: str, articles: list, lookup_number: str) -> str | None:
    """Trả về lý do loại bỏ, hoặc None nếu văn bản hợp lệ."""

    if not content or len(content) < 500:
        return "nội dung quá ngắn"

    hits = sum(1 for marker in VN_MARKERS if marker in content)
    if hits < 2:
        return "nội dung không phải tiếng Việt (có thể là bản dịch tiếng Anh)"

    if len(articles) < MIN_ARTICLES:
        return f"chỉ tách được {len(articles)} Điều"

    # Số hiệu phải xuất hiện trong văn bản. Mirror hay chèn khoảng trắng rác
    # vào số hiệu ("Số: 1 45/2020 /N Đ -CP"), nên so sánh sau khi bỏ hết space.
    squashed = re.sub(r"\s+", "", content)
    if re.sub(r"\s+", "", lookup_number) not in squashed and re.sub(r"\s+", "", law_id) not in squashed:
        return "không tìm thấy số hiệu trong nội dung"
    return None


def main() -> int:
    args = parse_args()
    entries = load_manifest(args.manifest)
    print(f"Manifest: {len(entries)} văn bản cần thu thập")

    import duckdb

    print("Tải dataset từ Hugging Face (dùng cache nếu đã có)...")
    meta_path, content_glob = ensure_dataset()
    con = duckdb.connect()

    print("Resolve số hiệu -> document id...")
    resolved = resolve_documents(con, meta_path, entries)
    print(f"  resolve được {len(resolved)}/{len(entries)}")

    print("Đọc nội dung từ shard parquet...")
    contents = fetch_contents(con, content_glob, [v["doc_id"] for v in resolved.values()])
    print(f"  lấy được nội dung cho {len(contents)} văn bản")

    records: list[dict] = []
    report: list[dict] = []
    dictionary: dict[str, str] = {}
    next_id = 1

    for entry in entries:
        law_id = entry["law_id"]
        law_name = entry["law_name"]
        doc_type = entry["doc_type"]
        author = entry.get("author") or "Quốc hội"

        meta = resolved.get(law_id)
        if meta is None:
            report.append({"law_id": law_id, "status": "missing_metadata", "articles": 0})
            continue

        content = contents.get(meta["doc_id"], "")
        articles = parse_document(content) if content else []
        reason = validate(law_id, content, articles, entry.get("source_document_number", law_id))
        if reason:
            print(f"  [SKIP] {law_id}: {reason}")
            report.append({"law_id": law_id, "status": f"invalid: {reason}", "articles": len(articles)})
            continue

        batch = list(
            build_records(
                articles,
                law_id=law_id,
                law_name=law_name,
                doc_type=doc_type,
                author=author,
                start_id=next_id,
            )
        )
        records.extend(batch)
        next_id += len(batch)
        dictionary[law_id] = law_name
        report.append(
            {
                "law_id": law_id,
                "law_name": law_name,
                "doc_type": doc_type,
                "category": entry.get("category"),
                "status": "ok",
                "articles": len(batch),
                "chars": sum(len(r["content"]) for r in batch),
                "source_url": meta["url"],
                "issuance_date": meta["issuance_date"],
            }
        )
        print(f"  [OK]   {law_id:<18} {len(batch):>4} Điều  {law_name[:52]}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.dictionary.write_text(json.dumps(dictionary, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for r in report if r["status"] == "ok")
    size_mb = args.out.stat().st_size / 1024 / 1024
    print(
        f"\nHoàn tất: {len(records)} Điều từ {ok}/{len(entries)} văn bản "
        f"-> {args.out} ({size_mb:.1f} MB)"
    )
    if ok < len(entries):
        print(f"Xem {args.report} để biết văn bản nào bị thiếu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
