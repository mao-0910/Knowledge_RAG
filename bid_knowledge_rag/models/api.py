"""API 请求/响应模型"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .knowledge import (
    AuditStatus,
    PublicLevel,
)


class KnowledgeCreateRequest(BaseModel):
    """知识创建请求"""
    entity_type: str = Field(..., description="实体类型")
    title: str = Field(..., description="知识标题")
    content: str = Field(..., description="知识内容")
    summary: str | None = Field(None, description="内容摘要")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    public_level: PublicLevel = Field(PublicLevel.INTERNAL, description="公开级别")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class KnowledgeUpdateRequest(BaseModel):
    """知识更新请求"""
    title: str | None = Field(None, description="知识标题")
    content: str | None = Field(None, description="知识内容")
    summary: str | None = Field(None, description="内容摘要")
    tags: list[str] | None = Field(None, description="标签列表")
    public_level: PublicLevel | None = Field(None, description="公开级别")
    metadata: dict[str, Any] | None = Field(None, description="额外元数据")


class KnowledgeResponse(BaseModel):
    """知识详情响应"""
    id: str
    entity_id: str
    entity_type: str
    entity_name: str
    title: str
    content: str
    summary: str | None
    tags: list[str]
    audit_status: AuditStatus
    public_level: PublicLevel
    confidence: float
    usage_count: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class KnowledgeListRequest(BaseModel):
    """知识列表请求"""
    entity_types: list[str] | None = Field(None, description="实体类型过滤")
    tags: list[str] | None = Field(None, description="标签过滤")
    audit_status: AuditStatus | None = Field(None, description="审核状态过滤")
    public_level: PublicLevel | None = Field(None, description="公开级别过滤")
    keyword: str | None = Field(None, description="关键词搜索")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


class KnowledgeListResponse(BaseModel):
    """知识列表响应"""
    items: list[KnowledgeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SearchRequest(BaseModel):
    """检索请求"""
    query: str = Field(..., description="查询文本")
    entity_types: list[str] | None = Field(None, description="限定实体类型")
    tags: list[str] | None = Field(None, description="标签过滤")
    keyword: str | None = Field(None, description="关键词搜索")
    top_k: int = Field(10, ge=1, le=100, description="返回数量")


class SearchResultItem(BaseModel):
    """检索结果项"""
    id: str
    entity_type: str
    entity_name: str
    title: str
    content: str
    summary: str | None
    tags: list[str]
    score: float
    vector_score: float | None = None
    bm25_score: float | None = None


class SearchResponse(BaseModel):
    """检索响应"""
    query: str
    results: list[SearchResultItem]
    total: int
    search_time: float  # 毫秒
