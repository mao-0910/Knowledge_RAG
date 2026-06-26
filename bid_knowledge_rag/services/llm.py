"""LLM 服务封装"""
import json
import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import LLMConfig, get_settings

logger = logging.getLogger(__name__)


class LLMService:
    """LLM 服务封装"""
    
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or get_settings().llm
        self.client: httpx.AsyncClient | None = None
    
    async def get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.config.api_base,
                timeout=httpx.Timeout(self.config.timeout),
                headers={"Authorization": f"Bearer {self.config.api_key}"},
            )
        return self.client
    
    async def close(self) -> None:
        """关闭客户端"""
        if self.client:
            await self.client.aclose()
            self.client = None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> str:
        """
        发送 chat 请求
        
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 返回格式 ("json_object" 等)
            
        Returns:
            LLM 返回的文本
        """
        client = await self.get_client()
        
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
        }
        
        if temperature is not None:
            payload["temperature"] = temperature
        elif self.config.temperature:
            payload["temperature"] = self.config.temperature
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        if response_format:
            payload["response_format"] = {"type": response_format}
        
        try:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            raise
    
    async def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """
        发送 chat 请求并解析 JSON 返回
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            
        Returns:
            解析后的 JSON 对象
        """
        content = await self.chat(
            messages=messages,
            temperature=temperature,
            response_format="json_object",
        )
        
        # 去除可能的 markdown fence
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        content = content.strip()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}, content: {content[:200]}")
            return {}
    
    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ):
        """
        流式 chat 请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            
        Yields:
            逐块返回的文本
        """
        client = await self.get_client()
        
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
        }
        
        if temperature is not None:
            payload["temperature"] = temperature
        elif self.config.temperature:
            payload["temperature"] = self.config.temperature
        
        try:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            content = chunk["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            raise


# 全局实例
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """获取 LLM 服务实例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
