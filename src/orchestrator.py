"""
Agentic CI/CD Platform - Main Workflow Orchestrator
Coordinates all agents through the state machine
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

import sys
sys.path.insert(0, '/workspace/src')

from core.models import (
    WorkflowContext,
    WorkflowState,
    MachineTaskSpecification,
    PreciseChangePlan
)
from pm_agent import PMAgent, create_pm_agent
from architect_agent import ArchitectAgent, create_architect_agent
from dev_agent import DevAgent, create_dev_agent
from qa_agent import QAAgent, create_qa_agent
from senior_agent import SeniorAgent, DevOpsAgent, create_senior_agent, create_devops_agent


class WorkflowOrchestrator:
    """
    Main orchestrator that coordinates all agents through the workflow
    Implements the state machine described in the architecture
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # Initialize all agents
        self.pm_agent = create_pm_agent(
            llm_config=self.config.get('llm'),
            vector_store_config=self.config.get('vector_store')
        )
        self.architect_agent = create_architect_agent(
            llm_config=self.config.get('llm'),
            vector_store_config=self.config.get('vector_store')
        )
        self.dev_agent = create_dev_agent(
            llm_config=self.config.get('llm'),
            sandbox_config=self.config.get('sandbox')
        )
        self.qa_agent = create_qa_agent(
            llm_config=self.config.get('llm'),
            test_runner_config=self.config.get('test_runner')
        )
        self.senior_agent = create_senior_agent(
            llm_config=self.config.get('llm')
        )
        self.devops_agent = create_devops_agent(
            k8s_config=self.config.get('k8s'),
            monitoring_config=self.config.get('monitoring')
        )
        
        self.context: Optional[WorkflowContext] = None
    
    async def execute_workflow(
        self, 
        raw_requirement: str,
        context: Optional[Dict[str, Any]] = None
    ) -> WorkflowContext:
        """
        Execute the complete Agentic CI/CD workflow
        
        Args:
            raw_requirement: Unstructured requirement from user
            context: Optional context (Jira ticket, screenshots, etc.)
        
        Returns:
            Final WorkflowContext with results
        """
        # Initialize workflow context
        self.context = WorkflowContext()
        self.context.metadata['raw_requirement'] = raw_requirement
        self.context.metadata['started_at'] = datetime.utcnow().isoformat()
        
        print(f"🚀 Starting Agentic CI/CD workflow for: {raw_requirement[:50]}...")
        
        try:
            # State 1: Requirement Analysis (PM Agent)
            await self._execute_requirement_analysis(raw_requirement, context)
            
            # State 2: Architecture Design (Architect Agent)
            await self._execute_architecture_design(context)
            
            # State 3 & 4: Code Generation + Testing (Dev + QA Agents with healing loop)
            await self._execute_code_and_test_loop(context)
            
            # State 5: Code Review (Senior Agent)
            await self._execute_code_review(context)
            
            # State 6 & 7: Deployment + Monitoring (DevOps Agent)
            await self._execute_deployment_and_monitoring(context)
            
            # Success!
            self.context.transition_to(WorkflowState.COMPLETED)
            print("✅ Workflow completed successfully!")
            
        except Exception as e:
            print(f"❌ Workflow failed: {e}")
            self.context.add_error("workflow_error", str(e), "orchestrator")
            self.context.transition_to(WorkflowState.FAILED)
        
        self.context.metadata['completed_at'] = datetime.utcnow().isoformat()
        return self.context
    
    async def _execute_requirement_analysis(
        self, 
        raw_requirement: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Execute PM Agent for requirement analysis"""
        print("\n📋 Phase 1: Requirement Analysis (PM Agent)")
        self.context.transition_to(WorkflowState.REQUIREMENT_ANALYSIS)
        
        # Analyze requirement
        mts = await self.pm_agent.analyze_requirement(raw_requirement, context)
        self.context.mts = mts
        
        print(f"  ✓ Generated MTS with {len(mts.functional_requirements)} functional requirements")
        print(f"  ✓ Confidence score: {mts.confidence_score:.2f}")
        print(f"  ✓ Ambiguities detected: {len(mts.ambiguities)}")
        
        # Check if human intervention needed
        needs_intervention, questions = self.pm_agent.should_request_human_intervention(mts)
        if needs_intervention:
            print(f"  ⚠️  Human intervention required: {len(questions)} questions")
            self.context.transition_to(WorkflowState.HUMAN_INTERVENTION)
            self.context.metadata['intervention_questions'] = questions
            # In real implementation: pause and notify product manager
            # For now, continue with warning
            self.context.transition_to(WorkflowState.ARCHITECTURE_DESIGN)
        else:
            self.context.transition_to(WorkflowState.ARCHITECTURE_DESIGN)
    
    async def _execute_architecture_design(self, context: Optional[Dict[str, Any]] = None):
        """Execute Architect Agent for precise change planning"""
        print("\n🏗️  Phase 2: Architecture Design (Architect Agent)")
        
        # Generate precise change plan
        pcp = await self.architect_agent.design_architecture(self.context.mts, context)
        self.context.pcp = pcp
        
        total_files = len(pcp.affected_files) + len(pcp.new_files)
        print(f"  ✓ Generated PCP affecting {total_files} files")
        print(f"  ✓ Risk level: {pcp.risk_assessment.get('overall_risk', 'unknown')}")
        print(f"  ✓ Complexity: {pcp.estimated_complexity}")
        
        # Validate change plan
        is_valid, issues = self.architect_agent.validate_change_plan(pcp)
        if not is_valid:
            print(f"  ⚠️  Change plan issues: {issues}")
        
        self.context.transition_to(WorkflowState.CODE_GENERATION)
    
    async def _execute_code_and_test_loop(self, context: Optional[Dict[str, Any]] = None):
        """Execute Dev + QA loop with automatic healing"""
        print("\n💻 Phase 3 & 4: Code Generation + Testing (Dev + QA Agents)")
        
        max_attempts = self.context.max_healing_cycles + 1
        
        for attempt in range(max_attempts):
            print(f"\n  🔄 Attempt {attempt + 1}/{max_attempts}")
            
            # Dev Agent: Implement changes
            code_changes = await self.dev_agent.implement_changes(
                self.context.mts,
                self.context.pcp,
                context
            )
            self.context.code_changes = code_changes
            print(f"    ✓ Generated {len(code_changes)} code changes")
            
            # QA Agent: Test changes
            test_results, all_passed = await self.qa_agent.execute_testing(
                self.context.mts,
                code_changes,
                context
            )
            self.context.test_results = test_results
            
            passed_count = sum(1 for t in test_results if t.passed)
            print(f"    ✓ Test results: {passed_count}/{len(test_results)} passed")
            
            if all_passed:
                print("    ✅ All tests passed!")
                break
            else:
                failed_count = len(test_results) - passed_count
                print(f"    ⚠️  {failed_count} tests failed")
                
                if attempt < max_attempts - 1 and self.context.can_heal():
                    print("    🔧 Initiating healing loop...")
                    self.context.increment_healing_cycle()
                    
                    # Get healing request from QA
                    defects = await self._get_defects_from_failures(test_results, code_changes)
                    healing_request = self.qa_agent.generate_healing_request(defects, test_results)
                    
                    # Update context for next iteration
                    if context is None:
                        context = {}
                    context['healing_request'] = healing_request
                else:
                    print("    ❌ Max healing cycles reached. Escalating to human.")
                    self.context.transition_to(WorkflowState.HUMAN_INTERVENTION)
                    raise Exception("Tests failed after maximum healing attempts")
        
        self.context.transition_to(WorkflowState.CODE_REVIEW)
    
    async def _get_defects_from_failures(self, test_results, code_changes):
        """Extract defects from test failures"""
        from qa_agent import DefectReport
        defects = []
        for result in test_results:
            if not result.passed and result.error_message:
                defects.append(DefectReport(
                    defect_id=result.test_id,
                    test_name=result.test_name,
                    severity='major',
                    description=result.error_message,
                    steps_to_reproduce=[f"Run {result.test_name}"],
                    expected_behavior="Test should pass",
                    actual_behavior=result.error_message,
                    suggested_fix="Review implementation"
                ))
        return defects
    
    async def _execute_code_review(self, context: Optional[Dict[str, Any]] = None):
        """Execute Senior Agent for code review"""
        print("\n🔍 Phase 5: Code Review (Senior Agent)")
        
        # Perform comprehensive review
        feedback = await self.senior_agent.review_code(
            self.context.mts,
            self.context.code_changes,
            self.context.test_results,
            context
        )
        self.context.review_feedback = feedback
        
        print(f"  ✓ Security score: {feedback.security_score:.1f}/100")
        print(f"  ✓ Performance score: {feedback.performance_score:.1f}/100")
        print(f"  ✓ Maintainability score: {feedback.maintainability_score:.1f}/100")
        print(f"  ✓ Issues found: {len(feedback.issues)}")
        print(f"  ✓ Approval status: {feedback.approval_status}")
        
        if feedback.approval_status == 'rejected':
            print("  ❌ Code rejected. Sending back for revision.")
            self.context.transition_to(WorkflowState.CODE_GENERATION)
            raise Exception("Code review rejected")
        elif feedback.approval_status == 'needs_revision':
            print(f"  ⚠️  Needs revision: {feedback.suggestions[:2]}")
            self.context.transition_to(WorkflowState.CODE_GENERATION)
            raise Exception("Code review needs revision")
        
        print("  ✅ Code approved for deployment")
        self.context.transition_to(WorkflowState.DEPLOYMENT)
    
    async def _execute_deployment_and_monitoring(self, context: Optional[Dict[str, Any]] = None):
        """Execute DevOps Agent for deployment and monitoring"""
        print("\n🚀 Phase 6 & 7: Deployment + Monitoring (DevOps Agent)")
        
        # Deploy to staging first
        print("  📦 Deploying to staging...")
        staging_status = await self.devops_agent.deploy(
            self.context.code_changes,
            environment='staging',
            strategy='canary'
        )
        
        if staging_status.status != 'completed':
            print(f"  ❌ Staging deployment failed: {staging_status.rollback_reason}")
            raise Exception("Staging deployment failed")
        
        print("  ✅ Staging deployment successful")
        
        # Deploy to production
        print("  📦 Deploying to production...")
        prod_status = await self.devops_agent.deploy(
            self.context.code_changes,
            environment='production',
            strategy='canary'
        )
        
        self.context.deployment_status = prod_status
        
        if prod_status.status == 'rolled_back':
            print(f"  ❌ Production deployment rolled back: {prod_status.rollback_reason}")
            raise Exception(f"Production rollback: {prod_status.rollback_reason}")
        
        print("  ✅ Production deployment successful")
        
        # Start continuous monitoring
        self.context.transition_to(WorkflowState.MONITORING)
        print("  👁️  Starting production monitoring...")
        
        monitoring_result = await self.devops_agent.monitor_production(
            environment='production',
            duration_minutes=5  # Shortened for demo
        )
        
        if monitoring_result.get('alerts'):
            print(f"  ⚠️  Monitoring detected {len(monitoring_result['alerts'])} alerts")
        else:
            print("  ✅ No monitoring alerts")


async def main():
    """Example usage of the Agentic CI/CD platform"""
    
    # Example requirement
    requirement = """
    作为用户，我希望能够重置我的密码，以便在忘记密码时恢复账户访问。
    
    功能需求:
    - 用户可以通过邮箱请求密码重置
    - 系统发送包含重置链接的邮件
    - 重置链接有效期为 1 小时
    - 用户可以输入新密码并确认
    
    验收标准:
    - 重置邮件必须在 1 分钟内送达
    - 过期链接必须显示错误提示
    - 新密码必须符合安全策略（至少 8 位，包含大小写字母和数字）
    """
    
    # Initialize orchestrator
    orchestrator = WorkflowOrchestrator(config={})
    
    # Execute workflow
    result = await orchestrator.execute_workflow(requirement)
    
    # Print summary
    print("\n" + "="*60)
    print("WORKFLOW SUMMARY")
    print("="*60)
    print(f"Status: {result.state.value}")
    print(f"Healing cycles: {result.healing_cycles}")
    print(f"Code changes: {len(result.code_changes)}")
    print(f"Tests: {sum(1 for t in result.test_results if t.passed)}/{len(result.test_results)} passed")
    
    if result.deployment_status:
        print(f"Deployment: {result.deployment_status.status}")
    
    return result


if __name__ == "__main__":
    asyncio.run(main())
