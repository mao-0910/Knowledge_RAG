"""知识管理 API 路由"""
import logging
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from models import (
    AuditStatus,
    KnowledgeCreateRequest,
    KnowledgeResponse,
    KnowledgeUpdateRequest,
    KnowledgeListRequest,
    KnowledgeListResponse,
    PublicLevel,
)
from storage import get_es_store
from services import get_embedding_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=KnowledgeResponse)
async def create_knowledge(request: KnowledgeCreateRequest):
    """创建知识条目"""
    try:
        es_store = get_es_store()
        item_id = str(uuid4())
        entity_id = str(uuid4())
        now = datetime.utcnow()

        # 生成向量
        vector = []
        if request.content:
            try:
                embedding_service = get_embedding_service()
                vector = embedding_service.encode([request.content])[0]
            except Exception as e:
                logger.warning(f"Embedding failed: {e}")

        item = {
            "id": item_id,
            "entity_id": entity_id,
            "entity_type": request.entity_type,
            "entity_name": request.title,
            "title": request.title,
            "content": request.content,
            "summary": request.summary,
            "tags": request.tags or [],
            "vector": vector,
            "audit_status": AuditStatus.DRAFT.value,
            "public_level": request.public_level.value if request.public_level else "内部",
            "confidence": 1.0,
            "usage_count": 0,
            "metadata": request.metadata or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        await es_store.create_knowledge_item(item)

        return _to_response(item)
    except Exception as e:
        logger.error(f"Create failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{knowledge_id}", response_model=KnowledgeResponse)
async def get_knowledge(knowledge_id: str):
    """获取知识详情"""
    try:
        es_store = get_es_store()
        item = await es_store.get_knowledge_item(knowledge_id)
        if not item:
            raise HTTPException(status_code=404, detail="Not found")
        return _to_response(item)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{knowledge_id}", response_model=KnowledgeResponse)
async def update_knowledge(knowledge_id: str, request: KnowledgeUpdateRequest):
    """更新知识条目"""
    try:
        es_store = get_es_store()
        item = await es_store.get_knowledge_item(knowledge_id)
        if not item:
            raise HTTPException(status_code=404, detail="Not found")

        updates = {}
        if request.title is not None:
            updates["title"] = request.title
            updates["entity_name"] = request.title
        if request.content is not None:
            updates["content"] = request.content
            try:
                embedding_service = get_embedding_service()
                updates["vector"] = embedding_service.encode([request.content])[0]
            except Exception:
                pass
        if request.summary is not None:
            updates["summary"] = request.summary
        if request.tags is not None:
            updates["tags"] = request.tags
        if request.public_level is not None:
            updates["public_level"] = request.public_level.value

        await es_store.update_knowledge_item(knowledge_id, updates)
        updated = await es_store.get_knowledge_item(knowledge_id)
        return _to_response(updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{knowledge_id}")
async def delete_knowledge(knowledge_id: str):
    """删除知识条目"""
    try:
        es_store = get_es_store()
        item = await es_store.get_knowledge_item(knowledge_id)
        if not item:
            raise HTTPException(status_code=404, detail="Not found")
        await es_store.delete_knowledge_item(knowledge_id)
        return {"success": True, "message": "Deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/list", response_model=KnowledgeListResponse)
async def list_knowledge(request: KnowledgeListRequest):
    """知识列表"""
    try:
        es_store = get_es_store()

        items, total = await es_store.list_knowledge_items(
            entity_types=request.entity_types,
            tags=request.tags,
            audit_status=request.audit_status.value if request.audit_status else None,
            keyword=request.keyword,
            page=request.page,
            page_size=request.page_size,
        )

        responses = [_to_response(item) for item in items]
        total_pages = (total + request.page_size - 1) // request.page_size

        return KnowledgeListResponse(
            items=responses,
            total=total,
            page=request.page,
            page_size=request.page_size,
            total_pages=total_pages,
        )
    except Exception as e:
        logger.error(f"List failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{knowledge_id}/submit")
async def submit_audit(knowledge_id: str):
    """提交审核"""
    try:
        es_store = get_es_store()
        item = await es_store.get_knowledge_item(knowledge_id)
        if not item:
            raise HTTPException(status_code=404, detail="Not found")
        await es_store.update_knowledge_item(knowledge_id, {"audit_status": AuditStatus.PENDING.value})
        return {"success": True, "message": "Submitted for audit"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Submit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{knowledge_id}/audit")
async def audit_knowledge(knowledge_id: str, action: str):
    """审核操作 (approve/reject)"""
    try:
        es_store = get_es_store()
        item = await es_store.get_knowledge_item(knowledge_id)
        if not item:
            raise HTTPException(status_code=404, detail="Not found")

        status = AuditStatus.APPROVED.value if action == "approve" else AuditStatus.REJECTED.value
        await es_store.update_knowledge_item(knowledge_id, {"audit_status": status})

        return {"success": True, "status": status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Audit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _to_response(item: dict) -> KnowledgeResponse:
    """转换为响应模型"""

    def parse_datetime(value):
        if value is None:
            return datetime.utcnow()
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except:
            return datetime.utcnow()

    return KnowledgeResponse(
        id=item.get("id", ""),
        entity_id=item.get("entity_id", ""),
        entity_type=item.get("entity_type", ""),
        entity_name=item.get("entity_name", ""),
        title=item.get("title", ""),
        content=item.get("content", ""),
        summary=item.get("summary"),
        tags=item.get("tags", []),
        audit_status=AuditStatus(item.get("audit_status", "草稿")),
        public_level=PublicLevel(item.get("public_level", "内部")),
        confidence=item.get("confidence", 1.0),
        usage_count=item.get("usage_count", 0),
        created_at=parse_datetime(item.get("created_at")),
        updated_at=parse_datetime(item.get("updated_at")),
        published_at=parse_datetime(item.get("published_at")) if item.get("published_at") else None,
    )
