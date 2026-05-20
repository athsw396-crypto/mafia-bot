import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

TOKEN = os.environ.get("BOT_TOKEN", "ضع_التوكن_هنا")

# ========================
# حالة اللعبة
# ========================
games = {}  # chat_id -> game state

ROLES = {
    "مافيا": "🔫",
    "مواطن": "👤",
    "دكتور": "💊",
    "محقق": "🔍"
}

def new_game():
    return {
        "players": {},       # user_id -> {name, role, alive}
        "phase": "joining",  # joining, night, day, voting
        "day": 0,
        "votes": {},
        "healed": None,
        "investigated": None,
        "mafia_target": None,
        "message_id": None,
    }

def assign_roles(players):
    ids = list(players.keys())
    random.shuffle(ids)
    n = len(ids)

    roles = ["مواطن"] * n
    roles[0] = "مافيا"
    if n >= 5:
        roles[1] = "مافيا"
    if n >= 4:
        roles[-1] = "دكتور"
    if n >= 6:
        roles[-2] = "محقق"

    random.shuffle(roles)
    for i, uid in enumerate(ids):
        players[uid]["role"] = roles[i]
    return players

def get_alive(game):
    return {uid: p for uid, p in game["players"].items() if p["alive"]}

def check_winner(game):
    alive = get_alive(game)
    mafia = [p for p in alive.values() if p["role"] == "مافيا"]
    citizens = [p for p in alive.values() if p["role"] != "مافيا"]
    if not mafia:
        return "مواطنون"
    if len(mafia) >= len(citizens):
        return "مافيا"
    return None

# ========================
# الأوامر
# ========================

async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        await update.message.reply_text("أضفني لمجموعة واستخدم /newgame هناك! 🎮")
        return

    games[chat_id] = new_game()
    keyboard = [[InlineKeyboardButton("✋ انضم للعبة", callback_data="join")]]
    msg = await update.message.reply_text(
        "🎭 *لعبة المافيا*\n\nاضغط انضم للمشاركة!\n\nالحد الأدنى: 4 لاعبين\n\nعندما يكتمل اللاعبون، اكتب /begin",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    games[chat_id]["message_id"] = msg.message_id

async def newgame_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, ctx)

async def join_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user = query.from_user

    if chat_id not in games or games[chat_id]["phase"] != "joining":
        await query.answer("اللعبة مو في مرحلة التسجيل!", show_alert=True)
        return

    game = games[chat_id]
    uid = user.id

    if uid in game["players"]:
        await query.answer("أنت مسجل بالفعل! ✅", show_alert=True)
        return

    game["players"][uid] = {
        "name": user.first_name,
        "role": None,
        "alive": True
    }

    names = [p["name"] for p in game["players"].values()]
    keyboard = [[InlineKeyboardButton("✋ انضم للعبة", callback_data="join")]]
    await query.edit_message_text(
        f"🎭 *لعبة المافيا*\n\n👥 اللاعبون ({len(names)}):\n" +
        "\n".join(f"• {n}" for n in names) +
        "\n\nاكتب /begin لبدء اللعبة (4 لاعبين على الأقل)",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def begin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        await update.message.reply_text("ما في لعبة! اكتب /newgame")
        return

    game = games[chat_id]
    if game["phase"] != "joining":
        await update.message.reply_text("اللعبة بدأت بالفعل!")
        return

    if len(game["players"]) < 4:
        await update.message.reply_text("تحتاج 4 لاعبين على الأقل! 😅")
        return

    game["players"] = assign_roles(game["players"])

    # أرسل لكل لاعب دوره
    for uid, player in game["players"].items():
        role = player["role"]
        emoji = ROLES.get(role, "❓")
        try:
            mafia_members = ""
            if role == "مافيا":
                mafia = [p["name"] for p in game["players"].values() if p["role"] == "مافيا"]
                mafia_members = f"\n\n🔫 زملاؤك في المافيا: {', '.join(mafia)}"
            await ctx.bot.send_message(
                uid,
                f"🎭 دورك في اللعبة:\n\n{emoji} *{role}*{mafia_members}\n\n{'أنت من المافيا، اقتل المواطنين ليلاً!' if role == 'مافيا' else 'أنت مواطن شريف، اكشف المافيا!' if role == 'مواطن' else 'أنت الدكتور، اشفِ لاعباً كل ليلة!' if role == 'دكتور' else 'أنت المحقق، تحقق من هوية لاعب كل ليلة!'}",
                parse_mode="Markdown"
            )
        except Exception:
            pass  # اللاعب لم يبدأ المحادثة مع البوت

    game["phase"] = "night"
    game["day"] = 1
    await update.message.reply_text(
        f"🌙 *الليلة {game['day']}*\n\nبدأت اللعبة! تم إرسال الأدوار للجميع.\n\nالمافيا والدكتور والمحقق، راجعوا رسائلكم الخاصة!",
        parse_mode="Markdown"
    )
    await asyncio.sleep(2)
    await send_night_actions(chat_id, ctx)

async def send_night_actions(chat_id, ctx):
    game = games[chat_id]
    alive = get_alive(game)

    for uid, player in game["players"].items():
        if not player["alive"]:
            continue
        role = player["role"]
        targets = [p for pid, p in alive.items() if pid != uid]

        if role == "مافيا":
            keyboard = [[InlineKeyboardButton(f"🎯 {p['name']}", callback_data=f"mafia_{tid}")] 
                       for tid, p in alive.items() if p["role"] != "مافيا"]
            try:
                await ctx.bot.send_message(
                    uid,
                    "🔫 *اختر من تقتل الليلة:*",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        elif role == "دكتور":
            keyboard = [[InlineKeyboardButton(f"💊 {p['name']}", callback_data=f"heal_{tid}")] 
                       for tid, p in alive.items()]
            try:
                await ctx.bot.send_message(
                    uid,
                    "💊 *اختر من تشفي الليلة:*",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        elif role == "محقق":
            keyboard = [[InlineKeyboardButton(f"🔍 {p['name']}", callback_data=f"invest_{tid}")] 
                       for tid, p in alive.items() if p["role"] != "محقق"]
            try:
                await ctx.bot.send_message(
                    uid,
                    "🔍 *اختر من تحقق معه الليلة:*",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

async def night_action_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    # إيجاد اللعبة الصحيحة
    game = None
    chat_id = None
    for cid, g in games.items():
        if uid in g["players"]:
            game = g
            chat_id = cid
            break

    if not game or game["phase"] != "night":
        return

    alive = get_alive(game)

    if data.startswith("mafia_"):
        target_id = int(data.split("_")[1])
        game["mafia_target"] = target_id
        await query.edit_message_text(f"✅ اخترت {game['players'][target_id]['name']} هدفاً!")

    elif data.startswith("heal_"):
        target_id = int(data.split("_")[1])
        game["healed"] = target_id
        await query.edit_message_text(f"✅ ستشفي {game['players'][target_id]['name']} الليلة!")

    elif data.startswith("invest_"):
        target_id = int(data.split("_")[1])
        game["investigated"] = target_id
        target = game["players"][target_id]
        is_mafia = target["role"] == "مافيا"
        await query.edit_message_text(
            f"🔍 نتيجة التحقيق:\n{target['name']} هو {'🔴 مافيا!' if is_mafia else '🟢 بريء!'}"
        )

    # تحقق إذا المافيا قرروا
    if game["mafia_target"] is not None:
        await asyncio.sleep(3)
        await resolve_night(chat_id, ctx)

async def resolve_night(chat_id, ctx):
    game = games[chat_id]
    target_id = game["mafia_target"]
    healed_id = game["healed"]

    if target_id:
        if target_id == healed_id:
            result_msg = f"🌅 *الصباح*\n\nالدكتور أنقذ {game['players'][target_id]['name']} الليلة! لم يمت أحد! 🎉"
        else:
            game["players"][target_id]["alive"] = False
            result_msg = f"🌅 *الصباح*\n\n💀 {game['players'][target_id]['name']} وجد ميتاً الليلة!"
    else:
        result_msg = "🌅 *الصباح*\n\nمرت ليلة هادئة، لم يحدث شيء!"

    # إعادة تعيين الليل
    game["mafia_target"] = None
    game["healed"] = None
    game["investigated"] = None

    winner = check_winner(game)
    if winner:
        await end_game(chat_id, ctx, winner)
        return

    game["phase"] = "day"
    game["day"] += 1
    alive = get_alive(game)
    alive_list = "\n".join(f"• {p['name']}" for p in alive.values())

    keyboard = [[InlineKeyboardButton(f"🗳️ {p['name']}", callback_data=f"vote_{uid}")] 
               for uid, p in alive.items()]
    await ctx.bot.send_message(
        chat_id,
        f"{result_msg}\n\n👥 اللاعبون الأحياء:\n{alive_list}\n\n🗳️ *التصويت بدأ!* اختاروا من تظنونه مافيا:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    game["votes"] = {}

async def vote_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    chat_id = query.message.chat_id
    if chat_id not in games:
        return

    game = games[chat_id]
    if game["phase"] != "day":
        await query.answer("مو وقت التصويت!", show_alert=True)
        return

    if uid not in game["players"] or not game["players"][uid]["alive"]:
        await query.answer("أنت لست لاعباً حياً!", show_alert=True)
        return

    target_id = int(data.split("_")[1])
    game["votes"][uid] = target_id
    alive = get_alive(game)

    await query.answer(f"✅ صوتك سُجِّل!")

    # تحقق إذا كل الأحياء صوتوا
    if len(game["votes"]) >= len(alive):
        await resolve_vote(chat_id, ctx)

async def resolve_vote(chat_id, ctx):
    game = games[chat_id]
    vote_count = {}
    for target in game["votes"].values():
        vote_count[target] = vote_count.get(target, 0) + 1

    if not vote_count:
        return

    max_votes = max(vote_count.values())
    candidates = [uid for uid, v in vote_count.items() if v == max_votes]
    executed = random.choice(candidates)

    game["players"][executed]["alive"] = False
    executed_name = game["players"][executed]["name"]
    executed_role = game["players"][executed]["role"]

    winner = check_winner(game)
    if winner:
        await ctx.bot.send_message(
            chat_id,
            f"🗳️ اللاعبون صوتوا على إعدام *{executed_name}*\nكان دوره: {ROLES.get(executed_role, '')} {executed_role}",
            parse_mode="Markdown"
        )
        await end_game(chat_id, ctx, winner)
        return

    game["phase"] = "night"
    await ctx.bot.send_message(
        chat_id,
        f"🗳️ *نتيجة التصويت:*\n\n💀 تم إعدام *{executed_name}*!\nكان دوره: {ROLES.get(executed_role, '')} {executed_role}\n\n🌙 حلّ الليل...",
        parse_mode="Markdown"
    )
    await asyncio.sleep(2)
    await send_night_actions(chat_id, ctx)

async def end_game(chat_id, ctx, winner):
    game = games[chat_id]
    roles_reveal = "\n".join(
        f"{'💀' if not p['alive'] else '✅'} {p['name']}: {ROLES.get(p['role'], '')} {p['role']}"
        for p in game["players"].values()
    )

    if winner == "مواطنون":
        msg = f"🎉 *انتهت اللعبة!*\n\n🏆 *فاز المواطنون!* قضوا على المافيا!\n\n📋 الأدوار:\n{roles_reveal}"
    else:
        msg = f"🎉 *انتهت اللعبة!*\n\n🔫 *فازت المافيا!* سيطروا على المدينة!\n\n📋 الأدوار:\n{roles_reveal}"

    await ctx.bot.send_message(chat_id, msg, parse_mode="Markdown")
    del games[chat_id]

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎭 *أوامر لعبة المافيا:*\n\n"
        "/newgame - بدء لعبة جديدة\n"
        "/begin - بدء اللعبة بعد اكتمال اللاعبين\n"
        "/help - عرض المساعدة\n\n"
        "📌 *كيف تلعب:*\n"
        "1. أضف البوت للمجموعة\n"
        "2. اكتب /newgame\n"
        "3. اضغط 'انضم' (4 لاعبين على الأقل)\n"
        "4. اكتب /begin لبدء اللعبة\n"
        "5. راجع رسائلك الخاصة لمعرفة دورك!",
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("newgame", newgame_cmd))
    app.add_handler(CommandHandler("begin", begin_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(join_callback, pattern="^join$"))
    app.add_handler(CallbackQueryHandler(night_action_callback, pattern="^(mafia|heal|invest)_"))
    app.add_handler(CallbackQueryHandler(vote_callback, pattern="^vote_"))
    print("✅ البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
