"""
Core State Machine and Workflow Orchestration
Uses Temporal.io for durable execution
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import json
import uuid
from datetime import datetime


class WorkflowState(Enum):
    """Workflow states for the CI/CD pipeline"""
    PENDING = "pending"
    REQUIREMENT_ANALYSIS = "requirement_analysis"
    ARCHITECTURE_DESIGN = "architecture_design"
    CODE_GENERATION = "code_generation"
    TESTING = "testing"
    CODE_REVIEW = "code_review"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    FAILED = "failed"
    HUMAN_INTERVENTION = "human_intervention"


@dataclass
class MachineTaskSpecification:
    """
    Machine Task Specification (MTS) - Output from PM Agent
    Structured requirement document for downstream agents
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    business_objective: str = ""
    functional_requirements: List[Dict[str, Any]] = field(default_factory=list)
    non_functional_requirements: Dict[str, Any] = field(default_factory=dict)
    acceptance_criteria: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    test_scenarios: List[Dict[str, Any]] = field(default_factory=list)
    ambiguities: List[Dict[str, str]] = field(default_factory=list)
    confidence_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "business_objective": self.business_objective,
            "functional_requirements": self.functional_requirements,
            "non_functional_requirements": self.non_functional_requirements,
            "acceptance_criteria": self.acceptance_criteria,
            "dependencies": self.dependencies,
            "test_scenarios": self.test_scenarios,
            "ambiguities": self.ambiguities,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MachineTaskSpecification":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            business_objective=data.get("business_objective", ""),
            functional_requirements=data.get("functional_requirements", []),
            non_functional_requirements=data.get("non_functional_requirements", {}),
            acceptance_criteria=data.get("acceptance_criteria", []),
            dependencies=data.get("dependencies", []),
            test_scenarios=data.get("test_scenarios", []),
            ambiguities=data.get("ambiguities", []),
            confidence_score=data.get("confidence_score", 0.0),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow()
        )


@dataclass
class PreciseChangePlan:
    """
    Precise Change Plan (PCP) - Output from Architect Agent
    Targeted file modifications with minimal impact
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mts_id: str = ""
    affected_files: List[Dict[str, Any]] = field(default_factory=list)
    new_files: List[Dict[str, Any]] = field(default_factory=list)
    deleted_files: List[str] = field(default_factory=list)
    dependency_changes: List[Dict[str, Any]] = field(default_factory=list)
    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    estimated_complexity: str = "medium"  # low, medium, high
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "mts_id": self.mts_id,
            "affected_files": self.affected_files,
            "new_files": self.new_files,
            "deleted_files": self.deleted_files,
            "dependency_changes": self.dependency_changes,
            "risk_assessment": self.risk_assessment,
            "estimated_complexity": self.estimated_complexity,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PreciseChangePlan":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            mts_id=data.get("mts_id", ""),
            affected_files=data.get("affected_files", []),
            new_files=data.get("new_files", []),
            deleted_files=data.get("deleted_files", []),
            dependency_changes=data.get("dependency_changes", []),
            risk_assessment=data.get("risk_assessment", {}),
            estimated_complexity=data.get("estimated_complexity", "medium"),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow()
        )


@dataclass
class CodeChange:
    """Represents a code modification"""
    file_path: str
    old_content: str
    new_content: str
    change_type: str  # modify, create, delete
    diff_summary: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "old_content": self.old_content,
            "new_content": self.new_content,
            "change_type": self.change_type,
            "diff_summary": self.diff_summary
        }


@dataclass
class TestResult:
    """Test execution result"""
    test_id: str
    test_name: str
    passed: bool
    error_message: Optional[str] = None
    execution_time_ms: int = 0
    coverage_percent: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "passed": self.passed,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms,
            "coverage_percent": self.coverage_percent
        }


@dataclass
class ReviewFeedback:
    """Code review feedback from Senior Agent"""
    reviewer_id: str
    issues: List[Dict[str, Any]] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    approval_status: str = "pending"  # approved, rejected, needs_revision
    security_score: float = 0.0
    performance_score: float = 0.0
    maintainability_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "reviewer_id": self.reviewer_id,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "approval_status": self.approval_status,
            "security_score": self.security_score,
            "performance_score": self.performance_score,
            "maintainability_score": self.maintainability_score
        }


@dataclass
class DeploymentStatus:
    """Deployment status from DevOps Agent"""
    deployment_id: str
    environment: str  # staging, production
    strategy: str  # blue_green, canary, rolling
    status: str  # pending, in_progress, completed, failed, rolled_back
    health_metrics: Dict[str, Any] = field(default_factory=dict)
    rollback_triggered: bool = False
    rollback_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "environment": self.environment,
            "strategy": self.strategy,
            "status": self.status,
            "health_metrics": self.health_metrics,
            "rollback_triggered": self.rollback_triggered,
            "rollback_reason": self.rollback_reason,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class WorkflowContext:
    """
    Central context object that flows through the entire workflow
    Maintains state and data across all agents
    """
    
    def __init__(self, workflow_id: str = None):
        self.workflow_id = workflow_id or str(uuid.uuid4())
        self.state = WorkflowState.PENDING
        self.mts: Optional[MachineTaskSpecification] = None
        self.pcp: Optional[PreciseChangePlan] = None
        self.code_changes: List[CodeChange] = []
        self.test_results: List[TestResult] = []
        self.review_feedback: Optional[ReviewFeedback] = None
        self.deployment_status: Optional[DeploymentStatus] = None
        self.healing_cycles: int = 0
        self.max_healing_cycles: int = 3
        self.errors: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def transition_to(self, new_state: WorkflowState):
        """Transition to a new state with validation"""
        valid_transitions = {
            WorkflowState.PENDING: [WorkflowState.REQUIREMENT_ANALYSIS],
            WorkflowState.REQUIREMENT_ANALYSIS: [WorkflowState.ARCHITECTURE_DESIGN, WorkflowState.HUMAN_INTERVENTION],
            WorkflowState.ARCHITECTURE_DESIGN: [WorkflowState.CODE_GENERATION, WorkflowState.HUMAN_INTERVENTION],
            WorkflowState.CODE_GENERATION: [WorkflowState.TESTING, WorkflowState.CODE_GENERATION],  # Self-loop for healing
            WorkflowState.TESTING: [WorkflowState.CODE_GENERATION, WorkflowState.CODE_REVIEW, WorkflowState.HUMAN_INTERVENTION],
            WorkflowState.CODE_REVIEW: [WorkflowState.CODE_GENERATION, WorkflowState.DEPLOYMENT, WorkflowState.HUMAN_INTERVENTION],
            WorkflowState.DEPLOYMENT: [WorkflowState.MONITORING, WorkflowState.DEPLOYMENT],  # Self-loop for retry
            WorkflowState.MONITORING: [WorkflowState.COMPLETED, WorkflowState.DEPLOYMENT],  # Rollback triggers redeploy
            WorkflowState.HUMAN_INTERVENTION: [WorkflowState.REQUIREMENT_ANALYSIS, WorkflowState.ARCHITECTURE_DESIGN, 
                                                WorkflowState.CODE_GENERATION, WorkflowState.TESTING, 
                                                WorkflowState.CODE_REVIEW, WorkflowState.DEPLOYMENT],
        }
        
        if new_state not in valid_transitions.get(self.state, []):
            raise ValueError(f"Invalid transition from {self.state} to {new_state}")
        
        self.state = new_state
        self.updated_at = datetime.utcnow()
    
    def add_error(self, error_type: str, message: str, agent: str):
        self.errors.append({
            "type": error_type,
            "message": message,
            "agent": agent,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.updated_at = datetime.utcnow()
    
    def can_heal(self) -> bool:
        return self.healing_cycles < self.max_healing_cycles
    
    def increment_healing_cycle(self):
        self.healing_cycles += 1
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "state": self.state.value,
            "mts": self.mts.to_dict() if self.mts else None,
            "pcp": self.pcp.to_dict() if self.pcp else None,
            "code_changes": [c.to_dict() for c in self.code_changes],
            "test_results": [t.to_dict() for t in self.test_results],
            "review_feedback": self.review_feedback.to_dict() if self.review_feedback else None,
            "deployment_status": self.deployment_status.to_dict() if self.deployment_status else None,
            "healing_cycles": self.healing_cycles,
            "max_healing_cycles": self.max_healing_cycles,
            "errors": self.errors,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowContext":
        ctx = cls(workflow_id=data.get("workflow_id"))
        ctx.state = WorkflowState(data.get("state", "pending"))
        ctx.mts = MachineTaskSpecification.from_dict(data["mts"]) if data.get("mts") else None
        ctx.pcp = PreciseChangePlan.from_dict(data["pcp"]) if data.get("pcp") else None
        ctx.code_changes = [CodeChange(**c) for c in data.get("code_changes", [])]
        ctx.test_results = [TestResult(**t) for t in data.get("test_results", [])]
        ctx.review_feedback = ReviewFeedback(**data["review_feedback"]) if data.get("review_feedback") else None
        ctx.deployment_status = DeploymentStatus(**data["deployment_status"]) if data.get("deployment_status") else None
        ctx.healing_cycles = data.get("healing_cycles", 0)
        ctx.max_healing_cycles = data.get("max_healing_cycles", 3)
        ctx.errors = data.get("errors", [])
        ctx.metadata = data.get("metadata", {})
        ctx.created_at = datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow()
        ctx.updated_at = datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.utcnow()
        return ctx
