"""测试后端服务"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from kzcts.realtime.data_store import store
from kzcts.realtime.models import Task, Position
from kzcts.realtime.situation_generator import situation_generator
from datetime import datetime


def test_data_store():
    """测试数据存储"""
    print("=" * 60)
    print("测试：数据存储")
    print("=" * 60)
    
    # 创建任务
    task = Task(
        task_id="TEST-001",
        task_name="测试任务",
        region="测试区域",
        sensor_type="optical",
        status="pending",
        start_time=datetime.now()
    )
    store.save_task(task)
    
    # 获取任务
    retrieved = store.get_task("TEST-001")
    print(f"任务创建成功: {retrieved.task_name}")
    
    # 列出任务
    tasks = store.list_tasks()
    print(f"任务列表: {len(tasks)} 个")
    print()


def test_situation_generator():
    """测试态势生成器"""
    print("=" * 60)
    print("测试：态势生成器")
    print("=" * 60)
    
    # 获取初始化的飞机
    aircrafts = situation_generator.aircrafts
    print(f"初始化飞机数量: {len(aircrafts)}")
    
    # 分类统计
    civilian_count = sum(1 for a in aircrafts.values() if a.aircraft_type == "civilian")
    military_count = sum(1 for a in aircrafts.values() if a.aircraft_type == "military")
    print(f"  - 民机: {civilian_count} 架")
    print(f"  - 军机: {military_count} 架")
    
    # 更新一次位置
    for aircraft in aircrafts.values():
        aircraft.update(delta_seconds=1.0)
    
    # 获取最新态势点
    latest_points = situation_generator.get_latest_points()
    print(f"最新态势点: {len(latest_points)} 个")
    
    # 显示前 3 个点
    for i, point in enumerate(latest_points[:3], 1):
        print(f"  [{i}] {point.aircraft_id} ({point.aircraft_type})")
        print(f"      位置: ({point.position.lat:.3f}, {point.position.lng:.3f})")
        print(f"      速度: {point.speed:.0f} km/h")
        print(f"      航向: {point.heading:.0f}°")
        print(f"      高度: {point.altitude:.0f} m")
    print()


if __name__ == "__main__":
    test_data_store()
    test_situation_generator()
    
    print("=" * 60)
    print("所有测试完成！")
    print("=" * 60)
    print()
    print("启动服务命令:")
    print("  py main.py")
    print()
    print("服务地址:")
    print("  - API 文档: http://localhost:8000/docs")
    print("  - 健康检查: http://localhost:8000/health")
    print("  - WebSocket 任务: ws://localhost:8000/api/ws/tasks/{task_id}")
    print("  - WebSocket 态势: ws://localhost:8000/api/ws/situation")
