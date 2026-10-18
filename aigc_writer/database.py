"""数据库连接与初始化。

三件事，由外到内：
1. init_db()：先连 MySQL 服务器建库（存在就跳过），再按 ORM 模型建表，
   最后把内置任务模板作为种子写进去 —— 用户装好 MySQL 后零手工 SQL。
2. engine：全局连接池（pool_pre_ping 会在取连接前先探活，避免 MySQL 重启后拿到死连接）。
3. get_db()：FastAPI 依赖注入，一个请求一个会话，用完自动关闭，防止连接泄漏。
"""
import json

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import load_config

_config = load_config()


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def _build_url(db_name: str | None = None) -> URL:
    """构造 MySQL 连接串；db_name 为 None 时只连服务器（用于建库）。"""
    return URL.create(
        "mysql+pymysql",
        username=_config.db_user,
        password=_config.db_password,
        host=_config.db_host,
        port=_config.db_port,
        database=db_name,
        query={"charset": "utf8mb4"},
    )


# 正式引擎：带库名的连接池。模块导入时不发真实连接，所以 MySQL 没起也不会导入报错
engine = create_engine(_build_url(_config.db_name), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def seed_templates() -> int:
    """把内置任务模板写进库：已存在（按 task）就跳过，不覆盖用户的修改。"""
    from . import models
    from .templates import DEFAULT_TEMPLATES

    created = 0
    with SessionLocal() as db:
        for item in DEFAULT_TEMPLATES:
            exists = db.scalar(
                select(models.PromptTemplate).where(
                    models.PromptTemplate.task == item["task"]
                )
            )
            if exists:
                continue
            db.add(
                models.PromptTemplate(
                    task=item["task"],
                    name=item["name"],
                    description=item["description"],
                    system_prompt=item["system_prompt"],
                    user_template=item["user_template"],
                    temperature=item["temperature"],
                    fields_json=json.dumps(item["fields"], ensure_ascii=False),
                    builtin=True,
                )
            )
            created += 1
        db.commit()
    return created


def init_db() -> None:
    """建库 + 建表 + 写种子模板（幂等，可重复调用）。"""
    server_engine = create_engine(_build_url(), pool_pre_ping=True)
    with server_engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{_config.db_name}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
        conn.commit()
    server_engine.dispose()

    from . import models  # noqa: F401  # 导入以把表定义注册到 Base.metadata

    Base.metadata.create_all(engine)
    seed_templates()


def get_db():
    """FastAPI 依赖：每个请求一个独立会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
