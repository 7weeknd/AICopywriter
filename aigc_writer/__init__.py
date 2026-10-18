"""AICopywriter · 多任务文本生成服务。

与 LocalRAG-QA 的分工：
- LocalRAG-QA：检索增强问答（知识库 + 检索算法 + 生成）；
- AICopywriter：纯生成侧（提示词模板可配置 + 多任务路由 + 生成记录可复现）。

包内模块：
    config.py     配置（.env + 环境变量覆盖）
    llm.py        大模型客户端（Ollama 原生 /api/chat，或任意 OpenAI 兼容服务）
    templates.py  内置任务模板 + 模板渲染（核心设计）
    generator.py  生成编排：参数增强 → 渲染 → 调模型
    database.py   SQLAlchemy 引擎 / 会话 / 建库建表 / 种子模板
    models.py     ORM 模型：PromptTemplate / GenerationHistory
    schemas.py    Pydantic 入参出参
    routes.py     接口层
    app.py        FastAPI 入口
"""

__version__ = "1.0.0"
