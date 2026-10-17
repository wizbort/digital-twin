import json
import re
from telethon import TelegramClient
from datetime import datetime, timezone

# Вставьте свои данные
api_id = YOUR_API_ID  # Замените на ваш API ID
api_hash = 'YOUR_API_HASH'  # Замените на ваш API Hash
session_name = 'session'  # Имя файла сессии

# Инициализация клиента
client = TelegramClient(session_name, api_id, api_hash)

# Файлы для сохранения
my_messages_file = "my_messages.txt"
all_messages_file = "all_messages.txt"
progress_file = "progress.json"

# Дата фильтрации
filter_date = datetime(2022, 1, 1, tzinfo=timezone.utc)

def append_to_file(filename, message):
    with open(filename, "a", encoding="utf-8") as file:
        file.write(message + "\n")

def load_progress():
    try:
        with open(progress_file, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_progress(progress):
    with open(progress_file, "w", encoding="utf-8") as file:
        json.dump(progress, file, ensure_ascii=False, indent=4)

def filter_message(message_text, message_date):
    if re.search(r'http[s]?://\S+', message_text) or re.search(r'tg://\S+', message_text):
        return False
    if "@" in message_text:
        return False
    if re.match(r'\w{10,}', message_text):
        return False
    blocked_patterns = [
        r"^Wizbort",
        r"^Файлы",
        r"^Документы"
    ]
    for pattern in blocked_patterns:
        if re.search(pattern, message_text):
            return False
    if message_date < filter_date:
        return False
    return True

async def main():
    progress = load_progress()
    my_id = (await client.get_me()).id  # Важный исправленный момент
    
    print("Начинаем сбор сообщений...")

    # Сбор ваших сообщений
    async for dialog in client.iter_dialogs():
        dialog_id = str(dialog.id)
        if dialog_id not in progress:
            progress[dialog_id] = {"my_messages_offset_id": 0, "all_messages_offset_id": 0}

        if not dialog.is_user and not dialog.is_group:
            continue

        offset_id = progress[dialog_id]["my_messages_offset_id"]
        async for message in client.iter_messages(dialog.id, from_user='me', reverse=True, offset_id=offset_id):
            if message.text and filter_message(message.text, message.date):
                formatted_message = f"[{dialog.title}] {message.date}: {message.text}"
                append_to_file(my_messages_file, formatted_message)
                progress[dialog_id]["my_messages_offset_id"] = message.id
        save_progress(progress)

    print(f"Ваши сообщения сохранены в: {my_messages_file}")

    # Сбор всех сообщений
    async for dialog in client.iter_dialogs():
        dialog_id = str(dialog.id)

        if not dialog.is_user and not dialog.is_group:
            continue

        offset_id = progress[dialog_id]["all_messages_offset_id"]
        async for message in client.iter_messages(dialog.id, reverse=True, offset_id=offset_id):
            if message.text and filter_message(message.text, message.date):
                # Исправленное определение отправителя
                sender = "Вы" if message.sender_id == my_id else "Собеседник"
                formatted_message = f"[{dialog.title}] {sender} ({message.date}): {message.text}"
                append_to_file(all_messages_file, formatted_message)
                progress[dialog_id]["all_messages_offset_id"] = message.id
        save_progress(progress)

    print(f"Все сообщения сохранены в: {all_messages_file}")

with client:
    client.loop.run_until_complete(main())