"""后台数据服务工具"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import random

from kzcts.models import TaskMetadata, Detection, DetectionPage, BoundingBox, Position


# 模拟任务数据
MOCK_TASKS: Dict[str, TaskMetadata] = {
    "TASK-001": TaskMetadata(
        task_id="TASK-001",
        task_name="东海区域光学扫描",
        region="东海海域",
        sensor_type="optical",
        start_time=datetime.now() - timedelta(hours=6),
        end_time=datetime.now(),
        status="running",
        priority=4,
        description="对东海指定区域进行光学卫星扫描，监测异常活动"
    ),
    "TASK-002": TaskMetadata(
        task_id="TASK-002",
        task_name="南海红外监测",
        region="南海岛礁",
        sensor_type="infrared",
        start_time=datetime.now() - timedelta(hours=12),
        status="running",
        priority=5,
        description="夜间红外监测，重点关注舰载机活动"
    ),
    "TASK-003": TaskMetadata(
        task_id="TASK-003",
        task_name="边境雷达扫描",
        region="西南边境",
        sensor_type="radar",
        start_time=datetime.now() - timedelta(days=1),
        end_time=datetime.now() - timedelta(hours=12),
        status="completed",
        priority=3,
        description="常规雷达扫描任务"
    ),
}


# 模拟检测数据生成器
def _generate_mock_detections(task_id: str, count: int = 50) -> List[Detection]:
    """生成模拟检测记录"""
    
    task = MOCK_TASKS.get(task_id)
    if not task:
        return []
    
    detections = []
    base_time = task.start_time
    
    # 目标类型列表
    target_types = ["fighter", "bomber", "drone", "helicopter"]
    
    # 生成 3-5 个跟踪目标
    num_tracks = random.randint(3, 5)
    track_ids = [f"TGT-{i:03d}" for i in range(1, num_tracks + 1)]
    
    for i in range(count):
        frame_time = base_time + timedelta(seconds=i * 10)
        track_id = random.choice(track_ids) if random.random() > 0.2 else None
        
        # 模拟目标移动
        base_lat = 25.0 + random.uniform(-2, 2)
        base_lng = 120.0 + random.uniform(-2, 2)
        lat_offset = (i / count) * random.uniform(0.1, 0.5)
        lng_offset = (i / count) * random.uniform(0.1, 0.3)
        
        detection = Detection(
            frame_id=f"F-{task_id}-{i+1:04d}",
            task_id=task_id,
            timestamp=frame_time,
            target_id=track_id,
            target_type=random.choice(target_types),
            confidence=random.uniform(0.65, 0.98),
            bounding_box=BoundingBox(
                x=random.uniform(100, 800),
                y=random.uniform(100, 600),
                width=random.uniform(30, 80),
                height=random.uniform(20, 60)
            ),
            position=Position(
                lat=base_lat + lat_offset,
                lng=base_lng + lng_offset,
                altitude=random.uniform(5000, 12000) if random.random() > 0.3 else None
            ),
            speed=random.uniform(400, 1200) if random.random() > 0.4 else None,
            heading=random.uniform(0, 360) if random.random() > 0.3 else None,
            sensor_type=task.sensor_type,
            image_quality=random.uniform(0.6, 0.95)
        )
        detections.append(detection)
    
    return detections


# 缓存生成的检测数据
_detection_cache: Dict[str, List[Detection]] = {}


def get_task_meta(task_id: str) -> Optional[Dict[str, Any]]:
    """
    获取任务元数据
    
    Args:
        task_id: 任务ID
    
    Returns:
        任务元数据字典，不存在则返回 None
    """
    task = MOCK_TASKS.get(task_id)
    if task:
        return task.model_dump()
    return None


def get_detections(
    task_id: str,
    time_range: Optional[Dict[str, str]] = None,
    target_filter: Optional[Dict[str, Any]] = None,
    page: int = 1,
    page_size: int = 20
) -> Optional[Dict[str, Any]]:
    """
    获取逐帧检测记录（分页）
    
    Args:
        task_id: 任务ID
        time_range: 时间范围 {"start": "ISO时间", "end": "ISO时间"}
        target_filter: 目标过滤 {"target_type": "fighter", "min_confidence": 0.8}
        page: 页码，从 1 开始
        page_size: 每页大小
    
    Returns:
        分页检测结果字典
    """
    # 生成或获取缓存的检测数据
    if task_id not in _detection_cache:
        _detection_cache[task_id] = _generate_mock_detections(task_id, count=100)
    
    detections = _detection_cache[task_id]
    
    # 时间范围过滤
    if time_range:
        start = datetime.fromisoformat(time_range.get("start", "1970-01-01"))
        end = datetime.fromisoformat(time_range.get("end", "2099-12-31"))
        detections = [d for d in detections if start <= d.timestamp <= end]
    
    # 目标过滤
    if target_filter:
        if "target_type" in target_filter:
            detections = [d for d in detections if d.target_type == target_filter["target_type"]]
        if "min_confidence" in target_filter:
            detections = [d for d in detections if d.confidence >= target_filter["min_confidence"]]
        if "target_id" in target_filter:
            detections = [d for d in detections if d.target_id == target_filter["target_id"]]
    
    # 分页
    total = len(detections)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_detections = detections[start_idx:end_idx]
    
    result = DetectionPage(
        task_id=task_id,
        total=total,
        page=page,
        page_size=page_size,
        detections=page_detections
    )
    
    return result.model_dump()


def list_available_tasks() -> List[Dict[str, Any]]:
    """
    列出所有可用的模拟任务
    
    Returns:
        任务列表
    """
    return [task.model_dump() for task in MOCK_TASKS.values()]
