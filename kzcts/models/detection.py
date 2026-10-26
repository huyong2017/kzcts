"""检测记录模型"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """目标边界框"""
    x: float = Field(..., description="左上角 x 坐标（像素）")
    y: float = Field(..., description="左上角 y 坐标（像素）")
    width: float = Field(..., description="宽度（像素）")
    height: float = Field(..., description="高度（像素）")


class Position(BaseModel):
    """地理位置"""
    lat: float = Field(..., description="纬度")
    lng: float = Field(..., description="经度")
    altitude: Optional[float] = Field(None, description="高度（米）")


class Detection(BaseModel):
    """单帧检测记录"""
    
    frame_id: str = Field(..., description="帧ID")
    task_id: str = Field(..., description="所属任务ID")
    timestamp: datetime = Field(..., description="采集时间")
    
    # 目标信息
    target_id: Optional[str] = Field(None, description="跟踪ID（跨帧关联）")
    target_type: str = Field(..., description="目标类型：fighter/bomber/drone/helicopter/unknown")
    confidence: float = Field(..., ge=0, le=1, description="识别置信度")
    
    # 位置信息
    bounding_box: BoundingBox = Field(..., description="图像中的边界框")
    position: Optional[Position] = Field(None, description="地理坐标（如有）")
    
    # 附加属性
    speed: Optional[float] = Field(None, description="速度（km/h）")
    heading: Optional[float] = Field(None, description="航向（度，0-360）")
    
    # 传感器元数据
    sensor_type: str = Field(..., description="传感器类型")
    image_quality: Optional[float] = Field(None, ge=0, le=1, description="图像质量评分")


class DetectionPage(BaseModel):
    """分页检测结果"""
    
    task_id: str
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    detections: List[Detection] = Field(default_factory=list)
