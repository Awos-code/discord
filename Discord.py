#!/usr/bin/env python3
import os
import discord
import random
import asyncio
import aiohttp
from discord.ext import commands
from yt_dlp import YoutubeDL
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Конфигурация API
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.getenv('SPOTIPY_CLIENT_ID'),
    client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'))
)

youtube = build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))

# Глобальные настройки
music_queue = []
now_playing = None
paused = False
REQUEST_DELAY = (0.8, 1.8)  # Случайные задержки между запросами

# Прокси и User-Agents
PROXIES = [
    os.getenv('PROXY_1'),
    os.getenv('PROXY_2')
]

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.5672.131 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1'
]

# Invidious резервные инстансы
INVIDIOUS_INSTANCES = [
    'https://vid.puffyan.us',
    'https://inv.riverside.rocks',
    'https://yt.artemislena.eu'
]

# Конфигурация yt-dlp с ротацией параметров
def get_ydl_config():
    return {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': 192,
        }],
        'noplaylist': True,
        'cookiefile': 'cookies.txt',
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'quiet': True,
        'no_warnings': True,
        'source_address': '0.0.0.0',
        'proxy': random.choice(PROXIES) if PROXIES else None,
        'http_headers': {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.youtube.com/'
        },
        'overrides': {
            'retries': 10,
            'fragment_retries': 10,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_embedded'],
                    'skip': ['hls', 'dash']
                }
            }
        }
    }

class PlayerControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(emoji="⏯", style=discord.ButtonStyle.grey)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ... (как в предыдущей версии) ...

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
        print(f"YouTube API Error: {e}")
        return await search_invidious(query)

async def search_invidious(query: str):
    instance = random.choice(INVIDIOUS_INSTANCES)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{instance}/api/v1/search",
                params={'q': query},
                headers={'User-Agent': random.choice(USER_AGENTS)},
                timeout=5
            ) as resp:
                results = await resp.json()
                return f"{instance}/watch?v={results[0]['videoId']"
    except Exception as e:
        print(f"Invidious Error: {e}")
        return None

async def get_audio_info(url: str):
    try:
        with YoutubeDL(get_ydl_config()) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            return info.get('entries')[0] if 'entries' in info else info
    except Exception as e:
        print(f"YT-DLP Error: {e}")
        return None

@bot.command()
@commands.cooldown(3, 60, commands.BucketType.user)
async def play(ctx, *, query: str):
    """Добавить трек в очередь"""
    # ... (проверка голосового канала) ...
    
    try:
        # Обработка Spotify
        if 'open.spotify.com' in query:
            track = sp.track(query)
            query = f"{track['name']} {track['artists'][0]['name']}"

        # Поиск YouTube
        await ctx.trigger_typing()
        youtube_url = await search_youtube(query)
        
        if not youtube_url:
            return await ctx.send("❌ Трек не найден")

        # Получение аудио
        info = await get_audio_info(youtube_url)
        if not info or not info.get('url'):
            return await ctx.send("❌ Ошибка получения аудио")

        source = discord.FFmpegPCMAudio(
            info['url'],
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn -loglevel error"
        )

        # Добавление в очередь
        music_queue.append((source, info))
        
        # ... (воспроизведение или уведомление о добавлении в очередь) ...

    except Exception as e:
        await ctx.send(f"⚠️ Ошибка: {str(e)}")

# ... остальные команды ...

bot.run(os.getenv('DISCORD_TOKEN'))
