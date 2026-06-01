import logging
import random
import re
from typing import List, Dict, Any
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("career_pilot.hunters")

SOURCES = [
    ("WeWorkRemotely (Programming)", "https://weworkremotely.com/categories/remote-programming-jobs.rss"),
    ("WeWorkRemotely (DevOps)", "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"),
    ("WFH.io", "https://www.wfh.io/jobs.rss"),
    ("JS Remotely", "https://jsremotely.com/index.xml"),
]

async def scrape_feed(client: httpx.AsyncClient, name: str, url: str) -> List[Dict[str, Any]]:
    logger.info(f"Initiating scrape for: {name}...")
    try:
        response = await client.get(url, timeout=12.0)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch {name} feed: Status {response.status_code}")
            return []
            
        items_raw = re.findall(r"<item>(.*?)</item>", response.text, re.DOTALL)
        logger.info(f"Scraped {name} feed. Regex resolved {len(items_raw)} raw items.")
        
        feed_jobs = []
        for item_content in items_raw:
            title_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item_content, re.DOTALL)
            if not title_match:
                title_match = re.search(r"<title>(.*?)</title>", item_content, re.DOTALL)
                
            link_match = re.search(r"<link><!\[CDATA\[(.*?)\]\]></link>", item_content, re.DOTALL)
            if not link_match:
                link_match = re.search(r"<link>(.*?)</link>", item_content, re.DOTALL)
                
            if not title_match or not link_match:
                continue
                
            raw_title = title_match.group(1).strip()
            job_url = link_match.group(1).strip()
            
            if ":" in raw_title:
                company, title = raw_title.split(":", 1)
                company = company.strip()
                title = title.strip()
            elif " at " in raw_title:
                title, company = raw_title.split(" at ", 1)
                company = company.strip()
                title = title.strip()
            else:
                company = name
                title = raw_title.strip()
                
            feed_jobs.append({
                "company": company,
                "title": title,
                "url": job_url
            })
            
        return feed_jobs
    except Exception as exc:
        logger.error(f"Scraping exception on {name} feed: {exc}", exc_info=True)
        return []

async def hunt_jobs(profile_json: Dict[str, Any], max_results: int = 30) -> List[Dict[str, Any]]:
    skills: List[str] = profile_json.get("skills", [])
    target_roles: List[str] = profile_json.get("target_roles", ["Software Engineer"])
    
    logger.info(f"Commencing multi-source job aggregation for roles: {target_roles} and skills: {skills}")
    
    all_scraped_jobs: List[Dict[str, Any]] = []
    
    limits = httpx.Limits(max_connections=5)
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        import asyncio
        tasks = [scrape_feed(client, name, url) for name, url in SOURCES]
        results = await asyncio.gather(*tasks)
        
        for feed_result in results:
            all_scraped_jobs.extend(feed_result)
            
    seen_urls = set()
    unique_jobs = []
    for job in all_scraped_jobs:
        url = job["url"]
        if url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)
            
    logger.info(f"Total unique parsed listings across all boards: {len(unique_jobs)}")
    
    filtered_jobs = []
    skills_lower = [s.lower() for s in skills]
    roles_lower = [r.lower() for r in target_roles]
    
    for job in unique_jobs:
        title_lower = job["title"].lower()
        
        role_match = any(role in title_lower for role in roles_lower)
        skill_match = any(skill in title_lower for skill in skills_lower)
        
        if role_match or skill_match:
            filtered_jobs.append(job)
            
    logger.info(f"Filtered job listings: {len(filtered_jobs)}")
    
    if len(filtered_jobs) < 10:
        logger.warning(f"Filtered count ({len(filtered_jobs)}) is low. Expanding list with direct RSS opportunities...")
        for job in unique_jobs:
            if job not in filtered_jobs:
                filtered_jobs.append(job)
            if len(filtered_jobs) >= max_results:
                break
                
    final_jobs = filtered_jobs[:max_results]
    
    logger.info(f"Hunt finalized. Dispatched {len(final_jobs)} genuine active remote listings.")
    return final_jobs
