# ĐỀ CƯƠNG CHI TIẾT KHÓA LUẬN TỐT NGHIỆP

**Tên đề tài dự kiến:** Nghiên cứu, Xây dựng và Đánh giá Hệ thống Trợ lý AI Tư vấn Pháp luật Chuyên sâu cho Doanh nghiệp Vừa và Nhỏ (SMEs) tại Việt Nam
**Ngành:** Công nghệ Thông tin / Khoa học Máy tính / Khoa học Dữ liệu
**Mã số đề tài:** [Cập nhật theo Trường]

---

## TỔNG QUAN ĐỀ TÀI & TÍNH CẤP THIẾT

Doanh nghiệp vừa và nhỏ (SME) chiếm hơn 97% tổng số doanh nghiệp tại Việt Nam, đóng góp đáng kể vào GDP và tạo việc làm. Tuy nhiên, các SME thường gặp hạn chế lớn về chi phí để duy trì bộ phận pháp chế chuyên trách. Hệ thống pháp luật doanh nghiệp Việt Nam (Thuế, Lao động, Đăng ký kinh doanh, Sở hữu trí tuệ, Hợp đồng) lại rất phức tạp, liên tục thay đổi với nhiều văn bản dưới luật (Nghị định, Thông tư). Việc vi phạm quy định pháp luật do thiếu thông tin dẫn đến các rủi ro pháp lý và thiệt hại tài chính nặng nề.

Ứng dụng Trí tuệ Nhân tạo (AI), đặc biệt là Mô hình Ngôn ngữ Lớn (LLMs) kết hợp Kiến trúc Retrieval-Augmented Generation (RAG) nâng cao, mở ra giải pháp tự động hóa tư vấn pháp lý với chi phí tối ưu, độ chính xác cao và có căn cứ trích dẫn rõ ràng.

---

## CẤU TRÚC BÁO CÁO KHÓA LUẬN (5 CHƯƠNG)

### CHƯƠNG 1: GIỚI THIỆU TỔNG QUAN
- **1.1. Bối cảnh và Tính cấp thiết của Đề tài**
  - Thực trạng pháp lý của các Doanh nghiệp Vừa và Nhỏ (SMEs) tại Việt Nam.
  - Thách thức trong tra cứu, tuân thủ và soát xét pháp lý cho SME.
- **1.2. Mục tiêu Nghiên cứu và Đóng góp của Đề tài**
  - *Mục tiêu 1 (Thực nghiệm/Thi đấu):* Tối ưu hóa mô hình Retrieval & QA trên bộ dữ liệu benchmark 2.000 câu hỏi pháp lý SME (Vietnamese Legal AI Competition - R2AI).
  - *Mục tiêu 2 (Ứng dụng/Sản phẩm):* Xây dựng hệ thống Trợ lý Virtual Legal Assistant hoàn chỉnh cho SME (Hỏi đáp pháp lý, Soát xét hợp đồng, Cảnh báo tuân thủ).
- **1.3. Đối tượng và Phạm vi Nghiên cứu**
  - Đối tượng: Các kỹ thuật Hybrid RAG (Dense/Sparse Retrieval, Cross-Encoder Reranking), Open-Source LLMs (Qwen2.5, PhoGPT) và Hệ thống VBQPPL doanh nghiệp Việt Nam.
  - Phạm vi: Hệ thống pháp luật điều chỉnh SME (Luật Hỗ trợ DNNVV, Luật Doanh nghiệp, Luật Thuế, Bộ luật Lao động, Luật SHTT, Bộ luật Dân sự).
- **1.4. Bố cục của Báo cáo Khóa luận**

---

### CHƯƠNG 2: CƠ SỞ LÝ THUYẾT & TỔNG QUAN CÔNG NGHỆ
- **2.1. Cấu trúc Hệ thống Văn bản Quy phạm Pháp luật Việt Nam liên quan SME**
  - Phân cấp hiệu lực pháp lý (Luật - Nghị định - Thông tư).
  - Cấu trúc tiêu chuẩn của một văn bản pháp luật (Phần - Chương - Mục - Điều - Khoản - Điểm).
  - Hiện tượng viện dẫn chéo (Cross-referencing) và văn bản hướng dẫn thi hành.
- **2.2. Kỹ thuật Truy hồi Thông tin (Information Retrieval - IR)**
  - Keyword Matching & Sparse Retrieval: Thuật toán BM25 và đặc thù xử lý tiếng Việt (`underthesea`/`pyvi`).
  - Dense Vector Retrieval: Embedding Models đa ngôn ngữ và tiếng Việt (`multilingual-e5-large`, `bge-m3`).
  - Hybrid Search & Reciprocal Rank Fusion (RRF).
- **2.3. Kỹ thuật Tinh lọc và Trình thứ tự (Reranking)**
  - Cross-Encoder Models trong bài toán Legal Search (`bge-reranker-large`).
- **2.4. Mô hình Ngôn ngữ Lớn (LLMs) & Kiến trúc RAG**
  - Khái niệm Retrieval-Augmented Generation (RAG) và các rủi ro (Hallucination, Citation Misalignment).
  - Mô hình open-source (< 14B tham số) và Prompt Engineering trong lĩnh vực pháp lý.
  - Legal Guardrails & Post-processing trích xuất Citation tự động.

---

### CHƯƠNG 3: PHÂN TÍCH, THIẾT KẾ VÀ XÂY DỰNG HỆ THỐNG
- **3.1. Phân tích Yêu cầu Hệ thống**
  - Yêu cầu chức năng: Tra cứu pháp lý theo ngữ cảnh, Hỏi đáp có trích dẫn Điều luật chuẩn xác, Soát xét hợp đồng rủi ro cho SME, Cảnh báo lịch tuân thủ.
  - Yêu cầu phi chức năng: Thời gian phản hồi (Latency), Độ chính xác trích dẫn (Precision/Recall/F2), Tính bảo mật dữ liệu doanh nghiệp.
- **3.2. Đóng đóng Dữ liệu & Xây dựng Corpus Pháp luật SME (Legal Corpus Builder)**
  - Thu thập, chuẩn hóa định dạng văn bản và lưu trữ Metadata.
  - Chiến lược Chunking theo cấp độ Điều (Article-level Chunking) bảo toàn ngữ cảnh.
- **3.3. Thiết kế Kiến trúc Pipeline Truy hồi & Hỏi đáp (Multi-tier Legal RAG Pipeline)**
  - Sơ đồ luồng dữ liệu (Data Pipeline Architecture).
  - Tích hợp Dense Retrieval + Sparse BM25 + Rerank Engine.
  - Thiết kế Prompt Template & Citation Guardrail.
- **3.4. Thiết kế các Module Mở rộng cho SME**
  - Module Soát xét Rủi ro Hợp đồng (Contract Risk Review Module).
  - Module Cảnh báo Nghĩa vụ Tuân thủ (SME Compliance Module).
- **3.5. Thiết kế Ứng dụng Web (Web Application Architecture)**

  Nội dung dưới đây mô tả kiến trúc **đã hiện thực** trong sản phẩm, không phải
  phương án dự kiến.

  - **3.5.1. Tổng quan kiến trúc ba lớp**
    - Lớp trình bày: SPA React 19 + Vite + TypeScript, Tailwind CSS 4, TanStack
      Query cho vòng đời dữ liệu server, Zustand cho phiên đăng nhập, React
      Router cho điều hướng. Khi deploy, nginx serve tệp tĩnh và proxy `/api`
      sang backend nên frontend và backend cùng origin.
    - Lớp ứng dụng: FastAPI, chia theo router nghiệp vụ `auth`, `conversations`,
      `legal` (hỏi đáp), `laws` (tra cứu), `documents` (hợp đồng), `compliance`,
      `admin`, `lab`. Pipeline RAG nằm trong `services/agents`, tách khỏi tầng
      HTTP để tái sử dụng được cho cả đường chat và đường soát xét hợp đồng.
    - Lớp dữ liệu: PostgreSQL 17 cho dữ liệu nghiệp vụ và corpus (kèm full-text
      search), ChromaDB cho vector, BM25 nạp vào bộ nhớ với cache theo manifest.

  - **3.5.2. Mô hình dữ liệu quan hệ**
    - Nghiệp vụ: `organizations`, `users`, `conversations`, `messages`,
      `documents`, `contract_reviews`, `contract_findings`, `compliance_rules`,
      `compliance_tasks`, `audit_logs`.
    - Tra cứu: `legal_knowledge_records` (giữ nguyên schema của pipeline thi đấu)
      và `laws` — bảng danh mục dẫn xuất, đồng bộ lại mỗi lần khởi động.
    - Schema do Alembic quản lý; ORM là SQLAlchemy 2.0 async trên driver asyncpg.

  - **3.5.3. Tra cứu toàn văn cho tiếng Việt**
    - PostgreSQL không có từ điển full-text tiếng Việt, nên chiến lược là bỏ dấu
      bằng `unaccent` rồi dùng cấu hình `simple`. Vì `unaccent()` chỉ ở mức
      `STABLE`, phải bọc thành hàm `IMMUTABLE` mới tạo được cột generated
      `search_vector tsvector` và index GIN trên đó.
    - Ba chiến lược tìm kiếm xếp theo độ ưu tiên: tra trực tiếp theo số Điều,
      full-text `ts_rank`, và `pg_trgm` để cứu truy vấn gõ sai.
    - Việc bôi đậm từ khóa **không** dùng `ts_headline`: hàm này chạy trên cột đã
      bỏ dấu nên đoạn trích trả về mất hết dấu tiếng Việt. Backend chỉ trả về
      danh sách từ khóa đã tách, client tự bôi đậm trên văn bản gốc theo kiểu bỏ
      qua dấu.

  - **3.5.4. Streaming và lịch sử hội thoại**
    - Hỏi đáp dùng Server-Sent Events với ba loại sự kiện: `status` (tiến độ từng
      node của graph), `token` (token LLM), `result` (câu trả lời kèm trích dẫn).
      Client đọc bằng Fetch Streams API thay vì `EventSource`, vì `EventSource`
      chỉ hỗ trợ GET và không gửi được header `Authorization`.
    - Lịch sử hội thoại nằm ở PostgreSQL thay vì `InMemorySaver` của LangGraph,
      nên sống sót qua restart và chạy được nhiều worker. Message được sắp theo
      cột `seq` (identity) chứ không theo `created_at`: `now()` của PostgreSQL trả
      về thời điểm bắt đầu transaction, mà câu hỏi và câu trả lời được ghi trong
      cùng một request nên `created_at` bằng nhau và thứ tự sẽ thành ngẫu nhiên.

  - **3.5.5. Xác thực, phân quyền và bảo vệ hạn mức**
    - Mật khẩu băm bằng argon2; JWT gồm access token ngắn hạn và refresh token,
      phân biệt bằng trường `typ` để không dùng lẫn được hai loại.
    - Bốn vai trò `owner | accountant | hr | admin` với dependency
      `require_role`. Dữ liệu hợp đồng và lịch tuân thủ cách ly theo
      `organization_id`; hội thoại cách ly theo `user_id` và trả 404 (không phải
      403) khi truy cập chéo để không tiết lộ sự tồn tại của tài nguyên.
    - CORS thu về danh sách origin cấu hình được; `slowapi` giới hạn tần suất
      trên endpoint chat và upload để tránh cạn quota LLM.

  - **3.5.6. Khả năng suy giảm chức năng có kiểm soát**
    - Việc dựng vector index không phải điều kiện sống của backend: khi thiếu API
      key hoặc provider embedding lỗi, đăng nhập, tra cứu văn bản và lịch tuân
      thủ vẫn hoạt động, chỉ endpoint hỏi đáp trả 503 kèm thông báo giải thích.
      Đây là lựa chọn thiết kế có chủ ý, vì phần lớn giá trị tra cứu không phụ
      thuộc vào LLM.
    - Soát xét hợp đồng chạy nền bằng `BackgroundTasks`, client poll trạng thái
      `pending | processing | done | failed`.
    - Việc index hỗ trợ chạy tiếp: chỉ dựng lại từ đầu khi đổi embedding model
      hoặc số chiều vector, còn lại bỏ qua những Điều đã có vector — cần thiết vì
      hạn mức của tầng miễn phí không cho phép index lại toàn bộ corpus.

---

### CHƯƠNG 4: THỬ NGHIỆM, ĐÁNH GIÁ VÀ KẾT QUẢ
- **4.1. Môi trường Thử nghiệm & Bộ Dữ liệu Đánh giá**
  - Bộ benchmark 2.000 câu hỏi R2AI (Thực tế thực địa SME).
  - Bộ testcase thực tế mở rộng từ các loại hình hợp đồng doanh nghiệp.
- **4.2. Kịch bản Thử nghiệm & Đánh giá Retrieval (Trục 1)**
  - So sánh hiệu năng các mô hình Embedding (`e5-large`, `bge-m3`, `PhoBERT-SimCSE`).
  - Đánh giá tác động của BM25, Reranker và chiến lược chọn Top-K đối với F2-Score.
- **4.3. Kịch bản Thử nghiệm & Đánh giá QA Quality (Trục 2)**
  - Đánh giá theo 5 tiêu chí: Căn cứ pháp lý, Độ chính xác, Đầy đủ, Thực tiễn, Rõ ràng (dùng LLM-as-a-Judge & Đánh giá chuyên gia).
- **4.4. Đánh giá Module Soát xét Hợp đồng & UI Web App**
- **4.5. Phân tích Kết quả, Thảo luận & Nhận xét**

---

### CHƯƠNG 5: KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN
- **5.1. Kết luận những Kết quả Đạt được**
  - Về mặt lý thuyết & đóng góp khoa học.
  - Về mặt thực tiễn & sản phẩm ứng dụng.
- **5.2. Hạn chế của Đề tài**
  - Giới hạn kích thước mô hình open-source (< 14B).
  - Độ phức tạp của văn bản hợp nhất và thay đổi luật theo thời gian.
- **5.3. Hướng phát triển trong Tương lai**
  - Nghiên cứu ứng dụng Legal Knowledge Graph (GraphRAG).
  - Xây dựng Multi-Agent System hỗ trợ đàm phán pháp lý tự động cho SME.

---

## KẾ HOẠCH TIẾN ĐỘ THỰC HIỆN (ROADMAP)

| Tuần | Nội dung công việc | Sản phẩm đầu ra |
|---|---|---|
| Tuần 1 - 2 | Thu thập Legal Corpus SME, Xây dựng Corpus Builder | `corpus/builder.py`, `corpus/law_manifest.json` |
| Tuần 3 - 4 | Cài đặt Hybrid Search (Dense + BM25 + Reranker), Chạy Baseline R2AI | `src/retrieval/`, submission đầu tiên trên R2AI |
| Tuần 5 - 6 | Tối ưu Generation LLM, Citation Verification & Post-processing | `src/generation/`, Nộp bài tối ưu R2AI Leaderboard |
| Tuần 7 - 8 | Xây dựng Module Soát xét Hợp đồng & Web Application UI | `src/services/`, `app/ui/` |
| Tuần 9 - 10| Thử nghiệm đa chiều, Thu thập chỉ số đánh giá, Hoàn thiện Quyển Khóa luận | Báo cáo Khóa luận tốt nghiệp (70-100 trang) |
