import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useChatStream } from "@/hooks/useChatStream";
import { stubSseFetch, type FetchStub, type SsePacket } from "@/test/sseServer";
import type { ChatResponse } from "@/lib/types";

let stub: FetchStub | null = null;

afterEach(() => {
  stub?.restore();
  stub = null;
});

function answer(text: string, citations: string[] = []): ChatResponse {
  return {
    conversation_id: "6f1c9e8a-0000-4000-8000-000000000001",
    conversation_title: "Thời gian thử việc",
    message: "ok",
    tool_calls: [],
    answer: {
      question: "Thời gian thử việc tối đa?",
      answer: text,
      relevant_docs: [],
      relevant_articles: citations,
      selected_articles: [],
      debug: {},
    },
  };
}

const HAPPY_PATH: SsePacket[] = [
  {
    event: "status",
    data: { message: "Phân tích ý định", stage: "intent", status: "started" },
  },
  {
    event: "status",
    data: {
      message: "Đã truy hồi 8 điều luật",
      stage: "retrieval",
      status: "completed",
      elapsed_ms: 1200,
      metadata: {
        top_results: [
          { rank: 1, score: 0.91, law_id: "test-02", article: "Điều 25", article_title: "Thử việc" },
        ],
      },
    },
  },
  { event: "token", data: { token: "Thời gian " } },
  { event: "token", data: { token: "thử việc " } },
  { event: "token", data: { token: "tối đa 180 ngày." } },
  {
    event: "result",
    data: answer("Thời gian thử việc tối đa 180 ngày.", ["test-02|Bộ luật Lao động|Điều 25"]),
  },
  { event: "done", data: { message: "Hoàn tất", stage: "response", status: "completed" } },
];

describe("useChatStream", () => {
  it("ghép token thành câu trả lời hoàn chỉnh", async () => {
    stub = stubSseFetch(HAPPY_PATH);
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.send({ message: "Thời gian thử việc tối đa?" });
    });

    expect(result.current.answer).toBe("Thời gian thử việc tối đa 180 ngày.");
    expect(result.current.streaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("gom event cùng stage thành một bước trace", async () => {
    stub = stubSseFetch([
      { event: "status", data: { message: "Truy hồi", stage: "retrieval", status: "started" } },
      { event: "status", data: { message: "Truy hồi", stage: "retrieval", status: "running" } },
      {
        event: "status",
        data: { message: "Xong", stage: "retrieval", status: "completed", elapsed_ms: 900 },
      },
      { event: "result", data: answer("xong") },
      { event: "done", data: { message: "Hoàn tất", stage: "response", status: "completed" } },
    ]);
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.send({ message: "câu hỏi" });
    });

    const retrievalSteps = result.current.trace.filter((step) => step.stage === "retrieval");
    expect(retrievalSteps).toHaveLength(1);
    expect(retrievalSteps[0].status).toBe("completed");
    expect(retrievalSteps[0].elapsedMs).toBe(900);
  });

  it("dịch stage sang nhãn tiếng Việt và giữ kết quả truy hồi", async () => {
    stub = stubSseFetch(HAPPY_PATH);
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.send({ message: "câu hỏi" });
    });

    const retrieval = result.current.trace.find((step) => step.stage === "retrieval");
    expect(retrieval?.title).toBe("Truy hồi điều luật");
    expect(retrieval?.topResults?.[0].article).toBe("Điều 25");
  });

  it("giữ kết quả retrieval khi event sau của cùng stage không mang metadata", async () => {
    stub = stubSseFetch([
      {
        event: "status",
        data: {
          message: "Truy hồi",
          stage: "retrieval",
          status: "running",
          metadata: { top_results: [{ rank: 1, article: "Điều 25" }] },
        },
      },
      { event: "status", data: { message: "Xong", stage: "retrieval", status: "completed" } },
      { event: "result", data: answer("xong") },
    ]);
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.send({ message: "câu hỏi" });
    });

    const retrieval = result.current.trace.find((step) => step.stage === "retrieval");
    expect(retrieval?.topResults).toHaveLength(1);
  });

  it("trả conversation_id cho caller để điều hướng URL", async () => {
    stub = stubSseFetch(HAPPY_PATH);
    const { result } = renderHook(() => useChatStream());
    let received: ChatResponse | null = null;

    await act(async () => {
      await result.current.send({
        message: "câu hỏi",
        onResult: (value) => {
          received = value;
        },
      });
    });

    expect(received).not.toBeNull();
    expect(received!.conversation_id).toBe("6f1c9e8a-0000-4000-8000-000000000001");
  });

  it("gửi conversation_id đang mở lên server", async () => {
    stub = stubSseFetch(HAPPY_PATH);
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.send({ message: "câu hỏi", conversationId: "abc-123" });
    });

    expect(stub!.requests[0]).toEqual({ message: "câu hỏi", conversation_id: "abc-123" });
  });

  it("dùng câu trả lời trong event result khi không có token nào", async () => {
    // Backend có thể tắt token_streaming; UI vẫn phải hiện câu trả lời.
    stub = stubSseFetch([
      { event: "result", data: answer("Câu trả lời đầy đủ.") },
      { event: "done", data: { message: "Hoàn tất", stage: "response", status: "completed" } },
    ]);
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.send({ message: "câu hỏi" });
    });

    expect(result.current.answer).toBe("Câu trả lời đầy đủ.");
  });

  it("ghép được khối SSE bị cắt giữa hai chunk mạng", async () => {
    // chunkSize nhỏ khiến "event:"/"data:" của cùng một khối rơi vào hai lần
    // read() khác nhau — đúng tình huống hay làm vỡ parser tự viết.
    stub = stubSseFetch(HAPPY_PATH, { chunkSize: 7 });
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.send({ message: "câu hỏi" });
    });

    expect(result.current.answer).toBe("Thời gian thử việc tối đa 180 ngày.");
    expect(result.current.trace.length).toBeGreaterThan(0);
  });

  it("hiện lỗi khi server trả event error", async () => {
    stub = stubSseFetch([
      {
        event: "error",
        data: {
          message: "Hết quota Gemini",
          stage: "answer",
          status: "error",
          detail: "RateLimitError",
        },
      },
    ]);
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.send({ message: "câu hỏi" });
    });

    expect(result.current.error).toBe("Hết quota Gemini");
    expect(result.current.status).toBe("error");
    expect(result.current.streaming).toBe(false);
  });

  it("chuyển lỗi HTTP thành thông báo đọc được", async () => {
    stub = stubSseFetch([], { status: 429 });
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.send({ message: "câu hỏi" });
    });

    expect(result.current.error).toBe("Đã vượt giới hạn truy vấn");
    expect(result.current.streaming).toBe(false);
  });

  it("reset xóa sạch câu trả lời và trace", async () => {
    stub = stubSseFetch(HAPPY_PATH);
    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.send({ message: "câu hỏi" });
    });
    act(() => result.current.reset());

    await waitFor(() => {
      expect(result.current.answer).toBe("");
      expect(result.current.trace).toEqual([]);
    });
  });
});
