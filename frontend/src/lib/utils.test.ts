import { describe, expect, it } from "vitest";

import {
  describeDueDays,
  formatBytes,
  highlightSegments,
  parseReference,
  removeAccents,
  snippetAround,
} from "@/lib/utils";

const CONTENT =
  "Thời gian thử việc không quá 180 ngày đối với công việc của người quản lý doanh nghiệp.";

function highlighted(text: string, terms: string[]): string[] {
  return highlightSegments(text, terms)
    .filter((segment) => segment.match)
    .map((segment) => segment.text);
}

describe("removeAccents", () => {
  it("bỏ dấu và chuyển đ/Đ", () => {
    expect(removeAccents("Thời gian thử việc")).toBe("Thoi gian thu viec");
    expect(removeAccents("Điều 25 đăng ký")).toBe("Dieu 25 dang ky");
  });
});

describe("highlightSegments", () => {
  it("bôi đậm đúng đoạn có dấu khi từ khóa gõ không dấu", () => {
    // Đây là lý do phải bôi đậm ở client: giữ nguyên dấu của văn bản gốc.
    // "việc" xuất hiện hai lần ("thử việc" và "công việc") nên phải sáng cả hai.
    expect(highlighted(CONTENT, ["thu", "viec"])).toEqual(["thử", "việc", "việc"]);
  });

  it("giữ nguyên toàn bộ ký tự khi ghép các đoạn lại", () => {
    const segments = highlightSegments(CONTENT, ["thoi gian", "quan ly"]);
    expect(segments.map((segment) => segment.text).join("")).toBe(CONTENT);
  });

  it("khớp được cả khi văn bản gốc ở dạng NFD", () => {
    // NFD tách dấu thành ký tự tổ hợp riêng nên độ dài chuỗi khác NFC; nếu map
    // index bằng cách giả định hai chuỗi dài bằng nhau thì sẽ cắt lệch.
    const nfd = CONTENT.normalize("NFD");
    const matches = highlighted(nfd, ["thu viec"]);
    expect(matches).toHaveLength(1);
    expect(matches[0].normalize("NFC")).toBe("thử việc");
  });

  it("gộp các vùng khớp chồng nhau", () => {
    const segments = highlightSegments("doanh nghiệp nhỏ", ["doanh nghiep", "nghiep nho"]);
    expect(segments.filter((segment) => segment.match)).toHaveLength(1);
    expect(segments.map((segment) => segment.text).join("")).toBe("doanh nghiệp nhỏ");
  });

  it("không bôi đậm gì khi không có từ khóa hợp lệ", () => {
    expect(highlightSegments(CONTENT, [])).toEqual([{ text: CONTENT, match: false }]);
    // Từ một ký tự bị loại, nếu không thì gần như mọi chữ đều sáng.
    expect(highlightSegments(CONTENT, ["a"])).toEqual([{ text: CONTENT, match: false }]);
  });

  it("trả về nguyên văn khi không khớp", () => {
    expect(highlightSegments(CONTENT, ["hoan toan khong co"])).toEqual([
      { text: CONTENT, match: false },
    ]);
  });
});

describe("snippetAround", () => {
  it("cắt quanh vị trí khớp đầu tiên", () => {
    const long = "x".repeat(500) + " thử việc " + "y".repeat(500);
    const snippet = snippetAround(long, ["thu viec"], 30);

    expect(snippet).toContain("thử việc");
    expect(snippet.startsWith("…")).toBe(true);
    expect(snippet.endsWith("…")).toBe(true);
  });

  it("lấy phần đầu khi không khớp gì", () => {
    const snippet = snippetAround(CONTENT, ["khong ton tai"], 500);
    expect(snippet).toBe(CONTENT);
  });
});

describe("parseReference", () => {
  it("tách citation của agent", () => {
    expect(parseReference("45/2019/QH14|Bộ luật Lao động|Điều 25")).toEqual({
      lawId: "45/2019/QH14",
      lawName: "Bộ luật Lao động",
      article: "Điều 25",
    });
  });

  it("trả null với chuỗi không đủ phần", () => {
    expect(parseReference("Điều 25")).toBeNull();
  });
});

describe("format helpers", () => {
  it("formatBytes đổi đơn vị theo độ lớn", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });

  it("describeDueDays phân biệt quá hạn và còn hạn", () => {
    expect(describeDueDays(-3)).toBe("Quá hạn 3 ngày");
    expect(describeDueDays(0)).toBe("Đến hạn hôm nay");
    expect(describeDueDays(1)).toBe("Còn 1 ngày");
    expect(describeDueDays(12)).toBe("Còn 12 ngày");
  });
});
