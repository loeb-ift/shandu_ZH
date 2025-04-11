"""
包裝函數用於處理LangGraph節點中的非同步函數。
此模塊提供了對asyncio事件循環的線程安全處理。
"""
import asyncio
import threading
from typing import Callable, Any, Awaitable, TypeVar, Dict
from concurrent.futures import ThreadPoolExecutor

T = TypeVar('T')

# 每個線程的本地存儲，用於存儲事件循環
_thread_local = threading.local()
# 操作事件循環時的線程安全鎖
_loop_lock = threading.Lock()
# 追蹤每個線程的活動事件循環
_thread_loops: Dict[int, asyncio.AbstractEventLoop] = {}

def get_or_create_event_loop():
    """取得當前線程的事件循環，若不存在則創建一個新的。"""
    thread_id = threading.get_ident()
    
    # 首先檢查線程本地存儲，看是否已有循環
    if hasattr(_thread_local, 'loop'):
        # 確保循環仍然有效（未關閉）
        if not _thread_local.loop.is_closed():
            return _thread_local.loop
    
    # 嘗試取得當前事件循環
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            # 存儲在線程本地，以便下次更快訪問
            _thread_local.loop = loop
            with _loop_lock:
                _thread_loops[thread_id] = loop
            return loop
    except RuntimeError:
        # 此線程不存在事件循環，或已關閉
        pass
    
    # 需要創建一個新的循環
    with _loop_lock:
        # 再次檢查此線程是否有有效的循環
        if thread_id in _thread_loops and not _thread_loops[thread_id].is_closed():
            _thread_local.loop = _thread_loops[thread_id]
            return _thread_loops[thread_id]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _thread_local.loop = loop
        _thread_loops[thread_id] = loop
        return loop

def run_async_in_new_loop(async_fn, *args, **kwargs):
    """在當前線程的新事件循環中運行非同步函數。"""
    loop = get_or_create_event_loop()
    try:
        return loop.run_until_complete(async_fn(*args, **kwargs))
    except Exception as e:

        raise e
    
def create_node_wrapper(async_fn: Callable[..., Awaitable[T]]) -> Callable[..., T]:
    """
    創建一個包裝器，安全地執行非同步函數，確保在不同線程場景下正確處理事件循環。
    """
    def wrapped_function(*args, **kwargs):
        # 使用可靠的get_or_create_event_loop函數
        loop = get_or_create_event_loop()

        if loop.is_running():
            # 我們處於正在運行的事件循環中 - 在ThreadPoolExecutor中創建一個任務
            # 這種方法可以防止事件循環嵌套
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_in_new_loop, async_fn, *args, **kwargs)
                return future.result()
        else:
            # 我們有一個事件循環，但它沒有運行，直接使用它
            try:
                return loop.run_until_complete(async_fn(*args, **kwargs))
            except Exception as e:
                # 若需要，記錄錯誤
                from ...utils.logger import log_error
                log_error(f"Error in async execution", e, 
                        context=f"Function: {async_fn.__name__}")
                # 重新拋出異常以保持原始行為
                raise
    
    return wrapped_function