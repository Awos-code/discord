#!/usr/bin/env python3
import os
import discord
from discord.ext import commands
from yt_dlp import YoutubeDL
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Конфигурация Spotify
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.getenv('SPOTIPY_CLIENT_ID'),
    client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'))
)

# Глобальные переменные
music_queue = []
now_playing = None
paused = False


# Класс для кнопок управления
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


# Конфигурация yt-dlp
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'noplaylist': True,
}


@bot.event
async def on_ready():
    print(f'Бот {bot.user.name} готов к работе!')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="музыку | !help"
    ))


async def play_next(ctx):
    global now_playing, paused
    if music_queue:
        now_playing = music_queue.pop(0)
        source, info = now_playing

        ctx.voice_client.play(source, after=lambda e: bot.loop.create_task(play_next(ctx)))

        # Создаем Embed с информацией
        embed = discord.Embed(
            title="🎶 Сейчас играет",
            description=f"[{info['title']}]({info['webpage_url']})",
            color=0x00ff00
        )
        embed.set_thumbnail(url=info['thumbnail'])
        embed.add_field(name="Длительность", value=info['duration_string'], inline=True)
        embed.add_field(name="Запросил", value=ctx.author.mention, inline=True)

        # Отправляем сообщение с кнопками
        view = PlayerControls()
        await ctx.send(embed=embed, view=view)
    else:
        now_playing = None


@bot.command()
async def play(ctx, *, query: str):
    """Воспроизвести трек"""
    global paused

    # Проверка голосового канала
    if not ctx.author.voice:
        return await ctx.send("❌ Вы не в голосовом канале!")

    voice_channel = ctx.author.voice.channel

    # Подключение к каналу
    if not ctx.voice_client:
        await voice_channel.connect()
    else:
        await ctx.voice_client.move_to(voice_channel)

    # Обработка Spotify
    if 'open.spotify.com' in query:
        try:
            track_info = sp.track(query)
            query = f"{track_info['name']} {track_info['artists'][0]['name']}"
        except Exception as e:
            return await ctx.send(f"❌ Ошибка Spotify: {e}")

    # Поиск на YouTube
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
        except Exception as e:
            return await ctx.send(f"❌ Ошибка поиска: {e}")

        url = info['url']
        source = discord.FFmpegPCMAudio(
            url,
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        )

    music_queue.append((source, info))

    if not ctx.voice_client.is_playing() and not paused:
        await play_next(ctx)


@bot.command()
async def pause(ctx):
    """Приостановить воспроизведение"""
    voice_client = ctx.voice_client
    if voice_client.is_playing():
        voice_client.pause()
        await ctx.send("⏸ Воспроизведение приостановлено")


@bot.command()
async def resume(ctx):
    """Возобновить воспроизведение"""
    voice_client = ctx.voice_client
    if voice_client.is_paused():
        voice_client.resume()
        await ctx.send("▶ Воспроизведение возобновлено")


bot.run(os.getenv('DISCORD_TOKEN'))
