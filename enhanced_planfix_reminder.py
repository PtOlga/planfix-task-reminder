# ОСНОВНЫЕ ИЗМЕНЕНИЯ В ЭТОЙ ВЕРСИИ:
# 1. Добавлена поддержка filter_id из config.ini
# 2. Новый метод get_filtered_tasks() вместо get_current_user_tasks()
# 3. Убрана логика определения user_id из токена
# 4. Исправлен список закрытых статусов: "Завершенная" вместо "Завершена"

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

# --- Конфигурация (будет загружаться из config.ini) ---
CHECK_INTERVAL_SECONDS = 300  # По умолчанию 5 минут (будет перезаписано из config)
MAX_WINDOWS_PER_CATEGORY = 5  # По умолчанию (будет перезаписано из config)
MAX_TOTAL_WINDOWS = 10        # По умолчанию (будет перезаписано из config)

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
                'duration': None,
                'sound': True,
                'sound_type': 'critical'
            },
            'urgent': {
                'bg_color': '#FF8800',
                'text_color': 'white',
                'border_color': '#CC4400', 
                'duration': None,
                'sound': True,
                'sound_type': 'warning'
            },
            'current': {
                'bg_color': '#0066CC',
                'text_color': 'white',
                'border_color': '#003388',
                'duration': None,
                'sound': False,
                'sound_type': None
            }
        }
        
    def create_window(self, master_root):
        """Создает окно уведомления в главном потоке"""
        self.root = tk.Toplevel(master_root)
        self.root.withdraw()
        
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.95)
        
        style = self.styles.get(self.category, self.styles['current'])
        
        window_width = 320
        window_height = 140
        
        x, y = self._calculate_position(window_width, window_height)
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        container = tk.Frame(
            self.root, 
            bg=style['border_color'], 
            relief='raised',
            bd=2
        )
        container.pack(fill='both', expand=True, padx=2, pady=2)
        
        title_bar = tk.Frame(container, bg=style['bg_color'], height=25)
        title_bar.pack(fill='x', padx=1, pady=(1, 0))
        title_bar.pack_propagate(False)
        
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
        
        task_id_label = tk.Label(
            title_bar,
            text=f"#{self.task_id}" if self.task_id else "",
            font=('Arial', 8),
            fg=style['text_color'],
            bg=style['bg_color']
        )
        task_id_label.pack(side='left', padx=(5, 0), pady=2)
        
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
        
        title_bar.bind("<Button-1>", self._start_drag)
        title_bar.bind("<B1-Motion>", self._on_drag)
        icon_label.bind("<Button-1>", self._start_drag)
        icon_label.bind("<B1-Motion>", self._on_drag)
        task_id_label.bind("<Button-1>", self._start_drag) 
        task_id_label.bind("<B1-Motion>", self._on_drag)
        
        content_frame = tk.Frame(container, bg=style['bg_color'], padx=8, pady=5)
        content_frame.pack(fill='both', expand=True, padx=1, pady=(0, 1))
        
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
        
        button_frame = tk.Frame(content_frame, bg=style['bg_color'])
        button_frame.pack(fill='x')
        
        if self.task_id:
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
        
        active_windows.append(self)
        
        if style['sound']:
            threading.Thread(target=self._play_sound, args=(style['sound_type'],), daemon=True).start()
        
        self.root.deiconify()
        self._animate_in()
    
    def _calculate_position(self, width, height):
        """Вычисляет позицию окна с учетом уже открытых окон"""
        screen_width = 1920
        screen_height = 1080
        
        start_x = screen_width - width - 20
        start_y = 20
        
        offset_x = 10
        offset_y = 30
        
        same_category_count = len([w for w in active_windows if w.category == self.category and not w.is_closed])
        
        x = start_x - (same_category_count * offset_x)
        y = start_y + (same_category_count * offset_y)
        
        if y + height > screen_height - 50:
            y = 20
            x = start_x - 200
        
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
                for _ in range(3):
                    winsound.MessageBeep(winsound.MB_ICONHAND)
                    time.sleep(0.3)
            elif sound_type == 'warning':
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
    
    def _open_task(self):
        """Открывает задачу в браузере"""
        if self.task_id:
            config = configparser.ConfigParser()
            try:
                config.read('config.ini', encoding='utf-8')
                account_url = config['Planfix']['account_url'].replace('/rest', '')
                task_url = f"{account_url}/task/{self.task_id}/"
                webbrowser.open(task_url)
            except Exception:
                task_url = f"https://planfix.com/task/{self.task_id}/"
                webbrowser.open(task_url)
    
    def _snooze(self):
        """Откладывает уведомление на 15 минут"""
        if self.task_id:
            snooze_until = datetime.datetime.now() + datetime.timedelta(minutes=15)
            closed_tasks[self.task_id] = {
                'closed_time': datetime.datetime.now(),
                'snooze_until': snooze_until,
                'auto_closed': False
            }
        self._close()
    
    def _remind_later(self):
        """Напоминает позже (через 1 час)"""
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
        if self.task_id:
            closed_tasks[self.task_id] = {
                'closed_time': datetime.datetime.now(),
                'snooze_until': None,
                'auto_closed': False
            }
        self._close()
    
    def _close(self):
        """Закрывает уведомление"""
        self.is_closed = True
        
        if self.task_id and self.task_id not in closed_tasks:
            if self.category == 'overdue':
                reshow_minutes = 5
            elif self.category == 'urgent':
                reshow_minutes = 15
            else:
                reshow_minutes = 30
                
            snooze_until = datetime.datetime.now() + datetime.timedelta(minutes=reshow_minutes)
            closed_tasks[self.task_id] = {
                'closed_time': datetime.datetime.now(),
                'snooze_until': snooze_until,
                'auto_closed': False
            }
        
        if self in active_windows:
            active_windows.remove(self)
        
        if self.root:
            try:
                self.root.destroy()
            except tk.TclError:
                pass

class ToastManager:
    """
    Менеджер Toast-уведомлений, работающий в главном потоке
    """
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Planfix Reminder")
        self.check_queue()
        
    def check_queue(self):
        """Проверяет очередь уведомлений"""
        try:
            while True:
                toast = toast_queue.get_nowait()
                toast.create_window(self.root)
        except queue.Empty:
            pass
        
        self.root.after(100, self.check_queue)
    
    def run(self):
        """Запускает цикл обработки событий"""
        self.root.mainloop()

def cleanup_closed_windows():
    """
    Удаляет закрытые окна из списка активных
    """
    global active_windows
    active_windows = [w for w in active_windows if not w.is_closed]

def should_show_notification(task_id: str, category: str) -> bool:
    """
    Определяет нужно ли показывать уведомление для задачи
    """
    if not task_id:
        return True
    
    cleanup_closed_windows()
    
    # 1. ПРОВЕРЯЕМ УЖЕ ОТКРЫТЫЕ ОКНА
    for window in active_windows:
        if window.task_id == task_id:
            return False
    
    # 2. ПРОВЕРЯЕМ ЛИМИТЫ ОКОН
    active_count = len(active_windows)
    category_count = len([w for w in active_windows if w.category == category])
    
    if active_count >= MAX_TOTAL_WINDOWS:
        return False
        
    if category_count >= MAX_WINDOWS_PER_CATEGORY:
        return False
    
    # 3. Проверяем есть ли задача в списке закрытых
    if task_id not in closed_tasks:
        return True
    
    task_info = closed_tasks[task_id]
    now = datetime.datetime.now()
    
    # 4. Если задача отложена и время еще не пришло
    if task_info['snooze_until'] and now < task_info['snooze_until']:
        return False
    
    # 5. Если время отложения прошло - удаляем из списка и показываем
    if task_info['snooze_until'] and now >= task_info['snooze_until']:
        del closed_tasks[task_id]
        return True
    
    # 6. Если задача помечена как "Готово"
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
        if now - task_info['closed_time'] > datetime.timedelta(hours=24):
            to_remove.append(task_id)
    
    for task_id in to_remove:
        del closed_tasks[task_id]

class PlanfixAPI:
    def __init__(self, account_url: str, api_token: str, filter_id: str = None):
        self.account_url = account_url.rstrip('/')
        self.api_token = api_token
        self.filter_id = filter_id  # НОВЫЙ ПАРАМЕТР - ID фильтра из config.ini
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_token}'
        })

    def get_filtered_tasks(self) -> List[Dict[Any, Any]]:
        """
        ОБНОВЛЕНО: Получает задачи по фильтру ИЛИ по ролям пользователя
        """
        try:
            if self.filter_id:
                # Используем готовый фильтр из Planfix
                return self._get_tasks_by_filter()
            else:
                # Используем настройки ролей из конфига
                return self._get_tasks_by_roles()
                
        except Exception:
            return []

    def _get_tasks_by_filter(self) -> List[Dict[Any, Any]]:
        """Получает задачи по готовому фильтру Planfix"""
        try:
            payload = {
                "offset": 0,
                "pageSize": 100,
                "filterId": int(self.filter_id),
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
                    all_tasks = data.get('tasks', [])
                    return self._filter_active_tasks(all_tasks)
            
            return []
            
        except Exception:
            return []

    def _get_tasks_by_roles(self) -> List[Dict[Any, Any]]:
        """Получает задачи по ролям пользователя (исполнитель/постановщик/контролер)"""
        # Загружаем настройки ролей из конфига
        config = configparser.ConfigParser()
        try:
            config.read('config.ini', encoding='utf-8')
            user_id = config.get('Planfix', 'user_id', fallback='1')
            include_assignee = config.getboolean('Roles', 'include_assignee', fallback=True)
            include_assigner = config.getboolean('Roles', 'include_assigner', fallback=True) 
            include_auditor = config.getboolean('Roles', 'include_auditor', fallback=True)
        except Exception:
            # Fallback настройки
            user_id = '1'
            include_assignee = True
            include_assigner = True
            include_auditor = True
        
        all_tasks = []
        task_ids_seen = set()
        
        # 1. Задачи где пользователь - ИСПОЛНИТЕЛЬ
        if include_assignee:
            assignee_tasks = self._get_tasks_by_role_type(user_id, role_type=2, role_name="Исполнитель")
            for task in assignee_tasks:
                task_id = task.get('id')
                if task_id not in task_ids_seen:
                    task_ids_seen.add(task_id)
                    all_tasks.append(task)
        
        # 2. Задачи где пользователь - ПОСТАНОВЩИК
        if include_assigner:
            assigner_tasks = self._get_tasks_by_role_type(user_id, role_type=3, role_name="Постановщик")
            for task in assigner_tasks:
                task_id = task.get('id')
                if task_id not in task_ids_seen:
                    task_ids_seen.add(task_id)
                    all_tasks.append(task)
        
        # 3. Задачи где пользователь - КОНТРОЛЕР/УЧАСТНИК
        if include_auditor:
            auditor_tasks = self._get_tasks_by_role_type(user_id, role_type=4, role_name="Контролер")
            for task in auditor_tasks:
                task_id = task.get('id')
                if task_id not in task_ids_seen:
                    task_ids_seen.add(task_id)
                    all_tasks.append(task)
        
        return self._filter_active_tasks(all_tasks)

    def _get_tasks_by_role_type(self, user_id: str, role_type: int, role_name: str) -> List[Dict]:
        """Получает задачи по конкретному типу роли"""
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
                    return data.get('tasks', [])
            
            return []
            
        except Exception:
            return []

    def _filter_active_tasks(self, all_tasks: List[Dict]) -> List[Dict]:
        """Фильтрует только активные задачи (убирает закрытые)"""
        active_tasks = []
        closed_statuses = ['Выполненная', 'Отменена', 'Закрыта', 'Завершенная']
        
        for task in all_tasks:
            status = task.get('status', {})
            status_name = status.get('name', '') if isinstance(status, dict) else str(status)
            
            if status_name not in closed_statuses:
                active_tasks.append(task)
        
        return active_tasks

    def test_connection(self) -> bool:
        """
        Тестирует соединение с API и корректность фильтра
        """
        try:
            if self.filter_id:
                # Тестируем с фильтром
                payload = {
                    "offset": 0,
                    "pageSize": 1,
                    "filterId": int(self.filter_id),
                    "fields": "id,name"
                }
            else:
                # Тестируем базовое подключение
                payload = {
                    "offset": 0,
                    "pageSize": 1,
                    "fields": "id,name"
                }
            
            response = self.session.post(
                f"{self.account_url}/task/list",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('result') == 'fail':
                    return False
                return True
            else:
                return False
        except Exception:
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
    
    closed_statuses = ['Выполненная', 'Отменена', 'Закрыта', 'Завершенная']  # ИСПРАВЛЕНО: "Завершенная"
    
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
                    except Exception:
                        pass
            
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
                
        except Exception:
            categorized['current'].append(task)
    
    return categorized

def show_toast_notification(title: str, message: str, category: str, task_id: str = None):
    """
    Добавляет Toast-уведомление в очередь (с проверкой нужно ли показывать)
    """
    if not should_show_notification(task_id, category):
        return False
    
    try:
        toast = ToastNotification(title, message, category, task_id)
        toast_queue.put(toast)
        return True
    except Exception:
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Planfix Reminder",
                timeout=10
            )
            return True
        except Exception:
            return False

def format_task_message(task: Dict, category: str) -> tuple:
    """
    Форматирует сообщение для задачи
    """
    task_name = task.get('name', 'Задача без названия')
    
    end_date_info = task.get('endDateTime')
    end_date_str = 'Не указана'
    
    if end_date_info:
        if isinstance(end_date_info, dict):
            end_date_str = (end_date_info.get('date') or 
                          end_date_info.get('datetime') or 
                          'Указана')
        else:
            end_date_str = str(end_date_info)
    
    assignees = task.get('assignees', {})
    assignee_names = []
    if assignees:
        users = assignees.get('users', [])
        for user in users:
            name = user.get('name', f"ID:{user.get('id')}")
            assignee_names.append(name)
    
    assignee_text = ', '.join(assignee_names) if assignee_names else 'Не назначен'
    
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
        except Exception:
            formatted_date = end_date_str
    
    title_prefix = {
        'overdue': '🔴 ПРОСРОЧЕНО',
        'urgent': '🟡 СРОЧНО', 
        'current': '📋 ЗАДАЧА'
    }.get(category, '📋 ЗАДАЧА')
    
    safe_limit = 45
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
    
    message_parts = [f"📅 {formatted_date}", f"👤 {assignee_text}"]
    message = '\n'.join(message_parts)
    
    return title, message

def load_config() -> tuple:
    """
    ОБНОВЛЕНО: Загружает конфигурацию из файла (с поддержкой всех параметров + ролей)
    """
    global CHECK_INTERVAL_SECONDS, MAX_WINDOWS_PER_CATEGORY, MAX_TOTAL_WINDOWS
    
    config = configparser.ConfigParser()
    config_file_path = 'config.ini'
    
    if not os.path.exists(config_file_path):
        return None, None, None, None, None
    
    encodings_to_try = ['utf-8', 'cp1251', 'windows-1251', 'latin-1']
    
    for encoding in encodings_to_try:
        try:
            config.read(config_file_path, encoding=encoding)
            
            # Основные параметры Planfix
            api_token = config['Planfix']['api_token']
            account_url = config['Planfix']['account_url']
            filter_id = config.get('Planfix', 'filter_id', fallback=None)
            
            # Настройки уведомлений
            check_interval = int(config.get('Settings', 'check_interval', fallback=300))
            notification_settings = {
                'current': config.getboolean('Settings', 'notify_current', fallback=True),
                'urgent': config.getboolean('Settings', 'notify_urgent', fallback=True),
                'overdue': config.getboolean('Settings', 'notify_overdue', fallback=True)
            }
            
            # Лимиты окон
            max_windows_per_category = int(config.get('Settings', 'max_windows_per_category', fallback=5))
            max_total_windows = int(config.get('Settings', 'max_total_windows', fallback=10))
            
            # НОВЫЕ НАСТРОЙКИ: Роли пользователя (если нет filter_id)
            role_settings = {
                'include_assignee': config.getboolean('Roles', 'include_assignee', fallback=True),
                'include_assigner': config.getboolean('Roles', 'include_assigner', fallback=True),
                'include_auditor': config.getboolean('Roles', 'include_auditor', fallback=True),
                'user_id': config.get('Planfix', 'user_id', fallback='1')
            }
            
            # Обновляем глобальные переменные
            CHECK_INTERVAL_SECONDS = check_interval
            MAX_WINDOWS_PER_CATEGORY = max_windows_per_category
            MAX_TOTAL_WINDOWS = max_total_windows
            
            # Проверки корректности
            if not api_token or api_token in ['ВАШ_API_ТОКЕН', 'ВАШ_API_ТОКЕН_ЗДЕСЬ', 'YOUR_API_TOKEN_HERE', 'YOUR_SHARED_API_TOKEN_HERE']:
                return None, None, None, None, None
                
            if not account_url.endswith('/rest'):
                return None, None, None, None, None
                
            return api_token, account_url, filter_id, check_interval, notification_settings
            
        except Exception:
            continue
    
    return None, None, None, None, None

def main():
    """
    ОБНОВЛЕНО: Основная функция программы (с поддержкой фильтров)
    """
    config_result = load_config()
    if not all(config_result[:4]):  # Проверяем первые 4 элемента (filter_id может быть None)
        return
        
    api_token, account_url, filter_id, check_interval, notification_settings = config_result
    planfix = PlanfixAPI(account_url, api_token, filter_id)  # ПЕРЕДАЕМ filter_id
    
    if not planfix.test_connection():
        return
    
    toast_manager = ToastManager()
    
    def monitor_tasks():
        cleanup_counter = 0
        
        while True:
            try:
                cleanup_closed_windows()
                
                # ИСПОЛЬЗУЕМ НОВЫЙ МЕТОД
                tasks = planfix.get_filtered_tasks()
                if not tasks:
                    time.sleep(check_interval)
                    continue
                    
                categorized_tasks = categorize_tasks(tasks)
                
                for category, tasks_list in categorized_tasks.items():
                    if not notification_settings.get(category, True):
                        continue
                        
                    for task in tasks_list:
                        task_id = str(task.get('id'))
                        title, message = format_task_message(task, category)
                        
                        show_toast_notification(title, message, category, task_id)
                        time.sleep(1)
                
                cleanup_counter += 1
                if cleanup_counter >= 10:
                    cleanup_old_closed_tasks()
                    cleanup_counter = 0
                
                time.sleep(check_interval)
                
            except Exception:
                time.sleep(30)
    
    monitor_thread = threading.Thread(target=monitor_tasks, daemon=True)
    monitor_thread.start()
    
    try:
        toast_manager.run()
    except KeyboardInterrupt:
        pass
    except Exception:
        pass

if __name__ == "__main__":
    main()