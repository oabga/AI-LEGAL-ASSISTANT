import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { BookText, Search } from "lucide-react";

import {
  Badge,
  Card,
  EmptyState,
  Input,
  LoadingState,
  Select,
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { LawListResponse, SearchResponse } from "@/lib/types";
import { highlightSegments, snippetAround } from "@/lib/utils";

/** Nhãn giải thích chiến lược tìm kiếm mà backend đã dùng. */
const STRATEGY_LABELS: Record<SearchResponse["strategy"], string> = {
  article_number: "tra theo số Điều",
  full_text: "full-text search",
  trigram: "so khớp gần đúng",
  empty: "truy vấn rỗng",
};

function Highlighted({ text, terms }: { text: string; terms: string[] }) {
  return (
    <>
      {highlightSegments(text, terms).map((segment, index) =>
        segment.match ? (
          <mark key={index} className="rounded bg-warn-bg px-0.5 text-warn">
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}

export function LawsPage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [docType, setDocType] = useState("");

  const trimmed = query.trim();
  const searching = trimmed.length >= 2;

  const laws = useQuery({
    queryKey: ["laws", category, docType],
    queryFn: async () => {
      const { data } = await api.get<LawListResponse>("/api/v1/laws", {
        params: { category: category || undefined, doc_type: docType || undefined, limit: 200 },
      });
      return data;
    },
  });

  const search = useQuery({
    queryKey: ["laws-search", trimmed, docType],
    queryFn: async () => {
      const { data } = await api.get<SearchResponse>("/api/v1/laws/search", {
        params: { q: trimmed, doc_type: docType || undefined, limit: 30 },
      });
      return data;
    },
    enabled: searching,
    // Giữ kết quả cũ trong lúc gõ để danh sách không nhấp nháy.
    placeholderData: keepPreviousData,
  });

  const grouped = useMemo(() => {
    const items = laws.data?.items ?? [];
    const byCategory = new Map<string, typeof items>();
    for (const law of items) {
      const bucket = byCategory.get(law.category) ?? [];
      bucket.push(law);
      byCategory.set(law.category, bucket);
    }
    return [...byCategory.entries()].sort((a, b) => a[0].localeCompare(b[0], "vi"));
  }, [laws.data]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-6">
        <header className="mb-5">
          <h1 className="text-xl font-semibold text-ink">Tra cứu văn bản pháp luật</h1>
          <p className="mt-1 text-sm text-muted">
            Tìm đúng từ khóa trong {laws.data?.total ?? "…"} văn bản đã nạp. Không cần gõ dấu.
          </p>
        </header>

        <div className="mb-5 flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-2" aria-hidden />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ví dụ: hop dong lao dong, thue GTGT, Điều 5 Luật Doanh nghiệp"
              className="pl-9"
            />
            {search.isFetching && (
              <span className="absolute top-1/2 right-3 -translate-y-1/2">
                <Spinner />
              </span>
            )}
          </div>
          <Select
            value={docType}
            onChange={(event) => setDocType(event.target.value)}
            className="sm:w-44"
          >
            <option value="">Mọi loại văn bản</option>
            {laws.data?.doc_types.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </Select>
          {!searching && (
            <Select
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              className="sm:w-52"
            >
              <option value="">Mọi lĩnh vực</option>
              {laws.data?.categories.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
          )}
        </div>

        {searching ? (
          <section>
            {search.isLoading && <LoadingState label="Đang tìm…" />}
            {search.data && (
              <>
                <p className="mb-3 text-sm text-muted">
                  {search.data.total} kết quả cho{" "}
                  <span className="text-ink">“{search.data.query}”</span>
                  <span className="text-muted-2">
                    {" "}
                    · {STRATEGY_LABELS[search.data.strategy]}
                  </span>
                </p>
                {!search.data.items.length ? (
                  <EmptyState
                    icon={<Search className="size-8" />}
                    title="Không tìm thấy điều luật nào"
                    description="Thử từ khóa ngắn hơn, hoặc bỏ bộ lọc loại văn bản."
                  />
                ) : (
                  <ul className="space-y-2.5">
                    {search.data.items.map((hit) => (
                      <li key={hit.id}>
                        <Link
                          to={`/laws/${hit.law_id}/${encodeURIComponent(hit.article)}`}
                          className="block rounded-2xl border border-line bg-surface p-4 transition-colors hover:border-brand/40"
                        >
                          <div className="mb-1.5 flex flex-wrap items-center gap-2">
                            <Badge tone="brand">{hit.article}</Badge>
                            <span className="text-sm font-medium text-ink">
                              <Highlighted text={hit.article_title} terms={search.data.terms} />
                            </span>
                          </div>
                          <p className="mb-2 text-xs text-muted-2">
                            {hit.doc_type} {hit.law_id} · {hit.law_name}
                            {hit.chapter && ` · ${hit.chapter}`}
                          </p>
                          <p className="text-sm leading-relaxed text-muted">
                            <Highlighted
                              text={snippetAround(hit.content, search.data.terms)}
                              terms={search.data.terms}
                            />
                          </p>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </section>
        ) : (
          <section className="space-y-5">
            {laws.isLoading && <LoadingState />}
            {grouped.map(([groupName, items]) => (
              <div key={groupName}>
                <h2 className="mb-2 text-sm font-medium tracking-wide text-muted-2 uppercase">
                  {groupName}
                </h2>
                <div className="grid gap-2 sm:grid-cols-2">
                  {items.map((law) => (
                    <Link key={law.law_id} to={`/laws/${law.law_id}`}>
                      <Card className="h-full p-4 transition-colors hover:border-brand/40">
                        <div className="mb-1.5 flex items-start gap-2">
                          <BookText className="mt-0.5 size-4 shrink-0 text-muted-2" aria-hidden />
                          <span className="text-sm font-medium text-ink">{law.law_name}</span>
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 pl-6">
                          <Badge>{law.doc_type}</Badge>
                          <span className="text-xs text-muted-2">{law.law_id}</span>
                          <span className="text-xs text-muted-2">
                            · {law.article_count} điều
                          </span>
                        </div>
                      </Card>
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
