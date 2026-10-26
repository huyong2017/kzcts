"""测试后台数据工具"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from kzcts.tools import get_task_meta, get_detections, list_available_tasks


def test_list_tasks():
    """测试列出任务"""
    print("=" * 60)
    print("测试：列出可用任务")
    print("=" * 60)
    tasks = list_available_tasks()
    for task in tasks:
        print(f"  - {task['task_id']}: {task['task_name']} [{task['status']}]")
    print()


def test_get_task_meta():
    """测试获取任务元数据"""
    print("=" * 60)
    print("测试：获取任务元数据")
    print("=" * 60)
    
    task_id = "TASK-001"
    meta = get_task_meta(task_id)
    if meta:
        print(f"任务ID: {meta['task_id']}")
        print(f"任务名称: {meta['task_name']}")
        print(f"区域: {meta['region']}")
        print(f"传感器: {meta['sensor_type']}")
        print(f"状态: {meta['status']}")
        print(f"优先级: {meta['priority']}")
    else:
        print(f"任务 {task_id} 不存在")
    print()


def test_get_detections():
    """测试获取检测记录"""
    print("=" * 60)
    print("测试：获取检测记录（分页）")
    print("=" * 60)
    
    task_id = "TASK-001"
    
    # 第一页
    result = get_detections(task_id, page=1, page_size=5)
    if result:
        print(f"任务: {result['task_id']}")
        print(f"总数: {result['total']}")
        print(f"当前页: {result['page']}")
        print(f"每页大小: {result['page_size']}")
        print(f"本页记录数: {len(result['detections'])}")
        print()
        
        for i, det in enumerate(result['detections'], 1):
            print(f"  [{i}] 帧ID: {det['frame_id']}")
            print(f"      时间: {det['timestamp']}")
            print(f"      目标类型: {det['target_type']}")
            print(f"      跟踪ID: {det.get('target_id', '无')}")
            print(f"      置信度: {det['confidence']:.2f}")
            if det.get('position'):
                pos = det['position']
                print(f"      位置: ({pos['lat']:.3f}, {pos['lng']:.3f})")
            print()


def test_filter_detections():
    """测试过滤检测记录"""
    print("=" * 60)
    print("测试：过滤检测记录")
    print("=" * 60)
    
    task_id = "TASK-001"
    
    # 过滤高置信度的 fighter
    result = get_detections(
        task_id,
        target_filter={"target_type": "fighter", "min_confidence": 0.85},
        page=1,
        page_size=10
    )
    
    if result:
        print(f"过滤条件：target_type=fighter, min_confidence=0.85")
        print(f"符合条件的记录数: {result['total']}")
        print(f"前 10 条记录:")
        for det in result['detections']:
            print(f"  - {det['frame_id']}: {det['target_type']} (置信度: {det['confidence']:.2f})")
    print()


if __name__ == "__main__":
    test_list_tasks()
    test_get_task_meta()
    test_get_detections()
    test_filter_detections()
    
    print("=" * 60)
    print("所有测试完成！")
    print("=" * 60)
