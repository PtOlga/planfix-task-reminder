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
import pystray
from PIL import Image, ImageDraw
import io
import base64
from pathlib import Path

# Глобальные переменные (все будут загружены из config.ini)
app_config = {
    'check_interval': 300,
    'max_windows_per_category': 5,
    'max_total_windows': 10,
    'notifications': {
        'current': True,
        'urgent': True,
        'overdue': True
    },
    'roles': {
        'include_assignee': True,
        'include_assigner': True,
        'include_auditor': True
    },
    'planfix': {
        'api_token': '',
        'account_url': '',
        'filter_id': None,
        'user_id': '1'
    }
}

# Глобальная очередь для Toast-уведомлений
toast_queue = queue.Queue()
# Список активных окон для управления позициями
active_windows = []
# Система отслеживания закрытых задач
closed_tasks = {}  # task_id: {'closed_time': datetime, 'snooze_until': datetime, 'auto_closed': bool}

# Глобальные переменные для трея
tray_icon = None
is_paused = False
pause_until = None
last_check_time = None
current_stats = {'total': 0, 'overdue': 0, 'urgent': 0}
planfix_api = None

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
            try:
                account_url = app_config['planfix']['account_url'].replace('/rest', '')
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
    
    if active_count >= app_config['max_total_windows']:
        return False
        
    if category_count >= app_config['max_windows_per_category']:
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
    def __init__(self):
        self.account_url = app_config['planfix']['account_url'].rstrip('/')
        self.api_token = app_config['planfix']['api_token']
        self.filter_id = app_config['planfix']['filter_id']
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_token}'
        })

    def get_filtered_tasks(self) -> List[Dict[Any, Any]]:
        """
        Получает задачи по фильтру ИЛИ по ролям пользователя
        """
        try:
            if self.filter_id:
                return self._get_tasks_by_filter()
            else:
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
        """Получает задачи по ролям пользователя"""
        user_id = app_config['planfix']['user_id']
        all_tasks = []
        task_ids_seen = set()
        
        # 1. Задачи где пользователь - ИСПОЛНИТЕЛЬ
        if app_config['roles']['include_assignee']:
            assignee_tasks = self._get_tasks_by_role_type(user_id, role_type=2)
            for task in assignee_tasks:
                task_id = task.get('id')
                if task_id not in task_ids_seen:
                    task_ids_seen.add(task_id)
                    all_tasks.append(task)
        
        # 2. Задачи где пользователь - POSTАНОВЩИК
        if app_config['roles']['include_assigner']:
            assigner_tasks = self._get_tasks_by_role_type(user_id, role_type=3)
            for task in assigner_tasks:
                task_id = task.get('id')
                if task_id not in task_ids_seen:
                    task_ids_seen.add(task_id)
                    all_tasks.append(task)
        
        # 3. Задачи где пользователь - КОНТРОЛЕР/УЧАСТНИК
        if app_config['roles']['include_auditor']:
            auditor_tasks = self._get_tasks_by_role_type(user_id, role_type=4)
            for task in auditor_tasks:
                task_id = task.get('id')
                if task_id not in task_ids_seen:
                    task_ids_seen.add(task_id)
                    all_tasks.append(task)
        
        return self._filter_active_tasks(all_tasks)

    def _get_tasks_by_role_type(self, user_id: str, role_type: int) -> List[Dict]:
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
        """Тестирует соединение с API"""
        try:
            if self.filter_id:
                payload = {
                    "offset": 0,
                    "pageSize": 1,
                    "filterId": int(self.filter_id),
                    "fields": "id,name"
                }
            else:
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
    
    closed_statuses = ['Выполненная', 'Отменена', 'Закрыта', 'Завершенная']
    
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

def load_config() -> bool:
    """
    Загружает конфигурацию из файла в глобальную переменную app_config
    С подробной диагностикой
    """
    global app_config
    
    print("=== ДИАГНОСТИКА ПОИСКА КОНФИГА ===")
    
    # Определяем возможные пути к конфигу
    script_dir = Path(__file__).parent.absolute()
    current_dir = Path.cwd()
    
    print(f"Текущая рабочая директория: {current_dir}")
    print(f"Директория скрипта: {script_dir}")
    print()
    
    config_paths = [
        current_dir / 'config.ini',
        script_dir / 'config.ini',
        Path('config.ini'),
    ]
    
    config_file_path = None
    
    # Ищем конфиг в разных местах
    for i, path in enumerate(config_paths, 1):
        print(f"🔍 Путь {i}: {path}")
        print(f"   Абсолютный: {path.absolute()}")
        print(f"   Существует: {path.exists()}")
        
        if path.exists():
            try:
                size = path.stat().st_size
                print(f"   ✅ Размер: {size} байт")
                config_file_path = path
                break
            except Exception as e:
                print(f"   ❌ Ошибка доступа: {e}")
        else:
            print(f"   ❌ Файл не найден")
        print()
    
    if not config_file_path:
        print("🚨 ФАЙЛ CONFIG.INI НЕ НАЙДЕН!")
        
        print(f"\n📂 Содержимое текущей директории ({current_dir}):")
        try:
            for item in sorted(current_dir.iterdir()):
                if item.is_file():
                    print(f"   📄 {item.name}")
                else:
                    print(f"   📁 {item.name}/")
        except Exception as e:
            print(f"   ❌ Ошибка чтения: {e}")
        
        if current_dir != script_dir:
            print(f"\n📂 Содержимое директории скрипта ({script_dir}):")
            try:
                for item in sorted(script_dir.iterdir()):
                    if item.is_file():
                        print(f"   📄 {item.name}")
                    else:
                        print(f"   📁 {item.name}/")
            except Exception as e:
                print(f"   ❌ Ошибка чтения: {e}")
        
        return False
    
    print(f"✅ НАЙДЕН CONFIG.INI: {config_file_path}")
    
    # Читаем конфиг с разными кодировками
    config = configparser.ConfigParser()
    encodings_to_try = ['utf-8', 'cp1251', 'windows-1251', 'latin-1']
    
    config_loaded = False
    for encoding in encodings_to_try:
        try:
            print(f"Пробую кодировку: {encoding}")
            config.read(str(config_file_path), encoding=encoding)
            
            # Проверяем что секции загрузились
            sections = config.sections()
            print(f"  Найдены секции: {sections}")
            
            if 'Planfix' not in sections:
                print(f"  ❌ Секция [Planfix] не найдена")
                continue
                
            # Проверяем обязательные поля
            api_token = config.get('Planfix', 'api_token', fallback='')
            account_url = config.get('Planfix', 'account_url', fallback='')
            
            print(f"  API Token: {'***' + api_token[-4:] if len(api_token) > 4 else 'НЕ ЗАДАН'}")
            print(f"  Account URL: {account_url}")
            
            if not api_token or api_token in ['ВАШ_API_ТОКЕН', 'YOUR_API_TOKEN', 'YOUR_API_TOKEN_HERE']:
                print(f"  ❌ API токен не настроен")
                continue
                
            if not account_url.endswith('/rest'):
                print(f"  ❌ URL должен заканчиваться на /rest")
                continue
            
            config_loaded = True
            print(f"  ✅ Конфиг успешно загружен с кодировкой {encoding}")
            break
            
        except Exception as e:
            print(f"  ❌ Ошибка с кодировкой {encoding}: {e}")
            continue
    
    if not config_loaded:
        print("❌ НЕ УДАЛОСЬ ЗАГРУЗИТЬ КОНФИГ!")
        return False
    
    try:
        # Загружаем настройки
        app_config['planfix']['api_token'] = config['Planfix']['api_token']
        app_config['planfix']['account_url'] = config['Planfix']['account_url']
        app_config['planfix']['filter_id'] = config.get('Planfix', 'filter_id', fallback=None)
        app_config['planfix']['user_id'] = config.get('Planfix', 'user_id', fallback='1')
        
        # Очищаем filter_id если он пустой
        if app_config['planfix']['filter_id'] == '':
            app_config['planfix']['filter_id'] = None
        
        # Загружаем настройки уведомлений
        app_config['check_interval'] = int(config.get('Settings', 'check_interval', fallback=300))
        app_config['max_windows_per_category'] = int(config.get('Settings', 'max_windows_per_category', fallback=5))
        app_config['max_total_windows'] = int(config.get('Settings', 'max_total_windows', fallback=10))
        
        app_config['notifications']['current'] = config.getboolean('Settings', 'notify_current', fallback=True)
        app_config['notifications']['urgent'] = config.getboolean('Settings', 'notify_urgent', fallback=True)
        app_config['notifications']['overdue'] = config.getboolean('Settings', 'notify_overdue', fallback=True)
        
        # Загружаем настройки ролей
        if config.has_section('Roles'):
            app_config['roles']['include_assignee'] = config.getboolean('Roles', 'include_assignee', fallback=True)
            app_config['roles']['include_assigner'] = config.getboolean('Roles', 'include_assigner', fallback=True)
            app_config['roles']['include_auditor'] = config.getboolean('Roles', 'include_auditor', fallback=True)
        
        print("✅ Все настройки успешно загружены")
        print(f"   Filter ID: {app_config['planfix']['filter_id'] or 'НЕ ИСПОЛЬЗУЕТСЯ'}")
        print(f"   User ID: {app_config['planfix']['user_id']}")
        print("=" * 35)
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при загрузке настроек: {e}")
        return False

# ========================================
# ФУНКЦИИ СИСТЕМНОГО ТРЕЯ
# ========================================

def create_tray_icon():
    """Создает иконку для системного трея"""
    # Создаем простую иконку программно
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Определяем цвет по состоянию
    global current_stats, is_paused
    
    if is_paused:
        color = (128, 128, 128)  # Серый - на паузе
    elif current_stats['overdue'] > 0:
        color = (255, 68, 68)    # Красный - есть просроченные
    elif current_stats['urgent'] > 0:
        color = (255, 136, 0)    # Оранжевый - есть срочные
    else:
        color = (0, 200, 0)      # Зеленый - все хорошо
    
    # Рисуем круг
    draw.ellipse([8, 8, 56, 56], fill=color, outline=(255, 255, 255), width=2)
    
    # Добавляем букву P
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = None
    
    draw.text((32, 32), "P", fill=(255, 255, 255), anchor="mm", font=font)
    
    return image

def update_tray_icon():
    """Обновляет иконку в трее"""
    global tray_icon
    if tray_icon:
        tray_icon.icon = create_tray_icon()

def get_tray_menu():
    """Создает меню для системного трея"""
    global is_paused, current_stats, last_check_time
    
    # Формируем строку состояния
    if is_paused:
        if pause_until:
            pause_str = f"На паузе до {pause_until.strftime('%H:%M')}"
        else:
            pause_str = "На паузе"
        status_item = pystray.MenuItem(f"⏸️ {pause_str}", None, enabled=False)
    else:
        total = current_stats['total']
        overdue = current_stats['overdue']
        status_item = pystray.MenuItem(f"🟢 Активен ({total} задач, {overdue} просроч.)", None, enabled=False)
    
    # Время последней проверки
    if last_check_time:
        time_str = last_check_time.strftime('%H:%M:%S')
        last_check_item = pystray.MenuItem(f"Последняя проверка: {time_str}", None, enabled=False)
    else:
        last_check_item = pystray.MenuItem("Еще не проверялось", None, enabled=False)
    
    # Создаем меню
    menu = pystray.Menu(
        status_item,
        last_check_item,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("📊 Проверить сейчас", lambda: check_tasks_now()),
        pystray.MenuItem("⏸️ Пауза на 1 час", lambda: pause_monitoring(60)) if not is_paused else pystray.MenuItem("▶️ Возобновить", lambda: resume_monitoring()),
        pystray.MenuItem("⏸️ Пауза до завтра 9:00", lambda: pause_until_tomorrow()) if not is_paused else None,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🌐 Открыть Planfix", lambda: open_planfix()),
        pystray.MenuItem("📖 Инструкция", lambda: show_help()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ Выход", lambda: quit_application()),
    )
    
    return menu

def check_tasks_now():
    """Принудительно проверяет задачи сейчас"""
    global last_check_time
    try:
        if planfix_api:
            tasks = planfix_api.get_filtered_tasks()
            categorized_tasks = categorize_tasks(tasks)
            
            # Обновляем статистику
            current_stats['total'] = len(tasks)
            current_stats['overdue'] = len(categorized_tasks['overdue'])
            current_stats['urgent'] = len(categorized_tasks['urgent'])
            
            # Показываем уведомления
            new_notifications = 0
            for category, tasks_list in categorized_tasks.items():
                if not app_config['notifications'].get(category, True):
                    continue
                    
                for task in tasks_list:
                    task_id = str(task.get('id'))
                    title, message = format_task_message(task, category)
                    
                    if show_toast_notification(title, message, category, task_id):
                        new_notifications += 1
                        time.sleep(0.5)
            
            last_check_time = datetime.datetime.now()
            update_tray_icon()
            
            # Показываем balloon tip с результатом
            if tray_icon:
                if new_notifications > 0:
                    tray_icon.notify(f"Найдено {new_notifications} новых уведомлений", "Planfix Reminder")
                else:
                    tray_icon.notify(f"Найдено {len(tasks)} задач, новых уведомлений нет", "Planfix Reminder")
                    
    except Exception as e:
        if tray_icon:
            tray_icon.notify(f"Ошибка проверки: {str(e)[:50]}", "Planfix Reminder")

def pause_monitoring(minutes: int):
    """Ставит мониторинг на паузу"""
    global is_paused, pause_until
    is_paused = True
    pause_until = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
    update_tray_icon()
    
    if tray_icon:
        tray_icon.notify(f"Мониторинг приостановлен на {minutes} минут", "Planfix Reminder")

def pause_until_tomorrow():
    """Ставит на паузу до завтра 9:00"""
    global is_paused, pause_until
    is_paused = True
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    pause_until = datetime.datetime.combine(tomorrow, datetime.time(9, 0))
    update_tray_icon()
    
    if tray_icon:
        tray_icon.notify("Мониторинг приостановлен до завтра 9:00", "Planfix Reminder")

def resume_monitoring():
    """Возобновляет мониторинг"""
    global is_paused, pause_until
    is_paused = False
    pause_until = None
    update_tray_icon()
    
    if tray_icon:
        tray_icon.notify("Мониторинг возобновлен", "Planfix Reminder")

def open_planfix():
    """Открывает Planfix в браузере"""
    try:
        url = app_config['planfix']['account_url'].replace('/rest', '')
        webbrowser.open(url)
    except Exception:
        webbrowser.open("https://planfix.com")

def show_help():
    """Показывает справку"""
    help_text = """
Planfix Reminder - Справка

УПРАВЛЕНИЕ:
• Двойной клик по иконке - проверить задачи
• ПКМ по иконке - меню управления
• Пауза - временно отключить уведомления
• Выход - полностью закрыть программу

ЦВЕТА ИКОНКИ:
🟢 Зеленый - все в порядке
🟡 Оранжевый - есть срочные задачи
🔴 Красный - есть просроченные задачи
⚫ Серый - на паузе

УВЕДОМЛЕНИЯ:
• Красные - просроченные задачи
• Оранжевые - срочные (сегодня/завтра)
• Синие - обычные задачи

Настройки в файле config.ini
    """
    
    # Создаем простое окно справки
    help_window = tk.Tk()
    help_window.title("Справка - Planfix Reminder")
    help_window.geometry("500x400")
    help_window.resizable(False, False)
    
    text_widget = tk.Text(help_window, wrap=tk.WORD, padx=10, pady=10)
    text_widget.pack(fill=tk.BOTH, expand=True)
    text_widget.insert(tk.END, help_text)
    text_widget.config(state=tk.DISABLED)
    
    help_window.mainloop()

def quit_application():
    """Выходит из приложения"""
    global tray_icon
    if tray_icon:
        tray_icon.stop()
    os._exit(0)

def on_double_click(icon, item):
    """Обработка двойного клика по иконке"""
    check_tasks_now()

def create_and_run_tray():
    """Создает и запускает системный трей"""
    global tray_icon
    
    tray_icon = pystray.Icon(
        name="Planfix Reminder",
        icon=create_tray_icon(),
        title="Planfix Reminder",
        menu=get_tray_menu()
    )
    
    # Обновляем меню каждые 30 секунд
    def update_menu():
        while True:
            time.sleep(30)
            if tray_icon:
                tray_icon.menu = get_tray_menu()
    
    threading.Thread(target=update_menu, daemon=True).start()
    
    # Запускаем трей
    tray_icon.run_detached()

def main():
    """
    Основная функция программы с системным треем
    """
    global planfix_api, current_stats, last_check_time
    
    print("🚀 Запуск Planfix Reminder...")
    print("=" * 40)
    
    # Загружаем конфигурацию
    print("📋 Загрузка конфигурации...")
    if not load_config():
        print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить конфигурацию!")
        
        try:
            import tkinter.messagebox as msgbox
            root = tk.Tk()
            root.withdraw()
            
            msgbox.showerror("Ошибка конфигурации", 
                           "Не удалось загрузить config.ini\n\n"
                           "Проверьте:\n"
                           "• Файл config.ini существует\n"
                           "• API токен настроен\n"
                           "• URL заканчивается на /rest")
            root.destroy()
        except:
            pass
        
        input("\nНажмите Enter для выхода...")
        return
    
    print("✅ Конфигурация загружена успешно")
    
    # Создаем API клиент
    print("\n🌐 Подключение к Planfix API...")
    planfix_api = PlanfixAPI()
    
    # Тестируем соединение
    print("🔄 Проверка подключения...")
    if not planfix_api.test_connection():
        print("❌ Не удалось подключиться к Planfix API")
        
        try:
            import tkinter.messagebox as msgbox
            root = tk.Tk()
            root.withdraw()
            
            msgbox.showerror("Ошибка подключения", 
                           "Не удалось подключиться к Planfix API\n\n"
                           "Проверьте:\n"
                           "• Интернет соединение\n"
                           "• Правильность API токена\n"
                           "• Доступность сервера Planfix")
            root.destroy()
        except:
            pass
        
        input("\nНажмите Enter для выхода...")
        return
    
    print("✅ Подключение к API успешно!")
    
    print(f"\n🎯 Настройки:")
    print(f"   Filter ID: {app_config['planfix']['filter_id'] or 'НЕ ИСПОЛЬЗУЕТСЯ'}")
    print(f"   User ID: {app_config['planfix']['user_id']}")
    print(f"   Интервал проверки: {app_config['check_interval']} сек")
    
    print("\n🎯 Создание системного трея...")
    # Создаем и запускаем системный трей
    try:
        create_and_run_tray()
        print("✅ Системный трей создан")
    except Exception as e:
        print(f"❌ Ошибка создания трея: {e}")
    
    print("\n📬 Создание менеджера уведомлений...")
    # Создаем менеджер Toast-уведомлений
    try:
        toast_manager = ToastManager()
        print("✅ Менеджер уведомлений создан")
    except Exception as e:
        print(f"❌ Ошибка создания менеджера уведомлений: {e}")
        return
    
    print(f"\n⏰ Запуск мониторинга")
    print("🎉 Приложение готово к работе!")
    print("=" * 40)
    
    # Запускаем мониторинг задач в отдельном потоке
    def monitor_tasks():
        global current_stats, last_check_time, is_paused, pause_until
        cleanup_counter = 0
        
        while True:
            try:
                # Проверяем не на паузе ли мы
                if is_paused:
                    if pause_until and datetime.datetime.now() >= pause_until:
                        # Время паузы истекло
                        resume_monitoring()
                    else:
                        # Все еще на паузе
                        time.sleep(60)  # Проверяем каждую минуту
                        continue
                
                cleanup_closed_windows()
                
                # Получаем задачи
                tasks = planfix_api.get_filtered_tasks()
                if not tasks:
                    print("ℹ️ Задач не найдено или ошибка получения")
                    time.sleep(app_config['check_interval'])
                    continue
                    
                categorized_tasks = categorize_tasks(tasks)
                
                # Обновляем статистику
                current_stats['total'] = len(tasks)
                current_stats['overdue'] = len(categorized_tasks.get('overdue', []))
                current_stats['urgent'] = len(categorized_tasks.get('urgent', []))
                
                print(f"📊 Найдено задач: {current_stats['total']} (просрочено: {current_stats['overdue']}, срочно: {current_stats['urgent']})")
                
                # Показываем уведомления
                new_notifications = 0
                for category, tasks_list in categorized_tasks.items():
                    if not app_config['notifications'].get(category, True):
                        continue
                        
                    for task in tasks_list:
                        task_id = str(task.get('id'))
                        title, message = format_task_message(task, category)
                        
                        if show_toast_notification(title, message, category, task_id):
                            new_notifications += 1
                            print(f"📬 Показано уведомление: {category} - {task.get('name', 'Без названия')}")
                        time.sleep(1)
                
                if new_notifications == 0:
                    print("📭 Новых уведомлений нет")
                
                last_check_time = datetime.datetime.now()
                update_tray_icon()
                
                # Периодическая очистка
                cleanup_counter += 1
                if cleanup_counter >= 10:
                    cleanup_old_closed_tasks()
                    cleanup_counter = 0
                
                time.sleep(app_config['check_interval'])
                
            except Exception as e:
                print(f"❌ Ошибка в мониторинге: {e}")
                time.sleep(30)
    
    monitor_thread = threading.Thread(target=monitor_tasks, daemon=True)
    monitor_thread.start()
    
    try:
        # Запускаем GUI в главном потоке
        print("🖥️ Запуск интерфейса...")
        toast_manager.run()
    except KeyboardInterrupt:
        print("\n⏹️ Остановка по Ctrl+C")
    except Exception as e:
        print(f"\n❌ Критическая ошибка GUI: {e}")
    finally:
        print("🔄 Завершение работы...")
        quit_application()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        input("\nНажмите Enter для выхода...")
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
        sys.exit(0)