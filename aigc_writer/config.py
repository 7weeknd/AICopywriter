"""配置模块。

优先级：先加载项目根目录 .env，再被真实环境变量覆盖（线上环境变量优先）。
因此本地开发写 .env，部署时用环境变量即可，代码不用改。
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（aigc_writer/ 的上一级），.env 放这里
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


@dataclass
class Config:
    # 大模型（支持 Ollama 本地 / DeepSeek / 豆包 等任意 OpenAI 兼容服务）
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # MySQL（提示词模板与生成记录都存这里）
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "aigc_writer"

    # 服务端口（start_web.bat 与 app.py 保持同一个值，避免两处不一致）
    port: int = 8020


def load_config() -> Config:
    """从环境变量读取配置，未设置时回退到默认值。"""
    return Config(
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        db_host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        db_port=int(os.getenv("MYSQL_PORT", "3306")),
        db_user=os.getenv("MYSQL_USER", "root"),
        db_password=os.getenv("MYSQL_PASSWORD", ""),
        db_name=os.getenv("MYSQL_DB", "aigc_writer"),
        port=int(os.getenv("APP_PORT", "8020")),
    )
