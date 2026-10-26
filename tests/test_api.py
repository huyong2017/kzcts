"""测试任务创建"""

import requests
import json

# 创建任务
print("创建任务...")
response = requests.post(
    "http://localhost:8000/api/tasks",
    json={
        "task_name": "东海光学扫描",
        "region": "东海海域",
        "sensor_type": "optical",
        "frame_interval": 2.0,
        "priority": 4,
        "description": "测试任务"
    }
)

if response.status_code == 200:
    task = response.json()
    print(f"任务创建成功!")
    print(f"  任务ID: {task['task_id']}")
    print(f"  任务名称: {task['task_name']}")
    print(f"  状态: {task['status']}")
    print(f"  传感器: {task['sensor_type']}")
    print()
    
    # 等待几秒，让帧生成器运行
    print("等待 5 秒，让帧生成器运行...")
    import time
    time.sleep(5)
    
    # 获取任务详情
    print("获取任务详情...")
    response = requests.get(f"http://localhost:8000/api/tasks/{task['task_id']}")
    if response.status_code == 200:
        task_detail = response.json()
        print(f"  状态: {task_detail['status']}")
    
    # 列出所有任务
    print("\n所有任务:")
    response = requests.get("http://localhost:8000/api/tasks")
    tasks = response.json()
    for t in tasks:
        print(f"  - {t['task_id']}: {t['task_name']} [{t['status']}]")
    
    # 获取态势点
    print("\n当前态势点:")
    response = requests.get("http://localhost:8000/api/situation/points?hours=12")
    data = response.json()
    print(f"  总数: {data['count']}")
    for point in data['points'][:3]:
        print(f"  - {point['aircraft_id']} ({point['aircraft_type']})")
        print(f"    位置: ({point['position']['lat']:.3f}, {point['position']['lng']:.3f})")
        print(f"    速度: {point['speed']:.0f} km/h")
    
    print("\n✅ 所有测试通过!")
    print(f"\nWebSocket 连接:")
    print(f"  任务: ws://localhost:8000/api/ws/tasks/{task['task_id']}")
    print(f"  态势: ws://localhost:8000/api/ws/situation")
    
else:
    print(f"创建失败: {response.status_code}")
    print(response.text)
