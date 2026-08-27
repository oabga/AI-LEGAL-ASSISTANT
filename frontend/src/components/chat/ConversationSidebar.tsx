import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Check, MessageSquarePlus, Pencil, Trash2, X } from "lucide-react";

import { Button, EmptyState, LoadingState, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { Conversation, Paginated } from "@/lib/types";
import { cn, formatRelative } from "@/lib/utils";

export function ConversationSidebar({
  activeId,
  onSelect,
  onNew,
}: {
  activeId?: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["conversations"],
    queryFn: async () => {
      const { data } = await api.get<Paginated<Conversation>>("/api/v1/conversations");
      return data;
    },
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["conversations"] });

  const rename = useMutation({
    mutationFn: async ({ id, title }: { id: string; title: string }) => {
      await api.patch(`/api/v1/conversations/${id}`, { title });
    },
    onSuccess: () => {
      setEditingId(null);
      void invalidate();
    },
  });

  const archive = useMutation({
    mutationFn: async (id: string) => {
      await api.patch(`/api/v1/conversations/${id}`, { archived: true });
    },
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/conversations/${id}`);
    },
    onSuccess: (_data, id) => {
      // Đang mở đúng hội thoại vừa xóa thì phải chuyển về đoạn chat mới.
      if (id === activeId) onNew();
      void invalidate();
    },
  });

  const conversations = data?.items ?? [];

  return (
    <div className="flex h-full w-72 shrink-0 flex-col border-r border-line bg-sidebar">
      <div className="p-3">
        <Button className="w-full justify-center" onClick={onNew}>
          <MessageSquarePlus className="size-4" aria-hidden />
          Đoạn chat mới
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {isLoading && <LoadingState label="Đang tải lịch sử…" />}
        {isError && (
          <p className="px-3 py-6 text-center text-sm text-danger">Không tải được lịch sử</p>
        )}
        {!isLoading && !isError && !conversations.length && (
          <EmptyState
            title="Chưa có hội thoại"
            description="Đặt câu hỏi đầu tiên để bắt đầu."
          />
        )}

        <ul className="space-y-0.5">
          {conversations.map((conversation) => {
            const isActive = conversation.id === activeId;
            const isEditing = editingId === conversation.id;

            if (isEditing) {
              return (
                <li key={conversation.id} className="px-1 py-1">
                  <form
                    className="flex items-center gap-1"
                    onSubmit={(event) => {
                      event.preventDefault();
                      const title = draftTitle.trim();
                      if (title) rename.mutate({ id: conversation.id, title });
                    }}
                  >
                    <input
                      autoFocus
                      value={draftTitle}
                      onChange={(event) => setDraftTitle(event.target.value)}
                      className="min-w-0 flex-1 rounded-lg border border-brand bg-surface px-2 py-1 text-sm focus:outline-none"
                    />
                    <Button type="submit" variant="ghost" size="icon" aria-label="Lưu tên">
                      {rename.isPending ? <Spinner /> : <Check className="size-4 text-ok" />}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label="Hủy"
                      onClick={() => setEditingId(null)}
                    >
                      <X className="size-4" />
                    </Button>
                  </form>
                </li>
              );
            }

            return (
              <li key={conversation.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onSelect(conversation.id)}
                  className={cn(
                    "w-full rounded-lg px-3 py-2 pr-20 text-left transition-colors",
                    isActive
                      ? "bg-brand-soft text-brand"
                      : "text-muted hover:bg-surface-2 hover:text-ink",
                  )}
                >
                  <span className="block truncate text-sm">{conversation.title}</span>
                  <span className="block text-xs text-muted-2">
                    {formatRelative(conversation.updated_at)}
                    {conversation.message_count > 0 && ` · ${conversation.message_count} tin nhắn`}
                  </span>
                </button>

                <div className="absolute top-1.5 right-1 hidden gap-0.5 group-hover:flex">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    aria-label="Đổi tên"
                    onClick={() => {
                      setEditingId(conversation.id);
                      setDraftTitle(conversation.title);
                    }}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    aria-label="Lưu trữ"
                    onClick={() => archive.mutate(conversation.id)}
                  >
                    <Archive className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7 hover:text-danger"
                    aria-label="Xóa"
                    onClick={() => remove.mutate(conversation.id)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
