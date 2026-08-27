"""Cấu hình ứng dụng: ``config.yaml`` cho hành vi, biến môi trường cho secret.

Nguyên tắc:

- ``backend/config.yaml`` khai báo mọi thứ có thể commit (host/port, model name,
  tham số retrieval, ngưỡng rerank...).
- Secret và giá trị phụ thuộc môi trường triển khai (API key, database URL,
  JWT key, CORS origin) đọc từ biến môi trường / ``.env`` và **ghi đè** YAML.

Thứ tự ưu tiên: init kwargs > biến môi trường > ``.env`` > ``config.yaml`` >
default trong code.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Tuple, Type

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# PRJ_ROOT trỏ tới thư mục backend. Các path tương đối trong config.yaml sẽ được
# resolve dựa trên thư mục này để chạy từ đâu cũng ổn định.
PRJ_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PRJ_ROOT / "config.yaml"
ENV_FILE = PRJ_ROOT / ".env"

# Map biến môi trường -> đường dẫn field trong Settings.
# Chỉ khai báo ở đây những giá trị thực sự phụ thuộc môi trường, để tránh biến
# config thành hai nguồn sự thật song song.
ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    "APP_HOST": ("app", "host"),
    "APP_PORT": ("app", "port"),
    "LLM_API_KEY": ("llm", "api_key"),
    "LLM_BASE_URL": ("llm", "base_url"),
    "LLM_MODEL": ("llm", "default_model"),
    "EMBEDDINGS_API_KEY": ("embeddings", "api_key"),
    "EMBEDDINGS_BASE_URL": ("embeddings", "base_url"),
    "EMBEDDINGS_MODEL": ("embeddings", "model"),
    "RERANKER_API_KEY": ("legal_assistant", "reranker", "api_key"),
    "LEGAL_DATABASE_URL": ("legal_assistant", "postgres", "database_url"),
    "JWT_SECRET_KEY": ("auth", "secret_key"),
    "CORS_ALLOW_ORIGINS": ("cors", "allow_origins"),
}

# Các field nhận danh sách từ env dạng "a,b,c".
LIST_ENV_KEYS = {"CORS_ALLOW_ORIGINS"}


class ConfigModel(BaseModel):
    """BaseModel chung cho các block config con.

    ``extra='ignore'`` giúp config.yaml có thể chứa key mới trong tương lai mà
    code cũ không bị crash. ``populate_by_name=True`` cho phép dùng cả alias
    và tên field Python khi validate.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class AppSettings(ConfigModel):
    """Cấu hình host/port mặc định cho FastAPI agent service."""

    host: str = "0.0.0.0"
    port: int = 8000


class UISettings(ConfigModel):
    """Cấu hình frontend dev server (Vite) để dựng CORS origin mặc định."""

    host: str = "0.0.0.0"
    port: int = 5173


class CORSSettings(ConfigModel):
    """Danh sách origin được phép gọi API.

    Production phải khai báo domain thật qua ``CORS_ALLOW_ORIGINS``; mặc định
    chỉ mở cho Vite dev server ở localhost.
    """

    allow_origins: list[str] = Field(default_factory=list)
    allow_credentials: bool = True

    @field_validator("allow_origins", mode="before")
    @classmethod
    def split_csv(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


class AuthSettings(ConfigModel):
    """Cấu hình JWT và chính sách mật khẩu."""

    secret_key: str = "dev-only-insecure-secret-change-me"
    algorithm: str = "HS256"
    access_token_minutes: int = Field(default=15, ge=1)
    refresh_token_days: int = Field(default=7, ge=1)
    min_password_length: int = Field(default=8, ge=6)
    # Cho phép tài khoản đầu tiên tự trở thành admin khi DB còn trống.
    bootstrap_first_admin: bool = True

    @property
    def is_insecure_default(self) -> bool:
        return self.secret_key == "dev-only-insecure-secret-change-me"


class RateLimitSettings(ConfigModel):
    """Giới hạn tần suất cho endpoint tốn quota LLM."""

    enabled: bool = True
    chat_per_minute: int = Field(default=20, ge=1)
    upload_per_hour: int = Field(default=30, ge=1)


class UploadSettings(ConfigModel):
    """Cấu hình lưu file hợp đồng do người dùng tải lên."""

    directory: Path = Path("./uploads")
    max_size_mb: int = Field(default=10, ge=1)
    allowed_extensions: list[str] = Field(default_factory=lambda: [".pdf", ".docx", ".txt"])

    @model_validator(mode="after")
    def resolve_directory(self):
        if not self.directory.is_absolute():
            self.directory = PRJ_ROOT / self.directory
        return self

    @property
    def max_size_bytes(self) -> int:
        return self.max_size_mb * 1024 * 1024


class LLMSettings(ConfigModel):
    """Cấu hình chat model OpenAI-compatible.

    Mặc định trỏ tới lớp tương thích OpenAI của Gemini; đổi ``base_url`` là có
    thể chuyển sang vLLM local hoặc provider khác mà không sửa code.
    """

    api_key: str = ""
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # AliasChoices cho phép config.yaml dùng ``default_model`` hoặc
    # ``model_name`` mà code vẫn đọc về cùng một field.
    model_name: str = Field(
        "gemini-2.5-flash",
        validation_alias=AliasChoices("model_name", "default_model"),
    )
    temperature: float = 0.0
    max_tokens: int | None = None
    enable_thinking: bool = False
    timeout_seconds: float = Field(default=120.0, gt=0)
    max_retries: int = Field(default=4, ge=0)


class EmbeddingsSettings(ConfigModel):
    """Cấu hình embedding endpoint OpenAI-compatible.

    ``dimensions`` dùng Matryoshka truncation của gemini-embedding-001 để giảm
    kích thước index. Đổi giá trị này bắt buộc phải build lại Chroma vì số chiều
    vector của collection cũ không còn khớp.
    """

    api_key: str = ""
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    model: str = "gemini-embedding-001"
    dimensions: int | None = Field(default=1536, ge=64)
    max_input_tokens: int = Field(default=8190, ge=128)
    tokenizer_encoding: str = "cl100k_base"
    # Provider cloud có rate limit, nên index theo batch nhỏ kèm backoff.
    batch_size: int = Field(default=64, ge=1)
    max_retries: int = Field(default=6, ge=0)
    retry_base_delay: float = Field(default=2.0, gt=0)
    retry_max_delay: float = Field(default=60.0, gt=0)
    request_timeout: float = Field(default=120.0, gt=0)


class ShortMemorySettings(ConfigModel):
    """Cấu hình bộ nhớ hội thoại ngắn hạn.

    Khác với bản gốc dùng LangGraph InMemorySaver (mất khi restart), lịch sử
    được nạp lại từ PostgreSQL nên sống sót qua restart và chạy được nhiều
    worker.
    """

    enabled: bool = True
    max_turns: int = Field(default=6, ge=1)


class ChatSettings(ConfigModel):
    """Cấu hình cách endpoint chat trả kết quả cho UI/client."""

    streaming: bool = True
    token_streaming: bool = True


class CompetitionSettings(ConfigModel):
    """Bật mode chạy tập test: luôn coi query là câu hỏi luật."""

    enabled: bool = False
    max_concurrency: int = Field(default=4, ge=1)
    save_outputs: bool = True
    output_dir: Path = Path("./outputs")

    @model_validator(mode="after")
    def resolve_output_dir(self):
        """Chuẩn hóa thư mục lưu kết quả competition dưới backend."""

        if not self.output_dir.is_absolute():
            self.output_dir = PRJ_ROOT / self.output_dir
        return self


class RewriteSettings(ConfigModel):
    """Bật/tắt rewrite query và giới hạn số biến thể query retrieval."""

    enabled: bool = False
    max_variants: int = 3


class HyDESettings(ConfigModel):
    """Bật/tắt HyDE: sinh hypothetical answer để làm query dense retrieval."""

    enabled: bool = False


class RerankerSettings(ConfigModel):
    """Cấu hình reranker cross-encoder chạy sau retrieval."""

    enabled: bool = False
    api_key: str = ""
    base_url: str = "http://localhost:8025/v1"
    model: str = "qwen3-reranker-06b"
    filter_mode: Literal["fixed", "largest_gap"] = "fixed"
    threshold: float = 0.0
    min_gap: float = Field(default=0.0, ge=0)
    min_keep: int = Field(default=1, ge=1)
    timeout_seconds: float = Field(default=60.0, gt=0)
    endpoint: str = "/v1/rerank"


class LLMFilterSettings(ConfigModel):
    """Bật/tắt bước LLM đánh giá từng điều luật sau rerank."""

    enabled: bool = False
    max_concurrency: int = Field(default=4, ge=1)
    min_keep: int = Field(default=1, ge=0)


class ContractReviewSettings(ConfigModel):
    """Cấu hình module soát xét rủi ro hợp đồng."""

    enabled: bool = True
    max_clauses: int = Field(default=60, ge=1)
    max_concurrency: int = Field(default=3, ge=1)
    retrieval_top_k: int = Field(default=4, ge=1)


class PostgreSQLSettings(ConfigModel):
    """Nguồn dữ liệu luật dùng để dựng Chroma và nạp BM25 khi startup."""

    enabled: bool = True
    database_url: str = "postgresql://postgres:postgres@localhost:23432/legal_assistant"
    table_name: str = "legal_knowledge_records"
    batch_size: int = Field(default=128, ge=1)
    # Pool cho SQLAlchemy async engine của phần dữ liệu ứng dụng.
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    echo_sql: bool = False

    @field_validator("table_name")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        """Chỉ chấp nhận identifier SQL đơn giản từ file cấu hình."""

        parts = value.split(".")
        if not all(part and part.replace("_", "").isalnum() and not part[0].isdigit() for part in parts):
            raise ValueError(f"SQL identifier không hợp lệ: {value}")
        return value

    @property
    def async_database_url(self) -> str:
        """DSN cho SQLAlchemy async engine (driver asyncpg)."""

        url = self.database_url
        if url.startswith("postgresql+"):
            return url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    @property
    def sync_database_url(self) -> str:
        """DSN đồng bộ dùng cho Alembic."""

        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return url


class VectorStoreSettings(ConfigModel):
    """Cấu hình backend retrieval: lexical, Chroma vector hoặc hybrid."""

    mode: Literal["bm25", "chroma", "hybrid"] = "hybrid"
    persist_directory: Path = Path("./chroma_db")
    default_collection: str = "legal_articles"
    rrf_k: int = 60
    dense_weight: float = Field(default=2.0, gt=0)
    bm25_weight: float = Field(default=1.0, gt=0)
    top_k: int = 8
    bm25_tokenizer: Literal["auto", "underthesea", "regex"] = "auto"
    bm25_k1: float = 2.0
    bm25_b: float = 1.0
    bm25_epsilon: float = 0.5

    @model_validator(mode="after")
    def resolve_persist_directory(self):
        """Chuẩn hóa path Chroma sau khi Pydantic parse xong model.

        Người dùng có thể viết ``./chroma_db`` trong YAML. Validator này đổi nó
        thành absolute path dưới thư mục backend để fallback local luôn nhìn đúng
        vị trí vector index.
        """

        if not self.persist_directory.is_absolute():
            self.persist_directory = PRJ_ROOT / self.persist_directory
        return self


class CorpusSettings(ConfigModel):
    """Đường dẫn tới dữ liệu corpus nằm ngoài database."""

    # Manifest liệt kê văn bản kèm lĩnh vực (category), dùng để đồng bộ bảng
    # ``laws``. Corpus vẫn là nguồn sự thật cho nội dung Điều luật.
    manifest_path: Path = Path("../corpus/law_manifest.json")
    data_path: Path = Path("../data/base_data.json")

    @model_validator(mode="after")
    def resolve_paths(self):
        """Neo path tương đối vào thư mục backend, không phụ thuộc CWD.

        Corpus nằm ngoài ``backend/`` nên path mặc định bắt đầu bằng ``..``;
        resolve theo PRJ_ROOT để chạy từ repo root, từ ``backend/`` hay trong
        container đều trỏ cùng một chỗ.
        """

        if not self.manifest_path.is_absolute():
            self.manifest_path = (PRJ_ROOT / self.manifest_path).resolve()
        if not self.data_path.is_absolute():
            self.data_path = (PRJ_ROOT / self.data_path).resolve()
        return self


class LegalAssistantSettings(ConfigModel):
    """Nhóm cấu hình riêng cho agent pháp lý."""

    corpus: CorpusSettings = Field(default_factory=CorpusSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)
    competition: CompetitionSettings = Field(default_factory=CompetitionSettings)
    rewrite: RewriteSettings = Field(default_factory=RewriteSettings)
    hyde: HyDESettings = Field(default_factory=HyDESettings)
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    llm_filter: LLMFilterSettings = Field(default_factory=LLMFilterSettings)
    contract_review: ContractReviewSettings = Field(default_factory=ContractReviewSettings)
    postgres: PostgreSQLSettings = Field(default_factory=PostgreSQLSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse ``.env`` tối giản: ``KEY=value``, bỏ comment và nháy bao ngoài."""

    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


class EnvOverrideSource(PydanticBaseSettingsSource):
    """Đọc các biến môi trường phẳng trong ``ENV_OVERRIDES`` thành dict lồng.

    Dùng nguồn riêng thay vì ``env_nested_delimiter`` để tên biến ngắn, dễ đọc
    trong ``.env``/compose (``LLM_API_KEY`` thay vì ``LLM__API_KEY``) và để
    danh sách secret được khai báo tường minh tại một chỗ.

    Biến môi trường thật luôn thắng giá trị trong ``.env``, để compose/CI có thể
    ghi đè file cấu hình của máy dev.
    """

    def get_field_value(self, field, field_name):  # pragma: no cover - không dùng
        raise NotImplementedError

    def __call__(self) -> dict[str, Any]:
        merged = {**_read_env_file(ENV_FILE), **os.environ}
        result: dict[str, Any] = {}
        for env_key, path in ENV_OVERRIDES.items():
            raw = merged.get(env_key)
            if raw is None or raw == "":
                continue
            value: Any = raw
            if env_key in LIST_ENV_KEYS:
                value = [item.strip() for item in raw.split(",") if item.strip()]
            cursor = result
            for part in path[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[path[-1]] = value
        return result


class Settings(BaseSettings):
    """Root settings object được inject vào toàn bộ ứng dụng."""

    app: AppSettings = Field(default_factory=AppSettings)
    ui: UISettings = Field(default_factory=UISettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    uploads: UploadSettings = Field(default_factory=UploadSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    embeddings: EmbeddingsSettings = Field(default_factory=EmbeddingsSettings)
    short_memory: ShortMemorySettings = Field(default_factory=ShortMemorySettings)
    legal_assistant: LegalAssistantSettings = Field(
        default_factory=LegalAssistantSettings,
        validation_alias=AliasChoices("legal_assistant", "legal-assistant"),
    )

    model_config = SettingsConfigDict(
        yaml_file=CONFIG_FILE,
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def apply_defaults(self):
        """Suy ra CORS origin mặc định và dùng LLM key cho embeddings nếu thiếu."""

        if not self.cors.allow_origins:
            self.cors.allow_origins = [
                f"http://localhost:{self.ui.port}",
                f"http://127.0.0.1:{self.ui.port}",
            ]
        # Gemini dùng cùng một API key cho chat và embeddings.
        if not self.embeddings.api_key and self.llm.api_key:
            self.embeddings.api_key = self.llm.api_key
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """Quy định thứ tự đọc config: env/.env ghi đè config.yaml."""

        return (
            init_settings,
            EnvOverrideSource(settings_cls),
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Trả về settings đã cache để không parse YAML nhiều lần."""

    return Settings()


# Biến tiện ích cho các module đơn giản cần đọc config trực tiếp.
settings = get_settings()
