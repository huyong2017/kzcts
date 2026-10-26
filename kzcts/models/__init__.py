"""数据模型"""

from .task import TaskMetadata
from .detection import Detection, DetectionPage, BoundingBox, Position

__all__ = [
    "TaskMetadata",
    "Detection",
    "DetectionPage",
    "BoundingBox",
    "Position",
]
