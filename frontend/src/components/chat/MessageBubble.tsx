import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { AgentTrace } from "@/components/chat/AgentTrace";
import { CitationList } from "@/components/chat/CitationList";
import { Alert } from "@/components/ui";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

export function MessageBubble({
  message,
  streaming = false,
}: {
  message: ChatMessage;
  streaming?: boolean;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-bubble rounded-br-md bg-brand px-4 py-2.5 text-white">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
      </div>
    );
  }

  const waiting = streaming && !message.content;

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[92%] space-y-2.5">
        {!!message.trace.length && (
          <AgentTrace steps={message.trace} running={streaming} defaultOpen={streaming} />
        )}

        {message.error && <Alert>{message.error}</Alert>}

        {(message.content || waiting) && (
          <div
            className={cn(
              "rounded-bubble rounded-bl-md border border-line bg-surface px-4 py-3",
              "prose-legal text-ink",
            )}
          >
            {waiting ? (
              <span className="flex items-center gap-1.5 text-sm text-muted">
                <span className="size-1.5 animate-trace-pulse rounded-full bg-muted" />
                Đang soạn câu trả lời…
              </span>
            ) : (
              <>
                <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
                {/* Con trỏ nhấp nháy cho biết token vẫn đang chảy về. */}
                {streaming && (
                  <span className="ml-0.5 inline-block h-4 w-0.5 animate-trace-pulse bg-brand align-text-bottom" />
                )}
              </>
            )}
          </div>
        )}

        {!streaming && <CitationList citations={message.citations} />}
      </div>
    </div>
  );
}
