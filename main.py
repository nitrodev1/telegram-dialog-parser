import asyncio
import json
import os
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import User, Chat, Channel

# config file
API_ID = 'YOUR_API_ID'
API_HASH = 'YOUR_API_HASH'
SESSION_NAME = 'account'

class TelegramDialogExporter:
    def __init__(self):
        self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        self.me = None
        
    async def authenticate(self):
        print("Подключение к Telegram...")
        await self.client.start()
        
        if not await self.client.is_user_authorized():
            print("Необходима авторизация")
            phone = input("Введите номер телефона (с кодом страны): ")
            await self.client.send_code_request(phone)
            
            try:
                code = input("Введите код подтверждения: ")
                await self.client.sign_in(phone, code)
            except SessionPasswordNeededError:
                password = input("Введите пароль двухфакторной аутентификации: ")
                await self.client.sign_in(password=password)
        
        self.me = await self.client.get_me()
        print(f"✅ Авторизация успешна! Вы: {self.me.first_name} {self.me.last_name or ''}")
        
    async def get_private_dialogs(self):
        print("\n📋 Загрузка личных диалогов...")
        dialogs = await self.client.get_dialogs()
        
        private_dialogs = []
        for i, dialog in enumerate(dialogs):
            if isinstance(dialog.entity, User) and not dialog.entity.bot:
                dialog_info = {
                    'number': len(private_dialogs) + 1,
                    'entity': dialog.entity,
                    'name': self.get_user_display_name(dialog.entity),
                    'username': dialog.entity.username,
                    'user_id': dialog.entity.id,
                    'last_message_date': dialog.date,
                    'unread_count': dialog.unread_count
                }
                private_dialogs.append(dialog_info)
        
        return private_dialogs
    
    def get_user_display_name(self, user):
        if user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        elif user.first_name:
            return user.first_name
        elif user.username:
            return f"@{user.username}"
        else:
            return f"User {user.id}"
    
    def display_dialogs(self, dialogs):
        print("\n" + "="*80)
        print("ЛИЧНЫЕ ДИАЛОГИ")
        print("="*80)
        
        for dialog in dialogs:
            username_info = f"@{dialog['username']}" if dialog['username'] else "нет username"
            last_date = dialog['last_message_date'].strftime('%Y-%m-%d %H:%M')
            unread_info = f"({dialog['unread_count']} непрочитанных)" if dialog['unread_count'] > 0 else ""
            
            print(f"{dialog['number']:3d}. {dialog['name'][:35]:<35} | {username_info:<20} | {last_date} {unread_info}")
        
        print("="*80)
    
    async def export_dialog(self, user_entity):
        user_name = self.get_user_display_name(user_entity)
        print(f"\n📥 Экспорт диалога с: {user_name}")
        print("🔄 Загрузка сообщений...")
        
        messages_data = []
        message_count = 0
        
        try:
            async for message in self.client.iter_messages(user_entity):
                message_count += 1
                
                is_from_me = message.from_id and message.from_id.user_id == self.me.id
                sender_name = self.get_user_display_name(self.me) if is_from_me else user_name
                
                message_info = {
                    'id': message.id,
                    'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                    'date_timestamp': message.date.timestamp(),
                    'from_me': is_from_me,
                    'sender_name': sender_name,
                    'text': message.text or '',
                    'media_type': str(type(message.media).__name__) if message.media else None,
                    'media_caption': getattr(message.media, 'caption', '') if message.media else '',
                    'reply_to': message.reply_to_msg_id if message.reply_to else None,
                    'forward_from': None,
                    'edit_date': message.edit_date.strftime('%Y-%m-%d %H:%M:%S') if message.edit_date else None,
                    'file_name': None,
                    'file_size': None
                }
                
                if message.media and hasattr(message.media, 'document'):
                    doc = message.media.document
                    if hasattr(doc, 'attributes'):
                        for attr in doc.attributes:
                            if hasattr(attr, 'file_name'):
                                message_info['file_name'] = attr.file_name
                                break
                    message_info['file_size'] = getattr(doc, 'size', None)
                
                if message.forward:
                    forward_info = {}
                    if hasattr(message.forward, 'from_name'):
                        forward_info['from_name'] = message.forward.from_name
                    if hasattr(message.forward, 'date'):
                        forward_info['date'] = message.forward.date.strftime('%Y-%m-%d %H:%M:%S')
                    message_info['forward_from'] = forward_info
                
                messages_data.append(message_info)
                
                if message_count % 500 == 0:
                    print(f"📊 Загружено сообщений: {message_count}")
        
        except Exception as e:
            print(f"❌ Ошибка при загрузке сообщений: {e}")
            return None
        
        messages_data.sort(key=lambda x: x['date_timestamp'])
        
        print(f"✅ Всего загружено сообщений: {message_count}")
        
        return {
            'export_info': {
                'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_messages': message_count,
                'dialog_participants': [
                    {
                        'name': self.get_user_display_name(self.me),
                        'username': self.me.username,
                        'user_id': self.me.id,
                        'is_me': True
                    },
                    {
                        'name': user_name,
                        'username': user_entity.username,
                        'user_id': user_entity.id,
                        'is_me': False
                    }
                ]
            },
            'messages': messages_data
        }
    
    def save_to_json(self, data, filename=None):
        if not filename:
            other_user = next(p for p in data['export_info']['dialog_participants'] if not p['is_me'])
            user_name = other_user['username'] or f"user_{other_user['user_id']}"
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"dialog_{user_name}_{timestamp}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 Диалог сохранен в JSON: {filename}")
            return filename
        except Exception as e:
            print(f"❌ Ошибка сохранения JSON: {e}")
            return None
    
    def create_html_page(self, data, json_filename):
        other_user = next(p for p in data['export_info']['dialog_participants'] if not p['is_me'])
        me_user = next(p for p in data['export_info']['dialog_participants'] if p['is_me'])
        
        html_filename = json_filename.replace('.json', '.html')
        
        html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Диалог с {other_user['name']}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white;
            padding: 25px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        
        .header .info {{
            opacity: 0.9;
            font-size: 14px;
        }}
        
        .stats {{
            background: #f8f9fa;
            padding: 20px;
            border-bottom: 1px solid #e9ecef;
            display: flex;
            justify-content: space-around;
            text-align: center;
        }}
        
        .stat-item {{
            flex: 1;
        }}
        
        .stat-number {{
            font-size: 24px;
            font-weight: bold;
            color: #4facfe;
        }}
        
        .stat-label {{
            font-size: 12px;
            color: #6c757d;
            text-transform: uppercase;
        }}
        
        .messages {{
            height: 60vh;
            overflow-y: auto;
            padding: 20px;
            background: #f8f9fa;
        }}
        
        .message {{
            margin-bottom: 15px;
            display: flex;
            animation: fadeIn 0.3s ease-in;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .message.from-me {{
            justify-content: flex-end;
        }}
        
        .message.from-other {{
            justify-content: flex-start;
        }}
        
        .message-bubble {{
            max-width: 70%;
            padding: 12px 16px;
            border-radius: 18px;
            word-wrap: break-word;
            position: relative;
        }}
        
        .message.from-me .message-bubble {{
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white;
            border-bottom-right-radius: 4px;
        }}
        
        .message.from-other .message-bubble {{
            background: white;
            color: #333;
            border: 1px solid #e9ecef;
            border-bottom-left-radius: 4px;
        }}
        
        .message-text {{
            line-height: 1.4;
            margin-bottom: 5px;
        }}
        
        .message-meta {{
            font-size: 11px;
            opacity: 0.7;
            text-align: right;
        }}
        
        .message.from-other .message-meta {{
            color: #6c757d;
        }}
        
        .media-info {{
            font-style: italic;
            color: #6c757d;
            font-size: 12px;
            margin-bottom: 5px;
        }}
        
        .forward-info {{
            font-size: 12px;
            opacity: 0.8;
            margin-bottom: 5px;
            padding: 5px;
            background: rgba(255,255,255,0.1);
            border-radius: 5px;
        }}
        
        .date-separator {{
            text-align: center;
            margin: 30px 0 20px 0;
            position: relative;
        }}
        
        .date-separator::before {{
            content: '';
            position: absolute;
            top: 50%;
            left: 0;
            right: 0;
            height: 1px;
            background: #dee2e6;
        }}
        
        .date-separator span {{
            background: #f8f9fa;
            padding: 5px 15px;
            color: #6c757d;
            font-size: 12px;
            font-weight: bold;
        }}
        
        .search-box {{
            padding: 15px 20px;
            border-bottom: 1px solid #e9ecef;
            background: white;
        }}
        
        .search-input {{
            width: 100%;
            padding: 10px 15px;
            border: 2px solid #e9ecef;
            border-radius: 25px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.3s;
        }}
        
        .search-input:focus {{
            border-color: #4facfe;
        }}
        
        .highlight {{
            background: yellow;
            padding: 2px 4px;
            border-radius: 3px;
        }}
        
        ::-webkit-scrollbar {{
            width: 6px;
        }}
        
        ::-webkit-scrollbar-track {{
            background: #f1f1f1;
        }}
        
        ::-webkit-scrollbar-thumb {{
            background: #4facfe;
            border-radius: 3px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💬 Диалог с {other_user['name']}</h1>
            <div class="info">
                Экспортировано: {data['export_info']['exported_at']} | 
                Участники: {me_user['name']} ↔ {other_user['name']}
            </div>
        </div>
        
        <div class="stats">
            <div class="stat-item">
                <div class="stat-number">{data['export_info']['total_messages']}</div>
                <div class="stat-label">Сообщений</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{len([m for m in data['messages'] if m['from_me']])}</div>
                <div class="stat-label">От меня</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{len([m for m in data['messages'] if not m['from_me']])}</div>
                <div class="stat-label">От собеседника</div>
            </div>
        </div>
        
        <div class="search-box">
            <input type="text" class="search-input" placeholder="🔍 Поиск по сообщениям..." id="searchInput">
        </div>
        
        <div class="messages" id="messagesContainer">
"""
        
        current_date = None
        for message in data['messages']:
            message_date = datetime.strptime(message['date'], '%Y-%m-%d %H:%M:%S').date()
            
            if current_date != message_date:
                current_date = message_date
                date_str = current_date.strftime('%d %B %Y')
                months = {
                    'January': 'января', 'February': 'февраля', 'March': 'марта',
                    'April': 'апреля', 'May': 'мая', 'June': 'июня',
                    'July': 'июля', 'August': 'августа', 'September': 'сентября',
                    'October': 'октября', 'November': 'ноября', 'December': 'декабря'
                }
                for eng, rus in months.items():
                    date_str = date_str.replace(eng, rus)
                
                html_content += f'''
            <div class="date-separator">
                <span>{date_str}</span>
            </div>
'''
            
            message_text = message['text'].replace('<', '&lt;').replace('>', '&gt;')
            message_text = message_text.replace('\n', '<br>')
            
            time_str = datetime.strptime(message['date'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M')
            
            message_class = 'from-me' if message['from_me'] else 'from-other'
            
            media_info = ''
            if message['media_type'] and message['media_type'] != 'NoneType':
                media_type_names = {
                    'MessageMediaPhoto': '📷 Фото',
                    'MessageMediaDocument': '📎 Файл',
                    'MessageMediaVideo': '🎥 Видео',
                    'MessageMediaAudio': '🎵 Аудио',
                    'MessageMediaVoice': '🎤 Голосовое сообщение',
                    'MessageMediaSticker': '🏷 Стикер',
                    'MessageMediaGif': '🎬 GIF'
                }
                media_name = media_type_names.get(message['media_type'], message['media_type'])
                if message['file_name']:
                    media_info = f'<div class="media-info">{media_name}: {message["file_name"]}</div>'
                else:
                    media_info = f'<div class="media-info">{media_name}</div>'
            
            forward_info = ''
            if message['forward_from']:
                forward_info = '<div class="forward-info">📤 Переслано</div>'
            
            html_content += f'''
            <div class="message {message_class}" data-text="{message_text.lower()}">
                <div class="message-bubble">
                    {forward_info}
                    {media_info}
                    <div class="message-text">{message_text}</div>
                    <div class="message-meta">{time_str}</div>
                </div>
            </div>
'''
        
        html_content += '''
        </div>
    </div>
    
    <script>
        const searchInput = document.getElementById('searchInput');
        const messagesContainer = document.getElementById('messagesContainer');
        
        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const messages = messagesContainer.querySelectorAll('.message');
            
            messages.forEach(message => {
                const text = message.getAttribute('data-text');
                if (searchTerm === '' || text.includes(searchTerm)) {
                    message.style.display = 'flex';
                    
                    if (searchTerm !== '') {
                        const messageText = message.querySelector('.message-text');
                        let html = messageText.innerHTML;
                        
                        html = html.replace(/<span class="highlight">(.*?)<\\/span>/gi, '$1');
                        
                        if (searchTerm.length > 0) {
                            const regex = new RegExp(`(${searchTerm})`, 'gi');
                            html = html.replace(regex, '<span class="highlight">$1</span>');
                        }
                        
                        messageText.innerHTML = html;
                    }
                } else {
                    message.style.display = 'none';
                }
            });
        });
        
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    </script>
</body>
</html>'''
        
        try:
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"🌐 HTML страница создана: {html_filename}")
            return html_filename
        except Exception as e:
            print(f"❌ Ошибка создания HTML: {e}")
            return None
    
    async def run(self):
        try:
            await self.authenticate()
            
            while True:
                dialogs = await self.get_private_dialogs()
                
                if not dialogs:
                    print("❌ Личные диалоги не найдены!")
                    break
                
                self.display_dialogs(dialogs)
                
                try:
                    choice = input("\nВведите номер диалога (или 'exit' для выхода): ").strip()
                    if choice.lower() == 'exit':
                        break
                    
                    dialog_number = int(choice)
                    if 1 <= dialog_number <= len(dialogs):
                        selected_dialog = dialogs[dialog_number - 1]
                        print(f"\n✅ Выбран диалог с: {selected_dialog['name']}")
                    else:
                        print("❌ Неверный номер диалога!")
                        continue
                        
                except ValueError:
                    print("❌ Введите корректный номер!")
                    continue
                
                print("\n🚀 Начинаем экспорт диалога...")
                dialog_data = await self.export_dialog(selected_dialog['entity'])
                
                if dialog_data:
                    json_filename = self.save_to_json(dialog_data)
                    
                    if json_filename:
                        html_filename = self.create_html_page(dialog_data, json_filename)
                        
                        print(f"\n📊 ЭКСПОРТ ЗАВЕРШЕН:")
                        print(f"   Диалог с: {selected_dialog['name']}")
                        print(f"   Сообщений: {dialog_data['export_info']['total_messages']}")
                        print(f"   JSON файл: {json_filename}")
                        if html_filename:
                            print(f"   HTML страница: {html_filename}")
                            print(f"   🌐 Откройте {html_filename} в браузере для просмотра")
                
                continue_choice = input("\nЭкспортировать еще один диалог? (y/n): ").strip().lower()
                if continue_choice != 'y':
                    break
                    
        except KeyboardInterrupt:
            print("\n\n❌ Работа прервана пользователем")
        except Exception as e:
            print(f"\n❌ Неожиданная ошибка: {e}")
        finally:
            await self.client.disconnect()
            print("👋 Отключение от Telegram")

async def main():
    print("🚀 TELEGRAM DIALOG EXPORTER")
    print("="*50)
    
    if API_ID == 'YOUR_API_ID' or API_HASH == 'YOUR_API_HASH':
        print("❌ ОШИБКА: Необходимо указать API_ID и API_HASH!")
        print("Получите их на https://my.telegram.org")
        print("Отредактируйте переменные в начале скрипта")
        return
    
    exporter = TelegramDialogExporter()
    await exporter.run()

if __name__ == "__main__":
    asyncio.run(main())
