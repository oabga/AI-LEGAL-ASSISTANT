import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, ChevronDown, Info, Play, ShieldCheck } from "lucide-react";

import { CitationList } from "@/components/chat/CitationList";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { ContractDocument, Review, RiskLevel } from "@/lib/types";
import { cn, formatRelative } from "@/lib/utils";

const RISK_ORDER: RiskLevel[] = ["cao", "trung bình", "thấp", "thông tin"];

const RISK_STYLES: Record<
  RiskLevel,
  { tone: "danger" | "warn" | "ok" | "neutral"; label: string; icon: typeof AlertTriangle }
> = {
  cao: { tone: "danger", label: "Rủi ro cao", icon: AlertTriangle },
  "trung bình": { tone: "warn", label: "Rủi ro trung bình", icon: AlertTriangle },
  thấp: { tone: "ok", label: "Rủi ro thấp", icon: ShieldCheck },
  "thông tin": { tone: "neutral", label: "Thông tin", icon: Info },
};

/** Điểm rủi ro 0-100: càng cao càng nhiều điều khoản cần sửa. */
function scoreTone(score: number): "danger" | "warn" | "ok" {
  if (score >= 60) return "danger";
  if (score >= 30) return "warn";
  return "ok";
}

export function ContractDetailPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filter, setFilter] = useState<RiskLevel | null>(null);

  const document = useQuery({
    queryKey: ["document", documentId],
    queryFn: async () => {
      const { data } = await api.get<ContractDocument>(`/api/v1/documents/${documentId}`);
      return data;
    },
    enabled: Boolean(documentId),
  });

  const reviewId = document.data?.latest_review_id;

  const review = useQuery({
    queryKey: ["review", reviewId],
    queryFn: async () => {
      const { data } = await api.get<Review>(`/api/v1/reviews/${reviewId}`);
      return data;
    },
    enabled: Boolean(reviewId),
    // Soát xét chạy nền, poll cho tới khi kết thúc.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "processing" ? 2500 : false;
    },
  });

  const start = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<Review>(`/api/v1/documents/${documentId}/review`);
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  if (document.isLoading) return <LoadingState />;
  if (document.isError) {
    return <ErrorState message={errorMessage(document.error, "Không tìm thấy hợp đồng")} />;
  }

  const data = review.data;
  const running = data?.status === "pending" || data?.status === "processing";
  const findings = (data?.findings ?? []).filter(
    (finding) => !filter || finding.risk_level === filter,
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-4 py-6">
        <button
          type="button"
          onClick={() => navigate("/contracts")}
          className="mb-3 inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          Danh sách hợp đồng
        </button>

        <header className="mb-5">
          <h1 className="text-xl font-semibold text-ink">{document.data?.filename}</h1>
          <p className="mt-1 text-sm text-muted">
            Tải lên {formatRelative(document.data!.created_at)} ·{" "}
            {document.data?.text_length.toLocaleString("vi-VN")} ký tự
          </p>
        </header>

        {!reviewId && (
          <EmptyState
            icon={<Play className="size-8" />}
            title="Chưa soát xét hợp đồng này"
            description="Quá trình soát xét tách từng điều khoản và đối chiếu với kho văn bản pháp luật."
            action={
              <Button loading={start.isPending} onClick={() => start.mutate()}>
                Bắt đầu soát xét
              </Button>
            }
          />
        )}

        {running && (
          <Card className="p-5">
            <LoadingState label="Đang đối chiếu từng điều khoản với văn bản pháp luật…" />
            <p className="text-center text-xs text-muted-2">
              Quá trình này mất khoảng một đến hai phút cho hợp đồng thông thường.
            </p>
          </Card>
        )}

        {data?.status === "failed" && (
          <div className="space-y-3">
            <Alert>{data.error_message ?? "Soát xét thất bại"}</Alert>
            <Button variant="secondary" loading={start.isPending} onClick={() => start.mutate()}>
              Thử lại
            </Button>
          </div>
        )}

        {data?.status === "done" && (
          <div className="space-y-4">
            <Card className="p-5">
              <div className="flex flex-wrap items-center gap-5">
                <div>
                  <p className="text-xs tracking-wide text-muted-2 uppercase">Điểm rủi ro</p>
                  <p
                    className={cn(
                      "text-3xl font-semibold tabular-nums",
                      scoreTone(data.risk_score) === "danger" && "text-danger",
                      scoreTone(data.risk_score) === "warn" && "text-warn",
                      scoreTone(data.risk_score) === "ok" && "text-ok",
                    )}
                  >
                    {data.risk_score}
                    <span className="text-base text-muted-2">/100</span>
                  </p>
                </div>
                <div className="h-12 w-px bg-line" />
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => setFilter(null)}>
                    <Badge tone={filter === null ? "brand" : "neutral"}>
                      Tất cả {data.clause_count} điều khoản
                    </Badge>
                  </button>
                  {RISK_ORDER.filter((level) => data.risk_counts[level]).map((level) => (
                    <button key={level} type="button" onClick={() => setFilter(level)}>
                      <Badge tone={filter === level ? "brand" : RISK_STYLES[level].tone}>
                        {RISK_STYLES[level].label}: {data.risk_counts[level]}
                      </Badge>
                    </button>
                  ))}
                </div>
              </div>

              {data.summary && (
                <div className="mt-4 border-t border-line-soft pt-4">
                  <p className="mb-1.5 text-xs font-medium tracking-wide text-muted-2 uppercase">
                    Nhận định tổng quan
                  </p>
                  <p className="text-sm leading-relaxed whitespace-pre-wrap text-muted">
                    {data.summary}
                  </p>
                </div>
              )}
            </Card>

            <Card>
              <CardHeader
                title="Chi tiết rủi ro"
                description={`${findings.length} phát hiện${filter ? ` ở mức ${filter}` : ""}`}
              />
              <ul className="divide-y divide-line-soft">
                {findings.map((finding) => {
                  const style = RISK_STYLES[finding.risk_level];
                  const Icon = style.icon;
                  const isOpen = expanded === finding.id;
                  return (
                    <li key={finding.id} className="px-5 py-4">
                      <div className="flex items-start gap-3">
                        <Icon
                          className={cn(
                            "mt-0.5 size-4 shrink-0",
                            style.tone === "danger" && "text-danger",
                            style.tone === "warn" && "text-warn",
                            style.tone === "ok" && "text-ok",
                            style.tone === "neutral" && "text-muted-2",
                          )}
                          aria-hidden
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium text-ink">
                              {finding.clause_title || `Điều khoản ${finding.position + 1}`}
                            </span>
                            <Badge tone={style.tone}>{style.label}</Badge>
                          </div>
                          <p className="mt-1.5 text-sm text-muted">{finding.issue}</p>

                          {finding.recommendation && (
                            <p className="mt-2 rounded-xl border border-brand/20 bg-brand-soft px-3 py-2 text-sm text-brand">
                              <span className="font-medium">Đề xuất: </span>
                              {finding.recommendation}
                            </p>
                          )}

                          <button
                            type="button"
                            onClick={() => setExpanded(isOpen ? null : finding.id)}
                            className="mt-2 inline-flex items-center gap-1 text-xs text-muted hover:text-ink"
                          >
                            <ChevronDown
                              className={cn("size-3.5 transition-transform", !isOpen && "-rotate-90")}
                              aria-hidden
                            />
                            Nguyên văn điều khoản
                          </button>
                          {isOpen && (
                            <p className="mt-1.5 rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap text-muted">
                              {finding.clause_text}
                            </p>
                          )}

                          <CitationList citations={finding.legal_refs} />
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Card>

            <p className="text-center text-xs text-muted-2">
              Kết quả mang tính tham khảo. Xem nguyên văn điều luật tại{" "}
              <Link to="/laws" className="text-brand hover:underline">
                trang tra cứu
              </Link>{" "}
              trước khi quyết định.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
