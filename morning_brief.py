import requests
import ollama
import webbrowser
import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
MODEL = "mistral"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brief.html")

FEED_QUERIES = [
    {"country": "au", "category": "business",   "pageSize": 10},
    {"country": "us", "category": "business",   "pageSize": 10},
    {"country": "us", "category": "technology", "pageSize": 10},
    {"country": "us", "category": "general",    "pageSize": 5},
]

def get_all_articles():
    all_articles = []
    seen = set()
    for query in FEED_QUERIES:
        params = {**query, "apiKey": NEWS_API_KEY}
        try:
            r = requests.get("https://newsapi.org/v2/top-headlines", params=params, timeout=10)
            r.raise_for_status()
            for a in r.json().get("articles", []):
                title = a.get("title", "")
                if title and "[Removed]" not in title and title not in seen:
                    seen.add(title)
                    all_articles.append({
                        "title": title,
                        "description": a.get("description", "") or "",
                        "source": a.get("source", {}).get("name", ""),
                        "country": query.get("country", ""),
                    })
        except Exception as e:
            print(f"  Warning: {e}")
    print(f"  Total articles: {len(all_articles)}")
    return all_articles

def get_brief(articles):
    news_block = "\n".join(
        f"[{a['source']} | {a['country'].upper()}] {a['title']}. {a['description'][:120]}"
        for a in articles
    )

    prompt = (
        "You are a senior financial analyst. Write a morning market brief for a finance student "
        "at Monash University, Australia. She follows ASX, AUD, RBA, global macro, tech stocks, and interest rates.\n\n"
        "FORMATTING RULES:\n"
        "- Use **word** (double asterisks) to bold important terms, numbers, names. Bold 2-3 things per paragraph.\n"
        "- Write in prose paragraphs only. No bullet points, no dashes at line starts.\n"
        "- No other markdown symbols.\n\n"
        "Include ALL of these sections with headers exactly as written:\n\n"
        "MARKET MOOD\n"
        "One sentence. Risk-on, risk-off, or uncertain, and the biggest reason. Bold the mood label.\n\n"
        "MOST IMPORTANT\n"
        "The top story. Two paragraphs. What happened, why it matters, what comes next.\n\n"
        "AUSTRALIA AND ASX\n"
        "Two paragraphs on Australian news, ASX, AUD, RBA. Connect global events to Australian impact.\n\n"
        "AMERICA AND GLOBAL\n"
        "Two paragraphs on biggest US or global macro story. Explain implications, not just facts.\n\n"
        "BUSINESS\n"
        "One to two paragraphs on corporate news, earnings, or deals.\n\n"
        "TECH AND AI\n"
        "One to two paragraphs on the most important tech or AI story and why a finance student should care.\n\n"
        "NEWS RUNDOWN\n"
        "Pick the 8 most important stories. For each story write exactly these three lines with no extra text:\n"
        "HEADLINE: [title of the story in plain text]\n"
        "MOOD: [write exactly one word: Bullish or Bearish or Neutral or Mixed]\n"
        "IMPACT: [one sentence explaining what this means for markets or investors]\n"
        "Leave a blank line between each story.\n\n"
        "THE BIGGER PICTURE\n"
        "One paragraph on what today's news tells us about the macro environment.\n\n"
        "INDICATORS TO WATCH TODAY\n"
        "Three to four short paragraphs. Each names a specific indicator or asset, states what to watch for, and explains why.\n\n"
        f"Headlines:\n{news_block}\n\n"
        "Be direct and clear. No filler."
    )

    response = ollama.generate(model=MODEL, prompt=prompt)
    return response["response"]

SECTION_ALIASES = {
    "MARKET MOOD":               ["MARKET MOOD"],
    "MOST IMPORTANT":            ["MOST IMPORTANT", "TOP STORY"],
    "AUSTRALIA AND ASX":         ["AUSTRALIA", "ASX"],
    "AMERICA AND GLOBAL":        ["AMERICA", "GLOBAL", "US MARKET"],
    "BUSINESS":                  ["BUSINESS", "CORPORATE"],
    "TECH AND AI":               ["TECH AND AI", "TECH &", "TECHNOLOGY AND AI",
                                  "AI AND TECH", "TECHNOLOGY & AI", "ARTIFICIAL INTELLIGENCE"],
    "NEWS RUNDOWN":              ["NEWS RUNDOWN", "RUNDOWN", "STORY BREAKDOWN"],
    "THE BIGGER PICTURE":        ["BIGGER PICTURE", "BIG PICTURE", "MACRO PICTURE"],
    "INDICATORS TO WATCH TODAY": ["INDICATORS", "WATCH TODAY", "TO WATCH", "WHAT TO WATCH"],
}

def is_header(line):
    up = line.strip().upper()
    if len(up) > 80 or len(up) < 3:
        return None
    for key, aliases in SECTION_ALIASES.items():
        if any(a in up for a in aliases):
            return key
    return None

def parse_sections(text):
    sections = {}
    current = None
    buf = []
    for line in text.split("\n"):
        h = is_header(line)
        if h:
            if current and buf:
                sections[current] = "\n".join(buf).strip()
            current = h
            buf = []
        elif current:
            cleaned = line.strip().lstrip("-*").strip()
            if cleaned:
                buf.append(cleaned)
    if current and buf:
        sections[current] = "\n".join(buf).strip()
    return sections

def to_html(text):
    if not text:
        return "<p>Not available.</p>"
    html = []
    for line in text.split("\n"):
        line = line.strip().lstrip("-*").strip()
        if not line:
            continue
        # Convert **bold** to HTML strong
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        html.append(f"<p>{line}</p>")
    return "\n".join(html) or "<p>Not available.</p>"

def parse_rundown(text):
    items = []
    current = {}
    for line in text.split("\n"):
        l = line.strip()
        if not l:
            if "headline" in current and "mood" in current:
                items.append(current)
                current = {}
            continue
        low = l.lower()
        if low.startswith("headline:"):
            if "headline" in current:
                items.append(current)
            current = {"headline": l.split(":", 1)[1].strip()}
        elif low.startswith("mood:"):
            current["mood"] = l.split(":", 1)[1].strip()
        elif low.startswith("impact:"):
            current["impact"] = l.split(":", 1)[1].strip()
    if "headline" in current:
        items.append(current)
    return items

def mood_chip(mood):
    m = (mood or "").lower()
    if "bull" in m: return "BULLISH", "#d4edda", "#155724"
    if "bear" in m: return "BEARISH", "#f8d7da", "#721c24"
    if "mix"  in m: return "MIXED",   "#fff3cd", "#856404"
    return "NEUTRAL", "#e2e3e5", "#383d41"

def generate_html(brief_text, article_count):
    now      = datetime.now()
    date_str = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%I:%M %p")
    s        = parse_sections(brief_text)

    def block(label, key, color="#666"):
        return (
            f'<div class="section">' +
            f'<div class="lbl" style="color:{color}">{label}</div>' +
            f'<div class="section-body">{to_html(s.get(key,""))}</div>' +
            f'</div>'
        )

    rundown_items = parse_rundown(s.get("NEWS RUNDOWN", ""))
    rundown_html = ""
    for item in rundown_items:
        chip_lbl, chip_bg, chip_fg = mood_chip(item.get("mood", ""))
        impact = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', item.get("impact", ""))
        rundown_html += (
            f'<div class="news-item">' +
            f'<span class="chip" style="background:{chip_bg};color:{chip_fg}">{chip_lbl}</span>' +
            f'<div><div class="news-hl">{item.get("headline","")}</div>' +
            f'<div class="news-imp">{impact}</div></div></div>'
        )

    mood_html = to_html(s.get("MARKET MOOD", ""))

    css = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f9f7f3;color:#111;font-family:'Source Serif 4',Georgia,serif;font-weight:300;font-size:16px;line-height:1.8}
.masthead{background:#111;color:#f9f7f3;padding:22px 44px;display:flex;justify-content:space-between;align-items:baseline}
.m-title{font-family:'Playfair Display',serif;font-size:24px;font-weight:700}
.m-meta{font-size:12px;color:#777;text-align:right;line-height:1.6}
.moodbar{background:#0d0d0d;padding:12px 44px;border-top:1px solid #222}
.moodbar p{color:#d4a843;font-family:'Playfair Display',serif;font-style:italic;font-size:15px}
.moodbar strong{color:#f5c842;font-weight:700}
.highlight{background:#111;padding:30px 44px}
.highlight .lbl{color:#c8a84b;font-family:'Playfair Display',serif;font-size:10px;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;margin-bottom:14px}
.highlight p{color:#e8e3d8;font-size:16px;line-height:1.85;margin-bottom:12px}
.highlight strong{color:#ffd97d;font-weight:700}
.wrap{max-width:800px;margin:0 auto;padding:0 44px 60px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:44px}
.section{padding:34px 0;border-bottom:1px solid #e5e0d8}
.section:last-child{border-bottom:none}
.lbl{font-family:'Playfair Display',serif;font-size:10px;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;margin-bottom:14px}
.section-body p{font-size:16px;line-height:1.85;margin-bottom:13px;font-weight:300}
.section-body p:last-child{margin-bottom:0}
strong{font-weight:700;color:#000}
.rundown{background:#f3ede3;padding:30px 44px}
.news-item{display:flex;gap:14px;align-items:flex-start;padding:14px 0;border-bottom:1px solid #e0d8cc}
.news-item:last-child{border-bottom:none}
.chip{font-size:9px;font-weight:700;letter-spacing:1px;padding:3px 8px;border-radius:3px;white-space:nowrap;margin-top:4px;font-family:'Playfair Display',serif}
.news-hl{font-family:'Playfair Display',serif;font-size:14px;font-weight:600;line-height:1.4;margin-bottom:4px}
.news-imp{font-size:13px;color:#555;line-height:1.6;font-weight:300}
.news-imp strong{font-weight:600;color:#333}
.watch{background:#fff;padding:30px 44px;border-top:3px solid #b03030}
.watch strong{color:#b03030;font-weight:700}
footer{text-align:center;font-size:11px;color:#bbb;padding:24px;letter-spacing:.5px}
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morning Brief &mdash; {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Source+Serif+4:wght@300;400;500&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<div class="masthead">
  <div class="m-title">Morning Brief</div>
  <div class="m-meta">{date_str}<br>{time_str} &middot; {article_count} articles</div>
</div>
<div class="moodbar">{mood_html}</div>
<div class="highlight">
  <div class="lbl">Most Important</div>
  <div>{to_html(s.get("MOST IMPORTANT",""))}</div>
</div>
<div class="wrap">
  <div class="grid2">
    {block("Australia &amp; ASX","AUSTRALIA AND ASX","#2e6b3e")}
    {block("America &amp; Global","AMERICA AND GLOBAL","#1a4a8a")}
  </div>
  <div class="grid2">
    {block("Business","BUSINESS","#444")}
    {block("Tech &amp; AI","TECH AND AI","#5b1a8a")}
  </div>
  {block("The Bigger Picture","THE BIGGER PICTURE","#888")}
</div>
<div class="rundown">
  <div class="lbl" style="margin-bottom:18px">News Rundown</div>
  {rundown_html if rundown_html else "<p style='color:#888;font-size:14px'>Rundown not generated this run.</p>"}
</div>
<div class="watch">
  <div class="lbl" style="color:#b03030;margin-bottom:14px">Indicators To Watch Today</div>
  <div class="section-body">{to_html(s.get("INDICATORS TO WATCH TODAY",""))}</div>
</div>
<footer>Mistral via Ollama &middot; NewsAPI &middot; {date_str}</footer>
</body></html>"""

if __name__ == "__main__":
    if not NEWS_API_KEY:
        print("ERROR: NEWS_API_KEY not found. Check your .env file.")
        exit(1)
    print("Fetching news...")
    articles = get_all_articles()
    if not articles:
        print("No articles fetched. Check your API key.")
        exit(1)
    print("Asking Mistral to write your brief... (30-45 seconds)\n")
    brief = get_brief(articles)
    html  = generate_html(brief, len(articles))
    with open(OUTPUT_FILE, "w") as f:
        f.write(html)
    print("Done. Opening in browser...")
    webbrowser.open(f"file://{os.path.abspath(OUTPUT_FILE)}")
