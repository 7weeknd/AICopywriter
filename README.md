# AICopywriter

**多任务文本生成服务 · 提示词模板可配置** · 检索无关，只做生成侧

用一套接口跑三类文本生成任务（**营销文案 / 文本摘要 / 改写润色**），
每个任务的**提示词存在数据库里、可以在页面上直接改**，改完立刻生效、不用重启。

技术栈：FastAPI + Pydantic（接口与校验）· SQLAlchemy 2.x + MySQL（模板与记录持久化）·
Ollama 本地大模型（也可换成任意 OpenAI 兼容服务）。

> 与 [LocalRAG-QA](../LocalRAG-QA) 的分工：
> 那个项目解决「**答案从哪来**」（检索算法、防幻觉），本项目解决「**文字怎么写**」
> （提示词工程、多任务抽象）。本项目是把前者的文案生成子模块抽出来独立演进的结果。

---

## 一、系统架构

```
用户：选任务 → 填参数
          │
          ▼
┌──────────────────────────────────┐
│ 模板渲染层（templates.py）          │
│ · 从 MySQL 取该任务的模板            │
│ · 补齐派生参数（风格代号 → 格式要求）  │
│ · 把 {字段名} 替换成实际值           │
└────────────────┬─────────────────┘
                 ▼
          system + user 提示词
                 │
                 ▼
        大模型（本地 Ollama，think 关闭）
                 │
                 ▼
     结果 + 耗时 ──▶ 写入 generation_history
```

一次生成走 4 步：**取模板 → 补参数 → 渲染提示词 → 调用模型并落库**。

---

## 二、核心设计（面试重点，三点）

### 1. 提示词是数据，不是代码
任务模板存在 `prompt_templates` 表里（system 提示词 + user 模板 + temperature）。
新增一种生成任务，**不用改代码、不用重启**，插入一条记录即可；
页面上也能直接改提示词和温度，下一次生成立即生效。

对比「把提示词写死在 .py 里」：改一句提示词要改代码、要发版、还要重跑测试。
提示词是最高频变更的东西，它应该被配置化。

### 2. 表单由后端元数据驱动
每条模板带一份 `fields_json`，描述这个任务要哪些输入框
（类型 / 标签 / 是否必填 / 下拉选项）。前端拿 `GET /api/tasks` 后**直接按元数据渲染表单**，
所以新增任务时前端一行都不用改。

### 3. 模板渲染用正则，不用 `str.format`
`render()` 只替换 `{字段名}` 这一种形式：

```python
_TOKEN = re.compile(r"\{(\w+)\}")
```

为什么不用更省事的 `str.format`？因为**模板内容来自数据库、参数来自用户输入**：
- `str.format` 会解析属性和下标访问（如 `{a.__class__}`），存在信息泄露风险；
- 参数缺失时会直接抛 `KeyError`，把一次正常请求变成 500。

正则白名单替换只认字段名、缺参数填空串，**模板怎么改都不会崩**。

### 4. 温度按任务差异化
不是所有生成都要「有创意」：

| 任务 | temperature | 原因 |
|------|-------------|------|
| 营销文案生成 | 0.8 | 求创意与感染力，发散是好事 |
| 改写润色 | 0.5 | 既要变又不能跑偏，取中间值 |
| 文本摘要 | 0.3 | 必须忠于原文，越低越稳 |

温度也是模板的一部分，所以**在页面上就能调**，不用改代码。

### 5. 可复现
`generation_history` 不只有输出，还存了**渲染后的最终提示词**（system + user）和入参，
所以任何一条历史都能被完整解释——「当时为什么生成成这样」有据可查，
也方便对比改模板前后的效果差异。

---

## 三、快速开始

> 环境要求：Python 3.10+；**MySQL 必须处于启动状态**（任务模板存在数据库里）。

### 1. 安装依赖

```bash
cd AICopywriter
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 配置

复制 `.env.example` 为 `.env`，填上 MySQL 账号密码即可（`.env` 已被 git 忽略）。

本地大模型默认走 Ollama，把模型拉下来：

```bash
ollama pull qwen3.5:0.8b
```

换 DeepSeek 等云端服务：只改 `.env` 里 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL` 三项，代码不动。

### 3. 启动

双击 `start_web.bat`（自动打开浏览器），或手动执行：

```bash
.venv\Scripts\python.exe -m uvicorn aigc_writer.app:app --host 0.0.0.0 --port 8020
```

浏览器打开 <http://127.0.0.1:8020>，首次启动会自动建 `aigc_writer` 库、
建表并写入三个内置任务模板，**无需手工执行任何 SQL**。

---

## 四、API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tasks` | 列出全部任务（含表单元数据） |
| POST | `/api/generate` | 生成（渲染模板 → 调模型 → 自动写入历史） |
| POST | `/api/preview` | 只渲染提示词，不调模型（改模板时先看效果，毫秒级返回） |
| GET | `/api/history?limit=20` | 查生成记录（最新在前） |
| DELETE | `/api/history/{id}` | 删除一条生成记录 |
| GET | `/api/templates/{task}` | 查看单个任务模板 |
| PUT | `/api/templates/{task}` | 修改模板（内置任务可改，但不可删） |
| POST | `/api/templates` | 新增自定义任务 |
| DELETE | `/api/templates/{task}` | 删除自定义任务（内置任务返回 400） |
| GET | `/health` | 服务状态 + 当前模型 + 库名 |

错误码约定：未配置大模型 → `503`；大模型调用失败 → `502`；
缺必填参数 → `422`；任务不存在 → `404`；任务标识重复 → `409`。

---

## 五、目录结构

```
AICopywriter/
├── aigc_writer/
│   ├── config.py      # 配置（.env + 环境变量覆盖）
│   ├── llm.py         # 大模型客户端（Ollama 原生端点 / OpenAI 兼容端点）
│   ├── templates.py   # 内置任务模板 + 渲染（核心设计所在）
│   ├── generator.py   # 生成编排：补派生参数 → 渲染 → 调用
│   ├── database.py    # 引擎 / 会话 / 自动建库建表 / 种子模板
│   ├── models.py      # ORM：PromptTemplate / GenerationHistory
│   ├── schemas.py     # Pydantic 入参出参
│   ├── routes.py      # 9 个接口
│   └── app.py         # FastAPI 入口（lifespan 里建库建表 + 写种子）
├── static/index.html  # 单页前端（原生 HTML/JS，无构建链）
├── .env.example
├── start_web.bat      # 一键启动（自动开浏览器）
├── requirements.txt
└── README.md
```

---

## 六、后续可扩展方向

1. **流式输出**：接 Ollama 的 `stream=true`，用 SSE 逐块推送，降低等待感。
2. **多版本提示词对比**：同一任务存多个模板版本，A/B 跑同一批输入比效果。
3. **Prompt 评估集**：为每个任务准备固定输入集，改模板后一键回归，避免「改好一个坏三个」。
4. **接入向量检索做少样本示例**：按输入相似度动态挑 few-shot 例子拼进提示词。
5. **批量生成 + 导出**：一次跑一批参数，结果导出 Excel/CSV。
