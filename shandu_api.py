"""
AI 搜尋與研究 RESTful API 服務（支援 WebSocket 實時通訊）
核心功能：提供 AI 增強搜尋（/aisearch）、基礎搜尋（/search）及深度研究（/research）的異步 API 接口，支持動態模型配置（OpenAI/Ollama）。

使用示例（Curl 調用）：
- AI 增強搜尋：
  `curl -X POST "http://localhost:5002/aisearch" -H "Content-Type: application/json" -d '{"query": "AI 限流算法", "engines": ["Google", "Bing"], "max_results": 5, "detailed": true}'`
- 基礎搜尋：
  `curl -X POST "http://localhost:5002/search" -H "Content-Type: application/json" -d '{"query": "FastAPI 限流", "max_results": 3}'`
- 深度研究：
  `curl -X POST "http://localhost:5002/research" -H "Content-Type: application/json" -d '{"query": "AI 搜尋技術演進", "depth": 3, "breadth": 5}'`
- 更新模型配置（切換 Ollama）：
  `curl -X POST "http://localhost:5002/update_config" -H "Content-Type: application/json" -d '{"model_type": "ollama", "api_base": "http://localhost:11434", "model_name": "llama2"}'`
- 查詢當前配置：
  `curl "http://localhost:5002/get_config"`

依賴套件：
- 標準庫：os, asyncio, logging（日誌）, time（時間測量）, pathlib（文件路徑）, enum（枚舉類型）, typing（類型註釋）, sqlalchemy（資料庫 ORM）
- 第三方庫：
  - fastapi（Web 框架，實現 RESTful API）
  - pydantic（請求/響應資料驗證）
  - python-dotenv（加載 .env 環境變數）
  - requests（HTTP 請求）
  - uvicorn（ASGI 伺服器）
  - sqlalchemy（資料庫連接池）
  - aiofiles（異步文件操作）
  - slowapi（限流實現，基於客戶端 IP 限制請求頻次）
- 安裝指令：`pip install fastapi pydantic python-dotenv requests uvicorn sqlalchemy aiofiles slowapi`

環境設定：
- 日誌配置：
  - 開發環境（`ENABLE_DEBUG_LOGS=true`）：輸出 DEBUG 級別日誌（含執行時間等調試資訊），建議配合 `uvicorn --reload` 熱重載使用。
  - 生產環境：預設關閉 DEBUG 日誌（僅記錄 ERROR 級別），日誌存儲於 `./logs/app.log`。
- 限流配置（關鍵環境變數）：
  - `RATE_LIMIT`：速率限制規則（預設 `50/min`，格式：數量/時間單位，如 `100/hour`）。
  - `RATE_LIMIT_STORAGE`：限流存儲方式（預設 `memory`，生產環境需設定 `redis` 並配置 `REDIS_URL`）。
  - `REDIS_URL`：Redis 服務地址（生產環境專用，如 `redis://localhost:6379`）。

啟動命令：
- 開發環境（熱重載+DEBUG日誌）：
  `python shandu_api2.py --rate-limit 100/min`（臨時調整限流為每分鐘100次）
- 生產環境（關閉熱重載+Redis限流）：
  `uvicorn shandu_api2:app --host 0.0.0.0 --port 5002`（需在 .env 配置 `RATE_LIMIT_STORAGE=redis` 和 `REDIS_URL`）
"""

# 標準庫導入
import os
import asyncio
import logging  # 日誌模組
import time  # 用於時間測量
from pathlib import Path  # 處理文件路徑
from enum import Enum
from typing import List, Optional
from sqlalchemy import create_engine  # 資料庫引擎
# 移除：from concurrent.futures import ThreadPoolExecutor  # 多執行緒池（不再需要）
from sqlalchemy.pool import QueuePool  # 資料庫連接池

# 第三方庫導入
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import requests
import uvicorn
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# ----------------------------
# 全局配置
# ----------------------------
# 新增：調試日誌開關（從環境變數加載，預設關閉）
ENABLE_DEBUG_LOGS = os.getenv("ENABLE_DEBUG_LOGS", "false").lower() == "true"

# 日誌配置
LOG_PATH = "./logs/app.log"
Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)  # 自動創建日誌目錄

# 初始化日誌實例
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # 設置最低捕獲級別為 DEBUG（由處理器過濾）

# 配置文件日誌（始終記錄 ERROR 及以上級別）
file_handler = logging.FileHandler(LOG_PATH)
file_handler.setLevel(logging.ERROR)  # 上線環境只存儲 ERROR 級別
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 配置螢幕日誌（根據 ENABLE_DEBUG_LOGS 切換級別）
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG if ENABLE_DEBUG_LOGS else logging.ERROR)  # 開關控制級別
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 資料庫連接池（示例配置，實際需在資料庫操作中引用）
mysql_pool = QueuePool(
    lambda: create_engine('mysql+pymysql://user:password@host/db').raw_connection(),
    pool_size=5,
    max_overflow=10
)
postgresql_pool = QueuePool(
    lambda: create_engine('postgresql://user:password@host/db').raw_connection(),
    pool_size=5,
    max_overflow=10
)

# ----------------------------
# 載入 .env 環境變數
# ----------------------------
load_dotenv()

# ----------------------------
# AI 模型類型與配置模型定義
# ----------------------------
class AIModelType(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"

from pydantic_settings import BaseSettings, SettingsConfigDict

class AIModelConfig(BaseSettings):
    model_type: AIModelType = Field(default=AIModelType.OPENAI)
    api_base: str = Field(default="https://api.openai.com/v1")
    api_key: str = Field(default="")
    model_name: str = Field(default="gpt-4o-mini")
    model_config: str = "config.yaml"  # 新增配置文件路徑

    model_config = SettingsConfigDict(env_prefix="OPENAI_", env_file=".env")  # 自動讀取以OPENAI_開頭的環境變量

def get_config(mode: str = "openai") -> AIModelConfig:
    prefix = mode.upper() + "_"
    return AIModelConfig(
        model_type=AIModelType(os.getenv(f"{prefix}AI_MODEL_TYPE", "openai").lower()),
        api_base=os.getenv(f"{prefix}AI_API_BASE", "https://api.openai.com/v1"),
        api_key=os.getenv(f"{prefix}AI_API_KEY", ""),
        model_name=os.getenv(f"{prefix}AI_MODEL_NAME", "gpt-4o-mini")
    )

# ----------------------------
# 載入自定義模組
# ----------------------------
from shandu.config import config

# ----------------------------
# 初始化 FastAPI 應用
# ----------------------------
async def lifespan(app: FastAPI):
    try:
        yield  # 應用運行期間執行此處
    finally:
        # 應用關閉時清理資源（僅保留資料庫連接池）
        mysql_pool.dispose()  # 銷毀 MySQL 連接池
        postgresql_pool.dispose()  # 銷毀 PostgreSQL 連接池

app = FastAPI(lifespan=lifespan)  # 綁定生命週期函數

# 初始化全域 AI 配置
LLM_mode = "ollama"  # 可選: openai / ollama
current_config = get_config(LLM_mode)

# ----------------------------
# 定義請求參數模型（Pydantic）
# ----------------------------
class SearchRequest(BaseModel):
    query: str
    engines: Optional[List[str]] = ["Google", "DuckDuckGo", "Bing", "Wikipedia"]
    max_results: int = 10
    detailed: bool = False
    enable_scraping: bool = True

class ResearchRequest(BaseModel):
    query: str
    depth: int = 2
    breadth: int = 4
    strategy: str = "langgraph"

# ----------------------------
# WebSocket 實時通訊端點（多執行緒優化）
# ----------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_ip = websocket.client.host  # 獲取客戶端IP
    connect_start = time.time()
    await websocket.accept()
    if ENABLE_DEBUG_LOGS:
        logger.debug(f"WebSocket 連接建立（客戶端IP：{client_ip}），耗時：{time.time()-connect_start:.2f}s")

    try:
        while True:
            data_start = time.time()
            data = await get_webhook_data()
            if ENABLE_DEBUG_LOGS:
                logger.debug(f"客戶端{client_ip}獲取Webhook數據，耗時：{time.time()-data_start:.2f}s，數據大小：{len(json.dumps(data))}字節")

            send_start = time.time()
            await websocket.send_json(data)
            if ENABLE_DEBUG_LOGS:
                logger.debug(f"客戶端{client_ip}發送數據，耗時：{time.time()-send_start:.2f}s")

            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1)
            except asyncio.TimeoutError:
                pass
    except (asyncio.TimeoutError, WebSocketDisconnect):
        if ENABLE_DEBUG_LOGS:
            logger.debug(f"客戶端{client_ip}WebSocket連接正常關閉")
        await websocket.close()

# 新增異步文件操作庫導入
import aiofiles

async def get_webhook_data():
    """異步獲取 Webhook 數據（替代原有同步阻塞實現）"""
    async with aiofiles.open("webhook_data.txt", mode="a+") as f:
        await f.seek(0)  # 異步跳轉到文件開頭
        content = await f.read() or "預設 Webhook 數據"  # 異步讀取文件內容
    return {"message": content}

# ----------------------------
# API 路由實作（異步處理）
# ----------------------------
"""
限流配置：
- 測試環境（預設）：使用內存存儲（無需額外配置，直接啓動即可）
- 生產環境：需設定 `RATE_LIMIT_STORAGE=redis` 並配置 `REDIS_URL` 環境變數
- 速率限制：生產環境建議每分鐘50次（可通過 `RATE_LIMIT` 環境變數調整，如 `50/min` 或 `200/hour`）
"""  // 補充閉合三引號

@app.post("/aisearch")
@limiter.limit(RATE_LIMIT)  # 應用速率限制（預設每分鐘 10 次）
async def aisearch(request: Request, search_request: SearchRequest):  # 新增 Request 參數（限流需要）
    request_start = time.time()  # 記錄請求開始時間
    try:
        from shandu.search.ai_search import AISearcher
        searcher = AISearcher(max_results=search_request.max_results)  # 修正參數名稱（request → search_request）
        results = await searcher.search(
            query=search_request.query,  # 修正參數名稱（request → search_request）
            engines=search_request.engines,  # 修正參數名稱（request → search_request）
            detailed=search_request.detailed,  # 修正參數名稱（request → search_request）
            enable_scraping=search_request.enable_scraping  # 修正參數名稱（request → search_request）
        )
        if ENABLE_DEBUG_LOGS:
            logger.debug(f"/aisearch 處理完成，總耗時：{time.time()-request_start:.2f}s")  # 輸出總耗時
        return JSONResponse(content=results.to_dict())
    except ImportError as e:  # 具體異常優先捕獲
        error_msg = f"模組缺失: {str(e)}，請檢查 shandu 安裝"
        if ENABLE_DEBUG_LOGS:
            logger.debug(f"/aisearch 異常終止（模組缺失），已執行：{time.time()-request_start:.2f}s")
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": error_msg, "log_path": LOG_PATH}
        )
    except requests.exceptions.RequestException as e:  # 網路異常其次
        error_msg = f"網路請求失敗: {str(e)}"
        if ENABLE_DEBUG_LOGS:
            logger.debug(f"/aisearch 異常終止（網路錯誤），已執行：{time.time()-request_start:.2f}s")
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=503,
            content={"detail": error_msg, "log_path": LOG_PATH}
        )
    except Exception as e:  # 最後捕獲通用異常
        error_msg = f"未知錯誤: {str(e)}，請檢查日誌"
        if ENABLE_DEBUG_LOGS:
            logger.debug(f"/aisearch 異常終止（未知錯誤），已執行：{time.time()-request_start:.2f}s")
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": error_msg, "log_path": LOG_PATH}
        )

@app.post("/search")
async def search(request: SearchRequest):
    try:
        from shandu.search.search import UnifiedSearcher
        searcher = UnifiedSearcher(max_results=request.max_results)
        results = await searcher.search(
            query=request.query,
            engines=request.engines
        )
        return JSONResponse(content=[r.to_dict() for r in results])
    except Exception as e:
        error_msg = f"搜尋失敗: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": error_msg, "log_path": LOG_PATH}
        )

@app.post("/research")
async def research(request: ResearchRequest):
    try:
        from shandu.research.researcher import DeepResearcher
        researcher = DeepResearcher(save_results=False)
        result = await researcher.research(
            query=request.query,
            strategy=request.strategy,
            depth=request.depth,
            breadth=request.breadth
        )
        return JSONResponse(content=result.to_dict())
    except Exception as e:
        error_msg = f"深度研究失敗: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": error_msg, "log_path": LOG_PATH}
        )

@app.post("/update_config")
async def update_config(config: AIModelConfig):
    global current_config
    current_config = config
    return {"message": "配置已更新", "config": current_config.model_dump()}

@app.get("/get_config")
async def get_current_config():
    return current_config.model_dump()

# ----------------------------
# 啟動伺服器
# ----------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5002, reload=True)


async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """自定義 429 錯誤響應"""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "請求過多，請稍後重試",
            "retry_after": 60,  # 與預設速率限制（100/minute）對應
            "rate_limit": RATE_LIMIT
        }
    )
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # 綁定異常處理

@app.post("/aisearch")
@limiter.limit(RATE_LIMIT)
async def aisearch(request: Request, search_request: SearchRequest):
    request_start = time.time()
    try:
        from shandu.search.ai_search import AISearcher
        searcher = AISearcher(max_results=search_request.max_results)
        results = await searcher.search(
            query=search_request.query,
            engines=search_request.engines,
            detailed=search_request.detailed,
            enable_scraping=search_request.enable_scraping
        )
        if ENABLE_DEBUG_LOGS:
            logger.debug(f"/aisearch 處理完成，總耗時：{time.time()-request_start:.2f}s，查詢：{search_request.query}")
        return JSONResponse(content=results.to_dict())
    except ImportError as e:
        error_msg = f"模塊缺失: {str(e)}，請檢查shandu安裝（可能缺少依賴：pip install shandu）"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": error_msg, "log_path": LOG_PATH})
    except requests.exceptions.ConnectionError as e:
        error_msg = f"網絡連接失敗: {str(e)}，請檢查代理配置（當前代理：{config.get('scraper', 'proxy')}）"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(status_code=503, content={"detail": error_msg, "log_path": LOG_PATH})
    except requests.exceptions.Timeout as e:
        error_msg = f"請求超時: {str(e)}，建議重試或增加超時時間（當前超時：{config.get('api', 'timeout', 30)}s）"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(status_code=408, content={"detail": error_msg, "log_path": LOG_PATH})
    except Exception as e:
        error_msg = f"未知錯誤: {str(e)}，錯誤詳情已記錄至{LOG_PATH}"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": error_msg, "log_path": LOG_PATH})

@app.post("/search")
async def search(request: SearchRequest):
    try:
        from shandu.search.search import UnifiedSearcher
        searcher = UnifiedSearcher(max_results=request.max_results)
        results = await searcher.search(
            query=request.query,
            engines=request.engines
        )
        return JSONResponse(content=[r.to_dict() for r in results])
    except Exception as e:
        error_msg = f"搜尋失敗: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": error_msg, "log_path": LOG_PATH}
        )

@app.post("/research")
async def research(request: ResearchRequest):
    try:
        from shandu.research.researcher import DeepResearcher
        researcher = DeepResearcher(save_results=False)
        result = await researcher.research(
            query=request.query,
            strategy=request.strategy,
            depth=request.depth,
            breadth=request.breadth
        )
        return JSONResponse(content=result.to_dict())
    except Exception as e:
        error_msg = f"深度研究失敗: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": error_msg, "log_path": LOG_PATH}
        )

@app.post("/update_config")
async def update_config(config: AIModelConfig):
    global current_config
    current_config = config
    return {"message": "配置已更新", "config": current_config.model_dump()}

@app.get("/get_config")
async def get_current_config():
    return current_config.model_dump()

# ----------------------------
# 啟動伺服器
# ----------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5002, reload=True)
