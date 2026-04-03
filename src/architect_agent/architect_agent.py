"""
Architect Agent - System Architecture Agent
Generates Precise Change Plans (PCP) using RAG and impact analysis
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import uuid
from datetime import datetime

import sys
sys.path.insert(0, '/workspace/src')
from core.models import MachineTaskSpecification, PreciseChangePlan, WorkflowContext


@dataclass
class FileImpact:
    """Represents the impact on a file"""
    file_path: str
    change_type: str  # modify, create, delete
    reason: str
    estimated_lines_changed: int
    risk_level: str  # low, medium, high
    dependencies_affected: List[str] = field(default_factory=list)


class ArchitectAgent:
    """
    Architect Agent
    Responsible for analyzing requirements and generating precise change plans
    """
    
    def __init__(self, llm_client=None, vector_store=None, codebase_index=None):
        self.llm_client = llm_client
        self.vector_store = vector_store
        self.codebase_index = codebase_index  # Code structure index (AST-based)
    
    async def design_architecture(
        self, 
        mts: MachineTaskSpecification,
        context: Optional[Dict[str, Any]] = None
    ) -> PreciseChangePlan:
        """
        Main entry point: Analyze MTS and produce Precise Change Plan
        
        Args:
            mts: Machine Task Specification from PM Agent
            context: Optional context (current codebase state, recent changes, etc.)
        
        Returns:
            PreciseChangePlan object
        """
        # Step 1: RAG-based retrieval of similar architectural patterns
        similar_patterns = await self._retrieve_architectural_patterns(mts)
        
        # Step 2: Analyze current codebase structure
        codebase_analysis = await self._analyze_codebase(mts, context)
        
        # Step 3: Identify affected components via call graph analysis
        affected_components = self._identify_affected_components(mts, codebase_analysis)
        
        # Step 4: Generate precise file-level change plan
        file_impacts = await self._generate_file_impacts(mts, affected_components)
        
        # Step 5: Assess risks and complexity
        risk_assessment = self._assess_risks(file_impacts, mts)
        
        # Step 6: Build Precise Change Plan
        pcp = self._build_precise_change_plan(
            mts, file_impacts, risk_assessment, similar_patterns
        )
        
        return pcp
    
    async def _retrieve_architectural_patterns(
        self, 
        mts: MachineTaskSpecification
    ) -> List[Dict[str, Any]]:
        """Retrieve similar architectural patterns from history via RAG"""
        if not self.vector_store:
            return []
        
        try:
            # Search for similar requirements and their architectural solutions
            query = f"{mts.business_objective}\n" + "\n".join(
                [fr['description'] for fr in mts.functional_requirements[:3]]
            )
            
            results = await self.vector_store.similarity_search(
                query=query,
                k=5,
                filter={"type": "architectural_pattern"}
            )
            
            return [
                {
                    "pattern_name": doc.metadata.get("pattern_name", ""),
                    "description": doc.metadata.get("description", ""),
                    "files_changed": doc.metadata.get("files_changed", []),
                    "lessons_learned": doc.metadata.get("lessons", []),
                    "anti_patterns": doc.metadata.get("anti_patterns", [])
                }
                for doc in results
            ]
        except Exception as e:
            print(f"RAG pattern retrieval failed: {e}")
            return []
    
    async def _analyze_codebase(
        self, 
        mts: MachineTaskSpecification,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Analyze current codebase structure"""
        if not self.codebase_index:
            # Fallback: basic analysis without AST index
            return {
                "modules": [],
                "dependencies": {},
                "recent_changes": context.get("recent_changes", []) if context else []
            }
        
        try:
            # Use AST-based index to understand codebase structure
            modules = await self.codebase_index.get_modules()
            dependencies = await self.codebase_index.get_dependency_graph()
            
            # Find modules related to the requirement
            relevant_modules = await self._find_relevant_modules(mts, modules)
            
            return {
                "modules": modules,
                "dependencies": dependencies,
                "relevant_modules": relevant_modules,
                "recent_changes": context.get("recent_changes", []) if context else []
            }
        except Exception as e:
            print(f"Codebase analysis failed: {e}")
            return {"modules": [], "dependencies": {}, "relevant_modules": []}
    
    async def _find_relevant_modules(
        self, 
        mts: MachineTaskSpecification,
        modules: List[Dict[str, Any]]
    ) -> List[str]:
        """Find modules relevant to the requirement"""
        if not self.llm_client:
            # Fallback: keyword matching
            keywords = set()
            for fr in mts.functional_requirements:
                keywords.update(fr['description'].lower().split())
            
            relevant = []
            for module in modules:
                module_name_lower = module.get('name', '').lower()
                if any(kw in module_name_lower for kw in keywords):
                    relevant.append(module['path'])
            return relevant[:10]  # Limit to top 10
        
        # Use LLM for semantic matching
        prompt = f"""Given these modules and the following requirement, identify which modules are likely affected:

Requirement: {mts.business_objective}

Modules: {[m['path'] for m in modules]}

Return a JSON list of module paths that need modification.
"""
        response = await self.llm_client.generate(prompt, response_format={"type": "json_object"})
        return json.loads(response).get("affected_modules", [])
    
    def _identify_affected_components(
        self, 
        mts: MachineTaskSpecification,
        codebase_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Identify components affected by the change using call graph analysis"""
        affected = {
            'direct': [],
            'transitive': [],
            'external_services': []
        }
        
        # Direct impacts: modules explicitly mentioned or matched
        direct_modules = codebase_analysis.get('relevant_modules', [])
        affected['direct'] = direct_modules
        
        # Transitive impacts: modules that depend on direct modules
        dependencies = codebase_analysis.get('dependencies', {})
        for module in direct_modules:
            # Find modules that import/call this module
            dependents = self._find_dependents(module, dependencies)
            affected['transitive'].extend(dependents)
        
        # External service impacts
        for fr in mts.functional_requirements:
            if 'api' in fr['description'].lower() or 'service' in fr['description'].lower():
                affected['external_services'].append(fr['description'])
        
        # Deduplicate
        affected['transitive'] = list(set(affected['transitive']) - set(affected['direct']))
        
        return affected
    
    def _find_dependents(
        self, 
        module: str, 
        dependencies: Dict[str, List[str]]
    ) -> List[str]:
        """Find modules that depend on the given module"""
        dependents = []
        for mod, deps in dependencies.items():
            if module in deps:
                dependents.append(mod)
        return dependents
    
    async def _generate_file_impacts(
        self,
        mts: MachineTaskSpecification,
        affected_components: Dict[str, Any]
    ) -> List[FileImpact]:
        """Generate detailed file-level impact analysis"""
        file_impacts = []
        
        # Process direct impacts
        for component in affected_components['direct']:
            impact = await self._analyze_file_change(component, mts, "direct")
            if impact:
                file_impacts.append(impact)
        
        # Process transitive impacts (usually lower risk)
        for component in affected_components['transitive'][:5]:  # Limit transitive analysis
            impact = await self._analyze_file_change(component, mts, "transitive")
            if impact:
                impact.risk_level = "low"  # Transitive changes are usually minor
                file_impacts.append(impact)
        
        # Identify new files needed
        new_files = await self._identify_new_files(mts)
        for new_file in new_files:
            file_impacts.append(FileImpact(
                file_path=new_file['path'],
                change_type="create",
                reason=new_file['reason'],
                estimated_lines_changed=new_file.get('estimated_lines', 100),
                risk_level="medium"
            ))
        
        return file_impacts
    
    async def _analyze_file_change(
        self,
        file_path: str,
        mts: MachineTaskSpecification,
        impact_type: str
    ) -> Optional[FileImpact]:
        """Analyze what changes are needed for a specific file"""
        if not self.llm_client:
            # Fallback: heuristic-based estimation
            return FileImpact(
                file_path=file_path,
                change_type="modify",
                reason=f"Affected by requirement: {mts.business_objective[:50]}...",
                estimated_lines_changed=20,
                risk_level="medium" if impact_type == "direct" else "low",
                dependencies_affected=[]
            )
        
        prompt = f"""Analyze the file '{file_path}' and determine what changes are needed for this requirement:

Requirement: {mts.business_objective}

Functional Requirements:
{json.dumps(mts.functional_requirements[:2], indent=2)}

Return a JSON object with:
- change_type: "modify", "delete", or "no_change"
- reason: brief explanation
- estimated_lines_changed: number
- risk_level: "low", "medium", or "high"
"""
        response = await self.llm_client.generate(prompt, response_format={"type": "json_object"})
        data = json.loads(response)
        
        if data.get('change_type') == 'no_change':
            return None
        
        return FileImpact(
            file_path=file_path,
            change_type=data.get('change_type', 'modify'),
            reason=data.get('reason', 'Required change'),
            estimated_lines_changed=data.get('estimated_lines_changed', 20),
            risk_level=data.get('risk_level', 'medium'),
            dependencies_affected=[]
        )
    
    async def _identify_new_files(
        self, 
        mts: MachineTaskSpecification
    ) -> List[Dict[str, Any]]:
        """Identify new files that need to be created"""
        if not self.llm_client:
            # Fallback: check if any FR suggests new functionality
            new_files = []
            for fr in mts.functional_requirements:
                if 'new' in fr['description'].lower() or 'add' in fr['description'].lower():
                    new_files.append({
                        'path': f'src/new_feature_{len(new_files)}.py',
                        'reason': f"New functionality: {fr['description'][:50]}",
                        'estimated_lines': 50
                    })
            return new_files[:3]
        
        prompt = f"""Based on these requirements, identify any new files that need to be created:

Business Objective: {mts.business_objective}

Functional Requirements:
{json.dumps(mts.functional_requirements, indent=2)}

Return a JSON array of objects with:
- path: suggested file path
- reason: why this file is needed
- estimated_lines: estimated lines of code
"""
        response = await self.llm_client.generate(prompt, response_format={"type": "json_object"})
        return json.loads(response).get("new_files", [])
    
    def _assess_risks(
        self,
        file_impacts: List[FileImpact],
        mts: MachineTaskSpecification
    ) -> Dict[str, Any]:
        """Assess overall risk of the change plan"""
        risk_assessment = {
            'overall_risk': 'low',
            'risk_factors': [],
            'mitigation_strategies': [],
            'rollback_complexity': 'low'
        }
        
        # Count high-risk files
        high_risk_count = sum(1 for f in file_impacts if f.risk_level == 'high')
        total_lines = sum(f.estimated_lines_changed for f in file_impacts)
        
        if high_risk_count > 2 or total_lines > 500:
            risk_assessment['overall_risk'] = 'high'
            risk_assessment['risk_factors'].append("Large scope change")
            risk_assessment['mitigation_strategies'].append("Consider breaking into smaller PRs")
        elif high_risk_count > 0 or total_lines > 200:
            risk_assessment['overall_risk'] = 'medium'
            risk_assessment['risk_factors'].append("Moderate scope change")
        
        # Check for sensitive file types
        sensitive_patterns = ['auth', 'payment', 'security', 'database', 'migration']
        for impact in file_impacts:
            if any(pattern in impact.file_path.lower() for pattern in sensitive_patterns):
                risk_assessment['risk_factors'].append(f"Sensitive file modified: {impact.file_path}")
                risk_assessment['mitigation_strategies'].append("Extra review required for security implications")
                if risk_assessment['overall_risk'] == 'low':
                    risk_assessment['overall_risk'] = 'medium'
        
        # Assess rollback complexity
        if any('migration' in f.file_path.lower() or 'schema' in f.file_path.lower() for f in file_impacts):
            risk_assessment['rollback_complexity'] = 'high'
            risk_assessment['mitigation_strategies'].append("Ensure backward-compatible migrations")
        
        return risk_assessment
    
    def _build_precise_change_plan(
        self,
        mts: MachineTaskSpecification,
        file_impacts: List[FileImpact],
        risk_assessment: Dict[str, Any],
        similar_patterns: List[Dict[str, Any]]
    ) -> PreciseChangePlan:
        """Build the final Precise Change Plan"""
        affected_files = []
        new_files = []
        deleted_files = []
        
        for impact in file_impacts:
            file_entry = {
                'path': impact.file_path,
                'change_type': impact.change_type,
                'reason': impact.reason,
                'estimated_lines_changed': impact.estimated_lines_changed,
                'risk_level': impact.risk_level,
                'dependencies_affected': impact.dependencies_affected
            }
            
            if impact.change_type == 'create':
                new_files.append(file_entry)
            elif impact.change_type == 'delete':
                deleted_files.append(impact.file_path)
            else:
                affected_files.append(file_entry)
        
        # Estimate complexity
        total_files = len(affected_files) + len(new_files)
        high_risk_count = sum(1 for f in file_impacts if f.risk_level == 'high')
        
        if total_files > 10 or high_risk_count > 3:
            complexity = 'high'
        elif total_files > 5 or high_risk_count > 0:
            complexity = 'medium'
        else:
            complexity = 'low'
        
        return PreciseChangePlan(
            mts_id=mts.id,
            affected_files=affected_files,
            new_files=new_files,
            deleted_files=deleted_files,
            dependency_changes=[],  # Could be populated with dependency analysis
            risk_assessment=risk_assessment,
            estimated_complexity=complexity
        )
    
    def validate_change_plan(self, pcp: PreciseChangePlan) -> Tuple[bool, List[str]]:
        """Validate the change plan meets precision requirements"""
        issues = []
        
        # Check file count (should be focused)
        total_files = len(pcp.affected_files) + len(pcp.new_files)
        if total_files > 15:
            issues.append(f"Too many files ({total_files}). Consider breaking into smaller changes.")
        
        # Check for risky patterns
        for file_entry in pcp.affected_files:
            if file_entry.get('risk_level') == 'high':
                issues.append(f"High-risk file: {file_entry['path']}. Ensure thorough review.")
        
        # Check risk assessment completeness
        if not pcp.risk_assessment.get('mitigation_strategies'):
            issues.append("Missing mitigation strategies for identified risks.")
        
        return len(issues) == 0, issues


# Factory function
def create_architect_agent(
    llm_config: Optional[Dict[str, Any]] = None,
    vector_store_config: Optional[Dict[str, Any]] = None,
    codebase_index_config: Optional[Dict[str, Any]] = None
) -> ArchitectAgent:
    """Create and configure Architect Agent"""
    llm_client = None
    vector_store = None
    codebase_index = None
    
    # TODO: Initialize actual services based on config
    
    return ArchitectAgent(
        llm_client=llm_client,
        vector_store=vector_store,
        codebase_index=codebase_index
    )
