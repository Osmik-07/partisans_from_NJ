from datetime import datetime, timezone
import logging

from aiogram import Router, Bot
from aiogram.types import BusinessMessagesDeleted, Message, BusinessConnection
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.base import AsyncSessionLocal
from db.models import User, Subscription, SavedMessage, MessageType

router = Router()
logger = logging.getLogger(__name__)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# 🔥 ВАЖНО: расширили поддержку медиа
def _extract_media(message: Message):
    if message.photo:
        return message.photo[-1].file_id, "photo"
    if message.video:
        return message.video.file_id, "video"
    if message.animation:
        return message.animation.file_id, "animation"
    if message.audio:
        return message.audio.file_id, "audio"
    if message.voice:
        return message.voice.file_id, "voice"
    if message.video_note:
        return message.video_note.file_id, "video_note"
    if message.sticker:
        return message.sticker.file_id, "sticker"
    if message.document:
        return message.document.file_id, "document"
    return None, None


def _format_deleted_from_cache(snapshot: SavedMessage) -> str:
    sender_name = snapshot.from_first_name or "Неизвестный"
    if snapshot.from_username:
        sender_name = f"{sender_name} (@{snapshot.from_username})"

    lines = [f"🗑 <b>{_escape(sender_name)} удалил(а) сообщение</b>\n"]

    if snapshot.original_text:
        lines.append(f"<blockquote>{_escape(snapshot.original_text)}</blockquote>")
    elif snapshot.media_type == "photo":
        lines.append("📷 <i>[Фото]</i>")
    elif snapshot.media_type == "video":
        lines.append("🎥 <i>[Видео]</i>")
    elif snapshot.media_type == "animation":
        lines.append("🎞 <i>[GIF]</i>")
    elif snapshot.media_type == "audio":
        lines.append("🎧 <i>[Аудио]</i>")
    elif snapshot.media_type == "voice":
        lines.append("🎤 <i>[Голосовое]</i>")
    elif snapshot.media_type == "video_note":
        lines.append("⭕️ <i>[Видеосообщение]</i>")
    elif snapshot.media_type == "sticker":
        lines.append("🎭 <i>[Стикер]</i>")
    elif snapshot.media_type == "document":
        lines.append("📎 <i>[Документ]</i>")
    else:
        lines.append("<i>[Медиа без текста]</i>")

    return "\n".join(lines)


async def _get_owner_if_active(business_connection_id: str) -> User | None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User)
            .options(selectinload(User.subscriptions))
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                User.business_connection_id == business_connection_id,
                Subscription.is_active == True,
                Subscription.expires_at > now,
            )
        )
        return result.scalar_one_or_none()


async def _get_snapshot(session, owner_id: int, message_id: int) -> SavedMessage | None:
    result = await session.execute(
        select(SavedMessage)
        .where(
            SavedMessage.owner_id == owner_id,
            SavedMessage.message_id == message_id,
        )
        .order_by(SavedMessage.event_at.asc())
    )
    rows = result.scalars().all()
    if not rows:
        return None

    for row in rows:
        if row.extra_data and row.extra_data.get("snapshot"):
            return row

    return rows[0]


async def _send_media(bot: Bot, chat_id: int, file_id: str, media_type: str, caption: str):
    if media_type == "photo":
        await bot.send_photo(chat_id, file_id, caption=caption, parse_mode="HTML")
    elif media_type == "video":
        await bot.send_video(chat_id, file_id, caption=caption, parse_mode="HTML")
    elif media_type == "animation":
        await bot.send_animation(chat_id, file_id, caption=caption, parse_mode="HTML")
    elif media_type == "audio":
        await bot.send_audio(chat_id, file_id, caption=caption, parse_mode="HTML")
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


# ── Подключение бизнеса ─────────────────────────
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
        else:
            user.business_connection_id = None
            await session.commit()


# ── КЕШ ─────────────────────────
@router.business_message()
async def on_business_message(message: Message):
    if not message.business_connection_id:
        return

    owner = await _get_owner_if_active(message.business_connection_id)
    if not owner:
        return

    sender = message.from_user
    text = message.text or message.caption or ""

    # 🔥 DEBUG (очень важно сейчас)
    logger.info(
        "MSG id=%s photo=%s video=%s animation=%s audio=%s doc=%s voice=%s video_note=%s spoiler=%s",
        message.message_id,
        bool(message.photo),
        bool(message.video),
        bool(message.animation),
        bool(message.audio),
        bool(message.document),
        bool(message.voice),
        bool(message.video_note),
        getattr(message, "has_media_spoiler", None),
    )

    media_file_id, media_type = _extract_media(message)

    async with AsyncSessionLocal() as session:
        snapshot = SavedMessage(
            owner_id=owner.id,
            message_type=MessageType.DELETED,
            from_user_id=sender.id if sender else None,
            from_username=sender.username if sender else None,
            from_first_name=sender.first_name if sender else None,
            chat_id=message.chat.id if message.chat else None,
            message_id=message.message_id,
            business_connection_id=message.business_connection_id,
            original_text=text,
            media_file_id=media_file_id,
            media_type=media_type,
            extra_data={"snapshot": True},
        )
        session.add(snapshot)
        await session.commit()


# ── Удалённые ─────────────────────────
@router.deleted_business_messages()
async def on_deleted_messages(event: BusinessMessagesDeleted, bot: Bot):
    owner = await _get_owner_if_active(event.business_connection_id)
    if not owner:
        return

    async with AsyncSessionLocal() as session:
        for message_id in event.message_ids:
            snapshot = await _get_snapshot(session, owner.id, message_id)
            if not snapshot:
                continue

            text = _format_deleted_from_cache(snapshot)

            if snapshot.media_file_id:
                await _send_media(
                    bot,
                    owner.id,
                    snapshot.media_file_id,
                    snapshot.media_type,
                    text,
                )
            else:
                await bot.send_message(owner.id, text, parse_mode="HTML")

        await session.commit()


# ── Редактирование ─────────────────────────
@router.edited_business_message()
async def on_edited_message(message: Message, bot: Bot):
    owner = await _get_owner_if_active(message.business_connection_id)
    if not owner:
        return

    new_text = message.text or message.caption or ""
    sender = message.from_user

    async with AsyncSessionLocal() as session:
        snapshot = await _get_snapshot(session, owner.id, message.message_id)
        old_text = snapshot.original_text if snapshot else None

    notify = (
        f"✏️ <b>{_escape(sender.first_name)} изменил(а) сообщение</b>\n\n"
        f"Было:\n{_escape(old_text or 'не сохранено')}\n\n"
        f"Стало:\n{_escape(new_text)}"
    )

    await bot.send_message(owner.id, notify, parse_mode="HTML")