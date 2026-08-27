import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Bỏ dấu tiếng Việt để so khớp truy vấn không dấu như backend đang làm. */
export function removeAccents(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D");
}

/**
 * Bỏ dấu nhưng giữ lại vị trí gốc của từng ký tự.
 *
 * Không thể giả định chuỗi bỏ dấu dài bằng chuỗi gốc: text ở dạng NFD có ký tự
 * tổ hợp riêng, một ký tự hiển thị chiếm nhiều code unit. Map index tường minh
 * mới cắt đúng đoạn trên chuỗi gốc.
 */
function foldWithIndex(text: string): { folded: string; indices: number[] } {
  let folded = "";
  const indices: number[] = [];
  for (let position = 0; position < text.length; position += 1) {
    const stripped = removeAccents(text[position]).toLowerCase();
    for (const character of stripped) {
      folded += character;
      indices.push(position);
    }
  }
  // Chốt cuối để end index của match cuối cùng luôn tra được.
  indices.push(text.length);
  return { folded, indices };
}

export type TextSegment = { text: string; match: boolean };

/**
 * Chia text thành các đoạn khớp / không khớp từ khóa, so sánh kiểu bỏ qua dấu.
 *
 * Việc bôi đậm làm ở client (không dùng ``ts_headline`` của PostgreSQL) vì
 * ``search_vector`` được build từ text đã bỏ dấu, nên đoạn trích do PostgreSQL
 * trả về sẽ mất hết dấu tiếng Việt.
 */
export function highlightSegments(text: string, terms: string[]): TextSegment[] {
  const needles = terms
    .map((term) => removeAccents(term).toLowerCase())
    .filter((term) => term.length > 1);
  if (!needles.length) return [{ text, match: false }];

  const { folded, indices } = foldWithIndex(text);
  const hits: [number, number][] = [];
  for (const needle of needles) {
    let from = 0;
    while (from <= folded.length - needle.length) {
      const at = folded.indexOf(needle, from);
      if (at === -1) break;
      hits.push([indices[at], indices[at + needle.length]]);
      from = at + needle.length;
    }
  }
  if (!hits.length) return [{ text, match: false }];

  hits.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const [start, end] of hits) {
    const last = merged[merged.length - 1];
    if (last && start <= last[1]) {
      last[1] = Math.max(last[1], end);
    } else {
      merged.push([start, end]);
    }
  }

  const segments: TextSegment[] = [];
  let cursor = 0;
  for (const [start, end] of merged) {
    if (start > cursor) segments.push({ text: text.slice(cursor, start), match: false });
    segments.push({ text: text.slice(start, end), match: true });
    cursor = end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), match: false });
  return segments;
}

/** Cắt quanh vị trí khớp đầu tiên để không luôn hiển thị phần đầu Điều luật. */
export function snippetAround(text: string, terms: string[], radius = 220): string {
  const needles = terms
    .map((term) => removeAccents(term).toLowerCase())
    .filter((term) => term.length > 1);
  const { folded, indices } = foldWithIndex(text);
  let at = -1;
  for (const needle of needles) {
    const found = folded.indexOf(needle);
    if (found !== -1 && (at === -1 || found < at)) at = found;
  }
  if (at === -1) return text.slice(0, radius * 2) + (text.length > radius * 2 ? "…" : "");

  const origin = indices[at];
  const start = Math.max(0, origin - radius);
  const end = Math.min(text.length, origin + radius);
  return `${start > 0 ? "…" : ""}${text.slice(start, end)}${end < text.length ? "…" : ""}`;
}

/** Tách reference ``law_id|law_name|Điều X`` thành các phần. */
export function parseReference(reference: string): {
  lawId: string;
  lawName: string;
  article: string;
} | null {
  const parts = reference.split("|").map((part) => part.trim());
  if (parts.length < 3) return null;
  return { lawId: parts[0], lawName: parts.slice(1, -1).join(" | "), article: parts[parts.length - 1] };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDuration(ms?: number | null): string {
  if (ms == null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

const DATE_FORMAT = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : DATE_FORMAT.format(date);
}

/** Nhãn thời gian tương đối cho sidebar hội thoại. */
export function formatRelative(value: string): string {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return "vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} ngày trước`;
  return formatDate(value);
}

/** Mô tả số ngày còn lại của một nghĩa vụ tuân thủ. */
export function describeDueDays(days: number): string {
  if (days < 0) return `Quá hạn ${Math.abs(days)} ngày`;
  if (days === 0) return "Đến hạn hôm nay";
  if (days === 1) return "Còn 1 ngày";
  return `Còn ${days} ngày`;
}
