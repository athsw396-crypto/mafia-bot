import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN", "ضع_التوكن_هنا")
games = {}

ROLES = {"مافيا": "🔫", "مواطن": "👤", "دكتور": "💊", "محقق": "🔍"}

def new_game():
    return {
        "players": {},
        "phase": "joining",
        "day": 0,
        "votes": {},
        "healed": None,
        "investigated": None,
        "mafia_target": None,
        "mafia_votes": {},
        "night_step": None,  # "mafia" / "doctor" / "detective"
        "timeout_task": None # لإلغاء مهلة الـ 3 دقائق إذا اختاروا مبكراً
    }

def assign_roles(players):
    ids = list(players.keys())
    random.shuffle(ids)
    n = len(ids)
    roles = ["مواطن"] * n
    
    # تحديد عدد المافيا بناءً على التحديث الجديد (13 لاعب وأكثر = 3 مافيا)
    if n >= 13:
        roles[0] = "مافيا"
        roles[1] = "مافيا"
        roles[2] = "مافيا"
    elif n >= 5:
        roles[0] = "مافيا"
        roles[1] = "مافيا"
    else:
        roles[0] = "مافيا"
        
    if n >= 4: roles[-1] = "دكتور"
    if n >= 6: roles[-2] = "محقق"
    
    random.shuffle(roles)
    for i, uid in enumerate(ids):
        players[uid]["role"] = roles[i]
    return players

def get_alive(game):
    return {uid: p for uid, p in game["players"].items() if p["alive"]}

def check_winner(game):
    alive = get_alive(game)
    mafia = [p for p in alive.values() if p["role"] == "مافيا"]
    others = [p for p in alive.values() if p["role"] != "مافيا"]
    if not mafia: return "مواطنون"
    if len(mafia) >= len(others): return "مافيا"
    return None

def joining_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✋ انضم للعبة", callback_data="join"),
        InlineKeyboardButton("🚪 خروج", callback_data="leave")
    ]])

# ── أوامر ──────────────────────────────────────────

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("أضفني لمجموعة واستخدم /newgame هناك! 🎮")
        return
    chat_id = update.effective_chat.id
    games[chat_id] = new_game()
    await update.message.reply_text(
        "🎭 *لعبة المافيا*\n\nاضغط انضم للمشاركة!\nالحد الأدنى: 4 لاعبين\n\nعندما يكتمل اللاعبون اكتب /begin",
        reply_markup=joining_keyboard(), parse_mode="Markdown"
    )

async def newgame_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user = query.from_user
    if chat_id not in games or games[chat_id]["phase"] != "joining":
        await query.answer("اللعبة مو في مرحلة التسجيل!", show_alert=True)
        return
    game = games[chat_id]
    if user.id in game["players"]:
        await query.answer("أنت مسجل بالفعل! ✅", show_alert=True)
        return
    game["players"][user.id] = {"name": user.first_name, "role": None, "alive": True}
    names = [p["name"] for p in game["players"].values()]
    
    await query.edit_message_text(
        f"🎭 *لعبة المافيا*\n\n👥 اللاعبون ({len(names)}):\n" +
        "\n".join(f"• {n}" for n in names) +
        "\n\nاكتب /begin لبدء اللعبة (4 لاعبين على الأقل)",
        reply_markup=joining_keyboard(), parse_mode="Markdown"
    )
    await query.answer()

async def leave_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
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
    text = (
        f"🎭 *لعبة المافيا*\n\n👥 اللاعبون ({len(names)}):\n" +
        "\n".join(f"• {n}" for n in names) +
        "\n\nاكتب /begin لبدء اللعبة (4 لاعبين على الأقل)"
    ) if names else "🎭 *لعبة المافيا*\n\nما في لاعبين. اضغط انضم للمشاركة!"
    await query.edit_message_text(text, reply_markup=joining_keyboard(), parse_mode="Markdown")
    await query.answer("خرجت من اللعبة 👋")

async def begin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        try:
            extra = ""
            if role == "مافيا":
                mafia_names = [p["name"] for p in game["players"].values() if p["role"] == "مافيا"]
                extra = f"\n\n🔫 زملاؤك في المافيا: {', '.join(mafia_names)}"
            desc = {"مافيا": "أنت من المافيا، اقتل المواطنين ليلاً!", "مواطن": "أنت مواطن شريف، اكشف المافيا!", "دكتور": "أنت الدكتور، اشفِ لاعباً كل ليلة!", "محقق": "أنت المحقق، تحقق من هوية لاعب كل ليلة!"}.get(role, "")
            await context.bot.send_message(uid, f"🎭 دورك:\n\n{ROLES.get(role,'')} *{role}*{extra}\n\n{desc}", parse_mode="Markdown")
        except Exception:
            pass
    game["phase"] = "night"
    game["day"] = 1
    await update.message.reply_text(f"🌙 *الليلة {game['day']}*\n\nبدأت اللعبة! تم إرسال الأدوار.", parse_mode="Markdown")
    await asyncio.sleep(2)
    await start_mafia_phase(chat_id, context)

# ── متحكمات الليل بالأحداث الفورية ──────────────────────────────────────────

async def start_mafia_phase(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]
    game["night_step"] = "mafia"
    
    alive = get_alive(game)
    mafia_uids = [uid for uid, p in alive.items() if p["role"] == "مافيا"]
    targets = {uid: p for uid, p in alive.items() if p["role"] != "مافيا"}
    
    if mafia_uids and targets:
        await context.bot.send_message(chat_id, "🌑 *حلّ الظلام على المدينة...*\n\n🔫 همسات المافيا تتردد في الأزقة وهم يتآمرون لاختيار ضحيتهم... (المهلة: 3 دقائق)", parse_mode="Markdown")
        kb = [[InlineKeyboardButton(f"🎯 {p['name']}", callback_data=f"mafia_{uid}")] for uid, p in targets.items()]
        for uid in mafia_uids:
            try: await context.bot.send_message(uid, "🔫 *اختر من تغتال الليلة:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
            except Exception: pass
        
        game["timeout_task"] = asyncio.create_task(mafia_timeout(chat_id, context, targets, mafia_uids))
    else:
        asyncio.create_task(start_doctor_phase(chat_id, context))

async def mafia_timeout(chat_id, context, targets, mafia_uids):
    try:
        await asyncio.sleep(180)
        if chat_id in games and games[chat_id]["night_step"] == "mafia":
            if targets:
                games[chat_id]["mafia_target"] = random.choice(list(targets.keys()))
            for uid in mafia_uids:
                try: await context.bot.send_message(uid, "⏱️ *انتهى الوقت! تم اختيار هدف عشوائي.*", parse_mode="Markdown")
                except Exception: pass
            await start_doctor_phase(chat_id, context)
    except asyncio.CancelledError:
        pass

async def start_doctor_phase(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]
    if game["timeout_task"] and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()
    
    alive = get_alive(game)
    has_doctor_in_game = any(p["role"] == "دكتور" for p in game["players"].values())
    doctor_uids = [uid for uid, p in alive.items() if p["role"] == "دكتور"]
    
    if has_doctor_in_game:
        game["night_step"] = "doctor"
        await context.bot.send_message(chat_id, "💊 *الدكتور استيقظ على صوت خطوات مريبة...*\n\nيسارع ليقرر من يحميه بدوائه قبل فوات الأوان... (المهلة: 3 دقائق)", parse_mode="Markdown")
        
        if doctor_uids:
            kb = [[InlineKeyboardButton(f"💊 {p['name']}", callback_data=f"heal_{uid}")] for uid, p in alive.items()]
            for uid in doctor_uids:
                try: await context.bot.send_message(uid, "💊 *اختر من تشفي الليلة:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
                except Exception: pass
            game["timeout_task"] = asyncio.create_task(doctor_timeout(chat_id, context, alive, doctor_uids))
        else:
            game["timeout_task"] = asyncio.create_task(fake_doctor_timeout(chat_id, context, alive))
    else:
        games[chat_id]["healed"] = None
        asyncio.create_task(start_detective_phase(chat_id, context))

async def doctor_timeout(chat_id, context, alive, doctor_uids):
    try:
        await asyncio.sleep(180)
        if chat_id in games and games[chat_id]["night_step"] == "doctor":
            if alive:
                games[chat_id]["healed"] = random.choice(list(alive.keys()))
            for uid in doctor_uids:
                try: await context.bot.send_message(uid, "⏱️ *انتهى الوقت! تم اختيار شخص عشوائي لحمايته.*", parse_mode="Markdown")
                except Exception: pass
            await start_detective_phase(chat_id, context)
    except asyncio.CancelledError:
        pass

async def fake_doctor_timeout(chat_id, context, alive):
    try:
        await asyncio.sleep(random.randint(15, 30))
        if chat_id in games and games[chat_id]["night_step"] == "doctor":
            if alive:
                games[chat_id]["healed"] = random.choice(list(alive.keys()))
            await start_detective_phase(chat_id, context)
    except asyncio.CancelledError:
        pass

async def start_detective_phase(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]
    if game["timeout_task"] and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()
    
    alive = get_alive(game)
    has_detective_in_game = any(p["role"] == "محقق" for p in game["players"].values())
    detect_uids = [uid for uid, p in alive.items() if p["role"] == "محقق"]
    det_targets = {uid: p for uid, p in alive.items() if uid not in detect_uids}
    
    if has_detective_in_game:
        game["night_step"] = "detective"
        await context.bot.send_message(chat_id, "🔍 *المحقق يتسلل في ظلام الليل...*\n\nعيناه تراقبان كل تفصيلة وهو يستعد للكشف عن أحد المشتبه بهم... (المهلة: 3 دقائق)", parse_mode="Markdown")
        
        if detect_uids and det_targets:
            kb = [[InlineKeyboardButton(f"🔍 {p['name']}", callback_data=f"invest_{uid}")] for uid, p in det_targets.items()]
            for uid in detect_uids:
                try: await context.bot.send_message(uid, "🔍 *اختر من تحقق معه الليلة:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
                except Exception: pass
            game["timeout_task"] = asyncio.create_task(detective_timeout(chat_id, context, det_targets, detect_uids))
        else:
            game["timeout_task"] = asyncio.create_task(fake_detective_timeout(chat_id, context, alive))
    else:
        games[chat_id]["investigated"] = None
        asyncio.create_task(end_night_phase(chat_id, context))

async def detective_timeout(chat_id, context, det_targets, detect_uids):
    try:
        await asyncio.sleep(180)
        if chat_id in games and games[chat_id]["night_step"] == "detective":
            if det_targets:
                games[chat_id]["investigated"] = random.choice(list(det_targets.keys()))
            for uid in detect_uids:
                try:
                    t_rand = games[chat_id]["investigated"]
                    is_mafia_rand = games[chat_id]["players"][t_rand]["role"] == "مافيا"
                    await context.bot.send_message(uid, f"⏱️ *انتهى الوقت! تم التحقيق عشوائياً مع:*\n*{games[chat_id]['players'][t_rand]['name']}* وهو {'🔴 مافيا!' if is_mafia_rand else '🟢 بريء!'}", parse_mode="Markdown")
                except Exception: pass
            await end_night_phase(chat_id, context)
    except asyncio.CancelledError:
        pass

async def fake_detective_timeout(chat_id, context, alive):
    try:
        await asyncio.sleep(random.randint(15, 30))
        if chat_id in games and games[chat_id]["night_step"] == "detective":
            if alive:
                det_targets = {uid: p for uid, p in alive.items() if p["role"] != "محقق"}
                if det_targets: games[chat_id]["investigated"] = random.choice(list(det_targets.keys()))
            await end_night_phase(chat_id, context)
    except asyncio.CancelledError:
        pass

async def end_night_phase(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]
    if game["timeout_task"] and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()
    game["night_step"] = None
    await resolve_night(chat_id, context)

# ── callback الليل ──────────────────────────────────

async def night_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    uid   = query.from_user.id

    game = None
    chat_id = None
    for cid, g in games.items():
        if uid in g["players"]:
            game = g
            chat_id = cid
            break

    if not game or game["phase"] != "night":
        await query.answer("مو وقت هذا الإجراء!", show_alert=True)
        return

    if uid not in game["players"] or not game["players"][uid]["alive"]:
        await query.answer("أنت خارج اللعبة!", show_alert=True)
        return

    step = game.get("night_step")
    parts = data.split("_")
    action = parts[0]
    target_id = int(parts[1])

    if action == "mafia" and step == "mafia":
        if game["players"][uid]["role"] != "مافيا":
            await query.answer("هذا مو دورك!", show_alert=True)
            return
        
        await query.answer("✅ تم تسجيل صوتك!")
        await query.edit_message_text(f"✅ اخترت *{game['players'][target_id]['name']}* هدفاً!", reply_markup=None, parse_mode="Markdown")
        
        game["mafia_votes"][uid] = target_id
        alive = get_alive(game)
        mafia_uids = [u for u, p in alive.items() if p["role"] == "مافيا"]
        
        if len(game["mafia_votes"]) >= len(mafia_uids):
            vc = {}
            for t in game["mafia_votes"].values(): vc[t] = vc.get(t, 0) + 1
            game["mafia_target"] = max(vc, key=vc.get)
            asyncio.create_task(start_doctor_phase(chat_id, context))
        else:
            for other in mafia_uids:
                if other != uid:
                    try: await context.bot.send_message(other, f"⚠️ زميلك اختار *{game['players'][target_id]['name']}*، اختر أنت أيضاً!", parse_mode="Markdown")
                    except Exception: pass

    elif action == "heal" and step == "doctor":
        if game["players"][uid]["role"] != "دكتور":
            await query.answer("هذا مو دورك!", show_alert=True)
            return
        
        await query.answer("✅ تم الشفاء!")
        await query.edit_message_text(f"✅ ستشفي *{game['players'][target_id]['name']}* الليلة!", reply_markup=None, parse_mode="Markdown")
        
        game["healed"] = target_id
        asyncio.create_task(start_detective_phase(chat_id, context))

    elif action == "invest" and step == "detective":
        if game["players"][uid]["role"] != "محقق":
            await query.answer("هذا مو دورك!", show_alert=True)
            return
        
        await query.answer("✅ تم التحقيق!")
        is_mafia = game["players"][target_id]["role"] == "مافيا"
        await query.edit_message_text(f"🔍 نتيجة التحقيق:\n*{game['players'][target_id]['name']}* هو {'🔴 مافيا!' if is_mafia else '🟢 بريء!'}", reply_markup=None, parse_mode="Markdown")
        
        game["investigated"] = target_id
        asyncio.create_task(end_night_phase(chat_id, context))
    else:
        await query.answer("مو وقت هذا الإجراء!", show_alert=True)

# ── نهاية الليل ─────────────────────────────────────

async def resolve_night(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]
    target_id = game["mafia_target"]
    healed_id  = game["healed"]

    if target_id:
        if target_id == healed_id:
            msg = f"🌅 *أشرقت شمس الصباح*\n\n✨ الدكتور أنقذ *{game['players'][target_id]['name']}* في اللحظة الأخيرة!\nلم يمت أحد الليلة! 🎉"
        else:
            game["players"][target_id]["alive"] = False
            role = game["players"][target_id]["role"]
            label = "مافيا 🔫" if role == "مافيا" else "مواطن 👤"
            msg = f"🌅 *أشرقت شمس الصباح*\n\n⚰️ اغتيل *{game['players'][target_id]['name']}* الليلة... وكان {label}"
    else:
        msg = "🌅 *أشرقت شمس الصباح*\n\nمرّت ليلة هادئة، لم يحدث شيء!"

    game["mafia_target"] = None
    game["healed"] = None
    game["investigated"] = None

    winner = check_winner(game)
    if winner:
        await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
        await end_game(chat_id, context, winner)
        return

    game["phase"] = "day"
    alive = get_alive(game)
    alive_list = "\n".join(f"• {p['name']}" for p in alive.values())
    kb = [[InlineKeyboardButton(f"🗳️ {p['name']}", callback_data=f"vote_{uid}")] for uid, p in alive.items()]
    kb.append([InlineKeyboardButton("⏭️ تخطي التصويت", callback_data="skip_vote")])
    game["votes"] = {}
    await context.bot.send_message(chat_id,
        f"{msg}\n\n👥 *اللاعبون الأحياء:*\n{alive_list}\n\n☀️ *بدأ النقاش!* من تظنه المافيا؟",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

# ── التصويت ─────────────────────────────────────────

async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    chat_id = query.message.chat_id
    uid     = query.from_user.id

    if chat_id not in games:
        await query.answer("ما في لعبة نشطة!", show_alert=True)
        return

    game = games[chat_id]

    if query.data == "skip_vote":
        await query.answer("تم تخطي التصويت!")
        await query.edit_message_reply_markup(reply_markup=None)
        await resolve_vote(chat_id, context, skipped=True)
        return

    if game["phase"] != "day":
        await query.answer("مو وقت التصويت!", show_alert=True)
        return
    if uid not in game["players"]:
        await query.answer("أنت لست لاعباً!", show_alert=True)
        return
    if not game["players"][uid]["alive"]:
        await query.answer("أنت خارج اللعبة!", show_alert=True)
        return

    try: target_id = int(query.data.split("_")[1])
    except Exception: return

    if not game["players"].get(target_id, {}).get("alive"):
        await query.answer("هذا اللاعب خارج اللعبة!", show_alert=True)
        return

    already = uid in game["votes"]
    game["votes"][uid] = target_id
    name = game["players"][target_id]['name']
    await query.answer(f"{'✅ غيّرت صوتك إلى' if already else '✅ صوّتت على'} {name}")

    alive = get_alive(game)
    if len(game["votes"]) >= len(alive):
        try: await query.edit_message_reply_markup(reply_markup=None)
        except Exception: pass
        await resolve_vote(chat_id, context)

async def resolve_vote(chat_id, context, skipped=False):
    if chat_id not in games: return
    game = games[chat_id]

    if skipped or not game["votes"]:
        game["phase"] = "night"
        game["day"] += 1
        await context.bot.send_message(chat_id, "⏭️ *لم يتفق أهل المدينة!*\n\nلم يُعدم أحد.\n\n🌙 يحل الليل...", parse_mode="Markdown")
        await asyncio.sleep(2)
        await start_mafia_phase(chat_id, context)
        return

    vc = {}
    for t in game["votes"].values(): vc[t] = vc.get(t, 0) + 1
    max_v = max(vc.values())
    candidates = [uid for uid, v in vc.items() if v == max_v]

    if len(candidates) > 1:
        game["phase"] = "night"
        game["day"] += 1
        names = [game["players"][u]["name"] for u in candidates]
        await context.bot.send_message(chat_id, f"⚖️ *تعادل!*\n\nتعادل بين: {', '.join(names)}\nلم يُعدم أحد!\n\n🌙 يحل الليل...", parse_mode="Markdown")
        await asyncio.sleep(2)
        await start_mafia_phase(chat_id, context)
        return

    executed = candidates[0]
    game["players"][executed]["alive"] = False
    name  = game["players"][executed]["name"]
    role  = game["players"][executed]["role"]
    label = "مافيا 🔫" if role == "مافيا" else "مواطن 👤"
    msg   = f"🗳️ *نتيجة التصويت:*\n\n⚰️ اغتيل *{name}* بـ {max_v} أصوات... وكان {label}"

    winner = check_winner(game)
    if winner:
        await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
        await end_game(chat_id, context, winner)
        return

    game["phase"] = "night"
    game["day"] += 1
    await context.bot.send_message(chat_id, f"{msg}\n\n🌙 يحل الليل مجدداً...", parse_mode="Markdown")
    await asyncio.sleep(2)
    await start_mafia_phase(chat_id, context)

async def end_game(chat_id, context, winner):
    game = games[chat_id]
    if game["timeout_task"] and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()
    reveal = "\n".join(f"{'💀' if not p['alive'] else '✅'} {p['name']}: {ROLES.get(p['role'],'')} {p['role']}" for p in game["players"].values())
    msg = f"🎉 *انتهت اللعبة!*\n\n{'🏆 فاز المواطنون! قضوا على المافيا!' if winner == 'مواطنون' else '🔫 فازت المافيا! سيطروا على المدينة!'}\n\n📋 *الأدوار:*\n{reveal}"
    await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
    del games[chat_id]

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎭 *أوامر لعبة المافيا:*\n\n/newgame - بدء لعبة\n/begin - بدء اللعبة\n/help - المساعدة\n\n"
        "📌 *كيف تلعب:*\n1. أضف البوت كـ Admin\n2. /newgame\n3. انضم (4 لاعبين+)\n4. /begin\n5. راجع رسائلك الخاصة!",
        parse_mode="Markdown"
    )

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        await update.message.reply_text("ما في لعبة نشطة الحين!")
        return
    game = games[chat_id]
    if game["timeout_task"] and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()
    del games[chat_id]
    await update.message.reply_text("🛑 *تم إيقاف اللعبة!*\n\nيمكنكم بدء لعبة جديدة بكتابة /newgame", parse_mode="Markdown")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",   start_cmd))
    app.add_handler(CommandHandler("newgame", newgame_cmd))
    app.add_handler(CommandHandler("begin",   begin_cmd))
    app.add_handler(CommandHandler("help",    help_cmd))
    app.add_handler(CommandHandler("stop",    stop_cmd))
    app.add_handler(CallbackQueryHandler(join_callback,   pattern="^join$"))
    app.add_handler(CallbackQueryHandler(leave_callback,  pattern="^leave$"))
    
    app.add_handler(CallbackQueryHandler(night_callback,  pattern="^(mafia|heal|invest)_.*"))
    app.add_handler(CallbackQueryHandler(vote_callback,   pattern="^(vote_.*|skip_vote)"))
    
    print("✅ البوت يعمل بكفاءة...")
    app.run_polling()

if __name__ == "__main__":
    main()
