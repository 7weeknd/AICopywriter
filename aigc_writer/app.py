"""FastAPI 服务入口。

启动（在项目根目录 AICopywriter/ 下）：
    uvicorn aigc_writer.app:app --host 0.0.0.0 --port 8020
或直接双击 start_web.bat（会自动开浏览器）。

启动时会自动建库建表并写入内置任务模板；
提示词模板与生成记录都存放在数据库，所以 MySQL 必须处于启动状态。
"""
import os
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from . import database
from .config import load_config
from .generator import get_llm
from .routes import router as api_router

_BASE = Path(__file__).resolve().parent
_ROOT = _BASE.parent
_config = load_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 建库建表 + 写种子模板；失败不退出，方便看到明确原因
    try:
        database.init_db()
        print(
            f"[startup] MySQL 就绪：库 {_config.db_name}，"
            "表 prompt_templates / generation_history 已建，内置任务模板已写入"
        )
    except Exception as exc:
        print(f"[error] MySQL 初始化失败：{exc}")
        print("[error] 任务模板与生成记录都依赖数据库，请先启动 MySQL 再重试")

    llm = get_llm()
    print(f"[startup] 大模型：{llm.model if llm.enabled else '未配置（生成接口会返回 503）'}")

    # 双击 start_web.bat 启动时自动打开浏览器
    if os.getenv("TEXTGEN_OPEN_BROWSER") == "1":
        webbrowser.open(f"http://127.0.0.1:{_config.port}")
    yield


app = FastAPI(
    title="AICopywriter · 多任务文本生成服务",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health")
def health():
    llm = get_llm()
    return {
        "status": "ok",
        "model": llm.model if llm.enabled else "未配置",
        "db": _config.db_name,
    }


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(_ROOT / "static" / "index.html")
