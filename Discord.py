#!/usr/bin/env python3
import os
import discord
import asyncio
import aiohttp
import re
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

# Инициализация API клиентов
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.getenv('SPOTIPY_CLIENT_ID'),
    client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'))
)

youtube = build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))

music_queue = []
now_playing = None

# Конфигурация yt-dlp
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -sn',
}

class Track:
    def __init__(self, url, title, duration, source):
        self.url = url
        self.title = title
        self.duration = duration
        self.source = source

async def get_youtube_track(query: str) -> Track:
    try:
        request = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=1
        )
        response = request.execute()
        
        if not response['items']:
            return None
            
        video_id = response['items'][0]['id']['videoId']
        title = response['items'][0]['snippet']['title']
        
        with YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"https://youtu.be/{video_id}", download=False)
            return Track(info['url'], title, info['duration'], 'YouTube')
            
    except Exception as e:
        print(f"YouTube API Error: {e}")
        return None

async def get_spotify_track(url: str) -> Track:
    try:
        if 'track' in url:
            track = sp.track(url)
            query = f"{track['name']} {track['artists'][0]['name']}"
            return await get_youtube_track(query)
            
        elif 'playlist' in url:
            results = sp.playlist_items(url)
            tracks = []
            for item in results['items']:
                track = item['track']
                query = f"{track['name']} {track['artists'][0]['name']}"
                tracks.append(await get_youtube_track(query))
            return tracks
            
    except Exception as e:
        print(f"Spotify Error: {e}")
        return None

async def get_soundcloud_track(url: str) -> Track:
    try:
        with YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            return Track(info['url'], info['title'], info['duration'], 'SoundCloud')
    except Exception as e:
        print(f"SoundCloud Error: {e}")
        return None

async def process_query(query: str) -> Track:
    # Определение источника
    if 'youtube.com' in query or 'youtu.be' in query':
        return await get_youtube_track(query)
    elif 'spotify.com' in query:
        return await get_spotify_track(query)
    elif 'soundcloud.com' in query:
        return await get_soundcloud_track(query)
    else:
        return await get_youtube_track(query)

@bot.event
async def on_ready():
    print(f'Бот {bot.user.name} готов к работе!')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="музыку | !help"
    ))

@bot.command()
async def play(ctx, *, query: str):
    global music_queue
    
    voice_client = ctx.guild.voice_client
    if not voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
            voice_client = ctx.guild.voice_client
        else:
            return await ctx.send("Сначала подключитесь к голосовому каналу!")
    
    track = await process_query(query)
    if not track:
        return await ctx.send("Не удалось найти трек!")
    
    music_queue.append(track)
    
    if not voice_client.is_playing():
        await play_next(ctx)
    else:
        await ctx.send(f"Добавлено в очередь: **{track.title}**")

async def play_next(ctx):
    global music_queue, now_playing
    
    if not music_queue:
        return
    
    voice_client = ctx.guild.voice_client
    if voice_client:
        track = music_queue.pop(0)
        now_playing = track
        
        voice_client.play(
            discord.FFmpegPCMAudio(track.url, **FFMPEG_OPTIONS),
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
        )
        
        await ctx.send(f"Сейчас играет: **{track.title}** ({track.source})")

@bot.command()
async def skip(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("Трек пропущен!")
    else:
        await ctx.send("Нет активного воспроизведения!")

@bot.command()
async def stop(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client:
        await voice_client.disconnect()
        music_queue.clear()
        await ctx.send("Воспроизведение остановлено!")
    else:
        await ctx.send("Бот не подключен к голосовому каналу!")

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))
