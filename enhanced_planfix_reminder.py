import requests
import time
from plyer import notification
import datetime
import sys
import configparser
import os
import json
from typing import List, Dict, Any
import tkinter as tk
from tkinter import ttk
import threading
import winsound
import webbrowser
from urllib.parse import quote
import queue

# --- Конфигурация ---  
CHECK_INTERVAL_SECONDS = 5 * 60  # 5 минут

# Глобальная очередь для Toast-уведомлений
toast_queue = queue.Queue()
# Список активных окон для управления позициями
active_windows = []
# Система отслеживания закрытых задач
closed_tasks = {}  # task_id: {'closed_time': datetime, 'snooze_until': datetime, 'auto_closed': bool}

class ToastNotification:
    """
    Кастомное Toast-уведомление поверх всех окон с возможностью перетаскивания
    """
    def __init__(self, title: str, message: str, category: str, task_id: str = None):
        self.title = title
        self.message = message
        self.category = category
        self.task_id = task_id
        self.root = None
        self.is_closed = False
        self.drag_data = {"x": 0, "y": 0}
        
        # Настройки внешнего вида по категориям
        self.styles = {
            'overdue': {
                'bg_color': '#FF4444',
                'text_color': 'white',
                'border_color': '#CC0000',
                'duration': None,  # Висит пока не закроют
                'sound': True,
                'sound_type': 'critical'
            },
            'urgent': {
                'bg_color': '#FF8800',
                'text_color': 'white',
                'border_color': '#CC4400', 
                'duration': None,  # Теперь тоже висит пока не закроют
                'sound': True,
                'sound_type': 'warning'
            },
            'current': {
                'bg_color': '#0066CC',
                'text_color': 'white',
                'border_color': '#003388',
                'duration': None,  # И обычные тоже висят
                'sound': False,
                'sound_type': None
            }
        }
        
    def create_window(self, master_root):
        """Создает окно уведомления в главном потоке"""
        # Создаем топлевел окно
        self.root = tk.Toplevel(master_root)
        self.root.withdraw()  # Скрываем сначала
        
        # Настройки окна
        self.root.overrideredirect(True)  # Убираем рамку окна
        self.root.attributes('-topmost', True)  # Поверх всех окон
        self.root.attributes('-alpha', 0.95)  # Немного прозрачности
        
        style = self.styles.get(self.category, self.styles['current'])
        
        # Размеры
        window_width = 320
        window_height = 140
        
        # Позиция - каскадом для множественных окон
        x, y = self._calculate_position(window_width, window_height)
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # Основной контейнер с рамкой
        container = tk.Frame(
            self.root, 
            bg=style['border_color'], 
            relief='raised',
            bd=2
        )
        container.pack(fill='both', expand=True, padx=2, pady=2)
        
        # Заголовок окна (для перетаскивания)
        title_bar = tk.Frame(container, bg=style['bg_color'], height=25)
        title_bar.pack(fill='x', padx=1, pady=(1, 0))
        title_bar.pack_propagate(False)
        
        # Иконка категории в заголовке
        category_icon = {
            'overdue': '🔴',
            'urgent': '🟡',
            'current': '📋'
        }.get(self.category, '📋')
        
        icon_label = tk.Label(
            title_bar,
            text=category_icon,
            font=('Arial', 10),
            fg=style['text_color'],
            bg=style['bg_color']
        )
        icon_label.pack(side='left', padx=(5, 0), pady=2)
        
        # ID задачи в заголовке
        task_id_label = tk.Label(
            title_bar,
            text=f"#{self.task_id}" if self.task_id else "",
            font=('Arial', 8),
            fg=style['text_color'],
            bg=style['bg_color']
        )
        task_id_label.pack(side='left', padx=(5, 0), pady=2)
        
        # Кнопка закрытия
        close_btn = tk.Button(
            title_bar,
            text="✕",
            font=('Arial', 8, 'bold'),
            command=self._close,
            bg=style['text_color'],
            fg=style['bg_color'],
            relief='flat',
            width=2,
            height=1
        )
        close_btn.pack(side='right', padx=(0, 5), pady=2)
        
        # Кнопка "pin" для закрепления
        pin_btn = tk.Button(
            title_bar,
            text="📌",
            font=('Arial', 6),
            command=self._toggle_pin,
            bg=style['text_color'],
            fg=style['bg_color'],
            relief='flat',
            width=2,
            height=1
        )
        pin_btn.pack(side='right', padx=(0, 2), pady=2)
        
        # Привязываем события для перетаскивания к заголовку
        title_bar.bind("<Button-1>", self._start_drag)
        title_bar.bind("<B1-Motion>", self._on_drag)
        icon_label.bind("<Button-1>", self._start_drag)
        icon_label.bind("<B1-Motion>", self._on_drag)
        task_id_label.bind("<Button-1>", self._start_drag) 
        task_id_label.bind("<B1-Motion>", self._on_drag)
        
        # Основной контент
        content_frame = tk.Frame(container, bg=style['bg_color'], padx=8, pady=5)
        content_frame.pack(fill='both', expand=True, padx=1, pady=(0, 1))
        
        # Название задачи
        task_title = self.title.split(': ', 1)[-1] if ': ' in self.title else self.title
        title_label = tk.Label(
            content_frame,
            text=task_title,
            font=('Arial', 9, 'bold'),
            fg=style['text_color'],
            bg=style['bg_color'],
            wraplength=280,
            justify='left',
            anchor='w'
        )
        title_label.pack(fill='x', pady=(0, 3))
        
        # Информация о задаче (первые 2 строки)
        message_lines = self.message.split('\n')[:2]
        message_text = '\n'.join(message_lines)
        
        info_label = tk.Label(
            content_frame,
            text=message_text,
            font=('Arial', 7),
            fg=style['text_color'],
            bg=style['bg_color'],
            wraplength=280,
            justify='left',
            anchor='w'
        )
        info_label.pack(fill='x', pady=(0, 5))
        
        # Фрейм для кнопок действий
        button_frame = tk.Frame(content_frame, bg=style['bg_color'])
        button_frame.pack(fill='x')
        
        # Кнопки действий
        if self.task_id:
            # Кнопка "Открыть задачу"
            open_btn = tk.Button(
                button_frame,
                text="Открыть",
                font=('Arial', 7),
                command=self._open_task,
                bg='white',
                fg='black',
                relief='flat',
                padx=6,
                pady=1
            )
            open_btn.pack(side='left', padx=(0, 3))
        
        # Кнопка "Отложить" для просроченных и срочных
        if self.category in ['overdue', 'urgent']:
            snooze_btn = tk.Button(
                button_frame,
                text="15мин",
                font=('Arial', 7),
                command=self._snooze,
                bg='lightgray',
                fg='black',
                relief='flat',
                padx=6,
                pady=1
            )
            snooze_btn.pack(side='left', padx=(0, 3))
        
        # Кнопка "Напомнить позже" для всех задач
        remind_btn = tk.Button(
            button_frame,
            text="1ч",
            font=('Arial', 7),
            command=self._remind_later,
            bg='lightyellow',
            fg='black',
            relief='flat',
            padx=6,
            pady=1
        )
        remind_btn.pack(side='left', padx=(0, 3))
        
        # Кнопка "Готово"
        done_btn = tk.Button(
            button_frame,
            text="Готово",
            font=('Arial', 7),
            command=self._mark_done,
            bg='lightgreen',
            fg='black',
            relief='flat',
            padx=6,
            pady=1
        )
        done_btn.pack(side='right')
        
        # Добавляем в список активных окон
        active_windows.append(self)
        
        # Звуковой сигнал в отдельном потоке
        if style['sound']:
            threading.Thread(target=self._play_sound, args=(style['sound_type'],), daemon=True).start()
        
        # Показываем окно
        self.root.deiconify()
        
        # Убираем автозакрытие - теперь все окна висят пока не закроют вручную
        # if style['duration']:
        #     self.root.after(style['duration'], self._auto_close)
        
        # Анимация появления
        self._animate_in()
    
    def _calculate_position(self, width, height):
        """Вычисляет позицию окна с учетом уже открытых окон"""
        screen_width = 1920  # Примерная ширина экрана, можно получить динамически
        screen_height = 1080
        
        # Начальная позиция в правом верхнем углу
        start_x = screen_width - width - 20
        start_y = 20
        
        # Смещение для каждого нового окна
        offset_x = 10
        offset_y = 30
        
        # Считаем количество активных окон той же категории
        same_category_count = len([w for w in active_windows if w.category == self.category and not w.is_closed])
        
        x = start_x - (same_category_count * offset_x)
        y = start_y + (same_category_count * offset_y)
        
        # Не выходим за пределы экрана
        if y + height > screen_height - 50:
            y = 20  # Начинаем сначала
            x = start_x - 200  # Сдвигаем влево
        
        return x, y
    
    def _start_drag(self, event):
        """Начало перетаскивания"""
        self.drag_data["x"] = event.x_root - self.root.winfo_x()
        self.drag_data["y"] = event.y_root - self.root.winfo_y()
    
    def _on_drag(self, event):
        """Процесс перетаскивания"""
        x = event.x_root - self.drag_data["x"]
        y = event.y_root - self.drag_data["y"]
        self.root.geometry(f"+{x}+{y}")
    
    def _toggle_pin(self):
        """Переключает закрепление окна"""
        current_topmost = self.root.attributes('-topmost')
        self.root.attributes('-topmost', not current_topmost)
        # Можно добавить визуальную индикацию закрепления
    
    def _animate_in(self):
        """Анимация появления окна"""
        alpha = 0.0
        def fade_in():
            nonlocal alpha
            if self.root and not self.is_closed:
                alpha += 0.15
                if alpha <= 0.95:
                    try:
                        self.root.attributes('-alpha', alpha)
                        self.root.after(40, fade_in)
                    except tk.TclError:
                        pass
        fade_in()
    
    def _play_sound(self, sound_type: str):
        """Воспроизводит звуковой сигнал"""
        try:
            if sound_type == 'critical':
                # Для просроченных - 3 коротких сигнала
                for _ in range(3):
                    winsound.MessageBeep(winsound.MB_ICONHAND)
                    time.sleep(0.3)
            elif sound_type == 'warning':
                # Для срочных - предупреждающий звук
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception as e:
            print(f"⚠️ Ошибка воспроизведения звука: {e}")
    
    def _open_task(self):
        """Открывает задачу в браузере"""
        if self.task_id:
            task_url = f"https://l-s.planfix.com/task/{self.task_id}/"
            try:
                webbrowser.open(task_url)
                print(f"🌐 Открываю задачу {self.task_id} в браузере")
            except Exception as e:
                print(f"❌ Ошибка открытия браузера: {e}")
        # Не закрываем окно автоматически - пользователь может захотеть оставить его
    
    def _snooze(self):
        """Откладывает уведомление на 15 минут"""
        print(f"⏰ Задача {self.task_id} отложена на 15 минут")
        if self.task_id:
            # Отмечаем что задача отложена
            snooze_until = datetime.datetime.now() + datetime.timedelta(minutes=15)
            closed_tasks[self.task_id] = {
                'closed_time': datetime.datetime.now(),
                'snooze_until': snooze_until,
                'auto_closed': False
            }
        self._close()
    
    def _remind_later(self):
        """Напоминает позже (через 1 час)"""
        print(f"🕐 Задача {self.task_id} - напомнить через 1 час")
        if self.task_id:
            snooze_until = datetime.datetime.now() + datetime.timedelta(hours=1)
            closed_tasks[self.task_id] = {
                'closed_time': datetime.datetime.now(),
                'snooze_until': snooze_until,
                'auto_closed': False
            }
        self._close()
    
    def _mark_done(self):
        """Помечает задачу как просмотренную"""
        print(f"✅ Задача {self.task_id} помечена как просмотренная")
        if self.task_id:
            # Отмечаем что задача закрыта пользователем намеренно
            closed_tasks[self.task_id] = {
                'closed_time': datetime.datetime.now(),
                'snooze_until': None,  # Не показывать пока задача активна
                'auto_closed': False
            }
        self._close()
    
    def _close(self):
        """Закрывает уведомление"""
        self.is_closed = True
        
        # Если закрываем кнопкой X - это случайное закрытие
        if self.task_id and self.task_id not in closed_tasks:
            # Показать снова через разное время в зависимости от категории
            if self.category == 'overdue':
                reshow_minutes = 5  # Просроченные - через 5 минут
            elif self.category == 'urgent':
                reshow_minutes = 15  # Срочные - через 15 минут  
            else:
                reshow_minutes = 30  # Обычные - через 30 минут
                
            snooze_until = datetime.datetime.now() + datetime.timedelta(minutes=reshow_minutes)
            closed_tasks[self.task_id] = {
                'closed_time': datetime.datetime.now(),
                'snooze_until': snooze_until,
                'auto_closed': False
            }
            print(f"🔄 Задача {self.task_id} будет показана снова через {reshow_minutes} минут")
        
        # Удаляем из списка активных окон
        if self in active_windows:
            active_windows.remove(self)
        
        if self.root:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
    
    def _auto_close(self):
        """
        Метод больше не используется - окна не закрываются автоматически
        Оставляем для совместимости
        """
        pass

class ToastManager:
    """
    Менеджер Toast-уведомлений, работающий в главном потоке
    """
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # Скрываем главное окно
        self.root.title("Planfix Reminder")
        
        # Проверяем очередь каждые 100мс
        self.check_queue()
        
    def check_queue(self):
        """Проверяет очередь уведомлений"""
        try:
            while True:
                toast = toast_queue.get_nowait()
                toast.create_window(self.root)
        except queue.Empty:
            pass
        
        # Планируем следующую проверку
        self.root.after(100, self.check_queue)
    
    def run(self):
        """Запускает цикл обработки событий"""
        self.root.mainloop()

def should_show_notification(task_id: str, category: str) -> bool:
    """
    Определяет нужно ли показывать уведомление для задачи
    """
    if not task_id:
        return True
    
    # Проверяем есть ли задача в списке закрытых
    if task_id not in closed_tasks:
        return True
    
    task_info = closed_tasks[task_id]
    now = datetime.datetime.now()
    
    # Если задача отложена и время еще не пришло
    if task_info['snooze_until'] and now < task_info['snooze_until']:
        return False
    
    # Если время отложения прошло - удаляем из списка и показываем
    if task_info['snooze_until'] and now >= task_info['snooze_until']:
        del closed_tasks[task_id]
        print(f"⏰ Время отложения истекло для задачи {task_id}")
        return True
    
    # Если задача помечена как "Готово" (snooze_until = None)
    if not task_info['snooze_until']:
        return False
    
    return False

def cleanup_old_closed_tasks():
    """
    Очищает старые записи о закрытых задачах
    """
    now = datetime.datetime.now()
    to_remove = []
    
    for task_id, task_info in closed_tasks.items():
        # Удаляем записи старше 24 часов
        if now - task_info['closed_time'] > datetime.timedelta(hours=24):
            to_remove.append(task_id)
    
    for task_id in to_remove:
        del closed_tasks[task_id]
        print(f"🧹 Очищена старая запись для задачи {task_id}")

def get_notification_summary():
    """
    Возвращает сводку по уведомлениям
    """
    now = datetime.datetime.now()
    active_count = len([w for w in active_windows if not w.is_closed])
    snoozed_count = len([info for info in closed_tasks.values() 
                        if info['snooze_until'] and now < info['snooze_until']])
    done_count = len([info for info in closed_tasks.values() 
                     if not info['snooze_until']])
    
    return {
        'active': active_count,
        'snoozed': snoozed_count, 
        'done': done_count
    }
    """
    Добавляет Toast-уведомление в очередь
    """
    try:
        toast = ToastNotification(title, message, category, task_id)
        toast_queue.put(toast)
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🍞 TOAST {category.upper()}: {title}")
    except Exception as e:
        print(f"❌ Ошибка добавления Toast-уведомления: {e}")
        # Fallback на системные уведомления
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Planfix Reminder",
                timeout=10
            )
        except:
            pass

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
        """
        if not self.user_id:
            self.get_current_user_id()
        
        print(f"👤 Пользователь: {self.user_name} (ID: {self.user_id})")
        print("📋 Получаем задачи где пользователь - исполнитель, постановщик или контролер")
        
        try:
            all_user_tasks = []
            
            # Фильтры для разных ролей
            filter_configs = [
                {
                    "name": "Исполнитель",
                    "filters": [
                        {
                            "type": 2,
                            "operator": "equal",
                            "value": f"user:{self.user_id}"
                        }
                    ]
                },
                {
                    "name": "Постановщик", 
                    "filters": [
                        {
                            "type": 3,
                            "operator": "equal",
                            "value": f"user:{self.user_id}"
                        }
                    ]
                },
                {
                    "name": "Контролер/Участник",
                    "filters": [
                        {
                            "type": 4,
                            "operator": "equal", 
                            "value": f"user:{self.user_id}"
                        }
                    ]
                }
            ]
            
            task_ids_seen = set()
            
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
            
            if not all_user_tasks:
                print("🔄 Фильтры не сработали, получаем все задачи и фильтруем вручную")
                all_user_tasks = self._get_all_tasks_and_filter_manually()
            
            # Фильтруем только незакрытые задачи
            active_tasks = []
            closed_statuses = ['Выполненная', 'Отменена', 'Закрыта', 'Завершена']
            
            for task in all_user_tasks:
                status = task.get('status', {})
                status_name = status.get('name', '') if isinstance(status, dict) else str(status)
                
                if status_name not in closed_statuses:
                    active_tasks.append(task)
            
            print(f"✅ Найдено активных задач для {self.user_name}: {len(active_tasks)}")
            
            if active_tasks:
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
                "pageSize": 200,
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
        Тестирует соединение с API
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
    """
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    
    categorized = {
        'overdue': [],
        'urgent': [],
        'current': []
    }
    
    closed_statuses = ['Выполненная', 'Отменена', 'Закрыта', 'Завершена']
    
    for task in tasks:
        try:
            status = task.get('status', {})
            status_name = status.get('name', '') if isinstance(status, dict) else str(status)
            
            if status_name in closed_statuses:
                continue
            
            if task.get('overdue', False):
                categorized['overdue'].append(task)
                continue
            
            end_date_info = task.get('endDateTime')
            end_date = None
            
            if end_date_info:
                if isinstance(end_date_info, dict):
                    date_str = (end_date_info.get('datetime') or 
                              end_date_info.get('date') or 
                              end_date_info.get('dateTimeUtcSeconds'))
                else:
                    date_str = str(end_date_info)
                
                if date_str:
                    try:
                        if 'T' in date_str:
                            end_date = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
                        elif '-' in date_str:
                            formats_to_try = ['%d-%m-%Y', '%Y-%m-%d', '%d-%m-%y']
                            for date_format in formats_to_try:
                                try:
                                    end_date = datetime.datetime.strptime(date_str, date_format).date()
                                    break
                                except ValueError:
                                    continue
                        elif '.' in date_str:
                            formats_to_try = ['%d.%m.%Y', '%d.%m.%y']
                            for date_format in formats_to_try:
                                try:
                                    end_date = datetime.datetime.strptime(date_str, date_format).date()
                                    break
                                except ValueError:
                                    continue
                    except Exception as e:
                        print(f"⚠️ Ошибка парсинга даты '{date_str}' для задачи {task.get('id')}: {e}")
            
            if not end_date:
                end_date_str = task.get('endDate', '')
                if end_date_str:
                    try:
                        if 'T' in end_date_str:
                            end_date = datetime.datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).date()
                        else:
                            for date_format in ['%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y']:
                                try:
                                    end_date = datetime.datetime.strptime(end_date_str, date_format).date()
                                    break
                                except ValueError:
                                    continue
                    except Exception:
                        pass
            
            if end_date:
                if end_date < today:
                    categorized['overdue'].append(task)
                elif end_date <= tomorrow:
                    categorized['urgent'].append(task)
                else:
                    categorized['current'].append(task)
            else:
                categorized['current'].append(task)
                
        except Exception as e:
            print(f"⚠️ Ошибка обработки задачи {task.get('id', 'Unknown')}: {e}")
            categorized['current'].append(task)
    
    return categorized

def show_toast_notification(title: str, message: str, category: str, task_id: str = None):
    """
    Добавляет Toast-уведомление в очередь (с проверкой нужно ли показывать)
    """
    # Проверяем нужно ли показывать уведомление
    if not should_show_notification(task_id, category):
        return False
    
    try:
        toast = ToastNotification(title, message, category, task_id)
        toast_queue.put(toast)
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🍞 TOAST {category.upper()}: {title}")
        return True
    except Exception as e:
        print(f"❌ Ошибка добавления Toast-уведомления: {e}")
        # Fallback на системные уведомления
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Planfix Reminder",
                timeout=10
            )
            return True
        except:
            return False

def format_task_message(task: Dict, category: str) -> tuple:
    """
    Форматирует сообщение для задачи
    """
    task_name = task.get('name', 'Задача без названия')
    
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
    
    # Обрабатываем исполнителей
    assignees = task.get('assignees', {})
    assignee_names = []
    if assignees:
        users = assignees.get('users', [])
        for user in users:
            name = user.get('name', f"ID:{user.get('id')}")
            assignee_names.append(name)
    
    assignee_text = ', '.join(assignee_names) if assignee_names else 'Не назначен'
    
    # Форматируем дату для отображения
    formatted_date = end_date_str
    if end_date_str and end_date_str not in ['Не указана', 'Указана']:
        try:
            if 'T' in end_date_str:
                date_obj = datetime.datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime('%d.%m.%Y')
            elif '-' in end_date_str and len(end_date_str) >= 8:
                for date_format in ['%d-%m-%Y', '%Y-%m-%d', '%d-%m-%y']:
                    try:
                        date_obj = datetime.datetime.strptime(end_date_str, date_format)
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        break
                    except ValueError:
                        continue
        except:
            formatted_date = end_date_str
    
    # Формируем заголовок
    title_prefix = {
        'overdue': '🔴 ПРОСРОЧЕНО',
        'urgent': '🟡 СРОЧНО', 
        'current': '📋 ЗАДАЧА'
    }.get(category, '📋 ЗАДАЧА')
    
    # Компактный заголовок для Toast
    safe_limit = 45  # Еще короче для Toast
    separator = ": "
    
    prefix_and_separator_length = len(title_prefix) + len(separator)
    max_task_name_length = safe_limit - prefix_and_separator_length
    
    if max_task_name_length <= 3:
        task_name_short = "..."
    elif len(task_name) > max_task_name_length:
        task_name_short = task_name[:max_task_name_length-3] + "..."
    else:
        task_name_short = task_name
    
    title = f"{title_prefix}{separator}{task_name_short}"
    
    # Компактное сообщение
    message_parts = [f"📅 {formatted_date}", f"👤 {assignee_text}"]
    message = '\n'.join(message_parts)
    
    return title, message

def load_config() -> tuple:
    """
    Загружает конфигурацию из файла
    """
    config = configparser.ConfigParser()
    config_file_path = 'config.ini'
    
    if not os.path.exists(config_file_path):
        print("❌ Файл конфигурации 'config.ini' не найден!")
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
                sys.exit(1)
            if not account_url.endswith('/rest'):
                print(f"⚠️ account_url '{account_url}' должен заканчиваться на '/rest'")
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
    print("🚀 Запуск Planfix Reminder с Toast-уведомлениями...")
    api_token, account_url, check_interval, notification_settings = load_config()
    planfix = PlanfixAPI(account_url, api_token)
    
    print(f"⚙️ Настройки:")
    print(f"   - Интервал проверки: {check_interval} сек")
    print(f"   - URL аккаунта: {account_url}")
    print(f"   - Уведомления: {notification_settings}")
    
    print("\n🔌 Тестирование соединения с Planfix...")
    if not planfix.test_connection():
        print("❌ Не удалось подключиться к Planfix API")
        sys.exit(1)
    
    print(f"✅ Мониторинг запущен! (Ctrl+C для остановки)")
    
    # Создаем менеджер Toast-уведомлений
    toast_manager = ToastManager()
    
    # Запускаем мониторинг задач в отдельном потоке
    def monitor_tasks():
        notified_tasks = set()  # Для совместимости, но теперь используем closed_tasks
        cleanup_counter = 0
        
        while True:
            try:
                tasks = planfix.get_current_user_tasks()
                if not tasks:
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📭 Активных задач не найдено")
                    time.sleep(check_interval)
                    continue
                    
                categorized_tasks = categorize_tasks(tasks)
                stats = {k: len(v) for k, v in categorized_tasks.items()}
                
                # Получаем сводку по уведомлениям
                notification_stats = get_notification_summary()
                
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📊 Задач: просрочено {stats['overdue']}, срочно {stats['urgent']}, текущие {stats['current']}")
                print(f"   🍞 Окна: активных {notification_stats['active']}, отложено {notification_stats['snoozed']}, завершено {notification_stats['done']}")
                
                new_notifications = 0
                for category, tasks_list in categorized_tasks.items():
                    if not notification_settings.get(category, True):
                        continue
                        
                    for task in tasks_list:
                        task_id = str(task.get('id'))
                        title, message = format_task_message(task, category)
                        
                        # Показываем уведомление только если нужно
                        if show_toast_notification(title, message, category, task_id):
                            new_notifications += 1
                            time.sleep(1)  # Пауза между уведомлениями
                
                if new_notifications == 0:
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ Новых уведомлений нет")
                else:
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🍞 Отправлено {new_notifications} Toast-уведомлений")
                
                # Очистка старых записей каждые 10 циклов
                cleanup_counter += 1
                if cleanup_counter >= 10:
                    cleanup_old_closed_tasks()
                    cleanup_counter = 0
                
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"❌ Ошибка в мониторинге: {e}")
                print("⏳ Попытка перезапуска через 30 секунд...")
                time.sleep(30)
    
    # Запускаем мониторинг в отдельном потоке
    monitor_thread = threading.Thread(target=monitor_tasks, daemon=True)
    monitor_thread.start()
    
    try:
        # Запускаем GUI в главном потоке
        toast_manager.run()
    except KeyboardInterrupt:
        print("\n👋 Planfix Reminder остановлен пользователем")
    except Exception as e:
        print(f"❌ Ошибка в GUI: {e}")

if __name__ == "__main__":
    main()