"""任务元数据模型"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class TaskMetadata(BaseModel):
    """判读任务元数据"""
    
    task_id: str = Field(..., description="任务ID")
    task_name: str = Field(..., description="任务名称")
    region: str = Field(..., description="关注区域")
    sensor_type: str = Field(..., description="传感器类型：optical/infrared/radar")
    start_time: datetime = Field(..., description="任务开始时间")
    end_time: Optional[datetime] = Field(None, description="任务结束时间")
    status: str = Field(..., description="任务状态：pending/running/completed/failed")
    priority: int = Field(default=1, description="优先级：1-5，5最高")
    description: Optional[str] = Field(None, description="任务描述")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
