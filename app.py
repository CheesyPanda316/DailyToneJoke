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

# 💡 未來日期排程（您可以在此自由增加、修改日期，重啟也不會影響當天分數）
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
    "2026-11-11": "23144231123",   
    "2026-11-12": "323144231123",   
    "2026-11-13": "4323144231123",   
    "2026-11-14": "24323144231123",   
    "2026-11-15": "424323144231123",   
    "2026-11-16": "3424323144231123",   
    "2026-11-17": "13424323144231123",   
    "2026-11-18": "213424323144231123",   
    "2026-11-19": "1213424323144231123",   
    "2026-11-20": "41213424323144231123",   
}

# 💾 安全自動適應路徑 (改為專案目錄底下的 data 資料夾)
if os.environ.get("RENDER"):
    # 在 Render 環境中，將資料夾建在當前專案目錄底下
    DATA_DIR = os.path.join(os.getcwd(), "data")
    DB_FILE = os.path.join(DATA_DIR, "discord_stats.json")
    os.makedirs(DATA_DIR, exist_ok=True)
else:
    # 本地測試時直接放在同級目錄
    DB_FILE = "discord_stats.json"

def load_all_data():
    """從永久檔案讀取所有頻道的數據"""
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 讀取資料庫檔案失敗: {e}", flush=True)
        return {}

def save_all_data(data):
    """將所有數據寫入永久檔案"""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"❌ 寫入資料庫檔案失敗: {e}", flush=True)

# ─── 機器人本體設定 ───
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

# ─── 自動跨日結算任務 ───
@tasks.loop(time=time(hour=0, minute=0, tzinfo=TAIPEI_TZ))
async def midnight_scheduler():
    now = datetime.now(TAIPEI_TZ)
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today_str = now.strftime("%Y-%m-%d")
    
    db_data = load_all_data()
    
    for channel_id_str, stats in list(db_data.items()):
        channel = bot.get_channel(int(channel_id_str))
        if not channel:
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
            
            # 跨日重設該頻道的計數數據
            db_data[channel_id_str] = {}
            
            if today_str in MY_SCHEDULED_TONES:
                target_tone = MY_SCHEDULED_TONES[today_str]
                embed_start = discord.Embed(
                    title="🚨 全新一日！今日指定聲調造句挑戰開始！",
                    description=f"全新的一天開始了！今天的目標聲調密碼是：\n\n➡️ **【 {target_tone} 】**\n\n昨日分數已全面歸零，大家快來搶下今天的第一分吧！",
                    color=0x27ae60
                )
                await channel.send(embed=embed_start)
        except Exception as e:
            print(f"❌ 頻道 [{channel_id_str}] 跨日自動結算發生錯誤: {e}", flush=True)
            
    save_all_data(db_data)

# ─── 斜線指令 ───
@bot.tree.command(name="listen", description="在此文字頻道開啟每日聲調笑笑偵測功能")
async def start_listening(interaction: discord.Interaction):
    channel_id_str = str(interaction.channel_id)
    db_data = load_all_data()
    
    if channel_id_str in db_data:
        await interaction.response.send_message("ℹ️ 此頻道已經在偵測名單中，無需重複開啟！", ephemeral=True)
        return
        
    db_data[channel_id_str] = {}
    save_all_data(db_data)
    await interaction.response.send_message("✅ 成功導入頻道！機器人已在此頻道建立獨立本地資料庫！")

@bot.tree.command(name="unlisten", description="停止此文字頻道的聲調偵測功能並清除數據")
async def stop_listening(interaction: discord.Interaction):
    channel_id_str = str(interaction.channel_id)
    db_data = load_all_data()
    
    if channel_id_str in db_data:
        del db_data[channel_id_str]
        save_all_data(db_data)
        await interaction.response.send_message("🗑️ 機器人已取消此頻道的偵測並從本地資料庫卸載數據！")
    else:
        await interaction.response.send_message("❌ 錯誤：此頻道原本就沒有啟用聲調偵測功能。", ephemeral=True)

@bot.tree.command(name="check", description="檢查中文字在機器人眼中的聲調密碼")
@discord.app_commands.describe(text="想要查詢聲調的中文字或句子")
async def check_tone(interaction: discord.Interaction, text: str):
    tone = convert_chinese_to_tone_code(text)
    await interaction.response.send_message(f"🔍 「{text}」在機器人眼中的聲調密碼是：**【 {tone} 】**")

@bot.tree.command(name="leaderboard", description="查看本頻道今日即時挑戰排行榜")
async def leaderboard(interaction: discord.Interaction):
    channel_id_str = str(interaction.channel_id)
    db_data = load_all_data()
    
    if channel_id_str not in db_data:
        await interaction.response.send_message("❌ 此頻道尚未啟用聲調偵測功能，請先輸入 `/listen` 啟用。", ephemeral=True)
        return
        
    stats = db_data[channel_id_str]
    if not stats:
        await interaction.response.send_message("📊 今天新一輪的挑戰還沒有人上榜喔！快來搶頭香！")
        return
    
    sorted_stats = sorted(stats.items(), key=lambda x: x[1]["correct"], reverse=True)
    leaderboard_text = f"🏆 **【 #{interaction.channel.name} 今日即時挑戰排行榜 】** 🏆\n"
    leaderboard_text += "（每天 00:00 將會自動結算並重設歸零）\n"
    leaderboard_text += "───────────────────\n"
    for index, (user_id, info) in enumerate(sorted_stats[:10], start=1):
        leaderboard_text += f"第 {index} 名 ｜ {info['name']} ── 💥 今日已觸發 **{info['correct']}** 次！\n"
    await interaction.response.send_message(leaderboard_text)

# ─── 訊息監聽 ───
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
            
        channel_id_str = str(message.channel.id)
        db_data = load_all_data()
        
        if channel_id_str not in db_data:
            return  
            
        today_str = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d")
        if today_str not in MY_SCHEDULED_TONES:
            return
            
        target_tone = MY_SCHEDULED_TONES[today_str]
        user_tone = convert_chinese_to_tone_code(user_sentence)
        
        if len(user_tone) != len(target_tone) or len(user_tone) == 0:
            return
            
        if user_tone == target_tone:
            stats = db_data[channel_id_str]
            user_id = str(message.author.id)
            
            if user_id not in stats:
                stats[user_id] = {"name": message.author.name, "correct": 0}
            stats[user_id]["correct"] += 1
            
            db_data[channel_id_str] = stats
            save_all_data(db_data)
            
            times = stats[user_id]["correct"]
            await message.channel.send(f"🎉 {message.author.mention} 成功觸發！你今天在此頻道已經講了 {times} 次每日聲調笑話。")
    except Exception as e:
        print(f"❌ 訊息監聽攔截錯誤: {e}", flush=True)

# ─── 啟動設定 ───
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
