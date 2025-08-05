#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика проблемы с config.ini
Запустите этот скрипт в папке с основным кодом
"""

import os
import sys
from pathlib import Path
import configparser

def diagnose_config():
    print("🔍 ДИАГНОСТИКА CONFIG.INI")
    print("=" * 50)
    
    # Определяем пути
    script_dir = Path(__file__).parent.absolute()
    current_dir = Path.cwd()
    
    print(f"📁 Директория скрипта: {script_dir}")
    print(f"📁 Текущая директория: {current_dir}")
    print()
    
    # Ищем config.ini
    config_paths = [
        current_dir / 'config.ini',
        script_dir / 'config.ini',
        Path('config.ini')
    ]
    
    config_found = None
    
    for i, path in enumerate(config_paths, 1):
        print(f"🔍 Путь {i}: {path}")
        print(f"   Абсолютный: {path.absolute()}")
        print(f"   Существует: {path.exists()}")
        
        if path.exists():
            try:
                size = path.stat().st_size
                print(f"   ✅ Размер: {size} байт")
                config_found = path
                break
            except Exception as e:
                print(f"   ❌ Ошибка доступа: {e}")
        else:
            print(f"   ❌ Файл не найден")
        print()
    
    if not config_found:
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
    
    print(f"✅ НАЙДЕН CONFIG.INI: {config_found}")
    
    # Читаем содержимое
    print(f"\n📖 СОДЕРЖИМОЕ ФАЙЛА:")
    print("-" * 30)
    try:
        with open(config_found, 'r', encoding='utf-8') as f:
            content = f.read()
            print(content)
    except UnicodeDecodeError:
        try:
            with open(config_found, 'r', encoding='cp1251') as f:
                content = f.read()
                print(content)
                print("⚠️  Файл в кодировке CP1251")
        except Exception as e:
            print(f"❌ Ошибка чтения файла: {e}")
            return False
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        return False
    
    print("-" * 30)
    
    # Парсим конфиг
    print(f"\n🔧 ПАРСИНГ КОНФИГУРАЦИИ:")
    config = configparser.ConfigParser()
    
    encodings = ['utf-8', 'cp1251', 'windows-1251']
    parsed = False
    
    for encoding in encodings:
        try:
            print(f"   Пробую кодировку: {encoding}")
            config.read(str(config_found), encoding=encoding)
            
            sections = config.sections()
            print(f"   ✅ Секции: {sections}")
            
            if 'Planfix' in sections:
                api_token = config.get('Planfix', 'api_token', fallback='')
                account_url = config.get('Planfix', 'account_url', fallback='')
                filter_id = config.get('Planfix', 'filter_id', fallback='')
                user_id = config.get('Planfix', 'user_id', fallback='')
                
                print(f"   API Token: {'***' + api_token[-4:] if len(api_token) > 4 else 'НЕ ЗАДАН'}")
                print(f"   Account URL: {account_url}")
                print(f"   Filter ID: {filter_id if filter_id else 'НЕ ЗАДАН'}")
                print(f"   User ID: {user_id}")
                
                # Проверяем корректность
                issues = []
                
                if not api_token or api_token in ['ВАШ_API_ТОКЕН', 'YOUR_API_TOKEN']:
                    issues.append("API токен не настроен")
                
                if not account_url:
                    issues.append("Account URL не задан")
                elif not account_url.endswith('/rest'):
                    issues.append("Account URL должен заканчиваться на /rest")
                
                if not filter_id and not user_id:
                    issues.append("Должен быть задан либо filter_id, либо user_id")
                
                if issues:
                    print(f"   ❌ ПРОБЛЕМЫ:")
                    for issue in issues:
                        print(f"      • {issue}")
                    return False
                else:
                    print(f"   ✅ Конфигурация корректна!")
                    parsed = True
                    break
            else:
                print(f"   ❌ Секция [Planfix] не найдена")
                
        except Exception as e:
            print(f"   ❌ Ошибка парсинга с {encoding}: {e}")
    
    if not parsed:
        print(f"\n❌ НЕ УДАЛОСЬ РАСПАРСИТЬ КОНФИГ!")
        return False
    
    print(f"\n🎉 ВСЁ В ПОРЯДКЕ!")
    print(f"   Файл найден: {config_found}")
    print(f"   Конфигурация корректна")
    print(f"   Готов к запуску основной программы")
    
    return True

if __name__ == "__main__":
    try:
        diagnose_config()
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    input("\nНажмите Enter для выхода...")