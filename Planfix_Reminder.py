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
            payload = {
                'offset': 0,
                'pageSize': 100,
                'fields': 'id,name,midname,lastname'
            }
            response = self.session.post(
                f"{self.account_url}/user/list",
                json=payload,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                users = data.get('users', [])
                if users:
                    self.user_id = users[0].get('id')
                    self.user_name = users[0].get('name', 'Unknown')
                    print(f"✅ Найден пользователь: {self.user_name} (ID: {self.user_id})")
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
        Получает задачи связанные с текущим пользователем из Planfix API
        Включает задачи где пользователь является исполнителем, постановщиком или контролером
        """
        # Получаем ID пользователя для информации
        if not self.user_id:
            self.get_current_user_id()
        
        print(f"👤 Пользователь: {self.user_name} (ID: {self.user_id})")
        print("📋 Получаем задачи где пользователь - исполнитель, постановщик или контролер")
        
        try:
            # Получаем задачи с различными фильтрами для разных ролей пользователя
            all_user_tasks = []
            
            # Фильтры для разных ролей
            filter_configs = [
                {
                    "name": "Исполнитель",
                    "filters": [
                        {
                            "type": 2,  # Фильтр по исполнителю
                            "operator": "equal",
                            "value": f"user:{self.user_id}"
                        }
                    ]
                },
                {
                    "name": "Постановщик", 
                    "filters": [
                        {
                            "type": 3,  # Фильтр по постановщику
                            "operator": "equal",
                            "value": f"user:{self.user_id}"
                        }
                    ]
                },
                {
                    "name": "Контролер/Участник",
                    "filters": [
                        {
                            "type": 4,  # Фильтр по участникам/контролерам
                            "operator": "equal", 
                            "value": f"user:{self.user_id}"
                        }
                    ]
                }
            ]
            
            task_ids_seen = set()  # Избегаем дублирования задач
            
            for config in filter_configs:
                try:
                    payload = {
                        "offset": 0,
                        "pageSize": 100,
                        "filters": config["filters"],
                        "fields": "id,name,description,endDateTime,startDateTime,status,priority,assignees,participants,auditors,assigner,overdue"
                    }
                    
                    response = self.session.post(
                        f"{self.account_url}/task/list",
                        json=payload,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('result') != 'fail':
                            tasks = data.get('tasks', [])
                            print(f"   {config['name']}: найдено {len(tasks)} задач")
                            
                            # Добавляем только новые задачи
                            for task in tasks:
                                task_id = task.get('id')
                                if task_id not in task_ids_seen:
                                    task_ids_seen.add(task_id)
                                    all_user_tasks.append(task)
                        else:
                            print(f"   {config['name']}: {data.get('error', 'ошибка API')}")
                    else:
                        print(f"   {config['name']}: HTTP {response.status_code}")
                        
                except Exception as e:
                    print(f"   {config['name']}: ошибка - {e}")
            
            # Если через фильтры ничего не нашли, получаем все задачи и фильтруем вручную
            if not all_user_tasks:
                print("🔄 Фильтры не сработали, получаем все задачи и фильтруем вручную")
                all_user_tasks = self._get_all_tasks_and_filter_manually()
            
            # Фильтруем только незакрытые задачи
            active_tasks = []
            closed_statuses = ['Выполненная', 'Отменена', 'Закрыта', 'Завершена']
            
            for task in all_user_tasks:
                status = task.get('status', {})
                status_name = status.get('name', '') if isinstance(status, dict) else str(status)
                
                # Пропускаем закрытые задачи
                if status_name not in closed_statuses:
                    active_tasks.append(task)
            
            print(f"✅ Найдено активных задач для {self.user_name}: {len(active_tasks)}")
            
            if active_tasks:
                # Показываем краткую статистику
                overdue_count = 0
                with_deadline = 0
                
                for task in active_tasks:
                    if task.get('overdue'):
                        overdue_count += 1
                    if task.get('endDateTime'):
                        with_deadline += 1
                
                print(f"📊 Статистика:")
                print(f"   🔴 Просроченных: {overdue_count}")
                print(f"   📅 С дедлайном: {with_deadline}")
                print(f"   📝 Без дедлайна: {len(active_tasks) - with_deadline}")
            
            return active_tasks
                
        except Exception as e:
            print(f"❌ Ошибка при получении задач: {str(e)}")
            return []

    def _get_all_tasks_and_filter_manually(self) -> List[Dict[Any, Any]]:
        """
        Получает все задачи и фильтрует по пользователю вручную
        """
        try:
            payload = {
                "offset": 0,
                "pageSize": 200,  # Увеличиваем лимит
                "fields": "id,name,description,endDateTime,startDateTime,status,priority,assignees,participants,auditors,assigner,overdue"
            }
            
            response = self.session.post(
                f"{self.account_url}/task/list",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                all_tasks = data.get('tasks', [])
                print(f"   Получено всего задач: {len(all_tasks)}")
                
                # Фильтруем задачи где пользователь участвует в любой роли
                user_tasks = []
                user_id_str = str(self.user_id)
                
                for task in all_tasks:
                    is_user_involved = False
                    
                    # Проверяем исполнителей
                    assignees = task.get('assignees', {})
                    if assignees:
                        users = assignees.get('users', [])
                        for user in users:
                            if str(user.get('id', '')) == user_id_str:
                                is_user_involved = True
                                break
                    
                    # Проверяем участников
                    participants = task.get('participants', {})
                    if participants and not is_user_involved:
                        users = participants.get('users', [])
                        for user in users:
                            if str(user.get('id', '')) == user_id_str:
                                is_user_involved = True
                                break
                    
                    # Проверяем контролеров
                    auditors = task.get('auditors', {})
                    if auditors and not is_user_involved:
                        users = auditors.get('users', [])
                        for user in users:
                            if str(user.get('id', '')) == user_id_str:
                                is_user_involved = True
                                break
                    
                    # Проверяем постановщика
                    assigner = task.get('assigner', {})
                    if assigner and not is_user_involved:
                        if str(assigner.get('id', '')) == user_id_str:
                            is_user_involved = True
                    
                    if is_user_involved:
                        user_tasks.append(task)
                
                print(f"   Отфильтровано для пользователя: {len(user_tasks)}")
                return user_tasks
            else:
                print(f"   Ошибка получения всех задач: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"   Ошибка ручной фильтрации: {e}")
            return []
      
    def test_connection(self) -> bool:
        """
        Тестирует соединение с API, пытаясь получить список сотрудников.
        """
        try:
            payload = {
                "offset": 0,
                "pageSize": 1,
                "fields": "id,name"
            }
            response = self.session.post(
                f"{self.account_url}/user/list",
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('result') == 'fail':
                    print(f"❌ API ошибка: {data.get('error', 'Неизвестная ошибка')}")
                    return False
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
    Учитывает только незакрытые задачи с дедлайнами
    """
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    
    categorized = {
        'overdue': [],    # Просроченные (дедлайн прошел, задача не закрыта)
        'urgent': [],     # Срочные (дедлайн сегодня/завтра)
        'current': []     # Текущие (дедлайн в будущем или без дедлайна)
    }
    
    closed_statuses = ['Выполненная', 'Отменена', 'Закрыта', 'Завершена']
    
    for task in tasks:
        try:
            # Проверяем статус задачи
            status = task.get('status', {})
            status_name = status.get('name', '') if isinstance(status, dict) else str(status)
            
            # Пропускаем закрытые задачи
            if status_name in closed_statuses:
                continue
            
            # Используем флаг overdue из API если он есть и задача не закрыта
            if task.get('overdue', False):
                categorized['overdue'].append(task)
                continue
            
            # Пробуем получить дату из endDateTime
            end_date_info = task.get('endDateTime')
            end_date = None
            
            if end_date_info:
                if isinstance(end_date_info, dict):
                    # Пробуем разные поля даты из API
                    date_str = (end_date_info.get('datetime') or 
                              end_date_info.get('date') or 
                              end_date_info.get('dateTimeUtcSeconds'))
                else:
                    date_str = str(end_date_info)
                
                if date_str:
                    try:
                        # Парсим дату в зависимости от формата
                        if 'T' in date_str:
                            # ISO формат: 1900-12-01T00:00Z
                            end_date = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
                        elif '-' in date_str:
                            # Попробуем разные форматы с дефисами
                            formats_to_try = ['%d-%m-%Y', '%Y-%m-%d', '%d-%m-%y']
                            for date_format in formats_to_try:
                                try:
                                    end_date = datetime.datetime.strptime(date_str, date_format).date()
                                    break
                                except ValueError:
                                    continue
                        elif '.' in date_str:
                            # Форматы с точками
                            formats_to_try = ['%d.%m.%Y', '%d.%m.%y']
                            for date_format in formats_to_try:
                                try:
                                    end_date = datetime.datetime.strptime(date_str, date_format).date()
                                    break
                                except ValueError:
                                    continue
                    except Exception as e:
                        print(f"⚠️ Ошибка парсинга даты '{date_str}' для задачи {task.get('id')}: {e}")
            
            # Fallback на старое поле endDate (если есть)
            if not end_date:
                end_date_str = task.get('endDate', '')
                if end_date_str:
                    try:
                        if 'T' in end_date_str:
                            end_date = datetime.datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).date()
                        else:
                            # Попробуем стандартные форматы
                            for date_format in ['%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y']:
                                try:
                                    end_date = datetime.datetime.strptime(end_date_str, date_format).date()
                                    break
                                except ValueError:
                                    continue
                    except Exception:
                        pass
            
            # Категоризуем задачу
            if end_date:
                if end_date < today:
                    # Просроченная задача
                    categorized['overdue'].append(task)
                elif end_date <= tomorrow:
                    # Срочная задача (сегодня или завтра)
                    categorized['urgent'].append(task)
                else:
                    # Текущая задача с дедлайном в будущем
                    categorized['current'].append(task)
            else:
                # Задача без дедлайна - считаем текущей
                categorized['current'].append(task)
                
        except Exception as e:
            print(f"⚠️ Ошибка обработки задачи {task.get('id', 'Unknown')}: {e}")
            categorized['current'].append(task)  # По умолчанию в текущие
    
    return categorized

def show_notification(title: str, message: str, urgency: str = 'normal'):
    """
    Отображает системное уведомление с учетом важности
    """
    try:
        # Проверяем длину заголовка перед отправкой
        if len(title) > 64:
            print(f"⚠️ Заголовок слишком длинный ({len(title)} символов): {title}")
            # Экстренное обрезание
            title = title[:61] + "..."
            print(f"   Обрезан до: {title}")
        
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
        print(f"   Заголовок ({len(title)} символов): {title}")
        print(f"   Сообщение ({len(message)} символов): {message[:100]}...")
        print("💡 Установите: pip install plyer")

def format_task_message(task: Dict, category: str) -> tuple:
    """
    Форматирует сообщение для задачи с указанием роли пользователя
    """
    task_name = task.get('name', 'Задача без названия')
    description = task.get('description', '')
    
    # Обрабатываем дату окончания
    end_date_info = task.get('endDateTime')
    end_date_str = 'Не указана'
    
    if end_date_info:
        if isinstance(end_date_info, dict):
            end_date_str = (end_date_info.get('date') or 
                          end_date_info.get('datetime') or 
                          'Указана')
        else:
            end_date_str = str(end_date_info)
    
    # Обрабатываем приоритет
    priority = task.get('priority', 'NotUrgent')
    priority_text = {
        'NotUrgent': 'Обычная',
        'Low': 'Низкая', 
        'Normal': 'Обычная',
        'High': 'Высокая',
        'Critical': 'Критическая'
    }.get(priority, priority)
    
    # Обрабатываем статус
    status = task.get('status', {})
    if isinstance(status, dict):
        status_name = status.get('name', 'Неизвестно')
    else:
        status_name = str(status)
    
    # Определяем роль пользователя в задаче
    user_roles = []
    
    # Проверяем исполнителей
    assignees = task.get('assignees', {})
    assignee_names = []
    if assignees:
        users = assignees.get('users', [])
        for user in users:
            name = user.get('name', f"ID:{user.get('id')}")
            assignee_names.append(name)
    
    # Проверяем постановщика
    assigner = task.get('assigner', {})
    assigner_name = assigner.get('name', 'Неизвестно') if assigner else 'Неизвестно'
    
    # Проверяем участников
    participants = task.get('participants', {})
    participant_names = []
    if participants:
        users = participants.get('users', [])
        for user in users:
            participant_names.append(user.get('name', f"ID:{user.get('id')}"))
    
    # Проверяем контролеров  
    auditors = task.get('auditors', {})
    auditor_names = []
    if auditors:
        users = auditors.get('users', [])
        for user in users:
            auditor_names.append(user.get('name', f"ID:{user.get('id')}"))
    
    # Формируем строку с исполнителями
    if assignee_names:
        assignee_text = ', '.join(assignee_names)
    else:
        assignee_text = 'Не назначен'
    
    # Ограничиваем описание
    if len(description) > 80:
        description = description[:80] + "..."
    
    # Форматируем дату для отображения
    formatted_date = end_date_str
    if end_date_str and end_date_str not in ['Не указана', 'Указана']:
        try:
            if 'T' in end_date_str:
                date_obj = datetime.datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime('%d.%m.%Y')
            elif '-' in end_date_str and len(end_date_str) >= 8:
                # Форматы с дефисами
                for date_format in ['%d-%m-%Y', '%Y-%m-%d', '%d-%m-%y']:
                    try:
                        date_obj = datetime.datetime.strptime(end_date_str, date_format)
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        break
                    except ValueError:
                        continue
            elif '.' in end_date_str:
                # Форматы с точками
                for date_format in ['%d.%m.%Y', '%d.%m.%y']:
                    try:
                        date_obj = datetime.datetime.strptime(end_date_str, date_format)
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        break
                    except ValueError:
                        continue
        except:
            formatted_date = end_date_str
    
    # Формируем заголовок с ограничением длины для Windows (максимум 64 символа)
    title_prefix = {
        'overdue': '🔴 ПРОСРОЧЕНО',
        'urgent': '🟡 СРОЧНО', 
        'current': '📋 ЗАДАЧА'
    }.get(category, '📋 ЗАДАЧА')
    
    # Очень консервативный лимит для Windows с эмодзи - 55 символов
    safe_limit = 55
    separator = ": "
    
    # Вычисляем максимальную длину названия задачи
    prefix_and_separator_length = len(title_prefix) + len(separator)
    max_task_name_length = safe_limit - prefix_and_separator_length
    
    if max_task_name_length <= 3:  # Если места совсем мало
        task_name_short = "..."
    elif len(task_name) > max_task_name_length:
        task_name_short = task_name[:max_task_name_length-3] + "..."
    else:
        task_name_short = task_name
    
    title = f"{title_prefix}{separator}{task_name_short}"
    
    # Финальная проверка длины
    if len(title) > safe_limit:
        # Аварийное обрезание
        title = title[:safe_limit-3] + "..."
    
    # Формируем сообщение
    message_parts = [f"📅 Срок: {formatted_date}"]
    message_parts.append(f"👤 Исполнитель: {assignee_text}")
    
    if assigner_name != 'Неизвестно':
        message_parts.append(f"📝 Постановщик: {assigner_name}")
    
    if participant_names:
        message_parts.append(f"👥 Участники: {', '.join(participant_names)}")
    
    if auditor_names:
        message_parts.append(f"👁 Контролеры: {', '.join(auditor_names)}")
    
    if priority_text != 'Обычная':
        message_parts.append(f"⚡ Приоритет: {priority_text}")
    
    if status_name != 'Неизвестно':
        message_parts.append(f"📊 Статус: {status_name}")
    
    if description:
        message_parts.append(f"📄 {description}")
    
    # Полное название задачи в сообщении если оно было обрезано
    if len(task_name) > max_task_name_length:
        message_parts.insert(0, f"📋 {task_name}")
    
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
                print(f"⚠️ account_url '{account_url}' должен заканчиваться на '/rest'")
                print("   Пример: https://l-s.planfix.com/rest")
            print(f"✅ Конфигурация загружена (кодировка: {encoding})")
            return api_token, account_url, check_interval, notification_settings
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"❌ Ошибка чтения конфигурации с кодировкой {encoding}: {e}")
            continue
    
    print("❌ Не удалось прочитать config.ini")
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
        print("💡 Проверьте API токен и права доступа")
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
            
            if new_notifications == 0:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ Новых уведомлений нет")
            else:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📬 Отправлено {new_notifications} новых уведомлений")
            
            # Сброс уведомленных задач каждый час
            current_hour = datetime.datetime.now().hour
            if hasattr(main, 'last_hour') and main.last_hour != current_hour:
                notified_tasks.clear()
                print("🔄 Сброс списка уведомленных задач (новый час)")
            main.last_hour = current_hour
            
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