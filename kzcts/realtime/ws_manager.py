"""WebSocket 连接管理器"""

from typing import Dict, List, Set
from fastapi import WebSocket
import asyncio
import json

from .models import Frame, Detection, SituationPoint
from .data_store import store


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # task_id -> Set[WebSocket]
        self.task_connections: Dict[str, Set[WebSocket]] = {}
        
        # 态势订阅者
        self.situation_connections: Set[WebSocket] = set()
    
    # ========== 任务 WebSocket ==========
    
    async def connect_task(self, task_id: str, websocket: WebSocket):
        """连接到任务"""
        await websocket.accept()
        
        if task_id not in self.task_connections:
            self.task_connections[task_id] = set()
        
        self.task_connections[task_id].add(websocket)
        
        # 发送历史数据（最近 10 帧）
        await self._send_task_history(task_id, websocket)
    
    def disconnect_task(self, task_id: str, websocket: WebSocket):
        """断开任务连接"""
        if task_id in self.task_connections:
            self.task_connections[task_id].discard(websocket)
            if not self.task_connections[task_id]:
                del self.task_connections[task_id]
    
    async def broadcast_frame(self, task_id: str, frame: Frame, detections: List[Detection]):
        """广播新帧到所有订阅者"""
        if task_id not in self.task_connections:
            return
        
        message = {
            "type": "new_frame",
            "task_id": task_id,
            "data": {
                "frame_id": frame.frame_id,
                "slice_id": frame.slice_id,
                "timestamp": frame.timestamp.isoformat(),
                "features": frame.features,
                "detections": [d.model_dump() for d in detections]
            }
        }
        
        await self._broadcast(task_id, message)
    
    async def broadcast_new_slice(self, task_id: str, slice_data):
        """广播新切片到所有订阅者"""
        if task_id not in self.task_connections:
            return
        
        # 手动序列化，处理 datetime 和嵌套对象
        detections_data = []
        for d in slice_data.detections:
            det_dict = d.model_dump()
            # 转换 datetime
            if 'timestamp' in det_dict and hasattr(det_dict['timestamp'], 'isoformat'):
                det_dict['timestamp'] = det_dict['timestamp'].isoformat()
            # 转换 Position 对象
            if 'position' in det_dict and hasattr(det_dict['position'], 'model_dump'):
                det_dict['position'] = det_dict['position'].model_dump()
            if 'detected_position' in det_dict and det_dict['detected_position'] and hasattr(det_dict['detected_position'], 'model_dump'):
                det_dict['detected_position'] = det_dict['detected_position'].model_dump()
            # 转换 InfraredFeatures 对象
            if 'infrared_features' in det_dict and det_dict['infrared_features'] and hasattr(det_dict['infrared_features'], 'model_dump'):
                det_dict['infrared_features'] = det_dict['infrared_features'].model_dump()
            detections_data.append(det_dict)
        
        message = {
            "type": "new_slice",
            "task_id": task_id,
            "data": {
                "slice_id": slice_data.slice_id,
                "task_id": slice_data.task_id,
                "frame_index": slice_data.frame_index,
                "timestamp": slice_data.timestamp.isoformat(),
                "scan_region": slice_data.scan_region.model_dump(),
                "detections": detections_data,
                "total_detections": slice_data.total_detections,
                "matched_count": slice_data.matched_count,
                "unmatched_count": slice_data.unmatched_count,
                "hidden_targets_count": slice_data.hidden_targets_count
            }
        }
        
        await self._broadcast(task_id, message)
    
    async def broadcast_target_update(self, task_id: str, target_id: str):
        """广播目标更新"""
        target = store.get_target(target_id)
        if not target:
            return
        
        message = {
            "type": "target_update",
            "task_id": task_id,
            "data": target.model_dump()
        }
        
        await self._broadcast(task_id, message)
    
    async def broadcast_task_status(self, task_id: str, status: str):
        """广播任务状态变更"""
        task = store.get_task(task_id)
        if not task:
            return
        
        frames = store.get_task_frames(task_id)
        targets = store.get_task_targets(task_id)
        
        message = {
            "type": "task_status",
            "task_id": task_id,
            "data": {
                "status": status,
                "total_frames": len(frames),
                "total_targets": len(targets),
                "current_frame": len(frames)
            }
        }
        
        await self._broadcast(task_id, message)
    
    async def _broadcast(self, task_id: str, message: dict):
        """广播消息到任务的所有订阅者"""
        if task_id not in self.task_connections:
            return
        
        disconnected = []
        for websocket in self.task_connections[task_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"WebSocket 发送错误: {e}")
                disconnected.append(websocket)
        
        # 清理断开的连接
        for ws in disconnected:
            self.disconnect_task(task_id, ws)
    
    async def _send_task_history(self, task_id: str, websocket: WebSocket):
        """发送任务历史数据"""
        frames = store.get_task_frames(task_id)
        targets = store.get_task_targets(task_id)
        
        # 发送最近 10 帧
        recent_frames = frames[-10:] if len(frames) > 10 else frames
        
        for frame in recent_frames:
            detections = store.get_frame_detections(frame.frame_id)
            message = {
                "type": "new_frame",
                "task_id": task_id,
                "data": {
                    "frame_id": frame.frame_id,
                    "slice_id": frame.slice_id,
                    "timestamp": frame.timestamp.isoformat(),
                    "features": frame.features,
                    "detections": [d.model_dump() for d in detections]
                }
            }
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"发送历史数据错误: {e}")
                break
    
    # ========== 态势 WebSocket ==========
    
    async def connect_situation(self, websocket: WebSocket):
        """连接到态势推送"""
        print(f"[WS] 准备接受 WebSocket 连接...")
        await websocket.accept()
        print(f"[WS] WebSocket 已接受")
        self.situation_connections.add(websocket)
        print(f"[WS] 态势 WebSocket 已连接，当前连接数: {len(self.situation_connections)}")
        
        # 发送最近 12 小时的态势数据
        await self._send_situation_history(websocket)
        print(f"[WS] 历史数据发送完成")
    
    def disconnect_situation(self, websocket: WebSocket):
        """断开态势连接"""
        self.situation_connections.discard(websocket)
        print(f"[WS] 态势 WebSocket 已断开，当前连接数: {len(self.situation_connections)}")
    
    async def broadcast_situation_update(self, points: List[SituationPoint]):
        """广播态势更新"""
        try:
            # 手动序列化，确保 datetime 被正确转换
            points_data = []
            for p in points:
                point_dict = p.model_dump()
                # 转换 datetime 为 ISO 格式字符串
                if 'timestamp' in point_dict and hasattr(point_dict['timestamp'], 'isoformat'):
                    point_dict['timestamp'] = point_dict['timestamp'].isoformat()
                points_data.append(point_dict)
            
            message = {
                "type": "situation_update",
                "data": {
                    "timestamp": points[0].timestamp.isoformat() if points else None,
                    "points": points_data
                }
            }
            
            print(f"[WS] 广播态势更新: {len(points)} 个点, {len(self.situation_connections)} 个连接")
            
            disconnected = []
            for websocket in self.situation_connections:
                try:
                    await websocket.send_json(message)
                    print(f"[WS] 成功发送消息到连接")
                except Exception as e:
                    print(f"[WS] 态势 WebSocket 发送错误: {e}")
                    disconnected.append(websocket)
            
            # 清理断开的连接
            for ws in disconnected:
                self.disconnect_situation(ws)
        except Exception as e:
            print(f"[WS] 态势广播序列化错误: {e}")
            import traceback
            traceback.print_exc()
    
    async def _send_situation_history(self, websocket: WebSocket):
        """发送历史态势数据（最近 12 小时）"""
        print(f"[WS] 准备发送历史态势数据...")
        # 获取所有飞机的最新位置
        latest_points = store.get_all_situation_points(hours=12)
        
        print(f"[WS] 获取到 {len(latest_points)} 个历史态势点")
        
        if latest_points:
            try:
                # 手动序列化，确保 datetime 被正确转换
                points_data = []
                for p in latest_points:
                    point_dict = p.model_dump()
                    # 转换 datetime 为 ISO 格式字符串
                    if 'timestamp' in point_dict and hasattr(point_dict['timestamp'], 'isoformat'):
                        point_dict['timestamp'] = point_dict['timestamp'].isoformat()
                    points_data.append(point_dict)
                
                message = {
                    "type": "situation_update",
                    "data": {
                        "timestamp": latest_points[0].timestamp.isoformat(),
                        "points": points_data,
                        "is_history": True
                    }
                }
                print(f"[WS] 发送历史数据: {len(points_data)} 个点")
                await websocket.send_json(message)
                print(f"[WS] 历史数据发送成功")
            except Exception as e:
                print(f"[WS] 发送历史态势数据错误: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[WS] 没有历史态势数据可发送")
    
    async def broadcast_recommendation(self, recommendation):
        """广播任务推荐到所有态势订阅者"""
        # 手动序列化
        rec_dict = recommendation.model_dump()
        
        # 转换 datetime
        if 'timestamp' in rec_dict and hasattr(rec_dict['timestamp'], 'isoformat'):
            rec_dict['timestamp'] = rec_dict['timestamp'].isoformat()
        
        # 转换 predicted_trajectory
        if 'predicted_trajectory' in rec_dict:
            trajectory_data = []
            for pos in recommendation.predicted_trajectory:
                if hasattr(pos, 'model_dump'):
                    trajectory_data.append(pos.model_dump())
                else:
                    trajectory_data.append(pos)
            rec_dict['predicted_trajectory'] = trajectory_data
        
        # 转换 recommended_region
        if 'recommended_region' in rec_dict and hasattr(rec_dict['recommended_region'], 'model_dump'):
            rec_dict['recommended_region'] = rec_dict['recommended_region'].model_dump()
        
        message = {
            "type": "task_recommendation",
            "data": rec_dict
        }
        
        # 广播给所有态势连接
        disconnected = []
        for websocket in self.situation_connections:
            try:
                await websocket.send_json(message)
                print(f"[WS] 发送任务推荐到连接")
            except Exception as e:
                print(f"[WS] 发送任务推荐错误: {e}")
                disconnected.append(websocket)
        
        # 清理断开的连接
        for ws in disconnected:
            self.situation_connections.discard(ws)


# 全局 WebSocket 管理器实例
ws_manager = ConnectionManager()
