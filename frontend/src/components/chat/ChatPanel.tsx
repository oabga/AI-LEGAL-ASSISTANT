import type { FormEvent } from "react";
import { ArrowUp, PanelLeftOpen, Scale, Square } from "lucide-react";

import { MessageBubble } from "@/components/chat/MessageBubble";
import { Button, LoadingState, Textarea } from "@/components/ui";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "Công ty tôi có 12 lao động thì phải nộp những báo cáo định kỳ nào?",
  "Thời gian thử việc tối đa với vị trí nhân viên kinh doanh là bao lâu?",
  "Hộ kinh doanh chuyển thành công ty TNHH cần thủ tục gì?",
  "Mức phạt khi chậm đóng bảo hiểm xã hội được tính thế nào?",
];

type ChatPanelProps = {
  messages: ChatMessage[];
  isLoading: boolean;
  showWelcome: boolean;
  draft: string;
  streaming: boolean;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onDraftChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onCancel: () => void;
};

/** Cột chính của trang chat: danh sách tin nhắn, streaming token, ô nhập. */
export function ChatPanel({
  messages,
  isLoading,
  showWelcome,
  draft,
  streaming,
  sidebarOpen,
  onToggleSidebar,
  onDraftChange,
  onSubmit,
  onCancel,
}: ChatPanelProps) {
  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-3">
        <Button
          variant="ghost"
          size="icon"
          className="hidden md:inline-flex"
          aria-label={sidebarOpen ? "Ẩn lịch sử" : "Hiện lịch sử"}
          onClick={onToggleSidebar}
        >
          <PanelLeftOpen className={cn("size-4", !sidebarOpen && "rotate-180")} />
        </Button>
        <h1 className="truncate text-sm font-medium text-ink">Hỏi đáp pháp lý</h1>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto" data-chat-scroll>
        <div className="mx-auto max-w-3xl px-4 py-6">
          {isLoading && <LoadingState label="Đang tải hội thoại…" />}

          {showWelcome && (
            <div className="py-10 text-center">
              <span className="mx-auto mb-4 grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand">
                <Scale className="size-6" aria-hidden />
              </span>
              <h2 className="text-lg font-semibold text-ink">
                Hỏi về pháp luật doanh nghiệp Việt Nam
              </h2>
              <p className="mx-auto mt-1.5 max-w-md text-sm text-muted">
                Mọi câu trả lời đều kèm trích dẫn Điều luật từ kho văn bản chính thống để
                bạn tự kiểm chứng.
              </p>
              <div className="mx-auto mt-6 grid max-w-xl gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => onDraftChange(suggestion)}
                    className="rounded-xl border border-line bg-surface px-3.5 py-2.5 text-left text-sm text-muted transition-colors hover:border-brand/40 hover:text-ink"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-5">
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                streaming={streaming && message.id === "pending-assistant"}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="shrink-0 border-t border-line px-4 py-3">
        <form onSubmit={onSubmit} className="mx-auto max-w-3xl">
          <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-2 focus-within:border-brand">
            <Textarea
              value={draft}
              onChange={(event) => onDraftChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  onSubmit(event);
                }
              }}
              rows={1}
              placeholder="Nhập câu hỏi pháp lý…"
              className="max-h-40 min-h-10 border-0 bg-transparent py-2 focus:outline-none"
              style={{ height: "auto" }}
            />
            {streaming ? (
              <Button type="button" variant="secondary" size="icon" aria-label="Dừng" onClick={onCancel}>
                <Square className="size-3.5" />
              </Button>
            ) : (
              <Button type="submit" size="icon" aria-label="Gửi câu hỏi" disabled={!draft.trim()}>
                <ArrowUp className="size-4" />
              </Button>
            )}
          </div>
          <p className="mt-1.5 text-center text-xs text-muted-2">
            Đây là tư vấn sơ bộ dựa trên văn bản pháp luật, không thay thế ý kiến luật sư.
          </p>
        </form>
      </div>
    </div>
  );
}
