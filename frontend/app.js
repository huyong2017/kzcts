/**
 * 空中飞机判读系统 - 3D 地球前端应用 (Cesium)
 */

// ========== 全局状态 ==========
const state = {
    // Cesium Viewer
    viewer: null,
    
    // WebSocket 连接
    situationWs: null,
    taskWs: null,
    currentTaskId: null,
    
    // 态势数据
    situationEntities: new Map(), // aircraft_id -> entity
    situationTrajectories: new Map(), // aircraft_id -> positions[]
    selectedEntityId: null, // 当前选中的实体ID
    
    // 任务数据
    targetEntities: new Map(), // target_id -> entity
    targetTrajectories: new Map(), // target_id -> positions[]
    currentFrame: 0,
    totalDetections: 0,
    
    // 检测点数据
    detectionEntities: new Map(), // detection_id -> entity
    
    // 预测轨迹数据
    predictedTrajectories: new Map(), // recommendation_id -> entity
    
    // 任务列表
    tasks: [],
    
    // 显示控制
    showCivilian: true,
    showMilitary: true,
    showTrajectory: true
};

// ========== 初始化 ==========

function initCesium() {
    // 创建 Viewer（使用高德地图影像）
    state.viewer = new Cesium.Viewer('cesiumContainer', {
        // 使用高德地图影像（国内可用）
        imageryProvider: new Cesium.UrlTemplateImageryProvider({
            url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
            subdomains: ['1', '2', '3', '4'],
            maximumLevel: 18
        }),
        // 不使用地形
        terrainProvider: new Cesium.EllipsoidTerrainProvider(),
        baseLayerPicker: false,
        geocoder: false,
        homeButton: true,
        sceneModePicker: true,
        navigationHelpButton: false,
        animation: false,
        timeline: false,
        fullscreenButton: false,
        vrButton: false,
        infoBox: false,
        selectionIndicator: true
    });
    
    // 设置初始视角 - 中国上空
    state.viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(110, 30, 8000000),
        duration: 2
    });
    
    console.log('Cesium 3D 地球初始化完成');
}

function bindOn(id, event, fn) {
    const el = document.getElementById(id);
    if (!el) {
        console.warn(`[bindOn] 页面缺少元素 #${id}（可能是 HTML/JS 版本不一致，请强制刷新）`);
        return;
    }
    el.addEventListener(event, fn);
}

function initEventListeners() {
    // 创建任务按钮
    const createTaskBtn = document.getElementById('btn-create-task');
    if (createTaskBtn) {
        createTaskBtn.addEventListener('click', () => {
            console.log('创建任务按钮被点击');
            showTaskPanel();
        });
        console.log('创建任务按钮事件监听器已设置');
    } else {
        console.error('找不到 btn-create-task 按钮');
    }
    
    // 其余按钮一律防御式绑定，避免单个元素缺失中断全部初始化
    bindOn('btn-connect-task', 'click', connectToSelectedTask);
    bindOn('btn-close-task-panel', 'click', hideTaskPanel);
    bindOn('btn-confirm-create-task', 'click', createTask);

    // 任务列表 / 详情面板
    bindOn('btn-task-list', 'click', toggleTaskListPanel);
    bindOn('btn-close-task-list', 'click', closeTaskPanels);
    bindOn('btn-close-task-detail', 'click', closeTaskPanels);
    bindOn('btn-back-to-task-list', 'click', backToTaskList);
    setupTaskListDelegation();
    
    // 输入框 -> 矩形 双向同步（扫描范围固定，只有中心可调；不移动相机）
    bindOn('task-region-center', 'change', syncRectFromInputs);
    
    // 推荐面板关闭按钮
    bindOn('btn-close-recommendation', 'click', () => {
        document.getElementById('recommendation-panel').classList.add('hidden');
    });
    
    // 显示控制
    bindOn('show-civilian', 'change', (e) => {
        state.showCivilian = e.target.checked;
        updateSituationVisibility();
    });
    
    bindOn('show-military', 'change', (e) => {
        state.showMilitary = e.target.checked;
        updateSituationVisibility();
    });
    
    bindOn('show-trajectory', 'change', (e) => {
        state.showTrajectory = e.target.checked;
        updateTrajectoryVisibility();
    });
    
    // 关闭面板
    bindOn('btn-close-panel', 'click', () => {
        document.getElementById('info-panel').classList.add('hidden');
    });
    
    // 点击实体
    const handler = new Cesium.ScreenSpaceEventHandler(state.viewer.scene.canvas);
    handler.setInputAction((click) => {
        const pickedObject = state.viewer.scene.pick(click.position);
        if (Cesium.defined(pickedObject) && pickedObject.id) {
            const entityId = pickedObject.id.id || pickedObject.id;
            handleEntityClick(entityId);
        }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    
    // 禁用双击放大
    state.viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(
        Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK
    );
    
    console.log('事件监听器初始化完成');
}

// ========== WebSocket 连接 ==========

function connectSituationWebSocket() {
    const wsUrl = 'ws://localhost:8000/api/ws/situation';
    console.log('🔌 正在连接态势 WebSocket:', wsUrl);
    
    state.situationWs = new WebSocket(wsUrl);
    
    // 立即记录初始状态
    console.log('📊 WebSocket 初始 readyState:', state.situationWs.readyState, '(0=CONNECTING)');
    
    state.situationWs.onopen = () => {
        console.log('✅ 态势 WebSocket 已连接');
        console.log('📊 WebSocket readyState:', state.situationWs.readyState, '(1=OPEN)');
        console.log('📊 WebSocket URL:', state.situationWs.url);
        console.log('📊 WebSocket protocol:', state.situationWs.protocol);
        
        updateConnectionStatus('situation', true);
        
        // 发送心跳
        setInterval(() => {
            if (state.situationWs && state.situationWs.readyState === WebSocket.OPEN) {
                console.log('💓 发送心跳...');
                state.situationWs.send('ping');
            } else {
                console.warn('⚠️ 心跳跳过：WebSocket 未连接, readyState:', state.situationWs?.readyState);
            }
        }, 30000);
    };
    
    state.situationWs.onmessage = (event) => {
        try {
            // 忽略心跳响应
            if (event.data === 'pong') {
                console.log('💚 收到心跳响应');
                return;
            }
            
            const message = JSON.parse(event.data);
            console.log('📩 收到态势消息:', message.type, message.data?.points?.length || 0, '个点');
            handleSituationMessage(message);
        } catch (error) {
            console.error('❌ 解析态势消息失败:', error, '原始数据:', event.data);
        }
    };
    
    state.situationWs.onclose = (event) => {
        console.log('⚠️ 态势 WebSocket 已断开');
        console.log('📊 Close code:', event.code);
        console.log('📊 Close reason:', event.reason);
        console.log('📊 Close wasClean:', event.wasClean);
        console.log('📊 WebSocket readyState:', state.situationWs.readyState, '(3=CLOSED)');
        
        updateConnectionStatus('situation', false);
        
        // 自动重连
        console.log('🔄 3秒后尝试重连...');
        setTimeout(connectSituationWebSocket, 3000);
    };
    
    state.situationWs.onerror = (error) => {
        console.error('❌ 态势 WebSocket 错误:', error);
        console.error('📊 WebSocket readyState:', state.situationWs.readyState);
        console.error('📊 WebSocket URL:', state.situationWs.url);
        updateConnectionStatus('situation', false);
    };
}

function connectTaskWebSocket(taskId) {
    // 断开旧连接
    if (state.taskWs) {
        state.taskWs.close();
    }
    
    const wsUrl = `ws://localhost:8000/api/ws/tasks/${taskId}`;
    state.taskWs = new WebSocket(wsUrl);
    state.currentTaskId = taskId;
    
    state.taskWs.onopen = () => {
        console.log(`任务 ${taskId} WebSocket 已连接`);
        updateConnectionStatus('task', true);
        
        // 发送心跳
        setInterval(() => {
            if (state.taskWs.readyState === WebSocket.OPEN) {
                state.taskWs.send('ping');
            }
        }, 30000);
    };
    
    state.taskWs.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleTaskMessages(message);
    };
    
    state.taskWs.onclose = () => {
        console.log(`任务 ${taskId} WebSocket 已断开`);
        updateConnectionStatus('task', false);
    };
    
    state.taskWs.onerror = (error) => {
        console.error(`任务 ${taskId} WebSocket 错误:`, error);
        updateConnectionStatus('task', false);
    };
}

// ========== 消息处理 ==========

function handleSituationMessage(message) {
    if (message.type === 'situation_update') {
        const { points, is_history } = message.data;
        
        // 获取当前所有飞机ID
        const currentAircraftIds = new Set(points.map(p => p.aircraft_id));
        
        // 移除不再存在的飞机（已降落）
        for (const aircraftId of Array.from(state.situationEntities.keys())) {
            if (!currentAircraftIds.has(aircraftId)) {
                console.log(`[LANDING] 飞机 ${aircraftId} 已降落，移除显示`);
                removeSituationEntity(aircraftId);
            }
        }
        
        if (is_history) {
            console.log(`收到历史态势数据: ${points.length} 个点`);
            points.forEach(point => updateSituationPoint(point));
        } else {
            console.log(`收到实时更新: ${points.length} 个点`);
            points.forEach(point => updateSituationPoint(point));
        }
        
        updateStats();
    } else if (message.type === 'new_slice') {
        console.log('收到新切片:', message.data.slice_id);
        displaySlice(message.data);
    } else if (message.type === 'task_recommendation') {
        console.log('收到任务推荐:', message.data.recommendation_id);
        showRecommendation(message.data);
    }
}

function handleTaskMessages(message) {
    if (message.type === 'new_frame') {
        handleNewFrame(message.data);
    } else if (message.type === 'target_update') {
        handleTargetUpdate(message.data);
    } else if (message.type === 'task_status') {
        handleTaskStatus(message.data);
    }
}

function handleNewFrame(frameData) {
    const { frame_id, slice_id, detections } = frameData;
    
    state.currentFrame = slice_id;
    
    detections.forEach(detection => {
        updateTargetDetection(detection);
    });
    
    updateStats();
}

function handleTargetUpdate(targetData) {
    const { target_id, target_type, classification, confidence } = targetData;
    
    if (state.targetEntities.has(target_id)) {
        const entity = state.targetEntities.get(target_id);
        entity.description = createTargetDescription(targetData);
    }
}

function handleTaskStatus(statusData) {
    console.log('任务状态更新:', statusData);
}

// ========== 态势点渲染 ==========

function updateSituationPoint(point) {
    const { aircraft_id, aircraft_type, position, speed, heading, altitude, callsign, classification } = point;
    
    // 保存轨迹历史
    if (!state.situationTrajectories.has(aircraft_id)) {
        state.situationTrajectories.set(aircraft_id, []);
    }
    const trajectory = state.situationTrajectories.get(aircraft_id);
    trajectory.push([position.lat, position.lng, altitude || 10000]);
    
    // 只保留最近 100 个点
    if (trajectory.length > 100) {
        trajectory.shift();
    }
    
    // 更新或创建实体
    if (state.situationEntities.has(aircraft_id)) {
        // 更新现有实体
        const entity = state.situationEntities.get(aircraft_id);
        const newPosition = Cesium.Cartesian3.fromDegrees(position.lng, position.lat, altitude || 10000);
        entity.position = newPosition;
        entity.description = createSituationDescription(point);
        
        // 如果这是选中的实体，更新信息面板
        if (state.selectedEntityId === aircraft_id) {
            showInfoPanel(aircraft_id, createSituationDescription(point));
        }
        
        // 更新轨迹
        updateSituationTrajectory(aircraft_id, trajectory);
    } else {
        // 创建新实体
        const color = aircraft_type === 'civilian' ? Cesium.Color.DODGERBLUE : Cesium.Color.RED;
        
        console.log(`创建新实体: ${aircraft_id} (${aircraft_type}) 位置: ${position.lat.toFixed(3)}, ${position.lng.toFixed(3)}`);
        
        const entity = state.viewer.entities.add({
            id: aircraft_id,
            position: Cesium.Cartesian3.fromDegrees(position.lng, position.lat, altitude || 10000),
            point: {
                pixelSize: 10,
                color: color,
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2,
                heightReference: Cesium.HeightReference.NONE
            },
            label: {
                text: callsign,
                font: '12px sans-serif',
                fillColor: Cesium.Color.WHITE,
                outlineColor: Cesium.Color.BLACK,
                outlineWidth: 2,
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -15)
            },
            description: createSituationDescription(point)
        });
        
        state.situationEntities.set(aircraft_id, entity);
        
        // 只有选中的飞机才显示轨迹
        if (state.selectedEntityId === aircraft_id) {
            createSituationTrajectory(aircraft_id, trajectory, color);
        }
    }
}

function updateSituationTrajectory(aircraft_id, trajectory) {
    const lineKey = aircraft_id + '_line';
    // 只有选中的飞机才更新轨迹
    if (state.selectedEntityId === aircraft_id && state.situationTrajectories.has(lineKey)) {
        const positions = trajectory.map(p => 
            Cesium.Cartesian3.fromDegrees(p[1], p[0], p[2])
        );
        state.situationTrajectories.get(lineKey).polyline.positions = new Cesium.ConstantProperty(positions);
    }
}

function removeSituationEntity(aircraft_id) {
    // 移除飞机实体
    if (state.situationEntities.has(aircraft_id)) {
        const entity = state.situationEntities.get(aircraft_id);
        state.viewer.entities.remove(entity);
        state.situationEntities.delete(aircraft_id);
    }
    
    // 移除轨迹线
    const lineKey = aircraft_id + '_line';
    if (state.situationTrajectories.has(lineKey)) {
        const line = state.situationTrajectories.get(lineKey);
        state.viewer.entities.remove(line);
        state.situationTrajectories.delete(lineKey);
    }
    
    // 移除轨迹历史数据
    if (state.situationTrajectories.has(aircraft_id)) {
        state.situationTrajectories.delete(aircraft_id);
    }
    
    // 如果移除的是选中的飞机，清空选中状态
    if (state.selectedEntityId === aircraft_id) {
        state.selectedEntityId = null;
        document.getElementById('info-panel').classList.add('hidden');
    }
}

function createSituationTrajectory(aircraft_id, trajectory, color) {
    const positions = trajectory.map(p => 
        Cesium.Cartesian3.fromDegrees(p[1], p[0], p[2])
    );
    
    const polyline = state.viewer.entities.add({
        id: aircraft_id + '_line',
        polyline: {
            positions: positions,
            width: 2,
            material: new Cesium.PolylineDashMaterialProperty({
                color: color.withAlpha(0.6),
                dashLength: 10
            })
        }
    });
    
    state.situationTrajectories.set(aircraft_id + '_line', polyline);
}

function createSituationDescription(point) {
    const { aircraft_id, aircraft_type, callsign, position, speed, heading, altitude, classification } = point;
    
    return `
        <div style="padding: 10px;">
            <h3 style="margin: 0 0 10px 0;">${callsign} (${aircraft_id})</h3>
            <table style="width: 100%; font-size: 13px;">
                <tr><td style="color: #666;">类型:</td><td style="font-weight: bold; color: ${aircraft_type === 'civilian' ? '#1890ff' : '#ff4d4f'};">${aircraft_type === 'civilian' ? '民机' : '军机'}</td></tr>
                <tr><td style="color: #666;">位置:</td><td>${position.lat.toFixed(3)}, ${position.lng.toFixed(3)}</td></tr>
                <tr><td style="color: #666;">速度:</td><td>${speed.toFixed(0)} km/h</td></tr>
                <tr><td style="color: #666;">航向:</td><td>${heading.toFixed(0)}°</td></tr>
                <tr><td style="color: #666;">高度:</td><td>${altitude.toFixed(0)} m</td></tr>
                <tr><td style="color: #666;">分类:</td><td>${classification}</td></tr>
            </table>
        </div>
    `;
}

// ========== 目标检测点渲染 ==========

function updateTargetDetection(detection) {
    const { target_id, position, confidence, speed, heading } = detection;
    
    state.totalDetections++;
    
    // 保存轨迹
    if (!state.targetTrajectories.has(target_id)) {
        state.targetTrajectories.set(target_id, []);
    }
    const trajectory = state.targetTrajectories.get(target_id);
    trajectory.push([position.lat, position.lng, position.altitude || 8000]);
    
    // 只保留最近 50 个点
    if (trajectory.length > 50) {
        trajectory.shift();
    }
    
    // 更新或创建实体
    if (state.targetEntities.has(target_id)) {
        const entity = state.targetEntities.get(target_id);
        entity.position = Cesium.Cartesian3.fromDegrees(position.lng, position.lat, position.altitude || 8000);
        
        updateTargetTrajectory(target_id, trajectory);
    } else {
        const entity = state.viewer.entities.add({
            id: target_id,
            position: Cesium.Cartesian3.fromDegrees(position.lng, position.lat, position.altitude || 8000),
            point: {
                pixelSize: 8,
                color: Cesium.Color.PURPLE,
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2
            },
            label: {
                text: target_id,
                font: '11px sans-serif',
                fillColor: Cesium.Color.WHITE,
                outlineColor: Cesium.Color.BLACK,
                outlineWidth: 2,
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -12)
            },
            description: createTargetDescription(detection)
        });
        
        state.targetEntities.set(target_id, entity);
        
        createTargetTrajectory(target_id, trajectory);
    }
}

function updateTargetTrajectory(target_id, trajectory) {
    const lineKey = target_id + '_line';
    if (state.targetTrajectories.has(lineKey)) {
        const positions = trajectory.map(p => 
            Cesium.Cartesian3.fromDegrees(p[1], p[0], p[2])
        );
        state.targetTrajectories.get(lineKey).polyline.positions = new Cesium.ConstantProperty(positions);
    }
}

function createTargetTrajectory(target_id, trajectory) {
    const positions = trajectory.map(p => 
        Cesium.Cartesian3.fromDegrees(p[1], p[0], p[2])
    );
    
    const polyline = state.viewer.entities.add({
        id: target_id + '_line',
        polyline: {
            positions: positions,
            width: 3,
            material: Cesium.Color.PURPLE.withAlpha(0.7)
        }
    });
    
    state.targetTrajectories.set(target_id + '_line', polyline);
}

function createTargetDescription(detection) {
    const { target_id, target_type, classification, confidence, position } = detection;
    
    return `
        <div style="padding: 10px;">
            <h3 style="margin: 0 0 10px 0;">目标 ${target_id}</h3>
            <table style="width: 100%; font-size: 13px;">
                <tr><td style="color: #666;">类型:</td><td>${target_type || 'unknown'}</td></tr>
                <tr><td style="color: #666;">分类:</td><td style="color: ${classification === 'military' ? '#ff4d4f' : '#faad14'};">${classification || 'unknown'}</td></tr>
                <tr><td style="color: #666;">置信度:</td><td>${(confidence * 100).toFixed(1)}%</td></tr>
                <tr><td style="color: #666;">位置:</td><td>${position.lat.toFixed(3)}, ${position.lng.toFixed(3)}</td></tr>
                ${speed ? `<tr><td style="color: #666;">速度:</td><td>${speed.toFixed(0)} km/h</td></tr>` : ''}
                ${heading ? `<tr><td style="color: #666;">航向:</td><td>${heading.toFixed(0)}°</td></tr>` : ''}
            </table>
        </div>
    `;
}

function handleEntityClick(entityId) {
    const previousSelectedId = state.selectedEntityId;
    
    // 记录选中的实体
    state.selectedEntityId = entityId;
    
    // 如果切换了选中的飞机，移除旧飞机的轨迹，创建新飞机的轨迹
    if (previousSelectedId && previousSelectedId !== entityId) {
        // 移除旧飞机的轨迹
        const oldLineKey = previousSelectedId + '_line';
        if (state.situationTrajectories.has(oldLineKey)) {
            const oldLine = state.situationTrajectories.get(oldLineKey);
            state.viewer.entities.remove(oldLine);
            state.situationTrajectories.delete(oldLineKey);
        }
    }
    
    // 检查是态势飞机还是任务目标
    if (state.situationEntities.has(entityId)) {
        const entity = state.situationEntities.get(entityId);
        showInfoPanel(entityId, entity.description._value);
        
        // 创建新飞机的轨迹
        if (!state.situationTrajectories.has(entityId + '_line')) {
            const trajectory = state.situationTrajectories.get(entityId) || [];
            const color = entity.point.color.getValue().toCssColorString() === 'rgb(30,144,255)' ? Cesium.Color.DODGERBLUE : Cesium.Color.RED;
            createSituationTrajectory(entityId, trajectory, color);
        }
    } else if (state.targetEntities.has(entityId)) {
        const entity = state.targetEntities.get(entityId);
        showInfoPanel(entityId, entity.description._value);
    }
}

function showInfoPanel(title, content) {
    const panel = document.getElementById('info-panel');
    const panelTitle = document.getElementById('panel-title');
    const panelContent = document.getElementById('panel-content');
    
    panelTitle.textContent = title;
    panelContent.innerHTML = content;
    panel.classList.remove('hidden');
}

// ========== 任务管理 ==========

async function loadTasks() {
    try {
        const response = await fetch('http://localhost:8000/api/tasks');
        state.tasks = await response.json();
        
        const selector = document.getElementById('task-selector');
        selector.innerHTML = '<option value="">选择任务...</option>';
        
        state.tasks.forEach(task => {
            const option = document.createElement('option');
            option.value = task.task_id;
            option.textContent = `${task.task_name} [${task.status}]`;
            selector.appendChild(option);
        });
        
        console.log(`加载了 ${state.tasks.length} 个任务`);
    } catch (error) {
        console.error('加载任务失败:', error);
    }
}

async function createNewTask() {
    const taskName = prompt('请输入任务名称:', '新任务');
    if (!taskName) return;
    
    const region = prompt('请输入关注区域:', '东海海域');
    if (!region) return;
    
    const sensorType = prompt('请输入传感器类型 (optical/infrared/radar):', 'optical');
    if (!sensorType) return;
    
    try {
        const response = await fetch('http://localhost:8000/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_name: taskName,
                region: region,
                sensor_type: sensorType,
                frame_interval: 2.0,
                priority: 3
            })
        });
        
        if (response.ok) {
            const task = await response.json();
            alert(`任务创建成功: ${task.task_id}`);
            await loadTasks();
            connectToTask(task.task_id);
        } else {
            alert('任务创建失败');
        }
    } catch (error) {
        console.error('创建任务失败:', error);
        alert('创建任务失败');
    }
}

function connectToSelectedTask() {
    const selector = document.getElementById('task-selector');
    const taskId = selector.value;
    
    if (!taskId) {
        alert('请先选择一个任务');
        return;
    }
    
    connectToTask(taskId);
}

function connectToTask(taskId) {
    clearTaskData();
    connectTaskWebSocket(taskId);
    document.getElementById('task-selector').value = taskId;
    console.log(`已连接到任务: ${taskId}`);
}

function clearTaskData() {
    // 清除目标实体
    state.targetEntities.forEach((entity, id) => {
        state.viewer.entities.remove(entity);
    });
    state.targetEntities.clear();
    
    // 清除轨迹线
    state.targetTrajectories.forEach((entity, key) => {
        if (key.endsWith('_line')) {
            state.viewer.entities.remove(entity);
        }
    });
    state.targetTrajectories.clear();
    
    state.currentFrame = 0;
    state.totalDetections = 0;
    
    updateStats();
}

// ========== 显示控制 ==========

function updateSituationVisibility() {
    state.situationEntities.forEach((entity, id) => {
        // 简化处理：根据 ID 前缀判断类型
        const isCivilian = id.startsWith('CIV');
        if (isCivilian) {
            entity.show = state.showCivilian;
        } else {
            entity.show = state.showMilitary;
        }
    });
}

function updateTrajectoryVisibility() {
    state.situationTrajectories.forEach((entity, key) => {
        if (key.endsWith('_line')) {
            entity.show = state.showTrajectory;
        }
    });
    
    state.targetTrajectories.forEach((entity, key) => {
        if (key.endsWith('_line')) {
            entity.show = state.showTrajectory;
        }
    });
}

// ========== UI 更新 ==========

function updateConnectionStatus(type, connected) {
    const element = document.getElementById(`status-${type}`);
    const dot = element.querySelector('.status-dot');
    const text = element.querySelector('.status-text');
    
    if (connected) {
        dot.classList.add('connected');
        dot.classList.remove('disconnected');
        text.textContent = `${type === 'situation' ? '态势' : '任务'}: 已连接`;
    } else {
        dot.classList.add('disconnected');
        dot.classList.remove('connected');
        text.textContent = `${type === 'situation' ? '态势' : '任务'}: 未连接`;
    }
}

function updateStats() {
    document.getElementById('stat-aircraft').textContent = state.situationEntities.size;
    document.getElementById('stat-targets').textContent = state.targetEntities.size;
    document.getElementById('stat-detections').textContent = state.totalDetections;
    document.getElementById('stat-frames').textContent = state.currentFrame;
}

// ========== 任务管理 ==========

let scanRectangle = null;
let rectangleCenter = { lat: 35.0, lng: 110.0 };
let rectangleSize = { width: 0.5, height: 0.5 }; // 度（≈55km，红外扫描 swath）
let isDraggingRectangle = false;

function showTaskPanel() {
    console.log('显示任务创建面板');
    const panel = document.getElementById('task-panel');
    if (!panel) {
        console.error('找不到 task-panel 元素');
        return;
    }
    panel.classList.remove('hidden');
    panel.style.display = 'flex';
    
    // 打开面板即在地球上显示可拖动矩形（不移动相机）
    syncRectFromInputs();
    createScanRectangle();
    setupRectangleDrag();
}

function hideTaskPanel() {
    const panel = document.getElementById('task-panel');
    if (panel) {
        panel.classList.add('hidden');
        panel.style.display = 'none';
    }
    removeScanRectangle();
}

function syncRectFromInputs() {
    const centerStr = document.getElementById('task-region-center').value.trim();
    const [lat, lng] = centerStr.split(',').map(s => parseFloat(s.trim()));
    if (!isNaN(lat) && !isNaN(lng)) {
        rectangleCenter.lat = lat;
        rectangleCenter.lng = lng;
    }
}

function createScanRectangle() {
    if (!state.viewer) return;
    removeScanRectangle();
    
    scanRectangle = state.viewer.entities.add({
        rectangle: {
            coordinates: new Cesium.CallbackProperty(() => Cesium.Rectangle.fromDegrees(
                rectangleCenter.lng - rectangleSize.width / 2,
                rectangleCenter.lat - rectangleSize.height / 2,
                rectangleCenter.lng + rectangleSize.width / 2,
                rectangleCenter.lat + rectangleSize.height / 2
            ), false),
            material: Cesium.Color.CYAN.withAlpha(0.45),
            outline: true,
            outlineColor: Cesium.Color.YELLOW
        }
    });
}

function removeScanRectangle() {
    if (scanRectangle && state.viewer) {
        state.viewer.entities.remove(scanRectangle);
        scanRectangle = null;
    }
    destroyDragHandler();
}

function setupRectangleDrag() {
    if (!state.viewer) return;
    destroyDragHandler();
    
    const handler = new Cesium.ScreenSpaceEventHandler(state.viewer.scene.canvas);
    const scc = state.viewer.scene.screenSpaceCameraController;
    
    // 只有按在矩形上才开始拖动，其余区域相机正常操作
    handler.setInputAction((movement) => {
        const picked = state.viewer.scene.pick(movement.position);
        const hitRect = picked && picked.id === scanRectangle;
        
        let hitInside = false;
        if (!hitRect) {
            const pos = state.viewer.camera.pickEllipsoid(movement.position, state.viewer.scene.globe.ellipsoid);
            if (pos) {
                const c = Cesium.Cartographic.fromCartesian(pos);
                const lat = Cesium.Math.toDegrees(c.latitude);
                const lng = Cesium.Math.toDegrees(c.longitude);
                hitInside = Math.abs(lat - rectangleCenter.lat) <= rectangleSize.height / 2 &&
                            Math.abs(lng - rectangleCenter.lng) <= rectangleSize.width / 2;
            }
        }
        
        if (hitRect || hitInside) {
            isDraggingRectangle = true;
            scc.enableRotate = false;
            scc.enableTranslate = false;
            scc.enableTilt = false;
            scc.enableLook = false;
        }
    }, Cesium.ScreenSpaceEventType.LEFT_DOWN);
    
    handler.setInputAction((movement) => {
        if (!isDraggingRectangle) return;
        const pos = state.viewer.camera.pickEllipsoid(movement.endPosition, state.viewer.scene.globe.ellipsoid);
        if (!pos) return;
        const c = Cesium.Cartographic.fromCartesian(pos);
        rectangleCenter.lat = Cesium.Math.toDegrees(c.latitude);
        rectangleCenter.lng = Cesium.Math.toDegrees(c.longitude);
        
        // 实时回填输入框
        document.getElementById('task-region-center').value =
            `${rectangleCenter.lat.toFixed(4)},${rectangleCenter.lng.toFixed(4)}`;
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
    
    handler.setInputAction(() => {
        if (!isDraggingRectangle) return;
        isDraggingRectangle = false;
        scc.enableRotate = true;
        scc.enableTranslate = true;
        scc.enableTilt = true;
        scc.enableLook = true;
    }, Cesium.ScreenSpaceEventType.LEFT_UP);
    
    state.draggingHandler = handler;
}

function destroyDragHandler() {
    isDraggingRectangle = false;
    if (state.draggingHandler) {
        state.draggingHandler.destroy();
        state.draggingHandler = null;
    }
    if (state.viewer && state.viewer.scene.screenSpaceCameraController) {
        const scc = state.viewer.scene.screenSpaceCameraController;
        scc.enableRotate = true;
        scc.enableTranslate = true;
        scc.enableZoom = true;
        scc.enableTilt = true;
        scc.enableLook = true;
    }
}

async function createTask() {
    const taskName = document.getElementById('task-name').value.trim();
    const sensorType = document.getElementById('task-sensor').value;
    const regionCenter = document.getElementById('task-region-center').value.trim();
    const duration = parseFloat(document.getElementById('task-duration').value);
    const interval = parseFloat(document.getElementById('task-interval').value);
    
    if (!taskName) {
        alert('请输入任务名称');
        return;
    }
    
    if (!regionCenter) {
        alert('请输入扫描区域中心');
        return;
    }
    
    // 解析区域（扫描范围固定）
    const [centerLat, centerLng] = regionCenter.split(',').map(s => parseFloat(s.trim()));
    const width = rectangleSize.width;
    const height = rectangleSize.height;
    
    if (isNaN(centerLat) || isNaN(centerLng)) {
        alert('区域格式错误，请使用：纬度,经度');
        return;
    }
    
    const region = `${centerLat},${centerLng},${width},${height}`;
    
    try {
        const response = await fetch('http://localhost:8000/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_name: taskName,
                region: region,
                sensor_type: sensorType,
                scan_duration: duration,
                frame_interval: interval,
                priority: 1,
                description: `${sensorType}扫描任务`
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const task = await response.json();
        console.log('任务创建成功:', task);
        
        hideTaskPanel();
        alert(`任务 ${task.task_id} 创建成功！`);
        
        // 刷新任务列表
        await loadTasks();
        
    } catch (error) {
        console.error('创建任务失败:', error);
        alert('创建任务失败: ' + error.message);
    }
}

// ========== 任务列表与聚焦 ==========

let focusEntities = [];   // 当前聚焦任务生成的实体
let historyCache = null;  // 当前聚焦任务的历史数据

function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function formatTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function toggleTaskListPanel() {
    const panel = document.getElementById('task-list-panel');
    const detail = document.getElementById('task-detail-panel');
    if (detail) detail.classList.add('hidden');
    if (panel.classList.contains('hidden')) {
        panel.classList.remove('hidden');
        refreshTaskList();
    } else {
        panel.classList.add('hidden');
    }
}

function closeTaskPanels() {
    const list = document.getElementById('task-list-panel');
    const detail = document.getElementById('task-detail-panel');
    if (list) list.classList.add('hidden');
    if (detail) detail.classList.add('hidden');
    clearFocusEntities();
}

function backToTaskList() {
    const detail = document.getElementById('task-detail-panel');
    const list = document.getElementById('task-list-panel');
    if (detail) detail.classList.add('hidden');
    if (list) list.classList.remove('hidden');
    refreshTaskList();
}

function setupTaskListDelegation() {
    const container = document.getElementById('task-list-items');
    if (!container) return;
    container.addEventListener('click', (e) => {
        const item = e.target.closest('.task-list-item');
        if (!item) return;
        const taskId = item.getAttribute('data-task-id');
        const task = state.tasks.find(t => t.task_id === taskId);
        if (task) focusOnTask(task);
    });
}

async function refreshTaskList() {
    try {
        const response = await fetch('http://localhost:8000/api/tasks');
        const tasks = await response.json();
        state.tasks = tasks;
        renderTaskListItems(tasks);
    } catch (error) {
        console.error('加载任务列表失败:', error);
        const container = document.getElementById('task-list-items');
        if (container) container.innerHTML = '<div class="task-list-empty">无法加载任务列表</div>';
    }
}

function renderTaskListItems(tasks) {
    const container = document.getElementById('task-list-items');
    if (!container) return;
    if (!tasks || !tasks.length) {
        container.innerHTML = '<div class="task-list-empty">暂无任务</div>';
        return;
    }
    const sorted = [...tasks].sort((a, b) => new Date(b.start_time) - new Date(a.start_time));
    container.innerHTML = sorted.map(task => {
        const sensorBadge = task.sensor_type === 'infrared' ? 'badge-infrared' : 'badge-optical';
        let statusClass = 'status-pending';
        if (task.status === 'running') statusClass = 'status-running';
        else if (task.status === 'completed') statusClass = 'status-completed';
        return `<div class="task-list-item" data-task-id="${task.task_id}">
            <div class="task-list-item-title">
                <span>${escapeHtml(task.task_name)}</span>
                <span class="task-badge ${sensorBadge}">${escapeHtml(task.sensor_type)}</span>
            </div>
            <div class="task-list-item-meta">
                <span class="task-status ${statusClass}">${escapeHtml(task.status)}</span>
                <span>${formatTime(task.start_time)}</span>
            </div>
            <div class="task-list-item-meta">${escapeHtml(task.region)}</div>
        </div>`;
    }).join('');
}

async function focusOnTask(task) {
    clearFocusEntities();

    const parts = (task.region || '').split(',').map(s => parseFloat(s.trim()));
    let centerLat, centerLng, width, height;
    if (parts.length === 4 && parts.every(n => !isNaN(n))) {
        [centerLat, centerLng, width, height] = parts;
    } else {
        centerLat = 35; centerLng = 110; width = 0.5; height = 0.5;
    }

    // 红色区域矩形
    const rect = state.viewer.entities.add({
        id: `FOCUS-RECT-${task.task_id}`,
        rectangle: {
            coordinates: Cesium.Rectangle.fromDegrees(
                centerLng - width / 2, centerLat - height / 2,
                centerLng + width / 2, centerLat + height / 2
            ),
            outline: true,
            outlineColor: Cesium.Color.RED,
            outlineWidth: 3,
            fill: false,
            height: 0
        }
    });
    focusEntities.push(rect);

    // 聚焦相机（用户主动点击任务，允许移动）
    const pad = Math.max(width, height) / 2 + 2;
    state.viewer.camera.flyTo({
        destination: Cesium.Rectangle.fromDegrees(
            centerLng - width / 2 - pad, centerLat - height / 2 - pad,
            centerLng + width / 2 + pad, centerLat + height / 2 + pad
        ),
        duration: 2
    });

    // 加载时域对齐历史数据
    try {
        const response = await fetch(`http://localhost:8000/api/tasks/${task.task_id}/history`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        historyCache = data;
        renderTrajectories(data.trajectories || []);
        renderSliceDetections(data.slices || []);
        showTaskDetail(task, data);
    } catch (error) {
        console.error('加载任务历史失败:', error);
        showTaskDetail(task, null, error.message);
    }

    // 列表 -> 详情
    const list = document.getElementById('task-list-panel');
    const detail = document.getElementById('task-detail-panel');
    if (list) list.classList.add('hidden');
    if (detail) detail.classList.remove('hidden');
}

function renderTrajectories(trajectories) {
    trajectories.forEach(traj => {
        if (!traj.points || traj.points.length === 0) return;
        const positions = traj.points.map(p =>
            Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.altitude || 10000)
        );
        const color = traj.classification === 'military'
            ? Cesium.Color.ORANGE.withAlpha(0.85)
            : Cesium.Color.GRAY.withAlpha(0.85);

        const line = state.viewer.entities.add({
            id: `FOCUS-TRAJ-${traj.aircraft_id}`,
            polyline: { positions: positions, width: 2, material: color }
        });
        focusEntities.push(line);

        const last = traj.points[traj.points.length - 1];
        const endpoint = state.viewer.entities.add({
            id: `FOCUS-TRAJ-END-${traj.aircraft_id}`,
            position: Cesium.Cartesian3.fromDegrees(last.lng, last.lat, last.altitude || 10000),
            point: { pixelSize: 7, color: color, outlineColor: Cesium.Color.WHITE, outlineWidth: 1 },
            label: {
                text: traj.aircraft_type || traj.aircraft_id,
                font: '11px sans-serif',
                fillColor: Cesium.Color.WHITE,
                outlineColor: Cesium.Color.BLACK,
                outlineWidth: 2,
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -8)
            }
        });
        focusEntities.push(endpoint);
    });
}

function renderSliceDetections(slices) {
    slices.forEach(slice => {
        (slice.detections || []).forEach(d => {
            const pos = d.detected_position || d.position;
            if (!pos) return;
            let color = Cesium.Color.YELLOW;
            if (d.classification === 'military') color = Cesium.Color.RED;
            else if (d.classification === 'suspected_military') color = Cesium.Color.PURPLE;
            else if (d.classification === 'civilian') color = Cesium.Color.DODGERBLUE;
            if (d.is_hidden_target) color = Cesium.Color.ORANGE;

            const entity = state.viewer.entities.add({
                id: `FOCUS-DET-${d.detection_id}`,
                position: Cesium.Cartesian3.fromDegrees(pos.lng, pos.lat, pos.altitude || 10000),
                point: { pixelSize: 8, color: color, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 }
            });
            focusEntities.push(entity);
        });
    });
}

function showTaskDetail(task, data, errorMsg) {
    const container = document.getElementById('task-detail-content');
    if (!container) return;
    const rows = [];
    rows.push(detailRow('任务ID', task.task_id));
    rows.push(detailRow('名称', task.task_name));
    rows.push(detailRow('传感器', task.sensor_type));
    rows.push(detailRow('状态', task.status));
    rows.push(detailRow('开始', formatTime(task.start_time)));
    rows.push(detailRow('结束', task.end_time ? formatTime(task.end_time) : '-'));
    rows.push(detailRow('区域', task.region));

    if (data) {
        const slices = data.slices || [];
        const detCount = slices.reduce((n, s) => n + (s.total_detections || (s.detections || []).length), 0);
        const hiddenCount = slices.reduce((n, s) => n + (s.detections || []).filter(d => d.is_hidden_target).length, 0);
        const suspectedCount = slices.reduce((n, s) => n + (s.detections || []).filter(d => d.classification === 'suspected_military').length, 0);
        const trajCount = (data.trajectories || []).length;
        const tw = data.time_window || {};
        rows.push(detailRow('时间窗', `${formatTime(tw.start)} ~ ${formatTime(tw.end)}`));
        rows.push(detailRow('切片数', slices.length));
        rows.push(detailRow('检测点', detCount));
        rows.push(detailRow('隐藏目标', hiddenCount));
        rows.push(detailRow('疑似军用', suspectedCount));
        rows.push(detailRow('历史轨迹', `${trajCount} 架`));
    } else if (errorMsg) {
        rows.push(detailRow('历史', `加载失败: ${errorMsg}`));
    }
    container.innerHTML = rows.join('');
}

function detailRow(k, v) {
    return `<div class="task-detail-row"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(v == null ? '' : String(v))}</span></div>`;
}

function clearFocusEntities() {
    focusEntities.forEach(e => state.viewer.entities.remove(e));
    focusEntities = [];
    historyCache = null;
}

// ========== 切片可视化 ==========

function displaySlice(sliceData) {
    console.log(`显示切片: ${sliceData.slice_id}, ${sliceData.total_detections} 个检测点`);
    
    // 更新统计
    state.totalDetections += sliceData.total_detections;
    state.currentFrame = sliceData.frame_index;
    updateStats();
    
    // 显示检测点
    sliceData.detections.forEach(detection => {
        displayDetection(detection);
    });
}

function displayDetection(detection) {
    const position = detection.detected_position || detection.position;
    
    // 根据分类确定颜色
    let color = Cesium.Color.YELLOW;
    if (detection.classification === 'military') {
        color = Cesium.Color.RED;
    } else if (detection.classification === 'suspected_military') {
        color = Cesium.Color.PURPLE;
    } else if (detection.classification === 'civilian') {
        color = Cesium.Color.DODGERBLUE;
    } else if (detection.is_hidden_target) {
        color = Cesium.Color.ORANGE;
    }
    
    // 创建检测点实体
    const entityId = `DET-${detection.detection_id}`;
    
    if (state.detectionEntities && state.detectionEntities.has(entityId)) {
        // 更新现有实体
        const entity = state.detectionEntities.get(entityId);
        entity.position = Cesium.Cartesian3.fromDegrees(position.lng, position.lat, position.altitude || 10000);
    } else {
        // 创建新实体
        if (!state.detectionEntities) {
            state.detectionEntities = new Map();
        }
        
        const entity = state.viewer.entities.add({
            id: entityId,
            position: Cesium.Cartesian3.fromDegrees(position.lng, position.lat, position.altitude || 10000),
            point: {
                pixelSize: 8,
                color: color,
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2,
                heightReference: Cesium.HeightReference.NONE
            },
            label: {
                text: detection.classification === 'suspected_military' ? '疑似' : '检测',
                font: '10px sans-serif',
                fillColor: Cesium.Color.WHITE,
                outlineColor: Cesium.Color.BLACK,
                outlineWidth: 2,
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -10)
            },
            description: createDetectionDescription(detection)
        });
        
        state.detectionEntities.set(entityId, entity);
    }
}

function createDetectionDescription(detection) {
    const position = detection.detected_position || detection.position;
    
    return `
        <div style="padding: 10px;">
            <h3 style="margin: 0 0 10px 0;">检测点 ${detection.detection_id}</h3>
            <table style="width: 100%; font-size: 13px;">
                <tr><td style="color: #666;">分类:</td><td style="font-weight: bold; color: ${detection.classification === 'suspected_military' ? '#9C27B0' : '#333'};">${detection.classification}</td></tr>
                <tr><td style="color: #666;">置信度:</td><td>${(detection.confidence * 100).toFixed(1)}%</td></tr>
                <tr><td style="color: #666;">位置:</td><td>${position.lat.toFixed(3)}, ${position.lng.toFixed(3)}</td></tr>
                <tr><td style="color: #666;">高度:</td><td>${(position.altitude || 0).toFixed(0)} m</td></tr>
                <tr><td style="color: #666;">速度:</td><td>${(detection.speed || 0).toFixed(0)} km/h</td></tr>
                <tr><td style="color: #666;">隐藏目标:</td><td>${detection.is_hidden_target ? '是' : '否'}</td></tr>
                ${detection.matched_aircraft_id ? `<tr><td style="color: #666;">匹配飞机:</td><td>${detection.matched_aircraft_id}</td></tr>` : ''}
            </table>
        </div>
    `;
}

// ========== 任务推荐处理 ==========

function showRecommendation(recommendation) {
    console.log('收到任务推荐:', recommendation);
    
    const panel = document.getElementById('recommendation-panel');
    const content = document.getElementById('recommendation-content');
    
    // 创建推荐项
    const item = document.createElement('div');
    item.className = 'recommendation-item';
    item.id = `rec-${recommendation.recommendation_id}`;
    
    item.innerHTML = `
        <div class="recommendation-title">
            <span>发现疑似目标</span>
            <span class="recommendation-badge">${recommendation.target_classification}</span>
        </div>
        <div class="recommendation-info">
            <strong>原因:</strong> ${recommendation.reason}<br>
            <strong>预测时长:</strong> ${recommendation.prediction_duration}秒<br>
            <strong>推荐传感器:</strong> ${recommendation.recommended_sensor === 'optical' ? '光学载荷' : '红外载荷'}<br>
            <strong>扫描区域:</strong> ${recommendation.recommended_region.center_lat.toFixed(2)}, ${recommendation.recommended_region.center_lng.toFixed(2)}
        </div>
        <div class="recommendation-actions">
            <button class="btn-accept" onclick="acceptRecommendation('${recommendation.recommendation_id}')">接受并创建查证任务</button>
            <button class="btn-reject" onclick="rejectRecommendation('${recommendation.recommendation_id}')">拒绝</button>
        </div>
    `;
    
    content.appendChild(item);
    panel.classList.remove('hidden');
    
    // 在地图上显示预测轨迹
    displayPredictedTrajectory(recommendation);
}

function displayPredictedTrajectory(recommendation) {
    if (!recommendation.predicted_trajectory || recommendation.predicted_trajectory.length === 0) {
        return;
    }
    
    const positions = recommendation.predicted_trajectory.map(p => 
        Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.altitude || 10000)
    );
    
    const entityId = `PRED-${recommendation.recommendation_id}`;
    
    // 移除旧的预测轨迹
    if (state.predictedTrajectories && state.predictedTrajectories.has(entityId)) {
        state.viewer.entities.remove(state.predictedTrajectories.get(entityId));
    }
    
    if (!state.predictedTrajectories) {
        state.predictedTrajectories = new Map();
    }
    
    // 创建预测轨迹线
    const entity = state.viewer.entities.add({
        id: entityId,
        polyline: {
            positions: positions,
            width: 3,
            material: new Cesium.PolylineGlowMaterialProperty({
                glowPower: 0.3,
                color: Cesium.Color.PURPLE
            }),
            clampToGround: false
        }
    });
    
    state.predictedTrajectories.set(entityId, entity);
    
    // 飞相机到预测区域
    const region = recommendation.recommended_region;
    state.viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(region.center_lng, region.center_lat, 2000000),
        duration: 2
    });
}

async function acceptRecommendation(recommendationId) {
    try {
        const response = await fetch(`http://localhost:8000/api/recommendations/${recommendationId}/accept`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const result = await response.json();
        console.log('查证任务创建成功:', result);
        
        // 移除推荐项
        const item = document.getElementById(`rec-${recommendationId}`);
        if (item) {
            item.remove();
        }
        
        alert(`查证任务 ${result.task_id} 创建成功！`);
        
        // 刷新任务列表
        await loadTasks();
        
    } catch (error) {
        console.error('接受推荐失败:', error);
        alert('接受推荐失败: ' + error.message);
    }
}

function rejectRecommendation(recommendationId) {
    // 移除推荐项
    const item = document.getElementById(`rec-${recommendationId}`);
    if (item) {
        item.remove();
    }
    
    // 移除预测轨迹
    const entityId = `PRED-${recommendationId}`;
    if (state.predictedTrajectories && state.predictedTrajectories.has(entityId)) {
        state.viewer.entities.remove(state.predictedTrajectories.get(entityId));
        state.predictedTrajectories.delete(entityId);
    }
    
    console.log('推荐已拒绝:', recommendationId);
}

// ========== 启动 ==========

async function start() {
    console.log('启动应用...');
    
    // 初始化 Cesium
    initCesium();
    
    // 初始化事件监听
    initEventListeners();
    
    // 加载初始态势数据（通过 REST API）
    await loadInitialSituation();
    
    // 加载任务列表
    await loadTasks();
    
    // 连接态势 WebSocket
    connectSituationWebSocket();
    
    // 定时刷新任务列表
    setInterval(loadTasks, 10000);
    
    console.log('应用启动完成');
}

async function loadInitialSituation() {
    try {
        console.log('加载初始态势数据...');
        const response = await fetch('http://localhost:8000/api/situation/points?hours=12');
        const data = await response.json();
        
        console.log(`获取到 ${data.count} 个初始态势点`);
        
        // 渲染所有态势点
        data.points.forEach(point => {
            updateSituationPoint(point);
        });
        
        updateStats();
        console.log('初始态势数据加载完成');
    } catch (error) {
        console.error('加载初始态势数据失败:', error);
    }
}

// 页面加载完成后启动
window.addEventListener('DOMContentLoaded', start);
