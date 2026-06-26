"""知识库核心数据模型"""
from enum import Enum


class AuditStatus(str, Enum):
    """审核状态"""
    DRAFT = "草稿"
    PENDING = "待审核"
    REVIEWING = "审核中"
    PUBLISHED = "已发布"
    REJECTED = "已驳回"
    OFFLINE = "已下架"


class PublicLevel(str, Enum):
    """公开级别"""
    PUBLIC = "公开"
    INTERNAL = "内部"
    CONFIDENTIAL = "机密"
    TOP_SECRET = "绝密"


class KnowledgeSource(str, Enum):
    """知识来源"""
    WORD = "word"
    PDF = "pdf"
    EXCEL = "excel"
    MARKDOWN = "markdown"
    TEXT = "text"
    MANUAL = "manual"
"""知识库核心数据模型

核心枚举和通用数据结构。
注意：实体类型定义请参考 config/entity_schema.py
"""
from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditStatus(str, Enum):
    """审核状态"""
    DRAFT = "草稿"
    PENDING = "待审核"
    REVIEWING = "审核中"
    PUBLISHED = "已发布"
    REJECTED = "已驳回"
    OFFLINE = "已下架"


class PublicLevel(str, Enum):
    """公开级别"""
    PUBLIC = "公开"
    INTERNAL = "内部"
    CONFIDENTIAL = "机密"
    TOP_SECRET = "绝密"


class KnowledgeSource(str, Enum):
    """知识来源"""
    WORD = "word"
    PDF = "pdf"
    EXCEL = "excel"
    MARKDOWN = "markdown"
    TEXT = "text"
    MANUAL = "manual"


# ============ 基础数据结构 ============

class OriginalFile(BaseModel):
    """原始文件信息"""
    file_id: str = Field(..., description="文件ID")
    file_name: str = Field(..., description="原始文件名")
    file_path: str = Field(..., description="存储路径")
    file_type: str = Field(..., description="文件类型: word/excel/pdf/markdown/image/text")
    file_size: int = Field(0, description="文件大小(字节)")
    content_hash: str | None = Field(None, description="文件内容哈希")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow, description="上传时间")


class Citation(BaseModel):
    """引用溯源"""
    knowledge_id: str = Field(..., description="知识ID")
    entity_type: str = Field(..., description="实体类型")
    entity_id: str = Field(..., description="实体ID")
    block_id: str = Field(..., description="来源块ID")
    document_id: str = Field(..., description="源文档ID")
    document_name: str = Field(..., description="源文档名称")
    page_range: str | None = Field(None, description="页码范围")
    chunk_index: int = Field(..., description="块索引")
    confidence: float = Field(1.0, description="置信度")
    excerpt: str = Field(..., description="引用原文摘录")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: str | None = Field(None, description="审核人")
    status: str = Field("published", description="状态")


class RetrievalResult(BaseModel):
    """检索结果"""
    score: float = Field(..., description="综合得分")
    vector_score: float | None = Field(None, description="向量相似度")
    bm25_score: float | None = Field(None, description="BM25得分")
    graph_score: float | None = Field(None, description="图谱得分")
    rerank_score: float | None = Field(None, description="重排得分")
    # 原始数据
    id: str = Field(..., description="知识ID")
    entity_type: str = Field(..., description="实体类型")
    entity_name: str = Field(..., description="实体名称")
    title: str = Field(..., description="标题")
    content: str = Field(..., description="内容")
    tags: list[str] = Field(default_factory=list, description="标签")


class SearchQuery(BaseModel):
    """检索查询"""
    query: str = Field(..., description="查询文本")
    entity_types: list[str] | None = Field(None, description="限定实体类型")
    tags: list[str] | None = Field(None, description="标签过滤")
    public_level: PublicLevel | None = Field(None, description="公开级别过滤")
    top_k: int = Field(10, description="返回数量")
    use_graph: bool = Field(True, description="是否使用图谱增强")
    use_rerank: bool = Field(True, description="是否使用重排")
