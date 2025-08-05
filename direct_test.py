import requests
import configparser

def get_user_tasks_simple(user_id, session, account_url):
    """Максимально простая версия без сложной логики"""
    print(f"🔍 Проверяю пользователя ID={user_id}...")
    
    # Получаем задачи где пользователь - исполнитель
    payload = {
        "offset": 0,
        "pageSize": 100,
        "filters": [
            {
                "type": 2,
                "operator": "equal",
                "value": f"user:{user_id}"
            }
        ],
        "fields": "id,name,status,overdue"
    }
    
    try:
        response = session.post(f"{account_url}/task/list", json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('result') == 'fail':
                print(f"   ❌ API ошибка: {data.get('error')}")
                return 0, 0
            
            all_tasks = data.get('tasks', [])
            print(f"   📋 Всего задач как исполнитель: {len(all_tasks)}")
            
            if not all_tasks:
                return 0, 0
            
            # Считаем активные задачи (НЕ "Выполненная" и НЕ "Завершенная")
            active_tasks = []
            for task in all_tasks:
                status = task.get('status', {})
                status_name = status.get('name', '') if isinstance(status, dict) else str(status)
                
                print(f"   - {task.get('name', 'Без названия')}: {status_name}")
                
                # Простое условие: если статус НЕ содержит "Выполнен" или "Завершен"
                if status_name not in ['Выполненная', 'Завершенная']:
                    active_tasks.append(task)
            
            # Считаем просроченные среди активных
            overdue_count = sum(1 for task in active_tasks if task.get('overdue', False))
            
            print(f"   ✅ Активных: {len(active_tasks)}, Просроченных: {overdue_count}")
            return len(active_tasks), overdue_count
        else:
            print(f"   ❌ HTTP ошибка: {response.status_code}")
            return 0, 0
            
    except Exception as e:
        print(f"   ❌ Исключение: {e}")
        return 0, 0

def main():
    print("🔧 ПРЯМОЙ ТЕСТ БЕЗ СЛОЖНОЙ ЛОГИКИ")
    print("="*50)
    
    # Загружаем конфиг
    config = configparser.ConfigParser()
    config.read('admin_config.ini', encoding='utf-8')
    api_token = config['Planfix']['api_token']
    account_url = config['Planfix']['account_url']
    
    session = requests.Session()
    session.headers.update({
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_token}'
    })
    
    # Тестируем всех пользователей
    users = [
        {'id': 1, 'name': 'Розум Андрей'},
        {'id': 3, 'name': 'Зайцева Светлана'},
        {'id': 4, 'name': 'Павлова Алёна'},
        {'id': 5, 'name': 'Довгаль Игорь'},
        {'id': 6, 'name': 'Пустовит Анна'}
    ]
    
    print(f"\n{'ID':<4} {'ИМЯ':<20} {'АКТИВНЫХ':<10} {'ПРОСРОЧ':<10}")
    print("-" * 50)
    
    for user in users:
        active_count, overdue_count = get_user_tasks_simple(user['id'], session, account_url)
        print(f"{user['id']:<4} {user['name']:<20} {active_count:<10} {overdue_count:<10}")
        print()

if __name__ == "__main__":
    main()
