"""
Dev Agent - Developer Agent
Executes code modifications in Docker sandbox with AST-based precision
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
    PreciseChangePlan, 
    CodeChange,
    WorkflowContext
)


@dataclass
class SandboxResult:
    """Result from executing code in sandbox"""
    success: bool
    output: str
    error_message: Optional[str] = None
    execution_time_ms: int = 0
    artifacts: Dict[str, Any] = field(default_factory=dict)


class DevAgent:
    """
    Developer Agent
    Responsible for implementing code changes based on PCP
    """
    
    def __init__(self, llm_client=None, sandbox_config=None):
        self.llm_client = llm_client
        self.sandbox_config = sandbox_config or {
            'image': 'python:3.11-slim',
            'timeout_seconds': 300,
            'memory_limit': '2GB'
        }
    
    async def implement_changes(
        self,
        mts: MachineTaskSpecification,
        pcp: PreciseChangePlan,
        context: Optional[Dict[str, Any]] = None
    ) -> List[CodeChange]:
        """
        Main entry point: Implement code changes based on PCP
        
        Args:
            mts: Machine Task Specification
            pcp: Precise Change Plan from Architect Agent
            context: Optional context (current file contents, git state, etc.)
        
        Returns:
            List of CodeChange objects
        """
        code_changes = []
        
        # Step 1: Prepare sandbox environment
        sandbox_id = await self._prepare_sandbox(context)
        
        try:
            # Step 2: Process affected files
            for file_entry in pcp.affected_files:
                change = await self._modify_file(file_entry, mts, pcp, context)
                if change:
                    code_changes.append(change)
            
            # Step 3: Create new files
            for file_entry in pcp.new_files:
                change = await self._create_file(file_entry, mts, pcp, context)
                if change:
                    code_changes.append(change)
            
            # Step 4: Delete files if needed
            for file_path in pcp.deleted_files:
                change = await self._delete_file(file_path, context)
                if change:
                    code_changes.append(change)
            
            # Step 5: Validate changes compile/build
            build_result = await self._validate_build(code_changes, sandbox_id)
            if not build_result.success:
                # Trigger self-healing
                healed_changes = await self._heal_build_errors(
                    code_changes, build_result.error_message, mts, pcp
                )
                code_changes = healed_changes
            
        finally:
            # Step 6: Cleanup sandbox
            await self._cleanup_sandbox(sandbox_id)
        
        return code_changes
    
    async def _prepare_sandbox(self, context: Optional[Dict[str, Any]] = None) -> str:
        """Prepare Docker sandbox environment"""
        sandbox_id = str(uuid.uuid4())
        
        # In real implementation, this would:
        # 1. Pull Docker image
        # 2. Mount source code
        # 3. Install dependencies
        # 4. Set up environment variables
        
        print(f"[DevAgent] Preparing sandbox {sandbox_id}...")
        
        # Simulate sandbox preparation
        await asyncio.sleep(0.1)
        
        return sandbox_id
    
    async def _modify_file(
        self,
        file_entry: Dict[str, Any],
        mts: MachineTaskSpecification,
        pcp: PreciseChangePlan,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[CodeChange]:
        """Modify an existing file"""
        file_path = file_entry['path']
        
        # Get current file content
        old_content = await self._get_file_content(file_path, context)
        
        # Generate new content using LLM
        if self.llm_client:
            new_content = await self._generate_modified_content(
                file_path, old_content, mts, pcp, file_entry
            )
        else:
            # Fallback: simple modification simulation
            new_content = self._simulate_modification(old_content, file_entry, mts)
        
        # Generate diff summary
        diff_summary = self._generate_diff_summary(file_path, old_content, new_content)
        
        return CodeChange(
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            change_type="modify",
            diff_summary=diff_summary
        )
    
    async def _create_file(
        self,
        file_entry: Dict[str, Any],
        mts: MachineTaskSpecification,
        pcp: PreciseChangePlan,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[CodeChange]:
        """Create a new file"""
        file_path = file_entry['path']
        
        # Generate file content using LLM
        if self.llm_client:
            content = await self._generate_new_file_content(
                file_path, mts, pcp, file_entry
            )
        else:
            # Fallback: generate template
            content = self._generate_file_template(file_path, file_entry, mts)
        
        diff_summary = f"Created new file with ~{len(content.splitlines())} lines"
        
        return CodeChange(
            file_path=file_path,
            old_content="",
            new_content=content,
            change_type="create",
            diff_summary=diff_summary
        )
    
    async def _delete_file(
        self,
        file_path: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[CodeChange]:
        """Delete a file"""
        old_content = await self._get_file_content(file_path, context)
        
        return CodeChange(
            file_path=file_path,
            old_content=old_content,
            new_content="",
            change_type="delete",
            diff_summary=f"Deleted file {file_path}"
        )
    
    async def _get_file_content(
        self, 
        file_path: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Get current content of a file"""
        if context and 'file_contents' in context:
            return context['file_contents'].get(file_path, "")
        
        # In real implementation, read from filesystem or git
        # Fallback: return empty string for new projects
        return ""
    
    async def _generate_modified_content(
        self,
        file_path: str,
        old_content: str,
        mts: MachineTaskSpecification,
        pcp: PreciseChangePlan,
        file_entry: Dict[str, Any]
    ) -> str:
        """Generate modified file content using LLM"""
        prompt = f"""You are an expert developer. Modify the following file to implement the requirement.

File: {file_path}
Reason: {file_entry.get('reason', 'Required change')}

Business Objective: {mts.business_objective}

Functional Requirements:
{json.dumps(mts.functional_requirements[:2], indent=2)}

Current Content:
```
{old_content}
```

Return ONLY the complete new content of the file. Do not include explanations.
"""
        response = await self.llm_client.generate(prompt, temperature=0.2)
        return self._extract_code_block(response)
    
    def _simulate_modification(
        self,
        old_content: str,
        file_entry: Dict[str, Any],
        mts: MachineTaskSpecification
    ) -> str:
        """Simulate file modification without LLM (for testing)"""
        if not old_content:
            # Create a basic Python module
            return f'''"""
Module: {file_entry["path"]}
Generated by DevAgent for: {mts.business_objective[:50]}
"""

def process_request(data):
    """Process incoming request according to requirements."""
    # TODO: Implement based on functional requirements
    return {{
        "status": "success",
        "data": data
    }}


def validate_input(data):
    """Validate input data."""
    if not data:
        raise ValueError("Input data cannot be empty")
    return True
'''
        # Append a comment about the change
        marker = f"\n# Modified for: {mts.business_objective[:50]}\n"
        return old_content + marker
    
    async def _generate_new_file_content(
        self,
        file_path: str,
        mts: MachineTaskSpecification,
        pcp: PreciseChangePlan,
        file_entry: Dict[str, Any]
    ) -> str:
        """Generate content for a new file using LLM"""
        prompt = f"""You are an expert developer. Create a new file to implement the requirement.

File Path: {file_path}
Purpose: {file_entry.get('reason', 'New functionality')}

Business Objective: {mts.business_objective}

Functional Requirements:
{json.dumps(mts.functional_requirements, indent=2)}

Create a complete, production-ready implementation. Include:
- Proper imports
- Type hints
- Docstrings
- Error handling

Return ONLY the complete file content. Do not include explanations.
"""
        response = await self.llm_client.generate(prompt, temperature=0.2)
        return self._extract_code_block(response)
    
    def _generate_file_template(
        self,
        file_path: str,
        file_entry: Dict[str, Any],
        mts: MachineTaskSpecification
    ) -> str:
        """Generate a file template without LLM (for testing)"""
        filename = file_path.split('/')[-1].replace('.py', '')
        
        return f'''"""
Module: {file_path}
Purpose: {file_entry.get('reason', 'New functionality')}
Generated by DevAgent for: {mts.business_objective[:50]}
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class {filename.title()}Result:
    """Result from {filename} operations."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


class {filename.title()}Service:
    """Service class for {filename} functionality."""
    
    def __init__(self):
        self.logger = logger
    
    async def process(self, input_data: Dict[str, Any]) -> {filename.title()}Result:
        """
        Process input data according to requirements.
        
        Args:
            input_data: Input data dictionary
            
        Returns:
            {filename.title()}Result with processed data
        """
        try:
            # TODO: Implement business logic based on MTS
            self.logger.info(f"Processing {{len(input_data)}} items")
            
            result = {{
                "status": "processed",
                "input_size": len(input_data)
            }}
            
            return {filename.title()}Result(success=True, data=result)
            
        except Exception as e:
            self.logger.error(f"Error processing: {{e}}")
            return {filename.title()}Result(success=False, error=str(e))
    
    def validate(self, data: Any) -> bool:
        """Validate input data."""
        if data is None:
            return False
        return True
'''
    
    def _generate_diff_summary(
        self,
        file_path: str,
        old_content: str,
        new_content: str
    ) -> str:
        """Generate a summary of changes"""
        old_lines = len(old_content.splitlines())
        new_lines = len(new_content.splitlines())
        
        if old_lines == 0:
            return f"Created new file with {new_lines} lines"
        elif new_lines == 0:
            return f"Deleted file with {old_lines} lines"
        else:
            diff = new_lines - old_lines
            sign = "+" if diff > 0 else ""
            return f"Modified: {old_lines} → {new_lines} lines ({sign}{diff})"
    
    def _extract_code_block(self, text: str) -> str:
        """Extract code from markdown code blocks"""
        import re
        pattern = r'```(?:\w+)?\n(.*?)```'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()
    
    async def _validate_build(
        self,
        code_changes: List[CodeChange],
        sandbox_id: str
    ) -> SandboxResult:
        """Validate that changes compile/build successfully"""
        print(f"[DevAgent] Validating build for {len(code_changes)} changes...")
        
        # In real implementation:
        # 1. Write changes to sandbox filesystem
        # 2. Run build/compile command
        # 3. Capture output
        
        # Simulate build validation
        await asyncio.sleep(0.1)
        
        # For demo: assume success unless there are obvious syntax errors
        for change in code_changes:
            if change.change_type == 'modify' or change.change_type == 'create':
                # Basic Python syntax check
                try:
                    compile(change.new_content, change.file_path, 'exec')
                except SyntaxError as e:
                    return SandboxResult(
                        success=False,
                        output="",
                        error_message=f"Syntax error in {change.file_path}: {e}",
                        execution_time_ms=50
                    )
        
        return SandboxResult(
            success=True,
            output="Build successful",
            execution_time_ms=150
        )
    
    async def _heal_build_errors(
        self,
        code_changes: List[CodeChange],
        error_message: str,
        mts: MachineTaskSpecification,
        pcp: PreciseChangePlan
    ) -> List[CodeChange]:
        """Attempt to heal build errors automatically"""
        print(f"[DevAgent] Healing build errors: {error_message}")
        
        # Parse error message to identify problematic file
        import re
        match = re.search(r'in ([\w/.]+)', error_message)
        if not match:
            # Cannot identify file, return original changes
            return code_changes
        
        error_file = match.group(1)
        
        # Find the problematic change
        for i, change in enumerate(code_changes):
            if change.file_path == error_file:
                # Attempt to fix using LLM
                if self.llm_client:
                    fixed_content = await self._fix_syntax_error(
                        change.new_content, error_message, mts
                    )
                    code_changes[i] = CodeChange(
                        file_path=change.file_path,
                        old_content=change.old_content,
                        new_content=fixed_content,
                        change_type=change.change_type,
                        diff_summary=change.diff_summary + " [HEALED]"
                    )
                break
        
        return code_changes
    
    async def _fix_syntax_error(
        self,
        content: str,
        error_message: str,
        mts: MachineTaskSpecification
    ) -> str:
        """Use LLM to fix syntax errors"""
        prompt = f"""Fix the syntax error in the following Python code.

Error: {error_message}

Code:
```
{content}
```

Return ONLY the corrected complete code. Do not include explanations.
"""
        response = await self.llm_client.generate(prompt, temperature=0.1)
        return self._extract_code_block(response)
    
    async def _cleanup_sandbox(self, sandbox_id: str):
        """Cleanup Docker sandbox"""
        print(f"[DevAgent] Cleaning up sandbox {sandbox_id}...")
        # In real implementation: stop and remove container
        await asyncio.sleep(0.05)


# Factory function
def create_dev_agent(
    llm_config: Optional[Dict[str, Any]] = None,
    sandbox_config: Optional[Dict[str, Any]] = None
) -> DevAgent:
    """Create and configure Dev Agent"""
    llm_client = None
    
    # TODO: Initialize actual LLM client based on config
    
    return DevAgent(llm_client=llm_client, sandbox_config=sandbox_config)
