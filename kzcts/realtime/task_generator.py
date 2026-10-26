"""任务生成器 - 模拟卫星扫描"""

import asyncio
import random
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid

from .models import Task, Slice, Detection, Position, Region, InfraredFeatures, SituationPoint
from .data_store import store
from .situation_generator import situation_generator


class TaskGenerator:
    """任务生成器"""
    
    def __init__(self):
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.task_slices: Dict[str, List[Slice]] = {}
        
    async def start_task(self, task: Task):
        """启动任务"""
        if task.task_id in self.running_tasks:
            return
        
        # 更新任务状态
        task.status = "running"
        store.save_task(task)
        
        # 创建异步任务
        asyncio_task = asyncio.create_task(self._scan_loop(task))
        self.running_tasks[task.task_id] = asyncio_task
        self.task_slices[task.task_id] = []
        
        print(f"[TASK] 任务启动: {task.task_id} ({task.task_name})")
    
    async def stop_task(self, task_id: str):
        """停止任务"""
        if task_id not in self.running_tasks:
            return
        
        # 取消异步任务
        asyncio_task = self.running_tasks[task_id]
        asyncio_task.cancel()
        
        try:
            await asyncio_task
        except asyncio.CancelledError:
            pass
        
        # 更新任务状态
        task = store.get_task(task_id)
        if task:
            task.status = "completed"
            task.end_time = datetime.now()
            store.save_task(task)
        
        del self.running_tasks[task_id]
        print(f"[TASK] 任务完成: {task_id}")
    
    async def _scan_loop(self, task: Task):
        """扫描循环"""
        try:
            frame_index = 0
            start_time = datetime.now()
            
            while True:
                # 检查是否超过扫描时长
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= task.scan_duration:
                    break
                
                # 生成一帧扫描数据
                slice_data = self._generate_slice(task, frame_index)
                
                # 保存切片
                self.task_slices[task.task_id].append(slice_data)
                for detection in slice_data.detections:
                    store.save_detection(detection)
                
                # 广播新切片
                from .ws_manager import ws_manager
                await ws_manager.broadcast_new_slice(task.task_id, slice_data)
                
                # 分析检测点，生成任务推荐
                from .target_analyzer import target_analyzer
                for detection in slice_data.detections:
                    await target_analyzer.analyze_detection(detection)
                
                frame_index += 1
                
                # 等待下一帧
                await asyncio.sleep(task.frame_interval)
            
            # 扫描完成
            task.status = "completed"
            task.end_time = datetime.now()
            store.save_task(task)
            
            print(f"[TASK] 任务扫描完成: {task.task_id}, 共 {frame_index} 帧")
            
        except asyncio.CancelledError:
            print(f"[TASK] 任务被取消: {task.task_id}")
            raise
    
    def _generate_slice(self, task: Task, frame_index: int) -> Slice:
        """生成一帧扫描数据"""
        # 解析区域
        region = self._parse_region(task.region)
        
        slice_id = f"SLICE-{uuid.uuid4().hex[:6]}"
        timestamp = datetime.now()
        
        # 生成检测点
        detections = []
        
        # 获取当前态势点
        situation_points = situation_generator.get_latest_points()
        
        # 1. 匹配态势系统中的飞机（70%概率被检测到）
        matched_count = 0
        for point in situation_points:
            if self._is_in_region(point.position, region):
                # 70% 概率被卫星检测到
                if random.random() < 0.7:
                    detection = self._create_detection_from_situation(
                        task.task_id, slice_id, frame_index, timestamp, point
                    )
                    detections.append(detection)
                    matched_count += 1
        
        # 2. 生成隐藏目标（2-5个）
        hidden_count = random.randint(2, 5)
        for i in range(hidden_count):
            detection = self._create_hidden_target_detection(
                task.task_id, slice_id, frame_index, timestamp, region
            )
            detections.append(detection)
        
        # 创建切片
        slice_data = Slice(
            slice_id=slice_id,
            task_id=task.task_id,
            frame_index=frame_index,
            timestamp=timestamp,
            scan_region=region,
            detections=detections,
            total_detections=len(detections),
            matched_count=matched_count,
            unmatched_count=len(detections) - matched_count,
            hidden_targets_count=hidden_count
        )
        
        return slice_data
    
    def _parse_region(self, region_str: str) -> Region:
        """解析区域字符串"""
        # 简单解析 "lat,lng,width,height" 格式
        try:
            parts = region_str.split(",")
            if len(parts) == 4:
                return Region(
                    center_lat=float(parts[0]),
                    center_lng=float(parts[1]),
                    width=float(parts[2]),
                    height=float(parts[3])
                )
        except:
            pass
        
        # 默认区域（中国中部）
        return Region(
            center_lat=35.0,
            center_lng=110.0,
            width=10.0,
            height=10.0,
            name="默认区域"
        )
    
    def _is_in_region(self, position: Position, region: Region) -> bool:
        """检查位置是否在区域内"""
        lat_diff = abs(position.lat - region.center_lat)
        lng_diff = abs(position.lng - region.center_lng)
        return lat_diff <= region.height / 2 and lng_diff <= region.width / 2
    
    def _create_detection_from_situation(
        self, task_id: str, slice_id: str, frame_index: int, 
        timestamp: datetime, point: SituationPoint
    ) -> Detection:
        """从态势点创建检测点（带坐标偏差）"""
        # 添加坐标偏差（±0.01-0.05度，约1-5公里）
        lat_offset = random.uniform(-0.05, 0.05)
        lng_offset = random.uniform(-0.05, 0.05)
        
        detected_position = Position(
            lat=point.position.lat + lat_offset,
            lng=point.position.lng + lng_offset,
            altitude=point.position.altitude
        )
        
        # 生成红外特征
        infrared_features = self._generate_infrared_features(point)
        
        # 匹配和分类
        matched_aircraft_id = point.aircraft_id
        match_confidence = random.uniform(0.7, 0.95)
        
        # 根据特征判断分类
        classification = point.aircraft_type
        if point.aircraft_type == "military" and random.random() < 0.3:
            classification = "suspected_military"  # 30% 概率标记为疑似军机
        
        detection_id = f"DET-{uuid.uuid4().hex[:8]}"
        
        return Detection(
            detection_id=detection_id,
            frame_id=slice_id,
            target_id=None,
            task_id=task_id,
            slice_id=frame_index,
            timestamp=timestamp,
            position=point.position,  # 实际位置
            detected_position=detected_position,  # 检测位置（有偏差）
            confidence=match_confidence,
            speed=point.speed,
            heading=point.heading,
            infrared_features=infrared_features,
            matched_aircraft_id=matched_aircraft_id,
            match_confidence=match_confidence,
            classification=classification,
            target_type=point.target_type,
            is_hidden_target=False
        )
    
    def _create_hidden_target_detection(
        self, task_id: str, slice_id: str, frame_index: int,
        timestamp: datetime, region: Region
    ) -> Detection:
        """创建隐藏目标检测点"""
        # 在区域内随机生成位置
        lat = region.center_lat + random.uniform(-region.height/2, region.height/2)
        lng = region.center_lng + random.uniform(-region.width/2, region.width/2)
        altitude = random.uniform(3000, 12000)
        
        detected_position = Position(lat=lat, lng=lng, altitude=altitude)
        
        # 生成红外特征（可能是军机特征）
        heat_signature = random.uniform(0.6, 1.0)
        infrared_features = InfraredFeatures(
            heat_signature=heat_signature,
            spectral_characteristics={
                "swir": random.uniform(0.5, 1.0),
                "mwir": random.uniform(0.5, 1.0)
            }
        )
        
        # 隐藏目标无法匹配到态势点
        classification = "unknown"
        if heat_signature > 0.8 and random.random() < 0.5:
            classification = "suspected_military"
        
        detection_id = f"DET-{uuid.uuid4().hex[:8]}"
        
        return Detection(
            detection_id=detection_id,
            frame_id=slice_id,
            target_id=None,
            task_id=task_id,
            slice_id=frame_index,
            timestamp=timestamp,
            position=detected_position,
            detected_position=detected_position,
            confidence=random.uniform(0.5, 0.8),
            speed=random.uniform(600, 1500),
            heading=random.uniform(0, 360),
            infrared_features=infrared_features,
            matched_aircraft_id=None,
            match_confidence=0.0,
            classification=classification,
            target_type=random.choice(["fighter", "bomber", "unknown"]),
            is_hidden_target=True
        )
    
    def _generate_infrared_features(self, point: SituationPoint) -> InfraredFeatures:
        """生成红外特征"""
        # 根据飞机类型生成不同的红外特征
        if point.aircraft_type == "military":
            heat_signature = random.uniform(0.7, 1.0)
        else:
            heat_signature = random.uniform(0.3, 0.7)
        
        return InfraredFeatures(
            heat_signature=heat_signature,
            spectral_characteristics={
                "swir": random.uniform(0.3, 1.0),
                "mwir": random.uniform(0.3, 1.0),
                "lwir": random.uniform(0.3, 1.0)
            }
        )


# 全局任务生成器实例
task_generator = TaskGenerator()
