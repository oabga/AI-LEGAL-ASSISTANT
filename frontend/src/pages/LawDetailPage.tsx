import { useEffect, useMemo, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Link2,
  MessagesSquare,
} from "lucide-react";

import { Badge, Button, Card, ErrorState, LoadingState } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { ArticleDetail, LawTreeResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Trang đọc một văn bản: cây Chương-Điều bên trái, nội dung Điều bên phải.
 *
 * Số hiệu văn bản chứa dấu "/" nên route dùng ``/laws/:lawId/*`` và số Điều nằm
 * ở phần splat; ``lawId`` phải ghép lại từ cả hai phần.
 */
function useLawRoute() {
  const params = useParams();
  const lawId = params.lawId ?? "";
  const rest = params["*"] ?? "";

  // "04/2017/QH14/Điều 5" -> lawId="04/2017/QH14", article="Điều 5".
  const segments = rest.split("/").filter(Boolean);
  const articleSegment = segments.length ? segments[segments.length - 1] : "";
  const isArticle = /^(điều|dieu)\s/i.test(decodeURIComponent(articleSegment));

  const fullLawId = [lawId, ...(isArticle ? segments.slice(0, -1) : segments)].join("/");
  return {
    lawId: fullLawId,
    article: isArticle ? decodeURIComponent(articleSegment) : null,
  };
}

export function LawDetailPage() {
  const { lawId, article } = useLawRoute();
  const navigate = useNavigate();
  const activeRef = useRef<HTMLAnchorElement>(null);

  const tree = useQuery({
    queryKey: ["law-tree", lawId],
    queryFn: async () => {
      const { data } = await api.get<LawTreeResponse>(
        `/api/v1/laws/${lawId}/articles`,
      );
      return data;
    },
    enabled: Boolean(lawId),
  });

  const detail = useQuery({
    queryKey: ["article", lawId, article],
    queryFn: async () => {
      const { data } = await api.get<ArticleDetail>(
        `/api/v1/laws/${lawId}/articles/${encodeURIComponent(article!)}`,
      );
      return data;
    },
    enabled: Boolean(lawId && article),
  });

  const firstArticle = tree.data?.chapters[0]?.articles[0]?.article;

  // Mở văn bản mà chưa chọn Điều thì vào thẳng Điều đầu tiên.
  useEffect(() => {
    if (!article && firstArticle) {
      navigate(`/laws/${lawId}/${encodeURIComponent(firstArticle)}`, { replace: true });
    }
  }, [article, firstArticle, lawId, navigate]);

  // Cuộn cây sidebar tới Điều đang đọc.
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [article]);

  const askAiQuestion = useMemo(() => {
    if (!detail.data) return "";
    return (
      `Giải thích ${detail.data.article} (${detail.data.article_title}) của ` +
      `${detail.data.law_name} và ý nghĩa với doanh nghiệp nhỏ và vừa.`
    );
  }, [detail.data]);

  if (tree.isLoading) return <LoadingState label="Đang tải văn bản…" />;
  if (tree.isError) {
    return (
      <ErrorState
        message={errorMessage(tree.error, "Không tải được văn bản")}
        onRetry={() => void tree.refetch()}
      />
    );
  }

  return (
    <div className="flex h-full">
      <aside className="hidden w-80 shrink-0 flex-col border-r border-line bg-sidebar md:flex">
        <div className="border-b border-line-soft p-3">
          <Link
            to="/laws"
            className="mb-2 inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink"
          >
            <ArrowLeft className="size-3.5" aria-hidden />
            Danh mục văn bản
          </Link>
          <p className="text-sm font-medium text-ink">{tree.data?.law.law_name}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <Badge>{tree.data?.law.doc_type}</Badge>
            <span className="text-xs text-muted-2">{tree.data?.law.law_id}</span>
          </div>
        </div>

        <nav className="min-h-0 flex-1 overflow-y-auto p-2">
          {tree.data?.chapters.map((chapter, index) => (
            <div key={`${chapter.chapter}-${index}`} className="mb-3">
              <p className="px-2 pb-1 text-xs font-medium text-muted-2">
                {chapter.chapter ?? "Không thuộc chương nào"}
              </p>
              <ul className="space-y-0.5">
                {chapter.articles.map((item) => {
                  const isActive = item.article === article;
                  return (
                    <li key={item.id}>
                      <Link
                        ref={isActive ? activeRef : undefined}
                        to={`/laws/${lawId}/${encodeURIComponent(item.article)}`}
                        className={cn(
                          "block rounded-lg px-2 py-1.5 text-sm transition-colors",
                          isActive
                            ? "bg-brand-soft text-brand"
                            : "text-muted hover:bg-surface-2 hover:text-ink",
                        )}
                      >
                        <span className="font-medium">{item.article}</span>
                        <span className="ml-1.5 text-muted-2">{item.article_title}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-6">
          {detail.isLoading && <LoadingState />}
          {detail.isError && (
            <ErrorState message={errorMessage(detail.error, "Không tải được điều luật")} />
          )}

          {detail.data && (
            <article>
              <div className="mb-4">
                <p className="text-xs text-muted-2">
                  {detail.data.doc_type} {detail.data.law_id} · {detail.data.law_name}
                  {detail.data.chapter && ` · ${detail.data.chapter}`}
                </p>
                <h1 className="mt-1.5 text-xl font-semibold text-ink">
                  {detail.data.article}. {detail.data.article_title}
                </h1>
                <Button
                  variant="secondary"
                  size="sm"
                  className="mt-3"
                  onClick={() =>
                    navigate("/chat", { state: { question: askAiQuestion } })
                  }
                >
                  <MessagesSquare className="size-4" aria-hidden />
                  Hỏi AI về Điều này
                </Button>
              </div>

              <Card className="p-5">
                <div className="prose-legal whitespace-pre-wrap text-ink">
                  {detail.data.content}
                </div>
              </Card>

              {!!detail.data.related.length && (
                <section className="mt-5">
                  <h2 className="mb-2 flex items-center gap-1.5 text-sm font-medium text-ink">
                    <Link2 className="size-4 text-muted-2" aria-hidden />
                    Viện dẫn chéo ({detail.data.related.length})
                  </h2>
                  <ul className="grid gap-1.5 sm:grid-cols-2">
                    {detail.data.related.map((reference) => (
                      <li key={`${reference.law_id}-${reference.article}`}>
                        <Link
                          to={`/laws/${reference.law_id}/${encodeURIComponent(reference.article)}`}
                          className="block rounded-xl border border-line bg-surface px-3 py-2 text-sm transition-colors hover:border-brand/40"
                        >
                          <span className="font-medium text-ink">{reference.article}</span>
                          <span className="ml-1.5 text-muted">{reference.article_title}</span>
                          <span className="mt-0.5 block truncate text-xs text-muted-2">
                            {reference.law_name}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <nav className="mt-6 flex items-center justify-between gap-2 border-t border-line-soft pt-4">
                {detail.data.previous_article ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      navigate(
                        `/laws/${lawId}/${encodeURIComponent(detail.data!.previous_article!)}`,
                      )
                    }
                  >
                    <ChevronLeft className="size-4" aria-hidden />
                    {detail.data.previous_article}
                  </Button>
                ) : (
                  <span />
                )}
                {detail.data.next_article && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      navigate(`/laws/${lawId}/${encodeURIComponent(detail.data!.next_article!)}`)
                    }
                  >
                    {detail.data.next_article}
                    <ChevronRight className="size-4" aria-hidden />
                  </Button>
                )}
              </nav>
            </article>
          )}
        </div>
      </div>
    </div>
  );
}
