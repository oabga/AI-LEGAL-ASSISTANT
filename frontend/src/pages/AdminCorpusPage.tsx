import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, RefreshCw, Upload } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  LoadingState,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { CorpusStats } from "@/lib/types";

type ImportResponse = { inserted: number; updated: number; skipped: number; total: number };
type ReindexResponse = { index_ready: boolean; indexed_vectors: number; message: string };

export function AdminCorpusPage() {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);

  const stats = useQuery({
    queryKey: ["corpus-stats"],
    queryFn: async () => {
      const { data } = await api.get<CorpusStats>("/api/v1/admin/corpus/stats");
      return data;
    },
  });

  const importCorpus = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post<ImportResponse>("/api/v1/admin/corpus/import", form);
      return data;
    },
    onSuccess: (data) => {
      setMessage({
        tone: "ok",
        text:
          `Đã nạp ${data.total} bản ghi: thêm mới ${data.inserted}, cập nhật ${data.updated}` +
          `${data.skipped ? `, bỏ qua ${data.skipped}` : ""}. Cần reindex để tìm kiếm ngữ nghĩa dùng dữ liệu mới.`,
      });
      void queryClient.invalidateQueries({ queryKey: ["corpus-stats"] });
    },
    onError: (caught) =>
      setMessage({ tone: "danger", text: errorMessage(caught, "Không nạp được corpus") }),
  });

  const reindex = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ReindexResponse>("/api/v1/admin/corpus/reindex");
      return data;
    },
    onSuccess: (data) => {
      setMessage({ tone: "ok", text: data.message });
      void queryClient.invalidateQueries({ queryKey: ["corpus-stats"] });
    },
    onError: (caught) =>
      setMessage({ tone: "danger", text: errorMessage(caught, "Reindex thất bại") }),
  });

  const data = stats.data;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-4 px-4 py-6">
        <header>
          <h1 className="text-xl font-semibold text-ink">Quản trị corpus</h1>
          <p className="mt-1 text-sm text-muted">
            Kho văn bản pháp luật dùng cho cả tra cứu full-text và truy hồi ngữ nghĩa.
          </p>
        </header>

        {message && <Alert tone={message.tone}>{message.text}</Alert>}

        {stats.isLoading && <LoadingState />}

        {data && (
          <>
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              {[
                { label: "Điều luật", value: data.total_articles.toLocaleString("vi-VN") },
                { label: "Văn bản", value: data.total_laws.toLocaleString("vi-VN") },
                { label: "Vector đã index", value: data.indexed_vectors.toLocaleString("vi-VN") },
                {
                  label: "Trạng thái index",
                  value: data.index_ready ? "Sẵn sàng" : "Chưa dựng",
                },
              ].map((item) => (
                <Card key={item.label} className="p-4">
                  <p className="text-2xl leading-none font-semibold tabular-nums text-ink">
                    {item.value}
                  </p>
                  <p className="mt-1.5 text-xs text-muted-2">{item.label}</p>
                </Card>
              ))}
            </div>

            <Card>
              <CardHeader
                title="Vector index"
                description={
                  data.embedding_model
                    ? `Embedding model: ${data.embedding_model}`
                    : "Chưa xác định embedding model"
                }
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={reindex.isPending}
                    onClick={() => reindex.mutate()}
                  >
                    <RefreshCw className="size-4" aria-hidden />
                    Reindex
                  </Button>
                }
              />
              <div className="px-5 py-4 text-sm text-muted">
                Reindex nạp lại toàn bộ điều luật vào Chroma và dựng lại cache BM25. Quá
                trình bỏ qua những điều đã có vector, chỉ dựng lại từ đầu khi đổi embedding
                model hoặc số chiều.
              </div>
            </Card>

            <Card>
              <CardHeader
                title="Nạp thêm văn bản"
                description="File JSON dạng mảng các bản ghi có law_id, article, content."
                action={
                  <>
                    <input
                      ref={fileRef}
                      type="file"
                      accept=".json"
                      className="hidden"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) importCorpus.mutate(file);
                        event.target.value = "";
                      }}
                    />
                    <Button
                      size="sm"
                      loading={importCorpus.isPending}
                      onClick={() => fileRef.current?.click()}
                    >
                      <Upload className="size-4" aria-hidden />
                      Chọn file JSON
                    </Button>
                  </>
                }
              />
              <div className="px-5 py-4 text-sm text-muted">
                Bản ghi trùng khóa (law_id + article) được cập nhật nội dung thay vì tạo mới,
                nên nạp lại cùng một file nhiều lần là an toàn.
              </div>
            </Card>

            <Card>
              <CardHeader title="Văn bản nhiều điều nhất" />
              <ul className="divide-y divide-line-soft">
                {data.largest_laws.map((law) => (
                  <li
                    key={law.law_id}
                    className="flex flex-wrap items-center gap-2 px-5 py-3 text-sm"
                  >
                    <Database className="size-4 shrink-0 text-muted-2" aria-hidden />
                    <span className="min-w-0 flex-1 truncate text-ink">{law.law_name}</span>
                    <Badge>{law.doc_type}</Badge>
                    <Badge tone="brand">{law.category}</Badge>
                    <span className="tabular-nums text-muted-2">{law.article_count} điều</span>
                  </li>
                ))}
              </ul>
            </Card>

            <div className="grid gap-4 sm:grid-cols-2">
              <Card>
                <CardHeader title="Theo loại văn bản" />
                <ul className="divide-y divide-line-soft">
                  {Object.entries(data.by_doc_type).map(([key, value]) => (
                    <li key={key} className="flex justify-between px-5 py-2.5 text-sm">
                      <span className="text-muted">{key}</span>
                      <span className="tabular-nums text-ink">{value.toLocaleString("vi-VN")}</span>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card>
                <CardHeader title="Theo lĩnh vực" />
                <ul className="divide-y divide-line-soft">
                  {Object.entries(data.by_category).map(([key, value]) => (
                    <li key={key} className="flex justify-between px-5 py-2.5 text-sm">
                      <span className="text-muted">{key}</span>
                      <span className="tabular-nums text-ink">{value.toLocaleString("vi-VN")}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
