"""目标识别和任务推荐系统"""

import asyncio
import math
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import uuid

from .models import Detection, SituationPoint, Position, Region, TaskRecommendation, Task
from .data_store import store
from .ws_manager import ws_manager


class TargetAnalyzer:
    """目标分析器"""
    
    def __init__(self):
        self.suspected_targets: Dict[str, Detection] = {}  # detection_id -> detection
        self.recommendations: Dict[str, TaskRecommendation] = {}  # recommendation_id -> recommendation
        
    async def analyze_detection(self, detection: Detection):
        """分析检测点，识别疑似军机"""
        # 检查是否为疑似军机
        if detection.classification == "suspected_military":
            print(f"[ANALYZE] 发现疑似军机: {detection.detection_id}")
            
            # 记录疑似目标
            self.suspected_targets[detection.detection_id] = detection
            
            # 生成任务推荐
            recommendation = await self._generate_recommendation(detection)
            
            if recommendation:
                self.recommendations[recommendation.recommendation_id] = recommendation
                
                # 通过 WebSocket 推送推荐
                await ws_manager.broadcast_recommendation(recommendation)
                
                print(f"[RECOMMEND] 生成任务推荐: {recommendation.recommendation_id}")
    
    async def _generate_recommendation(self, detection: Detection) -> Optional[TaskRecommendation]:
        """生成任务推荐"""
        # 预测未来60秒轨迹
        predicted_trajectory = self._predict_trajectory(detection, duration=60)
        
        if not predicted_trajectory:
            return None
        
        # 计算推荐扫描区域
        recommended_region = self._calculate_scan_region(predicted_trajectory)
        
        # 生成推荐原因
        reason = self._generate_reason(detection)
        
        recommendation_id = f"REC-{uuid.uuid4().hex[:6]}"
        
        return TaskRecommendation(
            recommendation_id=recommendation_id,
            source_task_id=detection.task_id,
            source_detection_id=detection.detection_id,
            target_id=detection.detection_id,
            target_classification=detection.classification,
            target_confidence=detection.confidence,
            predicted_trajectory=predicted_trajectory,
            prediction_duration=60.0,
            recommended_region=recommended_region,
            recommended_sensor="optical",
            reason=reason,
            priority=1,
            timestamp=datetime.now(),
            status="pending"
        )
    
    def _predict_trajectory(self, detection: Detection, duration: float = 60) -> List[Position]:
        """预测目标未来轨迹"""
        if not detection.speed or not detection.heading:
            return []
        
        trajectory = []
        current_lat = detection.detected_position.lat if detection.detected_position else detection.position.lat
        current_lng = detection.detected_position.lng if detection.detected_position else detection.position.lng
        current_alt = detection.detected_position.altitude if detection.detected_position else detection.position.altitude
        
        # 每秒预测一个点
        for t in range(int(duration)):
            # 速度转换为度/秒（1度约111km）
            speed_deg_per_sec = (detection.speed / 3600) / 111.0
            
            # 计算位置变化
            heading_rad = math.radians(detection.heading)
            delta_lat = speed_deg_per_sec * math.cos(heading_rad)
            delta_lng = speed_deg_per_sec * math.sin(heading_rad)
            
            # 更新位置
            current_lat += delta_lat
            current_lng += delta_lng
            
            # 添加随机扰动（模拟真实飞行）
            current_lat += (random.random() - 0.5) * 0.001
            current_lng += (random.random() - 0.5) * 0.001
            
            trajectory.append(Position(
                lat=current_lat,
                lng=current_lng,
                altitude=current_alt
            ))
        
        return trajectory
    
    def _calculate_scan_region(self, trajectory: List[Position]) -> Region:
        """计算覆盖轨迹的扫描区域（载荷扫描幅宽固定）"""
        if not trajectory:
            return Region(center_lat=35.0, center_lng=110.0, width=0.5, height=0.5)
        
        # 计算轨迹的边界
        min_lat = min(p.lat for p in trajectory)
        max_lat = max(p.lat for p in trajectory)
        min_lng = min(p.lng for p in trajectory)
        max_lng = max(p.lng for p in trajectory)
        
        # 中心点覆盖轨迹中点，尺寸固定为扫描幅宽
        center_lat = (min_lat + max_lat) / 2
        center_lng = (min_lng + max_lng) / 2
        
        return Region(
            center_lat=center_lat,
            center_lng=center_lng,
            width=0.5,
            height=0.5,
            name="推荐扫描区域"
        )
    
    def _generate_reason(self, detection: Detection) -> str:
        """生成推荐原因"""
        reasons = []
        
        if detection.classification == "suspected_military":
            reasons.append("红外特征显示疑似军机")
        
        if detection.infrared_features and detection.infrared_features.heat_signature > 0.8:
            reasons.append(f"热信号强度高 ({detection.infrared_features.heat_signature:.2f})")
        
        if detection.speed and detection.speed > 1000:
            reasons.append(f"高速飞行 ({detection.speed:.0f} km/h)")
        
        if not detection.matched_aircraft_id:
            reasons.append("未在态势系统中匹配到已知目标")
        
        return "；".join(reasons) if reasons else "需要进一步查证"
    
    def get_recommendations(self) -> List[TaskRecommendation]:
        """获取所有推荐"""
        return list(self.recommendations.values())
    
    def get_recommendation(self, recommendation_id: str) -> Optional[TaskRecommendation]:
        """获取指定推荐"""
        return self.recommendations.get(recommendation_id)
    
    def accept_recommendation(self, recommendation_id: str) -> Optional[Task]:
        """接受推荐，创建查证任务"""
        recommendation = self.recommendations.get(recommendation_id)
        if not recommendation:
            return None
        
        # 更新推荐状态
        recommendation.status = "accepted"
        
        # 创建查证任务
        task_id = f"TASK-{uuid.uuid4().hex[:6].upper()}"
        
        # 格式化区域字符串
        region_str = f"{recommendation.recommended_region.center_lat},{recommendation.recommended_region.center_lng},{recommendation.recommended_region.width},{recommendation.recommended_region.height}"
        
        task = Task(
            task_id=task_id,
            task_name=f"查证任务-{recommendation.target_classification}",
            region=region_str,
            region_obj=recommendation.recommended_region,
            sensor_type=recommendation.recommended_sensor,
            status="pending",
            start_time=datetime.now(),
            scan_duration=120.0,  # 查证任务扫描2分钟
            frame_interval=1.0,
            priority=recommendation.priority,
            description=recommendation.reason,
            parent_task_id=recommendation.source_task_id,
            target_id=recommendation.target_id
        )
        
        store.save_task(task)
        
        print(f"[TASK] 创建查证任务: {task_id} (来源推荐: {recommendation_id})")
        
        return task


# 全局目标分析器实例
target_analyzer = TargetAnalyzer()
