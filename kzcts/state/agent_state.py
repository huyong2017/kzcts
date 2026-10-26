"""共享状态定义"""

from typing import TypedDict, Optional


class AgentState(TypedDict):
    """LangGraph 共享状态"""
    
    # 任务上下文
    task_id: str
    user_request: str
    
    # 态势
    state_version: int
    consumed_version: int
    current_situation_summary: str
    
    # 判读流程
    detection_summary_ref: str
    planned_tasks: list
    approved_plans: list
    pending_requests: list
    
    # 知识库
    knowledge_version: str
    knowledge_context: dict
    
    # 结论与仲裁
    draft_verdict: dict
    final_verdict: dict
    conflicts: list
    arbitration_results: list
    
    # 前端联动
    active_alerts: list
    focused_target_id: str
    
    # 推荐
    recommendation: dict
