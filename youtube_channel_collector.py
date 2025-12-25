"""
YouTube Transcript Collector v2.0 with Proxy & Delays
Сбор транскриптов с YouTube каналов с защитой от банов
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import time
import random
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import requests


class ProxyManager:
    """Управление прокси с ротацией"""
    
    def __init__(self):
        self.proxies: List[str] = []
        self.current_index = 0
        self.requests_count = 0
        self.rotation_interval = 10
        self.consecutive_errors = 0
        self.paused = False
    
    def load_proxies(self, file_path: str):
        """Загрузить прокси из файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            self.current_index = 0
            self.consecutive_errors = 0
            return len(self.proxies)
        except Exception as e:
            raise Exception(f"Ошибка загрузки прокси: {e}")
    
    def get_current_proxy(self) -> Optional[str]:
        """Получить текущий прокси"""
        if not self.proxies:
            return None
        return self.proxies[self.current_index]
    
    def rotate_proxy(self):
        """Сменить прокси"""
        if not self.proxies:
            return
        
        self.current_index = (self.current_index + 1) % len(self.proxies)
        self.requests_count = 0
    
    def report_success(self):
        """Отметить успешный запрос"""
        self.requests_count += 1
        self.consecutive_errors = 0
        
        if self.requests_count >= self.rotation_interval:
            self.rotate_proxy()
    
    def report_error(self) -> str:
        """Отметить ошибку"""
        self.consecutive_errors += 1
        self.rotate_proxy()  # Моментальная смена!
        
        if self.consecutive_errors >= 3:
            self.paused = True
            return "pause"
        
        return "rotate"
    
    def resume(self):
        """Возобновить работу"""
        self.paused = False
        self.consecutive_errors = 0
    
    def get_proxy_dict(self) -> Optional[Dict[str, str]]:
        """Получить прокси для requests"""
        proxy = self.get_current_proxy()
        if not proxy:
            return None
        
        if not proxy.startswith(('http://', 'https://', 'socks5://', 'socks4://')):
            proxy = f'http://{proxy}'
        
        return {
            'http': proxy,
            'https': proxy
        }


class YouTubeChannelCollector:
    """Сбор транскриптов с YouTube каналов"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_channel_videos(self, channel_id: str, max_results: int = 50, 
                          min_duration: int = 0, proxies: Optional[Dict] = None) -> List[Dict]:
        """Получить список видео канала через YouTube Data API"""
        try:
            # Получаем uploads playlist ID
            url = "https://www.googleapis.com/youtube/v3/channels"
            params = {
                'part': 'contentDetails',
                'id': channel_id,
                'key': self.api_key
            }
            
            response = self.session.get(url, params=params, proxies=proxies, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'items' not in data or len(data['items']) == 0:
                raise Exception(f"Канал {channel_id} не найден")
            
            uploads_playlist = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # Получаем видео из playlist
            videos = []
            next_page_token = None
            
            while len(videos) < max_results:
                url = "https://www.googleapis.com/youtube/v3/playlistItems"
                params = {
                    'part': 'contentDetails',
                    'playlistId': uploads_playlist,
                    'maxResults': min(50, max_results - len(videos)),
                    'key': self.api_key
                }
                
                if next_page_token:
                    params['pageToken'] = next_page_token
                
                response = self.session.get(url, params=params, proxies=proxies, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                video_ids = [item['contentDetails']['videoId'] for item in data.get('items', [])]
                
                if not video_ids:
                    break
                
                # Получаем детали видео (duration, title)
                url = "https://www.googleapis.com/youtube/v3/videos"
                params = {
                    'part': 'contentDetails,snippet',
                    'id': ','.join(video_ids),
                    'key': self.api_key
                }
                
                response = self.session.get(url, params=params, proxies=proxies, timeout=30)
                response.raise_for_status()
                video_data = response.json()
                
                for item in video_data.get('items', []):
                    duration = self._parse_duration(item['contentDetails']['duration'])
                    
                    if duration >= min_duration:
                        videos.append({
                            'video_id': item['id'],
                            'title': item['snippet']['title'],
                            'duration': duration,
                            'published_at': item['snippet']['publishedAt']
                        })
                
                next_page_token = data.get('nextPageToken')
                if not next_page_token:
                    break
            
            return videos[:max_results]
        
        except Exception as e:
            raise Exception(f"Ошибка получения видео канала {channel_id}: {e}")
    
    def _parse_duration(self, duration_str: str) -> int:
        """Парсинг ISO 8601 duration в минуты"""
        import re
        
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)
        
        if not match:
            return 0
        
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        
        return hours * 60 + minutes + (1 if seconds > 30 else 0)
    
    def get_transcript(self, video_id: str, proxies: Optional[Dict] = None) -> Optional[List[Dict]]:
        """Получить транскрипт видео"""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            
            # Получаем транскрипт (приоритет английскому)
            transcript = YouTubeTranscriptApi.get_transcript(
                video_id,
                languages=['en', 'ru', 'es', 'fr', 'de']
            )
            
            return transcript
        
        except Exception as e:
            return None
    
    def format_transcript(self, transcript: List[Dict]) -> str:
        """Форматировать транскрипт в текст"""
        lines = []
        for entry in transcript:
            text = entry.get('text', '')
            lines.append(text)
        return ' '.join(lines)


class YouTubeCollectorGUI(tk.Tk):
    """GUI для YouTube Transcript Collector"""
    
    def __init__(self):
        super().__init__()
        
        self.title("YouTube Transcript Collector v2.0 Pro")
        self.geometry("700x850")
        
        # Менеджеры
        self.proxy_manager = ProxyManager()
        self.collector = None
        self.stop_event = threading.Event()
        self.worker_thread = None
        
        # Переменные
        self.api_key_file = tk.StringVar()
        self.output_file = tk.StringVar(value="transcripts_output.txt")
        self.channel_ids = tk.StringVar()
        self.video_count = tk.IntVar(value=100)
        self.min_duration = tk.IntVar(value=10)
        self.keyword = tk.StringVar()
        
        # Настройки прокси и задержек
        self.proxy_file = tk.StringVar()
        self.rotation_interval = tk.IntVar(value=10)
        self.delay_min = tk.IntVar(value=3)
        self.delay_max = tk.IntVar(value=10)
        
        # Создаем GUI
        self.create_gui()
    
    def create_gui(self):
        """Создать интерфейс"""
        
        # Заголовок
        header = tk.Label(
            self,
            text="YouTube Transcript Collector Pro",
            font=("Arial", 16, "bold"),
            bg="#4285F4",
            fg="white",
            pady=10
        )
        header.pack(fill=tk.X)
        
        # Основная рамка
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # ===== ОСНОВНЫЕ НАСТРОЙКИ =====
        settings_frame = ttk.LabelFrame(main_frame, text="Основные настройки", padding=10)
        settings_frame.pack(fill=tk.X, pady=5)
        
        # ID каналов
        ttk.Label(settings_frame, text="ID каналов (через запятую):").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(settings_frame, textvariable=self.channel_ids, width=50).grid(row=0, column=1, pady=5, padx=5)
        
        # API ключ
        ttk.Label(settings_frame, text="Файл с API ключом (.txt):").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(settings_frame, textvariable=self.api_key_file, width=40).grid(row=1, column=1, pady=5, padx=5)
        ttk.Button(settings_frame, text="Выбрать", command=self.select_api_file).grid(row=1, column=2, padx=5)
        
        # Куда сохранить
        ttk.Label(settings_frame, text="Куда сохранить файл:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(settings_frame, textvariable=self.output_file, width=40).grid(row=2, column=1, pady=5, padx=5)
        ttk.Button(settings_frame, text="Выбрать", command=self.select_output_file).grid(row=2, column=2, padx=5)
        
        # Количество видео
        ttk.Label(settings_frame, text="Количество видео:").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(settings_frame, from_=1, to=500, textvariable=self.video_count, width=20).grid(row=3, column=1, sticky=tk.W, pady=5, padx=5)
        
        # Минимальная длительность
        ttk.Label(settings_frame, text="Минимальная длительность (минут):").grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(settings_frame, from_=0, to=180, textvariable=self.min_duration, width=20).grid(row=4, column=1, sticky=tk.W, pady=5, padx=5)
        
        # Ключевое слово
        ttk.Label(settings_frame, text="Ключевое слово (например, META):").grid(row=5, column=0, sticky=tk.W, pady=5)
        ttk.Entry(settings_frame, textvariable=self.keyword, width=30).grid(row=5, column=1, sticky=tk.W, pady=5, padx=5)
        
        # ===== НАСТРОЙКИ ПРОКСИ =====
        proxy_frame = ttk.LabelFrame(main_frame, text="🌐 Настройки прокси (защита от банов)", padding=10)
        proxy_frame.pack(fill=tk.X, pady=5)
        
        # Файл прокси
        ttk.Label(proxy_frame, text="Файл прокси:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(proxy_frame, textvariable=self.proxy_file, width=40).grid(row=0, column=1, pady=5, padx=5)
        ttk.Button(proxy_frame, text="Выбрать", command=self.select_proxy_file).grid(row=0, column=2, padx=5)
        ttk.Button(proxy_frame, text="Загрузить", command=self.load_proxies).grid(row=0, column=3, padx=5)
        
        # Интервал ротации
        ttk.Label(proxy_frame, text="Ротация каждые (запросов):").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(proxy_frame, from_=5, to=50, textvariable=self.rotation_interval, width=10).grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)
        
        # Статус прокси
        self.proxy_status_label = ttk.Label(proxy_frame, text="Прокси не загружены", foreground="red")
        self.proxy_status_label.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=5)
        
        # ===== НАСТРОЙКИ ЗАДЕРЖЕК =====
        delay_frame = ttk.LabelFrame(main_frame, text="⏱️ Задержки между запросами", padding=10)
        delay_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(delay_frame, text="Задержка min (сек):").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(delay_frame, from_=1, to=30, textvariable=self.delay_min, width=10).grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        
        ttk.Label(delay_frame, text="Задержка max (сек):").grid(row=0, column=2, sticky=tk.W, pady=5, padx=(20, 0))
        ttk.Spinbox(delay_frame, from_=1, to=60, textvariable=self.delay_max, width=10).grid(row=0, column=3, sticky=tk.W, pady=5, padx=5)
        
        # ===== КНОПКИ УПРАВЛЕНИЯ =====
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        self.start_button = ttk.Button(
            control_frame,
            text="Собрать (Pro)",
            command=self.start_collection
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(
            control_frame,
            text="⏸ Остановить",
            command=self.stop_collection,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            control_frame,
            text="🔄 Перезагрузить прокси",
            command=self.reload_proxies
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            control_frame,
            text="▶ Продолжить",
            command=self.resume_work
        ).pack(side=tk.LEFT, padx=5)
        
        # ===== ЛОГ =====
        log_frame = ttk.LabelFrame(main_frame, text="Лог", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=80)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # ===== СТАТУС =====
        self.status_label = ttk.Label(self, text="Готово", font=('Arial', 10))
        self.status_label.pack(pady=10)
    
    def log(self, message: str, level: str = "INFO"):
        """Вывести сообщение в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        icons = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "ERROR": "❌",
            "WARNING": "⚠️",
            "PROXY": "🌐"
        }
        
        icon = icons.get(level, "ℹ️")
        log_message = f"[{timestamp}] {icon} {message}\n"
        
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.log_text.update()
    
    def select_api_file(self):
        """Выбрать файл с API ключом"""
        filename = filedialog.askopenfilename(
            title="Выберите файл с API ключом",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            self.api_key_file.set(filename)
    
    def select_output_file(self):
        """Выбрать файл для сохранения"""
        filename = filedialog.asksaveasfilename(
            title="Сохранить как",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            self.output_file.set(filename)
    
    def select_proxy_file(self):
        """Выбрать файл с прокси"""
        filename = filedialog.askopenfilename(
            title="Выберите файл с прокси",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            self.proxy_file.set(filename)
    
    def load_proxies(self):
        """Загрузить прокси"""
        proxy_file = self.proxy_file.get()
        
        if not proxy_file:
            messagebox.showerror("Ошибка", "Выберите файл с прокси!")
            return
        
        try:
            count = self.proxy_manager.load_proxies(proxy_file)
            self.proxy_manager.rotation_interval = self.rotation_interval.get()
            
            self.proxy_status_label.config(
                text=f"Загружено прокси: {count}",
                foreground="green"
            )
            
            self.log(f"Загружено {count} прокси из {proxy_file}", "SUCCESS")
        
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            self.log(f"Ошибка загрузки прокси: {e}", "ERROR")
    
    def reload_proxies(self):
        """Перезагрузить прокси"""
        if self.proxy_file.get():
            self.load_proxies()
            self.log("Прокси перезагружены", "SUCCESS")
    
    def resume_work(self):
        """Возобновить работу"""
        self.proxy_manager.resume()
        self.log("Работа возобновлена", "SUCCESS")
    
    def smart_delay(self):
        """Умная задержка"""
        delay = random.uniform(self.delay_min.get(), self.delay_max.get())
        
        # Иногда длинная пауза
        if random.random() < 0.05:
            delay += random.uniform(10, 30)
        
        time.sleep(delay)
    
    def start_collection(self):
        """Начать сбор"""
        # Проверки
        if not self.channel_ids.get().strip():
            messagebox.showwarning("Внимание", "Введите ID каналов!")
            return
        
        if not self.api_key_file.get():
            messagebox.showwarning("Внимание", "Выберите файл с API ключом!")
            return
        
        # Загружаем API ключ
        try:
            with open(self.api_key_file.get(), 'r', encoding='utf-8') as f:
                api_key = f.read().strip()
            
            self.collector = YouTubeChannelCollector(api_key)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить API ключ:\n{e}")
            return
        
        # Запуск
        self.stop_event.clear()
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        self.worker_thread = threading.Thread(
            target=self.collection_worker,
            daemon=True
        )
        self.worker_thread.start()
    
    def stop_collection(self):
        """Остановить сбор"""
        self.stop_event.set()
        self.log("Остановка...", "WARNING")
    
    def collection_worker(self):
        """Рабочий поток сбора"""
        try:
            # Парсим каналы
            channels = [ch.strip() for ch in self.channel_ids.get().split(',') if ch.strip()]
            
            self.log(f"Начало сбора с {len(channels)} каналов", "INFO")
            
            all_transcripts = []
            total_videos = 0
            
            for channel_id in channels:
                if self.stop_event.is_set():
                    break
                
                # Проверка паузы
                while self.proxy_manager.paused and not self.stop_event.is_set():
                    self.log("⏸ ПАУЗА: 3 ошибки подряд! Смените прокси и нажмите 'Продолжить'", "ERROR")
                    self.status_label.config(text="⏸ ПАУЗА - Ожидание оператора")
                    time.sleep(1)
                
                if self.stop_event.is_set():
                    break
                
                self.log(f"Обработка канала: {channel_id}", "INFO")
                
                try:
                    # Получаем прокси
                    proxies = self.proxy_manager.get_proxy_dict()
                    
                    if proxies:
                        self.log(f"Используем прокси: {self.proxy_manager.get_current_proxy()}", "PROXY")
                    
                    # Получаем видео канала
                    videos = self.collector.get_channel_videos(
                        channel_id,
                        max_results=self.video_count.get(),
                        min_duration=self.min_duration.get(),
                        proxies=proxies
                    )
                    
                    self.proxy_manager.report_success()
                    
                    self.log(f"Найдено {len(videos)} видео", "SUCCESS")
                    
                    # Обрабатываем каждое видео
                    for idx, video in enumerate(videos, 1):
                        if self.stop_event.is_set():
                            break
                        
                        # Проверка паузы
                        while self.proxy_manager.paused and not self.stop_event.is_set():
                            time.sleep(1)
                        
                        if self.stop_event.is_set():
                            break
                        
                        self.log(f"[{idx}/{len(videos)}] {video['title']}", "INFO")
                        
                        try:
                            # Получаем прокси
                            proxies = self.proxy_manager.get_proxy_dict()
                            
                            # Получаем транскрипт
                            transcript = self.collector.get_transcript(
                                video['video_id'],
                                proxies=proxies
                            )
                            
                            if transcript:
                                text = self.collector.format_transcript(transcript)
                                
                                # Фильтрация по ключевому слову
                                keyword = self.keyword.get().strip()
                                if keyword:
                                    if keyword.lower() in text.lower():
                                        all_transcripts.append({
                                            'channel_id': channel_id,
                                            'video_id': video['video_id'],
                                            'title': video['title'],
                                            'transcript': text
                                        })
                                        total_videos += 1
                                        self.log(f"✅ Найдено ключевое слово '{keyword}'", "SUCCESS")
                                else:
                                    all_transcripts.append({
                                        'channel_id': channel_id,
                                        'video_id': video['video_id'],
                                        'title': video['title'],
                                        'transcript': text
                                    })
                                    total_videos += 1
                                
                                self.proxy_manager.report_success()
                            else:
                                self.log(f"⚠️ Транскрипт недоступен", "WARNING")
                            
                            # Задержка
                            if idx < len(videos):
                                self.smart_delay()
                        
                        except Exception as e:
                            self.log(f"❌ Ошибка: {e}", "ERROR")
                            
                            action = self.proxy_manager.report_error()
                            
                            if action == "rotate":
                                self.log("Смена прокси...", "PROXY")
                            
                            time.sleep(random.uniform(2, 5))
                
                except Exception as e:
                    self.log(f"❌ Ошибка канала {channel_id}: {e}", "ERROR")
                    
                    action = self.proxy_manager.report_error()
                    
                    if action == "rotate":
                        self.log("Смена прокси...", "PROXY")
                
                # Задержка между каналами
                if channels.index(channel_id) < len(channels) - 1:
                    time.sleep(random.uniform(5, 15))
            
            # Сохраняем результаты
            if all_transcripts:
                output_path = self.output_file.get()
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    for item in all_transcripts:
                        f.write(f"="*80 + "\n")
                        f.write(f"Channel: {item['channel_id']}\n")
                        f.write(f"Video ID: {item['video_id']}\n")
                        f.write(f"Title: {item['title']}\n")
                        f.write(f"="*80 + "\n\n")
                        f.write(item['transcript'])
                        f.write("\n\n\n")
                
                self.log("="*50, "INFO")
                self.log(f"Завершено! Собрано транскриптов: {total_videos}", "SUCCESS")
                self.log(f"Сохранено в: {output_path}", "SUCCESS")
                
                messagebox.showinfo(
                    "Готово",
                    f"Собрано транскриптов: {total_videos}\n"
                    f"Сохранено в: {output_path}"
                )
            else:
                self.log("Транскрипты не найдены", "WARNING")
                messagebox.showwarning("Внимание", "Транскрипты не найдены")
        
        except Exception as e:
            self.log(f"Критическая ошибка: {e}", "ERROR")
            messagebox.showerror("Ошибка", str(e))
        
        finally:
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_label.config(text="Готово")


if __name__ == "__main__":
    app = YouTubeCollectorGUI()
    app.mainloop()
