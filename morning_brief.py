import requests
import webbrowser
import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

NEWS_API_KEY  = os.getenv("NEWS_API_KEY")
GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
IN_CLOUD      = bool(os.getenv("GITHUB_ACTIONS"))   # True when running in GitHub Actions
OUTPUT_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "index.html" if IN_CLOUD else "brief.html")

FEED_QUERIES = [
    # Major global financial sources only
    {"sources": "bloomberg,reuters,cnbc,the-wall-street-journal", "pageSize": 15},
    {"sources": "financial-times,fortune,associated-press",        "pageSize": 10},
    # Australian business news
    {"country": "au", "category": "business", "pageSize": 10},
]

def get_all_articles():
    all_articles = []
    seen = set()
    for query in FEED_QUERIES:
        params = {**query, "apiKey": NEWS_API_KEY}
        try:
            r = requests.get("https://newsapi.org/v2/top-headlines", params=params, timeout=10)
            data = r.json()
            if data.get("status") != "ok":
                print(f"  API error: {data.get('message', data)}")
                continue
            for a in data.get("articles", []):
                title = a.get("title", "")
                if not title or "[Removed]" in title or title in seen:
                    continue
                seen.add(title)
                all_articles.append({
                    "title": title,
                    "description": a.get("description", "") or "",
                    "source": a.get("source", {}).get("name", ""),
                    "url": a.get("url", ""),
                    "publishedAt": a.get("publishedAt", ""),
                })
        except Exception as e:
            print(f"  Warning: {e}")
    print(f"  Total articles: {len(all_articles)}")
    return all_articles

def get_brief(articles):
    news_block = "\n".join(
        f"[{a['source']}] {a['title']}. {a['description'][:120]}"
        for a in articles
    )

    prompt = (
        "You are writing a morning market brief for a finance student at Monash University in Australia. "
        "Write like a smart analyst talking to a colleague, not a textbook. Conversational but sharp. "
        "She follows the ASX, AUD, RBA, global macro, tech stocks and interest rates.\n\n"
        "STRICT RULE: Every fact, figure, company name, and event you write must come directly from the headlines below. "
        "Do not use anything from your training data. Do not invent numbers, earnings results, price moves, or events "
        "not in the headlines. If a section has no relevant headlines, write: Not enough news today to cover this.\n\n"
        "STYLE:\n"
        "- Bold 2-3 key terms or numbers per paragraph using **word**\n"
        "- Prose only, no bullet points or dashes\n"
        "- Short paragraphs, plain language, no jargon for its own sake\n\n"
        "Write ALL of these sections with these exact headers:\n\n"
        "MARKET MOOD\n"
        "One sentence. Is it risk-on, risk-off, or uncertain today and why? Bold the mood label.\n\n"
        "MOST IMPORTANT\n"
        "The single biggest story from the headlines. Two paragraphs: what happened, why it matters for markets.\n\n"
        "AUSTRALIA AND ASX\n"
        "Two paragraphs on anything Australia-related in the headlines: ASX, AUD, RBA, local economy.\n\n"
        "AMERICA AND GLOBAL\n"
        "Two paragraphs on the biggest US or global story and what it means.\n\n"
        "BUSINESS\n"
        "One to two paragraphs on corporate news, deals, or earnings from the headlines.\n\n"
        "TECH AND AI\n"
        "One to two paragraphs on the most important tech or AI story and why it matters to investors.\n\n"
        "NEWS RUNDOWN\n"
        "Pick the 8 most important stories from the headlines. For each write exactly:\n"
        "HEADLINE: [the headline in plain text, as close to the original as possible]\n"
        "MOOD: [one word only: Bullish or Bearish or Neutral or Mixed]\n"
        "IMPACT: [one plain sentence on what this means for markets]\n"
        "Blank line between each story.\n\n"
        "THE BIGGER PICTURE\n"
        "One paragraph on what today's headlines together say about where markets are heading.\n\n"
        "INDICATORS TO WATCH TODAY\n"
        "Three to four paragraphs. Each one names a real indicator or asset from today's news, "
        "says what to watch for, and explains why it matters today specifically.\n\n"
        f"Today's headlines:\n{news_block}\n\n"
        "Only write about what is in these headlines. Nothing else."
    )

    if GROQ_API_KEY:
        # Cloud mode: use Groq (free, fast)
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
        )
        return response.choices[0].message.content
    else:
        # Local mode: use Ollama/Mistral
        import ollama
        response = ollama.generate(model="mistral", prompt=prompt)
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
    "INDICATORS TO WATCH TODAY": ["INDICATORS", "WATCH TODAY", "TO WATCH", "WHAT TO WATCH", "INSIGHTS FOR INVESTORS", "INSIGHTS", "KEY TAKEAWAY", "INVESTOR INSIGHT"],
}

def is_header(line):
    stripped = line.strip()
    # Strip common formatting: numbers, asterisks, hashes, colons
    cleaned = re.sub(r'^\d+[\.\)]\s*', '', stripped)
    cleaned = cleaned.strip('*#- ').strip().rstrip(':').strip()

    # Must be mostly uppercase — real headers are all caps, content lines are not
    letters = [c for c in cleaned if c.isalpha()]
    if not letters:
        return None
    uppercase_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if uppercase_ratio < 0.75:
        return None

    up = cleaned.upper()
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
            # Capture inline content after colon e.g. "MARKET MOOD: Risk-on today"
            stripped = line.strip().strip('*#').strip()
            if ':' in stripped:
                inline = stripped.split(':', 1)[1].strip().strip('*').strip()
                if inline and len(inline) > 2:
                    buf.append(inline)
        elif current:
            cleaned = line.strip().lstrip("- ").strip()
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
        # Convert **bold** to HTML strong, then strip any stray asterisks
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        line = line.replace('*', '')
        html.append(f"<p>{line}</p>")
    return "\n".join(html) or "<p>Not available.</p>"

def parse_rundown(text):
    items = []
    current = {}
    for line in text.split("\n"):
        l = line.strip()
        # Treat blank lines and --- separators the same way
        is_separator = not l or l.startswith("---") or l.startswith("***")
        if is_separator:
            if "headline" in current and "mood" in current:
                items.append(current)
                current = {}
            continue
        low = l.lower()
        if low.startswith("headline:"):
            if "headline" in current:
                items.append(current)
                current = {}
            current = {"headline": l.split(":", 1)[1].strip()}
        elif low.startswith("mood:"):
            raw = l.split(":", 1)[1].strip()
            current["mood"] = raw.split()[0]  # take first word only e.g. "Mixed" not "Mixed (repeated...)"
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

def find_url(headline, articles):
    """Find the best matching article URL for a rundown headline."""
    headline_words = set(headline.lower().split())
    best_score = 0
    best_url = ""
    for a in articles:
        title_words = set(a["title"].lower().split())
        score = len(headline_words & title_words)
        if score > best_score:
            best_score = score
            best_url = a["url"]
    return best_url if best_score >= 3 else ""

def generate_html(brief_text, article_count, articles=None):
    now      = datetime.now()
    date_str = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%I:%M %p")
    s        = parse_sections(brief_text)

    def block(label, key, color="#b8860b"):
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
        hl = item.get("headline", "")
        url = find_url(hl, articles or [])
        hl_html = (
            f'<a href="{url}" target="_blank" rel="noopener" class="news-link">{hl}</a>'
            if url else hl
        )
        rundown_html += (
            f'<div class="news-item">' +
            f'<span class="chip" style="background:{chip_bg};color:{chip_fg}">{chip_lbl}</span>' +
            f'<div><div class="news-hl">{hl_html}</div>' +
            f'<div class="news-imp">{impact}</div></div></div>'
        )

    mood_html = to_html(s.get("MARKET MOOD", ""))

    css = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#fafaf7;color:#1c1c1c;font-family:'IM Fell English',Georgia,serif;font-size:19px;line-height:2.0}

/* ── Masthead ── */
.masthead{background:#111;padding:28px 52px;display:flex;justify-content:space-between;align-items:baseline}
.m-title{font-family:'Playfair Display',serif;font-size:32px;font-weight:700;color:#d4a843;letter-spacing:-0.5px}
.m-meta{font-size:13px;color:#c8a84b;text-align:right;line-height:1.8;letter-spacing:0.3px}

/* ── Mood bar ── */
.moodbar{background:#1a1a1a;padding:14px 52px;border-top:1px solid #333}
.moodbar p{font-family:'Playfair Display',serif;font-style:italic;font-size:17px;color:#d4a843}
.moodbar strong{color:#f5d060;font-weight:700}

/* ── Most Important (dark) ── */
.highlight{background:#111;padding:40px 52px;border-top:2px solid #d4a843}
.highlight .lbl{font-family:'Playfair Display',serif;font-size:10px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:#c8a84b;margin-bottom:18px}
.highlight p{color:#ede8dc;font-size:18px;line-height:2.0;margin-bottom:14px}
.highlight strong{color:#f5d060;font-weight:700}

/* ── White sections ── */
.wrap{max-width:860px;margin:0 auto;padding:0 52px 70px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:52px}
.section{padding:36px 0;border-bottom:1px solid #e8e4dc}
.section:last-child{border-bottom:none}
.lbl{font-family:'Playfair Display',serif;font-size:10px;font-weight:700;letter-spacing:3px;text-transform:uppercase;margin-bottom:16px;color:#b8860b}
.section-body p{font-size:18px;line-height:2.0;margin-bottom:14px;color:#2a2a2a}
.section-body p:last-child{margin-bottom:0}
strong{font-weight:700;color:#8b6400}

/* ── News Rundown (dark) ── */
.rundown{background:#111;padding:40px 52px;border-top:2px solid #d4a843}
.rundown .lbl{color:#c8a84b}
.news-item{display:flex;gap:16px;align-items:flex-start;padding:20px 0;border-bottom:1px solid #2a2a2a}
.news-item:last-child{border-bottom:none}
.chip{font-size:10px;font-weight:700;letter-spacing:0.8px;padding:5px 11px;border-radius:3px;white-space:nowrap;margin-top:4px;font-family:'Playfair Display',serif}
.news-hl{font-family:'Playfair Display',serif;font-size:16px;font-weight:600;line-height:1.5;margin-bottom:7px;color:#ede8dc}
.news-link{color:#d4a843;text-decoration:none;border-bottom:1px solid #6b5010}
.news-link:hover{color:#f5d060;border-bottom-color:#d4a843}
.news-imp{font-size:14px;color:#999;line-height:1.75}
.news-imp strong{color:#c8a84b;font-weight:600}

/* ── Watch section ── */
.watch{background:#fafaf7;padding:40px 52px;border-top:3px solid #d4a843}
.watch .lbl{color:#b8860b}
.watch .section-body p{color:#2a2a2a}
.watch strong{color:#8b6400;font-weight:700}

/* ── Footer ── */
footer{text-align:center;font-size:13px;color:#c8a84b;background:#111;padding:22px;letter-spacing:0.5px;border-top:1px solid #2a2a2a}
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morning Brief &mdash; {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&family=IM+Fell+English:ital@0;1&display=swap" rel="stylesheet">
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
<footer>{"Llama 3.3 via Groq" if IN_CLOUD else "Mistral via Ollama"} &middot; NewsAPI &middot; {date_str}</footer>
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
    ai_name = "Groq (cloud)" if GROQ_API_KEY else "Mistral (local, ~3 mins)"
    print(f"Generating brief with {ai_name}...\n")
    brief = get_brief(articles)
    html  = generate_html(brief, len(articles), articles)
    with open(OUTPUT_FILE, "w") as f:
        f.write(html)
    print(f"Done. Saved to {OUTPUT_FILE}")
    if not IN_CLOUD:
        webbrowser.open(f"file://{os.path.abspath(OUTPUT_FILE)}")
