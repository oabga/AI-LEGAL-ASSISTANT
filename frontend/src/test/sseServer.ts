/**
 * Giả lập một endpoint SSE bằng cách thay `fetch`.
 *
 * Trả về ReadableStream thật thay vì mock `streamSse`, để test đi qua đúng vòng
 * đọc stream của production — kể cả trường hợp một khối SSE bị cắt giữa hai
 * chunk mạng.
 */

export type SsePacket = { event: string; data: unknown };

export function encodePacket({ event, data }: SsePacket): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Ghép các packet thành từng chunk tùy ý, mô phỏng cách mạng chia gói. */
export function chunkify(text: string, size: number): string[] {
  const chunks: string[] = [];
  for (let index = 0; index < text.length; index += size) {
    chunks.push(text.slice(index, index + size));
  }
  return chunks;
}

export type FetchStub = {
  /** Các body JSON mà client đã gửi lên, theo thứ tự. */
  requests: unknown[];
  restore: () => void;
};

export function stubSseFetch(
  packets: SsePacket[],
  { chunkSize = 4096, status = 200 }: { chunkSize?: number; status?: number } = {},
): FetchStub {
  const original = globalThis.fetch;
  const requests: unknown[] = [];

  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    requests.push(init?.body ? JSON.parse(String(init.body)) : null);

    if (status !== 200) {
      return new Response(JSON.stringify({ detail: "Đã vượt giới hạn truy vấn" }), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }

    const payload = packets.map(encodePacket).join("");
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunkify(payload, chunkSize)) {
          controller.enqueue(encoder.encode(chunk));
        }
        controller.close();
      },
    });

    return new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  }) as typeof fetch;

  return {
    requests,
    restore: () => {
      globalThis.fetch = original;
    },
  };
}
