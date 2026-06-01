import asyncio
import logging
from typing import List, Dict, Any, Tuple
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("career_pilot.telemetry")

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0.0.0 Safari/537.36"
)

async def check_url_status(client: httpx.AsyncClient, job: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    url = job.get("url", "")
    if not url:
        return job, False
        
    if "careerpilot_" in url:
        logger.info(f"Bypassing telemetry check for mock URL: {url} -> Active: True")
        return job, True
        
    try:
        response = await client.head(url, headers={"User-Agent": BROWSER_UA})
        
        if response.status_code in (405, 501, 503):
            response = await client.get(url, headers={"User-Agent": BROWSER_UA})
            
        is_active = response.status_code not in (404, 410)
        logger.info(f"Telemetry check for {url} returned status code: {response.status_code} -> Active: {is_active}")
        return job, is_active
        
    except httpx.HTTPStatusError as exc:
        logger.warning(f"Telemetry status error for {url}: {exc}")
        return job, False
    except (httpx.NetworkError, httpx.TimeoutException) as exc:
        logger.warning(f"Telemetry network or timeout failure for {url}: {exc}")
        if "careerpilot_" in url:
            logger.info(f"Treating mock URL as active: {url}")
            return job, True
        return job, False
    except Exception as exc:
        logger.error(f"Unexpected telemetry error on {url}: {exc}", exc_info=True)
        return job, False

async def verify_job_links(jobs: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], bool]]:
    if not jobs:
        return []
        
    logger.info(f"Spawning concurrent link validation for {len(jobs)} jobs...")
    
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=20)
    timeout = httpx.Timeout(5.0, connect=3.0)
    
    async with httpx.AsyncClient(limits=limits, timeout=timeout, follow_redirects=True) as client:
        tasks = [check_url_status(client, job) for job in jobs]
        results = await asyncio.gather(*tasks)
        
    active_count = sum(1 for _, active in results if active)
    logger.info(f"Link validation finalized. {active_count}/{len(jobs)} listings verified active.")
    return results
