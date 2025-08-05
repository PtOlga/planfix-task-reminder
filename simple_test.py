import requests
import configparser

def test_svetlana_tasks():
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
    
    print("🔍 ПРОСТОЙ ТЕСТ ЗАДАЧ СВЕТЛАНЫ (ID=3)")
    print("="*50)
    
    # Запрос задач где Светлана - исполнитель
    payload = {
        "offset": 0,
        "pageSize": 50,
        "filters": [
            {
                "type": 2,
                "operator": "equal",
                "value": "user:3"
            }
        ],
        "fields": "id,name,status,overdue"
    }
    
    print("📡 Отправляю запрос...")
    response = session.post(f"{account_url}/task/list", json=payload, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('result') == 'fail':
            print(f"❌ API ошибка: {data.get('error')}")
            return
        
        tasks = data.get('tasks', [])
        print(f"✅ Получено {len(tasks)} задач")
        
        if tasks:
            # Анализируем статусы
            closed_statuses = ['Выполненная', 'Отменена', 'Закрыта', 'Завершена']
            active_tasks = []
            
            print(f"\n📋 ВСЕ ЗАДАЧИ СВЕТЛАНЫ:")
            for i, task in enumerate(tasks, 1):
                status = task.get('status', {})
                status_name = status.get('name', '') if isinstance(status, dict) else str(status)
                overdue = "ПРОСРОЧЕНА" if task.get('overdue') else "В срок"
                
                print(f"   {i}. {task.get('name', 'Без названия')}")
                print(f"      Статус: {status_name}")
                print(f"      Сроки: {overdue}")
                print()
                
                if status_name not in closed_statuses:
                    active_tasks.append(task)
            
            print(f"📊 ИТОГ:")
            print(f"   Всего задач: {len(tasks)}")
            print(f"   Активных: {len(active_tasks)}")
            print(f"   Закрытых: {len(tasks) - len(active_tasks)}")
            
            overdue_count = sum(1 for t in active_tasks if t.get('overdue'))
            print(f"   Просроченных активных: {overdue_count}")
            
        else:
            print("❌ Задач не найдено")
    else:
        print(f"❌ HTTP ошибка: {response.status_code}")
        print(f"Ответ: {response.text}")

if __name__ == "__main__":
    test_svetlana_tasks()
