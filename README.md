# Morning Brief

A personal AI-powered financial news tool that runs locally on your laptop. It pulls live headlines from NewsAPI, feeds them to Mistral (running via Ollama), and generates a structured morning briefing that opens in your browser.

Built as part of a 30-day learning challenge — Day 5.

## What it produces

- Market mood summary
- Top story of the day
- Australia & ASX section
- America & Global macro
- Business news
- Tech & AI
- News rundown with Bullish/Bearish/Neutral tags per story
- Indicators to watch today

## Setup

**1. Install dependencies**
```
pip install requests ollama python-dotenv
```

**2. Install Ollama and pull Mistral**

Download Ollama from [ollama.com](https://ollama.com), then run:
```
ollama pull mistral
```

**3. Get a free NewsAPI key**

Sign up at [newsapi.org](https://newsapi.org) (free tier: 100 requests/day).

**4. Create your .env file**

Copy `.env.example` to `.env` and add your key:
```
NEWS_API_KEY=your-key-here
```

**5. Run**

Make sure `ollama serve` is running, then:
```
python3 morning_brief.py
```

Or double-click `Morning Brief.command` (Mac only — run `chmod +x "Morning Brief.command"` once first).

## Note on the free tier

NewsAPI free tier returns top headlines updated in near real-time. The brief pulls ~35 articles across Australian business, US business, technology, and general news.

## Stack

- [NewsAPI](https://newsapi.org) — live news headlines
- [Ollama](https://ollama.com) + [Mistral 7B](https://mistral.ai) — local AI analysis, no API cost
- Python — fetch, prompt, generate HTML
