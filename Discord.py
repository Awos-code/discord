#!/usr/bin/env python3
import os
import discord
from discord.ext import commands
from yt_dlp import YoutubeDL
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from googleapiclient.discovery import build
import asyncio

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
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

# Конфигурация yt-dlp
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'noplaylist': True,
    'cookiefile': 'cookies.txt',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'force-ipv4': True,
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
}

class PlayerControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(emoji="⏯", style=discord.ButtonStyle.grey)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        global paused
        voice_client = interaction.guild.voice_client

        if voice_client.is_playing():
            voice_client.pause()
            paused = True
            button.emoji = "▶"
        elif voice_client.is_paused():
            voice_client.resume()
            paused = False
            button.emoji = "⏯"

        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.grey)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            await interaction.response.defer()

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if voice_client:
            await voice_client.disconnect()
            music_queue.clear()
            await interaction.response.send_message("⏹ Воспроизведение остановлено")
            self.stop()

async def search_youtube(query: str):
    try:
        search_response = youtube.search().list(
            q=query,
            part='id,snippet',
            maxResults=1,
            type='video'
        ).execute()
        
        if not search_response.get('items'):
            return None
        
        video_id = search_response['items'][0]['id']['videoId']
        return f"https://youtu.be/{video_id}"
    except Exception as e:
        print(f"YouTube API Error: {e}")
        return None

async def get_audio_info(url: str):
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            return info
    except Exception as e:
        print(f"YT-DLP Error: {e}")
        return None

async def play_next(ctx):
    global now_playing, paused
    if music_queue:
        now_playing = music_queue.pop(0)
        source, info = now_playing

        ctx.voice_client.play(source, after=lambda e: bot.loop.create_task(play_next(ctx)))

        embed = discord.Embed(
            title="🎶 Сейчас играет",
            description=f"[{info['title']}]({info['webpage_url']})",
            color=0x00ff00
        )
        embed.set_thumbnail(url=info['thumbnail'])
        embed.add_field(name="Длительность", value=info.get('duration_string', 'N/A'), inline=True)
        embed.add_field(name="Запросил", value=ctx.author.mention, inline=True)

        view = PlayerControls()
        await ctx.send(embed=embed, view=view)
    else:
        now_playing = None
        await ctx.send("🎵 Очередь воспроизведения пуста")

@bot.event
async def on_ready():
    print(f'Бот {bot.user.name} готов к работе!')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="музыку | !help"
    ))

@bot.command()
async def play(ctx, *, query: str):
    global paused
    
    if not ctx.author.voice:
        return await ctx.send("❌ Вы не в голосовом канале!")
    
    voice_channel = ctx.author.voice.channel

    try:
        if not ctx.voice_client:
            await voice_channel.connect()
        else:
            await ctx.voice_client.move_to(voice_channel)
    except Exception as e:
        return await ctx.send(f"❌ Ошибка подключения: {str(e)}")

    original_query = query
    is_spotify = 'open.spotify.com' in query
    
    try:
        if is_spotify:
            track_info = sp.track(query)
            query = f"{track_info['name']} {track_info['artists'][0]['name']}"
        
        youtube_url = await search_youtube(query)
        if not youtube_url:
            return await ctx.send("❌ Трек не найден")
        
        info = await get_audio_info(youtube_url)
        if not info:
            return await ctx.send("❌ Не удалось получить аудио поток")
        
        source = discord.FFmpegPCMAudio(
            info['url'],
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn -loglevel error"
        )

        music_queue.append((source, info))
        
        if not ctx.voice_client.is_playing() and not paused:
            await play_next(ctx)
        else:
            await ctx.send(f"🎵 Добавлено в очередь: {info['title']}")
            
    except Exception as e:
        await ctx.send(f"⚠️ Ошибка: {str(e)}")
        print(f"Play Command Error: {str(e)}")

@bot.command()
async def pause(ctx):
    voice_client = ctx.voice_client
    if voice_client.is_playing():
        voice_client.pause()
        await ctx.send("⏸ Воспроизведение приостановлено")

@bot.command()
async def resume(ctx):
    voice_client = ctx.voice_client
    if voice_client.is_paused():
        voice_client.resume()
        await ctx.send("▶ Воспроизведение возобновлено")

@bot.command()
async def queue(ctx):
    if not music_queue:
        return await ctx.send("🎵 Очередь воспроизведения пуста")
    
    embed = discord.Embed(title="🎵 Очередь воспроизведения", color=0x7289DA)
    for index, (_, info) in enumerate(music_queue[:10], 1):
        embed.add_field(
            name=f"{index}. {info['title'][:50]}",
            value=f"Длительность: {info.get('duration_string', 'N/A')}",
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command()
async def skip(ctx):
    voice_client = ctx.voice_client
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
        await ctx.send("⏭ Трек пропущен")

@bot.command()
async def stop(ctx):
    voice_client = ctx.voice_client
    if voice_client:
        await voice_client.disconnect()
        music_queue.clear()
        await ctx.send("⏹ Воспроизведение остановлено")

bot.run(os.getenv('DISCORD_TOKEN'))
