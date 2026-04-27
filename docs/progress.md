# 项目进度记录

> 最后更新：2026-04-26（V3 完成）

---

## 一、项目概览

| 属性 | 值 |
|---|---|
| 项目名 | AcademicSearch + PaperKB MCP |
| 仓库路径 | `/home/scratch.hansz_coreai/mcp/AcademicSearch-PaperKB-mcp` |
| Python 环境 | conda `academic-mcp`，Python 3.11 |
| Python 解释器 | `/home/hansz/scratch-data/tools/miniconda3/envs/academic-mcp/bin/python` |
| 当前分支 | `main` |
| 测试状态 | **116/116 passed** |

---

## 二、已完成工作

### 阶段 0：设计与环境搭建

- [x] 阅读并理解设计文档 `docs/academic_search_kb_mcp_design.md`
- [x] 生成完整多模块 Python 项目骨架（`src/core/`、`src/servers/`、`src/api/`、`tests/`、`examples/`、`scripts/`、`config/`）
- [x] 编写 `pyproject.toml`（修复 build-backend：`setuptools.build_meta`，原错写为 `setuptools.backends.legacy:build`）
- [x] 编写 `requirements.txt` 和 `.env.example`
- [x] 使用 conda 创建隔离环境 `academic-mcp`
- [x] `pip install -e ".[dev]"` 完成全部依赖安装
- [x] 编写 `README.md`（项目结构、设计思路、MCP Tools 一览、Roadmap、技术栈）

---

### V0：学术搜索 + AcademicSearch MCP

**目标**：arXiv 检索可用，AcademicSearch MCP server 可启动。

#### 实现文件

| 文件 | 功能 |
|---|---|
| `src/core/models.py` | Pydantic 数据模型：`Paper`、`PaperChunk`、`RetrievedChunk`、`IngestResult` |
| `src/core/paper_search/base.py` | `BaseSearchClient` 抽象接口 |
| `src/core/paper_search/arxiv_client.py` | arXiv Atom API 客户端，带 tenacity 重试（3次，指数退避） |
| `src/core/paper_search/semantic_scholar.py` | Semantic Scholar stub（V1 预留） |
| `src/core/paper_search/aggregator.py` | 多源聚合 + 去重，对外暴露 `search_papers()` |
| `src/servers/academic_search_server.py` | FastMCP server，端口 9001，tools：`search_papers`、`get_paper_metadata` |

#### Bug 修复记录

- **FastMCP host/port 配置方式错误**：原代码在 `mcp.run()` 里传 `host=` / `port=` / `path=`，但 mcp 1.27.0 的 `run()` 签名只接受 `transport` 和 `mount_path`。正确做法是在 `FastMCP()` 构造器里传 `host=`、`port=`、`streamable_http_path=`。

#### 测试文件

| 文件 | 测试数 | 覆盖内容 |
|---|---|---|
| `tests/test_paper_search.py` | 2 | Atom XML 解析基础单测 |
| `tests/test_v0_search.py` | 13 | Atom 解析边界、ArxivClient httpx mock、aggregator 行为 |

**注意点**：`pytest_httpx` 默认精确匹配 URL（含 query string）。`add_response()` 不传 `url=` 参数可匹配任意请求。重试测试需注册与重试次数等量的 mock 响应，或加 `@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)`。

---

### V1：PDF Ingest + SQLite KB + PaperKB MCP

**目标**：完整的论文入库流程可用，PaperKB MCP server 可启动，线性向量检索可用。

#### 实现文件

| 文件 | 功能 |
|---|---|
| `src/core/pdf_ingest/downloader.py` | 基于 URL SHA256 的本地缓存下载（跳过已缓存，带重试） |
| `src/core/pdf_ingest/parser.py` | PyMuPDF 文本提取 |
| `src/core/pdf_ingest/chunker.py` | 字符级 overlap 分块（默认 chunk_size=1000, overlap=100） |
| `src/core/kb_store/database.py` | SQLite 建表 + WAL 模式 + FK 约束；4张表：`papers`、`paper_chunks`、`paper_tags`、`kb_metadata` |
| `src/core/kb_store/paper_store.py` | `papers` / `paper_tags` CRUD，支持标签 + 年份 + 关键词过滤 |
| `src/core/kb_store/chunk_store.py` | `paper_chunks` CRUD，embedding 序列化为 float32 BLOB（`struct.pack`） |
| `src/core/embedding/base.py` | `BaseEmbedder` 抽象接口 |
| `src/core/embedding/openai_embedder.py` | OpenAI / NVIDIA NIM 兼容 embedding 客户端（异步，批量） |
| `src/core/embedding/fake_embedder.py` | 测试用 FakeEmbedder：SHA256 hash → 归一化向量，离线、确定性 |
| `src/core/kb_query/retriever.py` | `KBRetriever`：线性 cosine 扫描（纯 Python，无额外依赖） |
| `src/servers/paper_kb_server.py` | FastMCP server，端口 9002，tools：`ingest_paper`、`list_kb_papers`、`search_kb`、`qa_over_papers`、`tag_paper` |

#### 关键实现细节

- **chunker 行为**：对文本长度 3000、chunk_size=1000、overlap=100，实际生成 4 个 chunk（末尾不足整块的 partial chunk 也保留）。step = chunk_size - overlap = 900；起点：0, 900, 1800, 2700（均 < 3000）。
- **embedding 存储**：float32 BLOB，用 `struct.pack/unpack` 序列化，精度损失可忽略，比 JSON 存储节约约 4x 空间。
- **server 延迟初始化**：DB 连接和 embedder 客户端在第一次 MCP tool 调用时才初始化，避免进程启动时就需要 API key。

#### 测试文件

| 文件 | 测试数 | 覆盖内容 |
|---|---|---|
| `tests/test_pdf_ingest.py` | 3 | chunker 基础单测 |
| `tests/test_kb_store.py` | 4 | SQLite CRUD 集成测试（tmp_path） |
| `tests/test_v1_ingest.py` | 20 | chunker 边界、FakeEmbedder 性质、完整 ingest round-trip、KBRetriever 检索行为 |

---

### V2：FAISS 向量索引

**目标**：引入 FAISS 加速向量检索，与线性检索结果一致，可通过环境变量切换。

#### 实现文件

| 文件 | 功能 |
|---|---|
| `src/core/kb_query/faiss_retriever.py` | `FaissRetriever`：IndexFlatIP + L2 归一化 = 精确 cosine；惰性重建索引 |
| `src/core/kb_query/factory.py` | `make_retriever()`：根据 `KB_RETRIEVER_BACKEND` 环境变量返回 KBRetriever 或 FaissRetriever |

#### 关键实现细节

- **IndexFlatIP + L2 归一化 = 精确 cosine**：FAISS `IndexFlatIP` 做内积，向量预先 L2 归一化后内积 = cosine，结果与 KBRetriever 完全一致，无近似误差。
- **惰性重建策略**：通过对比当前 chunk 总数与上次建索引时的 chunk 总数决定是否重建，避免每次 search 都重建 index，同时保证 ingest 后第一次 search 能看到新数据。
- **paper_ids 过滤**：FAISS 不支持原生 per-query filter，通过 over-fetch（k × 10）后再 Python 层过滤实现。
- **环境变量切换**：`KB_RETRIEVER_BACKEND=faiss` 时使用 FaissRetriever，默认 `linear` 使用 KBRetriever，server 代码零修改。
- 在 `paper_kb_server.py` 中将 `KBRetriever(...)` 替换为 `make_retriever(...)` 调用。

#### 测试文件

| 文件 | 测试数 | 覆盖内容 |
|---|---|---|
| `tests/test_v2_faiss.py` | 13 | 与线性检索 top-1 一致性、score 范围、降序排列、paper_ids 过滤、auto-rebuild、factory 切换 |

---

## 三、全量测试结果

```
tests/test_kb_store.py              4 passed
tests/test_paper_search.py          2 passed
tests/test_pdf_ingest.py            3 passed
tests/test_v0_search.py            13 passed
tests/test_v1_ingest.py            20 passed
tests/test_v2_faiss.py             13 passed
tests/test_v3_chunking.py          17 passed
tests/test_v3_semantic_scholar.py  21 passed
tests/test_v3_rest_api.py          13 passed
tests/test_v3_mcp_server.py        10 passed
─────────────────────────────────────────────
TOTAL                             116 passed   (12.23s)
```

3 个 DeprecationWarning 来自 FAISS 的 SWIG C++ 绑定（`SwigPyPacked`、`SwigPyObject`），不影响功能，属于 `faiss-cpu` 包自身问题。

---

## 四、当前文件树（完整）

```
src/
├── core/
│   ├── models.py                     # Paper / PaperChunk / RetrievedChunk
│   ├── paper_search/
│   │   ├── base.py                   # BaseSearchClient
│   │   ├── arxiv_client.py           # arXiv Atom API ✅
│   │   ├── semantic_scholar.py       # Semantic Scholar Graph API ✅ (V3)
│   │   └── aggregator.py             # 多源聚合 + 引用排序 + 跨源去重 ✅ (V3)
│   ├── pdf_ingest/
│   │   ├── downloader.py             # URL hash 缓存下载 ✅
│   │   ├── parser.py                 # PyMuPDF ✅
│   │   └── chunker.py                # char chunking + paragraph_chunk + factory ✅ (V3)
│   ├── kb_store/
│   │   ├── database.py               # SQLite WAL ✅
│   │   ├── paper_store.py            # papers/tags CRUD ✅
│   │   └── chunk_store.py            # chunks + float32 BLOB ✅
│   ├── kb_query/
│   │   ├── retriever.py              # 线性 cosine ✅
│   │   ├── faiss_retriever.py        # FAISS IndexFlatIP ✅ (V2)
│   │   └── factory.py                # make_retriever() ✅ (V2)
│   ├── kb_service.py                 # KBService 共享服务层 ✅ (V3)
│   └── embedding/
│       ├── base.py                   # BaseEmbedder
│       ├── openai_embedder.py        # OpenAI / NIM ✅
│       └── fake_embedder.py          # 测试用，离线确定性 ✅
├── servers/
│   ├── academic_search_server.py     # AcademicSearch MCP :9001 ✅
│   └── paper_kb_server.py            # PaperKB MCP :9002（薄适配层）✅ (V3)
└── api/
    └── app.py                        # FastAPI REST API ✅ (V3)

tests/
├── test_paper_search.py              # V0 基础
├── test_pdf_ingest.py                # V1 基础
├── test_kb_store.py                  # V1 基础
├── test_v0_search.py                 # V0 完整 (13 cases)
├── test_v1_ingest.py                 # V1 完整 (20 cases)
├── test_v2_faiss.py                  # V2 完整 (13 cases)
├── test_v3_chunking.py               # V3 chunker (17 cases)
├── test_v3_semantic_scholar.py       # V3 SS + aggregator (21 cases)
├── test_v3_rest_api.py               # V3 REST API (13 cases)
└── test_v3_mcp_server.py             # V3 MCP tools end-to-end (10 cases)

scripts/
├── start_search_server.sh
├── start_kb_server.sh
├── run_tests_v0.sh
├── run_tests_v1.sh
├── run_tests_v2.sh
├── run_tests_v3.sh                   # V3 新增 ✅
└── run_tests_all.sh

config/
├── mcp_claude.json                   # Claude Code MCP 配置片段
└── mcp_cursor.json                   # Cursor MCP 配置片段
```

---

## 五、依赖清单（已安装版本）

| 包 | 版本 | 用途 |
|---|---|---|
| mcp | 1.27.0 | MCP SDK（FastMCP） |
| pydantic | 2.13.3 | 数据模型 |
| pymupdf | 1.27.2.3 | PDF 解析 |
| openai | 2.32.0 | embedding API |
| fastapi | 0.136.1 | REST API 层 |
| uvicorn | 0.46.0 | ASGI server |
| httpx | 0.28.1 | 异步 HTTP 客户端 |
| tenacity | 9.1.4 | 重试逻辑 |
| numpy | 2.4.4 | 向量计算 |
| faiss-cpu | 1.13.2 | V2 向量索引 |
| pytest | 9.0.3 | 测试框架 |
| pytest-asyncio | 1.3.0 | 异步测试 |
| pytest-httpx | 0.36.2 | httpx mock |
| ruff | 0.15.12 | linter |
| mypy | 1.20.2 | 类型检查 |

---

## 六、已知问题 / 注意事项

| 问题 | 状态 | 说明 |
|---|---|---|
| FAISS SWIG DeprecationWarning | 忽略 | faiss-cpu 包自身问题，不影响运行 |
| `openai` 2.x API | 兼容 | `AsyncOpenAI().embeddings.create()` 接口未变，测试通过 |
| pytest_httpx URL 匹配 | 已修复 | `add_response()` 不传 `url=` 参数可匹配任意请求 URL（含 query string） |
| FastMCP host/port | 已修复 | 必须在 `FastMCP()` 构造器传，`run()` 不接受这些参数 |
| server 端到端测试 | ✅ 已完成 | `test_v3_mcp_server.py` 通过 `FastMCP.call_tool()` 覆盖全部工具链路 |

---

## 七、Roadmap 状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| **V0** | arXiv 检索 + AcademicSearch MCP | ✅ 完成 |
| **V1** | PDF ingest + SQLite KB + embedding + PaperKB MCP | ✅ 完成 |
| **V2** | FAISS 向量索引 + factory 切换 | ✅ 完成 |
| **V3** | 段落级 chunking + Semantic Scholar + REST API + MCP 端到端测试 | ✅ 完成 |

---

## 八、V3 完成内容

### V3：段落级 Chunking + Semantic Scholar + REST API 解耦 + MCP 端到端测试

#### 实现文件

| 文件 | 功能 |
|---|---|
| `src/core/pdf_ingest/chunker.py` | 新增 `paragraph_chunk()`：按空行切段落，合并至 target_size，末段 overlap；`make_chunker()` 工厂函数（`CHUNK_STRATEGY` env var） |
| `src/core/paper_search/semantic_scholar.py` | Semantic Scholar Graph API 完整实现：搜索 + 单篇元数据，可选 API key，PDF URL fallback |
| `src/core/paper_search/aggregator.py` | 多源排序：`_rank_key()`（引用数 → 年份 → 来源优先级）；`_dedup_cross_source()`（标题 + 年份跨源去重，保留更丰富条目） |
| `src/core/kb_service.py` | **新**：`KBService` 共享服务层，解耦 MCP server 与 REST API 的公共逻辑；`get_kb_service()` 懒单例；`reset_kb_service()` 供测试注入 |
| `src/servers/paper_kb_server.py` | 精简为薄适配层：所有工具调用 `get_kb_service()` 方法，消除全局状态 |
| `src/api/app.py` | **重构**：不再依赖 `src.servers.*`；直接调用 `get_kb_service()` 和 `search_papers()`；补全 `/api/list_papers`、`/api/search_kb`、`/api/qa_over_papers`、`/api/tag_paper` |

#### 关键设计决策

- **KBService 解耦**：原来 `src/api/app.py` 直接 import server 模块的函数，形成 `api → servers` 循环依赖。引入 `KBService` 作为共享核心，MCP server 和 REST API 都调用它，各自只做薄适配。
- **FastMCP.call_tool() 双格式适配**：mcp 1.27 中 `list[dict]` 返回工具走 `(content_blocks, {'result': list})` tuple，`dict` 返回工具走 `[TextContent(text=json_str)]` list。`_unwrap()` 帮助函数同时处理两种格式。
- **paragraph_chunk 降级**：单段落（无空行）文本自动降级为字符级 `chunk_text()`，保证任意 PDF 格式都不会产生超长单块。

#### 测试文件

| 文件 | 测试数 | 覆盖内容 |
|---|---|---|
| `tests/test_v3_chunking.py` | 17 | `paragraph_chunk` 边界行为、`make_chunker` factory、策略切换 |
| `tests/test_v3_semantic_scholar.py` | 21 | `_to_paper` 字段映射、SS 客户端 mock、aggregator 排序 + 去重 + 多源合并 |
| `tests/test_v3_rest_api.py` | 13 | 全部 REST 端点（TestClient，in-memory SQLite + FakeEmbedder） |
| `tests/test_v3_mcp_server.py` | 10 | 全部 MCP tools via `FastMCP.call_tool()`（无 HTTP server，in-process） |

---

## 九、下一步（V4 候选）

1. **CrossRef 来源**：补充第三个搜索源（DOI 解析、期刊引用数据）。
2. **增量 ingest**：检测已存在 `(source, external_id)` 时跳过重新下载，仅更新元数据。
3. **摘要嵌入**：ingest 时同时向量化论文摘要，搜索时合并摘要分数与正文分数。
4. **Streaming MCP**：为 `search_kb` / `qa_over_papers` 添加 Server-Sent Events 流式返回，适合大 top_k 结果。
