/**
 * Vòng đọc SSE của trang chat.
 *
 * Giữ token đang stream và agent trace trong state cục bộ, chỉ commit vào cache
 * của TanStack Query khi nhận event ``result`` — lúc đó backend đã persist xong
 * message vào PostgreSQL.
 */
import { useCallback, useRef, useState } from "react";

import { API_BASE_URL } from "@/lib/api";
import { streamSse } from "@/lib/sse";
import { getAccessToken } from "@/lib/tokens";
import type {
  AgentTraceStep,
  ChatResponse,
  ChatStreamEvent,
  ChatStreamProgress,
  ProgressStatus,
  RetrievalTraceResult,
} from "@/lib/types";

/** Nhãn tiếng Việt cho từng stage của pipeline RAG. */
const STAGE_LABELS: Record<string, string> = {
  request: "Nhận yêu cầu",
  memory: "Khôi phục ngữ cảnh hội thoại",
  intent: "Phân tích ý định",
  query: "Chuẩn bị truy vấn tra cứu",
  retrieval: "Truy hồi điều luật",
  rerank: "Xếp hạng lại kết quả",
  llm_filter: "Lọc căn cứ bằng LLM",
  answer: "Soạn câu trả lời",
  submission: "Tổng hợp nguồn dẫn",
  response: "Hoàn thiện phản hồi",
};

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

function readTopResults(metadata?: Record<string, unknown>): RetrievalTraceResult[] {
  const results = metadata?.top_results ?? metadata?.results;
  return Array.isArray(results) ? (results as RetrievalTraceResult[]) : [];
}

function toTraceStep(progress: ChatStreamProgress): AgentTraceStep {
  return {
    stage: progress.stage,
    status: progress.status,
    title: stageLabel(progress.stage),
    detail: progress.detail || progress.message,
    elapsedMs: progress.elapsed_ms ?? null,
    topResults: readTopResults(progress.metadata),
  };
}

export type SendOptions = {
  message: string;
  conversationId?: string | null;
  onResult?: (result: ChatResponse) => void;
};

export type ChatStreamState = {
  streaming: boolean;
  /** Token đã nhận, ghép lại thành câu trả lời đang hình thành. */
  answer: string;
  trace: AgentTraceStep[];
  stage: string | null;
  status: ProgressStatus | null;
  error: string | null;
};

const IDLE: ChatStreamState = {
  streaming: false,
  answer: "",
  trace: [],
  stage: null,
  status: null,
  error: null,
};

export function useChatStream() {
  const [state, setState] = useState<ChatStreamState>(IDLE);
  const abortRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState((previous) => ({ ...previous, streaming: false }));
  }, []);

  const reset = useCallback(() => setState(IDLE), []);

  const send = useCallback(async ({ message, conversationId, onResult }: SendOptions) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({ ...IDLE, streaming: true });
    let received: ChatResponse | null = null;

    try {
      await streamSse<ChatStreamEvent>({
        url: `${API_BASE_URL}/api/v1/legal/chat/stream`,
        token: getAccessToken(),
        signal: controller.signal,
        body: {
          message,
          conversation_id: conversationId ?? null,
        },
        onEvent: (event) => {
          switch (event.event) {
            case "token":
              setState((previous) => ({
                ...previous,
                answer: previous.answer + event.data.token,
              }));
              break;

            case "status": {
              const step = toTraceStep(event.data);
              setState((previous) => {
                const trace = [...previous.trace];
                const last = trace[trace.length - 1];
                // Một stage gửi nhiều event (started → running → completed);
                // ghi đè entry cuối để trace không bị lặp dòng.
                if (last && last.stage === step.stage) {
                  trace[trace.length - 1] = {
                    ...step,
                    // Giữ lại kết quả retrieval đã có nếu event sau không mang theo.
                    topResults: step.topResults?.length ? step.topResults : last.topResults,
                  };
                } else {
                  trace.push(step);
                }
                return { ...previous, trace, stage: step.stage, status: step.status };
              });
              break;
            }

            case "result":
              received = event.data;
              setState((previous) => ({
                ...previous,
                // Ưu tiên câu trả lời hoàn chỉnh: token stream có thể thiếu khi
                // token_streaming bị tắt hoặc mất kết nối giữa đường.
                answer: event.data.answer.answer || previous.answer,
              }));
              break;

            case "done":
              setState((previous) => ({ ...previous, streaming: false, status: "completed" }));
              break;

            case "error":
              setState((previous) => ({
                ...previous,
                streaming: false,
                status: "error",
                error: event.data.message,
                trace: [...previous.trace, toTraceStep(event.data)],
              }));
              break;
          }
        },
      });

      if (received) onResult?.(received);
    } catch (caught) {
      if (controller.signal.aborted) {
        setState((previous) => ({ ...previous, streaming: false }));
        return;
      }
      setState((previous) => ({
        ...previous,
        streaming: false,
        status: "error",
        error: caught instanceof Error ? caught.message : "Không gửi được câu hỏi",
      }));
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setState((previous) => ({ ...previous, streaming: false }));
    }
  }, []);

  return { ...state, send, cancel, reset };
}
