"""投标知识库 RAG 系统主程序"""
import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import get_settings, reload_settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def initialize_system():
    """初始化系统组件"""
    from storage import get_es_store
    from services import get_embedding_service

    settings = get_settings()
    logger.info("Initializing system components...")

    # 1. 初始化 Elasticsearch 统一存储
    logger.info("Connecting to Elasticsearch...")
    es_store = get_es_store()
    await es_store.connect()
    await es_store.initialize_indices()

    # 2. 初始化 Embedding 模型
    logger.info("Loading embedding model...")
    try:
        embedding_service = get_embedding_service()
        embedding_service.load_model()
        logger.info("Embedding model loaded successfully")
    except Exception as e:
        logger.warning(f"Embedding model load failed, using fallback: {e}")

    logger.info("System initialization completed")


async def shutdown_system():
    """关闭系统组件"""
    from storage import get_es_store

    logger.info("Shutting down system components...")

    try:
        es_store = get_es_store()
        await es_store.close()
    except Exception as e:
        logger.error(f"Error closing Elasticsearch: {e}")

    logger.info("System shutdown completed")


async def run_server():
    """运行 FastAPI 服务器"""
    import uvicorn
    from api import app

    settings = get_settings()

    # 初始化系统
    await initialize_system()

    # 运行服务器
    config = uvicorn.Config(
        app=app,
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
        log_level=settings.logging.level.lower(),
    )
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        await shutdown_system()


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="投标知识库 RAG 系统")
    parser.add_argument("--config", type=str, help="配置文件路径")
    parser.add_argument("--init", action="store_true", help="仅初始化数据库")
    args = parser.parse_args()

    # 加载配置
    if args.config:
        reload_settings(args.config)

    settings = get_settings()
    logger.info(f"Starting {settings.app.name} v{settings.app.version}")

    if args.init:
        # 仅初始化
        asyncio.run(initialize_system())
        asyncio.run(shutdown_system())
        logger.info("Initialization completed")
    else:
        # 启动服务器
        asyncio.run(run_server())


if __name__ == "__main__":
    main()
