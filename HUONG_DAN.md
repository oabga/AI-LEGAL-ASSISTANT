# Hướng dẫn chạy, kiến trúc và đọc code

File này viết cho người muốn **hiểu hệ thống như chính người đã xây**. Đọc xong
nên vẽ được luồng một câu hỏi từ ô chat tới PostgreSQL, Chroma, Gemini và trở
lại giao diện — và biết sửa chỗ nào khi một khâu hỏng.

Báo cáo đồ án nằm ở `Baocao/`. File này là sổ tay kỹ thuật, không phải báo cáo nộp.

---

## 1. Hệ thống làm gì

Ứng dụng web trợ lý pháp lý cho DNNVV Việt Nam. Bốn nghiệp vụ:

1. **Hỏi đáp** — câu tiếng Việt thường, câu trả lời kèm Điều trong kho, hiện từng
   bước pipeline (SSE).
2. **Tra cứu văn bản** — cây Chương–Điều, tìm không dấu, viện dẫn chéo.
3. **Soát xét hợp đồng** — PDF/DOCX/TXT, tách điều khoản, mỗi finding có căn cứ.
4. **Lịch tuân thủ** — 12 loại nghĩa vụ sinh theo hồ sơ công ty (kỳ GTGT, số lao
   động), không do LLM “đoán hạn nộp”.

Hai kho dữ liệu tách nhau:

- **PostgreSQL**: tài khoản, hội thoại, chữ luật (để đọc và FTS), lịch, hợp đồng.
- **Chroma + BM25**: chỉ phục vụ RAG (hỏi đáp và soát hợp đồng).

Thiếu khóa Gemini: đăng nhập, tra cứu, lịch vẫn chạy; hỏi đáp trả HTTP 503.

---

## 2. Chạy project

### 2.1. Yêu cầu

- Docker + Docker Compose (cách nhanh nhất).
- Hoặc: Python **3.10** (bắt buộc vì `underthesea`), Node.js 20+, `uv`, PostgreSQL.
- Khóa Gemini: [Google AI Studio](https://aistudio.google.com/apikey) — hỏi đáp
  và nhúng vector cần khóa; phần còn lại không cần.

### 2.2. Docker (nên dùng khi demo / máy sạch)

Compose **chỉ đọc `.env` ở thư mục gốc**, không đọc `backend/.env`.

```bash
cd /home/oabga/AI-LEGAL-ASSISTANT   # hoặc thư mục clone của bạn
cp .env.example .env
```

Mở `.env`, điền:

| Biến | Việc cần làm |
| --- | --- |
| `LLM_API_KEY` | Dán khóa Gemini |
| `EMBEDDINGS_API_KEY` | Để trống thì dùng chung `LLM_API_KEY` |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |

```bash
docker compose up -d --build
```

Lần đầu corpus chữ chưa có trong Postgres. Nạp rồi restart backend:

```bash
docker compose exec backend python scripts/load_postgres.py --truncate
docker compose restart backend
```

| Cổng trên máy bạn | Việc |
| --- | --- |
| http://localhost:5173 | Giao diện (nginx phục vụ SPA) |
| http://localhost:8023/docs | Swagger API |
| localhost:23432 | PostgreSQL (tránh đụng 5432 sẵn có) |

Tài khoản **đăng ký đầu tiên** (bảng user trống) thành `admin`.

Dựng vector: vào **Quản trị → Kho văn bản → Reindex**, hoặc đợi startup nếu khóa
đã có từ đầu. Nhúng 3.844 Điều mất vài phút, có thể gặp 429 (hạn mức) — backend
đã backoff; nếu fail, bấm reindex lại.

Dừng giữ dữ liệu: `docker compose down`. Xóa luôn volume (mất tài khoản, Chroma,
file upload): `docker compose down -v`.

### 2.3. Chạy tách (dev, sửa code nóng)

Ba process: Postgres (Docker) + backend (uv) + frontend (Vite).

```bash
# Terminal 1 — chỉ Postgres
docker compose up -d postgres

# Terminal 2 — backend
cd backend
cp .env.example .env          # KHÁC file .env gốc; điền LEGAL_DATABASE_URL, LLM_API_KEY, JWT_SECRET_KEY
# LEGAL_DATABASE_URL mặc định trong config trỏ localhost:23432
uv sync --frozen
uv run alembic upgrade head
uv run python scripts/load_postgres.py --truncate
uv run python scripts/run_backend.py --reload

# Terminal 3 — frontend
cd frontend
npm ci
npm run dev
```

Vite (cổng 5173) **proxy** `/api` sang `http://127.0.0.1:8023`. SPA luôn gọi
đường tương đối `/api/v1/...`, giống lúc nginx trong Docker.

### 2.4. Lỗi hay gặp

| Hiện tượng | Nguyên nhân thường gặp |
| --- | --- |
| Hỏi đáp 503, tra cứu vẫn được | Chưa khóa, chưa nạp luật, hoặc Chroma chưa index |
| Đăng nhập được nhưng Compose “không thấy key” | Điền `backend/.env` trong khi `docker compose` chỉ đọc `.env` gốc |
| Backend không lên, Postgres connection refused | Trong container phải gọi host `postgres`, không phải `localhost` — Compose đã set `LEGAL_DATABASE_URL` sẵn |
| CORS lúc `npm run dev` | Thiếu origin `http://localhost:5173` trong `CORS_ALLOW_ORIGINS` |
| `uv` / underthesea fail | Không dùng Python 3.11+ cho backend |
| Test pytest fail FTS | Chưa `docker compose up -d postgres`; test **không** chạy SQLite |

### 2.5. Kiểm thử

```bash
docker compose up -d postgres   # cổng 23432
cd backend && uv run pytest     # ~53 test, DB tạm legal_assistant_test
cd frontend && npm test         # ~24 test parser SSE
```

---

## 3. Kiến trúc (hình trong đầu)

```text
Trình duyệt (React SPA)
    │  HTTP JSON  +  SSE (hỏi đáp)
    ▼
nginx (Docker)  hoặc  Vite proxy (dev)
    │  /api → FastAPI :8023
    ▼
FastAPI  (routers → services → models)
    ├── PostgreSQL     users, conversations, messages,
    │                  legal_knowledge_records, laws,
    │                  documents, compliance_*, audit
    ├── Chroma         embedding từng Điều
    ├── BM25 in-process  (cache tách từ underthesea)
    └── Gemini API     chat + embeddings (OpenAI-compatible URL)
```

**Ba lớp:**

| Lớp | Việc được phép | Việc cấm |
| --- | --- | --- |
| `frontend/` | UI, gọi API, cache TanStack Query | Không viết SQL, không gọi Gemini |
| `backend/src/routers/` | HTTP, auth, mã lỗi | Không nhét công thức RRF vào router |
| `backend/src/services/` | RAG, FTS, lịch, hợp đồng | Không render JSX |
| `backend/src/models/` | Bảng SQLAlchemy | Không gọi LLM |

Cấu hình hành vi: `backend/config.yaml` (commit được). Bí mật: biến môi trường.

---

## 4. Lý thuyết cần nắm trước khi đọc RAG

Không cần thuộc công thức. Cần biết **vì sao có từng khối** trong code.

### 4.1. Close-book vs open-book (RAG)

LLM “nhớ” luật trong trọng số thì không chỉ được Điều nào, và bịa số hiệu.
**RAG**: tìm vài đoạn trong kho, nhét vào prompt, bắt viết từ đó.

Trong code: kho = từng **Điều** (`legal_knowledge_records` + Chroma), không phải
chunk 512 token Wikipedia.

File: `backend/src/services/agents/legal_assistant/node.py`.

### 4.2. BM25 (truy hồi thưa)

Chấm tài liệu theo từ xuất hiện, phạt văn bản dài, hạ điểm từ quá phổ biến (IDF).
Giỏi số hiệu (`38/2019/QH14`, `Điều 25`). Yếu khi người nói “sa thải” còn luật
nói “đơn phương chấm dứt”.

Tham số đồ án: `k1=1.2`, `b=0.65` trong `config.yaml`.
Tách từ tiếng Việt: `underthesea` (Python 3.10).

### 4.3. Embedding + cosine (truy hồi dày)

Một đoạn → vector; câu gần nghĩa thì gần trong không gian. Đồ án:
`gemini-embedding-001`, cắt **1536** chiều (Matryoshka). Đổi model/chiều = xóa
volume `chroma_data` và index lại.

### 4.4. Reciprocal Rank Fusion (RRF)

Điểm BM25 và cosine **không cùng thước** — không cộng thô. RRF cộng
`weight / (k + hạng)` theo từng bảng xếp hạng.

Đồ án: `rrf_k=60`, `dense_weight=3`, `bm25_weight=1`, lấy `top_k=8`.
File: `backend/src/services/vector_store/hybrid.py`.

### 4.5. HyDE

Câu hỏi ngắn, luật dài. LLM viết 5–6 câu “giọng văn bản”, rồi **nhúng đoạn giả**
để tìm vector. Đoạn giả không hiện cho user như đáp án.

Bật: `legal_assistant.hyde.enabled: true`. Rewrite nhiều biến thể đang **tắt**.

### 4.6. LLM filter vs rerank

Rerank chéo (cặp câu hỏi–Điều) đang tắt: Gemini không có cổng rerank.
Thay bằng `llm_filter`: hỏi PASS/DROP từng Điều, song song, `min_keep=2`.

### 4.7. Hallucination và hậu kiểm citation

Sau khi sinh câu, chỉ giữ số Điều **có trong tập vừa truy hồi**. Diễn giải sai
trên Điều đúng thì lớp này không bắt — hạn chế đã biết.

### 4.8. FTS PostgreSQL tiếng Việt

Không có từ điển FTS tiếng Việt. Đồ án: cột generated `search_vector` =
`to_tsvector('simple', immutable_unaccent(...))`. Tìm trên bản không dấu, **hiển
thị bản còn dấu**. Highlight ở React, không dùng `ts_headline`.

Ba tầng: số Điều → `ts_rank` → `pg_trgm` (ngưỡng 0.3).
File: `backend/src/services/legal/search.py`.

### 4.9. JWT, SSE, SPA

- **JWT**: access 15 phút + refresh 7 ngày, claim `type` để không lấy nhầm token.
  File: `backend/src/core/security.py`.
- **SSE**: một HTTP giữ lâu, server đẩy `status` / `token` / `result`. Trình duyệt
  `EventSource` không gắn Bearer → frontend dùng **Fetch**.
  File: `frontend/src/lib/sse.ts`, `frontend/src/hooks/useChatStream.ts`.
- **SPA**: một lần tải JS, React Router đổi trang. Docker: nginx + fallback
  `index.html`.

### 4.10. Lý thuyết “nhỏ nhưng làm hỏng demo nếu không biết”

- HTTP không trạng thái → mỗi request tự mang JWT.
- `async`/`await`: chờ Gemini/Postgres không chặn hết process; BM25+Chroma nặng
  được đẩy `asyncio.to_thread` để heartbeat SSE còn đập.
- Cột `messages.seq` (Identity): `created_at` trong cùng transaction Postgres
  có thể trùng, sort theo thời gian làm đảo câu hỏi/đáp.
- Hội thoại người khác: trả **404** (không 403) để khỏi dò tồn tại.
- Lịch tuân thủ: **rule trong Python** (`seed.py`), không phải LLM.

---

## 5. Bản đồ thư mục (chỉ việc cần nhớ)

```text
AI-LEGAL-ASSISTANT/
├── docker-compose.yml      3 dịch vụ: postgres, backend, frontend
├── .env.example            bí mật cho Compose (copy thành .env ở GỐC)
├── corpus/law_manifest.json
├── data/base_data.json     ~3844 Điều
├── backend/
│   ├── config.yaml         hành vi RAG, cổng, HyDE, RRF
│   ├── alembic/            schema
│   ├── src/main.py         tạo app + lifespan
│   ├── src/config.py       YAML + env
│   ├── src/core/           DB, JWT, rate limit, deps
│   ├── src/models/         bảng
│   ├── src/routers/        HTTP
│   ├── src/services/       nghiệp vụ
│   └── tests/
├── frontend/src/
│   ├── App.tsx             route
│   ├── pages/              một file ~ một màn
│   ├── hooks/useChatStream.ts
│   ├── lib/api.ts          Axios + refresh
│   └── store/auth.ts       Zustand phiên
└── Baocao/                 báo cáo XeLaTeX
```

Router backend ↔ việc:

| File router | Việc |
| --- | --- |
| `auth.py` | Đăng ký, login, refresh, đổi mật khẩu |
| `conversations.py` | Hội thoại, tin nhắn |
| `legal.py` | SSE hỏi đáp |
| `laws.py` | Catalog, cây, FTS |
| `documents.py` | Upload + soát xét nền |
| `compliance.py` | Rule, task, sinh lịch |
| `admin.py` | Corpus, user, reindex |
| `lab.py` | Chạy hàng loạt câu (admin) |
| `health.py` | Docker healthcheck, không gọi Gemini |

---

## 6. Thứ tự đọc code (như tự viết lại)

Đừng đọc `node.py` trước. Đừng đọc `prompt.py` trước. Làm theo lớp.

### Ngày 1 — Xương sống HTTP

1. `backend/src/main.py` — lifespan: kết nối DB, sync catalog, seed rule, cố
   index (fail thì `index_ready=False`).
2. `backend/src/core/deps.py` — `get_current_user`, `require_role`.
3. `backend/src/routers/auth.py` + `models/user.py` — bootstrap admin.
4. `frontend/src/store/auth.ts` + `lib/api.ts` — token, interceptor 401.
5. `frontend/src/App.tsx` — `RequireAuth`, lazy admin.

**Câu tự hỏi:** Tại sao refresh không gọi được `/laws`? (claim `type`).

### Ngày 2 — Tra cứu (không LLM)

1. `scripts/load_postgres.py` — JSON → `legal_knowledge_records`.
2. `models/legal.py` — cột generated `search_vector`, `article_number`.
3. `services/legal/search.py` — ba tầng FTS.
4. `routers/laws.py` + `frontend/src/pages/LawsPage.tsx`, `LawDetailPage.tsx`.

**Câu tự hỏi:** Gõ `thue gtgt` ra hit, đoạn trích còn dấu ở đâu?

### Ngày 3 — RAG (trái tim đồ án)

1. `config.yaml` mục `legal_assistant` + `vector_store` — bật/tắt HyDE, filter.
2. `services/vector_store/hybrid.py` — RRF.
3. `services/vector_store/chroma.py` + `index_builder.py` — lúc nào nhúng lại.
4. `services/agents/legal_assistant/agent.py` — `StateGraph` 7 nút, **không**
   checkpointer (history từ Postgres).
5. `node.py` từ trên xuống: intent → HyDE → retrieve → rerank (tắt) → filter →
   generate → format.
6. `routers/legal.py` — ghi tin user **trước** khi gọi graph; SSE.
7. `frontend/src/hooks/useChatStream.ts` + `lib/sse.ts`.

**Câu tự hỏi:** Intent SKIP thì Chroma có bị gọi không? (Không.)

### Ngày 4 — Hợp đồng và lịch

1. `services/contracts/extract.py` — lớp chữ PDF; rỗng thì fail lúc tải.
2. `services/contracts/reviewer.py` — mỗi clause = một retrieval.
3. `routers/documents.py` — 202 + `BackgroundTasks`.
4. `services/compliance/seed.py` — 12 rule, `applies_to`, `legal_refs`.
5. `services/compliance/generator.py` — unique (org, rule, kỳ).

---

## 7. Bốn luồng, từng file

### 7.1. Người dùng gửi câu hỏi

```text
ChatPage
  → useChatStream → Fetch POST /api/v1/legal/chat/stream  (Bearer)
      → legal.py: persist user message (Postgres, có seq)
      → load_history (tối đa ~6 lượt)
      → LegalAssistantAgent.answer_with_progress
          → 7 node LangGraph
          → SSE: status, token, result
      → persist assistant + citations + trace
  → CitationList bấm → /laws/:lawId/...
```

Nếu `app.state.index_ready` sai: 503, không mở SSE giả.

### 7.2. Tra cứu không dấu

Không đi LangGraph. `GET /api/v1/laws/search?q=...` → `search.py`.

### 7.3. Soát hợp đồng

Upload → trích chữ ngay (201 `ready`) → POST review (202) → poll 2,5 giây
(TanStack Query) → bảng finding.

### 7.4. Lịch

Đăng ký kèm hồ sơ → `ensure_rules_seeded` + generate cửa sổ 3 tháng trước / 12
tháng tới. Đổi số lao động / kỳ GTGT → sinh lại, **không xóa** task đã `done`.

---

## 8. Quyết định thiết kế (đọc comment trong code cho khớp)

Những chỗ này dễ tưởng “bug” nếu không biết chủ đích:

1. **Cắt theo Điều**, không overlapping chunk — để dẫn chiếu nghề.
2. **Compose `.env` gốc** — sai file thì Docker không có key.
3. **`seq` trên messages** — không sort `created_at`.
4. **404 khi xem chéo hội thoại** — không 403.
5. **unaccent chỉ để index** — UI nhận Unicode đầy đủ.
6. **Rerank tắt, llm_filter bật** — phụ thuộc Gemini.
7. **HyDE bật, rewrite tắt** — độ trễ / hạn mức.
8. **BackgroundTasks** — chết container giữa soát xét thì mất việc (chưa Celery).
9. **Token `localStorage`** — đơn giản, rủi ro XSS; hướng nâng cấp cookie HttpOnly.
10. **Tên `competition_mode` trong API** — cờ nội bộ “chạy hàng loạt, bỏ intent”;
    giao diện gọi **Chạy hàng loạt** (`/admin/batch-eval`). Không phải kỳ thi.

---

## 9. `config.yaml` — chỉnh gì thì đụng chỗ nào

| Khóa | Ảnh hưởng |
| --- | --- |
| `hyde.enabled` | Có gọi LLM trước retrieve không |
| `vector_store.mode` | `hybrid` / chỉ BM25 / chỉ Chroma |
| `dense_weight` / `bm25_weight` / `rrf_k` / `top_k` | Phễu retrieval |
| `llm_filter.enabled` | Có PASS/DROP từng Điều không |
| `embeddings.dimensions` | **Bắt buộc** xóa Chroma và index lại |
| `short_memory.max_turns` | Độ dài ngữ cảnh chat |
| `llm.temperature` | Đồ án 0 — diễn giải ổn định |

Secret không nằm YAML: `LLM_API_KEY`, `JWT_SECRET_KEY`, `LEGAL_DATABASE_URL`.

---

## 10. Làm sao biết mình đã “tự xây” được

Bạn đạt mức đó khi làm được các việc sau **không nhìn file này**:

- [ ] Chỉ ra vì sao hỏi đáp cần Chroma còn trang Luật thì không.
- [ ] Sửa `top_k` và giải thích trade-off cửa sổ ngữ cảnh vs bỏ sót Điều.
- [ ] Thêm một rule tuân thủ mới trong `seed.py` và thấy task sau khi sinh lại.
- [ ] Giải thích một tin nhắn user đã nằm DB dù SSE bị ngắt giữa chừng.
- [ ] Chỉ đường code highlight FTS trên chữ có dấu.
- [ ] Dựng lại môi trường từ máy trắng bằng mục 2.2.

Khi sửa RAG: đổi `config.yaml` trước, đo tay vài câu (thử việc, GTGT quý, số
hiệu Điều), rồi mới đụng `hybrid.py` hay prompt.
