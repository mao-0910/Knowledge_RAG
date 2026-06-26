"""Elasticsearch 存储

向量检索、元数据存储
"""
import logging
from datetime import datetime
from typing import Any

from elasticsearch import AsyncElasticsearch

from config import ElasticsearchConfig

logger = logging.getLogger(__name__)


class ElasticsearchStore:
    """Elasticsearch 存储服务"""

    def __init__(self, config: ElasticsearchConfig):
        self.config = config
        self.client: AsyncElasticsearch | None = None
        self.items_index = f"{config.index_prefix}_items"

    async def connect(self) -> None:
        """建立连接"""
        self.client = AsyncElasticsearch(
            hosts=[{"host": self.config.host, "port": self.config.port, "scheme": "http"}],
            request_timeout=30,
        )
        info = await self.client.info()
        logger.info(f"Connected to Elasticsearch {info['version']['number']}")

    async def close(self) -> None:
        """关闭连接"""
        if self.client:
            await self.client.close()
            logger.info("Elasticsearch connection closed")

    async def initialize_indices(self) -> None:
        """初始化索引"""
        if not self.client:
            raise RuntimeError("Client not connected")

        items_mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "entity_id": {"type": "keyword"},
                    "entity_type": {"type": "keyword"},
                    "entity_name": {"type": "text"},
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "summary": {"type": "text"},
                    "tags": {"type": "keyword"},
                    "vector": {
                        "type": "dense_vector",
                        "dims": self.config.dimension,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "audit_status": {"type": "keyword"},
                    "public_level": {"type": "keyword"},
                    "confidence": {"type": "float"},
                    "usage_count": {"type": "integer"},
                    "metadata": {"type": "object", "enabled": False},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "published_at": {"type": "date"},
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
        }

        if not await self.client.indices.exists(index=self.items_index):
            await self.client.indices.create(index=self.items_index, body=items_mapping)
            logger.info(f"Created index: {self.items_index}")
        else:
            logger.info(f"Index already exists: {self.items_index}")

    async def vector_search(
        self,
        query_vector: list[float],
        top_k: int = 100,
        entity_types: list[str] | None = None,
        tags: list[str] | None = None,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        """向量相似度搜索"""
        if not self.client:
            raise RuntimeError("Client not connected")

        filter_clauses = []
        if entity_types:
            filter_clauses.append({"terms": {"entity_type": entity_types}})
        if tags:
            filter_clauses.append({"terms": {"tags": tags}})

        query = {
            "knn": {
                "field": "vector",
                "query_vector": query_vector,
                "k": top_k,
                "num_candidates": top_k * 2,
            },
        }

        if filter_clauses:
            query = {"bool": {"must": [query], "filter": filter_clauses}}

        result = await self.client.search(
            index=self.items_index,
            body={
                "query": query,
                "_source": ["id", "entity_id", "entity_type", "title", "content", "summary", "tags"],
                "min_score": score_threshold,
            },
        )

        return [
            {
                "id": hit["_source"]["id"],
                "entity_id": hit["_source"].get("entity_id", ""),
                "entity_type": hit["_source"].get("entity_type", ""),
                "title": hit["_source"].get("title", ""),
                "content": hit["_source"].get("content", ""),
                "summary": hit["_source"].get("summary", ""),
                "tags": hit["_source"].get("tags", []),
                "score": hit["_score"] or 0,
            }
            for hit in result.get("hits", {}).get("hits", [])
        ]

    async def fulltext_search(
        self,
        query: str,
        entity_types: list[str] | None = None,
        tags: list[str] | None = None,
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """全文搜索"""
        if not self.client:
            raise RuntimeError("Client not connected")

        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["title^2", "content", "summary", "tags^1.5"],
                    "type": "best_fields",
                }
            }
        ]

        filter_clauses = []
        if entity_types:
            filter_clauses.append({"terms": {"entity_type": entity_types}})
        if tags:
            for tag in tags:
                filter_clauses.append({"term": {"tags": tag}})

        query_body = {"bool": {"must": must_clauses}}
        if filter_clauses:
            query_body["bool"]["filter"] = filter_clauses

        result = await self.client.search(
            index=self.items_index,
            body={
                "query": query_body,
                "size": top_k,
                "_source": ["id", "entity_id", "entity_type", "title", "content", "summary", "tags"],
            },
        )

        return [
            {
                "id": hit["_source"]["id"],
                "entity_id": hit["_source"].get("entity_id", ""),
                "entity_type": hit["_source"].get("entity_type", ""),
                "title": hit["_source"].get("title", ""),
                "content": hit["_source"].get("content", ""),
                "summary": hit["_source"].get("summary", ""),
                "tags": hit["_source"].get("tags", []),
                "score": hit["_score"] or 0,
            }
            for hit in result.get("hits", {}).get("hits", [])
        ]

    async def create_knowledge_item(self, item: dict[str, Any]) -> bool:
        """创建知识条目"""
        if not self.client:
            raise RuntimeError("Client not connected")

        doc = {
            "id": item.get("id"),
            "entity_id": item.get("entity_id"),
            "entity_type": item.get("entity_type"),
            "entity_name": item.get("entity_name"),
            "title": item.get("title"),
            "content": item.get("content"),
            "summary": item.get("summary"),
            "tags": item.get("tags", []),
            "audit_status": item.get("audit_status", "草稿"),
            "public_level": item.get("public_level", "内部"),
            "confidence": item.get("confidence", 1.0),
            "usage_count": item.get("usage_count", 0),
            "metadata": item.get("metadata", {}),
            "created_at": item.get("created_at", datetime.utcnow().isoformat()),
            "updated_at": item.get("updated_at", datetime.utcnow().isoformat()),
            "published_at": item.get("published_at"),
        }

        vector = item.get("vector")
        if vector and len(vector) > 0:
            doc["vector"] = vector

        await self.client.index(index=self.items_index, id=item["id"], document=doc)
        logger.info(f"Created knowledge item: {item['id']}")
        return True

    async def get_knowledge_item(self, item_id: str) -> dict[str, Any] | None:
        """获取知识条目"""
        if not self.client:
            raise RuntimeError("Client not connected")

        try:
            result = await self.client.get(index=self.items_index, id=item_id)
            return result["_source"]
        except Exception:
            return None

    async def update_knowledge_item(self, item_id: str, updates: dict[str, Any]) -> bool:
        """更新知识条目"""
        if not self.client:
            raise RuntimeError("Client not connected")

        updates["updated_at"] = datetime.utcnow().isoformat()
        await self.client.update(index=self.items_index, id=item_id, doc=updates)
        logger.info(f"Updated knowledge item: {item_id}")
        return True

    async def delete_knowledge_item(self, item_id: str) -> bool:
        """删除知识条目"""
        if not self.client:
            raise RuntimeError("Client not connected")

        try:
            await self.client.delete(index=self.items_index, id=item_id)
            logger.info(f"Deleted knowledge item: {item_id}")
            return True
        except Exception as e:
            logger.error(f"Delete knowledge item failed: {e}")
            return False

    async def list_knowledge_items(
        self,
        entity_types: list[str] | None = None,
        tags: list[str] | None = None,
        audit_status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """列表查询知识条目"""
        if not self.client:
            raise RuntimeError("Client not connected")

        must_clauses = []
        filter_clauses = []

        if entity_types:
            filter_clauses.append({"terms": {"entity_type": entity_types}})
        if tags:
            for tag in tags:
                filter_clauses.append({"term": {"tags": tag}})
        if audit_status:
            filter_clauses.append({"term": {"audit_status": audit_status}})
        if keyword:
            must_clauses.append({
                "multi_match": {
                    "query": keyword,
                    "fields": ["title^2", "content", "summary"],
                }
            })

        query = {"bool": {}}
        if must_clauses:
            query["bool"]["must"] = must_clauses
        if filter_clauses:
            query["bool"]["filter"] = filter_clauses

        if not query["bool"]:
            query = {"match_all": {}}

        from_offset = (page - 1) * page_size

        result = await self.client.search(
            index=self.items_index,
            body={
                "query": query,
                "from": from_offset,
                "size": page_size,
                "sort": [{"updated_at": {"order": "desc"}}],
            },
        )

        total = result["hits"]["total"]["value"]
        items = [hit["_source"] for hit in result["hits"]["hits"]]

        return items, total


# 全局单例
_es_store: ElasticsearchStore | None = None


def get_es_store() -> ElasticsearchStore:
    """获取 ES 存储实例"""
    global _es_store
    if _es_store is None:
        from config import get_settings
        settings = get_settings()
        _es_store = ElasticsearchStore(settings.elasticsearch)
    return _es_store
