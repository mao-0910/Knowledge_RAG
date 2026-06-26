# 投标知识库 RAG 系统

基于 **Elasticsearch** 的知识库 RAG 系统，为投标领域知识管理设计。

## 核心功能

- **知识管理**：分类管理、标签体系、审核发布
- **检索服务**：向量检索 + 关键词检索

## 技术架构

```
FastAPI 服务层
    ├── 知识管理 API (CRUD + 审核)
    └── 检索服务 API
            ↓
Elasticsearch 存储
            ↓
AI 服务层 (BGE-M3 + Qwen3.5)
```

## 环境要求

- Python 3.10+
- Elasticsearch 8.x / 9.x

## 快速开始

### 1. 安装依赖

```bash
pip install -e .
```

### 2. 配置服务

编辑 `config.yaml`：

```yaml
elasticsearch:
  host: "localhost"
  port: 9200
  dimension: 1024

llm:
  api_base: "http://192.168.2.3:42121/v1"
  model: "Qwen3.5-122B-A10B-GPTQ-Int4"

embedding:
  model_name: "BAAI/bge-m3-multilingual"
```

### 3. 启动服务

```bash
# 启动服务器
python main.py

# 仅初始化数据库
python main.py --init
```

服务地址：`http://localhost:8000`

## API 接口

### 知识管理 `/knowledge`

| 接口 | 方法 | 说明 |
|------|------|------|
| `/knowledge` | POST | 创建知识条目 |
| `/knowledge/{id}` | GET/PUT/DELETE | 获取/更新/删除 |
| `/knowledge/list` | POST | 列表查询 |
| `/knowledge/{id}/submit` | POST | 提交审核 |
| `/knowledge/{id}/audit` | POST | 审核操作 |

### 检索服务 `/search`

| 接口 | 方法 | 说明 |
|------|------|------|
| `/search` | POST | 检索（向量+关键词） |

## 实体类型

| 类型 | 说明 |
|------|------|
| Enterprise | 企业介绍 |
| Certificate | 资质证照 |
| Project | 项目案例 |
| TechPlan | 技术方案 |
| ServicePlan | 服务方案 |
| Resume | 人员简历 |
| BusTerms | 商务条款 |
| Standard | 标准承诺 |
| Industry | 行业资料 |
| FAQ | 常见问答 |

## 标签体系

- **行业标签**：政府机关、教育医疗、金融银行、电力能源等
- **客户标签**：战略客户、大客户、国企客户等
- **项目类型**：软件开发、系统集成、运维服务等
- **产品能力**：自有产品、代理产品、解决方案等
- **服务区域**：全国、华东、华南、华北等
- **可公开程度**：公开、内部、机密、绝密

## 依赖

| 依赖 | 用途 |
|------|------|
| FastAPI | Web 框架 |
| Elasticsearch | 统一存储 |
| sentence-transformers | Embedding |

## 许可证

MIT License
