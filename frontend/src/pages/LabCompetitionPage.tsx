/**
 * Trang chạy tập test cuộc thi.
 *
 * Giữ lại để chương 4 khóa luận còn chỗ tái tạo số liệu thi đấu: upload bộ test
 * JSON, xem tiến độ qua SSE, tải về ``results.json`` đúng format submit.
 */
import { useRef, useState } from "react";
import { Download, FlaskConical, Play, Square, Upload } from "lucide-react";

import { Alert, Badge, Button, Card, CardHeader, EmptyState } from "@/components/ui";
import { API_BASE_URL } from "@/lib/api";
import { streamSse } from "@/lib/sse";
import { getAccessToken } from "@/lib/tokens";
import type { ChatStreamProgress } from "@/lib/types";
import { formatDuration } from "@/lib/utils";

type CompetitionRecord = {
  id: number;
  question: string;
  answer: string;
  relevant_docs: string[];
  relevant_articles: string[];
};

type LabEvent =
  | { event: "status"; data: ChatStreamProgress }
  | { event: "done"; data: ChatStreamProgress }
  | { event: "error"; data: ChatStreamProgress }
  | { event: "competition_item_result"; data: CompetitionRecord & { index: number; total: number } }
  | { event: "competition_result"; data: CompetitionRecord[] };

export function LabCompetitionPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [testset, setTestset] = useState<{ name: string; items: unknown[] } | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<ChatStreamProgress | null>(null);
  const [records, setRecords] = useState<CompetitionRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function loadFile(file: File) {
    setError(null);
    try {
      const parsed = JSON.parse(await file.text());
      if (!Array.isArray(parsed)) throw new Error("File phải là một mảng JSON");
      setTestset({ name: file.name, items: parsed });
      setRecords([]);
      setProgress(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không đọc được file");
    }
  }

  async function run() {
    if (!testset) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setRecords([]);
    setError(null);

    try {
      await streamSse<LabEvent>({
        url: `${API_BASE_URL}/api/v1/lab/competition/stream`,
        token: getAccessToken(),
        signal: controller.signal,
        body: testset.items,
        onEvent: (event) => {
          switch (event.event) {
            case "status":
            case "done":
              setProgress(event.data);
              break;
            case "error":
              setProgress(event.data);
              setError(event.data.message);
              break;
            case "competition_item_result":
              // Một câu xong là hiện ngay, không đợi cả bộ test.
              setRecords((previous) => [...previous, event.data]);
              break;
            case "competition_result":
              setRecords(event.data);
              break;
          }
        },
      });
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : "Chạy tập test thất bại");
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  function download() {
    const blob = new Blob([JSON.stringify(records, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "results.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const total = testset?.items.length ?? 0;
  const percent = total ? Math.round((records.length / total) * 100) : 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-4 px-4 py-6">
        <header>
          <h1 className="text-xl font-semibold text-ink">Competition mode</h1>
          <p className="mt-1 text-sm text-muted">
            Chạy tập test theo format cuộc thi. Bỏ qua bước phân tích ý định và không dùng
            lịch sử hội thoại để kết quả tái lập được.
          </p>
        </header>

        {error && <Alert>{error}</Alert>}

        <Card>
          <CardHeader
            title="Bộ test"
            description={
              testset
                ? `${testset.name} · ${total} câu hỏi`
                : "File JSON dạng mảng các object có id và question."
            }
            action={
              <div className="flex gap-2">
                <input
                  ref={fileRef}
                  type="file"
                  accept=".json"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void loadFile(file);
                    event.target.value = "";
                  }}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={running}
                  onClick={() => fileRef.current?.click()}
                >
                  <Upload className="size-4" aria-hidden />
                  Chọn file
                </Button>
                {running ? (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => abortRef.current?.abort()}
                  >
                    <Square className="size-3.5" aria-hidden />
                    Dừng
                  </Button>
                ) : (
                  <Button size="sm" disabled={!testset} onClick={() => void run()}>
                    <Play className="size-4" aria-hidden />
                    Chạy
                  </Button>
                )}
                {!!records.length && !running && (
                  <Button variant="secondary" size="sm" onClick={download}>
                    <Download className="size-4" aria-hidden />
                    results.json
                  </Button>
                )}
              </div>
            }
          />

          {(running || progress) && (
            <div className="border-b border-line-soft px-5 py-4">
              <div className="mb-2 flex items-center justify-between text-xs text-muted">
                <span>{progress?.message ?? "Đang chuẩn bị…"}</span>
                <span className="tabular-nums">
                  {records.length}/{total}
                  {progress?.elapsed_ms != null && ` · ${formatDuration(progress.elapsed_ms)}`}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                <div
                  className="h-full rounded-full bg-brand transition-all"
                  style={{ width: `${percent}%` }}
                />
              </div>
              {progress?.detail && (
                <p className="mt-2 text-xs text-muted-2">{progress.detail}</p>
              )}
            </div>
          )}

          {!records.length && !running && (
            <EmptyState
              icon={<FlaskConical className="size-8" />}
              title="Chưa có kết quả"
              description="Chọn bộ test rồi bấm Chạy. Kết quả từng câu hiện dần và được lưu vào outputs/ trên server."
            />
          )}

          <ul className="divide-y divide-line-soft">
            {records.map((record, index) => (
              <li key={`${record.id}-${index}`} className="px-5 py-4">
                <div className="mb-1.5 flex items-start gap-2">
                  <Badge>#{record.id}</Badge>
                  <span className="min-w-0 flex-1 text-sm font-medium text-ink">
                    {record.question}
                  </span>
                </div>
                <p className="line-clamp-3 text-sm text-muted">{record.answer}</p>
                {!!record.relevant_articles.length && (
                  <p className="mt-1.5 text-xs text-muted-2">
                    {record.relevant_articles.length} điều luật:{" "}
                    {record.relevant_articles.slice(0, 4).join("; ")}
                    {record.relevant_articles.length > 4 && "…"}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
