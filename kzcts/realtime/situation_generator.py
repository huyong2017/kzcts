"""态势生成器 - 持续生成移动的飞机轨迹"""

import asyncio
import random
import math
from datetime import datetime, timedelta
from typing import Dict, List
import uuid

from .models import SituationPoint, Position
from .data_store import store


class Aircraft:
    """模拟飞机"""
    
    def __init__(
        self,
        aircraft_id: str,
        aircraft_type: str,  # civilian/military
        target_type: str,  # airliner/fighter/bomber/helicopter
        start_position: Position,
        speed: float,  # km/h
        heading: float,  # 度，0-360
        altitude: float,  # 米
        callsign: str = None
    ):
        self.aircraft_id = aircraft_id
        self.aircraft_type = aircraft_type
        self.target_type = target_type
        self.position = start_position
        self.speed = speed
        self.heading = heading
        self.altitude = altitude
        self.callsign = callsign or f"{aircraft_type[:3].upper()}-{random.randint(1000, 9999)}"
        self.classification = "known_civilian" if aircraft_type == "civilian" else "known_military"
        self.confidence = 0.95
        
        # 航路点（用于模拟转弯）
        self.waypoints = []
        self.current_waypoint_idx = 0
        self._generate_waypoints()
        
        # 起飞和降落状态
        self.is_takeoff = True  # 新飞机从起飞开始
        self.is_landing = False
        self.takeoff_duration = 60  # 起飞爬升持续60秒
        self.landing_duration = 60  # 降落过程持续60秒
        self.target_altitude = altitude  # 目标巡航高度
        self.target_speed = speed  # 目标巡航速度
        self.takeoff_start_time = 0  # 起飞开始时间戳
    
    def _generate_waypoints(self):
        """生成航路点"""
        # 生成 3-5 个航路点
        num_waypoints = random.randint(3, 5)
        lat = self.position.lat
        lng = self.position.lng
        
        for _ in range(num_waypoints):
            # 随机偏移 0.5-2 度
            lat += random.uniform(0.5, 2.0) * random.choice([-1, 1])
            lng += random.uniform(0.5, 2.0) * random.choice([-1, 1])
            
            # 限制在合理范围内
            lat = max(-90, min(90, lat))
            lng = max(-180, min(180, lng))
            
            self.waypoints.append(Position(lat=lat, lng=lng))
    
    def update(self, delta_seconds: float):
        """更新飞机位置"""
        # 起飞阶段：从地面爬升到巡航高度
        if self.is_takeoff:
            self.takeoff_start_time += delta_seconds
            
            # 爬升率：每秒爬升目标高度的1/60
            climb_rate = self.target_altitude / self.takeoff_duration
            self.altitude += climb_rate * delta_seconds
            
            # 加速：从0加速到巡航速度
            acceleration_rate = self.speed / self.takeoff_duration
            self.speed += acceleration_rate * delta_seconds
            
            # 达到巡航高度后结束起飞
            if self.altitude >= self.target_altitude:
                self.altitude = self.target_altitude
                self.is_takeoff = False
                print(f"[CRUISE] {self.aircraft_id} 达到巡航高度 {self.altitude:.0f}m")
            
            # 继续水平移动
            speed_deg_per_sec = (self.speed / 3600) / 111.0
            delta_deg = speed_deg_per_sec * delta_seconds
            
            heading_rad = math.radians(self.heading)
            self.position.lat += delta_deg * math.cos(heading_rad)
            self.position.lng += delta_deg * math.sin(heading_rad)
            
            # 限制在合理范围内
            self.position.lat = max(-90, min(90, self.position.lat))
            self.position.lng = max(-180, min(180, self.position.lng))
            
            return
        
        # 降落阶段：从巡航高度下降到地面
        if self.is_landing:
            # 下降率：每秒下降当前高度的1/60
            descent_rate = self.landing_start_altitude / self.landing_duration
            self.altitude -= descent_rate * delta_seconds
            self.altitude = max(0, self.altitude)
            
            # 减速：从当前速度减速到0
            deceleration_rate = self.landing_start_speed / self.landing_duration
            self.speed -= deceleration_rate * delta_seconds
            self.speed = max(50, self.speed)  # 保持最小速度继续前进
            
            # 继续水平移动（按照当前航向）
            speed_deg_per_sec = (self.speed / 3600) / 111.0
            delta_deg = speed_deg_per_sec * delta_seconds
            
            heading_rad = math.radians(self.heading)
            self.position.lat += delta_deg * math.cos(heading_rad)
            self.position.lng += delta_deg * math.sin(heading_rad)
            
            # 限制在合理范围内
            self.position.lat = max(-90, min(90, self.position.lat))
            self.position.lng = max(-180, min(180, self.position.lng))
            
            return
        
        # 正常巡航阶段
        # 如果有航路点，向航路点移动
        if self.waypoints and self.current_waypoint_idx < len(self.waypoints):
            target = self.waypoints[self.current_waypoint_idx]
            
            # 计算到目标点的方向和距离
            dlat = target.lat - self.position.lat
            dlng = target.lng - self.position.lng
            distance = math.sqrt(dlat**2 + dlng**2)
            
            # 如果接近目标点，切换到下一个航路点
            if distance < 0.1:
                self.current_waypoint_idx += 1
                if self.current_waypoint_idx >= len(self.waypoints):
                    # 重新生成航路点
                    self.waypoints = []
                    self._generate_waypoints()
                    self.current_waypoint_idx = 0
            else:
                # 计算新航向
                self.heading = math.degrees(math.atan2(dlng, dlat))
                
                # 随机扰动航向（模拟真实飞行）
                self.heading += random.uniform(-2, 2)
        
        # 根据速度和航向更新位置
        # 速度转换为度/秒（简化计算，1 度约 111km）
        speed_deg_per_sec = (self.speed / 3600) / 111.0
        delta_deg = speed_deg_per_sec * delta_seconds
        
        heading_rad = math.radians(self.heading)
        self.position.lat += delta_deg * math.cos(heading_rad)
        self.position.lng += delta_deg * math.sin(heading_rad)
        
        # 限制在合理范围内
        self.position.lat = max(-90, min(90, self.position.lat))
        self.position.lng = max(-180, min(180, self.position.lng))
        
        # 高度小幅随机扰动（模拟气流）
        self.altitude += random.uniform(-10, 10)
        self.altitude = max(self.target_altitude - 200, min(self.target_altitude + 200, self.altitude))
        
        # 速度小幅随机扰动
        self.speed += random.uniform(-5, 5)
        self.speed = max(self.target_speed - 50, min(self.target_speed + 50, self.speed))
    
    def start_landing(self):
        """开始降落"""
        if not self.is_landing:
            self.is_landing = True
            self.landing_start_altitude = self.altitude
            self.landing_start_speed = self.speed
            print(f"[DESCENT] {self.aircraft_id} 开始降落，当前高度 {self.altitude:.0f}m，速度 {self.speed:.0f}km/h")
    
    def create_situation_point(self) -> SituationPoint:
        """创建态势点"""
        return SituationPoint(
            point_id=f"SP-{uuid.uuid4().hex[:8]}",
            aircraft_id=self.aircraft_id,
            aircraft_type=self.aircraft_type,
            target_type=self.target_type,
            timestamp=datetime.now(),
            position=Position(
                lat=self.position.lat,
                lng=self.position.lng,
                altitude=self.altitude
            ),
            speed=self.speed,
            heading=self.heading,
            altitude=self.altitude,
            callsign=self.callsign,
            classification=self.classification,
            confidence=self.confidence
        )


class SituationGenerator:
    """态势生成器"""
    
    def __init__(self):
        self.aircrafts: Dict[str, Aircraft] = {}
        self.running = False
        self._task = None
        self._aircraft_counter = 10  # 用于生成新飞机ID
        
        # 飞机生命周期管理
        self.aircraft_lifespan: Dict[str, int] = {}  # aircraft_id -> 剩余生存帧数
        
        # 初始化一些飞机
        self._init_aircrafts()
    
    def _init_aircrafts(self):
        """初始化模拟飞机"""
        # 民机（3-5 架）
        for i in range(random.randint(3, 5)):
            self._create_aircraft("civilian")
        
        # 军机（2-4 架）
        for i in range(random.randint(2, 4)):
            self._create_aircraft("military")
    
    def _create_aircraft(self, aircraft_type: str) -> str:
        """创建新飞机"""
        self._aircraft_counter += 1
        
        if aircraft_type == "civilian":
            aircraft_id = f"CIV-{self._aircraft_counter:03d}"
            target_type = "airliner"
            target_speed = random.uniform(700, 900)
            target_altitude = random.uniform(8000, 12000)
            callsign = f"CA{random.randint(1000, 9999)}"
        else:  # military
            aircraft_id = f"MIL-{self._aircraft_counter:03d}"
            target_type = random.choice(["fighter", "bomber", "helicopter"])
            target_speed = random.uniform(600, 1200)
            target_altitude = random.uniform(3000, 10000)
            callsign = f"MIL{random.randint(10, 99)}"
        
        # 新飞机从地面起飞（高度0，速度0）
        aircraft = Aircraft(
            aircraft_id=aircraft_id,
            aircraft_type=aircraft_type,
            target_type=target_type,
            start_position=Position(
                lat=random.uniform(20, 40),
                lng=random.uniform(100, 130)
            ),
            speed=0,  # 初始速度为0
            heading=random.uniform(0, 360),
            altitude=0,  # 初始高度为0（地面）
            callsign=callsign
        )
        
        # 设置目标巡航参数
        aircraft.target_speed = target_speed
        aircraft.target_altitude = target_altitude
        aircraft.speed = target_speed  # 用于update中的加速计算
        aircraft.altitude = 0  # 从0开始爬升
        
        self.aircrafts[aircraft_id] = aircraft
        
        # 设置生命周期（120-600 秒，即 2-10 分钟，更长一些）
        lifespan = random.randint(120, 600)
        self.aircraft_lifespan[aircraft_id] = lifespan
        
        print(f"[TAKEOFF] New aircraft: {aircraft_id} ({aircraft_type}), target altitude {target_altitude:.0f}m, target speed {target_speed:.0f}km/h, lifespan {lifespan}s")
        
        return aircraft_id
    
    async def start(self):
        """启动态势生成"""
        self.running = True
        self._task = asyncio.create_task(self._generate_loop())
    
    async def stop(self):
        """停止态势生成"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _generate_loop(self):
        """生成循环（每秒更新）"""
        tick_count = 0
        
        while self.running:
            try:
                tick_count += 1
                
                # 更新所有飞机位置
                for aircraft in list(self.aircrafts.values()):
                    aircraft.update(delta_seconds=1.0)
                    
                    # 创建态势点并保存
                    point = aircraft.create_situation_point()
                    store.save_situation_point(point)
                
                # 更新飞机生命周期
                self._update_aircraft_lifecycle()
                
                # 每 30 秒检查是否需要添加新飞机
                if tick_count % 30 == 0:
                    self._maybe_add_new_aircraft()
                
                # 等待 1 秒
                await asyncio.sleep(1.0)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"态势生成错误: {e}")
                await asyncio.sleep(1.0)
    
    def _update_aircraft_lifecycle(self):
        """更新飞机生命周期，处理降落"""
        landing_aircraft = []
        remove_aircraft = []
        
        for aircraft_id in list(self.aircraft_lifespan.keys()):
            self.aircraft_lifespan[aircraft_id] -= 1
            
            # 生命周期结束，开始降落（提前60秒开始降落）
            if self.aircraft_lifespan[aircraft_id] == 60:
                if aircraft_id in self.aircrafts:
                    self.aircrafts[aircraft_id].start_landing()
            
            # 降落完成（生命周期结束），移除飞机
            if self.aircraft_lifespan[aircraft_id] <= 0:
                remove_aircraft.append(aircraft_id)
        
        # 移除已降落的飞机
        for aircraft_id in remove_aircraft:
            if aircraft_id in self.aircrafts:
                aircraft = self.aircrafts[aircraft_id]
                print(f"[LANDING] Aircraft landed: {aircraft_id} ({aircraft.callsign})")
                del self.aircrafts[aircraft_id]
            if aircraft_id in self.aircraft_lifespan:
                del self.aircraft_lifespan[aircraft_id]
    
    def _maybe_add_new_aircraft(self):
        """随机添加新飞机"""
        # 当前飞机数量
        current_count = len(self.aircrafts)
        
        # 如果飞机太少（< 5），强制添加
        if current_count < 5:
            aircraft_type = random.choice(["civilian", "military"])
            self._create_aircraft(aircraft_type)
            return
        
        # 否则 30% 概率添加新飞机
        if random.random() < 0.3:
            # 70% 概率民机，30% 概率军机
            aircraft_type = "civilian" if random.random() < 0.7 else "military"
            self._create_aircraft(aircraft_type)
    
    def get_latest_points(self) -> List[SituationPoint]:
        """获取所有飞机的最新态势点"""
        return [aircraft.create_situation_point() for aircraft in self.aircrafts.values()]


# 全局态势生成器实例
situation_generator = SituationGenerator()
