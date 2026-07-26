"""FastMCP server: SpecAnalysisMCP."""

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from specsync.core.config import load_config
from specsync.core.llm import get_llm_with_fallback
from specsync.core.models import APIChange, DataModel, EdgeCase, Requirement
from specsync.core.storage import get_config_path


# Initialize FastMCP server
mcp = FastMCP("SpecAnalysisMCP")


def _get_llm() -> Any:
    """Helper to get the configured LLM instance."""
    # We ignore the env var for now and just load default config path
    # as get_config_path() handles the platform-specific resolution.
    config_path_env = os.environ.get("SPECSYNC_CONFIG_PATH")
    
    # We just use the standard load_config since it relies on storage.py
    config = load_config()
    return get_llm_with_fallback(config)


@mcp.tool()
async def parse_spec_to_requirements(spec_text: str, context: str = ""):
    """Extract structured, atomic requirements from a raw specification.

    Args:
        spec_text: The raw specification text (e.g., GitHub issue body, markdown).
        context: Optional project context to ground the LLM.

    Returns:
        JSON string representing a list of Requirement objects.
    """
    llm = _get_llm()
    
    system_prompt = (
        "You are an expert technical product manager. Your job is to extract atomic, testable "
        "requirements from the provided specification text.\n\n"
        "Each requirement MUST include:\n"
        "- id: A unique string identifier (e.g., REQ-001)\n"
        "- description: Clear, concise description of the requirement\n"
        "- requirement_type: One of [feature, constraint, data_model, api_change, behaviour]\n"
        "- priority: One of [high, medium, low]\n"
        "- raw_text: The exact sentence(s) from the spec it came from\n\n"
        "IMPORTANT: You MUST return ONLY a valid JSON array of Requirement objects. "
        "Do NOT include any markdown formatting, code fences, or preamble. Return RAW JSON."
    )
    
    user_prompt = f"Specification:\n{spec_text}\n\nContext:\n{context}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    # Attempt 1
    try:
        response = await llm.ainvoke(messages)
    except AttributeError:
        # Fallback to sync if ainvoke not available
        response = llm.invoke(messages)
    content = response.content
    
    try:
        # Strip potential markdown fences just in case
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        json_data = json.loads(content)
        if not isinstance(json_data, list):
            raise ValueError("Expected a JSON array.")
        
        # Validate through Pydantic to ensure correctness
        valid_reqs = [Requirement(**req).model_dump() for req in json_data]
        return json.dumps(valid_reqs)
        
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        # Attempt 2 (Repair)
        repair_messages = messages + [
            {"role": "assistant", "content": response.content},
            {
                "role": "user", 
                "content": (
                    f"The previous response was not valid JSON or failed validation: {e}. "
                    "Return ONLY the JSON array, nothing else. No markdown."
                )
            }
        ]
        
        repair_response = llm.invoke(repair_messages)
        repair_content = repair_response.content
        
        # Strip potential markdown fences just in case
        if repair_content.startswith("```json"):
            repair_content = repair_content[7:-3].strip()
        elif repair_content.startswith("```"):
            repair_content = repair_content[3:-3].strip()
            
        try:
            json_data = json.loads(repair_content)
            valid_reqs = [Requirement(**req).model_dump() for req in json_data]
            return json.dumps(valid_reqs)
        except Exception as exc:
            raise RuntimeError(f"Failed to parse spec to JSON after repair: {exc}")


@mcp.tool()
async def infer_edge_cases(requirements: list[dict], spec_text: str):
    """Infer edge cases implied by the specification.

    Args:
        requirements: List of parsed requirements (dicts).
        spec_text: The original specification text.

    Returns:
        JSON string representing a list of EdgeCase objects.
    """
    llm = _get_llm()
    
    req_str = json.dumps(requirements, indent=2)
    system_prompt = (
        "You are an expert QA engineer. Analyze the specification and requirements. "
        "What edge cases does this spec imply but not state explicitly? "
        "What could go wrong? What boundaries need testing?\n\n"
        "Return ONLY a valid JSON array of objects with keys: "
        "'description' (str), 'related_requirement_id' (str or null), and 'severity' ('must_discuss' or 'should_discuss'). "
        "Do NOT include markdown fences."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Spec:\n{spec_text}\n\nRequirements:\n{req_str}"}
    ]
    
    try:
        response = await llm.ainvoke(messages)
    except AttributeError:
        response = llm.invoke(messages)
    content = response.content
    if content.startswith("```json"):
        content = content[7:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()
        
    try:
        data = json.loads(content)
        valid_ecs = [EdgeCase(**ec).model_dump() for ec in data]
        return json.dumps(valid_ecs)
    except Exception:
        # If parsing fails, just return empty list to not block the pipeline
        return "[]"


@mcp.tool()
async def extract_data_models(spec_text: str):
    """Extract implied data model changes from the specification.

    Args:
        spec_text: The original specification text.

    Returns:
        JSON string representing a list of DataModel objects.
    """
    llm = _get_llm()
    
    system_prompt = (
        "Identify any data model changes implied by the spec (new fields, tables, etc.).\n"
        "Return ONLY a valid JSON array of objects with keys: "
        "'name' (str), 'description' (str), 'fields' (list of str), 'is_new' (bool). "
        "Do NOT include markdown fences."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": spec_text}
    ]
    
    try:
        response = await llm.ainvoke(messages)
    except AttributeError:
        response = llm.invoke(messages)
    content = response.content
    if content.startswith("```json"):
        content = content[7:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()
        
    try:
        data = json.loads(content)
        valid_dms = [DataModel(**dm).model_dump() for dm in data]
        return json.dumps(valid_dms)
    except Exception:
        return "[]"


@mcp.tool()
async def identify_api_changes(spec_text: str):
    """Extract implied API changes from the specification.

    Args:
        spec_text: The original specification text.

    Returns:
        JSON string representing a list of APIChange objects.
    """
    llm = _get_llm()
    
    system_prompt = (
        "Identify any API endpoint changes implied by the spec (new routes, parameters, etc.).\n"
        "Return ONLY a valid JSON array of objects with keys: "
        "'endpoint' (str), 'method' (str), 'description' (str), 'is_new' (bool). "
        "Do NOT include markdown fences."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": spec_text}
    ]
    
    try:
        response = await llm.ainvoke(messages)
    except AttributeError:
        response = llm.invoke(messages)
    content = response.content
    if content.startswith("```json"):
        content = content[7:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()
        
    try:
        data = json.loads(content)
        valid_acs = [APIChange(**ac).model_dump() for ac in data]
        return json.dumps(valid_acs)
    except Exception:
        return "[]"


if __name__ == "__main__":
    mcp.run()
