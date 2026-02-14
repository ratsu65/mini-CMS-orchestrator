# -*- coding: utf-8 -*-
"""تنظیمات متمرکز — تمام ثابت‌ها و مسیرها."""

import os

# --- تلگرام ---
BOT_TOKEN = "8240823331:AAEWcjoHQGUdL_ubE5wMgEtVAKleI0ODH0c"
CHAT_ID = "5446479004"

# --- CMS ---
CMS_USERNAME = "ramezani"
CMS_PASSWORD = "jIyMTg2NTI"
CMS_BASE_URL = "https://www.didbaniran.ir"
CMS_HEADLESS = False
CMS_COOKIES_FILE = "cms_cookies.pkl"

# --- شبکه ---
PROXY_URL = None
REQUEST_TIMEOUT = 30

# --- RSS ---
RSS_FEEDS = [
    "https://www.khabaronline.ir/rss/tp/1",
    "https://www.khabaronline.ir/rss/tp/2",
    "https://www.khabaronline.ir/rss/tp/4",
    "https://www.khabaronline.ir/rss/tp/5",
    "https://www.khabaronline.ir/rss/tp/7",
    "https://www.khabaronline.ir/rss/tp/6",
    "https://www.mehrnews.com/rss/tp/7",
    "https://www.mehrnews.com/rss/tp/25",
    "https://www.mehrnews.com/rss/tp/6",
]

# --- مسیرها ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "bot_state.json")
DB_FILE = os.path.join(BASE_DIR, "news_bot.db")
NEWS_FOLDER = os.path.join(BASE_DIR, "news_archive")
SENT_NEWS_FILE = os.path.join(BASE_DIR, "sent_news.json")
BLACKLIST_FILE = os.path.join(BASE_DIR, "blacklist.txt")

# --- ذخیره‌سازی ---
SENT_NEWS_SAVE_DEBOUNCE_SEC = 5

# --- صف و بازنشانی ---
RSS_CHECK_INTERVAL_SEC = 300
MAX_RETRIES = 3
