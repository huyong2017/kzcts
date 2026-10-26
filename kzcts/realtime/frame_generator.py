"""任务帧生成器 - 为任务生成逐帧检测数据"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .models import Task, Frame, Target, Detection, Position, BoundingBox
from .data_store import store


class TaskFrameGenerator:
    """任务帧生成器"""
    
    def __init__(self):
        # task_id -> asyncio.Task
        self.generators: Dict[str, asyncio.Task] = {}
        
        # task_id -> List[Target] (任务的目标列表)
        self.task_targets: Dict[str, List[Target]] = {}
    
    async def start_task(self, task: Task):
        """启动任务帧生成"""
        if task.task_id in self.generators:
            return
        
        # 初始化任务目标
        self._init_task_targets(task)
        
        # 启动生成任务
        gen_task = asyncio.create_task(self._generate_loop(task))
        self.generators[task.task_id] = gen_task
        
        # 更新任务状态
        store.update_task_status(task.task_id, "running")
    
    async def stop_task(self, task_id: str):
        """停止任务帧生成"""
        if task_id in self.generators:
            self.generators[task_id].cancel()
            try:
                await self.generators[task_id]
            except asyncio.CancelledError:
                pass
            del self.generators[task_id]
        
        store.update_task_status(task_id, "completed")
    
    def _init_task_targets(self, task: Task):
        """初始化任务目标"""
        num_targets = random.randint(3, 5)
        targets = []
        
        for i in range(num_targets):
            target_id = f"TGT-{task.task_id}-{i+1:03d}"
            
            # 根据传感器类型决定目标类型分布
            if task.sensor_type == "optical":
                target_type = random.choice(["fighter", "bomber", "drone", "helicopter"])
            elif task.sensor_type == "infrared":
                target_type = random.choice(["fighter", "bomber", "helicopter"])
            else:  # radar
                target_type = random.choice(["fighter", "bomber", "drone"])
            
            # 随机分类
            classification = random.choice(["military", "military", "unknown"])
            
            target = Target(
                target_id=target_id,
                task_id=task.task_id,
                target_type=target_type,
                classification=classification,
                confidence=random.uniform(0.75, 0.95),
                first_seen=datetime.now(),
                last_seen=datetime.now(),
                detection_count=0
            )
            
            targets.append(target)
            store.save_target(target)
        
        self.task_targets[task.task_id] = targets
    
    async def _generate_loop(self, task: Task):
        """帧生成循环"""
        frame_count = 0
        
        try:
            while task.status == "running":
                frame_count += 1
                frame_id = f"F-{task.task_id}-{frame_count:04d}"
                
                # 生成帧
                frame = self._generate_frame(task, frame_id, frame_count)
                store.save_frame(frame)
                
                # 生成检测点
                detections = self._generate_detections(task, frame)
                
                # 更新目标
                for detection in detections:
                    if detection.target_id:
                        target = store.get_target(detection.target_id)
                        if target:
                            target.last_seen = detection.timestamp
                            target.detection_count += 1
                            store.save_target(target)
                
                # 推送消息（通过 WebSocket 管理器）
                from .ws_manager import ws_manager
                await ws_manager.broadcast_frame(task.task_id, frame, detections)
                
                # 等待下一帧
                await asyncio.sleep(task.frame_interval)
        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"任务 {task.task_id} 帧生成错误: {e}")
        finally:
            store.update_task_status(task.task_id, "completed")
    
    def _generate_frame(self, task: Task, frame_id: str, slice_id: int) -> Frame:
        """生成帧数据"""
        features = self._generate_features(task.sensor_type)
        
        return Frame(
            frame_id=frame_id,
            task_id=task.task_id,
            slice_id=slice_id,
            timestamp=datetime.now(),
            features=features
        )
    
    def _generate_features(self, sensor_type: str) -> Dict:
        """生成帧特征"""
        if sensor_type == "optical":
            return {
                "image_quality": random.uniform(0.7, 0.95),
                "brightness": random.uniform(0.5, 0.9),
                "contrast": random.uniform(0.5, 0.8),
            }
        elif sensor_type == "infrared":
            return {
                "infrared_intensity": random.uniform(0.6, 0.95),
                "temperature_kelvin": random.uniform(280, 350),
                "background_clutter": random.uniform(0.1, 0.3),
            }
        else:  # radar
            return {
                "radar_cross_section": random.uniform(5, 20),
                "doppler_shift": random.uniform(800, 1500),
                "signal_to_noise_ratio": random.uniform(15, 25),
            }
    
    def _generate_detections(self, task: Task, frame: Frame) -> List[Detection]:
        """生成检测点"""
        detections = []
        targets = self.task_targets.get(task.task_id, [])
        
        # 每个目标有 80% 概率被检测到
        for target in targets:
            if random.random() < 0.8:
                detection = self._generate_detection(task, frame, target)
                detections.append(detection)
                store.save_detection(detection)
        
        return detections
    
    def _generate_detection(
        self,
        task: Task,
        frame: Frame,
        target: Target
    ) -> Detection:
        """生成单个检测点"""
        # 基于目标上次位置生成新位置（模拟移动）
        target_detections = store.get_target_detections(target.target_id)
        
        if target_detections:
            # 基于上次位置偏移
            last_pos = target_detections[-1].position
            lat = last_pos.lat + random.uniform(-0.01, 0.01)
            lng = last_pos.lng + random.uniform(-0.01, 0.01)
            altitude = (last_pos.altitude or 8000) + random.uniform(-200, 200)
        else:
            # 首次出现，随机位置
            lat = random.uniform(20, 40)
            lng = random.uniform(100, 130)
            altitude = random.uniform(5000, 12000)
        
        position = Position(
            lat=lat,
            lng=lng,
            altitude=max(1000, min(15000, altitude))
        )
        
        # 生成边界框
        bounding_box = BoundingBox(
            x=random.uniform(100, 800),
            y=random.uniform(100, 600),
            width=random.uniform(30, 80),
            height=random.uniform(20, 60)
        )
        
        # 速度和航向
        speed = random.uniform(400, 1200) if random.random() > 0.3 else None
        heading = random.uniform(0, 360) if random.random() > 0.3 else None
        
        return Detection(
            detection_id=f"D-{uuid.uuid4().hex[:8]}",
            frame_id=frame.frame_id,
            target_id=target.target_id,
            task_id=task.task_id,
            slice_id=frame.slice_id,
            timestamp=frame.timestamp,
            position=position,
            bounding_box=bounding_box,
            confidence=random.uniform(0.70, 0.98),
            speed=speed,
            heading=heading
        )


# 全局帧生成器实例
frame_generator = TaskFrameGenerator()
