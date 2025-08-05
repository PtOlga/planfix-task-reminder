import requests
import configparser
import os
import json
from typing import List, Dict, Any

class DebugTaskManager:
    def __init__(self, account_url: str, api_token: str):
        self.account_url = account_url.rstrip('/')
        self.api_token = api_token
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_token}'
        })

    def debug_user_tasks(self, user_id: str, user_name: str):
        """Отладочная проверка задач пользователя"""
        print(f"\n🔍 ОТЛАДКА ЗАДАЧ ДЛЯ: {user_name} (ID: {user_id})")
        print("="*60)
        
        # 1. Проверяем задачи где пользователь - исполнитель
        print("1️⃣ Проверяю задачи где пользователь ИСПОЛНИТЕЛЬ...")
        assignee_tasks = self._get_tasks_by_filter(user_id, filter_type=2, filter_name="Исполнитель")
        
        # 2. Проверяем задачи где пользователь - постановщик  
        print("2️⃣ Проверяю задачи где пользователь ПОСТАНОВЩИК...")
        assigner_tasks = self._get_tasks_by_filter(user_id, filter_type=3, filter_name="Постановщик")
        
        # 3. Проверяем задачи где пользователь - контролер
        print("3️⃣ Проверяю задачи где пользователь КОНТРОЛЕР...")
        auditor_tasks = self._get_tasks_by_filter(user_id, filter_type=4, filter_name="Контролер")
        
        # 4. Получаем ВСЕ задачи без фильтров и ищем пользователя вручную
        print("4️⃣ Проверяю ВСЕ задачи и ищу пользователя вручную...")
        manual_tasks = self._get_all_tasks_and_filter_manually(user_id, user_name)
        
        # 5. Итоговая статистика
        total_unique_tasks = set()
        for tasks in [assignee_tasks, assigner_tasks, auditor_tasks, manual_tasks]:
            for task in tasks:
                total_unique_tasks.add(task.get('id'))
        
        print(f"\n📊 ИТОГОВАЯ СТАТИСТИКА для {user_name}:")
        print(f"   Как исполнитель: {len(assignee_tasks)} задач")
        print(f"   Как постановщик: {len(assigner_tasks)} задач") 
        print(f"   Как контролер: {len(auditor_tasks)} задач")
        print(f"   Найдено вручную: {len(manual_tasks)} задач")
        print(f"   ВСЕГО уникальных: {len(total_unique_tasks)} задач")
        
        return list(total_unique_tasks)

    def _get_tasks_by_filter(self, user_id: str, filter_type: int, filter_name: str) -> List[Dict]:
        """Получает задачи по конкретному типу фильтра"""
        try:
            payload = {
                "offset": 0,
                "pageSize": 100,
                "filters": [
                    {
                        "type": filter_type,
                        "operator": "equal",
                        "value": f"user:{user_id}"
                    }
                ],
                "fields": "id,name,status,overdue,endDateTime,assignees,assigner,auditors"
            }
            
            print(f"   📡 Отправляю запрос для фильтра {filter_name}...")
            response = self.session.post(
                f"{self.account_url}/task/list",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('result') == 'fail':
                    print(f"   ❌ API ошибка: {data.get('error', 'Неизвестная ошибка')}")
                    return []
                
                tasks = data.get('tasks', [])
                print(f"   ✅ Получено {len(tasks)} задач как {filter_name}")
                
                # Показываем первые несколько задач для отладки
                if tasks:
                    print(f"   📋 Примеры задач:")
                    for i, task in enumerate(tasks[:3]):
                        print(f"      {i+1}. {task.get('name', 'Без названия')} (ID: {task.get('id')})")
                
                return tasks
            else:
                print(f"   ❌ HTTP ошибка: {response.status_code}")
                print(f"   📄 Ответ: {response.text[:200]}")
                return []
                
        except Exception as e:
            print(f"   ❌ Исключение: {e}")
            return []

    def _get_all_tasks_and_filter_manually(self, user_id: str, user_name: str) -> List[Dict]:
        """Получает все задачи и фильтрует вручную"""
        try:
            print(f"   📡 Получаю ВСЕ задачи из системы...")
            payload = {
                "offset": 0,
                "pageSize": 200,
                "fields": "id,name,status,overdue,endDateTime,assignees,participants,auditors,assigner"
            }
            
            response = self.session.post(
                f"{self.account_url}/task/list",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                all_tasks = data.get('tasks', [])
                print(f"   ✅ Получено {len(all_tasks)} задач всего в системе")
                
                user_tasks = []
                user_id_str = str(user_id)
                
                for task in all_tasks:
                    is_user_involved = False
                    involvement_reason = []
                    
                    # Проверяем исполнителей
                    assignees = task.get('assignees', {})
                    if assignees and isinstance(assignees, dict):
                        users = assignees.get('users', [])
                        for user in users:
                            if str(user.get('id', '')) == user_id_str:
                                is_user_involved = True
                                involvement_reason.append("исполнитель")
                                break
                    
                    # Проверяем участников
                    participants = task.get('participants', {})
                    if participants and isinstance(participants, dict):
                        users = participants.get('users', [])
                        for user in users:
                            if str(user.get('id', '')) == user_id_str:
                                is_user_involved = True
                                involvement_reason.append("участник")
                                break
                    
                    # Проверяем контролеров
                    auditors = task.get('auditors', {})
                    if auditors and isinstance(auditors, dict):
                        users = auditors.get('users', [])
                        for user in users:
                            if str(user.get('id', '')) == user_id_str:
                                is_user_involved = True
                                involvement_reason.append("контролер")
                                break
                    
                    # Проверяем постановщика
                    assigner = task.get('assigner', {})
                    if assigner and isinstance(assigner, dict):
                        if str(assigner.get('id', '')) == user_id_str:
                            is_user_involved = True
                            involvement_reason.append("постановщик")
                    
                    if is_user_involved:
                        task['involvement_reason'] = involvement_reason
                        user_tasks.append(task)
                
                print(f"   ✅ Найдено {len(user_tasks)} задач связанных с пользователем")
                
                # Показываем найденные задачи
                if user_tasks:
                    print(f"   📋 Найденные задачи:")
                    for i, task in enumerate(user_tasks[:5]):
                        reasons = ", ".join(task.get('involvement_reason', []))
                        print(f"      {i+1}. {task.get('name', 'Без названия')} - как {reasons}")
                
                return user_tasks
            else:
                print(f"   ❌ HTTP ошибка: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"   ❌ Исключение: {e}")
            return []

    def debug_api_filters(self):
        """Отладка работы фильтров API"""
        print(f"\n🔧 ОТЛАДКА API ФИЛЬТРОВ")
        print("="*40)
        
        # Тест базового запроса без фильтров
        print("1️⃣ Тестирую базовый запрос без фильтров...")
        try:
            payload = {
                "offset": 0,
                "pageSize": 5,
                "fields": "id,name,assignees,assigner"
            }
            
            response = self.session.post(
                f"{self.account_url}/task/list",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                tasks = data.get('tasks', [])
                print(f"   ✅ Получено {len(tasks)} задач")
                
                if tasks:
                    print("   📋 Пример структуры задачи:")
                    print(json.dumps(tasks[0], indent=2, ensure_ascii=False))
            else:
                print(f"   ❌ Ошибка: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Исключение: {e}")

    def test_specific_user(self, user_id: str):
        """Тестирует конкретного пользователя"""
        print(f"\n🎯 ТЕСТ ПОЛЬЗОВАТЕЛЯ ID: {user_id}")
        print("="*40)
        
        # Получаем информацию о пользователе
        try:
            payload = {
                "offset": 0,
                "pageSize": 100,
                "fields": "id,name,lastname,email"
            }
            
            response = self.session.post(
                f"{self.account_url}/user/list",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                users = data.get('users', [])
                
                target_user = None
                for user in users:
                    if str(user.get('id')) == str(user_id):
                        target_user = user
                        break
                
                if target_user:
                    name = f"{target_user.get('lastname', '')} {target_user.get('name', '')}"
                    print(f"👤 Найден пользователь: {name}")
                    self.debug_user_tasks(user_id, name)
                else:
                    print(f"❌ Пользователь с ID {user_id} не найден")
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")

def load_admin_config():
    """Загружает конфигурацию администратора"""
    config_file = 'admin_config.ini'
    
    if not os.path.exists(config_file):
        print(f"❌ Файл {config_file} не найден!")
        return None, None
    
    config = configparser.ConfigParser()
    
    try:
        config.read(config_file, encoding='utf-8')
        api_token = config['Planfix']['api_token']
        account_url = config['Planfix']['account_url']
        return api_token, account_url
        
    except Exception as e:
        print(f"❌ Ошибка чтения конфигурации: {e}")
        return None, None

def main():
    print("🔍 PLANFIX TASK DEBUG - Отладка задач пользователей")
    print("="*60)
    
    # Загружаем конфигурацию
    api_token, account_url = load_admin_config()
    if not api_token:
        return
    
    # Создаем отладчик
    debugger = DebugTaskManager(account_url, api_token)
    
    print("🔧 Тестирую API фильтры...")
    debugger.debug_api_filters()
    
    print("\n" + "="*60)
    user_id = input("Введите ID пользователя для отладки (например: 1): ").strip()
    
    if user_id:
        debugger.test_specific_user(user_id)
    
    print("\n✅ Отладка завершена!")

if __name__ == "__main__":
    main()
