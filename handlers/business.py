from datetime import datetime, timezone
from aiogram import Router, F, Bot
from aiogram.types import BusinessMessagesDeleted, Message, BusinessConnection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from db.base import AsyncSessionLocal
from db.models import User, Subscription, SavedMessage, MessageType
from bot.utils.formatters import format_user_link, format_deleted_notify, format_edited_notify

router = Router()


async def get_owner_if_active(business_connection_id: str) -> User | None:
    """Возвращает владельца business-аккаунта только если у него есть активная подписка."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        # Один запрос: находим пользователя у которого есть активная подписка
        result = await session.execute(
            select(User)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                User.business_connection_id == business_connection_id,
                Subscription.is_active == True,
                Subscription.expires_at > now,
            )
        )
        return result.scalar_one_or_none()


# ── Бизнес-соединение подключено / отключено ─────────────────────────
@router.business_connection()
async def on_business_connection(bc: BusinessConnection):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, bc.user.id)
        if not user:
            return
        if bc.is_enabled:
            user.business_connection_id = bc.id
            user.business_connected_at = datetime.now(timezone.utc)
            await session.commit()
            await bc.bot.send_message(
                bc.user.id,
                "🟢 <b>Бизнес-бот подключён!</b>\n\n"
                "Теперь я буду отслеживать удалённые сообщения, правки и исчезающие фото "
                "в реальном времени.\n\n"
                "⚠️ История сообщений до подключения недоступна.",
                parse_mode="HTML",
            )
        else:
            user.business_connection_id = None
            await session.commit()
            await bc.bot.send_message(
                bc.user.id,
                "🔴 <b>Бизнес-бот отключён.</b>\n\n"
                "Отслеживание остановлено.",
                parse_mode="HTML",
            )


# ── Удалённые сообщения ───────────────────────────────────────────────
@router.deleted_business_messages()
async def on_deleted_messages(event: BusinessMessagesDeleted, bot: Bot):
    owner = await get_owner_if_active(event.business_connection_id)
    if not owner:
        return

    async with AsyncSessionLocal() as session:
        for msg in event.messages:
            sender = msg.from_user
            text = msg.text or msg.caption or ""
            media_file_id = None
            media_type = None

            if msg.photo:
                media_file_id = msg.photo[-1].file_id
                media_type = "photo"
            elif msg.video:
                media_file_id = msg.video.file_id
                media_type = "video"
            elif msg.voice:
                media_file_id = msg.voice.file_id
                media_type = "voice"
            elif msg.video_note:
                media_file_id = msg.video_note.file_id
                media_type = "video_note"
            elif msg.sticker:
                media_file_id = msg.sticker.file_id
                media_type = "sticker"
            elif msg.document:
                media_file_id = msg.document.file_id
                media_type = "document"

            saved = SavedMessage(
                owner_id=owner.id,
                message_type=MessageType.DELETED,
                from_user_id=sender.id if sender else None,
                from_username=sender.username if sender else None,
                from_first_name=sender.first_name if sender else None,
                chat_id=msg.chat.id if msg.chat else None,
                message_id=msg.message_id,
                business_connection_id=event.business_connection_id,
                original_text=text,
                media_file_id=media_file_id,
                media_type=media_type,
            )
            session.add(saved)

            notify_text = format_deleted_notify(msg, sender)
            try:
                if media_file_id and media_type:
                    await _send_media(bot, owner.id, media_file_id, media_type, notify_text)
                else:
                    await bot.send_message(owner.id, notify_text, parse_mode="HTML")
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to notify {owner.id}: {e}")

        await session.commit()


# ── Отредактированные сообщения ───────────────────────────────────────
@router.edited_business_message()
async def on_edited_message(message: Message, bot: Bot):
    owner = await get_owner_if_active(message.business_connection_id)
    if not owner:
        return

    new_text = message.text or message.caption or ""
    sender = message.from_user

    async with AsyncSessionLocal() as session:
        # Получаем предыдущую версию текста
        prev_result = await session.execute(
            select(SavedMessage)
            .where(
                SavedMessage.owner_id == owner.id,
                SavedMessage.message_id == message.message_id,
                SavedMessage.message_type == MessageType.EDITED,
            )
            .order_by(SavedMessage.event_at.desc())
            .limit(1)
        )
        prev = prev_result.scalar_one_or_none()
        old_text = prev.new_text if prev else None

        saved = SavedMessage(
            owner_id=owner.id,
            message_type=MessageType.EDITED,
            from_user_id=sender.id if sender else None,
            from_username=sender.username if sender else None,
            from_first_name=sender.first_name if sender else None,
            chat_id=message.chat.id if message.chat else None,
            message_id=message.message_id,
            business_connection_id=message.business_connection_id,
            original_text=old_text,
            new_text=new_text,
        )
        session.add(saved)
        await session.commit()

    notify_text = format_edited_notify(message, sender, old_text, new_text)
    try:
        await bot.send_message(owner.id, notify_text, parse_mode="HTML")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to notify {owner.id}: {e}")


# ── Исчезающие фото/видео ─────────────────────────────────────────────
@router.business_message(F.photo | F.video)
async def on_business_message_media(message: Message, bot: Bot):
    if not message.business_connection_id:
        return

    is_vanishing = getattr(message, "has_media_spoiler", False)
    if not is_vanishing:
        return

    owner = await get_owner_if_active(message.business_connection_id)
    if not owner:
        return

    sender = message.from_user
    media_file_id = None
    media_type = None

    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        media_file_id = message.video.file_id
        media_type = "video"

    async with AsyncSessionLocal() as session:
        saved = SavedMessage(
            owner_id=owner.id,
            message_type=MessageType.VANISHING_PHOTO,
            from_user_id=sender.id if sender else None,
            from_username=sender.username if sender else None,
            from_first_name=sender.first_name if sender else None,
            chat_id=message.chat.id if message.chat else None,
            message_id=message.message_id,
            business_connection_id=message.business_connection_id,
            media_file_id=media_file_id,
            media_type=media_type,
        )
        session.add(saved)
        await session.commit()

    sender_link = format_user_link(sender)
    try:
        await _send_media(
            bot, owner.id, media_file_id, media_type,
            f"📸 <b>Исчезающее фото</b> от {sender_link}",
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to notify {owner.id}: {e}")


async def _send_media(bot: Bot, chat_id: int, file_id: str, media_type: str, caption: str):
    if media_type == "photo":
        await bot.send_photo(chat_id, file_id, caption=caption, parse_mode="HTML")
    elif media_type == "video":
        await bot.send_video(chat_id, file_id, caption=caption, parse_mode="HTML")
    elif media_type == "voice":
        await bot.send_voice(chat_id, file_id, caption=caption, parse_mode="HTML")
    elif media_type == "video_note":
        await bot.send_video_note(chat_id, file_id)
    elif media_type == "sticker":
        await bot.send_sticker(chat_id, file_id)
    elif media_type == "document":
        await bot.send_document(chat_id, file_id, caption=caption, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, caption, parse_mode="HTML")
