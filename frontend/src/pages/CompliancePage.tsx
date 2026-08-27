import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarCheck,
  CalendarClock,
  CheckCircle2,
  ListChecks,
  RefreshCw,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Select,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type {
  ComplianceFrequency,
  ComplianceStatus,
  ComplianceSummary,
  ComplianceTask,
  Paginated,
} from "@/lib/types";
import { cn, describeDueDays, formatDate, parseReference } from "@/lib/utils";

const FREQUENCY_LABELS: Record<ComplianceFrequency, string> = {
  monthly: "Hàng tháng",
  quarterly: "Hàng quý",
  annual: "Hàng năm",
  one_time: "Một lần",
};

const STATUS_LABELS: Record<ComplianceStatus, string> = {
  pending: "Chưa làm",
  done: "Đã hoàn thành",
  skipped: "Bỏ qua",
};

function StatCard({
  icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone?: "neutral" | "brand" | "ok" | "warn" | "danger";
}) {
  const tones = {
    neutral: "text-muted",
    brand: "text-brand",
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
  } as const;
  return (
    <Card className="flex items-center gap-3 p-4">
      <span className={cn("shrink-0", tones[tone])}>{icon}</span>
      <div>
        <p className="text-2xl leading-none font-semibold tabular-nums text-ink">{value}</p>
        <p className="mt-1 text-xs text-muted-2">{label}</p>
      </div>
    </Card>
  );
}

export function CompliancePage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<ComplianceStatus | "">("pending");

  const summary = useQuery({
    queryKey: ["compliance-summary"],
    queryFn: async () => {
      const { data } = await api.get<ComplianceSummary>("/api/v1/compliance/summary");
      return data;
    },
  });

  const tasks = useQuery({
    queryKey: ["compliance-tasks", statusFilter],
    queryFn: async () => {
      const { data } = await api.get<Paginated<ComplianceTask>>("/api/v1/compliance/tasks", {
        params: { status: statusFilter || undefined },
      });
      return data;
    },
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["compliance-tasks"] });
    void queryClient.invalidateQueries({ queryKey: ["compliance-summary"] });
  };

  const update = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: ComplianceStatus }) => {
      await api.patch(`/api/v1/compliance/tasks/${id}`, { status });
    },
    onSuccess: invalidate,
  });

  const regenerate = useMutation({
    mutationFn: async () => {
      await api.post("/api/v1/compliance/tasks/generate");
    },
    onSuccess: invalidate,
  });

  // Nhóm theo tháng đến hạn để đọc như một cuốn lịch.
  const grouped = useMemo(() => {
    const buckets = new Map<string, ComplianceTask[]>();
    for (const task of tasks.data?.items ?? []) {
      const key = task.due_date.slice(0, 7);
      const bucket = buckets.get(key) ?? [];
      bucket.push(task);
      buckets.set(key, bucket);
    }
    return [...buckets.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [tasks.data]);

  if (summary.isError) {
    return (
      <ErrorState
        message={errorMessage(summary.error, "Không tải được lịch tuân thủ")}
        onRetry={() => void summary.refetch()}
      />
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-4 py-6">
        <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-ink">Lịch tuân thủ</h1>
            <p className="mt-1 text-sm text-muted">
              Nghĩa vụ định kỳ sinh theo hồ sơ doanh nghiệp của bạn, mỗi nghĩa vụ đều dẫn
              về Điều luật căn cứ.
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            loading={regenerate.isPending}
            onClick={() => regenerate.mutate()}
          >
            <RefreshCw className="size-4" aria-hidden />
            Sinh lại lịch
          </Button>
        </header>

        {summary.data && (
          <div className="mb-5 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            <StatCard
              icon={<ListChecks className="size-5" />}
              label="Tổng nghĩa vụ"
              value={summary.data.total}
            />
            <StatCard
              icon={<TriangleAlert className="size-5" />}
              label="Đã quá hạn"
              value={summary.data.overdue}
              tone="danger"
            />
            <StatCard
              icon={<CalendarClock className="size-5" />}
              label="Hạn trong 30 ngày"
              value={summary.data.due_soon}
              tone="warn"
            />
            <StatCard
              icon={<CheckCircle2 className="size-5" />}
              label="Đã hoàn thành"
              value={summary.data.done}
              tone="ok"
            />
          </div>
        )}

        {summary.data?.next_due && (
          <Card className="mb-5 border-brand/30 bg-brand-soft p-4">
            <p className="text-xs font-medium tracking-wide text-brand uppercase">
              Việc gần nhất
            </p>
            <p className="mt-1 text-sm font-medium text-ink">
              {summary.data.next_due.rule.title}
            </p>
            <p className="mt-0.5 text-sm text-muted">
              {summary.data.next_due.period_label} · hạn{" "}
              {formatDate(summary.data.next_due.due_date)} ·{" "}
              {describeDueDays(summary.data.next_due.days_remaining)}
            </p>
          </Card>
        )}

        <div className="mb-3 flex items-center gap-2">
          <Select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as ComplianceStatus | "")}
            className="w-44"
          >
            <option value="">Mọi trạng thái</option>
            <option value="pending">Chưa làm</option>
            <option value="done">Đã hoàn thành</option>
            <option value="skipped">Bỏ qua</option>
          </Select>
          <span className="text-sm text-muted-2">{tasks.data?.total ?? 0} nghĩa vụ</span>
        </div>

        {tasks.isLoading && <LoadingState />}

        {!tasks.isLoading && !grouped.length && (
          <EmptyState
            icon={<CalendarCheck className="size-8" />}
            title="Chưa có nghĩa vụ nào"
            description="Bổ sung thông tin doanh nghiệp trong trang cá nhân rồi bấm Sinh lại lịch."
          />
        )}

        <div className="space-y-5">
          {grouped.map(([month, items]) => (
            <section key={month}>
              <h2 className="mb-2 text-sm font-medium tracking-wide text-muted-2 uppercase">
                Tháng {month.slice(5)}/{month.slice(0, 4)}
              </h2>
              <ul className="space-y-2">
                {items.map((task) => (
                  <li key={task.id}>
                    <Card
                      className={cn(
                        "p-4",
                        task.overdue && "border-danger/30",
                        task.status === "done" && "opacity-70",
                      )}
                    >
                      <div className="flex flex-wrap items-start gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium text-ink">
                              {task.rule.title}
                            </span>
                            <Badge>{FREQUENCY_LABELS[task.rule.frequency]}</Badge>
                            <Badge tone="neutral">{task.rule.category}</Badge>
                            {task.status !== "pending" && (
                              <Badge tone={task.status === "done" ? "ok" : "neutral"}>
                                {STATUS_LABELS[task.status]}
                              </Badge>
                            )}
                          </div>

                          <p className="mt-1 text-sm text-muted">
                            {task.period_label} · hạn {formatDate(task.due_date)} ·{" "}
                            <span
                              className={cn(
                                task.overdue && "text-danger",
                                !task.overdue &&
                                  task.days_remaining <= 7 &&
                                  task.status === "pending" &&
                                  "text-warn",
                              )}
                            >
                              {task.status === "pending"
                                ? describeDueDays(task.days_remaining)
                                : `hoàn thành ${formatDate(task.completed_at)}`}
                            </span>
                          </p>

                          {task.rule.description && (
                            <p className="mt-1 text-xs text-muted-2">{task.rule.description}</p>
                          )}

                          {!!task.rule.references?.length && (
                            <ul className="mt-2 flex flex-wrap gap-1.5">
                              {task.rule.references.map((reference) => (
                                <li key={`${reference.law_id}-${reference.article}`}>
                                  <Link
                                    to={`/laws/${reference.law_id}/${encodeURIComponent(reference.article)}`}
                                    title={reference.article_title}
                                    className="flex items-center gap-1.5 rounded-lg border border-line bg-surface-2 px-2 py-1 text-xs text-muted hover:border-brand/40 hover:text-brand"
                                  >
                                    <span className="font-medium">{reference.article}</span>
                                    <span className="max-w-[14rem] truncate">
                                      {reference.law_name}
                                    </span>
                                  </Link>
                                </li>
                              ))}
                            </ul>
                          )}

                          {!task.rule.references?.length && !!task.rule.legal_refs.length && (
                            <p className="mt-2 text-xs text-muted-2">
                              Căn cứ:{" "}
                              {task.rule.legal_refs
                                .map((reference) => parseReference(reference)?.article ?? reference)
                                .join(", ")}
                            </p>
                          )}
                        </div>

                        {task.status === "pending" ? (
                          <div className="flex gap-1.5">
                            <Button
                              size="sm"
                              onClick={() => update.mutate({ id: task.id, status: "done" })}
                            >
                              <CheckCircle2 className="size-4" aria-hidden />
                              Hoàn thành
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => update.mutate({ id: task.id, status: "skipped" })}
                            >
                              Bỏ qua
                            </Button>
                          </div>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => update.mutate({ id: task.id, status: "pending" })}
                          >
                            <RotateCcw className="size-4" aria-hidden />
                            Hoàn tác
                          </Button>
                        )}
                      </div>
                    </Card>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
