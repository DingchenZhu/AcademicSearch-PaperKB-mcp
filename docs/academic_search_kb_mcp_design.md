# 学术搜索 & 论文知识库 MCP 设计文档

## 1. 背景与目标

本项目目标是实现一套**通用的学术搜索 Agent + 论文知识库（KB）能力**，以 **MCP（Model Context Protocol）** 为对外标准接口，使其可以在 Claude Code、Cursor、自研 Agent 平台等多种工具中复用。

### 1.1 具体目标

1. **学术搜索能力（AcademicSearch Agent）**
   - 支持对 arXiv / Semantic Scholar / CrossRef / PubMed 等来源的论文检索。
   - 返回结构化的论文元数据（标题、作者、年份、venue、摘要、PDF URL、引用数等）。

2. **论文知识库能力（PaperKB Agent）**
   - 下载并解析论文 PDF，构建本地向量化知识库。
   - 支持：
     - 论文入库（ingest）
     - 库内论文列表 / 筛选
     - 基于论文集的向量检索
     - 针对指定论文集的 QA / 对比 / 综述辅助

3. **通用性与可迁移性**
   - 对外通过 **MCP server** 暴露能力，不耦合特定 LLM 提供商。
   - 可方便迁移到支持 MCP 的任意 Host：
     - Claude Code / Claude Desktop
     - Cursor / VS Code MCP 插件
     - NeMo / AIQ 等自研或第三方 Agent 平台
   -（可选）通过 REST API 再暴露一层 HTTP 接口给不支持 MCP 的工具（LangChain、Langflow、ChatGPT 插件等）使用。

### 1.2 非目标（第一阶段不做）

- 不做模型训练或微调，只做 **检索 + 调用现有大模型推理**。
- 不做复杂 Web UI，先从 CLI + MCP Host 集成开始。

---

## 2. 整体架构

### 2.1 分层设计

整个系统按“**核心业务逻辑**”与“**协议适配层**”分离：

1. **核心库（core library）**
   - `paper_search`：调用外部学术 API，统一封装论文检索逻辑。
   - `pdf_ingest`：下载 PDF、解析文本、切 chunk。
   - `kb_store`：管理 SQLite / 向量库中的论文与文本块。
   - `kb_query`：对 KB 执行向量检索与过滤。

2. **MCP Server 1：AcademicSearch MCP**
   - 将“学术搜索相关功能”以 MCP tools 的形式暴露给 Host。
   - 仅负责参数校验 + 调用 core lib + 返回结构化 JSON。

3. **MCP Server 2：PaperKB MCP**
   - 将“论文知识库相关功能”以 MCP tools 的形式暴露。
   - 负责论文 ingest、KB 检索、QA 等操作。

4. **（可选）REST API 层**
   - 使用 FastAPI 或类似框架，对外提供 `/search_papers`、`/ingest_paper`、`/qa_over_papers` 等端点。
   - 面向不支持 MCP 的环境（如部分自研 Agent、普通 Web 服务）。

### 2.2 数据流概览

典型使用流程：

1. Host（如 Claude Code）调用 **AcademicSearch MCP** 的 `search_papers`：
   - 用户自然语言请求 → LLM 解析 → 调用 MCP tool。
   - MCP server 访问外部学术 API，返回论文列表。

2. 用户或 Agent 从结果中选择若干论文，调用 **PaperKB MCP** 的 `ingest_paper`：
   - MCP server 下载 PDF → 解析文本 → 分块 → 向量化 → 入库。

3. 后续对话中，Host 调用 **PaperKB MCP** 的 `qa_over_papers` / `search_kb`：
   - MCP server 做向量检索，返回相关 chunks、论文 ID 等。
   - Host 端 LLM 使用这些上下文生成回答、对比表或综述。

---

## 3. 技术栈选择

- **语言**：Python
- **MCP SDK**：官方 Python SDK（FastMCP / `modelcontextprotocol`）
- **Web 框架（可选）**：FastAPI / Starlette（用于 HTTP MCP & REST）
- **数据库**：SQLite（本地单机足够，可后续换 PG/MySQL）
- **向量库**：
  - V0–V1：SQLite + 手写 cosine 相似度（线性扫描）
  - V2 之后：FAISS 或 sqlite-vec（加速向量检索）
- **PDF 解析**：`pymupdf` 或 `pdfminer.six`
- **Embedding 模型**：
  - 初期使用任一可用 embedding API（如 OpenAI / NVIDIA NIM / 本地 Ollama embedding）
  - 将 embedding 调用封装在独立模块，便于替换。

---

## 4. 数据模型设计（SQLite 初版）

### 4.1 表结构草案

1. `papers`
   - `id` (TEXT, internal UUID, PK)
   - `source` (TEXT, 如 `"arxiv"`, `"semantic_scholar"`)
   - `external_id` (TEXT, 如 arxiv id / doi / semantic scholar id)
   - `title` (TEXT)
   - `abstract` (TEXT)
   - `authors` (TEXT，简单用 `;` 拼接或 JSON)
   - `year` (INTEGER)
   - `venue` (TEXT)
   - `url_pdf` (TEXT)
   - `created_at` (TIMESTAMP)

2. `paper_chunks`
   - `id` (TEXT, PK)
   - `paper_id` (TEXT, FK→`papers.id`)
   - `chunk_index` (INTEGER)
   - `text` (TEXT)
   - `embedding` (BLOB 或向量类型，视具体向量库实现)

3. `paper_tags`
   - `paper_id` (TEXT)
   - `tag` (TEXT)

4. `kb_metadata`（可选）
   - `key` (TEXT)
   - `value` (TEXT)
   - 用于记录 embedding 模型版本、参数等元信息。

### 4.2 设计注意点

- 保持 `papers` 与 `paper_chunks` 解耦，便于后续替换向量库实现。
- `embedding` 字段在 V0 可以先不落库（仅做 in-memory 实验），V1 之后再正式入库。
- `authors` 建议用 JSON 存数组，方便 Host 端展示。

---

## 5. AcademicSearch MCP 设计

### 5.1 职责与边界

- 只负责“发现论文”和返回**元数据**；不做 PDF 下载与 KB 写入。
- 不包含任何 Host 相关的提示文案，只返回结构化数据。

### 5.2 MCP Tools 设计

1. `search_papers`
   - 入参：
     - `query: string`
     - `year_from?: int`
     - `year_to?: int`
     - `max_results?: int`（默认 20）
   - 行为：
     - 汇总调用外部源（arXiv 起步），聚合排序。
   - 返回：
     - `papers: [Paper]`，每个结构类似：
       ```json
       {
         "internal_id": "uuid",
         "source": "arxiv",
         "external_id": "2101.00001",
         "title": "...",
         "authors": ["A", "B"],
         "year": 2023,
         "venue": "NeurIPS",
         "abstract": "...",
         "url_pdf": "https://arxiv.org/pdf/2101.00001.pdf",
         "citations": 123
       }
       ```

2. `get_paper_metadata`
   - 入参：
     - `internal_id` 或 `external_id + source`
   - 行为：
     - 从缓存 / 远端重新获取单篇完整元数据。
   - 返回：
     - 单个 `Paper` 对象。

3. `get_paper_pdf_url`（可选）
   - 入参：`external_id`, `source`
   - 返回：`url_pdf` 字符串。

### 5.3 实现要点

- 在 core lib 中：
  - `search_arxiv(query, year_from, year_to, max_results)`
  - 其他源后续扩展：`search_semantic_scholar(...)` 等。
- AcademicSearch MCP server 只负责：
  - 解析 MCP 请求 → 调 core lib → 返回 JSON。

---

## 6. PaperKB MCP 设计

### 6.1 职责与边界

- 负责论文内容的生命周期：
  - 下载 / 解析 / 入库（ingest）
  - 向量化存储与检索
  - 提供便于上层 LLM 使用的“上下文片段集合”

### 6.2 MCP Tools 设计

1. `ingest_paper`
   - 入参：
     - `pdf_url: string`（或 `source + external_id`，可扩展）
     - `tags?: [string]`
   - 行为：
     1. 下载 PDF。
     2. 解析文本，按一定长度切 chunk（例如 512–1024 tokens 级别）。
     3. 调用 embedding 模型为每个 chunk 生成向量。
     4. 写入 `papers` / `paper_chunks` / `paper_tags` 表。
   - 返回：
     - `paper_id`
     - `num_chunks`
     - `char_count` 等统计信息。

2. `list_kb_papers`
   - 入参（全可选）：
     - `query?: string`（按标题/摘要模糊搜索）
     - `tag?: string`
     - `year_from?: int`
     - `year_to?: int`
   - 行为：
     - 查询 `papers` + `paper_tags`。
   - 返回：
     - Paper 列表。

3. `search_kb`
   - 入参：
     - `query: string`
     - `top_k?: int`
   - 行为：
     1. 对 `query` 进行 embedding。
     2. 在所有 chunk 或摘要上做向量检索。
   - 返回：
     - 相关论文列表（可带 `score` 和简短摘要）。

4. `qa_over_papers`
   - 入参：
     - `paper_ids: [string]`（为空则表示全库）
     - `question: string`
     - `top_k?: int`
   - 行为：
     1. 限定检索范围为指定论文的 chunks。
     2. 嵌入 `question`，做向量检索。
     3. 返回若干“候选片段”：
        ```json
        {
          "paper_id": "...",
          "chunk_index": 3,
          "score": 0.87,
          "text": "..."
        }
        ```
   - **不直接生成自然语言回答**，只返回上下文，由 Host 端 LLM 负责最终回答。

5. `tag_paper`（可选）
   - 入参：
     - `paper_id: string`
     - `tags: [string]`
   - 行为：
     - 更新 `paper_tags`。

---

## 7. 协议适配层

### 7.1 MCP Server 实现

- 建议两个独立 Python 模块：
  - `academic_search_server.py`
  - `paper_kb_server.py`
- 使用 FastMCP / MCP Python SDK：
  - 在文件顶部初始化 MCP server。
  - 用装饰器或注册函数声明各个 tool。
  - 在 tool handler 中只做：
    - 参数解析与校验；
    - 调用 core library；
    - 将返回值转成 MCP 定义的 JSON schema。

**重要约束：**

- **不要在 server 内部直接调 LLM**，只做数据操作。
- 返回值中不要包含与特定 Host UI 绑定的文案（如“请点击 Run tool”），保持 Host 无关。

### 7.2 REST API 层（可选）

- 使用 FastAPI 实现一个纯 REST 服务：
  - `POST /api/search_papers`
  - `POST /api/ingest_paper`
  - `POST /api/qa_over_papers`
- 复用同一套 core library，确保 MCP 和 REST 一致。
- 便于：
  - LangChain：写 `Tool` 调 HTTP；
  - Langflow：添加 HTTP 节点；
  - 其他框架：直接调用 REST。

---

## 8. 与各类 Host 的集成方式

### 8.1 Claude Code / Claude CLI

1. 启动两个 MCP server（HTTP 形式）：
   - `http://localhost:9001/mcp`（AcademicSearch）
   - `http://localhost:9002/mcp`（PaperKB）
2. 在终端里执行：
   ```bash
   claude mcp add --transport http AcademicSearch http://localhost:9001/mcp --scope user
   claude mcp add --transport http PaperKB       http://localhost:9002/mcp --scope user
   claude mcp list
   ```
3. 在 Claude 会话中使用自然语言驱动：
   - 例如：
     - “先用 AcademicSearch 搜索 2021–2024 graph transformer 相关论文，挑 10 篇代表作。”
     - “对其中最相关的 5 篇调用 PaperKB.ingest_paper，然后基于这些论文帮我写一个综述大纲。”

### 8.2 Cursor / VS Code MCP

1. 本地启动 MCP server。
2. 编辑 `~/.cursor/mcp.json`（或项目 `.cursor/mcp.json`）：
   ```json
   {
     "mcpServers": {
       "AcademicSearch": { "url": "http://localhost:9001/mcp" },
       "PaperKB":       { "url": "http://localhost:9002/mcp" }
     }
   }
   ```
3. 重启 Cursor，检查 MCP 面板中的连接状态与可用 tools。

### 8.3 其他 Agent 平台（LangChain / NeMo / Langflow）

- 若平台支持 MCP client：
  - 直接按其 MCP client 文档连接两个 MCP server。
- 若不支持：
  - 使用 REST API 端点；
  - 为每个 API 写一个轻量的封装（Tool / Node / Function）。

---

## 9. 实现路线（Roadmap）

建议按以下阶段逐步实现，每一阶段都可用 Claude Code 帮忙写具体代码：

### V0：基础学术搜索 + AcademicSearch MCP

- 实现：
  - `paper_search` 模块（仅支持 arXiv）。
  - `search_papers` / `get_paper_metadata` MCP tools。
- 不做 PDF 下载，不动 KB。

### V1：PDF ingest + 简单 KB + PaperKB MCP

- 新增：
  - `pdf_ingest` 模块（下载 + 解析 + 分块）。
  - 基于 SQLite 的 `papers` / `paper_chunks`。
  - embedding 调用（可先走一个简单 API）。
  - PaperKB MCP 的：
    - `ingest_paper`
    - `list_kb_papers`
    - `search_kb`
- 向量检索先用“线性扫描 + cosine”。

### V2：向量检索优化 + QA 能力

- 引入真正的向量库（FAISS / sqlite-vec）。
- 实现 `qa_over_papers` 工具。
- 设计好返回 schema，方便 Host 端 LLM：
  - 按论文分组；
  - 输出对比表、综述结构等。

### V3：标签体系 + REST 支持 + 体验打磨

- `tag_paper` 等管理工具。
- 实现 REST API 层，方便迁移到 LangChain / Langflow 等。
- 优化 chunk 策略（按段落 / 标题分块，而非纯固定长度），提升语义一致性。

---

## 10. 与 Claude 的协作建议

后续可以直接把本 Markdown 作为“系统设计文档”丢给 Claude，让它分别执行：

1. 生成项目骨架（多模块 Python 项目 + `pyproject.toml` / `requirements.txt`）。
2. 按 **V0 → V1 → V2** 的顺序逐步实现与测试：
   - 每阶段完成后写简单 CLI demo（例如 `python examples/search_demo.py`）。
3. 最后让 Claude 自动生成：
   - `README.md`（安装与使用教程）
   - 示例 MCP 配置片段（Claude / Cursor 各一份）
   - 若需要，再生成 Dockerfile / 部署脚本。

