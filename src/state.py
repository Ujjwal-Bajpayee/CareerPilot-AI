from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    user_id: int
    resume_text: str
    profile_json: Dict[str, Any]
    discovered_links: List[Dict[str, Any]]
    verified_matches: List[Dict[str, Any]]
