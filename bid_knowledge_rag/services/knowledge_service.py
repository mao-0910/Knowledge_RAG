"""知识库服务

提供知识条目的创建等公共功能
"""
import logging
from uuid import uuid4

from models import AuditStatus
from storage import get_es_store
from services import get_embedding_service

logger = logging.getLogger(__name__)


def generate_embedding(text: str) -> list:
    """
    生成文本向量

    Args:
        text: 文本内容

    Returns:
        向量列表
    """
    try:
        embedding_service = get_embedding_service()
        return embedding_service.encode([text])[0]
    except Exception as e:
        logger.warning(f"Embedding failed: {e}")
        return []


async def create_knowledge_item(
    entity_type: str,
    content: str,
    title: str,
    tags: list | None = None,
    metadata: dict | None = None,
    public_level: str = "内部",
) -> dict:
    """
    创建知识条目

    Args:
        entity_type: 实体类型
        content: 知识内容
        title: 知识标题
        tags: 标签列表
        metadata: 元数据
        public_level: 公开级别

    Returns:
        创建的知识条目信息
    """
    # 生成向量
    vector = generate_embedding(content)

    # 处理标签
    tag_list = tags or []

    from datetime import datetime

    # 创建知识条目
    es_store = get_es_store()
    item_id = str(uuid4())
    entity_id = str(uuid4())
    now = datetime.utcnow()

    item = {
        "id": item_id,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "entity_name": title,
        "title": title,
        "content": content,
        "summary": None,
        "tags": tag_list,
        "vector": vector,
        "audit_status": AuditStatus.DRAFT.value,
        "public_level": public_level,
        "confidence": 1.0,
        "usage_count": 0,
        "metadata": metadata or {},
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    await es_store.create_knowledge_item(item)

    return {
        "id": item_id,
        "entity_type": entity_type,
        "title": title,
        "tags": tag_list,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
