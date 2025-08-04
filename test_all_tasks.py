#!/usr/bin/env python3
"""
Тестирует получение всех задач без фильтров
"""
import requests
import json
import configparser

def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    return config['Planfix']['api_token'], config['Planfix']['account_url']

def test_all_tasks():
    api_token, account_url = load_config()
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_token}'
    }
    
    print("🔍 Тестирование получения ВСЕХ задач")
    print("=" * 50)
    
    # Запрос без фильтров - все задачи
    payload = {
        "offset": 0,
        "pageSize": 10,  # Ограничиваем для тестирования
        "fields": "id,name,description,endDateTime,status,priority,assignees,overdue"
    }
    
    print(f"📋 Запрос: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    response = requests.post(
        f"{account_url}/task/list",
        headers=headers,
        json=payload,
        timeout=15
    )
    
    print(f"\n📊 Статус ответа: {response.status_code}")
    
    if response.status_code == 200:
        try:
            data = response.json()
            
            if data.get('result') == 'fail':
                print(f"❌ API ошибка: {data.get('error')}")
                return
            
            tasks = data.get('tasks', [])
            print(f"✅ Найдено задач: {len(tasks)}")
            
            if tasks:
                print(f"\n📋 СПИСОК ЗАДАЧ:")
                print("-" * 40)
                
                for i, task in enumerate(tasks, 1):
                    print(f"\n{i}. ID: {task.get('id')}")
                    print(f"   Название: {task.get('name', 'Без названия')}")
                    
                    # Статус
                    status = task.get('status', {})
                    if isinstance(status, dict):
                        print(f"   Статус: {status.get('name', 'Неизвестно')}")
                    else:
                        print(f"   Статус: {status}")
                    
                    # Исполнители
                    assignees = task.get('assignees', {})
                    if assignees:
                        users = assignees.get('users', [])
                        groups = assignees.get('groups', [])
                        
                        if users:
                            user_names = [u.get('name', f"ID:{u.get('id')}") for u in users]
                            print(f"   Исполнители: {', '.join(user_names)}")
                        
                        if groups:
                            group_names = [g.get('name', f"ID:{g.get('id')}") for g in groups]
                            print(f"   Группы: {', '.join(group_names)}")
                    
                    # Дата окончания
                    end_date = task.get('endDateTime')
                    if end_date:
                        if isinstance(end_date, dict):
                            date_str = end_date.get('date') or end_date.get('datetime') or 'Указана'
                        else:
                            date_str = str(end_date)
                        print(f"   Срок: {date_str}")
                    
                    # Просрочена ли
                    if task.get('overdue'):
                        print(f"   🔴 ПРОСРОЧЕНА!")
                
                print(f"\n" + "=" * 50)
                print("💡 АНАЛИЗ:")
                
                # Анализируем исполнителей
                all_assignees = set()
                for task in tasks:
                    assignees = task.get('assignees', {})
                    users = assignees.get('users', [])
                    for user in users:
                        user_id = user.get('id')
                        user_name = user.get('name', f'ID:{user_id}')
                        all_assignees.add(f"{user_name} (ID: {user_id})")
                
                if all_assignees:
                    print(f"👥 Все исполнители в задачах:")
                    for assignee in sorted(all_assignees):
                        print(f"   - {assignee}")
                else:
                    print("⚠️ Ни в одной задаче нет исполнителей")
                
                # Проверяем есть ли задачи для пользователя ID:1
                user_1_tasks = []
                for task in tasks:
                    assignees = task.get('assignees', {})
                    users = assignees.get('users', [])
                    for user in users:
                        if user.get('id') == '1' or user.get('id') == 1:
                            user_1_tasks.append(task.get('name'))
                
                if user_1_tasks:
                    print(f"\n✅ Задачи для пользователя ID:1 (Андрей):")
                    for task_name in user_1_tasks:
                        print(f"   - {task_name}")
                else:
                    print(f"\n❌ Задач для пользователя ID:1 (Андрей) не найдено")
                    print("💡 Возможные причины:")
                    print("   - Задачи назначены на других пользователей")
                    print("   - Задачи назначены на группы")
                    print("   - ID пользователя отличается от ожидаемого")
            
            else:
                print("📭 В системе вообще нет задач")
                print("💡 Создайте несколько тестовых задач в Planfix")
                
        except json.JSONDecodeError:
            print(f"❌ Ответ не в формате JSON: {response.text}")
        except Exception as e:
            print(f"❌ Ошибка обработки ответа: {e}")
            print(f"📄 Сырой ответ: {response.text[:500]}")
    else:
        print(f"❌ Ошибка HTTP: {response.text}")

def main():
    test_all_tasks()

if __name__ == "__main__":
    main()