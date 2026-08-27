import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";

import { parseReference } from "@/lib/utils";

/**
 * Danh sách căn cứ pháp lý của một câu trả lời.
 *
 * Mỗi citation dạng ``law_id|law_name|Điều X`` được đổi thành link tới trang tra
 * cứu để người dùng đọc nguyên văn Điều luật và tự kiểm chứng.
 */
export function CitationList({ citations }: { citations: string[] }) {
  if (!citations.length) return null;

  return (
    <div className="mt-3 border-t border-line-soft pt-3">
      <p className="mb-2 text-xs font-medium tracking-wide text-muted-2 uppercase">
        Căn cứ pháp lý ({citations.length})
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {citations.map((citation) => {
          const parsed = parseReference(citation);
          if (!parsed) {
            return (
              <li
                key={citation}
                className="rounded-lg border border-line bg-surface-2 px-2 py-1 text-xs text-muted"
              >
                {citation}
              </li>
            );
          }
          return (
            <li key={citation}>
              <Link
                to={`/laws/${parsed.lawId}/${encodeURIComponent(parsed.article)}`}
                title={`${parsed.article} — ${parsed.lawName}`}
                className="group flex items-center gap-1.5 rounded-lg border border-line bg-surface-2 px-2 py-1 text-xs text-muted transition-colors hover:border-brand/40 hover:text-brand"
              >
                <span className="font-medium text-ink group-hover:text-brand">
                  {parsed.article}
                </span>
                <span className="max-w-[16rem] truncate">{parsed.lawName}</span>
                <ExternalLink className="size-3 shrink-0 opacity-0 group-hover:opacity-100" aria-hidden />
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
