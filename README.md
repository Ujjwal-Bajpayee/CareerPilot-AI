# CareerPilot

CareerPilot is an autonomous self-hosted multi-user career operations daemon. Users upload a resume PDF to a Telegram bot, which triggers a LangGraph workflow that extracts skills using the Groq LLM, scrapes remote developer job postings concurrently, validates URLs, grades compatibility, writes records to MySQL, and serves an interactive job board with dynamic limit selectors and on-demand explanations.

## Screenshots

Below are demonstrations of the bot interface and analysis pipeline:

![Start and Ingestion](Img/1.png)

![Orchestration Progress](Img/2.png)

![Interactive Alignment Selector](Img/3.png)

![Verified Job Alignments and On-Demand Explanations](Img/4.png)

## Core Pipeline

1. Profile Ingestion: PDF resumes are parsed, extracting raw text and structured technical skills using Groq LLM.
2. Job Scraper: Concurrently queries remote developer RSS boards including WeWorkRemotely, WFH.io, and JS Remotely.
3. Link Telemetry: Parallel HTTPX probes verify link status in real-time, filtering out expired or broken links.
4. Match Critic: Grades match compatibility from 0 to 100, identifies key skill gaps, and prepares custom alignment explanations.
5. Interactive Delivery: Serves findings with customizable view counts (3, 5, or 10) and interactive inline explanation buttons.

## Prerequisites

- Python 3.10 or higher
- MySQL Database
- Groq API Key
- Telegram Bot Token (obtained from @BotFather)

## Setup and Installation

1. Clone the repository and navigate to the project directory:
   ```bash
   cd CareerPilot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create and configure your environment file:
   Create a `.env` file in the root directory with the following variables:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   GROQ_API_KEY=your_groq_api_key
   DATABASE_URL=mysql+aiomysql://username:password@localhost:3306/career_pilot
   ```
   Note: If your database password contains special characters like `@`, ensure they are URL-encoded (e.g. `@` as `%40`).

## Running the Application

Start the daemon using the main entrypoint:
```bash
python main.py
```
Upon startup, the system will automatically bootstrap the database schemas (users, resumes, job_listings, job_matches) if they do not exist and launch the long-polling Telegram application.
