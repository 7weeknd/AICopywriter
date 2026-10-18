"""ORM 数据模型：提示词模板表 + 生成记录表。

设计思路（面试常问「为什么这么设计」）：
- prompt_templates：task 建唯一索引 —— 一个任务只对应一条模板，查询必走索引；
  fields_json 存输入框元数据（JSON 字符串），前端据此渲染表单；
  builtin 标记内置任务，内置的只允许改不允许删，避免把系统自带能力删空。
- generation_history：把「渲染后的最终提示词」也存下来（system_prompt + user_prompt），
  这样任何一条历史都能被完整复现，方便对比同一个模板改动前后的效果。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class PromptTemplate(Base):
    """一条记录 = 一个生成任务的提示词配置。"""

    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.8)
    fields_json: Mapped[str] = mapped_column(Text, default="[]")  # 输入框元数据
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class GenerationHistory(Base):
    """一条记录 = 一次生成：输入参数 + 最终提示词 + 输出文本 + 耗时。"""

    __tablename__ = "generation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    params: Mapped[str] = mapped_column(Text, nullable=False)  # 入参（JSON 字符串）
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
