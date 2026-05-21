import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

TOKEN = os.environ.get("BOT_TOKEN", "ضع_التوكن_هنا")

games = {}

ROLES = {
    "مافيا": "🔫",
    "مواطن": "👤",
    "دكتور": "💊",
    "محقق": "🔍"
}

def new_game():
    return {
        "players": {},
        "phase": "joining",
        "day": 0,
        "votes": {},
        "healed": None,
        "investigated": None,
        "mafia_target": None,
        "mafia_voted": set(),
        "night_timer_task": None,
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

def joining_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✋ انضم للعبة", callback_data="join"),
         InlineKeyboardButton("🚪 خروج", callback_data="leave")]
    ])

async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        await update.message.reply_text("أضفني لمجموعة واستخدم /newgame هناك! 🎮")
        return
    games[chat_id] = new_game()
    await update.message.reply_text(
        "🎭 *لعبة المافيا*\n\nاضغط انضم للمشاركة!\nالحد الأدنى: 4 لاعبين\n\nعندما يكتمل اللاعبون، اكتب /begin",
        reply_markup=joining_keyboard(),
        parse_mode="Markdown"
    )

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
    game["players"][uid] = {"name": user.first_name, "role": None, "alive": True}
    names = [p["name"] for p in game["players"].values()]
    await query.edit_message_text(
        f"🎭 *لعبة المافيا*\n\n👥 اللاعبون ({len(names)}):\n" +
        "\n".join(f"• {n}" for n in names) +
        "\n\nاكتب /begin لبدء اللعبة (4 لاعبين على الأقل)",
        reply_markup=joining_keyboard(),
        parse_mode="Markdown"
    )

async def leave_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    uid = query.from_user.id

    if chat_id not in games or games[chat_id]["phase"] != "joining":
        await query.answer("ما تقدر تخرج الحين!", show_alert=True)
        return

    game = games[chat_id]
    if uid not in game["players"]:
        await query.answer("أنت مو مسجل أصلاً!", show_alert=True)
        return

    del game["players"][uid]
    names = [p["name"] for p in game["players"].values()]

    if names:
        await query.edit_message_text(
            f"🎭 *لعبة المافيا*\n\n👥 اللاعبون ({len(names)}):\n" +
            "\n".join(f"• {n}" for n in names) +
            "\n\nاكتب /begin لبدء اللعبة (4 لاعبين على الأقل)",
            reply_markup=joining_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            "🎭 *لعبة المافيا*\n\nما في لاعبين حالياً. اضغط انضم للمشاركة!",
            reply_markup=joining_keyboard(),
            parse_mode="Markdown"
        )
    await query.answer(f"خرجت من اللعبة 👋")


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
    for uid, player in game["players"].items():
        role = player["role"]
        emoji = ROLES.get(role, "❓")
        try:
            mafia_members = ""
            if role == "مافيا":
                mafia = [p["name"] for p in game["players"].values() if p["role"] == "مافيا"]
                mafia_members = f"\n\n🔫 زملاؤك في المافيا: {', '.join(mafia)}"
            desc = {
                "مافيا": "أنت من المافيا، اقتل المواطنين ليلاً!",
                "مواطن": "أنت مواطن شريف، اكشف المافيا!",
                "دكتور": "أنت الدكتور، اشفِ لاعباً كل ليلة!",
                "محقق": "أنت المحقق، تحقق من هوية لاعب كل ليلة!"
            }.get(role, "")
            await ctx.bot.send_message(
                uid,
                f"🎭 دورك في اللعبة:\n\n{emoji} *{role}*{mafia_members}\n\n{desc}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    game["phase"] = "night"
    game["day"] = 1
    await update.message.reply_text(
        f"🌙 *الليلة {game['day']}*\n\nبدأت اللعبة! تم إرسال الأدوار للجميع.",
        parse_mode="Markdown"
    )
    await asyncio.sleep(2)
    await start_night_phase(chat_id, ctx)

# ========================
# مرحلة الليل مع مؤقتات
# ========================

async def start_night_phase(chat_id, ctx):
    game = games[chat_id]
    game["mafia_target"] = None
    game["healed"] = None
    game["investigated"] = None
    game["mafia_voted"] = set()

    alive = get_alive(game)
    mafia_players = {uid: p for uid, p in alive.items() if p["role"] == "مافيا"}
    doctor_players = {uid: p for uid, p in alive.items() if p["role"] == "دكتور"}
    detective_players = {uid: p for uid, p in alive.items() if p["role"] == "محقق"}

    async def send_countdown(uid, text, seconds, keyboard):
        """يرسل رسالة مع مؤقت يتحدث كل 5 ثواني"""
        try:
            msg = await ctx.bot.send_message(
                uid,
                f"{text}\n\n⏱️ الوقت المتبقي: *{seconds} ثانية*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            remaining = seconds
            while remaining > 0:
                await asyncio.sleep(5)
                remaining -= 5
                if remaining <= 0:
                    break
                try:
                    await ctx.bot.edit_message_text(
                        f"{text}\n\n⏱️ الوقت المتبقي: *{remaining} ثانية*",
                        chat_id=uid,
                        message_id=msg.message_id,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
        except Exception:
            pass

    # مرحلة المافيا
    if mafia_players:
        await ctx.bot.send_message(
            chat_id,
            "🌑 *الليل يحل على المدينة...*\n\n🔫 المافيا تتحرك في الظلام وتختار ضحيتها...",
            parse_mode="Markdown"
        )
        targets = {uid: p for uid, p in alive.items() if p["role"] != "مافيا"}
        keyboard = [[InlineKeyboardButton(f"🎯 {p['name']}", callback_data=f"mafia_{uid}")]
                   for uid, p in targets.items()]
        for uid in mafia_players:
            asyncio.create_task(send_countdown(uid, "🔫 *اختر من تغتال الليلة:*", 20, keyboard))

        for i in range(20):
            await asyncio.sleep(1)
            if chat_id not in games:
                return
            if games[chat_id].get("mafia_target") is not None:
                break

        if games[chat_id].get("mafia_target") is None and targets:
            games[chat_id]["mafia_target"] = random.choice(list(targets.keys()))

    # مرحلة الدكتور
    if doctor_players:
        await ctx.bot.send_message(
            chat_id,
            "💊 *الدكتور يجول في المدينة...*\n\nيسعى لإنقاذ من قد يكون في خطر...",
            parse_mode="Markdown"
        )
        keyboard = [[InlineKeyboardButton(f"💊 {p['name']}", callback_data=f"heal_{uid}")]
                   for uid, p in alive.items()]
        for uid in doctor_players:
            asyncio.create_task(send_countdown(uid, "💊 *اختر من تشفي الليلة:*", 10, keyboard))

        for i in range(10):
            await asyncio.sleep(1)
            if chat_id not in games:
                return
            if games[chat_id].get("healed") is not None:
                break

        if games[chat_id].get("healed") is None and alive:
            games[chat_id]["healed"] = random.choice(list(alive.keys()))

    # مرحلة المحقق
    if detective_players:
        await ctx.bot.send_message(
            chat_id,
            "🔍 *المحقق يفتش في الأدلة...*\n\nيحاول كشف هوية أحد المشتبه بهم...",
            parse_mode="Markdown"
        )
        targets_for_detective = {uid: p for uid, p in alive.items() if uid not in detective_players}
        keyboard = [[InlineKeyboardButton(f"🔍 {p['name']}", callback_data=f"invest_{uid}")]
                   for uid, p in targets_for_detective.items()]
        for uid in detective_players:
            asyncio.create_task(send_countdown(uid, "🔍 *اختر من تحقق معه الليلة:*", 10, keyboard))

        for i in range(10):
            await asyncio.sleep(1)
            if chat_id not in games:
                return
            if games[chat_id].get("investigated") is not None:
                break

    await resolve_night(chat_id, ctx)

async def night_action_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

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
        game["mafia_voted"].add(uid)
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

async def resolve_night(chat_id, ctx):
    if chat_id not in games:
        return
    game = games[chat_id]
    target_id = game["mafia_target"]
    healed_id = game["healed"]

    if target_id:
        if target_id == healed_id:
            result_msg = f"🌅 *الصباح أشرق على المدينة*\n\n✨ الدكتور كان يقظاً وأنقذ {game['players'][target_id]['name']} في اللحظة الأخيرة!\nلم يمت أحد الليلة! 🎉"
        else:
            game["players"][target_id]["alive"] = False
            result_msg = f"🌅 *الصباح أشرق على المدينة*\n\n💀 وجد أهل المدينة *{game['players'][target_id]['name']}* ميتاً هذا الصباح!\nكان دوره: {ROLES.get(game['players'][target_id]['role'], '')} {game['players'][target_id]['role']}"
    else:
        result_msg = "🌅 *الصباح أشرق على المدينة*\n\nمرت ليلة هادئة، لم يحدث شيء!"

    game["mafia_target"] = None
    game["healed"] = None
    game["investigated"] = None

    winner = check_winner(game)
    if winner:
        await ctx.bot.send_message(chat_id, result_msg, parse_mode="Markdown")
        await end_game(chat_id, ctx, winner)
        return

    game["phase"] = "day"
    alive = get_alive(game)
    alive_list = "\n".join(f"• {p['name']}" for p in alive.values())

    keyboard = []
    for uid, p in alive.items():
        keyboard.append([InlineKeyboardButton(f"🗳️ {p['name']}", callback_data=f"vote_{uid}")])
    keyboard.append([InlineKeyboardButton("⏭️ تخطي التصويت", callback_data="skip_vote")])

    game["votes"] = {}
    await ctx.bot.send_message(
        chat_id,
        f"{result_msg}\n\n👥 *اللاعبون الأحياء:*\n{alive_list}\n\n☀️ *بدأ النقاش!*\nمن تظنه المافيا؟ صوّتوا لإعدامه!\n⏱️ لديكم وقت للتصويت:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def vote_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    uid = query.from_user.id

    if chat_id not in games:
        await query.answer("ما في لعبة نشطة!", show_alert=True)
        return

    game = games[chat_id]

    # تخطي التصويت
    if query.data == "skip_vote":
        await query.answer("تم تخطي التصويت!")
        await resolve_vote(chat_id, ctx, skipped=True)
        return

    if game["phase"] != "day":
        await query.answer("مو وقت التصويت!", show_alert=True)
        return

    # تحقق إن اللاعب في اللعبة وحي
    if uid not in game["players"]:
        await query.answer("أنت لست لاعباً في هذه اللعبة!", show_alert=True)
        return

    if not game["players"][uid]["alive"]:
        await query.answer("أنت خارج اللعبة، لا يمكنك التصويت!", show_alert=True)
        return

    target_id = int(query.data.split("_")[1])

    # تحقق إن الهدف حي
    if target_id not in game["players"] or not game["players"][target_id]["alive"]:
        await query.answer("هذا اللاعب خارج اللعبة!", show_alert=True)
        return

    # سجل الصوت
    already_voted = uid in game["votes"]
    game["votes"][uid] = target_id
    target_name = game["players"][target_id]["name"]

    if already_voted:
        await query.answer(f"✅ غيّرت صوتك إلى {target_name}")
    else:
        await query.answer(f"✅ صوّتت على {target_name}")

    alive = get_alive(game)
    if len(game["votes"]) >= len(alive):
        await resolve_vote(chat_id, ctx)

async def resolve_vote(chat_id, ctx, skipped=False):
    if chat_id not in games:
        return
    game = games[chat_id]

    if skipped or not game["votes"]:
        game["phase"] = "night"
        game["day"] += 1
        await ctx.bot.send_message(
            chat_id,
            "⏭️ *لم يتفق الجميع!*\n\nلم يتم إعدام أحد هذا اليوم.\n\n🌙 يحل الليل مجدداً...",
            parse_mode="Markdown"
        )
        await asyncio.sleep(2)
        await start_night_phase(chat_id, ctx)
        return

    vote_count = {}
    for target in game["votes"].values():
        vote_count[target] = vote_count.get(target, 0) + 1

    max_votes = max(vote_count.values())
    candidates = [uid for uid, v in vote_count.items() if v == max_votes]

    # إذا تعادل، ما يُعدم أحد
    if len(candidates) > 1:
        game["phase"] = "night"
        game["day"] += 1
        names = [game["players"][uid]["name"] for uid in candidates]
        await ctx.bot.send_message(
            chat_id,
            f"⚖️ *تعادل في التصويت!*\n\nتعادل بين: {', '.join(names)}\nلم يتم إعدام أحد!\n\n🌙 يحل الليل...",
            parse_mode="Markdown"
        )
        await asyncio.sleep(2)
        await start_night_phase(chat_id, ctx)
        return

    executed = candidates[0]
    game["players"][executed]["alive"] = False
    executed_name = game["players"][executed]["name"]
    executed_role = game["players"][executed]["role"]
    votes_received = max_votes

    winner = check_winner(game)
    msg = (
        f"🗳️ *نتيجة التصويت:*\n\n"
        f"💀 تم إعدام *{executed_name}* بـ {votes_received} أصوات!\n"
        f"كان دوره: {ROLES.get(executed_role, '')} {executed_role}"
    )

    if winner:
        await ctx.bot.send_message(chat_id, msg, parse_mode="Markdown")
        await end_game(chat_id, ctx, winner)
        return

    game["phase"] = "night"
    game["day"] += 1
    await ctx.bot.send_message(
        chat_id,
        f"{msg}\n\n🌙 يحل الليل مجدداً...",
        parse_mode="Markdown"
    )
    await asyncio.sleep(2)
    await start_night_phase(chat_id, ctx)

async def end_game(chat_id, ctx, winner):
    game = games[chat_id]
    roles_reveal = "\n".join(
        f"{'💀' if not p['alive'] else '✅'} {p['name']}: {ROLES.get(p['role'], '')} {p['role']}"
        for p in game["players"].values()
    )
    if winner == "مواطنون":
        msg = f"🎉 *انتهت اللعبة!*\n\n🏆 *فاز المواطنون!* قضوا على المافيا!\n\n📋 *الأدوار:*\n{roles_reveal}"
    else:
        msg = f"🎉 *انتهت اللعبة!*\n\n🔫 *فازت المافيا!* سيطروا على المدينة!\n\n📋 *الأدوار:*\n{roles_reveal}"
    await ctx.bot.send_message(chat_id, msg, parse_mode="Markdown")
    del games[chat_id]

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎭 *أوامر لعبة المافيا:*\n\n"
        "/newgame - بدء لعبة جديدة\n"
        "/begin - بدء اللعبة بعد اكتمال اللاعبين\n"
        "/help - عرض المساعدة\n\n"
        "📌 *كيف تلعب:*\n"
        "1. أضف البوت للمجموعة كـ Admin\n"
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
    app.add_handler(CallbackQueryHandler(leave_callback, pattern="^leave$"))
    app.add_handler(CallbackQueryHandler(night_action_callback, pattern="^(mafia|heal|invest)_"))
    app.add_handler(CallbackQueryHandler(vote_callback, pattern="^(vote_|skip_vote)"))
    print("✅ البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
