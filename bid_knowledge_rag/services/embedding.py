"""Embedding 向量化服务"""
import logging
import os
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from config import EmbeddingConfig, get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """向量化服务"""
    
    def __init__(self, config: EmbeddingConfig | None = None):
        self.config = config or get_settings().embedding
        self.model: SentenceTransformer | None = None
        # 从配置文件获取 HuggingFace token
        self.hf_token = self.config.hf_token or os.environ.get("HF_TOKEN", "")
    
    def load_model(self) -> None:
        """加载模型"""
        if self.model is None:
            logger.info(f"Loading embedding model: {self.config.model_name}")
            self.model = SentenceTransformer(
                model_name_or_path=self.config.model_name,
                device=self.config.device,
                token=self.hf_token if self.hf_token else None,
            )
            logger.info(f"Embedding model loaded, dimension: {self.config.dimension}")
    
    def encode(
        self,
        texts: list[str],
        normalize: bool | None = None,
        batch_size: int | None = None,
    ) -> list[list[float]]:
        """
        将文本编码为向量
        
        Args:
            texts: 文本列表
            normalize: 是否归一化
            batch_size: 批次大小
            
        Returns:
            向量列表
        """
        if self.model is None:
            self.load_model()
        
        normalize = normalize if normalize is not None else self.config.normalize
        batch_size = batch_size or self.config.batch_size
        
        embeddings = self.model.encode(
            sentences=texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=len(texts) > 100,
        )
        
        return embeddings.tolist()
    
    def encode_query(self, query: str) -> list[float]:
        """编码查询文本"""
        vectors = self.encode([query])
        return vectors[0]
    
    def compute_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """计算两个文本的相似度"""
        embeddings = self.encode([text1, text2])
        vec1 = np.array(embeddings[0])
        vec2 = np.array(embeddings[1])
        
        # 余弦相似度
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))


# 全局实例
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """获取向量化服务实例"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
