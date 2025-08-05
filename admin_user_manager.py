import requests
import configparser
import os
import sys
from typing import List, Dict, Any
import json

class PlanfixUserManager:
    def __init__(self, account_url: str, api_token: str):
        self.account_url = account_url.rstrip('/')
        self.api_token = api_token
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_token}'
        })

    def get_all_users(self) -> List[Dict[Any, Any]]:
        """Получает список всех пользователей"""
        try:
            all_users = []
            offset = 0
            page_size = 100
            
            while True:
                payload = {
                    'offset': offset,
                    'pageSize': page_size,
                    'fields': 'id,name,lastname,midname,email,position,status,groups'
                }
                
                response = self.session.post(
                    f"{self.account_url}/user/list",
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('result') == 'fail':
                        print(f"❌ Ошибка API: {data.get('error', 'Неизвестная ошибка')}")
                        return []
                    
                    users = data.get('users', [])
                    if not users:
                        break
                        
                    all_users.extend(users)
                    
                    # Если получили меньше чем page_size, значит это последняя страница
                    if len(users) < page_size:
                        break
                        
                    offset += page_size
                else:
                    print(f"❌ Ошибка HTTP: {response.status_code}")
                    return []
            
            return all_users
            
        except Exception as e:
            print(f"❌ Ошибка получения пользователей: {e}")
            return []

    def get_user_tasks_count(self, user_id: str) -> Dict[str, int]:
        """Получает количество задач пользователя по ролям (ПРОСТАЯ РАБОЧАЯ ВЕРСИЯ)"""
        try:
            # 1. ИСПОЛНИТЕЛЬ - простой запрос
            assignee_tasks = self._get_simple_tasks_by_role(user_id, role_type=2)
            
            # 2. ПОСТАНОВЩИК - простой запрос  
            assigner_tasks = self._get_simple_tasks_by_role(user_id, role_type=3)
            
            # 3. КОНТРОЛЕР - простой запрос
            auditor_tasks = self._get_simple_tasks_by_role(user_id, role_type=4)
            
            # Подсчитываем активные (исключаем "Выполненная" и "Завершенная")
            def count_active_and_overdue(tasks):
                active = []
                overdue = 0
                for task in tasks:
                    status = task.get('status', {})
                    status_name = status.get('name', '') if isinstance(status, dict) else str(status)
                    
                    if status_name not in ['Выполненная', 'Завершенная']:
                        active.append(task)
                        if task.get('overdue', False):
                            overdue += 1
                
                return len(active), overdue
            
            assignee_count, assignee_overdue = count_active_and_overdue(assignee_tasks)
            assigner_count, assigner_overdue = count_active_and_overdue(assigner_tasks)
            auditor_count, auditor_overdue = count_active_and_overdue(auditor_tasks)
            
            # Объединяем уникальные задачи по ID
            all_task_ids = set()
            all_overdue_ids = set()
            
            for task in assignee_tasks + assigner_tasks + auditor_tasks:
                status = task.get('status', {})
                status_name = status.get('name', '') if isinstance(status, dict) else str(status)
                
                if status_name not in ['Выполненная', 'Завершенная']:
                    task_id = task.get('id')
                    all_task_ids.add(task_id)
                    if task.get('overdue', False):
                        all_overdue_ids.add(task_id)
            
            total_count = len(all_task_ids)
            total_overdue = len(all_overdue_ids)
            
            return {
                'total': total_count,
                'overdue': total_overdue,
                'current': total_count - total_overdue,
                'assignee_count': assignee_count,
                'assigner_count': assigner_count,
                'auditor_count': auditor_count,
                'assignee_overdue': assignee_overdue,
                'assigner_overdue': assigner_overdue,
                'auditor_overdue': auditor_overdue
            }
            
        except Exception as e:
            return {
                'total': 0, 'overdue': 0, 'current': 0,
                'assignee_count': 0, 'assigner_count': 0, 'auditor_count': 0,
                'assignee_overdue': 0, 'assigner_overdue': 0, 'auditor_overdue': 0
            }

    def _get_simple_tasks_by_role(self, user_id: str, role_type: int) -> List[Dict]:
        """Простое получение задач по типу роли БЕЗ сложной логики"""
        try:
            payload = {
                "offset": 0,
                "pageSize": 100,
                "filters": [
                    {
                        "type": role_type,
                        "operator": "equal",
                        "value": f"user:{user_id}"
                    }
                ],
                "fields": "id,name,status,overdue"
            }
            
            response = self.session.post(
                f"{self.account_url}/task/list",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('result') != 'fail':
                    return data.get('tasks', [])
            
            return []
            
        except Exception:
            return []
    
    def _get_tasks_by_role(self, user_id: str, role_type: int) -> List[Dict]:
        """Получает задачи пользователя по конкретной роли"""
        try:
            payload = {
                "offset": 0,
                "pageSize": 200,
                "filters": [
                    {
                        "type": role_type,
                        "operator": "equal",
                        "value": f"user:{user_id}"
                    }
                ],
                "fields": "id,status,overdue,endDateTime,name"
            }
            
            response = self.session.post(
                f"{self.account_url}/task/list",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('result') != 'fail':
                    return data.get('tasks', [])
            
            return []
            
        except Exception:
            return []

    def test_connection(self) -> bool:
        """Тестирует соединение с API"""
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
                return True
            else:
                print(f"❌ HTTP ошибка: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Ошибка соединения: {e}")
            return False

def load_admin_config():
    """Загружает конфигурацию администратора"""
    config_file = 'admin_config.ini'
    
    if not os.path.exists(config_file):
        print(f"❌ Файл {config_file} не найден!")
        print("\nСоздайте файл admin_config.ini с содержимым:")
        print("""
[Planfix]
api_token = ВАШ_АДМИНСКИЙ_ТОКЕН
account_url = https://your-account.planfix.com/rest
        """)
        return None, None
    
    config = configparser.ConfigParser()
    
    try:
        config.read(config_file, encoding='utf-8')
        api_token = config['Planfix']['api_token']
        account_url = config['Planfix']['account_url']
        
        if not api_token or api_token in ['ВАШ_АДМИНСКИЙ_ТОКЕН', 'YOUR_API_TOKEN_HERE']:
            print("❌ API токен не настроен в admin_config.ini")
            return None, None
            
        return api_token, account_url
        
    except Exception as e:
        print(f"❌ Ошибка чтения конфигурации: {e}")
        return None, None

def display_users_table(users: List[Dict], show_tasks: bool = False, manager: PlanfixUserManager = None):
    """Отображает таблицу пользователей с расширенной статистикой по ролям"""
    if not users:
        print("❌ Пользователи не найдены")
        return
    
    print(f"\n{'='*120}")
    print(f"📋 СПИСОК ПОЛЬЗОВАТЕЛЕЙ PLANFIX ({len(users)} чел.)")
    print(f"{'='*120}")
    
    # Заголовок таблицы
    if show_tasks:
        print(f"{'ID':<4} {'ИМЯ':<20} {'EMAIL':<25} {'ВСЕГО':<6} {'ПРОСР':<6} {'ИСПОЛН':<7} {'ПОСТАВ':<7} {'КОНТР':<6}")
        print(f"{'-'*4} {'-'*20} {'-'*25} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*6}")
    else:
        print(f"{'ID':<4} {'ИМЯ':<20} {'EMAIL':<25} {'ДОЛЖНОСТЬ':<15}")
        print(f"{'-'*4} {'-'*20} {'-'*25} {'-'*15}")
    
    for user in users:
        user_id = str(user.get('id', ''))
        name = user.get('name', '')
        lastname = user.get('lastname', '')
        email = user.get('email', '')
        position = user.get('position', '')
        
        # Формируем полное имя
        full_name = f"{lastname} {name}".strip()
        if not full_name:
            full_name = f"User {user_id}"
        
        # Обрезаем длинные поля
        full_name = full_name[:19]
        email = email[:24] if email else 'Не указан'
        position = position[:14] if position else 'Не указана'
        
        if show_tasks and manager:
            print(f"  Анализирую задачи для {full_name}...", end='\r')
            task_stats = manager.get_user_tasks_count(user_id)
            
            # Форматируем строку с основной статистикой
            total = task_stats['total']
            overdue = task_stats['overdue'] 
            assignee = task_stats['assignee_count']
            assigner = task_stats['assigner_count']
            auditor = task_stats['auditor_count']
            
            print(f"{user_id:<4} {full_name:<20} {email:<25} {total:<6} {overdue:<6} {assignee:<7} {assigner:<7} {auditor:<6}")
        else:
            print(f"{user_id:<4} {full_name:<20} {email:<25} {position:<15}")
    
    if show_tasks:
        print(f"\n📊 РАСШИФРОВКА КОЛОНОК:")
        print(f"   ВСЕГО  - общее количество активных задач")
        print(f"   ПРОСР  - просроченные задачи")
        print(f"   ИСПОЛН - задачи где пользователь исполнитель")
        print(f"   ПОСТАВ - задачи где пользователь постановщик")
        print(f"   КОНТР  - задачи где пользователь контролер/участник")

def generate_config_templates(users: List[Dict]):
    """Генерирует шаблоны config.ini для каждого пользователя"""
    if not users:
        return
    
    print(f"\n🔧 ГЕНЕРАЦИЯ ШАБЛОНОВ КОНФИГУРАЦИЙ")
    print(f"{'='*50}")
    
    # Создаем папку для конфигов
    config_dir = "user_configs"
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    
    for user in users:
        user_id = str(user.get('id', ''))
        name = user.get('name', '')
        lastname = user.get('lastname', '')
        
        # Формируем имя файла
        filename = f"{lastname}_{name}_config.ini".replace(' ', '_')
        filepath = os.path.join(config_dir, filename)
        
        # Создаем содержимое файла
        config_content = f"""[Planfix]
# Общий API токен (одинаковый для всех сотрудников)
api_token = YOUR_SHARED_API_TOKEN_HERE

# URL аккаунта Planfix
account_url = https://your-account.planfix.com/rest

# ID фильтра для {lastname} {name} (ID пользователя: {user_id})
# СОЗДАЙТЕ ФИЛЬТР В PLANFIX:
# - Исполнитель = {lastname} {name} ИЛИ
# - Постановщик = {lastname} {name} ИЛИ  
# - Контролер = {lastname} {name}
# - Статус ≠ Выполнена, Отменена, Закрыта
filter_id = FILTER_ID_FOR_USER_{user_id}

[Settings]
# Интервал проверки задач (секунды)
check_interval = 300

# Типы уведомлений
notify_current = true
notify_urgent = true
notify_overdue = true

# Лимиты окон уведомлений
max_windows_per_category = 5
max_total_windows = 10
"""
        
        # Сохраняем файл
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        print(f"✅ {filename} - создан")
    
    print(f"\n📁 Все конфигурации сохранены в папку: {config_dir}")
    print("\n📋 ЧТО ДЕЛАТЬ ДАЛЬШЕ:")
    print("1. Создайте в Planfix фильтры для каждого сотрудника")
    print("2. Замените FILTER_ID_FOR_USER_XXX на реальные ID фильтров")
    print("3. Замените YOUR_SHARED_API_TOKEN_HERE на общий токен")
    print("4. Замените your-account на название вашего аккаунта")

def main():
    print("🚀 PLANFIX USER MANAGER - Инструмент администратора")
    print("="*60)
    
    # Загружаем конфигурацию
    api_token, account_url = load_admin_config()
    if not api_token:
        return
    
    # Создаем менеджер
    manager = PlanfixUserManager(account_url, api_token)
    
    # Тестируем соединение
    print("🔌 Тестирую подключение к Planfix...")
    if not manager.test_connection():
        print("❌ Не удалось подключиться к Planfix API")
        return
    
    print("✅ Подключение успешно!")
    
    # Получаем пользователей
    print("👥 Получаю список пользователей...")
    users = manager.get_all_users()
    
    if not users:
        print("❌ Пользователи не найдены")
        return
    
    # Меню
    while True:
        print(f"\n📋 МЕНЮ:")
        print("1. Показать всех пользователей")
        print("2. Показать пользователей с количеством задач")
        print("3. Генерировать шаблоны config.ini")
        print("0. Выход")
        
        choice = input("\nВыберите действие (0-3): ").strip()
        
        if choice == '1':
            display_users_table(users, show_tasks=False)
        elif choice == '2':
            print("⏳ Получаю данные о задачах для каждого пользователя...")
            display_users_table(users, show_tasks=True, manager=manager)
        elif choice == '3':
            generate_config_templates(users)
        elif choice == '0':
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор")

if __name__ == "__main__":
    main()