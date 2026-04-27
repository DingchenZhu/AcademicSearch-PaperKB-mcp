# AcademicSearch + PaperKB MCP

一套通用的**学术论文检索 + 知识库**能力，以 [MCP（Model Context Protocol）](https://modelcontextprotocol.io) 为对外接口，可直接集成到 Claude Code、Cursor、VS Code 等任意支持 MCP 的 Host，也可通过可选的 REST API 层对接 LangChain / Langflow 等框架。

---

## 设计思路

### 核心原则

1. **业务逻辑与协议适配分离**：所有检索、存储、向量化逻辑集中在 `src/core/`，MCP server 和 REST API 只负责参数校验 + 调用 core + 格式化返回值，不包含任何业务逻辑。
2. **不在 server 层调用 LLM**：MCP tools 只返回结构化数据（论文元数据、文本 chunk），由 Host 端 LLM 负责最终推理和生成。
3. **可替换的关键组件**：embedding 提供商、向量检索后端、PDF 解析器均通过抽象接口隔离，切换时只需换实现，不动调用方。
4. **渐进式路线**：V0 先跑通 arXiv 检索，V1 加 PDF ingest，V2 引入高效向量索引，V3 加标签管理和 REST 层。

### 数据流

```
用户 / Agent
    │
    ▼
MCP Host（Claude Code / Cursor / …）
    │  自然语言 → LLM 解析 → 调用 MCP tool
    │
    ├─▶ AcademicSearch MCP (port 9001)
    │       └─▶ core/paper_search  ──▶  arXiv / Semantic Scholar API
    │               返回: Paper[] (结构化元数据)
    │
    └─▶ PaperKB MCP (port 9002)
            ├─▶ core/pdf_ingest   ──▶  下载 PDF → 解析 → 分块
            ├─▶ core/kb_store     ──▶  SQLite (papers / paper_chunks / paper_tags)
            ├─▶ core/embedding    ──▶  OpenAI / NVIDIA NIM embedding API
            └─▶ core/kb_query     ──▶  向量检索 (V0: 线性 cosine, V2: FAISS)
                    返回: RetrievedChunk[] (文本片段 + score)
```

---

## 项目结构

```
AcademicSearch-PaperKB-mcp/
│
├── src/
│   ├── core/                        # 纯业务逻辑层，不耦合任何 Host 或协议
│   │   ├── models.py                # Pydantic 数据模型：Paper / PaperChunk / RetrievedChunk
│   │   │
│   │   ├── paper_search/            # 学术检索模块
│   │   │   ├── base.py              #   BaseSearchClient 抽象接口
│   │   │   ├── arxiv_client.py      #   arXiv Atom API 实现（带重试）
│   │   │   ├── semantic_scholar.py  #   Semantic Scholar 客户端（V1 stub）
│   │   │   └── aggregator.py        #   多源聚合 + 去重，对外暴露 search_papers()
│   │   │
│   │   ├── pdf_ingest/              # PDF 下载 → 解析 → 分块
│   │   │   ├── downloader.py        #   基于 URL hash 的本地缓存下载
│   │   │   ├── parser.py            #   PyMuPDF 文本提取
│   │   │   └── chunker.py           #   字符级 overlap 分块（V3 可换段落级）
│   │   │
│   │   ├── kb_store/                # SQLite 持久化层
│   │   │   ├── database.py          #   建表 + 连接管理（WAL 模式）
│   │   │   ├── paper_store.py       #   papers / paper_tags CRUD
│   │   │   └── chunk_store.py       #   paper_chunks CRUD，embedding 以 float32 BLOB 存储
│   │   │
│   │   ├── kb_query/                # 向量检索层
│   │   │   └── retriever.py         #   KBRetriever：线性 cosine（V2 可换 FAISS）
│   │   │
│   │   └── embedding/               # Embedding 提供商抽象
│   │       ├── base.py              #   BaseEmbedder 接口
│   │       └── openai_embedder.py   #   OpenAI / NVIDIA NIM 兼容实现
│   │
│   ├── servers/                     # MCP 协议适配层（两个独立 server）
│   │   ├── academic_search_server.py  # AcademicSearch MCP，默认端口 9001
│   │   └── paper_kb_server.py         # PaperKB MCP，默认端口 9002
│   │
│   └── api/                         # 可选 REST API 层（V3）
│       └── app.py                   # FastAPI，镜像所有 MCP tool 为 HTTP 端点
│
├── examples/
│   ├── search_demo.py               # V0 CLI：搜索 arXiv 并打印结果
│   └── kb_demo.py                   # V1 CLI：ingest 一篇论文并做语义检索
│
├── tests/
│   ├── test_paper_search.py         # arXiv Atom 解析单测
│   ├── test_pdf_ingest.py           # chunker 单测
│   └── test_kb_store.py             # SQLite CRUD 集成测试（tmp_path）
│
├── scripts/
│   ├── start_search_server.sh       # 一键启动 AcademicSearch MCP
│   └── start_kb_server.sh           # 一键启动 PaperKB MCP
│
├── config/
│   ├── mcp_claude.json              # Claude Code / Claude Desktop MCP 配置片段
│   └── mcp_cursor.json              # Cursor / VS Code MCP 配置片段
│
├── docs/
│   └── academic_search_kb_mcp_design.md   # 完整设计文档
│
├── pyproject.toml                   # 包配置 + 依赖声明
├── requirements.txt                 # 直接 pip install 用
└── .env.example                     # 环境变量模板
```

---

## MCP Tools 一览

### AcademicSearch MCP（port 9001）

| Tool | 说明 |
|---|---|
| `search_papers` | 按关键词搜索论文，支持年份范围和多源，返回 `Paper[]` |
| `get_paper_metadata` | 按 external_id 获取单篇完整元数据 |

### PaperKB MCP（port 9002）

| Tool | 说明 |
|---|---|
| `ingest_paper` | 下载 PDF → 解析 → 分块 → embedding → 入库 |
| `list_kb_papers` | 列出已入库论文，支持关键词 / 标签 / 年份过滤 |
| `search_kb` | 对全库做向量检索，返回最相关 chunks |
| `qa_over_papers` | 限定论文范围的向量检索，返回上下文 chunks（不生成回答） |
| `tag_paper` | 给已入库论文添加标签 |

---

## 数据模型（SQLite）

```
papers          → id, source, external_id, title, abstract, authors(JSON),
                  year, venue, url_pdf, citations, created_at
paper_chunks    → id, paper_id(FK), chunk_index, text, embedding(BLOB float32)
paper_tags      → paper_id(FK), tag
kb_metadata     → key, value  (记录 embedding 模型版本等元信息)
```

---

## 快速开始

### 1. 安装

```bash
conda create -n academic-mcp python=3.11 -y
conda activate academic-mcp
pip install -e ".[dev]"
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 和 EMBEDDING_MODEL 等
```

### 3. 运行测试

```bash
pytest tests/
```

### 4. 启动 MCP servers

```bash
# 终端 1
bash scripts/start_search_server.sh

# 终端 2
bash scripts/start_kb_server.sh
```

### 5. 注册到 Claude Code

```bash
claude mcp add --transport http AcademicSearch http://localhost:9001/mcp --scope user
claude mcp add --transport http PaperKB       http://localhost:9002/mcp --scope user
```

### 6. 注册到 Cursor

将 `config/mcp_cursor.json` 的内容合并到 `~/.cursor/mcp.json`，重启 Cursor。

---

## 实现路线（Roadmap）

| 阶段 | 内容 | 状态 |
|---|---|---|
| **V0** | arXiv 检索 + AcademicSearch MCP | 骨架已生成 |
| **V1** | PDF ingest + SQLite KB + embedding + PaperKB MCP | 骨架已生成 |
| **V2** | FAISS 向量索引 + `qa_over_papers` 完善 | 待实现 |
| **V3** | 标签体系 + REST API 层 + 段落级 chunking | 待实现 |

---

## 技术栈

| 用途 | 选型 |
|---|---|
| MCP SDK | `mcp` 1.x（FastMCP） |
| HTTP 客户端 | `httpx` + `tenacity` |
| PDF 解析 | `pymupdf` |
| 数据校验 | `pydantic` v2 |
| 持久化 | SQLite（WAL 模式） |
| 向量检索（V0-V1） | 线性 cosine（纯 Python） |
| 向量检索（V2+） | FAISS / sqlite-vec |
| Embedding | OpenAI API / NVIDIA NIM（可替换） |
| REST API（可选） | FastAPI + uvicorn |
| 测试 | pytest + pytest-asyncio |

---

## 与其他 Agent 平台集成

- **支持 MCP 的平台**（Claude Code / Cursor / VS Code）：直接用 `config/` 下的配置文件。
- **不支持 MCP 的平台**（LangChain / Langflow / NeMo）：启动 REST API 层（`src/api/app.py`），用 HTTP 端点封装为 Tool / Node。
