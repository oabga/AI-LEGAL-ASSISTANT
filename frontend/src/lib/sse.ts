/**
 * Đọc SSE bằng Fetch Streams API.
 *
 * Không dùng ``EventSource`` vì nó chỉ hỗ trợ GET và không gửi được header
 * Authorization; endpoint chat là POST kèm JWT.
 */

/** Parse một khối SSE ``event: ...\ndata: ...`` thành object. */
export function parseSseChunk<T>(raw: string): T | null {
  const lines = raw.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event:"));
  const dataLine = lines.find((line) => line.startsWith("data:"));
  if (!eventLine || !dataLine) return null;

  try {
    return {
      event: eventLine.slice(6).trim(),
      data: JSON.parse(dataLine.slice(5).trim() || "{}"),
    } as T;
  } catch {
    // Bỏ qua khối lỗi thay vì làm sập cả vòng đọc stream.
    return null;
  }
}

export type SseOptions<T> = {
  url: string;
  body: unknown;
  token?: string | null;
  signal?: AbortSignal;
  onEvent: (event: T) => void;
};

/** Mở POST SSE và gọi ``onEvent`` cho từng khối nhận được. */
export async function streamSse<T>({
  url,
  body,
  token,
  signal,
  onEvent,
}: SseOptions<T>): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      /* response không phải JSON, giữ nguyên mã lỗi HTTP */
    }
    throw new Error(detail);
  }
  if (!response.body) throw new Error("Server không trả về stream");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    // Các khối SSE cách nhau bằng dòng trống; khối cuối có thể chưa đủ nên giữ
    // lại trong buffer để ghép với chunk sau.
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const parsed = parseSseChunk<T>(chunk);
      if (parsed) onEvent(parsed);
    }
  }

  const tail = parseSseChunk<T>(buffer);
  if (tail) onEvent(tail);
}
