import os
import logging
import asyncio
from typing import Dict, Any, List
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import get_db_session
from src.models import User, Resume, JobListing, JobMatch
from src.parsers import extract_text_from_pdf
from src.graph import career_pilot_graph

load_dotenv()
logger = logging.getLogger("career_pilot.gateway")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    username_str = f" @{user.username}" if user.username else ""
    
    welcome_text = (
        f"◈ *C A R E E R P I L O T* ◈\n"
        f"*Autonomous Talent & Market Intelligence Daemon*{username_str}\n\n"
        "Welcome to your self-hosted career operations node. CareerPilot leverages multi-agent pipelines and live link telemetry to align your professional profile with active market openings.\n\n"
        "**Core Operations Pipeline:**\n"
        "1. **Profile Ingestion**: Submit your resume in PDF format. The agent parses and indexes your technical skill graph.\n"
        "2. **Aggregated Job Hunting**: The system scrapes remote developer boards for active listings corresponding to your target roles.\n"
        "3. **Link Status Telemetry**: Concurrent network probes verify the liveness of all application endpoints in real-time.\n"
        "4. **LLM Fit Auditing**: The orchestration engine performs semantic alignment matching, identifies skill gaps, and compiles custom match explanations.\n\n"
        "To initiate the analysis, please upload your resume **PDF** directly to this chat."
    )
    
    await update.message.reply_text(text=welcome_text, parse_mode="Markdown")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    document = message.document
    
    if not document or not document.file_name.lower().endswith(".pdf"):
        await message.reply_text(
            "◈ *Invalid Ingestion Request*\n"
            "Please upload your resume strictly in standard **PDF format** (.pdf).",
            parse_mode="Markdown"
        )
        return
        
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    status_msg = await message.reply_text(
        "◈ *Document Ingested*\n"
        "Initializing background talent-matching pipeline...",
        parse_mode="Markdown"
    )
    
    asyncio.create_task(
        run_orchestration_pipeline(user_id, username, document, status_msg, context)
    )

async def run_orchestration_pipeline(
    user_id: int, 
    username: str | None,
    document: Any, 
    status_msg: Any, 
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    try:
        logger.info(f"Downloading resume PDF for user {user_id}...")
        file_obj = await context.bot.get_file(document.file_id)
        
        import io
        out_buffer = io.BytesIO()
        await file_obj.download_to_memory(out_buffer)
        pdf_bytes = out_buffer.getvalue()
        
        logger.info(f"Extracting text from PDF for user {user_id}...")
        await status_msg.edit_text(
            "◈ *Pipeline Step [1/5]*\n"
            "Extracting document plain text structure and layouts...",
            parse_mode="Markdown"
        )
        raw_text = extract_text_from_pdf(bytes(pdf_bytes))
        
        logger.info(f"Triggering LangGraph runtime for user {user_id}...")
        await status_msg.edit_text(
            "◈ *Pipeline Step [2/5]*\n"
            "Invoking ResumeParserNode: Mapping skill taxonomy...",
            parse_mode="Markdown"
        )
        
        initial_state = {
            "user_id": user_id,
            "resume_text": raw_text,
            "profile_json": {},
            "discovered_links": [],
            "verified_matches": []
        }
        
        async with get_db_session() as session:
            stmt = select(User).where(User.tg_user_id == user_id)
            res = await session.execute(stmt)
            user_rec = res.scalar_one_or_none()
            if not user_rec:
                user_rec = User(tg_user_id=user_id, username=username)
                session.add(user_rec)
            else:
                user_rec.username = username
            await session.flush()
            
        final_state = None
        
        async for event in career_pilot_graph.astream(initial_state, stream_mode="updates"):
            if "ResumeParserNode" in event:
                await status_msg.edit_text(
                    "◈ *Pipeline Step [3/5]*\n"
                    "Invoking JobHunterNode: Scraping remote programming indices...",
                    parse_mode="Markdown"
                )
            elif "JobHunterNode" in event:
                discovered_count = len(event["JobHunterNode"].get("discovered_links", []))
                await status_msg.edit_text(
                    f"◈ *Pipeline Step [4/5]*\n"
                    f"Located {discovered_count} job postings. Invoking LinkTelemetryNode: Probing liveness...",
                    parse_mode="Markdown"
                )
            elif "LinkTelemetryNode" in event:
                active_count = len(event["LinkTelemetryNode"].get("discovered_links", []))
                await status_msg.edit_text(
                    f"◈ *Pipeline Step [5/5]*\n"
                    f"Telemetry probe complete. {active_count} active listings validated.\n"
                    f"Invoking MatchCriticNode: Conducting semantic fit audit...",
                    parse_mode="Markdown"
                )
            elif "MatchCriticNode" in event:
                final_state = event["MatchCriticNode"]
                
        if not final_state or "verified_matches" not in final_state:
            graph_res = await career_pilot_graph.ainvoke(initial_state)
            final_matches = graph_res.get("verified_matches", [])
        else:
            final_matches = final_state["verified_matches"]
            
        keyboard = [
            [
                InlineKeyboardButton("Show 3 Positions", callback_data=f"limit:3:{user_id}"),
                InlineKeyboardButton("Show 5 Positions", callback_data=f"limit:5:{user_id}")
            ],
            [
                InlineKeyboardButton("Show 10 Positions", callback_data=f"limit:10:{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.edit_text(
            "◈ *CareerPilot Analysis Complete* ◈\n\n"
            "Please select the number of top alignments you would like to display:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    except Exception as exc:
        logger.error(f"Error in background orchestration pipeline for user {user_id}: {exc}", exc_info=True)
        await status_msg.edit_text(
            f"❌ *An internal error occurred during processing.*\n\n"
            f"*Error Details:* `{type(exc).__name__}: {str(exc)}`\n\n"
            f"Please check your daemon console logs or try again.",
            parse_mode="Markdown"
        )

async def render_job_board(
    user_id: int, 
    matches: List[Dict[str, Any]], 
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not matches:
        await context.bot.send_message(
            chat_id=user_id,
            text="◈ *No Alignments Resolved*\nConsider updating your profile skill matrix to broaden matching parameters.",
            parse_mode="Markdown"
        )
        return
        
    top_matches = matches
    
    await context.bot.send_message(
        chat_id=user_id,
        text=f"◈ **VERIFIED CAREER ALIGNMENTS** ◈\nListing top {len(top_matches)} active remote positions sorted by compatibility:",
        parse_mode="Markdown"
    )
    
    for i, match in enumerate(top_matches):
        match_id = match["match_id"]
        company = match["company"]
        title = match["title"]
        url = match["url"]
        score = match["match_score"]
        gaps = match["skill_gaps"]
        
        card_text = (
            f"🏢 **{i+1}. {company}**\n"
            f"💼 **Role:** {title}\n"
            f"📈 **Match Compatibility:** `{score}%` \n\n"
            f"⚠️ **Core Skill Gaps:** {', '.join(gaps[:3]) if gaps else 'None'}\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("Apply Position", url=url),
                InlineKeyboardButton("Explain Match", callback_data=f"explain:{match_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=user_id,
            text=card_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    
    if not data:
        await query.answer()
        return
        
    if data.startswith("limit:"):
        try:
            _, limit_str, tg_user_id_str = data.split(":")
            limit = int(limit_str)
            tg_user_id = int(tg_user_id_str)
        except (ValueError, IndexError):
            await query.answer(text="Error parsing limit parameters.", show_alert=True)
            return
            
        await query.answer(text=f"Retrieving top {limit} alignments...")
        
        async with get_db_session() as session:
            stmt = (
                select(JobMatch)
                .options(selectinload(JobMatch.job))
                .where(JobMatch.tg_user_id == tg_user_id)
                .order_by(JobMatch.match_score.desc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            db_matches = res.scalars().all()
            
        matches_to_render = []
        for db_match in db_matches:
            matches_to_render.append({
                "match_id": db_match.match_id,
                "company": db_match.job.company,
                "title": db_match.job.title,
                "url": db_match.job.url,
                "match_score": db_match.match_score,
                "skill_gaps": db_match.skill_gaps
            })
            
        try:
            await query.message.delete()
        except Exception:
            pass
            
        await render_job_board(tg_user_id, matches_to_render, context)
        return
        
    if data.startswith("explain:"):
        try:
            match_id = int(data.split(":")[1])
        except (ValueError, IndexError):
            await query.answer(text="Error parsing target match ID.", show_alert=True)
            return
            
        logger.info(f"Handling on-demand match explanation for match_id={match_id}...")
        
        await query.answer(text="Retrieving audit report...")
        
        async with get_db_session() as session:
            stmt = select(JobMatch).options(selectinload(JobMatch.job)).where(JobMatch.match_id == match_id)
            res = await session.execute(stmt)
            match_record = res.scalar_one_or_none()
            
            if not match_record:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ *Error:* Match explanation could not be resolved from the database.",
                    parse_mode="Markdown"
                )
                return
                
            company = match_record.job.company
            title = match_record.job.title
            explanation = match_record.explanation
            score = match_record.match_score
            
            explanation_msg = (
                f"🧠 *CareerPilot Match Audit Explanation*\n"
                f"🏢 *Company:* {company}\n"
                f"💼 *Position:* {title}\n"
                f"📊 *Compatibility Score:* `{score}%` \n\n"
                f"✏️ *Analysis:*\n{explanation}"
            )
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                reply_to_message_id=query.message.message_id,
                text=explanation_msg,
                parse_mode="Markdown"
            )

async def bootstrap_db(application: Application) -> None:
    logger.info("Post-initialization hook: Bootstrapping database schema...")
    from src.database import init_db
    await init_db()

def init_telegram_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or "your_telegram_bot_token" in token:
        logger.critical("TELEGRAM_BOT_TOKEN is missing or contains default placeholders. Daemon aborted.")
        raise ValueError("TELEGRAM_BOT_TOKEN must be correctly populated in your environment configurations.")
        
    logger.info("Initializing Telegram Gateway application build...")
    
    from telegram.request import HTTPXRequest
    req_engine = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
    
    app = Application.builder().token(token).request(req_engine).post_init(bootstrap_db).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    
    logger.info("Telegram Gateway application and handlers initialized successfully.")
    return app
