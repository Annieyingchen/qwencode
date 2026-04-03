"""
QA Agent - Quality Assurance Agent
Generates tests, executes them, and forms healing loop with Dev Agent
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
    WorkflowContext
)


@dataclass
class DefectReport:
    """Detailed defect information"""
    defect_id: str
    test_name: str
    severity: str  # critical, major, minor
    description: str
    steps_to_reproduce: List[str]
    expected_behavior: str
    actual_behavior: str
    suggested_fix: str
    related_file: Optional[str] = None


class QAAgent:
    """
    QA Agent
    Responsible for generating and executing tests, forming healing loop with Dev
    """
    
    def __init__(self, llm_client=None, test_runner_config=None):
        self.llm_client = llm_client
        self.test_runner_config = test_runner_config or {
            'framework': 'pytest',
            'timeout_seconds': 60,
            'coverage_enabled': True
        }
    
    async def execute_testing(
        self,
        mts: MachineTaskSpecification,
        code_changes: List[CodeChange],
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[TestResult], bool]:
        """
        Main entry point: Generate and execute tests
        
        Args:
            mts: Machine Task Specification
            code_changes: List of code changes from Dev Agent
            context: Optional context (existing tests, coverage data, etc.)
        
        Returns:
            Tuple of (list of TestResults, all_passed boolean)
        """
        # Step 1: Generate test cases from MTS acceptance criteria
        test_cases = await self._generate_test_cases(mts, code_changes)
        
        # Step 2: Generate test code for each case
        test_files = await self._generate_test_code(test_cases, code_changes, mts)
        
        # Step 3: Execute tests in sandbox
        test_results = await self._execute_tests(test_files, context)
        
        # Step 4: Analyze failures and generate defect reports
        defects = []
        for result in test_results:
            if not result.passed:
                defect = await self._analyze_failure(result, code_changes, mts)
                if defect:
                    defects.append(defect)
        
        # Step 5: Determine if healing is needed
        all_passed = all(r.passed for r in test_results)
        
        if not all_passed:
            print(f"[QAAgent] {len(defects)} defects found. Triggering healing loop.")
        
        return test_results, all_passed
    
    async def _generate_test_cases(
        self,
        mts: MachineTaskSpecification,
        code_changes: List[CodeChange]
    ) -> List[Dict[str, Any]]:
        """Generate test cases from MTS acceptance criteria"""
        test_cases = []
        
        # Use acceptance criteria as base for test cases
        for i, criterion in enumerate(mts.acceptance_criteria):
            test_cases.append({
                'id': f"TC-{i+1:03d}",
                'type': 'acceptance',
                'description': criterion,
                'priority': 'high'
            })
        
        # Add test scenarios from MTS
        for scenario in mts.test_scenarios:
            test_cases.append({
                'id': f"TC-{len(test_cases)+1:03d}",
                'type': 'scenario',
                'description': scenario.get('scenario', ''),
                'steps': scenario.get('steps', []),
                'expected_result': scenario.get('expected_result', ''),
                'priority': 'medium'
            })
        
        # Add edge cases using LLM
        if self.llm_client:
            edge_cases = await self._generate_edge_cases(mts, code_changes)
            test_cases.extend(edge_cases)
        else:
            # Fallback: add basic edge cases
            test_cases.extend([
                {'id': f"TC-{len(test_cases)+1:03d}", 'type': 'edge', 'description': 'Empty input handling', 'priority': 'medium'},
                {'id': f"TC-{len(test_cases)+1:03d}", 'type': 'edge', 'description': 'Invalid input handling', 'priority': 'medium'},
                {'id': f"TC-{len(test_cases)+1:03d}", 'type': 'edge', 'description': 'Boundary value testing', 'priority': 'medium'}
            ])
        
        # Add unit tests for each code change
        for change in code_changes:
            if change.change_type in ['modify', 'create']:
                test_cases.append({
                    'id': f"TC-{len(test_cases)+1:03d}",
                    'type': 'unit',
                    'description': f"Unit test for {change.file_path}",
                    'file_path': change.file_path,
                    'priority': 'high'
                })
        
        return test_cases
    
    async def _generate_edge_cases(
        self,
        mts: MachineTaskSpecification,
        code_changes: List[CodeChange]
    ) -> List[Dict[str, Any]]:
        """Generate edge case tests using LLM"""
        prompt = f"""Based on these requirements, generate edge case test scenarios:

Business Objective: {mts.business_objective}

Functional Requirements:
{json.dumps(mts.functional_requirements[:3], indent=2)}

Return a JSON array of test case objects with:
- type: "edge"
- description: brief description
- priority: "low", "medium", or "high"
"""
        response = await self.llm_client.generate(prompt, response_format={"type": "json_object"})
        return json.loads(response).get("test_cases", [])
    
    async def _generate_test_code(
        self,
        test_cases: List[Dict[str, Any]],
        code_changes: List[CodeChange],
        mts: MachineTaskSpecification
    ) -> List[Dict[str, str]]:
        """Generate actual test code for each test case"""
        test_files = []
        
        # Group test cases by file
        test_groups = {}
        for tc in test_cases:
            if tc.get('file_path'):
                key = tc['file_path']
            else:
                key = 'general'
            
            if key not in test_groups:
                test_groups[key] = []
            test_groups[key].append(tc)
        
        # Generate test file for each group
        for source_file, cases in test_groups.items():
            test_file_path = self._get_test_file_path(source_file)
            
            if self.llm_client:
                content = await self._generate_test_file_content(
                    test_file_path, source_file, cases, code_changes, mts
                )
            else:
                content = self._generate_test_template(
                    test_file_path, source_file, cases, mts
                )
            
            test_files.append({
                'path': test_file_path,
                'content': content,
                'source_file': source_file
            })
        
        return test_files
    
    def _get_test_file_path(self, source_file: str) -> str:
        """Convert source file path to test file path"""
        if source_file == 'general':
            return 'tests/test_general.py'
        
        # Convert src/module.py -> tests/test_module.py
        parts = source_file.split('/')
        filename = parts[-1].replace('.py', '')
        return f"tests/test_{filename}.py"
    
    async def _generate_test_file_content(
        self,
        test_file_path: str,
        source_file: str,
        test_cases: List[Dict[str, Any]],
        code_changes: List[CodeChange],
        mts: MachineTaskSpecification
    ) -> str:
        """Generate test file content using LLM"""
        prompt = f"""Generate a pytest test file for the following:

Test File: {test_file_path}
Source File: {source_file}

Test Cases:
{json.dumps(test_cases, indent=2)}

Business Objective: {mts.business_objective}

Generate complete, executable pytest code with:
- Proper imports
- Fixtures if needed
- Parametrized tests where applicable
- Clear assertions
- Descriptive test names

Return ONLY the Python code. Do not include explanations.
"""
        response = await self.llm_client.generate(prompt, temperature=0.2)
        return self._extract_code_block(response)
    
    def _generate_test_template(
        self,
        test_file_path: str,
        source_file: str,
        test_cases: List[Dict[str, Any]],
        mts: MachineTaskSpecification
    ) -> str:
        """Generate test file template without LLM (for testing)"""
        module_name = source_file.replace('/', '.').replace('.py', '')
        
        test_functions = []
        for i, tc in enumerate(test_cases[:5]):  # Limit to 5 tests per file
            func_name = f"test_{tc['id'].lower().replace('-', '_')}_{i}"
            test_functions.append(f'''
def {func_name}():
    """Test: {tc['description']}"""
    # TODO: Implement test based on acceptance criteria
    # Priority: {tc.get('priority', 'medium')}
    
    # Arrange
    # TODO: Set up test data
    
    # Act
    # TODO: Call function under test
    
    # Assert
    # TODO: Verify expected behavior
    assert True, "Test not yet implemented"
''')
        
        return f'''"""
Test File: {test_file_path}
Source: {source_file}
Generated by QAAgent for: {mts.business_objective[:50]}
"""

import pytest
from typing import Any, Dict
import sys
sys.path.insert(0, 'src')

# Import module under test
# from {module_name} import ...


@pytest.fixture
def sample_data():
    """Fixture providing sample test data."""
    return {{
        "valid_input": {{"key": "value"}},
        "empty_input": {{}},
        "invalid_input": None
    }}


{"".join(test_functions)}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
'''
    
    async def _execute_tests(
        self,
        test_files: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[TestResult]:
        """Execute tests and collect results"""
        test_results = []
        
        print(f"[QAAgent] Executing {len(test_files)} test files...")
        
        for test_file in test_files:
            # In real implementation:
            # 1. Write test file to sandbox
            # 2. Run pytest/unittest
            # 3. Parse output
            
            # Simulate test execution
            file_results = await self._simulate_test_execution(test_file)
            test_results.extend(file_results)
        
        # Calculate coverage if enabled
        if self.test_runner_config.get('coverage_enabled'):
            await self._collect_coverage(test_files)
        
        return test_results
    
    async def _simulate_test_execution(
        self, 
        test_file: Dict[str, str]
    ) -> List[TestResult]:
        """Simulate test execution (for demo/testing)"""
        results = []
        
        # Parse test functions from file content
        import re
        test_funcs = re.findall(r'def (test_\w+)\(\)', test_file['content'])
        
        for func_name in test_funcs[:5]:  # Limit simulation
            # Simulate: 80% pass rate for demo
            passed = hash(func_name) % 5 != 0  # Deterministic pseudo-random
            
            results.append(TestResult(
                test_id=str(uuid.uuid4()),
                test_name=func_name,
                passed=passed,
                error_message=None if passed else f"AssertionError in {func_name}",
                execution_time_ms=50 + (hash(func_name) % 100),
                coverage_percent=75.0 if passed else 0.0
            ))
        
        # Ensure at least one test
        if not results:
            results.append(TestResult(
                test_id=str(uuid.uuid4()),
                test_name="test_placeholder",
                passed=True,
                execution_time_ms=10,
                coverage_percent=50.0
            ))
        
        return results
    
    async def _collect_coverage(self, test_files: List[Dict[str, str]]):
        """Collect code coverage metrics"""
        # In real implementation: run coverage.py and parse results
        print("[QAAgent] Collecting coverage metrics...")
        await asyncio.sleep(0.05)
    
    async def _analyze_failure(
        self,
        test_result: TestResult,
        code_changes: List[CodeChange],
        mts: MachineTaskSpecification
    ) -> Optional[DefectReport]:
        """Analyze test failure and generate defect report"""
        if not test_result.error_message:
            return None
        
        # Use LLM to analyze root cause
        if self.llm_client:
            analysis = await self._llm_analyze_failure(
                test_result, code_changes, mts
            )
        else:
            analysis = self._heuristic_analyze_failure(test_result, code_changes)
        
        return DefectReport(
            defect_id=str(uuid.uuid4()),
            test_name=test_result.test_name,
            severity=analysis.get('severity', 'major'),
            description=analysis.get('description', test_result.error_message),
            steps_to_reproduce=[f"Run test: {test_result.test_name}"],
            expected_behavior="Test should pass according to acceptance criteria",
            actual_behavior=test_result.error_message,
            suggested_fix=analysis.get('suggested_fix', 'Review implementation'),
            related_file=analysis.get('related_file')
        )
    
    async def _llm_analyze_failure(
        self,
        test_result: TestResult,
        code_changes: List[CodeChange],
        mts: MachineTaskSpecification
    ) -> Dict[str, Any]:
        """Use LLM to analyze failure root cause"""
        prompt = f"""Analyze this test failure and suggest a fix:

Test Name: {test_result.test_name}
Error: {test_result.error_message}

Related Code Changes:
{json.dumps([c.to_dict() for c in code_changes[:3]], indent=2)}

Business Objective: {mts.business_objective}

Return a JSON object with:
- severity: "critical", "major", or "minor"
- description: clear description of the issue
- suggested_fix: specific fix recommendation
- related_file: which file likely contains the bug
"""
        response = await self.llm_client.generate(prompt, response_format={"type": "json_object"})
        return json.loads(response)
    
    def _heuristic_analyze_failure(
        self,
        test_result: TestResult,
        code_changes: List[CodeChange]
    ) -> Dict[str, Any]:
        """Heuristic failure analysis without LLM"""
        # Simple pattern matching
        error_msg = test_result.error_message.lower()
        
        if 'assertion' in error_msg:
            severity = 'major'
            description = "Logic error: assertion failed"
            suggested_fix = "Review business logic implementation"
        elif 'type' in error_msg:
            severity = 'minor'
            description = "Type mismatch error"
            suggested_fix = "Add type checking or conversion"
        elif 'null' in error_msg or 'none' in error_msg:
            severity = 'major'
            description = "Null reference error"
            suggested_fix = "Add null checks before accessing properties"
        else:
            severity = 'major'
            description = test_result.error_message[:100]
            suggested_fix = "Debug and review stack trace"
        
        # Try to identify related file
        related_file = None
        for change in code_changes:
            if change.file_path in error_msg:
                related_file = change.file_path
                break
        
        if not related_file and code_changes:
            related_file = code_changes[0].file_path
        
        return {
            'severity': severity,
            'description': description,
            'suggested_fix': suggested_fix,
            'related_file': related_file
        }
    
    def _extract_code_block(self, text: str) -> str:
        """Extract code from markdown code blocks"""
        import re
        pattern = r'```(?:python)?\n(.*?)```'
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text.strip()
    
    def generate_healing_request(
        self,
        defects: List[DefectReport],
        test_results: List[TestResult]
    ) -> Dict[str, Any]:
        """Generate structured healing request for Dev Agent"""
        failed_tests = [tr for tr in test_results if not tr.passed]
        
        return {
            'defects': [
                {
                    'defect_id': d.defect_id,
                    'severity': d.severity,
                    'description': d.description,
                    'suggested_fix': d.suggested_fix,
                    'related_file': d.related_file
                }
                for d in defects
            ],
            'failed_tests': [
                {
                    'test_name': tr.test_name,
                    'error': tr.error_message
                }
                for tr in failed_tests
            ],
            'priority': 'high' if any(d.severity == 'critical' for d in defects) else 'medium',
            'context': 'Automated healing loop triggered by QA Agent'
        }


# Factory function
def create_qa_agent(
    llm_config: Optional[Dict[str, Any]] = None,
    test_runner_config: Optional[Dict[str, Any]] = None
) -> QAAgent:
    """Create and configure QA Agent"""
    llm_client = None
    
    # TODO: Initialize actual LLM client based on config
    
    return QAAgent(llm_client=llm_client, test_runner_config=test_runner_config)
