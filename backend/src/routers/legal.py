"""Các HTTP endpoint phục vụ hỏi đáp pháp lý."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from src.config import get_settings
from src.core.database import get_session_factory
from src.core.deps import CurrentUser, SessionDep
from src.core.rate_limit import chat_rate_limit
from src.dependencies import get_legal_assistant_agent
from src.schemas.api.chat import (
    ChatRequest,
    ChatResponse,
    ChatStreamDoneEvent,
    ChatStreamErrorEvent,
    ChatStreamMessagePayload,
    ChatStreamResultEvent,
    ChatStreamStatusEvent,
    ChatStreamTokenEvent,
    ChatStreamTokenPayload,
    LegalRuntimeConfig,
)
from src.schemas.legal import LegalAnswerRequest, LegalAnswerResponse
from src.services.agents.legal_assistant import LegalAssistantAgent
from src.services.chat.history import (
    append_assistant_message,
    append_user_message,
    load_history,
    resolve_conversation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/legal", tags=["legal-assistant"])


async def require_index(request: Request, _user: CurrentUser) -> None:
    """Chặn sớm khi vector index chưa dựng được.

    Phụ thuộc ``CurrentUser`` để request chưa đăng nhập nhận 401 thay vì 503.
    Startup không còn coi việc dựng index là điều kiện sống của backend, nên
    phải chặn ở đây để người dùng nhận thông báo hiểu được thay vì một lỗi
    ``Missing credentials`` từ SDK của OpenAI.
    """

    if not getattr(request.app.state, "index_ready", True):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Chức năng hỏi đáp chưa sẵn sàng: hệ thống chưa dựng được chỉ mục "
                "tra cứu ngữ nghĩa. Kiểm tra LLM_API_KEY rồi chạy lại reindex. "
                "Trong lúc chờ, bạn vẫn tra cứu được văn bản ở trang Tra cứu."
            ),
        )


IndexReady = Depends(require_index)


@router.get("/config", response_model=LegalRuntimeConfig)
async def runtime_config() -> LegalRuntimeConfig:
    """Trả config runtime để UI biết có dùng chat streaming hay không."""

    settings = get_settings().legal_assistant
    return LegalRuntimeConfig(
        chat_streaming=settings.chat.streaming,
        token_streaming=settings.chat.token_streaming,
        competition_enabled=settings.competition.enabled,
    )


@router.post("/answer", response_model=LegalAnswerResponse, dependencies=[IndexReady])
@chat_rate_limit
async def answer_question(
    request: Request,
    payload: LegalAnswerRequest,
    _user: CurrentUser,
    agent: LegalAssistantAgent = Depends(get_legal_assistant_agent),
) -> LegalAnswerResponse:
    """Trả lời một câu hỏi pháp lý đơn lẻ, không lưu vào hội thoại."""

    return await agent.answer(payload)


@router.post("/chat", response_model=ChatResponse, dependencies=[IndexReady])
@chat_rate_limit
async def chat(
    request: Request,
    payload: ChatRequest,
    user: CurrentUser,
    session: SessionDep,
    agent: LegalAssistantAgent = Depends(get_legal_assistant_agent),
) -> ChatResponse:
    """Chat có lịch sử: nạp short-memory từ DB, lưu cả câu hỏi và câu trả lời."""

    conversation = await resolve_conversation(
        session, user, payload.conversation_id, payload.message
    )
    history = await load_history(session, conversation)
    await append_user_message(session, conversation, payload.message)

    answer = await agent.answer(
        LegalAnswerRequest(
            session_id=str(conversation.id),
            question=payload.message,
            competition_mode=payload.competition_mode,
            top_k=payload.top_k,
            include_debug=True,
            history=history,
            search_spaces=payload.databases,
        )
    )

    await append_assistant_message(
        session,
        conversation,
        content=answer.answer,
        citations=answer.relevant_articles,
        relevant_docs=answer.relevant_docs,
        trace=answer.debug,
    )
    return ChatResponse(
        session_id=str(conversation.id),
        conversation_id=conversation.id,
        conversation_title=conversation.title,
        message=payload.message,
        answer=answer,
        tool_calls=answer.debug.get("tool_calls", []),
    )


@router.post("/chat/stream", dependencies=[IndexReady])
@chat_rate_limit
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    user: CurrentUser,
    session: SessionDep,
    agent: LegalAssistantAgent = Depends(get_legal_assistant_agent),
) -> StreamingResponse:
    """Stream từng stage, heartbeat và kết quả chat cuối cùng bằng SSE."""

    # Chuẩn bị hội thoại và ghi câu hỏi *trước* khi mở stream: session của
    # request đã đóng khi generator chạy, nên phần persist sau đó phải dùng
    # session riêng.
    conversation = await resolve_conversation(
        session, user, payload.conversation_id, payload.message
    )
    history = await load_history(session, conversation)
    await append_user_message(session, conversation, payload.message)
    await session.commit()

    conversation_id = conversation.id
    conversation_title = conversation.title

    async def persist_answer(answer: LegalAnswerResponse) -> None:
        """Lưu câu trả lời bằng session riêng vì request session đã đóng."""

        async with get_session_factory()() as own_session:
            own_conversation = await own_session.get(type(conversation), conversation_id)
            if own_conversation is None:  # pragma: no cover - hội thoại vừa bị xóa
                return
            await append_assistant_message(
                own_session,
                own_conversation,
                content=answer.answer,
                citations=answer.relevant_articles,
                relevant_docs=answer.relevant_docs,
                trace=answer.debug,
            )
            await own_session.commit()

    async def events():
        def pack(stream_event) -> str:
            event = stream_event.event
            data = stream_event.data.model_dump(mode="json")
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        started = perf_counter()
        stage_started = started
        current_stage = "request"
        current_message = "Đang chuẩn bị request"
        current_status = "started"
        progress_queue: asyncio.Queue[dict] = asyncio.Queue()

        async def on_progress(payload_event: dict) -> None:
            await progress_queue.put(payload_event)
            # Nhường event loop để StreamingResponse gửi event trước khi node
            # tiếp tục một tác vụ nặng.
            await asyncio.sleep(0)

        answer_request = LegalAnswerRequest(
            session_id=str(conversation_id),
            question=payload.message,
            competition_mode=payload.competition_mode,
            top_k=payload.top_k,
            include_debug=True,
            history=history,
            search_spaces=payload.databases,
        )
        task = asyncio.create_task(agent.answer_with_progress(answer_request, on_progress))
        try:
            yield pack(
                ChatStreamStatusEvent(
                    data=ChatStreamMessagePayload(
                        message="Đã nhận request chat",
                        stage="request",
                        status="started",
                        elapsed_ms=0,
                        detail=f"Hội thoại: {conversation_id}; {len(payload.message)} ký tự.",
                    )
                )
            )

            while not task.done() or not progress_queue.empty():
                try:
                    event_payload = await asyncio.wait_for(progress_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if current_status in {"completed", "warning", "error"}:
                        current_stage = "response"
                        current_message = "Đang hoàn thiện response"
                        current_status = "running"
                        stage_started = perf_counter()
                    elapsed_ms = round((perf_counter() - stage_started) * 1000)
                    yield pack(
                        ChatStreamStatusEvent(
                            data=ChatStreamMessagePayload(
                                message=f"{current_message} ({elapsed_ms / 1000:.1f}s)",
                                stage=current_stage,
                                status="running",
                                elapsed_ms=elapsed_ms,
                                detail="Backend vẫn đang xử lý stage này; kết nối SSE còn hoạt động.",
                            )
                        )
                    )
                    continue

                if event_payload.get("event") == "token":
                    yield pack(
                        ChatStreamTokenEvent(
                            data=ChatStreamTokenPayload(
                                token=str(event_payload.get("token") or ""),
                                stage=str(event_payload.get("stage") or "answer"),
                            )
                        )
                    )
                    continue

                current_stage = str(event_payload.get("stage") or current_stage)
                current_message = str(event_payload.get("message") or current_message)
                current_status = str(event_payload.get("status") or current_status)
                if event_payload.get("status") == "started":
                    stage_started = perf_counter()
                elif event_payload.get("elapsed_ms") is None:
                    event_payload["elapsed_ms"] = round((perf_counter() - stage_started) * 1000)
                yield pack(
                    ChatStreamStatusEvent(data=ChatStreamMessagePayload.model_validate(event_payload))
                )

            answer = await task
            await persist_answer(answer)
            response = ChatResponse(
                session_id=str(conversation_id),
                conversation_id=conversation_id,
                conversation_title=conversation_title,
                message=payload.message,
                answer=answer,
                tool_calls=answer.debug.get("tool_calls", []),
            )
            yield pack(ChatStreamResultEvent(data=response))
            yield pack(
                ChatStreamDoneEvent(
                    data=ChatStreamMessagePayload(
                        message="Hoàn tất request",
                        stage="request",
                        status="completed",
                        elapsed_ms=round((perf_counter() - started) * 1000),
                    )
                )
            )
        except asyncio.CancelledError:
            task.cancel()
            raise
        except Exception as exc:  # pragma: no cover - trả lỗi runtime cho UI
            logger.exception("Chat stream thất bại tại stage %s", current_stage)
            yield pack(
                ChatStreamErrorEvent(
                    data=ChatStreamMessagePayload(
                        message=f"Lỗi tại stage {current_stage}: {exc}",
                        stage=current_stage,
                        status="error",
                        elapsed_ms=round((perf_counter() - stage_started) * 1000),
                        detail=exc.__class__.__name__,
                        metadata={"request_elapsed_ms": round((perf_counter() - started) * 1000)},
                    )
                )
            )
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
