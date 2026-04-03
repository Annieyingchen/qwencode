"""
PM Agent - Product Manager Agent
Converts unstructured requirements into Machine Task Specifications (MTS)
"""

import re
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import uuid
from datetime import datetime

# Import core models
import sys
sys.path.insert(0, '/workspace/src')
from core.models import MachineTaskSpecification, WorkflowContext


@dataclass
class AmbiguityDetection:
    """Detected ambiguity in requirements"""
    text_segment: str
    ambiguity_type: str  # vague, incomplete, contradictory, missing_context
    severity: str  # low, medium, high
    suggested_clarification: str


class PMAgent:
    """
    Product Manager Agent
    Responsible for parsing requirements and generating structured MTS
    """
    
    def __init__(self, llm_client=None, vector_store=None):
        self.llm_client = llm_client
        self.vector_store = vector_store
        self.ambiguity_patterns = {
            'vague': [r'\b可能\b', r'\b大概\b', r'\b也许\b', r'\b差不多\b', 
                     r'\bmight\b', r'\bmaybe\b', r'\bprobably\b', r'\broughly\b'],
            'incomplete': [r'\b等\b', r'\b等等\b', r'\b其他\b', r'\band so on\b', r'\betc\b'],
            'conditional': [r'\b如果\b', r'\b假如\b', r'\bwhen\b', r'\bif\b']
        }
    
    async def analyze_requirement(
        self, 
        raw_requirement: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> MachineTaskSpecification:
        """
        Main entry point: Analyze raw requirement and produce MTS
        
        Args:
            raw_requirement: Unstructured requirement text
            context: Optional context (screenshots OCR, attached docs, etc.)
        
        Returns:
            MachineTaskSpecification object
        """
        # Step 1: Multi-modal parsing (text + OCR if needed)
        parsed_content = await self._parse_multimodal(raw_requirement, context)
        
        # Step 2: Retrieve historical patterns via RAG
        historical_examples = await self._retrieve_historical_patterns(parsed_content)
        
        # Step 3: Detect ambiguities
        ambiguities = self._detect_ambiguities(parsed_content)
        
        # Step 4: Generate structured MTS using LLM
        mts = await self._generate_mts(parsed_content, historical_examples, ambiguities)
        
        # Step 5: Calculate confidence score
        mts.confidence_score = self._calculate_confidence_score(mts, ambiguities)
        
        # Step 6: Validate output schema
        self._validate_mts_schema(mts)
        
        return mts
    
    async def _parse_multimodal(
        self, 
        text: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Parse multi-modal inputs (text, OCR, documents)"""
        content_parts = [text]
        
        if context:
            # Handle OCR from screenshots
            if 'ocr_text' in context:
                content_parts.append(f"\n[OCR Extracted]:\n{context['ocr_text']}")
            
            # Handle attached documents
            if 'documents' in context:
                for doc in context['documents']:
                    content_parts.append(f"\n[Document: {doc.get('name', 'unknown')}]:\n{doc.get('content', '')}")
            
            # Handle user context (Jira ticket, PR description, etc.)
            if 'metadata' in context:
                meta = context['metadata']
                content_parts.append(f"\n[Context]: Project={meta.get('project', 'N/A')}, "
                                   f"Priority={meta.get('priority', 'N/A')}, "
                                   f"Stakeholders={meta.get('stakeholders', [])}")
        
        return "\n".join(content_parts)
    
    async def _retrieve_historical_patterns(self, content: str) -> List[Dict[str, Any]]:
        """Retrieve similar historical requirements via RAG"""
        if not self.vector_store:
            return []
        
        try:
            # Embed the content and search for similar historical requirements
            results = await self.vector_store.similarity_search(
                query=content,
                k=3,
                filter={"quality_score": {"$gte": 0.8}}  # Only high-quality examples
            )
            
            return [
                {
                    "original_requirement": doc.metadata.get("requirement", ""),
                    "mts_example": doc.metadata.get("mts", {}),
                    "lessons_learned": doc.metadata.get("lessons", [])
                }
                for doc in results
            ]
        except Exception as e:
            print(f"RAG retrieval failed: {e}")
            return []
    
    def _detect_ambiguities(self, content: str) -> List[AmbiguityDetection]:
        """Detect ambiguous statements in the requirement"""
        ambiguities = []
        
        for amb_type, patterns in self.ambiguity_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Get surrounding context (±20 chars)
                    start = max(0, match.start() - 20)
                    end = min(len(content), match.end() + 20)
                    segment = content[start:end].strip()
                    
                    severity = self._assess_ambiguity_severity(match.group(), amb_type)
                    clarification = self._generate_clarification_question(match.group(), amb_type, segment)
                    
                    ambiguities.append(AmbiguityDetection(
                        text_segment=segment,
                        ambiguity_type=amb_type,
                        severity=severity,
                        suggested_clarification=clarification
                    ))
        
        # Check for missing components
        missing = self._check_missing_components(content)
        ambiguities.extend(missing)
        
        return ambiguities
    
    def _assess_ambiguity_severity(self, matched_text: str, amb_type: str) -> str:
        """Assess severity of ambiguity"""
        high_severity_keywords = ['可能', '大概', 'might', 'maybe']
        if any(k in matched_text.lower() for k in high_severity_keywords):
            return 'high'
        elif amb_type == 'incomplete':
            return 'medium'
        return 'low'
    
    def _generate_clarification_question(
        self, 
        matched_text: str, 
        amb_type: str, 
        segment: str
    ) -> str:
        """Generate a clarifying question for the ambiguity"""
        questions = {
            'vague': f"请明确'{matched_text}'的具体含义或量化标准是什么？",
            'incomplete': f"请完整列出'{segment}'中省略的内容，避免使用'等'字。",
            'conditional': f"请说明'{matched_text}'条件下的具体行为和备选方案。"
        }
        return questions.get(amb_type, f"请澄清：{segment}")
    
    def _check_missing_components(self, content: str) -> List[AmbiguityDetection]:
        """Check for commonly missing requirement components"""
        missing = []
        
        required_sections = [
            ('user story', '用户故事'),
            ('acceptance criteria', '验收标准'),
            ('input', '输入'),
            ('output', '输出'),
            ('error handling', '错误处理')
        ]
        
        content_lower = content.lower()
        for key, key_cn in required_sections:
            if key not in content_lower and key_cn not in content:
                missing.append(AmbiguityDetection(
                    text_segment="[整体需求]",
                    ambiguity_type='incomplete',
                    severity='medium',
                    suggested_clarification=f"需求中缺少{key_cn}，请补充。"
                ))
        
        return missing
    
    async def _generate_mts(
        self,
        content: str,
        historical_examples: List[Dict[str, Any]],
        ambiguities: List[AmbiguityDetection]
    ) -> MachineTaskSpecification:
        """Generate Machine Task Specification using LLM"""
        
        # Build prompt with few-shot examples
        prompt = self._build_mts_generation_prompt(content, historical_examples, ambiguities)
        
        if self.llm_client:
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.3,  # Lower temperature for structured output
                response_format={"type": "json_object"}
            )
            mts_data = json.loads(response)
        else:
            # Fallback: Basic template-based generation (for testing)
            mts_data = self._fallback_mts_generation(content, ambiguities)
        
        return MachineTaskSpecification(
            business_objective=mts_data.get("business_objective", ""),
            functional_requirements=mts_data.get("functional_requirements", []),
            non_functional_requirements=mts_data.get("non_functional_requirements", {}),
            acceptance_criteria=mts_data.get("acceptance_criteria", []),
            dependencies=mts_data.get("dependencies", []),
            test_scenarios=mts_data.get("test_scenarios", []),
            ambiguities=[
                {
                    "text_segment": a.text_segment,
                    "ambiguity_type": a.ambiguity_type,
                    "severity": a.severity,
                    "suggested_clarification": a.suggested_clarification
                }
                for a in ambiguities
            ],
            confidence_score=0.0  # Will be calculated later
        )
    
    def _build_mts_generation_prompt(
        self,
        content: str,
        historical_examples: List[Dict[str, Any]],
        ambiguities: List[AmbiguityDetection]
    ) -> str:
        """Build the prompt for MTS generation"""
        
        examples_section = ""
        if historical_examples:
            examples_section = "\n\n参考历史高质量需求模式:\n"
            for i, ex in enumerate(historical_examples[:2], 1):
                examples_section += f"\n示例{i}:\n{json.dumps(ex['mts_example'], ensure_ascii=False, indent=2)}"
        
        ambiguities_section = ""
        if ambiguities:
            ambiguities_section = "\n\n检测到的歧义点 (请在生成时标注):\n"
            for a in ambiguities:
                ambiguities_section += f"- [{a.severity}] {a.text_segment}: {a.suggested_clarification}\n"
        
        prompt = f"""你是一位资深产品经理，请将以下需求转化为结构化的机器任务书(MTS)。

原始需求:
{content}
{examples_section}
{ambiguities_section}

请严格按照以下 JSON Schema 输出:
{{
    "business_objective": "业务目标描述",
    "functional_requirements": [
        {{
            "id": "FR-001",
            "description": "功能描述",
            "inputs": ["输入列表"],
            "outputs": ["输出列表"],
            "preconditions": ["前置条件"]
        }}
    ],
    "non_functional_requirements": {{
        "performance": "性能要求",
        "security": "安全要求",
        "scalability": "扩展性要求"
    }},
    "acceptance_criteria": ["验收标准列表"],
    "dependencies": ["依赖服务列表"],
    "test_scenarios": [
        {{
            "scenario": "测试场景",
            "steps": ["步骤"],
            "expected_result": "期望结果"
        }}
    ]
}}

注意:
1. 功能需求必须包含明确的输入/输出
2. 验收标准必须是可验证的
3. 如有歧义，在 ambiguities 字段中标注（已在上方列出）
"""
        return prompt
    
    def _fallback_mts_generation(
        self, 
        content: str, 
        ambiguities: List[AmbiguityDetection]
    ) -> Dict[str, Any]:
        """Fallback MTS generation without LLM (for testing/demo)"""
        # Simple heuristic-based extraction
        lines = content.split('\n')
        
        functional_requirements = []
        acceptance_criteria = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith(('功能', 'Feature', '- [ ]')):
                functional_requirements.append({
                    "id": f"FR-{len(functional_requirements)+1:03d}",
                    "description": line.lstrip('功能Feature- []').strip(),
                    "inputs": [],
                    "outputs": [],
                    "preconditions": []
                })
            elif line.startswith(('验收', 'Acceptance', '- [x]')):
                acceptance_criteria.append(line.lstrip('验收 Acceptance- []').strip())
        
        return {
            "business_objective": lines[0] if lines else "未明确",
            "functional_requirements": functional_requirements or [{"id": "FR-001", "description": content[:200], "inputs": [], "outputs": [], "preconditions": []}],
            "non_functional_requirements": {
                "performance": "响应时间 < 500ms",
                "security": "符合 OWASP Top 10",
                "scalability": "支持水平扩展"
            },
            "acceptance_criteria": acceptance_criteria or ["功能正常工作"],
            "dependencies": [],
            "test_scenarios": [{
                "scenario": "主流程测试",
                "steps": ["执行主要功能"],
                "expected_result": "功能按预期工作"
            }]
        }
    
    def _calculate_confidence_score(
        self, 
        mts: MachineTaskSpecification, 
        ambiguities: List[AmbiguityDetection]
    ) -> float:
        """
        Calculate confidence score based on:
        - Completeness
        - Consistency
        - Testability
        - Semantic coverage
        """
        scores = {
            'completeness': 0.0,
            'consistency': 0.0,
            'testability': 0.0,
            'semantic_coverage': 0.0
        }
        
        # Completeness: Check if all required fields are populated
        required_fields = [
            mts.business_objective,
            len(mts.functional_requirements) > 0,
            len(mts.acceptance_criteria) > 0
        ]
        scores['completeness'] = sum(required_fields) / len(required_fields)
        
        # Consistency: No contradictions detected (simplified check)
        scores['consistency'] = 1.0 - (len([a for a in ambiguities if a.ambiguity_type == 'contradictory']) * 0.2)
        
        # Testability: Acceptance criteria are specific and measurable
        testable_count = sum(
            1 for ac in mts.acceptance_criteria 
            if any(kw in ac.lower() for kw in ['%', 'ms', 'second', 'must', 'shall', 'verify'])
        )
        scores['testability'] = testable_count / max(len(mts.acceptance_criteria), 1)
        
        # Semantic coverage: Functional requirements cover the business objective
        scores['semantic_coverage'] = min(1.0, len(mts.functional_requirements) * 0.2)
        
        # Penalize for high-severity ambiguities
        high_severity_penalty = len([a for a in ambiguities if a.severity == 'high']) * 0.15
        medium_severity_penalty = len([a for a in ambiguities if a.severity == 'medium']) * 0.05
        
        final_score = (
            scores['completeness'] * 0.3 +
            scores['consistency'] * 0.25 +
            scores['testability'] * 0.25 +
            scores['semantic_coverage'] * 0.2 -
            high_severity_penalty -
            medium_severity_penalty
        )
        
        return max(0.0, min(1.0, final_score))
    
    def _validate_mts_schema(self, mts: MachineTaskSpecification):
        """Validate MTS conforms to expected schema"""
        if not mts.business_objective:
            raise ValueError("MTS must have a business objective")
        
        if not mts.functional_requirements:
            raise ValueError("MTS must have at least one functional requirement")
        
        for fr in mts.functional_requirements:
            if not isinstance(fr, dict):
                raise ValueError("Each functional requirement must be a dictionary")
            if 'description' not in fr:
                raise ValueError("Functional requirement must have a description")
        
        if not isinstance(mts.confidence_score, (int, float)):
            raise ValueError("Confidence score must be a number")
        
        if not 0.0 <= mts.confidence_score <= 1.0:
            raise ValueError("Confidence score must be between 0 and 1")
    
    def should_request_human_intervention(self, mts: MachineTaskSpecification) -> Tuple[bool, List[str]]:
        """
        Determine if human intervention is needed
        Returns: (needs_intervention, list_of_questions)
        """
        questions = []
        
        # High severity ambiguities require clarification
        high_severity_ambiguities = [
            a for a in mts.ambiguities 
            if a.get('severity') == 'high'
        ]
        
        if len(high_severity_ambiguities) > 2:
            questions.extend([a['suggested_clarification'] for a in high_severity_ambiguities])
        
        # Low confidence score requires review
        if mts.confidence_score < 0.6:
            questions.append("需求置信度较低，请人工审核关键假设。")
        
        # Missing critical components
        if not mts.acceptance_criteria:
            questions.append("缺少验收标准，请补充可验证的验收条件。")
        
        return len(questions) > 0, questions


# Factory function for creating PM Agent
def create_pm_agent(llm_config: Optional[Dict[str, Any]] = None, vector_store_config: Optional[Dict[str, Any]] = None) -> PMAgent:
    """Create and configure PM Agent"""
    llm_client = None
    vector_store = None
    
    # TODO: Initialize actual LLM client and vector store based on config
    # This is a placeholder for integration with real services
    
    return PMAgent(llm_client=llm_client, vector_store=vector_store)
