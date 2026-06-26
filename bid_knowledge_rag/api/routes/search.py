"""检索服务 API 路由"""
import logging
import time

from fastapi import APIRouter, HTTPException

from models import SearchRequest, SearchResponse, SearchResultItem
from storage import get_es_store
from services import get_embedding_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=SearchResponse)
async def search_knowledge(request: SearchRequest):
    """检索接口（向量检索 + 关键词检索）"""
    try:
        start_time = time.time()
        es_store = get_es_store()
        results = []

        # 1. 向量检索
        try:
            embedding_service = get_embedding_service()
            query_vector = embedding_service.encode([request.query])[0]

            vector_results = await es_store.vector_search(
                query_vector=query_vector,
                top_k=request.top_k,
                entity_types=request.entity_types,
                tags=request.tags,
            )

            for r in vector_results:
                results.append(SearchResultItem(
                    id=r.get("id"),
                    entity_type=r.get("entity_type"),
                    entity_name=r.get("entity_name", ""),
                    title=r.get("title"),
                    content=r.get("content", ""),
                    summary=r.get("summary"),
                    tags=r.get("tags", []),
                    score=r.get("score", 0),
                    vector_score=r.get("score", 0),
                    bm25_score=None,
                ))
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")

        # 2. 关键词检索
        keyword = request.keyword or request.query
        text_results = await es_store.fulltext_search(
            query=keyword,
            entity_types=request.entity_types,
            tags=request.tags,
            top_k=request.top_k,
        )

        # 避免重复
        existing_ids = {res.id for res in results}
        for r in text_results:
            if r.get("id") not in existing_ids:
                results.append(SearchResultItem(
                    id=r.get("id"),
                    entity_type=r.get("entity_type"),
                    entity_name=r.get("entity_name", ""),
                    title=r.get("title"),
                    content=r.get("content", ""),
                    summary=r.get("summary"),
                    tags=r.get("tags", []),
                    score=r.get("score", 0),
                    vector_score=None,
                    bm25_score=r.get("score", 0),
                ))

        return SearchResponse(
            query=request.query,
            results=results,
            total=len(results),
            search_time=(time.time() - start_time) * 1000,
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
