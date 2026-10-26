"""内存数据存储"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import threading

from .models import Task, Frame, Target, Detection, SituationPoint


class DataStore:
    """线程安全的内存数据存储"""
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 任务存储
        self.tasks: Dict[str, Task] = {}
        
        # 帧存储: task_id -> List[Frame]
        self.frames: Dict[str, List[Frame]] = defaultdict(list)
        
        # 目标存储: target_id -> Target
        self.targets: Dict[str, Target] = {}
        
        # 检测点存储: frame_id -> List[Detection]
        self.detections: Dict[str, List[Detection]] = defaultdict(list)
        
        # 目标检测点索引: target_id -> List[Detection]
        self.target_detections: Dict[str, List[Detection]] = defaultdict(list)
        
        # 态势点存储: aircraft_id -> List[SituationPoint] (按时间排序)
        self.situation_points: Dict[str, List[SituationPoint]] = defaultdict(list)
        
        # 态势点时间索引: 用于清理超过 12 小时的数据
        self.situation_cleanup_time: datetime = datetime.now()
    
    # ========== 任务操作 ==========
    
    def save_task(self, task: Task) -> None:
        """保存任务"""
        with self._lock:
            self.tasks[task.task_id] = task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        with self._lock:
            return self.tasks.get(task_id)
    
    def list_tasks(self) -> List[Task]:
        """列出所有任务"""
        with self._lock:
            return list(self.tasks.values())
    
    def update_task_status(self, task_id: str, status: str) -> None:
        """更新任务状态"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = status
                if status == "completed":
                    self.tasks[task_id].end_time = datetime.now()
    
    # ========== 帧操作 ==========
    
    def save_frame(self, frame: Frame) -> None:
        """保存帧"""
        with self._lock:
            self.frames[frame.task_id].append(frame)
    
    def get_frame(self, frame_id: str) -> Optional[Frame]:
        """获取帧"""
        with self._lock:
            for frames in self.frames.values():
                for frame in frames:
                    if frame.frame_id == frame_id:
                        return frame
            return None
    
    def get_task_frames(self, task_id: str) -> List[Frame]:
        """获取任务的所有帧"""
        with self._lock:
            return self.frames.get(task_id, [])
    
    # ========== 目标操作 ==========
    
    def save_target(self, target: Target) -> None:
        """保存目标"""
        with self._lock:
            self.targets[target.target_id] = target
    
    def get_target(self, target_id: str) -> Optional[Target]:
        """获取目标"""
        with self._lock:
            return self.targets.get(target_id)
    
    def get_task_targets(self, task_id: str) -> List[Target]:
        """获取任务的所有目标"""
        with self._lock:
            return [t for t in self.targets.values() if t.task_id == task_id]
    
    def update_target(self, target_id: str, **kwargs) -> None:
        """更新目标属性"""
        with self._lock:
            if target_id in self.targets:
                target = self.targets[target_id]
                for key, value in kwargs.items():
                    if hasattr(target, key):
                        setattr(target, key, value)
    
    # ========== 检测点操作 ==========
    
    def save_detection(self, detection: Detection) -> None:
        """保存检测点"""
        with self._lock:
            self.detections[detection.frame_id].append(detection)
            if detection.target_id:
                self.target_detections[detection.target_id].append(detection)
    
    def get_frame_detections(self, frame_id: str) -> List[Detection]:
        """获取帧的所有检测点"""
        with self._lock:
            return self.detections.get(frame_id, [])
    
    def get_target_detections(self, target_id: str) -> List[Detection]:
        """获取目标的所有检测点（轨迹）"""
        with self._lock:
            return self.target_detections.get(target_id, [])
    
    # ========== 态势点操作 ==========
    
    def save_situation_point(self, point: SituationPoint) -> None:
        """保存态势点"""
        with self._lock:
            self.situation_points[point.aircraft_id].append(point)
            
            # 定期清理超过 12 小时的数据
            if datetime.now() - self.situation_cleanup_time > timedelta(minutes=5):
                self._cleanup_old_situation_points()
                self.situation_cleanup_time = datetime.now()
    
    def get_aircraft_trajectory(self, aircraft_id: str, hours: float = 12.0) -> List[SituationPoint]:
        """获取飞机轨迹（最近 N 小时）"""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            points = self.situation_points.get(aircraft_id, [])
            return [p for p in points if p.timestamp >= cutoff_time]
    
    def get_all_situation_points(self, hours: float = 12.0) -> List[SituationPoint]:
        """获取所有飞机的最新态势点"""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            latest_points = []
            
            for aircraft_id, points in self.situation_points.items():
                # 获取每架飞机的最新点
                recent_points = [p for p in points if p.timestamp >= cutoff_time]
                if recent_points:
                    latest_points.append(recent_points[-1])
            
            return latest_points
    
    def get_situation_points_in_range(self, start: datetime, end: datetime) -> Dict[str, List[SituationPoint]]:
        """获取指定时间窗口内所有飞机的态势点（时域对齐用）"""
        with self._lock:
            result = {}
            for aircraft_id, points in self.situation_points.items():
                window_points = [p for p in points if start <= p.timestamp <= end]
                if window_points:
                    result[aircraft_id] = window_points
            return result
    
    def _cleanup_old_situation_points(self) -> None:
        """清理超过 12 小时的态势点"""
        cutoff_time = datetime.now() - timedelta(hours=12)
        
        for aircraft_id in list(self.situation_points.keys()):
            points = self.situation_points[aircraft_id]
            # 保留最近的点
            self.situation_points[aircraft_id] = [
                p for p in points if p.timestamp >= cutoff_time
            ]
            # 如果没有点了，删除这个飞机的记录
            if not self.situation_points[aircraft_id]:
                del self.situation_points[aircraft_id]


# 全局数据存储实例
store = DataStore()
