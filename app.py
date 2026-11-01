import json
import os
import re
import asyncio
from datetime import datetime, timedelta, time, timezone
import discord
from discord.ext import commands, tasks
from pypinyin import pinyin, Style
from flask import Flask
import threading

# 設定台灣台北時區 (GMT+8)
TAIPEI_TZ = timezone(timedelta(hours=8))

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

TOKEN = os.environ.get("DISCORD_TOKEN")  

# 💡 未來日期排程（配合 2026 年時間）
MY_SCHEDULED_TONES = {
    "2026-11-01": "3",    
    "2026-11-02": "23",   
    "2026-11-03": "123",   
    "2026-11-04": "1123",   
    "2026-11-05": "31123",   
    "2026-11-06": "231123",   
    "2026-11-07": "4231123",   
    "2026-11-08": "44231123",   
    "2026-11-09": "144231123",   
    "2026-11-10": "3144231123",   
}

intents = discord.Intents.default()
intents.message_content = True  
intents.members = True  
bot = commands.Bot(command_prefix=[], intents=intents)

def convert_chinese_to_tone_code(text):
    clean_text = "".join(re.findall(r"[\u4e00-\u9fa5]", text))
    pinyin_list = pinyin(clean_text, style=Style.TONE3, neutral_tone_with_five=True, heteronym=False)
    
    tone_code = ""
    for item in pinyin_list:
        raw_pinyin = str(item).strip()
        match = re.search(r"\d", raw_pinyin)
        tone_code += match.group() if match else "5"
    return tone_code

async def load_stats_from_channel(channel):
    # 強化：如果完全沒有啟用過（無 topic），返回 None
    if not channel or not hasattr(channel, 'topic') or not channel.topic:
        return None
    
    # 檢查是否含有特定資料庫結構標記
    if "DATA_START" not in channel.topic:
        return None
        
    match = re.search(r"DATA_START({.*})DATA_END", channel.topic)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    return {} # 若有標記但解析失敗，回傳空字典確保不崩潰

async def save_stats_to_channel(channel, data):
    if not channel or not hasattr(channel, 'edit'):
        return
    
    clean_topic = ""
    if channel.topic:
        clean_topic = re.sub(r"\n?DATA_START.*DATA_END", "", channel.topic).strip()
        
    if data is None:
        new_topic = clean_topic
    else:
        json_str = json.dumps(data, ensure_ascii=False)
        separator = "\n" if clean_topic else ""
        new_topic = f"{clean_topic}{separator}DATA_START{json_str}DATA_END"
    try:
        await channel.edit(topic=new_topic)
    except Exception as e:
        print(f"❌ 寫入頻道 [{channel.name}] 簡介失敗: {e}", flush=True)

@tasks.loop(time=time(hour=0, minute=0, tzinfo=TAIPEI_TZ))
async def midnight_scheduler():
    now = datetime.now(TAIPEI_TZ)
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today_str = now.strftime("%Y-%m-%d")
    
    for guild in bot.guilds:
        for channel in guild.text_channels:
            stats = await load_stats_from_channel(channel)
            if stats is None:
                continue  
            try:
                embed_end = discord.Embed(
                    title=f"🏆 【{yesterday_str}】今日聲調造句挑戰 ｜ 最終榮譽榜 🏆",
                    description="昨天的挑戰已經結束！以下是最終勝出的前 10 名大師：\n───────────────────",
                    color=0xf1c40f
                )
                if stats:
                    sorted_stats = sorted(stats.items(), key=lambda x: x[1]["correct"], reverse=True)
                    leaderboard_text = ""
                    for index, (user_id, info) in enumerate(sorted_stats[:10], start=1):
                        leaderboard_text += f"🥇 第 {index} 名 ｜ {info['name']} ── 💥 成功觸發 **{info['correct']}** 次！\n"
                    embed_end.description += f"\n{leaderboard_text}"
                else:
                    embed_end.description += "\n😭 昨天竟然沒有人挑戰成功，大家都太害羞了！"
                
                await channel.send(embed=embed_end)
                await save_stats_to_channel(channel, {})
                
                if today_str in MY_SCHEDULED_TONES:
                    target_tone = MY_SCHEDULED_TONES[today_str]
                    embed_start = discord.Embed(
                        title="🚨 全新一日！今日指定聲調造句挑戰開始！",
                        description=f"全新的一天開始了！今天的目標聲調密碼是：\n\n➡️ **【 {target_tone} 】**\n\n昨日分數已全面歸零，大家快來搶下今天的第一分吧！",
                        color=0x27ae60
                    )
                    await channel.send(embed=embed_start)
            except Exception as e:
                print(f"❌ 跨日自動結算發生錯誤: {e}", flush=True)

@bot.tree.command(name="listen", description="在此文字頻道開啟每日聲調笑笑偵測功能")
async def start_listening(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        channel = bot.get_channel(interaction.channel_id) or await bot.fetch_channel(interaction.channel_id)
        
    if isinstance(channel, discord.TextChannel):
        await interaction.followup.send("✅ 成功導入頻道！機器人正在此頻道建立獨立資料庫（若簡介更新較慢是受 Discord 官方限速影響，請稍候）！")
        await save_stats_to_channel(channel, {})
    else:
        await interaction.followup.send("❌ 錯誤：此功能只能在伺服器的「文字頻道」中使用！")

@bot.tree.command(name="unlisten", description="停止此文字頻道的聲調偵測功能並清除數據")
async def stop_listening(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        channel = bot.get_channel(interaction.channel_id) or await bot.fetch_channel(interaction.channel_id)
        
    if isinstance(channel, discord.TextChannel):
        await interaction.followup.send("🗑️ 機器人已取消此頻道的偵測並正在卸載簡介數據！")
        await save_stats_to_channel(channel, None)
    else:
        await interaction.followup.send("❌ 錯誤：此功能只能在伺服器的「文字頻道」中使用！")

@bot.tree.command(name="check", description="檢查中文字在機器人眼中的聲調密碼")
@discord.app_commands.describe(text="想要查詢聲調的中文字或句子")
async def check_tone(interaction: discord.Interaction, text: str):
    tone = convert_chinese_to_tone_code(text)
    await interaction.response.send_message(f"🔍 「{text}」在機器人眼中的聲調密碼是：**【 {tone} 】**")

@bot.tree.command(name="leaderboard", description="查看本頻道今日即時挑戰排行榜")
async def leaderboard(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        channel = bot.get_channel(interaction.channel_id) or await bot.fetch_channel(interaction.channel_id)
        
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ 錯誤：此功能只能在伺服器的「文字頻道」中使用！")
        return

    stats = await load_stats_from_channel(channel)
    if stats is None:
        await interaction.response.send_message("❌ 此頻道尚未啟用聲調偵測功能，請先輸入 `/listen` 啟用。")
        return
    if not stats:
        await interaction.response.send_message("📊 今天新一輪的挑戰還沒有人上榜喔！快來搶頭香！")
        return
    
    sorted_stats = sorted(stats.items(), key=lambda x: x[1]["correct"], reverse=True)
    leaderboard_text = f"🏆 **【 #{channel.name} 今日即時挑戰排行榜 】** 🏆\n"
    leaderboard_text += "（每天 00:00 將會自動結算並重設歸零）\n"
    leaderboard_text += "───────────────────\n"
    for index, (user_id, info) in enumerate(sorted_stats[:10], start=1):
        leaderboard_text += f"第 {index} 名 ｜ {info['name']} ── 💥 今日已觸發 **{info['correct']}** 次！\n"
    await interaction.response.send_message(leaderboard_text)

@bot.event
async def on_message(message):
    try:
        if message.author.bot:
            return
        if message.interaction_metadata is not None:
            return

        user_sentence = message.content.strip()
        if user_sentence.startswith("/"):
            return
            
        stats = await load_stats_from_channel(message.channel)
        # 💡 核心修正：如果 stats 為 None 代表頻道未啟用，直接忽略
        if stats is None:
            return  
            
        today_str = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d")
        if today_str not in MY_SCHEDULED_TONES:
            return
            
        target_tone = MY_SCHEDULED_TONES[today_str]
        user_tone = convert_chinese_to_tone_code(user_sentence)
        
        if len(user_tone) != len(target_tone) or len(user_tone) == 0:
            return
            
        if user_tone == target_tone:
            user_id = str(message.author.id)
            if user_id not in stats:
                stats[user_id] = {"name": message.author.name, "correct": 0}
            stats[user_id]["correct"] += 1
            
            await save_stats_to_channel(message.channel, stats)
            
            times = stats[user_id]["correct"]
            await message.channel.send(f"🎉 {message.author.mention} 成功觸發！你今天在此頻道已經講了 {times} 次每日聲調笑話。")
    except Exception as e:
        print(f"❌ 訊息監聽攔截錯誤: {e}", flush=True)

@bot.event
async def setup_hook():
    print("🌐 Discord 已就緒，正在非阻塞啟動背景保活 Flask 網頁伺服器...", flush=True)
    threading.Thread(target=run_dummy_server, daemon=True).start()
    try:
        await bot.tree.sync()
        print("✨ 斜線指令全自動同步成功！", flush=True)
    except Exception as e:
        print(f"❌ 同步斜線指令失敗: {e}", flush=True)

@bot.event
async def on_ready():
    print(f"🤖 機器人 {bot.user.name} 已成功連線至 Discord 網關並正常上線！", flush=True)
    if not midnight_scheduler.is_running():
        midnight_scheduler.start()

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
