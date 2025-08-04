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
            'Content-Type': 'application/json'
        })
    
    def get_current_user_tasks(self) -> List[Dict[Any, Any]]:
        """
        Получает задачи текущего пользователя из Planfix API
        """
        try:
            # Сначала получаем информацию о текущем пользователе
            current_user = self._get_current_user()
            if not current_user:
                print("❌ Не удалось получить информацию о текущем пользователе")
                return []
            
            user_id = current_user.get('id')
            print(f"👤 Получаем задачи для пользователя: {current_user.get('name', 'Unknown')} (ID: {user_id})")
            
            # Параметры для получения задач согласно документации Planfix API
            payload = {
                'token': self.api_token,
                'filters': {
                    'status': {
                        'type': 'select',
                        'value': ['1', '2']  # 1 = Новая, 2 = В работе (активные статусы)
                    },
                    'assignee': {
                        'type': 'user',
                        'value': [str(user_id)]  # Только задачи текущего пользователя
                    }
                },
                'fields': 'id,name,description,beginDate,endDate,status,priority,assignee,general'
            }
            
            response = self.session.post(
                f"{self.account_url}/task/",
                json=payload,
                timeout=30
            )
            
            print(f"🔍 Статус ответа API: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"📊 Получено данных: {len(str(data))} символов")
                
                # Обрабатываем ответ в зависимости от структуры Planfix API
                if 'tasks' in data:
                    tasks = data['tasks']
                elif isinstance(data, list):
                    tasks = data
                else:
                    print(f"⚠️  Неожиданная структура ответа: {list(data.keys())}")
                    tasks = []
                
                print(f"✅ Найдено задач: {len(tasks)}")
                return tasks
            else:
                print(f"❌ Ошибка API: {response.status_code}")
                print(f"📄 Ответ сервера: {response.text[:500]}")
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"🌐 Ошибка соединения с Planfix API: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"📄 Ошибка парсинга ответа API: {e}")
            return []
    
    def _get_current_user(self) -> Dict[Any, Any]:
        """
        Получает информацию о текущем пользователе
        """
        try:
            payload = {
                'token': self.api_token
            }
            
            response = self.session.post(
                f"{self.account_url}/user/",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                # В зависимости от API может возвращаться по-разному
                if 'user' in data:
                    return data['user']
                elif 'users' in data and len(data['users']) > 0:
                    return data['users'][0]  # Берем первого пользователя
                elif isinstance(data, dict) and 'id' in data:
                    return data
                else:
                    print(f"⚠️  Неожиданная структура пользователя: {data}")
                    return {'id': '1', 'name': 'Current User'}  # Fallback
            else:
                print(f"❌ Не удалось получить пользователя: {response.status_code}")
                return {'id': '1', 'name': 'Current User'}  # Fallback
                
        except Exception as e:
            print(f"❌ Ошибка получения пользователя: {e}")
            return {'id': '1', 'name': 'Current User'}  # Fallback
    
    def test_connection(self) -> bool:
        """
        Тестирует соединение с API
        """
        try:
            payload = {'token': self.api_token}
            response = self.session.post(
                f"{self.account_url}/user/",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                print("✅ Соединение с Planfix API успешно!")
                return True
            else:
                print(f"❌ Ошибка соединения: {response.status_code} - {response.text}")
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
        'overdue': [],      # Просроченные
        'urgent': [],       # Срочные (сегодня/завтра)
        'current': []       # Текущие
    }
    
    for task in tasks:
        try:
            # Парсим дату окончания задачи
            end_date_str = task.get('endDate', '')
            if not end_date_str:
                categorized['current'].append(task)
                continue
                
            # Предполагаем формат даты ISO 8601 или дату в формате YYYY-MM-DD
            if 'T' in end_date_str:
                end_date = datetime.datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).date()
            else:
                end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
            
            # Категоризуем задачи
            if end_date < today:
                categorized['overdue'].append(task)
            elif end_date <= tomorrow:
                categorized['urgent'].append(task)
            else:
                categorized['current'].append(task)
                
        except (ValueError, TypeError) as e:
            print(f"Ошибка парсинга даты для задачи {task.get('id', 'Unknown')}: {e}")
            categorized['current'].append(task)  # По умолчанию в текущие
    
    return categorized

def show_notification(title: str, message: str, urgency: str = 'normal'):
    """
    Отображает системное уведомление с учетом важности
    """
    try:
        # Настройки уведомления в зависимости от важности
        timeout = {
            'critical': 15,  # Критические - дольше показываем
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
    
    # Обрезаем описание если слишком длинное
    if len(description) > 100:
        description = description[:100] + "..."
    
    # Форматируем дату
    try:
        if end_date and end_date != 'Не указана':
            if 'T' in end_date:
                date_obj = datetime.datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime('%d.%m.%Y')
            else:
                date_obj = datetime.datetime.strptime(end_date, "%Y-%m-%d")
                formatted_date = date_obj.strftime('%d.%m.%Y')
        else:
            formatted_date = "Не указана"
    except:
        formatted_date = end_date
    
    # Заголовки в зависимости от категории
    title_prefix = {
        'overdue': '🔴 ПРОСРОЧЕНО',
        'urgent': '🟡 СРОЧНО',
        'current': '📋 ЗАДАЧА'
    }.get(category, '📋 ЗАДАЧА')
    
    title = f"{title_prefix}: {task_name}"
    
    message_parts = [f"📅 Срок: {formatted_date}"]
    if priority != 'Обычная':
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
    
    # Пробуем разные кодировки для чтения файла
    encodings_to_try = ['utf-8', 'cp1251', 'windows-1251', 'latin-1']
    
    for encoding in encodings_to_try:
        try:
            config.read(config_file_path, encoding=encoding)
            
            # Обязательные параметры
            api_token = config['Planfix']['api_token']
            account_url = config['Planfix']['account_url']
            
            # Опциональные параметры
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
                
            print(f"✅ Конфигурация загружена (кодировка: {encoding})")
            return api_token, account_url, check_interval, notification_settings
            
        except UnicodeDecodeError:
            continue  # Пробуем следующую кодировку
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
    
    # Загружаем конфигурацию
    api_token, account_url, check_interval, notification_settings = load_config()
    
    # Инициализируем API
    planfix = PlanfixAPI(account_url, api_token)
    
    print(f"⚙️  Настройки:")
    print(f"   - Интервал проверки: {check_interval} сек")
    print(f"   - URL аккаунта: {account_url}")
    print(f"   - Уведомления: {notification_settings}")
    
    # Тестируем соединение
    print("\n🔌 Тестирование соединения с Planfix...")
    if not planfix.test_connection():
        print("❌ Не удалось подключиться к Planfix API")
        print("💡 Проверьте:")
        print("   - Правильность API токена")
        print("   - URL аккаунта в config.ini")
        print("   - Интернет соединение")
        sys.exit(1)
    
    print(f"✅ Мониторинг запущен! (Ctrl+C для остановки)")
    
    notified_tasks = set()  # Отслеживаем уведомленные задачи
    
    while True:
        try:
            # Получаем задачи
            tasks = planfix.get_current_user_tasks()
            
            if not tasks:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📭 Активных задач не найдено")
                time.sleep(check_interval)
                continue
            
            # Категоризуем задачи
            categorized_tasks = categorize_tasks(tasks)
            
            # Показываем статистику
            stats = {k: len(v) for k, v in categorized_tasks.items()}
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📊 Задач: просрочено {stats['overdue']}, срочно {stats['urgent']}, текущие {stats['current']}")
            
            new_notifications = 0
            
            # Отправляем уведомления по категориям
            for category, tasks_list in categorized_tasks.items():
                if not notification_settings.get(category, True):
                    continue  # Пропускаем если уведомления отключены
                
                urgency_map = {
                    'overdue': 'critical',
                    'urgent': 'urgent', 
                    'current': 'normal'
                }
                
                for task in tasks_list:
                    task_id = task.get('id')
                    
                    # Проверяем, было ли уже уведомление
                    if task_id not in notified_tasks:
                        title, message = format_task_message(task, category)
                        show_notification(title, message, urgency_map[category])
                        
                        notified_tasks.add(task_id)
                        new_notifications += 1
                        
                        # Пауза между уведомлениями
                        time.sleep(1)
            
            if new_notifications == 0:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ Новых уведомлений нет")
            else:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📬 Отправлено {new_notifications} новых уведомлений")
            
            # Очищаем список уведомленных задач раз в час
            # (чтобы повторно уведомлять о критических задачах)
            if len(notified_tasks) > 50:  # Примерный лимит
                notified_tasks.clear()
                print("🔄 Сброс списка уведомленных задач")
            
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