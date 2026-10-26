"""实时数据 API 路由"""

from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from pydantic import BaseModel

from .models import Task, Region, SituationPoint, Slice
from .data_store import store
from .frame_generator import frame_generator
from .task_generator import task_generator
from .situation_generator import situation_generator
from .ws_manager import ws_manager


router = APIRouter()


# ========== 工具函数 ==========

def parse_region(region: str) -> Optional[Region]:
    """解析 "center_lat,center_lng,width,height" 区域字符串"""
    try:
        parts = [float(x.strip()) for x in region.split(",")]
        if len(parts) != 4:
            return None
        return Region(center_lat=parts[0], center_lng=parts[1], width=parts[2], height=parts[3])
    except ValueError:
        return None


def serialize_slice(s: Slice) -> dict:
    """手动序列化切片，确保 datetime/嵌套模型可 JSON 编码"""
    slice_dict = s.model_dump()
    if hasattr(slice_dict.get('timestamp'), 'isoformat'):
        slice_dict['timestamp'] = slice_dict['timestamp'].isoformat()
    if hasattr(slice_dict.get('scan_region'), 'model_dump'):
        slice_dict['scan_region'] = slice_dict['scan_region'].model_dump()
    
    detections_data = []
    for d in s.detections:
        det_dict = d.model_dump(mode="json")
        detections_data.append(det_dict)
    slice_dict['detections'] = detections_data
    return slice_dict


# ========== 请求/响应模型 ==========

class CreateTaskRequest(BaseModel):
    task_name: str
    region: str  # "lat,lng,width,height" 格式
    sensor_type: str  # optical/infrared
    scan_duration: float = 300.0  # 扫描时长（秒）
    frame_interval: float = 1.0
    priority: int = 1
    description: Optional[str] = None
    parent_task_id: Optional[str] = None  # 父任务ID（用于查证任务）
    target_id: Optional[str] = None  # 目标ID（用于查证任务）


class TaskResponse(BaseModel):
    task_id: str
    task_name: str
    region: str
    sensor_type: str
    status: str
    start_time: datetime
    end_time: Optional[datetime] = None
    scan_duration: float
    frame_interval: float
    priority: int
    description: Optional[str] = None
    parent_task_id: Optional[str] = None
    target_id: Optional[str] = None


# ========== REST API ==========

@router.get("/tasks", response_model=List[TaskResponse])
async def list_tasks():
    """列出所有任务"""
    tasks = store.list_tasks()
    return [TaskResponse(**t.model_dump()) for t in tasks]


@router.post("/tasks", response_model=TaskResponse)
async def create_task(request: CreateTaskRequest):
    """创建并启动任务"""
    import uuid
    
    task_id = f"TASK-{uuid.uuid4().hex[:6].upper()}"
    
    task = Task(
        task_id=task_id,
        task_name=request.task_name,
        region=request.region,
        sensor_type=request.sensor_type,
        status="pending",
        start_time=datetime.now(),
        scan_duration=request.scan_duration,
        frame_interval=request.frame_interval,
        priority=request.priority,
        description=request.description,
        parent_task_id=request.parent_task_id,
        target_id=request.target_id
    )
    
    # 解析区域字符串 "center_lat,center_lng,width,height"
    region_obj = parse_region(request.region)
    if region_obj:
        task.region_obj = region_obj
    
    store.save_task(task)
    
    # 自动启动任务
    await task_generator.start_task(task)
    
    return TaskResponse(**task.model_dump())


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """获取任务详情"""
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskResponse(**task.model_dump())


@router.post("/tasks/{task_id}/stop")
async def stop_task(task_id: str):
    """停止任务"""
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    await frame_generator.stop_task(task_id)
    await ws_manager.broadcast_task_status(task_id, "completed")
    
    return {"status": "ok", "message": "任务已停止"}


@router.get("/targets/{target_id}")
async def get_target(target_id: str):
    """获取目标详情"""
    target = store.get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")
    
    # 获取目标轨迹
    detections = store.get_target_detections(target_id)
    trajectory = [
        {
            "lat": d.position.lat,
            "lng": d.position.lng,
            "timestamp": d.timestamp.isoformat()
        }
        for d in detections
    ]
    
    result = target.model_dump()
    result["trajectory"] = trajectory
    
    return result


@router.get("/frames/{frame_id}")
async def get_frame(frame_id: str):
    """获取帧详情"""
    frame = store.get_frame(frame_id)
    if not frame:
        raise HTTPException(status_code=404, detail="帧不存在")
    
    detections = store.get_frame_detections(frame_id)
    
    result = frame.model_dump()
    result["detections"] = [d.model_dump() for d in detections]
    
    return result


@router.get("/tasks/{task_id}/slices")
async def get_task_slices(task_id: str):
    """获取任务的所有切片"""
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    slices = task_generator.task_slices.get(task_id, [])
    slices_data = [serialize_slice(s) for s in slices]
    
    return {"slices": slices_data, "count": len(slices_data)}


@router.get("/tasks/{task_id}/history")
async def get_task_history(task_id: str):
    """任务的时域对齐数据：扫描时间窗内的态势轨迹 + 扫描切片"""
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    start = task.start_time
    end = task.end_time or (task.start_time + timedelta(seconds=task.scan_duration))
    
    # 时间窗内的历史态势点（时域对齐），只保留经过任务区域附近的飞机
    region_obj = task.region_obj or parse_region(task.region)
    traj_by_aircraft = store.get_situation_points_in_range(start, end)
    trajectories = []
    for aircraft_id, pts in traj_by_aircraft.items():
        if region_obj:
            buf = 1.0
            near = any(
                abs(p.position.lat - region_obj.center_lat) <= region_obj.height / 2 + buf and
                abs(p.position.lng - region_obj.center_lng) <= region_obj.width / 2 + buf
                for p in pts
            )
            if not near:
                continue
        trajectories.append({
            "aircraft_id": aircraft_id,
            "aircraft_type": pts[0].aircraft_type,
            "classification": pts[0].classification,
            "points": [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "lat": p.position.lat,
                    "lng": p.position.lng,
                    "altitude": p.altitude,
                    "speed": p.speed,
                    "heading": p.heading,
                }
                for p in pts
            ],
        })
    
    slices = task_generator.task_slices.get(task_id, [])
    slices_data = [serialize_slice(s) for s in slices]
    
    return {
        "task": task.model_dump(mode="json"),
        "time_window": {"start": start.isoformat(), "end": end.isoformat()},
        "trajectories": trajectories,
        "slices": slices_data,
    }


@router.get("/recommendations")
async def get_recommendations():
    """获取所有任务推荐"""
    from .target_analyzer import target_analyzer
    
    recommendations = target_analyzer.get_recommendations()
    
    # 手动序列化
    recs_data = []
    for rec in recommendations:
        rec_dict = rec.model_dump()
        # 转换 datetime
        if 'timestamp' in rec_dict and hasattr(rec_dict['timestamp'], 'isoformat'):
            rec_dict['timestamp'] = rec_dict['timestamp'].isoformat()
        # 转换 predicted_trajectory
        if 'predicted_trajectory' in rec_dict:
            trajectory_data = []
            for pos in rec.predicted_trajectory:
                if hasattr(pos, 'model_dump'):
                    trajectory_data.append(pos.model_dump())
                else:
                    trajectory_data.append(pos)
            rec_dict['predicted_trajectory'] = trajectory_data
        # 转换 recommended_region
        if 'recommended_region' in rec_dict and hasattr(rec_dict['recommended_region'], 'model_dump'):
            rec_dict['recommended_region'] = rec_dict['recommended_region'].model_dump()
        recs_data.append(rec_dict)
    
    return {"recommendations": recs_data, "count": len(recs_data)}


@router.post("/recommendations/{recommendation_id}/accept")
async def accept_recommendation(recommendation_id: str):
    """接受推荐，创建查证任务"""
    from .target_analyzer import target_analyzer
    
    task = target_analyzer.accept_recommendation(recommendation_id)
    if not task:
        raise HTTPException(status_code=404, detail="推荐不存在")
    
    # 自动启动查证任务
    await task_generator.start_task(task)
    
    return {
        "status": "accepted",
        "task_id": task.task_id,
        "task": task.model_dump()
    }


@router.get("/situation/points")
async def get_situation_points(hours: float = Query(default=12.0, ge=0.1, le=24.0)):
    """获取态势点（最近 N 小时）"""
    points = store.get_all_situation_points(hours=hours)
    return {"points": [p.model_dump() for p in points], "count": len(points)}


@router.get("/situation/aircraft/{aircraft_id}")
async def get_aircraft_trajectory(
    aircraft_id: str,
    hours: float = Query(default=12.0, ge=0.1, le=24.0)
):
    """获取飞机轨迹"""
    points = store.get_aircraft_trajectory(aircraft_id, hours=hours)
    if not points:
        raise HTTPException(status_code=404, detail="飞机不存在")
    
    return {
        "aircraft_id": aircraft_id,
        "points": [p.model_dump() for p in points],
        "count": len(points)
    }


# ========== WebSocket 端点 ==========

@router.websocket("/ws/tasks/{task_id}")
async def websocket_task(websocket: WebSocket, task_id: str):
    """任务 WebSocket 端点"""
    task = store.get_task(task_id)
    if not task:
        await websocket.close(code=4004, reason="任务不存在")
        return
    
    await ws_manager.connect_task(task_id, websocket)
    
    try:
        while True:
            # 接收客户端消息（可用于控制）
            data = await websocket.receive_text()
            
            # 简单的心跳响应
            if data == "ping":
                await websocket.send_text("pong")
    
    except WebSocketDisconnect:
        ws_manager.disconnect_task(task_id, websocket)
    except Exception as e:
        print(f"任务 WebSocket 错误: {e}")
        ws_manager.disconnect_task(task_id, websocket)


@router.websocket("/ws/situation")
async def websocket_situation(websocket: WebSocket):
    """态势 WebSocket 端点"""
    print(f"[API] 收到态势 WebSocket 连接请求")
    try:
        await ws_manager.connect_situation(websocket)
        print(f"[API] 态势 WebSocket 已处理")
        
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            
            # 心跳响应
            if data == "ping":
                await websocket.send_text("pong")
    
    except WebSocketDisconnect:
        print(f"[API] 态势 WebSocket 断开连接")
        ws_manager.disconnect_situation(websocket)
    except Exception as e:
        print(f"[API] 态势 WebSocket 错误: {e}")
        import traceback
        traceback.print_exc()
        ws_manager.disconnect_situation(websocket)
