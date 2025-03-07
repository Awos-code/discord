#!/usr/bin/env python3
import os
import discord
import random
import asyncio
import aiohttp
import json
from datetime import datetime
from discord.ext import commands
from yt_dlp import YoutubeDL
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from googleapiclient.discovery import build
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Инициализация API клиентов
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.getenv('SPOTIPY_CLIENT_ID'),
    client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'))
)

youtube = build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))

# Глобальные переменные
music_queue = []
now_playing = None
paused = False
REQUEST_DELAY = (1.2, 2.8)
COOKIES_FILE = 'cookies.txt'

# Конфигурация Invidious
INVIDIOUS_INSTANCES = [
    'https://vid.puffyan.us',
    'https://inv.riverside.rocks',
    'https://yt.artemislena.eu'
]

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36'
]

def get_ydl_config():
    return {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': 192,
        }],
        'cookiefile': COOKIES_FILE,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'quiet': True,
        'no_warnings': True,
        'source_address': '0.0.0.0',
        'http_headers': {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.youtube.com/'
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android_embedded'],
                'skip': ['hls', 'dash']
            }
        },
        'overrides': {
            'retries': 15,
            'fragment_retries': 15
        }
    }

class PlayerControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(emoji="⏯", style=discord.ButtonStyle.grey)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ... (реализация кнопок как в предыдущих версиях) ...

async def update_cookies():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get("https://www.youtube.com")
        await asyncio.sleep(random.uniform(2.5, 4.5))
        
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f)
        
        print(f"[{datetime.now()}] Cookies успешно обновлены")
    except Exception as e:
        print(f"Ошибка обновления cookies: {str(e)}")
    finally:
        driver.quit()

async def search_youtube(query: str):
    try:
        await asyncio.sleep(random.uniform(*REQUEST_DELAY))
        search_response = youtube.search().list(
            q=query,
            part='id,snippet',
            maxResults=1,
            type='video'
        ).execute()
        
        return f"https://youtu.be/{search_response['items'][0]['id']['videoId']}"
    except Exception as e:
        print(f"Ошибка YouTube API: {str(e)}")
        return await search_invidious(query)

async def search_invidious(query: str):
    instance = random.choice(INVIDIOUS_INSTANCES)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{instance}/api/v1/search",
                params={'q': query},
                headers={'User-Agent': random.choice(USER_AGENTS)},
                timeout=7
            ) as resp:
                results = await resp.json()
                return f"{instance}/watch?v={results[0]['videoId']}"
    except Exception as e:
        print(f"Ошибка Invidious: {str(e)}")
        return None

async def get_audio_info(url: str):
    try:
        with YoutubeDL(get_ydl_config()) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('entries')[0] if 'entries' in info else info
    except Exception as e:
        print(f"Ошибка yt-dlp: {str(e)}")
        return None

@bot.event
async def on_ready():
    if not os.path.exists(COOKIES_FILE):
        await update_cookies()
    
    bot.loop.create_task(cron_job())
    print(f'Бот {bot.user.name} готов к работе!')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="музыку | !help"
    ))

async def cron_job():
    while True:
        await update_cookies()
        await asyncio.sleep(6 * 3600)  # Обновление каждые 6 часов

@bot.command()
@commands.cooldown(3, 60, commands.BucketType.user)
async def play(ctx, *, query: str):
    # ... (реализация команды play с обработкой Spotify и очередью) ...

@bot.command()
async def update(ctx):
    """Принудительное обновление cookies"""
    await update_cookies()
    await ctx.send("🍪 Cookies успешно обновлены!")

# ... остальные команды (pause, resume, queue, skip, stop) ...

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))
