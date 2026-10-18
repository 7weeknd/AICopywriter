@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ===== 大模型配置（默认本地 Ollama；换 DeepSeek 就改这三行）=====
set LLM_BASE_URL=http://localhost:11434
set LLM_API_KEY=ollama
set LLM_MODEL=qwen3.5:0.8b

rem 启动后自动打开浏览器
set TEXTGEN_OPEN_BROWSER=1

if not exist ".venv\Scripts\python.exe" (
  echo [error] 没找到 .venv，请先执行：
  echo     python -m venv .venv
  echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

echo [info] 服务启动中，请确保本机 MySQL 已启动（提示词模板存在数据库里）
".venv\Scripts\python.exe" -m uvicorn aigc_writer.app:app --host 0.0.0.0 --port 8020

pause
