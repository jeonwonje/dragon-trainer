import telegram
from telegram import InputMediaPhoto, InputMediaAudio, InputMediaDocument, InputMediaVideo
from telegram.ext import Filters
from sqlalchemy import or_, and_
from dracobot2.models import MessageMapping, MsgFrom
from dracobot2.resources import *
from .resources import *


SUPPORTED_MESSAGE_FILTERS = Filters.audio | Filters.document | Filters.photo | Filters.sticker | Filters.text | Filters.video | Filters.video_note | Filters.voice
UNSUPPORTED_MESSAGE_FILTERS = Filters.animation | Filters.contact | Filters.dice | Filters.game | Filters.invoice | Filters.location | Filters.passport_data | Filters.poll | Filters.successful_payment | Filters.venue


def get_highest_resolution(photos):
    return max(photos, key=lambda x: x.file_size)


def forward_message(message, chat_id, bot, session, message_from=MsgFrom.DRAGON):
    is_forward = message.forward_from is not None or message.forward_from_message_id is not None
    is_photo = len(message.photo) > 0
    is_document = message.document is not None
    is_video = message.video is not None
    is_audio = message.audio is not None
    is_voice = message.voice is not None
    is_sticker = message.sticker is not None
    is_video_note = message.video_note is not None

    caption = message.caption
    caption_msg = None
    caption_style_text = format_message(
        caption, message_from=message_from, is_prefix=False)

    reply_to_message_id = None
    if message.reply_to_message is not None:
        cur_reply_to_message_id = message.reply_to_message.message_id
        cur_reply_to_chat_id = message.reply_to_message.chat_id
        reply_message = session.query(MessageMapping).filter(or_(and_(MessageMapping.sender_message_id == cur_reply_to_message_id, MessageMapping.sender_chat_id == cur_reply_to_chat_id), and_(
            MessageMapping.receiver_message_id == cur_reply_to_message_id, MessageMapping.receiver_chat_id == cur_reply_to_chat_id))).first()
        if reply_message is not None:
            if reply_message.sender_message_id == cur_reply_to_message_id:
                reply_to_message_id = reply_message.receiver_message_id
            else:
                reply_to_message_id = reply_message.sender_message_id

    if is_forward:
        sent_msg = message.forward(chat_id)
        caption_msg = bot.send_message(
            chat_id=chat_id, text=caption_style_text, reply_to_message_id=sent_msg.message_id)
    elif is_photo:
        highest_res_photo = get_highest_resolution(message.photo)
        sent_msg = bot.send_photo(chat_id=chat_id, photo=highest_res_photo,
                                  caption=caption_style_text, reply_to_message_id=reply_to_message_id)
    elif is_document:
        sent_msg = bot.send_document(chat_id=chat_id, document=message.document,
                                     caption=caption_style_text, reply_to_message_id=reply_to_message_id)
    elif is_video:
        sent_msg = bot.send_video(chat_id=chat_id, video=message.video,
                                  caption=caption_style_text, reply_to_message_id=reply_to_message_id)
    elif is_audio:
        sent_msg = bot.send_audio(chat_id=chat_id, audio=message.audio,
                                  caption=caption_style_text, reply_to_message_id=reply_to_message_id)
    elif is_voice:
        sent_msg = bot.send_voice(chat_id=chat_id, voice=message.voice,
                                  caption=caption_style_text, reply_to_message_id=reply_to_message_id)
    elif is_sticker:
        sent_msg = bot.send_sticker(
            chat_id=chat_id, sticker=message.sticker, reply_to_message_id=reply_to_message_id)
        caption_msg = bot.send_message(
            chat_id=chat_id, text=caption_style_text, reply_to_message_id=sent_msg.message_id)
    elif is_video_note:
        sent_msg = bot.send_video_note(
            chat_id=chat_id, video_note=message.video_note, reply_to_message_id=reply_to_message_id)
        caption_msg = bot.send_message(
            chat_id=chat_id, text=caption_style_text, reply_to_message_id=sent_msg.message_id)
    else:
        sent_msg = bot.send_message(chat_id=chat_id, text=format_message(
            message.text, message_from=message_from, is_prefix=True), reply_to_message_id=reply_to_message_id)

    mapping = MessageMapping(sender_message_id=message.message_id, sender_chat_id=message.chat_id,
                             receiver_message_id=sent_msg.message_id, receiver_chat_id=sent_msg.chat_id, message_from=message_from)
    if caption_msg is not None:
        mapping.receiver_caption_message_id = caption_msg.message_id
    session.add(mapping)
    session.commit()

# Must be used together with db_session


def handle_edited_message(func):
    def handle_edited_message_decorator(update, context, session):
        if update.edited_message is not None:
            edited_message = update.edited_message
            message_id = edited_message.message_id
            chat_id = edited_message.chat_id
            edited_messages_db = session.query(MessageMapping).filter(and_(
                MessageMapping.sender_message_id == message_id, MessageMapping.sender_chat_id == chat_id, MessageMapping.deleted == False)).all()

            is_photo = len(edited_message.photo) > 0
            is_document = edited_message.document is not None
            is_video = edited_message.video is not None
            is_audio = edited_message.audio is not None

            if edited_messages_db and len(edited_messages_db) > 0:
                if is_photo or is_document or is_video or is_audio:
                    if is_photo:
                        edited_media = InputMediaPhoto(
                            media=get_highest_resolution(edited_message.photo))
                    elif is_document:
                        edited_media = InputMediaDocument(
                            media=edited_message.document)
                    elif is_video:
                        edited_media = InputMediaVideo(
                            media=edited_message.video)
                    elif is_audio:
                        edited_media = InputMediaAudio(
                            media=edited_message.audio)

                    for edited_message_db in edited_messages_db:
                        try:
                            context.bot.edit_message_media(
                                media=edited_media, chat_id=edited_message_db.receiver_chat_id, message_id=edited_message_db.receiver_message_id)
                        except telegram.error.BadRequest as e:
                            print(e)
                            pass

                if edited_message.text:
                    for edited_message_db in edited_messages_db:
                        formatted_text = format_message(
                            edited_message.text, message_from=edited_message_db.message_from, is_prefix=True, is_edited=True)

                        try:
                            context.bot.edit_message_text(
                                formatted_text, chat_id=edited_message_db.receiver_chat_id, message_id=edited_message_db.receiver_message_id)
                        except telegram.error.BadRequest as e:
                            print(e)
                            pass
                elif edited_message.caption:
                    for edited_message_db in edited_messages_db:
                        formatted_caption = format_message(
                            edited_message.caption, message_from=edited_message_db.message_from, is_prefix=False, is_edited=True)

                        try:
                            context.bot.edit_message_caption(
                                caption=formatted_caption, chat_id=edited_message_db.receiver_chat_id, message_id=edited_message_db.receiver_message_id)
                        except telegram.error.BadRequest as e:
                            print(e)
                            pass
            return
        else:
            return func(update, context, session)
    return handle_edited_message_decorator


def delete_message(message, message_id, chat_id, reply_to_message_id, bot, session):
    to_delete_messages = session.query(MessageMapping).filter(
        MessageMapping.sender_message_id == message_id, MessageMapping.sender_chat_id == chat_id).all()

    if not (to_delete_messages and len(to_delete_messages) > 0):
        message.reply_text(CANNOT_DELETE_ERROR,
                           reply_to_message_id=reply_to_message_id)
    elif to_delete_messages[0].deleted:
        message.reply_text(DELETE_MESSAGE_ERROR,
                           reply_to_message_id=reply_to_message_id)
    else:
        for to_delete_message in to_delete_messages:
            bot.delete_message(chat_id=to_delete_message.receiver_chat_id,
                               message_id=to_delete_message.receiver_message_id)
            if to_delete_message.receiver_caption_message_id:
                bot.delete_message(chat_id=to_delete_message.receiver_chat_id,
                                   message_id=to_delete_message.receiver_caption_message_id)
            to_delete_message.deleted = True
        session.commit()
        message.reply_text(DELETE_MESSAGE_SUCCESS,
                           reply_to_message_id=reply_to_message_id)


def delete_message_reply(message, bot, session):
    is_replying = message.reply_to_message is not None
    if is_replying:
        message_id = message.reply_to_message.message_id
        chat_id = message.reply_to_message.chat_id
        delete_message(message, message_id, chat_id, message_id, bot, session)
    else:
        message.reply_text(DELETE_MESSAGE_REPLY_ERROR)
