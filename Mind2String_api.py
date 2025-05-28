"""
Markdown 語句生成 API 服務
描述：本服務提供 API 接口，用於將 Markdown 標題層級與列表項組合成連貫語句（例如："父標題 子標題 列表項"）。

環境安裝與依賴：
- 前置環境：Python 3.12
- 安裝套件：執行 `pip install fastapi uvicorn` 安裝核心框架與服務運行工具

服務啓動：
- 運行指令：進入項目目錄後執行 `python Mind2String_api.py [--port 端口號]`（端口號可選，默認 8000）
- 示例：`python Mind2String_api.py --port 8080`  // 監聽 8080 端口
- 服務驗證：訪問 `http://localhost:端口號/docs` 查看 Swagger 文檔（如 `http://localhost:8080/docs`）

API 接口說明：
【接口 1】/process-markdown/text（POST）
- 功能：直接傳入 Markdown 文本，返回組合後的語句列表
- 請求方式：POST
- 請求頭：Content-Type: multipart/form-data
- 請求參數：
  - markdown_content（必填）：類型為 `str`，Markdown 文本內容（通過 Form Data 傳送）
- curl 示例：
  curl -X POST "http://localhost:8000/process-markdown/text" \
       -H "Content-Type: multipart/form-data" \
       -F "markdown_content=# 動物\n- 哺乳類\n  - 獅子"
- 響應格式（JSON）：
  {
    "code": 200,          // 狀態碼（200: 成功，400: 參數錯誤，500: 服務器錯誤）
    "message": "成功",     // 描述信息
    "data": ["動物 哺乳類 獅子"]  // 生成的語句列表
  }

【接口 2】/process-markdown/file（POST）
- 功能：上傳 .md 文件，返回組合後的語句列表
- 請求方式：POST
- 請求頭：Content-Type: multipart/form-data
- 請求參數：
  - file（必填）：類型為 `UploadFile`，上傳的 .md 文件（通過 Form Data 傳送）
- curl 示例：
  curl -X POST "http://localhost:8000/process-markdown/file" \
       -H "Content-Type: multipart/form-data" \
       -F "file=@/path/to/input.md"  // 替換為實際 .md 文件路徑
- 響應格式（JSON）：
  {
    "code": 200,
    "message": "成功",
    "data": ["父標題 子標題 列表項1", "父標題 子標題 列表項2"]
  }
"""

import argparse 
import logging  # 導入日誌模組
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel  # 導入 Pydantic 基礎模型
import uvicorn

# 新增：配置日誌格式（等級為 DEBUG，包含時間、等級、訊息）
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # 輸出到終端
)
logger = logging.getLogger(__name__)  # 創建日誌實例

def generate_strings_from_leaves(markdown_content):
    lines = markdown_content.splitlines()  # 將 Markdown 內容按行分割
    result = []  # 用於存儲生成的字串
    stack = []  # 用於跟蹤當前的標題層級

    for line in lines:
        logger.debug(f"Processing line: {line}")  # 替換 print 為 DEBUG 等級日誌
        try:  # 新增：捕獲單行處理異常
            if line.startswith('#'):
                level = line.count('#')  # 計算標題層級
                name = line[level:].strip()  # 獲取標題名稱
                logger.debug(f"Found header: {name} at level {level}")  # DEBUG 日誌
                if level > len(stack):  # 如果層級增加
                    stack.append(name)  # 將標題添加到堆疊
                else:
                    stack = stack[:level - 1] + [name]  # 更新堆疊
                logger.debug(f"Updated stack: {stack}")  # DEBUG 日誌
            elif line.strip().startswith(('-', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                item = line.strip().lstrip('- ').lstrip('1. ').lstrip('2. ').lstrip('3. ').lstrip('4. ').lstrip('5. ').lstrip('6. ').lstrip('7. ').lstrip('8. ').lstrip('9. ').strip()  # 獲取項目內容
                if stack and item:
                    generated_string = " ".join(stack + [item])
                    result.append(generated_string)
                    logger.debug(f"Generated string: {generated_string}")  # DEBUG 日誌
            elif line.strip() == '':
                continue
        except Exception as e:  # 捕獲單行處理異常
            logger.error(f"處理行 [{line}] 時發生異常: {str(e)}", exc_info=True)  # 記錄錯誤及堆疊
            continue  # 跳過異常行，繼續處理後續內容

    logger.debug(f"Final result: {result}")  # DEBUG 日誌
    return result  # 返回生成的字串列表





# 設定命令行參數解析
parser = argparse.ArgumentParser(description='Process a Markdown file to generate strings.')
parser.add_argument('--input', type=str, required=True, help='Path to the Markdown file')

# 解析命令行參數
args = parser.parse_args()

# 讀取 Markdown 檔案內容
try:
    with open(args.input, 'r', encoding='utf-8') as file:
        markdown_content = file.read()  # 讀取檔案內容
except FileNotFoundError:
    print(f'指定的文件 {args.input} 未找到，請檢查路徑。')
    exit(1)

# 調用函數並傳遞讀取的內容
result = generate_strings_from_leaves(markdown_content)

# 打印結果
if result:
    for string in result:
        print(string)  # 每行輸出一個字串
else:
    print("No strings generated.")  # 調試信息：未生成任何字串

# 新增：定義統一的 JSON 響應模型
class ApiResponse(BaseModel):
    code: int = 200  # 狀態碼（200: 成功，400: 參數錯誤等）
    message: str = "成功"  # 描述信息
    data: list[str] = []  # 實際數據（生成的語句列表）

# 初始化 FastAPI 應用
app = FastAPI(
    title="Markdown String Generator",
    description="API 用於將 Markdown 標題和列表項組合成語句",
    version="1.0.0"
)

# 配置 CORS 中間件（允許跨域請求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/process-markdown/text", response_model=ApiResponse, tags=["處理接口"])
async def process_markdown_text(markdown_content: str = Form(..., description="直接傳入的 Markdown 文本內容")):
    """通過文本內容處理 Markdown（返回 JSON 格式結果）"""
    if not markdown_content.strip():
        logger.warning("接收到空的 Markdown 文本內容")  # WARNING 等級日誌（參數異常）
        raise HTTPException(
            status_code=400,
            detail={"code": 400, "message": "Markdown 內容不能為空", "data": []}
        )
    try:  # 新增：捕獲函數調用異常
        result = generate_strings_from_leaves(markdown_content)
        logger.info("文本處理成功，生成 %d 條語句" % len(result))  # INFO 等級日誌（正常流程）
        return {"code": 200, "message": "成功", "data": result}
    except Exception as e:
        logger.error(f"文本處理發生異常: {str(e)}", exc_info=True)  # 記錄錯誤及堆疊
        raise HTTPException(
            status_code=500,
            detail={"code": 500, "message": "服務器內部錯誤", "data": []}
        )

@app.post("/process-markdown/file", response_model=ApiResponse, tags=["處理接口"])
async def process_markdown_file(file: UploadFile = File(..., description="上傳的 Markdown 文件")):
    """通過上傳文件處理 Markdown（返回 JSON 格式結果）"""
    if not file.filename.endswith(".md"):
        logger.warning(f"上傳文件格式錯誤：{file.filename}（非 .md 文件）")  # WARNING 日誌
        raise HTTPException(
            status_code=400,
            detail={"code": 400, "message": "僅支持 .md 格式的文件", "data": []}
        )
    try:
        content = await file.read()
        result = generate_strings_from_leaves(content.decode("utf-8"))
        logger.info(f"文件 {file.filename} 處理成功，生成 {len(result)} 條語句")  # INFO 日誌
        return {"code": 200, "message": "成功", "data": result}
    except UnicodeDecodeError as e:
        logger.error(f"文件 {file.filename} 解碼失敗（非 UTF-8 編碼）: {str(e)}")  # 編碼異常
        raise HTTPException(
            status_code=400,
            detail={"code": 400, "message": "文件編碼需為 UTF-8", "data": []}
        )
    except Exception as e:
        logger.error(f"文件 {file.filename} 處理發生異常: {str(e)}", exc_info=True)  # 通用異常
        raise HTTPException(
            status_code=500,
            detail={"code": 500, "message": "服務器內部錯誤", "data": []}
        )

if __name__ == "__main__":
    # 新增：解析命令行端口參數
    parser = argparse.ArgumentParser(description='Markdown String Generator API 服務啓動參數')
    parser.add_argument('--port', type=int, default=8000, help='監聽端口（默認 8000）')
    args = parser.parse_args()

    logger.info(f"Markdown String Generator API 服務啓動，監聽端口 {args.port}...")  # 顯示實際端口
    uvicorn.run("Mind2String_api:app", host="0.0.0.0", port=args.port, reload=True)  # 使用參數指定端口