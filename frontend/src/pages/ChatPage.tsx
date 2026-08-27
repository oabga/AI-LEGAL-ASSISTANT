import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ChatPanel } from "@/components/chat/ChatPanel";
import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import { useChatStream } from "@/hooks/useChatStream";
import { api } from "@/lib/api";
import type { AgentTraceStep, ApiMessage, ChatMessage } from "@/lib/types";

/** Trace lưu trong DB là JSON tự do; chỉ nhận đúng phần có cấu trúc mong đợi. */
function readStoredTrace(trace: Record<string, unknown> | undefined): AgentTraceStep[] {
  const steps = trace?.trace ?? trace?.steps;
  return Array.isArray(steps) ? (steps as AgentTraceStep[]) : [];
}

function toChatMessage(message: ApiMessage): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    citations: message.citations ?? [],
    relevantDocs: message.relevant_docs ?? [],
    trace: readStoredTrace(message.trace),
  };
}

export function ChatPage() {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  const [draft, setDraft] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const stream = useChatStream();

  const { data: history, isLoading } = useQuery({
    queryKey: ["messages", conversationId],
    queryFn: async () => {
      const { data } = await api.get<ApiMessage[]>(
        `/api/v1/conversations/${conversationId}/messages`,
      );
      return data.map(toChatMessage);
    },
    enabled: Boolean(conversationId),
  });

  const seededQuestion = (location.state as { question?: string } | null)?.question;
  useEffect(() => {
    if (seededQuestion) {
      setDraft(seededQuestion);
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [seededQuestion, navigate, location.pathname]);

  const messages = useMemo<ChatMessage[]>(() => {
    const stored = history ?? [];
    if (!pendingQuestion) return stored;
    return [
      ...stored,
      {
        id: "pending-user",
        role: "user",
        content: pendingQuestion,
        citations: [],
        relevantDocs: [],
        trace: [],
      },
      {
        id: "pending-assistant",
        role: "assistant",
        content: stream.answer,
        citations: [],
        relevantDocs: [],
        trace: stream.trace,
        error: stream.error,
      },
    ];
  }, [history, pendingQuestion, stream.answer, stream.trace, stream.error]);

  useEffect(() => {
    const scroller = scrollRef.current?.querySelector("[data-chat-scroll]");
    scroller?.scrollTo({ top: scroller.scrollHeight });
  }, [messages.length, stream.answer, conversationId]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || stream.streaming) return;

    setDraft("");
    setPendingQuestion(message);

    await stream.send({
      message,
      conversationId: conversationId ?? null,
      onResult: (result) => {
        const newId = result.conversation_id;
        setPendingQuestion(null);
        void queryClient.invalidateQueries({ queryKey: ["conversations"] });
        if (newId && newId !== conversationId) {
          navigate(`/chat/${newId}`, { replace: true });
        } else {
          void queryClient.invalidateQueries({ queryKey: ["messages", conversationId] });
        }
      },
    });
    setPendingQuestion((previous) => (stream.error ? previous : null));
  }

  function startNewChat() {
    stream.reset();
    setPendingQuestion(null);
    setDraft("");
    navigate("/chat");
  }

  const showWelcome = !conversationId && !pendingQuestion && !messages.length;

  return (
    <div ref={scrollRef} className="flex h-full">
      {sidebarOpen && (
        <div className="hidden md:block">
          <ConversationSidebar
            activeId={conversationId}
            onSelect={(id) => {
              stream.reset();
              setPendingQuestion(null);
              navigate(`/chat/${id}`);
            }}
            onNew={startNewChat}
          />
        </div>
      )}

      <ChatPanel
        messages={messages}
        isLoading={isLoading}
        showWelcome={showWelcome}
        draft={draft}
        streaming={stream.streaming}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((value) => !value)}
        onDraftChange={setDraft}
        onSubmit={handleSubmit}
        onCancel={stream.cancel}
      />
    </div>
  );
}
