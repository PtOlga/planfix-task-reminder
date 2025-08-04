import requests
import time
from plyer import notification
import datetime
import sys
import configparser
import os
import json
from typing import List, Dict, Any

# --- Конфигурация ---
CHECK_INTERVAL_SECONDS = 5 * 60  # 5 минут

class PlanfixAPI:
    def __init__(self, account_url: str, api_token: str):
        self.account_url = account_url.rstrip('/')
        self.api_token = api_token
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_token}'
        })
        self.user_id = None
        self.user_name = None

    def get_current_user_id(self) -> str:
        """
        Получает ID текущего пользователя по токену через /user/list
        """
        try:
            response = self.session.post(
                f"{self.account_url}/user/list",
                json={},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                users = data.get('users', [])
                # Обычно токен возвращает только одного пользователя
                if users:
                    self.user_id = users[0].get('id')
                    self.user_name = users[0].get('name', 'Unknown')
                    return self.user_id
                else:
                    print("❌ Не удалось найти пользователя в ответе /user/list")
                    return None
            else:
                print(f"❌ Ошибка получения списка пользователей: {response.status_code}")
                print(f"📄 Ответ сервера: {response.text[:500]}")
                return None
        except Exception as e:
            print(f"❌ Ошибка получения ID пользователя: {e}")
            return None

    def get_current_user_tasks(self) -> List[Dict[Any, Any]]:
        """
        Получает задачи текущего пользователя из Planfix API
        """
        if not self.user_id:
            self.get_current_user_id()
        if not self.user_id:
            print("❌ Не удалось получить ID пользователя. Невозможно отфильтровать задачи.")
            return []
        print(f"👤 Получаем задачи для пользователя: {self.user_name} (ID: {self.user_id})")
        try:
            payload = {
                'filters': [
                    {
                        'field': 'status',
                        'operator': 'in',
                        'value': ['1', '2']
                    },
                    {
                        'field': 'assignee',
                        'operator': 'eq',
                        'value': [str(self.user_id)]
                    }
                ],
                'fields': ['id', 'name', 'description', 'beginDate', 'endDate', 'status', 'priority', 'assignee', 'general']
            }
            response = self.session.post(
                f"{self.account_url}/task/list",
                json=payload,
                timeout=30
            )
            print(f"🔍 Статус ответа API: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if 'tasks' in data:
                    tasks = data['tasks']
                elif isinstance(data, list):
                    tasks = data
                else:
                    print(f"⚠️ Неожиданная структура ответа: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    tasks = []
                print(f"✅ Найдено задач: {len(tasks)}")
                return tasks
            else:
                print(f"❌ Ошибка API: {response.status_code}")
                print(f"📄 Ответ сервера: {response.text[:1000]}")
                return []
        except requests.exceptions.RequestException as e:
            print(f"🌐 Ошибка соединения с Planfix API: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"📄 Ошибка парсинга ответа API (неверный JSON): {e}")
            print(f"📄 Полученный текст: {response.text[:500]}")
            return []

    def test_connection(self) -> bool:
        """
        Тестирует соединение с API, пытаясь получить список сотрудников.
        """
        try:
            response = self.session.post(
                f"{self.account_url}/user/list",
                json={},
                timeout=10
            )
            if response.status_code == 200:
                print("✅ Соединение с Planfix API успешно!")
                return True
            else:
                print(f"❌ Ошибка соединения: {response.status_code} - {response.text[:500]}")
                return False
        except Exception as e:
            print(f"❌ Ошибка тестирования соединения: {e}")
            return False

def categorize_tasks(tasks: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Категоризует задачи на текущие, просроченные и срочные
    """
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    
    categorized = {
        'overdue': [],
        'urgent': [],
        'current': []
    }
    
    for task in tasks:
        try:
            end_date_str = task.get('endDate', '')
            if not end_date_str:
                categorized['current'].append(task)
                continue
            if 'T' in end_date_str:
                end_date = datetime.datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).date()
            else:
                end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date < today:
                categorized['overdue'].append(task)
            elif end_date <= tomorrow:
                categorized['urgent'].append(task)
            else:
                categorized['current'].append(task)
        except (ValueError, TypeError) as e:
            print(f"Ошибка парсинга даты '{task.get('endDate', '')}' для задачи {task.get('id', 'Unknown')}: {e}")
            categorized['current'].append(task)
    return categorized

def show_notification(title: str, message: str, urgency: str = 'normal'):
    """
    Отображает системное уведомление с учетом важности
    """
    try:
        timeout = {
            'critical': 15,
            'urgent': 12,
            'normal': 8
        }.get(urgency, 8)
        
        notification.notify(
            title=title,
            message=message,
            app_name="Planfix Reminder",
            timeout=timeout
        )
        
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📧 {urgency.upper()}: {title}")
        
    except Exception as e:
        print(f"❌ Ошибка уведомления: {e}")
        print("💡 Возможные решения:")
        print("   - pip install plyer")
        print("   - Для Linux: sudo apt-get install libnotify-bin")
        print("   - Для macOS: brew install terminal-notifier")

def format_task_message(task: Dict, category: str) -> tuple:
    """
    Форматирует сообщение для задачи
    """
    task_name = task.get('name', 'Задача без названия')
    description = task.get('description', '')
    end_date = task.get('endDate', 'Не указана')
    priority = task.get('priority', 'Обычная')
    
    if len(description) > 100:
        description = description[:100] + "..."
    
    formatted_date = "Не указана"
    if end_date and end_date != 'Не указана':
        try:
            if 'T' in end_date:
                date_obj = datetime.datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            else:
                date_obj = datetime.datetime.strptime(end_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime('%d.%m.%Y')
        except:
            formatted_date = end_date
    
    title_prefix = {
        'overdue': '🔴 ПРОСРОЧЕНО',
        'urgent': '🟡 СРОЧНО',
        'current': '📋 ЗАДАЧА'
    }.get(category, '📋 ЗАДАЧА')
    
    title = f"{title_prefix}: {task_name}"
    
    message_parts = [f"📅 Срок: {formatted_date}"]
    if priority and priority != 'Обычная':
        message_parts.append(f"⚡ Приоритет: {priority}")
    if description:
        message_parts.append(f"📝 {description}")
    
    message = "\n".join(message_parts)
    
    return title, message

def load_config() -> tuple:
    """
    Загружает конфигурацию из файла
    """
    config = configparser.ConfigParser()
    config_file_path = 'config.ini'
    
    if not os.path.exists(config_file_path):
        print("❌ Файл конфигурации 'config.ini' не найден!")
        print("📝 Создайте файл со следующим содержимым:")
        print("""
[Planfix]
api_token = ВАШ_API_ТОКЕН
account_url = https://ваш-аккаунт.planfix.com/rest

[Settings]
check_interval = 300
notify_current = true
notify_urgent = true
notify_overdue = true
        """.strip())
        sys.exit(1)
    
    encodings_to_try = ['utf-8', 'cp1251', 'windows-1251', 'latin-1']
    
    for encoding in encodings_to_try:
        try:
            config.read(config_file_path, encoding=encoding)
            api_token = config['Planfix']['api_token']
            account_url = config['Planfix']['account_url']
            check_interval = int(config.get('Settings', 'check_interval', fallback=300))
            notification_settings = {
                'current': config.getboolean('Settings', 'notify_current', fallback=True),
                'urgent': config.getboolean('Settings', 'notify_urgent', fallback=True),
                'overdue': config.getboolean('Settings', 'notify_overdue', fallback=True)
            }
            if not api_token or api_token in ['ВАШ_API_ТОКЕН', 'ВАШ_API_ТОКЕН_ЗДЕСЬ']:
                print("❌ API-токен не указан в config.ini")
                print("🔑 Получите токен в настройках Planfix и укажите его в конфиге")
                sys.exit(1)
            if not account_url.endswith('/rest'):
                print(f"⚠️ account_url '{account_url}' в config.ini должен заканчиваться на '/rest'.")
                print("   Пример: https://l-s.planfix.com/rest")
            print(f"✅ Конфигурация загружена (кодировка: {encoding})")
            return api_token, account_url, check_interval, notification_settings
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"❌ Ошибка чтения конфигурации с кодировкой {encoding}: {e}")
            continue
    print("❌ Не удалось прочитать config.ini ни с одной кодировкой")
    print("💡 Пересоздайте файл config.ini в кодировке UTF-8")
    sys.exit(1)

def main():
    """
    Основная функция программы
    """
    print("🚀 Запуск Planfix Reminder...")
    api_token, account_url, check_interval, notification_settings = load_config()
    planfix = PlanfixAPI(account_url, api_token)
    print(f"⚙️ Настройки:")
    print(f"   - Интервал проверки: {check_interval} сек")
    print(f"   - URL аккаунта: {account_url}")
    print(f"   - Уведомления: {notification_settings}")
    print("\n🔌 Тестирование соединения с Planfix...")
    if not planfix.test_connection():
        print("❌ Не удалось подключиться к Planfix API")
        print("💡 Проверьте:")
        print("   - Правильность API токена")
        print("   - URL аккаунта в config.ini (должен заканчиваться на /rest)")
        print("   - Интернет соединение")
        sys.exit(1)
    print(f"✅ Мониторинг запущен! (Ctrl+C для остановки)")
    notified_tasks = set()
    while True:
        try:
            tasks = planfix.get_current_user_tasks()
            if not tasks:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📭 Активных задач не найдено")
                time.sleep(check_interval)
                continue
            categorized_tasks = categorize_tasks(tasks)
            stats = {k: len(v) for k, v in categorized_tasks.items()}
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📊 Задач: просрочено {stats['overdue']}, срочно {stats['urgent']}, текущие {stats['current']}")
            new_notifications = 0
            for category, tasks_list in categorized_tasks.items():
                if not notification_settings.get(category, True):
                    continue
                urgency_map = {
                    'overdue': 'critical',
                    'urgent': 'urgent',
                    'current': 'normal'
                }
                for task in tasks_list:
                    task_id = task.get('id')
                    if task_id not in notified_tasks:
                        title, message = format_task_message(task, category)
                        show_notification(title, message, urgency_map[category])
                        notified_tasks.add(task_id)
                        new_notifications += 1
                        time.sleep(1)
            if datetime.datetime.now().hour != (datetime.datetime.now() - datetime.timedelta(seconds=check_interval)).hour:
                notified_tasks.clear()
                print("🔄 Сброс списка уведомленных задач (прошел час)")
            time.sleep(check_interval)
        except KeyboardInterrupt:
            print("\n👋 Planfix Reminder остановлен пользователем")
            break
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            print("⏳ Попытка перезапуска через 30 секунд...")
            time.sleep(30)

if __name__ == "__main__":
    main()