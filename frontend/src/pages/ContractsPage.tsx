import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSearch, FileText, Trash2, Upload } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  LoadingState,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { ContractDocument, DocumentStatus, Paginated, Review } from "@/lib/types";
import { formatBytes, formatRelative } from "@/lib/utils";

const ACCEPTED = ".pdf,.docx,.txt";

const STATUS_BADGES: Record<DocumentStatus, { label: string; tone: "neutral" | "brand" | "ok" | "warn" | "danger" }> = {
  pending: { label: "Chờ xử lý", tone: "neutral" },
  ready: { label: "Sẵn sàng soát xét", tone: "brand" },
  processing: { label: "Đang soát xét", tone: "warn" },
  done: { label: "Đã soát xét", tone: "ok" },
  failed: { label: "Lỗi", tone: "danger" },
};

export function ContractsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const documents = useQuery({
    queryKey: ["documents"],
    queryFn: async () => {
      const { data } = await api.get<Paginated<ContractDocument>>("/api/v1/documents");
      return data;
    },
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post<ContractDocument>("/api/v1/documents", form);
      return data;
    },
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (caught) => setError(errorMessage(caught, "Không tải được file lên")),
  });

  const review = useMutation({
    mutationFn: async (documentId: string) => {
      const { data } = await api.post<Review>(`/api/v1/documents/${documentId}/review`);
      return data;
    },
    onSuccess: (data) => navigate(`/contracts/${data.document_id}`),
    onError: (caught) => setError(errorMessage(caught, "Không khởi động được soát xét")),
  });

  const remove = useMutation({
    mutationFn: async (documentId: string) => {
      await api.delete(`/api/v1/documents/${documentId}`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });

  const items = documents.data?.items ?? [];

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-4 py-6">
        <header className="mb-5">
          <h1 className="text-xl font-semibold text-ink">Soát xét hợp đồng</h1>
          <p className="mt-1 text-sm text-muted">
            Tải hợp đồng lên, hệ thống tách từng điều khoản và đối chiếu với văn bản pháp
            luật để chỉ ra rủi ro kèm căn cứ.
          </p>
        </header>

        {error && (
          <div className="mb-4">
            <Alert>{error}</Alert>
          </div>
        )}

        <label
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const file = event.dataTransfer.files[0];
            if (file) upload.mutate(file);
          }}
          className={`mb-6 flex cursor-pointer flex-col items-center gap-2 rounded-2xl border border-dashed px-6 py-10 text-center transition-colors ${
            dragging ? "border-brand bg-brand-soft" : "border-line hover:border-brand/40"
          }`}
        >
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPTED}
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) upload.mutate(file);
              // Reset để chọn lại cùng một file vẫn kích hoạt onChange.
              event.target.value = "";
            }}
          />
          {upload.isPending ? (
            <LoadingState label="Đang tải lên và trích nội dung…" />
          ) : (
            <>
              <Upload className="size-7 text-muted-2" aria-hidden />
              <p className="text-sm font-medium text-ink">
                Kéo file vào đây hoặc bấm để chọn
              </p>
              <p className="text-xs text-muted-2">PDF, DOCX hoặc TXT, tối đa 10 MB</p>
            </>
          )}
        </label>

        {documents.isLoading && <LoadingState />}

        {!documents.isLoading && !items.length && (
          <EmptyState
            icon={<FileText className="size-8" />}
            title="Chưa có hợp đồng nào"
            description="Tải hợp đồng đầu tiên lên để nhận báo cáo rủi ro."
            action={
              <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
                Chọn file
              </Button>
            }
          />
        )}

        <ul className="space-y-2">
          {items.map((document) => {
            const badge = STATUS_BADGES[document.status];
            return (
              <li key={document.id}>
                <Card className="flex flex-wrap items-center gap-3 p-4">
                  <FileText className="size-5 shrink-0 text-muted-2" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{document.filename}</p>
                    <p className="text-xs text-muted-2">
                      {formatBytes(document.size_bytes)} ·{" "}
                      {document.text_length.toLocaleString("vi-VN")} ký tự ·{" "}
                      {formatRelative(document.created_at)}
                    </p>
                    {document.error_message && (
                      <p className="mt-1 text-xs text-danger">{document.error_message}</p>
                    )}
                  </div>
                  <Badge tone={badge.tone}>{badge.label}</Badge>

                  {document.latest_review_id ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => navigate(`/contracts/${document.id}`)}
                    >
                      <FileSearch className="size-4" aria-hidden />
                      Xem kết quả
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      loading={review.isPending && review.variables === document.id}
                      onClick={() => review.mutate(document.id)}
                    >
                      Soát xét
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Xóa hợp đồng"
                    className="hover:text-danger"
                    onClick={() => remove.mutate(document.id)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </Card>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
