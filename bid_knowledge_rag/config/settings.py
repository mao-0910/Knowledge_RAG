"""配置加载模块"""
import os
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    """应用配置"""
    name: str = "投标知识库 RAG"
    version: str = "0.1.0"
    debug: bool = False


class ServerConfig(BaseSettings):
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    reload: bool = False


class ElasticsearchConfig(BaseSettings):
    """Elasticsearch 配置"""
    host: str = "localhost"
    port: int = 9200
    index_prefix: str = "bid_knowledge"
    dimension: int = 1024
    enabled: bool = True


class LLMConfig(BaseSettings):
    """LLM 服务配置"""
    api_base: str = "http://192.168.2.3:42121/v1"
    api_key: str = "dummy-key"
    model: str = "Qwen3.5-122B-A10B-GPTQ-Int4"
    timeout: int = 120
    max_retries: int = 3
    temperature: float = 0.1


class EmbeddingConfig(BaseSettings):
    """Embedding 服务配置"""
    model_name: str = "BAAI/bge-m3-multilingual"
    dimension: int = 1024
    device: str = "cpu"
    batch_size: int = 32
    max_length: int = 512
    normalize: bool = True
    hf_token: str = ""


class AuditConfig(BaseSettings):
    """审核配置"""
    auto_pass_threshold: float = 0.95
    duplicate_threshold: float = 0.85


class LoggingConfig(BaseSettings):
    """日志配置"""
    level: str = "INFO"
    format: str = "json"
    file: str = "./logs/app.log"
    max_bytes: int = 10485760
    backup_count: int = 5


class Settings(BaseSettings):
    """全局设置"""
    app: AppConfig = Field(default_factory=AppConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    elasticsearch: ElasticsearchConfig = Field(default_factory=ElasticsearchConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def load_from_yaml(cls, config_path: str | Path | None = None) -> "Settings":
        """从 YAML 文件加载配置"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"

        config_path = Path(config_path)
        if not config_path.exists():
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        return cls(
            app=AppConfig(**config_data.get("app", {})),
            server=ServerConfig(**config_data.get("server", {})),
            elasticsearch=ElasticsearchConfig(**config_data.get("elasticsearch", {})),
            llm=LLMConfig(**config_data.get("llm", {})),
            embedding=EmbeddingConfig(**config_data.get("embedding", {})),
            audit=AuditConfig(**config_data.get("audit", {})),
            logging=LoggingConfig(**config_data.get("logging", {})),
        )


# 全局配置实例
_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置实例"""
    global _settings
    if _settings is None:
        _settings = Settings.load_from_yaml()
    return _settings


def reload_settings(config_path: str | Path | None = None) -> Settings:
    """重新加载配置"""
    global _settings
    _settings = Settings.load_from_yaml(config_path)
    return _settings
"""配置加载模块"""
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    """应用配置"""
    name: str = "投标知识库 RAG"
    version: str = "0.1.0"
    debug: bool = False


class ServerConfig(BaseSettings):
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    reload: bool = False


class ElasticsearchConfig(BaseSettings):
    """Elasticsearch 配置"""
    host: str = "localhost"
    port: int = 9200
    index_prefix: str = "bid_knowledge"
    dimension: int = 1024
    enabled: bool = True


class LLMConfig(BaseSettings):
    """LLM 服务配置"""
    api_base: str = "http://192.168.2.3:42121/v1"
    api_key: str = "dummy-key"
    model: str = "Qwen3.5-122B-A10B-GPTQ-Int4"
    timeout: int = 120
    max_retries: int = 3
    temperature: float = 0.1


class EmbeddingConfig(BaseSettings):
    """Embedding 服务配置"""
    model_name: str = "BAAI/bge-m3-multilingual"
    dimension: int = 1024
    device: str = "cpu"
    batch_size: int = 32
    max_length: int = 512
    normalize: bool = True
    hf_token: str = ""


class RerankConfig(BaseSettings):
    """Rerank 服务配置"""
    model_name: str = "BAAI/bge-reranker-base"
    device: str = "cpu"
    top_k: int = 20
    max_length: int = 512


class DocumentConfig(BaseSettings):
    """文档处理配置"""
    max_file_size: int = 50  # MB
    supported_formats: list[str] = [".docx", ".doc", ".pdf", ".xlsx", ".xls", ".md", ".txt", ".jpg", ".png"]
    temp_dir: str = "./temp"
    output_dir: str = "./output"


class StorageConfig(BaseSettings):
    """文件存储配置"""
    path: str = "./storage/uploads"
    max_size_mb: int = 50
    enable_original_preserve: bool = True


class ChunkingConfig(BaseSettings):
    """分块配置"""
    chunk_size: int = 512
    chunk_overlap: int = 128
    min_chunk_size: int = 50
    semantic_window: int = 3
    table_as_block: bool = True


class RetrievalConfig(BaseSettings):
    """检索配置"""
    vector_top_k: int = 100
    bm25_top_k: int = 100
    rrf_top_k: int = 50
    final_top_k: int = 10
    score_threshold: float = 0.5
    rrf_k: int = 60


class GraphConfig(BaseSettings):
    """图谱增强配置"""
    enabled: bool = True
    depth: int = 2
    expand_factor: int = 3
    relation_weights: dict[str, float] = Field(default_factory=lambda: {
        "拥有": 1.0,
        "参与": 0.9,
        "包含": 0.8,
        "支撑": 0.8,
        "基于": 0.7,
        "参考": 0.6,
        "需要": 0.9,
        "服务于": 0.7,
        "配备": 0.8,
        "被用于": 0.7,
        "提供": 0.8,
        "关联": 0.5,
    })


class AuditConfig(BaseSettings):
    """审核配置"""
    auto_pass_threshold: float = 0.95
    duplicate_threshold: float = 0.85
    require_manual_review: list[str] = Field(default_factory=lambda: [
        "涉及合同金额",
        "涉及人员信息",
        "涉及资质证书",
    ])


class LoggingConfig(BaseSettings):
    """日志配置"""
    level: str = "INFO"
    format: str = "json"
    file: str = "./logs/app.log"
    max_bytes: int = 10485760
    backup_count: int = 5


class Settings(BaseSettings):
    """全局设置"""
    app: AppConfig = Field(default_factory=AppConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    elasticsearch: ElasticsearchConfig = Field(default_factory=ElasticsearchConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    document: DocumentConfig = Field(default_factory=DocumentConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def load_from_yaml(cls, config_path: str | Path | None = None) -> "Settings":
        """从 YAML 文件加载配置"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"

        config_path = Path(config_path)
        if not config_path.exists():
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        return cls(
            app=AppConfig(**config_data.get("app", {})),
            server=ServerConfig(**config_data.get("server", {})),
            elasticsearch=ElasticsearchConfig(**config_data.get("elasticsearch", {})),
            llm=LLMConfig(**config_data.get("llm", {})),
            embedding=EmbeddingConfig(**config_data.get("embedding", {})),
            rerank=RerankConfig(**config_data.get("rerank", {})),
            document=DocumentConfig(**config_data.get("document", {})),
            storage=StorageConfig(**config_data.get("storage", {})),
            chunking=ChunkingConfig(**config_data.get("chunking", {})),
            retrieval=RetrievalConfig(**config_data.get("retrieval", {})),
            graph=GraphConfig(**config_data.get("graph", {})),
            audit=AuditConfig(**config_data.get("audit", {})),
            logging=LoggingConfig(**config_data.get("logging", {})),
        )

    @property
    def storage_path(self) -> str:
        """获取文件存储路径"""
        return self.storage.path


# 全局配置实例
_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置实例"""
    global _settings
    if _settings is None:
        _settings = Settings.load_from_yaml()
    return _settings


def reload_settings(config_path: str | Path | None = None) -> Settings:
    """重新加载配置"""
    global _settings
    _settings = Settings.load_from_yaml(config_path)
    return _settings
