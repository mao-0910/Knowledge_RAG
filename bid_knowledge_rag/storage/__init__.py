"""存储层模块

基于 Elasticsearch 进行存储：
- 知识条目管理
- 向量检索
- 全文搜索
"""
from .es_store import ElasticsearchStore, get_es_store

__all__ = [
    "ElasticsearchStore",
    "get_es_store",
]
