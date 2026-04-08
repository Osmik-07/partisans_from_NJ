from aiogram.types import Message, User


def format_user_link(user: User | None) -> str:
    if not user:
        return "<i>Неизвестный</i>"
    name = user.first_name or "?"
    if user.username:
        return f'<a href="tg://user?id={user.id}">{name}</a> (@{user.username})'
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def format_deleted_notify(msg: Message, sender: User | None) -> str:
    sender_link = format_user_link(sender)
    text = msg.text or msg.caption or ""

    lines = [f"🗑 <b>{sender_link} удалил(а) сообщение</b>\n"]

    if text:
        lines.append(f"<blockquote>{_escape(text)}</blockquote>")
    elif msg.photo:
        lines.append("📷 <i>[Фото]</i>")
    elif msg.video:
        lines.append("🎥 <i>[Видео]</i>")
    elif msg.voice:
        lines.append("🎤 <i>[Голосовое]</i>")
    elif msg.video_note:
        lines.append("⭕️ <i>[Видеосообщение]</i>")
    elif msg.sticker:
        lines.append(f"🎭 <i>[Стикер: {msg.sticker.emoji or ''}]</i>")
    elif msg.document:
        name = msg.document.file_name or "файл"
        lines.append(f"📎 <i>[Документ: {name}]</i>")
    else:
        lines.append("<i>[Медиа без текста]</i>")

    return "\n".join(lines)


def format_edited_notify(
    msg: Message,
    sender: User | None,
    old_text: str | None,
    new_text: str,
) -> str:
    sender_link = format_user_link(sender)
    lines = [f"✏️ <b>{sender_link} отредактировал(а) сообщение</b>\n"]

    if old_text:
        lines.append(f"<b>Было:</b>\n<blockquote>{_escape(old_text)}</blockquote>")
    else:
        lines.append("<b>Было:</b> <i>(не сохранено)</i>")

    lines.append(f"\n<b>Стало:</b>\n<blockquote>{_escape(new_text)}</blockquote>")
    return "\n".join(lines)


def _escape(text: str) -> str:
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
