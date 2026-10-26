"""FastAPI 服务"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kzcts.config import settings
from kzcts.realtime.api import router as realtime_router
from kzcts.realtime.situation_generator import situation_generator
from kzcts.realtime.ws_manager import ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("启动实时数据服务...")
    
    # 启动态势生成器
    await situation_generator.start()
    print("态势生成器已启动")
    
    # 启动态势广播任务
    broadcast_task = asyncio.create_task(broadcast_situation_loop())
    
    yield
    
    # 关闭时
    print("关闭实时数据服务...")
    broadcast_task.cancel()
    await situation_generator.stop()
    print("服务已关闭")


async def broadcast_situation_loop():
    """态势广播循环（每秒广播一次）"""
    print("[广播] 态势广播循环已启动")
    try:
        while True:
            # 获取最新态势点
            latest_points = situation_generator.get_latest_points()
            
            # 广播给所有订阅者
            if latest_points:
                try:
                    await ws_manager.broadcast_situation_update(latest_points)
                except Exception as e:
                    print(f"[广播] 态势广播错误: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[广播] 没有态势点可广播")
            
            # 等待 1 秒
            await asyncio.sleep(1.0)
    
    except asyncio.CancelledError:
        print("[广播] 态势广播循环已取消")
        pass
    except Exception as e:
        print(f"[广播] 态势广播循环错误: {e}")
        import traceback
        traceback.print_exc()


app = FastAPI(
    title="空中飞机判读智能助手 - 实时数据服务",
    description="提供实时任务数据推送和空态势信息",
    version="0.1.0",
    lifespan=lifespan
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(realtime_router, prefix="/api", tags=["实时数据"])


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "service": "kzcts-realtime",
        "situation_generator": "running" if situation_generator.running else "stopped"
    }


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "空中飞机判读智能助手 - 实时数据服务",
        "version": "0.1.0",
        "docs": "/docs",
        "websocket": {
            "task": "ws://localhost:8000/api/ws/tasks/{task_id}",
            "situation": "ws://localhost:8000/api/ws/situation"
        }
    }
