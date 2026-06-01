import os
import json
import logging
from typing import Dict, Any, List
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from sqlalchemy import select
import random
import re 

from src.state import AgentState
from src.database import get_db_session
from src.models import User, Resume, JobListing, JobMatch
from src.parsers import parse_resume_to_json
from src.hunters import hunt_jobs
from src.telemetry import verify_job_links

logger = logging.getLogger("career_pilot.graph")

class FitAssessment(BaseModel):
    match_score: int = Field(
        description="Integrity value from 0 to 100 reflecting how well the candidate's skills fit this job posting."
    )
    skill_gaps: List[str] = Field(
        description="A list of 1 to 4 specific technical skills or domains required for this job that the candidate lacks."
    )
    explanation: str = Field(
        description="A brief, professional, and encouraging 2-3 sentence analysis explaining the alignment, highlighting key matches and how to address gaps."
    )

async def resume_parser_node(state: AgentState) -> Dict[str, Any]:
    user_id = state.get("user_id")
    raw_text = state.get("resume_text", "")
    
    logger.info(f"[Node: ResumeParser] Commencing parser node for user {user_id}")
    
    profile_json = await parse_resume_to_json(raw_text)
    
    async with get_db_session() as session:
        stmt = select(User).where(User.tg_user_id == user_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        
        if not user:
            logger.info(f"User {user_id} not found in DB. Creating new profile...")
            user = User(tg_user_id=user_id, username=None)
            session.add(user)
            await session.flush()
            
        stmt_resume = select(Resume).where(Resume.tg_user_id == user_id)
        res_resume = await session.execute(stmt_resume)
        resume = res_resume.scalar_one_or_none()
        
        if not resume:
            logger.info(f"Creating new Resume record for user {user_id}")
            resume = Resume(
                tg_user_id=user_id,
                raw_text=raw_text,
                parsed_skills=profile_json
            )
            session.add(resume)
        else:
            logger.info(f"Updating existing Resume record for user {user_id}")
            resume.raw_text = raw_text
            resume.parsed_skills = profile_json
            
        await session.flush()
        
    logger.info(f"[Node: ResumeParser] Finished. skills={profile_json.get('skills', [])}")
    return {"profile_json": profile_json}

async def job_hunter_node(state: AgentState) -> Dict[str, Any]:
    profile_json = state.get("profile_json", {})
    logger.info("[Node: JobHunter] Commencing job hunter node...")
    
    raw_jobs = await hunt_jobs(profile_json, max_results=20)
    
    logger.info(f"[Node: JobHunter] Finished. Found {len(raw_jobs)} job listings.")
    return {"discovered_links": raw_jobs}

async def link_telemetry_node(state: AgentState) -> Dict[str, Any]:
    discovered_jobs = state.get("discovered_links", [])
    logger.info(f"[Node: LinkTelemetry] Commencing telemetry validation for {len(discovered_jobs)} jobs...")
    
    telemetry_results = await verify_job_links(discovered_jobs)
    
    active_jobs_state = []
    
    async with get_db_session() as session:
        for job_dict, is_active in telemetry_results:
            url = job_dict["url"]
            company = job_dict["company"]
            title = job_dict["title"]
            
            stmt = select(JobListing).where(JobListing.url == url)
            res = await session.execute(stmt)
            listing = res.scalar_one_or_none()
            
            if not listing:
                listing = JobListing(
                    company=company,
                    title=title,
                    url=url,
                    is_active=is_active
                )
                session.add(listing)
            else:
                listing.is_active = is_active
                
            await session.flush()
            
            if is_active:
                job_entry = job_dict.copy()
                job_entry["job_id"] = listing.job_id
                active_jobs_state.append(job_entry)
                
    logger.info(f"[Node: LinkTelemetry] Finished. Filtered down to {len(active_jobs_state)} active listings.")
    return {"discovered_links": active_jobs_state}

async def match_critic_node(state: AgentState) -> Dict[str, Any]:
    user_id = state.get("user_id")
    profile = state.get("profile_json", {})
    active_jobs = state.get("discovered_links", [])
    
    logger.info(f"[Node: MatchCritic] Commencing alignment audit for user {user_id} on {len(active_jobs)} active listings...")
    
    api_key = os.getenv("GROQ_API_KEY")
    verified_matches = []
    
    use_llm = api_key and "your_groq" not in api_key and not api_key.startswith("gsk_your")
    
    llm = None
    parser = None
    prompt_template = None
    
    if use_llm:
        try:
            llm = ChatGroq(
                groq_api_key=api_key,
                model_name="llama-3.3-70b-versatile",
                temperature=0.2,
                max_retries=2
            )
            parser = JsonOutputParser(pydantic_object=FitAssessment)
            prompt_template = ChatPromptTemplate.from_template(
                "You are an expert career counselor and resume auditor.\n"
                "Evaluate how well a candidate's profile fits a specific job posting.\n\n"
                "Candidate Profile:\n"
                "- Skills: {skills}\n"
                "- Summary: {summary}\n"
                "- Target Roles: {target_roles}\n\n"
                "Job Listing:\n"
                "- Company: {company}\n"
                "- Title: {job_title}\n\n"
                "Formatting requirements:\n{format_instructions}\n\n"
                "Analyze details carefully. Calculate a realistic score (0-100), identify 1-4 core gaps, and write a professional 2-3 sentence explanation."
            )
        except Exception as exc:
            logger.error(f"Failed to initialize Groq client for MatchCritic: {exc}. Reverting to local heuristic.", exc_info=True)
            use_llm = False
            
    for job in active_jobs:
        job_id = job["job_id"]
        company = job["company"]
        title = job["title"]
        url = job["url"]
        
        assessment = None
        
        if use_llm:
            try:
                chain = prompt_template | llm | parser
                assessment = await chain.ainvoke({
                    "skills": profile.get("skills", []),
                    "summary": profile.get("experience_summary", ""),
                    "target_roles": profile.get("target_roles", []),
                    "company": company,
                    "job_title": title,
                    "format_instructions": parser.get_format_instructions()
                })
            except Exception as exc:
                logger.warning(f"Groq API error evaluating job '{title}' at '{company}': {exc}. Using heuristic fallback.")
                assessment = None
                
        if not assessment:
            assessment = _local_fit_critic(profile, title, company)
            
        async with get_db_session() as session:
            stmt = select(JobMatch).where(
                (JobMatch.tg_user_id == user_id) & 
                (JobMatch.job_id == job_id)
            )
            res = await session.execute(stmt)
            match_record = res.scalar_one_or_none()
            
            if not match_record:
                match_record = JobMatch(
                    tg_user_id=user_id,
                    job_id=job_id,
                    match_score=assessment["match_score"],
                    skill_gaps=assessment["skill_gaps"],
                    explanation=assessment["explanation"]
                )
                session.add(match_record)
            else:
                match_record.match_score = assessment["match_score"]
                match_record.skill_gaps = assessment["skill_gaps"]
                match_record.explanation = assessment["explanation"]
                
            await session.flush()
            
            verified_matches.append({
                "match_id": match_record.match_id,
                "job_id": job_id,
                "company": company,
                "title": title,
                "url": url,
                "match_score": assessment["match_score"],
                "skill_gaps": assessment["skill_gaps"],
                "explanation": assessment["explanation"]
            })
            
    verified_matches.sort(key=lambda x: x["match_score"], reverse=True)
    
    logger.info(f"[Node: MatchCritic] Finished. Audited {len(verified_matches)} matches.")
    return {"verified_matches": verified_matches}

def _local_fit_critic(profile: Dict[str, Any], job_title: str, company: str) -> Dict[str, Any]:
    candidate_skills = profile.get("skills", [])
    title_lower = job_title.lower()
    
    matched_skills = []
    unmatched_skills = []
    
    title_words = set(re.findall(r"\b\w+\b", title_lower))
    
    for skill in candidate_skills:
        skill_lower = skill.lower()
        if skill_lower in title_lower or any(word in skill_lower for word in title_words):
            matched_skills.append(skill)
        else:
            unmatched_skills.append(skill)
            
    score = 50
    if matched_skills:
        score += len(matched_skills) * 15
    if any(role.lower() in title_lower for role in profile.get("target_roles", [])):
        score += 20
        
    score = min(max(score, 30), 98)
    
    possible_gaps = ["Docker", "Kubernetes", "AWS / Cloud Infra", "System Architecture", 
                     "GraphQL", "Redis", "TypeScript", "CI/CD Pipelines", "Unit Testing"]
    candidate_skills_set = {s.lower() for s in candidate_skills}
    gaps = [g for g in possible_gaps if g.lower() not in candidate_skills_set]
    
    selected_gaps = random.sample(gaps, min(len(gaps), random.randint(1, 3)))
    
    matched_str = ", ".join(matched_skills[:3]) if matched_skills else "general software development concepts"
    gap_str = " and ".join(selected_gaps[:2])
    
    explanation = (
        f"This role at {company} matches your experience in {matched_str}. "
        f"Your alignment score is {score}% based on your target roles. "
        f"To increase your chances, focus on highlighting or brushing up on {gap_str} during the application process."
    )
    
    return {
        "match_score": int(score),
        "skill_gaps": selected_gaps,
        "explanation": explanation
    }

workflow = StateGraph(AgentState)

workflow.add_node("ResumeParserNode", resume_parser_node)
workflow.add_node("JobHunterNode", job_hunter_node)
workflow.add_node("LinkTelemetryNode", link_telemetry_node)
workflow.add_node("MatchCriticNode", match_critic_node)

workflow.add_edge(START, "ResumeParserNode")
workflow.add_edge("ResumeParserNode", "JobHunterNode")
workflow.add_edge("JobHunterNode", "LinkTelemetryNode")
workflow.add_edge("LinkTelemetryNode", "MatchCriticNode")
workflow.add_edge("MatchCriticNode", END)

career_pilot_graph = workflow.compile()
