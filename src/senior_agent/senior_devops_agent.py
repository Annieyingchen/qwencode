"""
Senior Agent & DevOps Agent
Senior: Code review, security, performance analysis
DevOps: Deployment, monitoring, auto-rollback
"""

import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import uuid
from datetime import datetime

import sys
sys.path.insert(0, '/workspace/src')
from core.models import (
    MachineTaskSpecification,
    CodeChange,
    TestResult,
    ReviewFeedback,
    DeploymentStatus,
    WorkflowContext
)


# ============================================================================
# Senior Agent - Code Review and Quality Gate
# ============================================================================

@dataclass
class CodeIssue:
    """Represents a code quality issue"""
    issue_id: str
    category: str  # security, performance, maintainability, bug, style
    severity: str  # critical, major, minor, info
    file_path: str
    line_number: Optional[int] = None
    description: str = ""
    suggestion: str = ""
    cwe_id: Optional[str] = None  # For security issues


class SeniorAgent:
    """
    Senior Developer Agent
    Responsible for code review, security analysis, and quality gates
    """
    
    def __init__(self, llm_client=None, security_scanner=None):
        self.llm_client = llm_client
        self.security_scanner = security_scanner
    
    async def review_code(
        self,
        mts: MachineTaskSpecification,
        code_changes: List[CodeChange],
        test_results: List[TestResult],
        context: Optional[Dict[str, Any]] = None
    ) -> ReviewFeedback:
        """
        Main entry point: Perform comprehensive code review
        
        Args:
            mts: Machine Task Specification
            code_changes: Code changes from Dev Agent
            test_results: Test results from QA Agent
            context: Optional context (coding standards, security policies, etc.)
        
        Returns:
            ReviewFeedback with approval decision
        """
        issues = []
        suggestions = []
        
        # Step 1: Security analysis
        security_issues = await self._analyze_security(code_changes)
        issues.extend(security_issues)
        
        # Step 2: Performance analysis
        performance_issues = await self._analyze_performance(code_changes, mts)
        issues.extend(performance_issues)
        
        # Step 3: Code quality and maintainability
        quality_issues = await self._analyze_quality(code_changes)
        issues.extend(quality_issues)
        
        # Step 4: Compliance with requirements
        compliance_check = await self._check_requirement_compliance(code_changes, mts)
        if not compliance_check['compliant']:
            issues.extend(compliance_check['issues'])
        
        # Step 5: Review test coverage
        test_review = self._review_test_coverage(test_results, code_changes)
        suggestions.extend(test_review)
        
        # Step 6: Calculate scores
        security_score = self._calculate_security_score(issues, 'security')
        performance_score = self._calculate_security_score(issues, 'performance')
        maintainability_score = self._calculate_security_score(issues, 'maintainability')
        
        # Step 7: Determine approval status
        approval_status = self._determine_approval_status(
            issues, security_score, test_results
        )
        
        # Step 8: Generate suggestions
        if approval_status == 'needs_revision':
            suggestions.extend(self._generate_fix_suggestions(issues))
        
        return ReviewFeedback(
            reviewer_id="senior-agent",
            issues=[self._issue_to_dict(i) for i in issues],
            suggestions=suggestions,
            approval_status=approval_status,
            security_score=security_score,
            performance_score=performance_score,
            maintainability_score=maintainability_score
        )
    
    async def _analyze_security(self, code_changes: List[CodeChange]) -> List[CodeIssue]:
        """Analyze code for security vulnerabilities"""
        issues = []
        
        # Security patterns to check
        security_patterns = {
            'sql_injection': [r'execute\s*\(\s*["\'].*%.*["\']', r'cursor\.execute\(.*\+'],
            'xss': [r'return\s+.*\.html\(.*request\.', r'RenderText\s*\(.*user'],
            'hardcoded_secrets': [r'password\s*=\s*["\'][^"\']+["\']', r'api_key\s*=\s*["\']'],
            'path_traversal': [r'open\s*\(\s*.*\+.*request', r'os\.path\.join\(.*user'],
        }
        
        for change in code_changes:
            if change.change_type in ['modify', 'create']:
                content = change.new_content
                
                for vuln_type, patterns in security_patterns.items():
                    for pattern in patterns:
                        import re
                        matches = re.finditer(pattern, content, re.IGNORECASE)
                        for match in matches:
                            line_num = content[:match.start()].count('\n') + 1
                            issues.append(CodeIssue(
                                issue_id=str(uuid.uuid4()),
                                category='security',
                                severity='critical',
                                file_path=change.file_path,
                                line_number=line_num,
                                description=f"Potential {vuln_type.replace('_', ' ')} vulnerability",
                                suggestion=f"Review line {line_num} for {vuln_type}",
                                cwe_id=self._get_cwe_id(vuln_type)
                            ))
        
        # Use external security scanner if available
        if self.security_scanner:
            scan_results = await self.security_scanner.scan(code_changes)
            for result in scan_results:
                issues.append(CodeIssue(**result))
        
        return issues
    
    def _get_cwe_id(self, vuln_type: str) -> Optional[str]:
        """Get CWE ID for vulnerability type"""
        cwe_map = {
            'sql_injection': 'CWE-89',
            'xss': 'CWE-79',
            'hardcoded_secrets': 'CWE-798',
            'path_traversal': 'CWE-22'
        }
        return cwe_map.get(vuln_type)
    
    async def _analyze_performance(
        self, 
        code_changes: List[CodeChange],
        mts: MachineTaskSpecification
    ) -> List[CodeIssue]:
        """Analyze code for performance issues"""
        issues = []
        
        performance_patterns = {
            'inefficient_loop': [r'for\s+\w+\s+in\s+\w+:\s*\n\s+for\s+\w+\s+in\s+\w+:'],
            'missing_caching': [r'def\s+get_\w+\(.*\):\s*\n\s+.*db\.'],
            'n_plus_one': [r'for\s+\w+\s+in\s+\w+:\s*\n\s+.*\.query\('],
            'large_memory_allocation': [r'\[\s*for\s+.*\s+in\s+range\s*\(\s*\d{6,}'],
        }
        
        for change in code_changes:
            if change.change_type in ['modify', 'create']:
                content = change.new_content
                
                for perf_type, patterns in performance_patterns.items():
                    for pattern in patterns:
                        import re
                        if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                            line_num = content.count('\n') // 2
                            issues.append(CodeIssue(
                                issue_id=str(uuid.uuid4()),
                                category='performance',
                                severity='major',
                                file_path=change.file_path,
                                line_number=line_num,
                                description=f"Potential {perf_type.replace('_', ' ')} issue",
                                suggestion=f"Consider optimizing: {perf_type}"
                            ))
        
        return issues
    
    async def _analyze_quality(self, code_changes: List[CodeChange]) -> List[CodeIssue]:
        """Analyze code quality and maintainability"""
        issues = []
        
        for change in code_changes:
            if change.change_type in ['modify', 'create']:
                content = change.new_content
                lines = content.split('\n')
                
                # Check function length
                import re
                functions = re.findall(r'def\s+(\w+)\s*\([^)]*\)\s*:', content)
                for func in functions:
                    # Simplified check - count lines until next def
                    func_match = re.search(rf'def\s+{func}\s*\([^)]*\)\s*:', content)
                    if func_match:
                        start = func_match.end()
                        next_def = re.search(r'\ndef\s+\w+', content[start:])
                        end = start + next_def.start() if next_def else len(content)
                        func_lines = content[start:end].count('\n')
                        
                        if func_lines > 50:
                            issues.append(CodeIssue(
                                issue_id=str(uuid.uuid4()),
                                category='maintainability',
                                severity='minor',
                                file_path=change.file_path,
                                description=f"Function '{func}' is too long ({func_lines} lines)",
                                suggestion="Consider breaking into smaller functions"
                            ))
                
                # Check for missing docstrings
                if 'def ' in content and '"""' not in content:
                    issues.append(CodeIssue(
                        issue_id=str(uuid.uuid4()),
                        category='style',
                        severity='info',
                        file_path=change.file_path,
                        description="Missing docstrings in functions",
                        suggestion="Add docstrings to all public functions"
                    ))
                
                # Check for TODO comments
                todos = re.findall(r'#\s*TODO[:\s]*(.+)', content)
                for todo in todos:
                    issues.append(CodeIssue(
                        issue_id=str(uuid.uuid4()),
                        category='maintainability',
                        severity='info',
                        file_path=change.file_path,
                        description=f"TODO comment found: {todo[:50]}",
                        suggestion="Address or remove TODO comment"
                    ))
        
        return issues
    
    async def _check_requirement_compliance(
        self,
        code_changes: List[CodeChange],
        mts: MachineTaskSpecification
    ) -> Dict[str, Any]:
        """Check if code changes comply with requirements"""
        result = {'compliant': True, 'issues': []}
        
        # Use LLM to verify requirement coverage
        if self.llm_client:
            prompt = f"""Verify if these code changes implement the requirements:

Business Objective: {mts.business_objective}

Acceptance Criteria:
{json.dumps(mts.acceptance_criteria, indent=2)}

Code Changes Summary:
{json.dumps([{'file': c.file_path, 'summary': c.diff_summary} for c in code_changes], indent=2)}

Return JSON with:
- compliant: boolean
- gaps: list of unmet requirements
"""
            response = await self.llm_client.generate(prompt, response_format={"type": "json_object"})
            analysis = json.loads(response)
            
            if not analysis.get('compliant', True):
                result['compliant'] = False
                for gap in analysis.get('gaps', []):
                    result['issues'].append(CodeIssue(
                        issue_id=str(uuid.uuid4()),
                        category='bug',
                        severity='major',
                        file_path='multiple',
                        description=f"Requirement gap: {gap}",
                        suggestion="Implement missing functionality"
                    ))
        
        return result
    
    def _review_test_coverage(
        self,
        test_results: List[TestResult],
        code_changes: List[CodeChange]
    ) -> List[str]:
        """Review test coverage and quality"""
        suggestions = []
        
        # Check pass rate
        if test_results:
            pass_rate = sum(1 for t in test_results if t.passed) / len(test_results)
            if pass_rate < 1.0:
                suggestions.append(f"Test pass rate is {pass_rate:.1%}. Fix failing tests before merge.")
            
            # Check coverage
            avg_coverage = sum(t.coverage_percent for t in test_results) / len(test_results)
            if avg_coverage < 80:
                suggestions.append(f"Test coverage is {avg_coverage:.1%}. Aim for >80% coverage.")
        
        # Check if all changed files have tests
        tested_files = set()
        for change in code_changes:
            # Simple heuristic: check if test file exists in results
            test_file = f"tests/test_{change.file_path.split('/')[-1]}"
            if not any(test_file in str(tr.test_name) for tr in test_results):
                if change.change_type == 'create':
                    suggestions.append(f"Add unit tests for new file: {change.file_path}")
        
        return suggestions
    
    def _calculate_security_score(
        self, 
        issues: List[CodeIssue], 
        category: str
    ) -> float:
        """Calculate score for a specific category (0-100)"""
        category_issues = [i for i in issues if i.category == category]
        
        if not category_issues:
            return 100.0
        
        # Deduct points based on severity
        severity_weights = {'critical': 30, 'major': 15, 'minor': 5, 'info': 1}
        deduction = sum(severity_weights.get(i.severity, 5) for i in category_issues)
        
        return max(0.0, min(100.0, 100.0 - deduction))
    
    def _determine_approval_status(
        self,
        issues: List[CodeIssue],
        security_score: float,
        test_results: List[TestResult]
    ) -> str:
        """Determine if code is approved for merge"""
        # Critical issues block approval
        critical_count = sum(1 for i in issues if i.severity == 'critical')
        if critical_count > 0:
            return 'rejected'
        
        # Low security score blocks approval
        if security_score < 70:
            return 'rejected'
        
        # Multiple major issues need revision
        major_count = sum(1 for i in issues if i.severity == 'major')
        if major_count > 3:
            return 'needs_revision'
        
        # Failing tests block approval
        if test_results and not all(t.passed for t in test_results):
            return 'needs_revision'
        
        return 'approved'
    
    def _generate_fix_suggestions(self, issues: List[CodeIssue]) -> List[str]:
        """Generate actionable fix suggestions"""
        suggestions = []
        
        # Group by category
        by_category = {}
        for issue in issues:
            if issue.category not in by_category:
                by_category[issue.category] = []
            by_category[issue.category].append(issue)
        
        if 'security' in by_category:
            suggestions.append("🔒 Address all security vulnerabilities before deployment")
        
        if 'performance' in by_category:
            suggestions.append("⚡ Optimize identified performance bottlenecks")
        
        if 'bug' in by_category:
            suggestions.append("🐛 Fix logic errors to meet requirements")
        
        return suggestions
    
    def _issue_to_dict(self, issue: CodeIssue) -> Dict[str, Any]:
        """Convert CodeIssue to dictionary"""
        return {
            'issue_id': issue.issue_id,
            'category': issue.category,
            'severity': issue.severity,
            'file_path': issue.file_path,
            'line_number': issue.line_number,
            'description': issue.description,
            'suggestion': issue.suggestion,
            'cwe_id': issue.cwe_id
        }


# ============================================================================
# DevOps Agent - Deployment and Monitoring
# ============================================================================

class DevOpsAgent:
    """
    DevOps Agent
    Responsible for deployment, monitoring, and automatic rollback
    """
    
    def __init__(self, k8s_client=None, monitoring_client=None):
        self.k8s_client = k8s_client
        self.monitoring_client = monitoring_client
        self.health_thresholds = {
            'error_rate': 0.01,  # 1%
            'latency_p99_ms': 500,
            'success_rate': 0.99  # 99%
        }
    
    async def deploy(
        self,
        code_changes: List[CodeChange],
        environment: str = 'staging',
        strategy: str = 'canary',
        context: Optional[Dict[str, Any]] = None
    ) -> DeploymentStatus:
        """
        Main entry point: Deploy code changes
        
        Args:
            code_changes: Approved code changes
            environment: Target environment (staging, production)
            strategy: Deployment strategy (blue_green, canary, rolling)
            context: Optional context (current version, traffic config, etc.)
        
        Returns:
            DeploymentStatus object
        """
        deployment_id = str(uuid.uuid4())
        
        status = DeploymentStatus(
            deployment_id=deployment_id,
            environment=environment,
            strategy=strategy,
            status='in_progress',
            started_at=datetime.utcnow()
        )
        
        try:
            # Step 1: Build container image
            print(f"[DevOps] Building image for deployment {deployment_id}...")
            image_tag = await self._build_image(code_changes, deployment_id)
            
            # Step 2: Execute deployment strategy
            if strategy == 'canary':
                await self._deploy_canary(image_tag, environment, deployment_id)
            elif strategy == 'blue_green':
                await self._deploy_blue_green(image_tag, environment, deployment_id)
            else:  # rolling
                await self._deploy_rolling(image_tag, environment, deployment_id)
            
            # Step 3: Monitor health metrics
            health_ok = await self._monitor_deployment_health(deployment_id, environment)
            
            if health_ok:
                status.status = 'completed'
                status.health_metrics = await self._get_health_metrics(deployment_id)
                print(f"[DevOps] Deployment {deployment_id} completed successfully")
            else:
                # Trigger automatic rollback
                status = await self._rollback(status, deployment_id, environment)
            
        except Exception as e:
            print(f"[DevOps] Deployment failed: {e}")
            status.status = 'failed'
            status = await self._rollback(status, deployment_id, environment, str(e))
        
        status.completed_at = datetime.utcnow()
        return status
    
    async def _build_image(
        self, 
        code_changes: List[CodeChange], 
        deployment_id: str
    ) -> str:
        """Build container image from code changes"""
        image_tag = f"app:{deployment_id[:8]}"
        
        # In real implementation:
        # 1. Create Docker context with changes
        # 2. Run docker build
        # 3. Push to registry
        
        await asyncio.sleep(0.2)  # Simulate build time
        
        return image_tag
    
    async def _deploy_canary(
        self, 
        image_tag: str, 
        environment: str, 
        deployment_id: str
    ):
        """Deploy using canary strategy"""
        print(f"[DevOps] Deploying canary {image_tag} to {environment}...")
        
        # In real implementation with K8s:
        # 1. Create canary deployment with 10% traffic
        # 2. Wait for stabilization
        # 3. Gradually increase traffic
        
        if self.k8s_client:
            await self.k8s_client.create_canary_deployment(
                image=image_tag,
                environment=environment,
                traffic_percentage=10
            )
        
        await asyncio.sleep(0.3)  # Simulate deployment
    
    async def _deploy_blue_green(
        self, 
        image_tag: str, 
        environment: str, 
        deployment_id: str
    ):
        """Deploy using blue-green strategy"""
        print(f"[DevOps] Deploying blue-green {image_tag} to {environment}...")
        
        if self.k8s_client:
            await self.k8s_client.create_deployment(
                image=image_tag,
                environment=f"{environment}-green",
                replicas=3
            )
        
        await asyncio.sleep(0.3)
    
    async def _deploy_rolling(
        self, 
        image_tag: str, 
        environment: str, 
        deployment_id: str
    ):
        """Deploy using rolling update strategy"""
        print(f"[DevOps] Rolling update {image_tag} to {environment}...")
        
        if self.k8s_client:
            await self.k8s_client.rolling_update(
                image=image_tag,
                environment=environment
            )
        
        await asyncio.sleep(0.3)
    
    async def _monitor_deployment_health(
        self, 
        deployment_id: str, 
        environment: str
    ) -> bool:
        """Monitor deployment health and detect issues"""
        print(f"[DevOps] Monitoring deployment health...")
        
        # Collect metrics over time window
        for _ in range(3):  # Check 3 times
            await asyncio.sleep(0.2)
            
            metrics = await self._get_health_metrics(deployment_id)
            
            # Check thresholds
            if metrics.get('error_rate', 0) > self.health_thresholds['error_rate']:
                print(f"[DevOps] High error rate detected: {metrics.get('error_rate')}")
                return False
            
            if metrics.get('latency_p99_ms', 0) > self.health_thresholds['latency_p99_ms']:
                print(f"[DevOps] High latency detected: {metrics.get('latency_p99_ms')}ms")
                return False
        
        return True
    
    async def _get_health_metrics(self, deployment_id: str) -> Dict[str, Any]:
        """Get current health metrics"""
        # In real implementation: query Prometheus/Datadog
        
        # Simulate metrics
        return {
            'error_rate': 0.005,  # 0.5%
            'latency_p99_ms': 250,
            'success_rate': 0.995,
            'requests_per_second': 1000,
            'cpu_utilization': 0.45,
            'memory_utilization': 0.60
        }
    
    async def _rollback(
        self,
        status: DeploymentStatus,
        deployment_id: str,
        environment: str,
        reason: Optional[str] = None
    ) -> DeploymentStatus:
        """Execute automatic rollback"""
        print(f"[DevOps] Initiating rollback for {deployment_id}...")
        
        status.rollback_triggered = True
        status.rollback_reason = reason or "Health check failed"
        status.status = 'rolled_back'
        
        if self.k8s_client:
            await self.k8s_client.rollback(environment)
        
        await asyncio.sleep(0.2)  # Simulate rollback
        
        print(f"[DevOps] Rollback completed for {deployment_id}")
        return status
    
    async def monitor_production(
        self,
        environment: str = 'production',
        duration_minutes: int = 30
    ) -> Dict[str, Any]:
        """Continuously monitor production environment"""
        print(f"[DevOps] Starting production monitoring for {duration_minutes} minutes...")
        
        alerts = []
        
        # Simulate continuous monitoring
        for i in range(duration_minutes):
            metrics = await self._get_health_metrics(f"prod-{i}")
            
            # Check for anomalies
            if metrics['error_rate'] > self.health_thresholds['error_rate']:
                alerts.append({
                    'type': 'high_error_rate',
                    'value': metrics['error_rate'],
                    'threshold': self.health_thresholds['error_rate'],
                    'timestamp': datetime.utcnow().isoformat()
                })
            
            await asyncio.sleep(0.1)  # Simulate per-minute check
        
        return {
            'status': 'completed',
            'alerts': alerts,
            'summary': {
                'total_alerts': len(alerts),
                'avg_error_rate': 0.005,
                'avg_latency_ms': 250
            }
        }


# Factory functions
def create_senior_agent(
    llm_config: Optional[Dict[str, Any]] = None,
    security_scanner_config: Optional[Dict[str, Any]] = None
) -> SeniorAgent:
    """Create and configure Senior Agent"""
    llm_client = None
    security_scanner = None
    
    return SeniorAgent(llm_client=llm_client, security_scanner=security_scanner)


def create_devops_agent(
    k8s_config: Optional[Dict[str, Any]] = None,
    monitoring_config: Optional[Dict[str, Any]] = None
) -> DevOpsAgent:
    """Create and configure DevOps Agent"""
    k8s_client = None
    monitoring_client = None
    
    return DevOpsAgent(k8s_client=k8s_client, monitoring_client=monitoring_client)
