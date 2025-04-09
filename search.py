from flask import Flask, request, render_template_string, redirect, url_for
import subprocess
import sys
from datetime import datetime, timezone

app = Flask(__name__)

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

for pkg in ["torch", "requests", "beautifulsoup4", "transformers", "duckduckgo-search"]:
    try:
        __import__(pkg if pkg != "beautifulsoup4" else "bs4")
    except ImportError:
        install(pkg)

import torch
import requests
from bs4 import BeautifulSoup
from transformers import pipeline
from duckduckgo_search import DDGS
from urllib.parse import urlparse
import re

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6", device=0 if torch.cuda.is_available() else -1)

def human_readable_time_ago(date_str):
    try:
        past_time = datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - past_time
        seconds = diff.total_seconds()
        minutes = int(seconds // 60)
        hours = int(minutes // 60)
        days = int(hours // 24)
        months = int(days // 30)

        if seconds < 60:
            return "Just now"
        elif minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif days < 30:
            return f"{days} day{'s' if days != 1 else ''} ago"
        else:
            return f"{months} month{'s' if months != 1 else ''} ago"
    except:
        return "Unknown time"

def search_duckduckgo(query, max_results=100, search_type="text", news_category=None):
    with DDGS() as ddgs:
        if search_type == "text":
            return [r for r in ddgs.text(query, max_results=max_results)]
        elif search_type == "image":
            return [r for r in ddgs.images(query, max_results=max_results)]
        elif search_type in ["news", "stories"]:
            if news_category and search_type == "news":
                category_queries = {
                    "general": query,
                    "political": f"{query} politics",
                    "business": f"{query} business finance",
                    "technology": f"{query} technology tech",
                    "education": f"{query} education",
                    "entertainment": f"{query} entertainment",
                    "sports": f"{query} sports",
                    "weather": f"{query} weather",
                    "science": f"{query} science",
                    "health": f"{query} health"
                }
                query = category_queries.get(news_category, query)
            return sorted([r for r in ddgs.news(query, max_results=max_results)], key=lambda x: x.get("date", ""), reverse=True)
        elif search_type == "video":
            return [r for r in ddgs.videos(query, max_results=max_results)]
        elif search_type == "shopping":
            return [r for r in ddgs.text(f"{query} site:*.com | site:*.co | site:*.in -inurl:(login | signup)", max_results=max_results)]
        else:
            return []

def fetch_page_content(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        text = "\n".join([p.get_text() for p in paragraphs[:3]])
        return text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def summarize_text(text):
    if len(text.split()) < 50:
        return text
    try:
        summary = summarizer(text, max_length=200, min_length=50, do_sample=False)
        return summary[0]['summary_text']
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return text

def get_favicon_url(url):
    try:
        domain = urlparse(url).netloc
        favicon_url = f"https://{domain}/favicon.ico"
        response = requests.head(favicon_url, timeout=5)
        if response.status_code == 200:
            return favicon_url
        return f"https://www.google.com/s2/favicons?domain={domain}"
    except Exception:
        return "https://www.google.com/s2/favicons?domain=example.com"

def get_website_name(url):
    return urlparse(url).netloc

def extract_price_and_image(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        
        price = "Price not found"
        price_patterns = [
            r'\$\d+\.?\d*', 
            r'USD\s*\d+\.?\d*', 
            r'₹\s*\d+,?\d*\.?\d*',
        ]
        for tag in soup.find_all(['span', 'div', 'p'], class_=['price', 'amount', 'cost', 'product-price', 'price-tag', 'deal']):
            text = tag.get_text().strip()
            for pattern in price_patterns:
                match = re.search(pattern, text)
                if match:
                    price = match.group()
                    break
            if price != "Price not found":
                break
        
        image = "https://via.placeholder.com/600x400?text=No+Image"  # Larger default for primary story
        for img in soup.find_all('img', class_=['product-image', 'thumbnail', 'main-image', 'item-image', 'hero-image']):
            if img.get('src'):
                image = img['src']
                if not image.startswith('http'):
                    image = urlparse(url).scheme + "://" + urlparse(url).netloc + image
                break
        if image == "https://via.placeholder.com/600x400?text=No+Image":
            for img in soup.find_all('img'):
                if 'article' in str(img.get('alt', '').lower()) or 'news' in str(img.get('alt', '').lower()) or 'featured' in str(img.get('alt', '').lower()):
                    image = img.get('src', image)
                    if not image.startswith('http'):
                        image = urlparse(url).scheme + "://" + urlparse(url).netloc + image
                    break

        return price, image
    except Exception as e:
        print(f"Error processing {url}: {e}")
        return "Price not found", "https://via.placeholder.com/600x400?text=No+Image"

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        query = request.form.get("query")
        return redirect(url_for("results", query=query, type="text"))
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Starry Search</title>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    height: 100vh;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    background: linear-gradient(to bottom, #0f0c29, #302b63, #24243e);
                    color: white;
                    font-family: 'Arial', sans-serif;
                    overflow: hidden;
                    position: relative;
                }
                .search-container {
                    text-align: center;
                    z-index: 10;
                }
                h1 {
                    font-size: 2.5rem;
                    margin-bottom: 2rem;
                    text-shadow: 0 0 10px rgba(255,255,255,0.5);
                }
                form {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                }
                input {
                    padding: 15px 20px;
                    width: 500px;
                    border: none;
                    border-radius: 30px;
                    font-size: 1.2rem;
                    outline: none;
                    box-shadow: 0 0 20px rgba(0,0,0,0.2);
                    margin-bottom: 20px;
                }
                button {
                    padding: 12px 30px;
                    background: #4e54c8;
                    color: white;
                    border: none;
                    border-radius: 30px;
                    font-size: 1.1rem;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    box-shadow: 0 0 15px rgba(78, 84, 200, 0.5);
                }
                button:hover {
                    background: #6a6fd1;
                    transform: scale(1.05);
                }
                .star {
                    position: absolute;
                    background-color: white;
                    border-radius: 50%;
                    animation: twinkle var(--duration) infinite ease-in-out;
                    opacity: 0;
                }
                @keyframes twinkle {
                    0%, 100% { opacity: 0; }
                    50% { opacity: var(--opacity); }
                }
            </style>
        </head>
        <body>
            <div class="search-container">
                <h1>✨ Starry Search ✨</h1>
                <form method="POST">
                    <input name="query" placeholder="Search the universe..." required>
                    <button type="submit">Explore</button>
                </form>
            </div>
            <script>
                function createStars() {
                    const count = 150;
                    const container = document.body;
                    for (let i = 0; i < count; i++) {
                        const star = document.createElement('div');
                        star.classList.add('star');
                        const size = Math.random() * 3;
                        const posX = Math.random() * window.innerWidth;
                        const posY = Math.random() * window.innerHeight;
                        const opacity = Math.random();
                        const duration = 2 + Math.random() * 3;
                        const delay = Math.random() * 5;
                        star.style.width = `${size}px`;
                        star.style.height = `${size}px`;
                        star.style.left = `${posX}px`;
                        star.style.top = `${posY}px`;
                        star.style.setProperty('--opacity', opacity);
                        star.style.setProperty('--duration', `${duration}s`);
                        star.style.animationDelay = `${delay}s`;
                        container.appendChild(star);
                    }
                }
                window.addEventListener('load', createStars);
            </script>
        </body>
        </html>
    ''')

@app.route("/results")
def results():
    query = request.args.get("query")
    search_type = request.args.get("type", "text")
    news_category = request.args.get("news_category", None)
    page = request.args.get("page", 1, type=int)
    per_page = 10
    results = search_duckduckgo(query, max_results=100, search_type=search_type, news_category=news_category)
    
    total_results = len(results)
    total_pages = (total_results + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, total_results)
    page_results = results[start_idx:end_idx]

    top_stories = []
    if search_type == "stories":
        top_stories = search_duckduckgo(query, max_results=5, search_type="stories")[:5]
        for story in top_stories:
            url = story.get("url")
            if url:
                story["favicon"] = get_favicon_url(url)
                story["website"] = get_website_name(url)
                story["thumbnail"] = story.get("image", "https://via.placeholder.com/600x400?text=No+Image")
                content = fetch_page_content(url)
                story["summary"] = summarize_text(content) if content else story.get("body", "No description available.")
                if "via.placeholder.com" in story["thumbnail"]:
                    _, new_image = extract_price_and_image(url)
                    story["thumbnail"] = new_image

    for result in page_results:
        url = result.get("href") or result.get("url")
        if url:
            result["favicon"] = get_favicon_url(url)
        if search_type == "news":
            result["thumbnail"] = result.get("image", "https://via.placeholder.com/100x100?text=No+Image")
        if search_type == "shopping":
            price, image = extract_price_and_image(url)
            result["price"] = price
            result["thumbnail"] = image

    summary = None
    if search_type == "text":
        all_text = ""
        for r in results[:2]:
            url = r.get("href") or r.get("url")
            if url:
                content = fetch_page_content(url)
                if content:
                    all_text += content + "\n"
        if all_text.strip():
            summary = summarize_text(all_text)
        else:
            summary = "Unable to generate summary due to lack of fetchable content."

    news_categories = [
        ("general", "🗞️ General News"),
        ("political", "⚖️ Political News"),
        ("business", "💹 Business & Finance News"),
        ("technology", "🤖 Technology News"),
        ("education", "🎓 Education News"),
        ("entertainment", "🎭 Entertainment News"),
        ("sports", "🏆 Sports News"),
        ("weather", "🌦️ Weather News"),
        ("science", "🌐 Science News"),
        ("health", "🧘 Health News")
    ]

    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Search Results - Starry Search</title>
            <style>
                body {
                    background: linear-gradient(to bottom, #0f0c29, #302b63);
                    color: white;
                    font-family: 'Arial', sans-serif;
                    padding: 2rem;
                    max-width: 1200px;
                    margin: 0 auto;
                }
                h2 {
                    color: #fff;
                    margin-bottom: 1rem;
                }
                h3 {
                    color: #ccc;
                    margin: 1.5rem 0;
                }
                .search-bar {
                    margin-bottom: 1rem;
                }
                .search-bar form {
                    display: flex;
                    align-items: center;
                }
                .search-bar input {
                    padding: 10px;
                    width: 500px;
                    border: none;
                    border-radius: 20px 0 0 20px;
                    font-size: 1rem;
                    outline: none;
                }
                .search-bar button {
                    padding: 10px 20px;
                    background: #4e54c8;
                    color: white;
                    border: none;
                    border-radius: 0 20px 20px 0;
                    cursor: pointer;
                    transition: background 0.3s ease;
                }
                .search-bar button:hover {
                    background: #6a6fd1;
                }
                .tabs {
                    display: flex;
                    gap: 10px;
                    margin-bottom: 2rem;
                }
                .tabs a {
                    padding: 10px 20px;
                    background: rgba(255,255,255,0.1);
                    color: white;
                    text-decoration: none;
                    border-radius: 20px;
                    transition: all 0.3s ease;
                }
                .tabs a:hover {
                    background: rgba(255,255,255,0.2);
                }
                .tabs a.active {
                    background: #4e54c8;
                }
                .news-categories {
                    margin-bottom: 1rem;
                }
                .news-categories select {
                    padding: 10px;
                    background: rgba(255,255,255,0.1);
                    color: white;
                    border: none;
                    border-radius: 20px;
                    font-size: 1rem;
                    cursor: pointer;
                    outline: none;
                }
                .news-categories select option {
                    background: #0f0c29;
                }
                .top-stories {
                    display: flex;
                    gap: 20px;
                    margin-bottom: 2rem;
                }
                .primary-story {
                    flex: 2;
                    background: rgba(255,255,255,0.1);
                    padding: 20px;
                    border-radius: 8px;
                    transition: transform 0.2s;
                }
                .primary-story:hover {
                    transform: scale(1.02);
                }
                .primary-story img.thumbnail {
                    width: 100%;
                    height: 400px;
                    object-fit: cover;
                    border-radius: 8px;
                    margin-bottom: 15px;
                }
                .primary-story h4 {
                    margin: 0 0 10px 0;
                    font-size: 1.8rem;
                }
                .primary-story .website {
                    font-size: 1.1rem;
                    color: #90ee90;
                    margin-bottom: 5px;
                }
                .primary-story img.favicon {
                    width: 24px;
                    height: 24px;
                    vertical-align: middle;
                    margin-right: 5px;
                }
                .secondary-stories {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                    gap: 15px;
                }
                .secondary-story {
                    background: rgba(255,255,255,0.1);
                    padding: 15px;
                    border-radius: 8px;
                    transition: transform 0.2s;
                }
                .secondary-story:hover {
                    transform: scale(1.02);
                }
                .secondary-story img.thumbnail {
                    width: 100%;
                    height: 150px;
                    object-fit: cover;
                    border-radius: 8px;
                    margin-bottom: 10px;
                }
                .secondary-story h5 {
                    margin: 0 0 8px 0;
                    font-size: 1.2rem;
                }
                .secondary-story .website {
                    font-size: 0.9rem;
                    color: #90ee90;
                    margin-bottom: 5px;
                }
                .secondary-story img.favicon {
                    width: 16px;
                    height: 16px;
                    vertical-align: middle;
                    margin-right: 5px;
                }
                .result {
                    background: rgba(255,255,255,0.1);
                    padding: 1rem;
                    border-radius: 8px;
                    margin-bottom: 1rem;
                    display: flex;
                    align-items: center;
                    gap: 15px;
                }
                .result img.favicon {
                    width: 16px;
                    height: 16px;
                    margin-right: 10px;
                }
                .result img.thumbnail {
                    width: 100px;
                    height: 100px;
                    object-fit: cover;
                    border-radius: 4px;
                }
                .shopping-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
                    gap: 20px;
                }
                .shopping-result {
                    background: rgba(255,255,255,0.1);
                    padding: 15px;
                    border-radius: 8px;
                    text-align: center;
                    transition: transform 0.2s;
                }
                .shopping-result:hover {
                    transform: scale(1.05);
                }
                .shopping-result img {
                    max-width: 150px;
                    height: 150px;
                    object-fit: contain;
                    border-radius: 4px;
                    margin-bottom: 10px;
                }
                .image-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                    gap: 10px;
                }
                .image-result {
                    background: rgba(255,255,255,0.1);
                    padding: 10px;
                    border-radius: 8px;
                    text-align: center;
                }
                .image-result img {
                    max-width: 100%;
                    height: auto;
                    border-radius: 4px;
                }
                a {
                    color: #6a6fd1;
                    text-decoration: none;
                }
                a:hover {
                    text-decoration: underline;
                }
                .snippet {
                    color: #d3d3d3;
                    font-size: 0.9rem;
                    margin-top: 5px;
                }
                .price {
                    color: #90ee90;
                    font-weight: bold;
                    font-size: 1.1rem;
                    margin-top: 5px;
                }
                .pagination {
                    margin-top: 2rem;
                    text-align: center;
                }
                .pagination a, .pagination span {
                    padding: 0.5rem 1rem;
                    margin: 0 0.2rem;
                    background: rgba(255,255,255,0.1);
                    border-radius: 4px;
                    color: white;
                    text-decoration: none;
                }
                .pagination a:hover {
                    background: rgba(255,255,255,0.2);
                }
                .pagination .current {
                    background: #4e54c8;
                }
            </style>
        </head>
        <body>
            <div class="search-bar">
                <form method="POST" action="{{ url_for('results', type=search_type) }}">
                    <input name="query" value="{{query}}" placeholder="Search the universe..." required>
                    <button type="submit">Search</button>
                </form>
            </div>

            <h2>Results for: {{query}}</h2>

            <div class="tabs">
                <a href="{{ url_for('results', query=query, type='text', page=1) }}" class="{% if search_type == 'text' %}active{% endif %}">Text</a>
                <a href="{{ url_for('results', query=query, type='news', page=1) }}" class="{% if search_type == 'news' %}active{% endif %}">News</a>
                <a href="{{ url_for('results', query=query, type='image', page=1) }}" class="{% if search_type == 'image' %}active{% endif %}">Images</a>
                <a href="{{ url_for('results', query=query, type='video', page=1) }}" class="{% if search_type == 'video' %}active{% endif %}">Videos</a>
                <a href="{{ url_for('results', query=query, type='shopping', page=1) }}" class="{% if search_type == 'shopping' %}active{% endif %}">Shopping</a>
                <a href="{{ url_for('results', query=query, type='stories', page=1) }}" class="{% if search_type == 'stories' %}active{% endif %}">Stories</a>
            </div>

            {% if search_type == "news" %}
                <div class="news-categories">
                    <form method="GET" action="{{ url_for('results') }}">
                        <input type="hidden" name="query" value="{{query}}">
                        <input type="hidden" name="type" value="news">
                        <input type="hidden" name="page" value="1">
                        <select name="news_category" onchange="this.form.submit()">
                            <option value="" {% if not news_category %}selected{% endif %}>All News</option>
                            {% for value, label in news_categories %}
                                <option value="{{value}}" {% if news_category == value %}selected{% endif %}>{{label}}</option>
                            {% endfor %}
                        </select>
                    </form>
                </div>
            {% endif %}

            {% if search_type == "stories" and top_stories %}
                <div class="top-stories">
                    <div class="primary-story">
                        <img src="{{ top_stories[0].get('thumbnail') }}" class="thumbnail" alt="{{ top_stories[0].get('title', 'No Title') }}">
                        <h4><a href="{{ top_stories[0].get('url') }}">{{ top_stories[0].get("title", "No Title") }}</a></h4>
                        <div class="website">
                            <img src="{{ top_stories[0].get('favicon') }}" class="favicon" alt="favicon">
                            {{ top_stories[0].get("website") }}
                        </div>
                        <div class="snippet">{{ top_stories[0].get("summary") }}</div>
                        <span>{{ human_readable_time_ago(top_stories[0].get("date", "")) }}</span>
                    </div>
                    <div class="secondary-stories">
                        {% for story in top_stories[1:] %}
                            <div class="secondary-story">
                                <img src="{{ story.get('thumbnail') }}" class="thumbnail" alt="{{ story.get('title', 'No Title') }}">
                                <h5><a href="{{ story.get('url') }}">{{ story.get("title", "No Title")[:50] ~ "..." if story.get("title", "No Title")|length > 50 else story.get("title", "No Title") }}</a></h5>
                                <div class="website">
                                    <img src="{{ story.get('favicon') }}" class="favicon" alt="favicon">
                                    {{ story.get("website") }}
                                </div>
                                <div class="snippet">{{ story.get("summary")[:100] ~ "..." if story.get("summary")|length > 100 else story.get("summary") }}</div>
                                <span>{{ human_readable_time_ago(story.get("date", "")) }}</span>
                            </div>
                        {% endfor %}
                    </div>
                </div>
            {% endif %}

            {% if search_type == "text" and summary %}
                <h3>🧠 AI Summary:</h3>
                <div class="result">
                    <p>{{ summary }}</p>
                </div>
            {% endif %}

            {% if search_type == "image" %}
                <div class="image-grid">
                    {% for r in page_results %}
                        <div class="image-result">
                            <img src="{{ r.get('image') or r.get('content') }}" alt="{{ r.get('title', 'No Title') }}">
                            <div><a href="{{ r.get('url') }}">{{ r.get("title", "No Title") }}</a></div>
                            <img src="{{ r.get('favicon') }}" class="favicon" alt="favicon">
                        </div>
                    {% endfor %}
                </div>
            {% elif search_type == "shopping" %}
                <div class="shopping-grid">
                    {% for r in page_results %}
                        <div class="shopping-result">
                            <img src="{{ r.get('thumbnail') }}" alt="{{ r.get('title', 'No Title') }}">
                            <div><a href="{{ r.get('href') or r.get('url') }}">{{ r.get("title", "No Title")[:50] ~ "..." if r.get("title", "No Title")|length > 50 else r.get("title", "No Title") }}</a></div>
                            <div class="price">{{ r.get("price", "Price not found") }}</div>
                            <img src="{{ r.get('favicon') }}" class="favicon" alt="favicon">
                        </div>
                    {% endfor %}
                </div>
            {% elif search_type != "stories" %}
                {% for r in page_results %}
                    <div class="result">
                        {% if search_type == "text" %}
                            <img src="{{ r.get('favicon') }}" class="favicon" alt="favicon">
                            <div>
                                <b>{{ loop.index0 + start_idx + 1 }}. {{ r.get("title", "No Title") }}</b><br>
                                <a href="{{ r.get('href') or r.get('url') }}">{{ r.get('href') or r.get('url') }}</a>
                                <div class="snippet">{{ r.get("body", "No description available.") }}</div>
                            </div>
                        {% elif search_type == "news" %}
                            <img src="{{ r.get('thumbnail') }}" class="thumbnail" alt="thumbnail">
                            <div>
                                <img src="{{ r.get('favicon') }}" class="favicon" alt="favicon">
                                <b>{{ loop.index0 + start_idx + 1 }}. {{ r.get("title", "No Title") }} ({{ human_readable_time_ago(r.get("date", "")) }})</b><br>
                                <div class="snippet">{{ r.get("body", "No description available.") }}</div>
                                <a href="{{ r.get('url') }}">{{ r.get('url') }}</a>
                            </div>
                        {% elif search_type == "video" %}
                            <img src="{{ r.get('favicon') }}" class="favicon" alt="favicon">
                            <div>
                                <b>{{ loop.index0 + start_idx + 1 }}. {{ r.get("title", "No Title") }}</b><br>
                                {{ r.get("content", "") }}<br>
                                <a href="{{ r.get('url') }}">Watch Video</a>
                            </div>
                        {% endif %}
                    </div>
                {% endfor %}
            {% endif %}

            {% if search_type != "stories" %}
            <div class="pagination">
                {% if page > 1 %}
                    <a href="{{ url_for('results', query=query, type=search_type, news_category=news_category, page=page-1) }}">Previous</a>
                {% endif %}
                
                {% for p in range(1, total_pages + 1) %}
                    {% if p == page %}
                        <span class="current">{{ p }}</span>
                    {% else %}
                        <a href="{{ url_for('results', query=query, type=search_type, news_category=news_category, page=p) }}">{{ p }}</a>
                    {% endif %}
                {% endfor %}
                
                {% if page < total_pages %}
                    <a href="{{ url_for('results', query=query, type=search_type, news_category=news_category, page=page+1) }}">Next</a>
                {% endif %}
            </div>
            {% endif %}
        </body>
        </html>
    ''', query=query, search_type=search_type, news_category=news_category, results=results, page_results=page_results,
       page=page, total_pages=total_pages, start_idx=start_idx, summary=summary, news_categories=news_categories,
       top_stories=top_stories, fetch_page_content=fetch_page_content, summarize_text=summarize_text,
       human_readable_time_ago=human_readable_time_ago)

if __name__ == "__main__":
    app.run(debug=True)
