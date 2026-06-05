# Kế Hoạch Thực Hiện End-to-End: Cuộc Thi Vietnamese Legal AI (R2AI Stage 1)

> **Cuộc thi:** Truy hồi và Hỏi đáp Văn bản Pháp luật Tiếng Việt
> **Deadline nộp bài:** 30/06/2026 — 23:59 (UTC+7)
> **Công bố Top 10:** 05/07/2026
> **DemoDay:** 11/07/2026
> **Leaderboard:** http://leaderboard.aiguru.com.vn/

---

## Phân Tích Bài Toán (Đọc Kỹ Trước Khi Làm)

### Hiểu đúng bản chất cuộc thi

Sau khi đọc kỹ toàn bộ `docs/` và `data/`, đây **không phải** bài toán xây dựng chatbot thông thường. Đây là bài toán **Legal Information Retrieval + Question Answering** với **2.000 câu hỏi pháp lý về SME**, được chấm điểm theo hai trục độc lập:

**Trục 1 — Retrieval (tự động, ngay lập tức):**
Hệ thống tự động tìm pattern `Điều X` trong trường `answer` của bài nộp và so sánh với đáp án. Đây là điểm **F2-score**, ưu tiên **Recall gấp đôi Precision**.

**Trục 2 — QA Quality (bán tự động, chấm theo tuần):**
LLM-as-a-Judge + chuyên gia pháp luật chấm 5 tiêu chí: căn cứ pháp lý, chính xác nội dung, đầy đủ toàn diện, thực tiễn, rõ ràng. 4 tiêu chí cuối hiện = 0.0, sẽ cập nhật sau mỗi kỳ chấm hàng tuần.

### Phân tích câu hỏi trong data/R2AIStage1DATA.json

Đọc kỹ 2.000 câu hỏi, các chủ đề bao gồm:

| Nhóm chủ đề | Ví dụ câu hỏi | Văn bản pháp luật liên quan chính |
|---|---|---|
| Hỗ trợ DNNVV | Điều kiện hưởng hỗ trợ, quỹ tín dụng, ươm tạo | Luật 04/2017/QH14, NĐ 80/2021 |
| Thuế | Đăng ký thuế, khai thuế, hoàn thuế, cưỡng chế | Luật 38/2019/QH14 |
| Lao động & BHXH | Hợp đồng lao động, xử phạt, bảo hiểm | Bộ luật LĐ 45/2019, Luật BHXH |
| Đăng ký doanh nghiệp | Thành lập, thay đổi vốn, chi nhánh | Luật DN 59/2020, NĐ 01/2021 |
| Sở hữu trí tuệ | Nhãn hiệu, kiểu dáng, sáng chế, tên TM | Luật SHTT 50/2005 sửa đổi |
| Hóa đơn điện tử | Lập hóa đơn, chuyển đổi | NĐ 123/2020, TT 78/2021 |
| Kế toán – Tài chính | Báo cáo tài chính, hạch toán | Luật Kế toán, Thông tư BTC |
| Hợp đồng dân sự | Vô hiệu, bồi thường, trọng tài | Bộ luật Dân sự 91/2015 |
| Bảo vệ người tiêu dùng | Thu thập dữ liệu, quảng cáo, bồi thường | Luật BVNTD 19/2023 |
| An toàn lao động | Quan trắc môi trường, tai nạn, xử phạt | NĐ 12/2022/NĐ-CP |

**Lưu ý quan trọng:** Khoảng 30-40% câu hỏi cuối (từ ~ID 1500 trở đi) là câu hỏi **tổng hợp đa văn bản**, tức là một câu hỏi duy nhất đòi hỏi tra cứu và kết hợp 2-3 lĩnh vực pháp luật khác nhau. Đây là phần khó nhất và cần kiến trúc retrieval đủ mạnh.

### Ràng buộc cứng (vi phạm = bị loại)

- Mô hình phải **open-source**, **< 14B tham số**, **phát hành trước 01/03/2026**
- **Không dùng** GPT-4o, Gemini, Claude, hay bất kỳ model đóng nào
- Nộp file `results.json` → nén thành `submission.zip` phẳng (không có thư mục con)
- Tối đa **10 lần/ngày** ở Public Phase, **5 lần tổng cộng** ở Private Phase
- Phải nộp **working notes paper** mô tả phương pháp thì kết quả mới được tính chính thức

---

## Timeline & Phân Công

| Thời gian | Mốc | Người phụ trách |
|---|---|---|
| 05–07/06 | Đọc toàn bộ docs, phân tích câu hỏi, xác định danh sách văn bản cần thu thập | Toàn team |
| 08–10/06 | Thu thập corpus văn bản pháp luật, chuẩn hóa định dạng | Data team |
| 11–13/06 | Chunking theo Điều, embedding, xây index | ML team |
| 14–16/06 | Baseline pipeline chạy được, nộp bài đầu tiên | ML team |
| 17–21/06 | Tối ưu retrieval (hybrid, reranker) | ML team |
| 22–25/06 | Tối ưu answer generation, prompt engineering | NLP team |
| 26–28/06 | Chạy toàn bộ 2.000 câu, validate, dry-run | Toàn team |
| 29–30/06 | Buffer, fix bug, nộp bài cuối | Toàn team |
| **30/06** | **Deadline 23:59 UTC+7** | |

---

## Giai Đoạn 1 — Xây Dựng Corpus Văn Bản Pháp Luật

Đây là giai đoạn **quan trọng nhất**. Nếu corpus thiếu một điều luật, pipeline dù tốt đến đâu cũng không thể tìm ra đáp án đúng.

### 1.1 Danh sách văn bản cần thu thập

Dựa trên phân tích câu hỏi, danh sách **tối thiểu** cần có:

**Nhóm DNNVV (chiếm tỉ trọng lớn nhất):**
- `04/2017/QH14` — Luật Hỗ trợ doanh nghiệp nhỏ và vừa
- `80/2021/NĐ-CP` — Nghị định hướng dẫn thi hành Luật Hỗ trợ DNNVV
- `38/2023/NĐ-CP` — Nghị định về hỗ trợ DNNVV (nếu có sửa đổi sau 80/2021)

**Nhóm Doanh nghiệp:**
- `59/2020/QH14` — Luật Doanh nghiệp
- `01/2021/NĐ-CP` — Nghị định về đăng ký doanh nghiệp
- `45/2024/NĐ-CP` — Nghị định sửa đổi về đăng ký doanh nghiệp (có đề cập trong câu hỏi)

**Nhóm Thuế:**
- `38/2019/QH14` — Luật Quản lý thuế
- `123/2020/NĐ-CP` — Nghị định về hóa đơn, chứng từ
- `78/2021/TT-BTC` — Thông tư hướng dẫn về hóa đơn điện tử

**Nhóm Lao động:**
- `45/2019/QH14` — Bộ luật Lao động
- `12/2022/NĐ-CP` — Nghị định xử phạt vi phạm hành chính về lao động, BHXH
- `28/2020/NĐ-CP` — Nghị định xử phạt vi phạm hành chính (lao động cũ, kiểm tra chồng)
- `41/2024/QH15` — Luật Bảo hiểm xã hội (mới nhất)

**Nhóm Sở hữu trí tuệ:**
- `50/2005/QH11` — Luật Sở hữu trí tuệ (và các lần sửa đổi 36/2009, 07/2022)
- `65/2023/NĐ-CP` — Nghị định hướng dẫn Luật SHTT (mới nhất)

**Nhóm Dân sự:**
- `91/2015/QH13` — Bộ luật Dân sự

**Nhóm Kế toán – Tài chính:**
- `88/2015/QH13` — Luật Kế toán
- Các Thông tư chế độ kế toán doanh nghiệp nhỏ và vừa (TT 133/2016, TT 200/2014)

**Nhóm Bảo vệ người tiêu dùng:**
- `19/2023/QH15` — Luật Bảo vệ quyền lợi người tiêu dùng (mới nhất)

> **Hành động:** Tạo file `corpus/law_manifest.json` liệt kê toàn bộ văn bản cần thu thập, có `law_id`, `law_name` chuẩn, URL nguồn, và trạng thái (chưa có / đã có / đã xử lý).

### 1.2 Nguồn thu thập

- **thuvienphapluat.vn** — Nguồn chính, đầy đủ nhất, có text sạch
- **vbpl.vn** — Cơ sở dữ liệu quốc gia, bản gốc chính thống
- **congbao.chinhphu.vn** — Công báo, bản gốc khi cần xác minh

Ưu tiên lấy từ **thuvienphapluat.vn** vì đã có text rõ ràng, cấu trúc Điều/Khoản được tổ chức tốt.

### 1.3 Chuẩn hóa tên văn bản (CỰC KỲ QUAN TRỌNG)

Hệ thống chấm điểm so sánh từng ký tự trong `relevant_docs` và `relevant_articles`. Tên văn bản phải theo đúng công thức:

```
[Loại văn bản] [Mã văn bản] [Trích yếu nội dung]
```

Ví dụ chuẩn từ docs:
```
04/2017/QH14|Luật Hỗ trợ doanh nghiệp nhỏ và vừa
80/2021/NĐ-CP|Nghị định Quy định chi tiết và hướng dẫn thi hành một số điều của Luật Hỗ trợ doanh nghiệp nhỏ và vừa
```

> **Hành động:** Xây dựng file `corpus/law_name_dictionary.json` — một bảng tra cứu dứt khoát: `law_id → tên chuẩn`. Tất cả output đều phải tra từ bảng này, không được tự gõ tay.

---

## Giai Đoạn 2 — Tiền Xử Lý & Chunking

### 2.1 Nguyên tắc chunking cốt lõi

Hệ thống chấm **tự động tìm pattern `Điều X`** trong câu trả lời. Điều này có nghĩa:

- Đơn vị cơ bản của corpus phải là **một Điều** (article-level), không phải đoạn văn hay câu
- Mỗi chunk phải có metadata: `law_id`, `law_name`, `article_id` (ví dụ: `Điều 5`)
- `full_reference` phải có dạng: `04/2017/QH14|Luật Hỗ trợ doanh nghiệp nhỏ và vừa|Điều 5`

**Xử lý Điều dài:** Một số Điều trong Bộ luật Dân sự hay Luật Quản lý thuế có thể dài tới 1.000-2.000 token. Trong trường hợp này, chia thành các sub-chunk nhưng **vẫn giữ nguyên metadata Điều cha**.

### 2.2 Cấu trúc dữ liệu mỗi chunk

```json
{
  "chunk_id": "04-2017-QH14_dieu5",
  "law_id": "04/2017/QH14",
  "law_name": "Luật Hỗ trợ doanh nghiệp nhỏ và vừa",
  "article_id": "Điều 5",
  "full_reference": "04/2017/QH14|Luật Hỗ trợ doanh nghiệp nhỏ và vừa|Điều 5",
  "text": "Điều 5. Tiêu chí xác định doanh nghiệp nhỏ và vừa..."
}
```

### 2.3 Xây dựng hai index song song

- **Index 1 (Article-level):** Mỗi entry = một Điều → dùng để trả về `relevant_articles`
- **Index 2 (Document-level):** Mỗi entry = một đoạn tóm tắt toàn bộ văn bản → dùng để trả về `relevant_docs`

---

## Giai Đoạn 3 — Embedding & Vector Store

### 3.1 Lựa chọn mô hình embedding

Yêu cầu: open-source, phát hành trước 01/03/2026.

| Mô hình | Điểm mạnh | Lưu ý |
|---|---|---|
| `intfloat/multilingual-e5-large` | Đa ngôn ngữ mạnh, tiếng Việt tốt | Lựa chọn **khuyến nghị đầu tiên** |
| `bkai-foundation-models/vietnamese-bi-encoder` | Chuyên tiếng Việt | Kiểm tra release date |
| `BAAI/bge-m3` | Hybrid dense+sparse trong một model | Nếu muốn đơn giản hóa |
| `VoVanPhuc/sup-SimCSE-VietNamese-phobert-base` | Nhỏ, nhanh | Làm baseline nhanh |

**Chiến lược:** Test `multilingual-e5-large` trước. Nếu còn thời gian, chạy so sánh với `bge-m3`.

### 3.2 Vector store

- **Qdrant** (self-hosted Docker) — Khuyến nghị. Hỗ trợ hybrid search tốt, có payload filter
- **ChromaDB** — Đơn giản hơn, dùng khi prototype nhanh

### 3.3 BM25 song song (quan trọng với văn bản pháp luật)

Văn bản pháp luật có nhiều thuật ngữ kỹ thuật, số điều khoản, mã văn bản. BM25 (keyword matching) sẽ bắt được những trường hợp mà dense retrieval bỏ sót do mismatch ngữ nghĩa. Cài thêm `rank_bm25` song song là **bắt buộc**.

---

## Giai Đoạn 4 — Retrieval Pipeline

### 4.1 Pipeline cơ bản (xây trước, nộp bài đầu tiên)

```
Câu hỏi → Embed → Tìm top-20 (dense) → Trả về articles + docs
```

Mục tiêu: có bài nộp đầu tiên trong ngày **14-15/06** để biết điểm baseline.

### 4.2 Pipeline nâng cao (tối ưu sau)

```
Câu hỏi
  ├── Dense retrieval (top-20)
  └── BM25 retrieval (top-20)
       ↓
  Merge + Dedup (top-30 unique)
       ↓
  Reranker (cross-encoder)
       ↓
  Top-K articles (K = 10-15)
```

### 4.3 Chiến lược K — Bao nhiêu articles là đủ?

F2-score = (5 × P × R) / (4 × P + R). Vì β=2, **Recall quan trọng gấp đôi Precision**. Tính toán:

- Nếu một câu hỏi có 3 điều luật đúng trong đáp án:
  - Lấy top-5 đúng cả 3: P=3/5=0.6, R=1.0, F2=0.88
  - Lấy top-3 đúng cả 3: P=1.0, R=1.0, F2=1.0 ← lý tưởng
  - Lấy top-5 đúng 2: P=2/5=0.4, R=2/3=0.67, F2=0.59
  - Lấy top-3 đúng 2: P=2/3=0.67, R=2/3=0.67, F2=0.67

**Kết luận:** Thà lấy nhiều hơn (top 12-15) và bị giảm Precision, còn hơn bỏ sót. Nhưng đừng lấy quá nhiều (top 30+) vì sẽ đưa quá nhiều context sai vào prompt → answer quality giảm.

**Khuyến nghị:** Lấy top-12 đến top-15 cho mỗi câu hỏi.

### 4.4 Query Expansion cho câu hỏi tiếng Việt

Câu hỏi dùng ngôn ngữ đời thường, văn bản pháp luật dùng ngôn ngữ pháp lý. Ví dụ:
- Câu hỏi: "bị phạt bao nhiêu" → Văn bản: "xử phạt vi phạm hành chính... mức phạt tiền từ..."
- Câu hỏi: "công ty giữ bằng cấp" → Văn bản: "giữ bản chính văn bằng, chứng chỉ"

Chiến lược mở rộng truy vấn:
- **HyDE (Hypothetical Document Embeddings):** Dùng LLM sinh một đoạn văn pháp lý giả định cho câu hỏi, embed đoạn đó, tìm kiếm bằng embedding này thay vì embedding câu hỏi gốc
- **Thêm từ khóa pháp lý:** Map các từ thông dụng sang thuật ngữ pháp lý chuẩn

---

## Giai Đoạn 5 — Answer Generation

### 5.1 Lựa chọn mô hình sinh câu trả lời

Yêu cầu: open-source, < 14B, phát hành trước 01/03/2026.

| Mô hình | Điểm mạnh | Khuyến nghị |
|---|---|---|
| `Qwen2.5-7B-Instruct` | Tiếng Việt tốt, instruction following mạnh | **Thử trước** |
| `Qwen2.5-14B-Instruct` | Mạnh hơn, ở giới hạn 14B | Cần verify tham số chính xác |
| `vinai/PhoGPT-7B5-Instruct` | Chuyên tiếng Việt | Thử nếu Qwen không đủ tốt |
| `SeaLLMs/SeaLLM-7B-v2.5` | Đông Nam Á, có tiếng Việt | Phương án dự phòng |

**Lưu ý về `Qwen2.5-14B`:** Cần xác nhận chính xác số tham số ≤ 14B trước khi dùng, vì BTC có quyền yêu cầu chứng minh.

### 5.2 Thiết kế prompt

Hệ thống chấm điểm **tự động trích xuất `Điều X`** từ `answer`. Prompt phải buộc model:

1. Trích dẫn điều khoản cụ thể trong câu trả lời (ví dụ: "Theo Điều 4 Luật Hỗ trợ DNNVV...")
2. Trả lời bằng tiếng Việt rõ ràng, dễ hiểu
3. Không bịa điều luật không có trong context được cung cấp

Cấu trúc prompt tham khảo:

```
[SYSTEM]
Bạn là chuyên gia pháp lý AI chuyên về pháp luật doanh nghiệp Việt Nam.
Nhiệm vụ: trả lời câu hỏi pháp lý DỰA TRÊN và CHỈ DỰA TRÊN các điều luật được cung cấp.

Yêu cầu bắt buộc:
- Khi trích dẫn điều luật, phải ghi rõ "Điều X" trong câu trả lời (ví dụ: "Theo Điều 5 Luật Hỗ trợ doanh nghiệp nhỏ và vừa...")
- Không được suy diễn hoặc bịa thêm quy định ngoài context
- Trả lời đầy đủ, bao quát các khía cạnh của câu hỏi
- Ngôn ngữ rõ ràng, dễ hiểu cho người không chuyên

[USER]
Câu hỏi: {question}

Các điều luật liên quan:
---
{retrieved_articles_text}
---

Hãy trả lời câu hỏi trên.
```

### 5.3 Post-processing: Căn chỉnh citations

Sau khi model sinh ra `answer`, cần một bước post-processing để build `relevant_articles` và `relevant_docs`:

1. Parse tất cả `Điều X` xuất hiện trong `answer`
2. Với mỗi `Điều X`, match với metadata của articles đã retrieve
3. Build danh sách `relevant_articles` từ các articles được match
4. Build `relevant_docs` từ các `law_id` duy nhất trong `relevant_articles`
5. Tra tên chuẩn từ `law_name_dictionary.json`

Đây là bước quan trọng để đảm bảo **ba trường `answer`, `relevant_articles`, `relevant_docs` nhất quán với nhau**.

---

## Giai Đoạn 6 — Định Dạng Output & Validation

### 6.1 Schema bắt buộc của từng entry

```json
{
  "id": 1,
  "question": "...",
  "answer": "Theo Điều 4 Luật Hỗ trợ doanh nghiệp nhỏ và vừa, doanh nghiệp...",
  "relevant_docs": [
    "04/2017/QH14|Luật Hỗ trợ doanh nghiệp nhỏ và vừa",
    "80/2021/NĐ-CP|Nghị định Quy định chi tiết và hướng dẫn thi hành một số điều của Luật Hỗ trợ doanh nghiệp nhỏ và vừa"
  ],
  "relevant_articles": [
    "04/2017/QH14|Luật Hỗ trợ doanh nghiệp nhỏ và vừa|Điều 4",
    "04/2017/QH14|Luật Hỗ trợ doanh nghiệp nhỏ và vừa|Điều 5",
    "80/2021/NĐ-CP|Nghị định Quy định chi tiết và hướng dẫn thi hành một số điều của Luật Hỗ trợ doanh nghiệp nhỏ và vừa|Điều 5"
  ]
}
```

### 6.2 Các lỗi thường gặp → kết quả bị 0 điểm

| Lỗi | Hậu quả |
|---|---|
| `answer` không chứa `Điều X` nào | Điểm retrieval = 0 cho câu đó |
| `relevant_articles` chứa `Điều X` nhưng `answer` không đề cập | Hệ thống chỉ tính `Điều X` trong `answer`, không tính trong `relevant_articles` |
| Tên văn bản sai format (ví dụ: thiếu "Nghị định", dùng tên tắt) | Không match với đáp án → 0 |
| File zip có thư mục con | Không được chấm điểm |
| Tên file không phải `results.json` | Không được chấm điểm |
| Thiếu ID câu hỏi | Entry đó bị coi là không hợp lệ |

### 6.3 Checklist trước mỗi lần nộp

- [ ] File tên đúng là `results.json`
- [ ] Có đủ 2.000 entries, không thiếu ID nào
- [ ] Mỗi entry có đủ 5 trường: `id`, `question`, `answer`, `relevant_docs`, `relevant_articles`
- [ ] Mỗi entry trong `answer` chứa ít nhất một pattern `Điều X`
- [ ] Format `relevant_docs`: `mã|tên` (2 phần cách bởi `|`)
- [ ] Format `relevant_articles`: `mã|tên|Điều X` (3 phần cách bởi `|`)
- [ ] Tên văn bản khớp với `law_name_dictionary.json`
- [ ] File zip không có thư mục con: `unzip -l submission.zip` phải hiện `results.json` ở root

---

## Giai Đoạn 7 — Đánh Giá Nội Bộ & Iteration

### 7.1 Xây dựng bộ test nội bộ

Vì không có train/dev set, cần tự tạo:

1. Chọn ~50-100 câu hỏi từ test set (rải đều các chủ đề)
2. Thủ công tra thuvienphapluat.vn, viết câu trả lời mẫu và xác định điều luật đúng
3. Dùng bộ này để đo F2-score nội bộ trước khi nộp chính thức

Đây là cách duy nhất để biết pipeline tốt đến đâu mà không tốn submission quota.

### 7.2 Thứ tự ưu tiên tối ưu

| Ưu tiên | Việc cần làm | Tác động |
|---|---|---|
| 🔴 Rất cao | Corpus đầy đủ, không thiếu văn bản nào | Retrieval recall tăng |
| 🔴 Rất cao | Tên văn bản đúng format 100% | Tránh mất điểm oan |
| 🟠 Cao | Thêm BM25 hybrid retrieval | F2 tăng đáng kể |
| 🟠 Cao | Prompt buộc model trích dẫn `Điều X` | QA score tăng |
| 🟡 Trung bình | Reranker cross-encoder | Precision tăng |
| 🟡 Trung bình | Tăng top-K lên 12-15 | Recall tăng |
| 🟢 Thấp | Query expansion / HyDE | Cải thiện nhỏ |
| 🟢 Thấp | Fine-tune embedding model | Tốn thời gian |

### 7.3 Chiến lược QA scoring hàng tuần

QA được chấm **mỗi tuần một lần**. Cần **chủ động promote** bài nộp tốt nhất lên leaderboard trước mỗi kỳ chấm. Đừng để quên — bài đang ở leaderboard lúc BTC chấm mới được tính điểm.

---

## Giai Đoạn 8 — Private Phase & DemoDay

### 8.1 Quản lý 5 lần nộp Private Phase

Chỉ có 5 lần tổng cộng. Kế hoạch đề xuất:

- **Lần 1:** Bài tốt nhất từ Public Phase (khoảng ngày 27-28/06 sau khi đã tối ưu xong)
- **Lần 2:** Dự phòng nếu phát hiện lỗi format sau lần 1
- **Lần 3-5:** Giữ lại, chỉ dùng nếu có cải thiện đáng kể đã được kiểm chứng trên bộ test nội bộ

### 8.2 Chuẩn bị DemoDay (nếu lọc vào Top 10)

- Chuẩn bị demo trực quan hệ thống
- Ghi lại kết quả thực tế trên một số câu hỏi tiêu biểu
- Chuẩn bị giải thích kiến trúc pipeline rõ ràng
- Chuẩn bị `working notes paper` (bắt buộc để kết quả được công nhận)

---

## Working Notes Paper — Nội Dung Cần Có

Paper này là **bắt buộc** để kết quả được tính chính thức:

1. **Giới thiệu bài toán** — mô tả ngắn gọn
2. **Thu thập dữ liệu** — liệt kê văn bản đã thu thập, nguồn, cách xử lý
3. **Kiến trúc hệ thống** — sơ đồ pipeline từ câu hỏi đến output
4. **Mô hình sử dụng** — tên model, số tham số, link Hugging Face, ngày phát hành (để BTC xác minh)
5. **Chiến lược retrieval** — chunking, embedding, hybrid search, reranking
6. **Chiến lược generation** — prompt template, post-processing
7. **Kết quả & phân tích** — điểm F2, QA score, ablation nếu có
8. **Hạn chế & hướng cải thiện**

---

## Rủi Ro Cần Lưu Ý

| Rủi ro | Xác suất | Cách phòng tránh |
|---|---|---|
| Corpus thiếu văn bản quan trọng | Cao | Đọc kỹ 200 câu hỏi cuối, nhiều câu đề cập văn bản ngoài nhóm quen thuộc |
| Tên văn bản sai format → mất điểm | Cao | Dùng dictionary cứng, validate tự động |
| Model ảo hallucinate `Điều X` không tồn tại | Trung bình | Prompt rõ ràng + post-process verify |
| Nộp sai format zip | Thấp nhưng nghiêm trọng | Checklist + script validate trước mỗi lần nộp |
| Dùng model phát hành sau 01/03/2026 | Thấp nhưng nghiêm trọng | Kiểm tra release date trên HuggingFace |
| Private Phase: nộp bài không đúng lúc | Thấp | Chốt chiến lược từ sớm, không nộp vội |

---

## Stack Công Nghệ Đề Xuất

| Thành phần | Công cụ |
|---|---|
| Thu thập văn bản | `requests` + `BeautifulSoup` |
| Xử lý tiếng Việt | `underthesea` |
| Embedding | `sentence-transformers` |
| Vector store | `Qdrant` (Docker) |
| Sparse retrieval | `rank_bm25` |
| Reranking | `sentence-transformers` CrossEncoder |
| LLM inference | `vllm` hoặc `transformers` + pipeline |
| Orchestration | Python thuần hoặc `LangChain` |
| Tracking experiment | JSON log đơn giản |
| Validation output | Script Python tự viết |
