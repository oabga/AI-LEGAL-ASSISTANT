/** Kiểu dữ liệu khớp với schema Pydantic của backend. */

export type UserRole = "owner" | "accountant" | "hr" | "admin";

export type Organization = {
  id: string;
  name: string;
  tax_code?: string | null;
  business_type?: string | null;
  employee_count?: number | null;
  annual_revenue_bn?: number | null;
  address?: string | null;
  vat_period?: string | null;
};

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  organization?: Organization | null;
  created_at: string;
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type AuthResponse = { user: User; tokens: TokenPair };

export type RuntimeConfig = {
  chat_streaming: boolean;
  token_streaming: boolean;
  competition_enabled: boolean;
};

/* ---------------------------------------------------------------- chat --- */

export type LegalArticle = {
  id: string;
  article_id: string;
  law_id: string;
  law_name: string;
  doc_type: string;
  chapter?: string | null;
  article: string;
  article_title?: string | null;
  content: string;
  author?: string | null;
  extra?: string[];
  score?: number | null;
};

export type LegalAnswerResponse = {
  id?: number | null;
  session_id?: string | null;
  question: string;
  answer: string;
  relevant_docs: string[];
  relevant_articles: string[];
  selected_articles: LegalArticle[];
  debug: Record<string, unknown>;
};

export type ChatResponse = {
  session_id?: string | null;
  conversation_id?: string | null;
  conversation_title?: string | null;
  message: string;
  answer: LegalAnswerResponse;
  tool_calls: Record<string, unknown>[];
};

export type ProgressStatus = "started" | "running" | "completed" | "warning" | "error";

export type ChatStreamProgress = {
  message: string;
  stage: string;
  status: ProgressStatus;
  elapsed_ms?: number | null;
  detail?: string | null;
  metadata?: Record<string, unknown>;
};

export type ChatStreamEvent =
  | { event: "status"; data: ChatStreamProgress }
  | { event: "token"; data: { token: string; stage?: string } }
  | { event: "result"; data: ChatResponse }
  | { event: "done"; data: ChatStreamProgress }
  | { event: "error"; data: ChatStreamProgress };

export type RetrievalTraceResult = {
  rank?: number;
  score?: number;
  source?: string;
  law_id?: string;
  law_name?: string;
  article?: string;
  article_title?: string;
  passed_threshold?: boolean;
};

export type AgentTraceStep = {
  stage: string;
  status: ProgressStatus;
  title: string;
  detail: string;
  elapsedMs?: number | null;
  topResults?: RetrievalTraceResult[];
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: string[];
  relevantDocs: string[];
  trace: AgentTraceStep[];
  pending?: boolean;
  error?: string | null;
};

export type Conversation = {
  id: string;
  title: string;
  archived: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type ApiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: string[];
  relevant_docs: string[];
  trace: Record<string, unknown>;
  created_at: string;
};

/* ---------------------------------------------------------------- laws --- */

export type Law = {
  law_id: string;
  law_name: string;
  doc_type: string;
  issuer?: string | null;
  category: string;
  effective_date?: string | null;
  status: string;
  article_count: number;
};

export type LawListResponse = {
  items: Law[];
  total: number;
  categories: string[];
  doc_types: string[];
};

export type ArticleSummary = { id: number; article: string; article_title: string };

export type ChapterNode = { chapter: string | null; articles: ArticleSummary[] };

export type LawTreeResponse = { law: Law; chapters: ChapterNode[] };

export type ArticleRef = {
  law_id: string;
  law_name: string;
  article: string;
  article_title: string;
};

export type ArticleDetail = {
  id: number;
  law_id: string;
  law_name: string;
  doc_type: string;
  chapter?: string | null;
  article: string;
  article_title: string;
  content: string;
  author: string;
  related: ArticleRef[];
  previous_article?: string | null;
  next_article?: string | null;
};

export type SearchHit = {
  id: number;
  law_id: string;
  law_name: string;
  doc_type: string;
  chapter?: string | null;
  article: string;
  article_title: string;
  content: string;
  score: number;
};

export type SearchResponse = {
  items: SearchHit[];
  total: number;
  query: string;
  strategy: "article_number" | "full_text" | "trigram" | "empty";
  terms: string[];
};

/* ----------------------------------------------------------- contracts --- */

export type DocumentStatus = "pending" | "ready" | "processing" | "done" | "failed";
export type ReviewStatus = "pending" | "processing" | "done" | "failed";
export type RiskLevel = "cao" | "trung bình" | "thấp" | "thông tin";

export type ContractDocument = {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: DocumentStatus;
  error_message?: string | null;
  created_at: string;
  text_length: number;
  latest_review_id?: string | null;
};

export type Finding = {
  id: string;
  position: number;
  clause_title?: string | null;
  clause_text: string;
  risk_level: RiskLevel;
  issue: string;
  recommendation?: string | null;
  legal_refs: string[];
};

export type Review = {
  id: string;
  document_id: string;
  status: ReviewStatus;
  risk_score: number;
  clause_count: number;
  summary?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  filename?: string | null;
  findings: Finding[];
  risk_counts: Record<string, number>;
};

/* ---------------------------------------------------------- compliance --- */

export type ComplianceFrequency = "monthly" | "quarterly" | "annual" | "one_time";
export type ComplianceStatus = "pending" | "done" | "skipped";

export type ComplianceRule = {
  id: number;
  code: string;
  title: string;
  description?: string | null;
  frequency: ComplianceFrequency;
  category: string;
  legal_refs: string[];
  references?: ArticleRef[];
};

export type ComplianceTask = {
  id: string;
  period_label: string;
  due_date: string;
  status: ComplianceStatus;
  completed_at?: string | null;
  notes?: string | null;
  rule: ComplianceRule;
  days_remaining: number;
  overdue: boolean;
};

export type ComplianceSummary = {
  total: number;
  pending: number;
  done: number;
  skipped: number;
  overdue: number;
  due_soon: number;
  next_due?: ComplianceTask | null;
};

/* --------------------------------------------------------------- admin --- */

export type CorpusStats = {
  total_articles: number;
  total_laws: number;
  by_doc_type: Record<string, number>;
  by_category: Record<string, number>;
  largest_laws: {
    law_id: string;
    law_name: string;
    doc_type: string;
    category: string;
    article_count: number;
  }[];
  index_ready: boolean;
  indexed_vectors: number;
  embedding_model?: string | null;
};

export type AdminUser = {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  organization_id?: string | null;
  organization_name?: string | null;
  created_at: string;
};

export type Paginated<T> = { items: T[]; total: number };
