"""实时数据模型"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class Position(BaseModel):
    """地理位置"""
    lat: float = Field(..., description="纬度")
    lng: float = Field(..., description="经度")
    altitude: Optional[float] = Field(None, description="高度（米）")


class Region(BaseModel):
    """扫描区域"""
    center_lat: float = Field(..., description="中心纬度")
    center_lng: float = Field(..., description="中心经度")
    width: float = Field(..., description="宽度（经度范围）")
    height: float = Field(..., description="高度（纬度范围）")
    name: str = ""


class BoundingBox(BaseModel):
    """目标边界框"""
    x: float = Field(..., description="左上角 x 坐标（像素）")
    y: float = Field(..., description="左上角 y 坐标（像素）")
    width: float = Field(..., description="宽度（像素）")
    height: float = Field(..., description="高度（像素）")


class InfraredFeatures(BaseModel):
    """红外特征"""
    heat_signature: float = Field(..., ge=0, le=1, description="热信号强度")
    spectral_characteristics: Dict[str, float] = Field(default_factory=dict, description="光谱特征")


class Task(BaseModel):
    """判读任务"""
    task_id: str
    task_name: str
    region: str  # 兼容旧代码，后续改为 Region 对象
    region_obj: Optional[Region] = None  # 新的区域对象
    sensor_type: str  # optical/infrared/radar
    status: str = "pending"  # pending/running/completed
    start_time: datetime
    end_time: Optional[datetime] = None
    scan_duration: float = 300.0  # 扫描时长（秒）
    frame_interval: float = 1.0  # 帧间隔（秒）
    priority: int = 1
    description: Optional[str] = None
    parent_task_id: Optional[str] = None  # 父任务ID（用于查证任务）
    target_id: Optional[str] = None  # 目标ID（用于查证任务）


class Frame(BaseModel):
    """帧数据"""
    frame_id: str
    task_id: str
    slice_id: int
    timestamp: datetime
    features: Dict[str, Any] = Field(default_factory=dict)


class Target(BaseModel):
    """目标（跨帧关联）"""
    target_id: str
    task_id: str
    target_type: str  # fighter/bomber/drone/helicopter/unknown
    classification: str = "unknown"  # military/civilian/unknown
    confidence: float = 0.0
    first_seen: datetime
    last_seen: datetime
    detection_count: int = 0


class Detection(BaseModel):
    """检测点"""
    detection_id: str
    frame_id: str
    target_id: Optional[str] = None
    task_id: str
    slice_id: int
    timestamp: datetime
    position: Position
    
    # 卫星检测的位置（有偏差）
    detected_position: Optional[Position] = None
    
    bounding_box: Optional[BoundingBox] = None
    confidence: float
    
    # 特征信息
    infrared_features: Optional[InfraredFeatures] = None
    optical_features: Optional[Dict[str, Any]] = None
    
    speed: Optional[float] = None  # km/h
    heading: Optional[float] = None  # 度，0-360
    
    # 匹配结果
    matched_aircraft_id: Optional[str] = None
    match_confidence: float = 0.0
    classification: str = "unknown"  # unknown/civilian/military/suspected_military
    target_type: Optional[str] = None
    
    # 是否隐藏目标
    is_hidden_target: bool = False


class SituationPoint(BaseModel):
    """态势点（空态势）"""
    point_id: str
    aircraft_id: str
    aircraft_type: str  # civilian/military/unknown
    target_type: str  # airliner/fighter/bomber/drone/helicopter/unknown
    timestamp: datetime
    position: Position
    speed: float  # km/h
    heading: float  # 度，0-360
    altitude: float  # 米
    callsign: Optional[str] = None  # 呼号
    classification: str = "unknown"  # known_civilian/known_military/unknown
    confidence: float = 0.95


class WSMessage(BaseModel):
    """WebSocket 消息"""
    type: str  # new_frame / target_update / task_status / situation_update
    task_id: Optional[str] = None
    data: Dict[str, Any]


class TaskStatus(BaseModel):
    """任务状态"""
    task_id: str
    status: str
    total_frames: int = 0
    total_targets: int = 0
    current_frame: int = 0


class Slice(BaseModel):
    """切片（一帧扫描数据）"""
    slice_id: str
    task_id: str
    frame_index: int
    timestamp: datetime
    scan_region: Region
    
    detections: List[Detection] = []
    
    # 统计信息
    total_detections: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    hidden_targets_count: int = 0


class TaskRecommendation(BaseModel):
    """任务推荐"""
    recommendation_id: str
    source_task_id: str
    source_detection_id: str
    
    # 目标信息
    target_id: str
    target_classification: str  # suspected_military
    target_confidence: float
    
    # 预测轨迹
    predicted_trajectory: List[Position]
    prediction_duration: float  # 预测时长（秒）
    
    # 推荐扫描区域
    recommended_region: Region
    recommended_sensor: str = "optical"
    
    # 推荐信息
    reason: str
    priority: int = 1
    timestamp: datetime
    
    # 状态
    status: str = "pending"  # pending/accepted/rejected/expired
