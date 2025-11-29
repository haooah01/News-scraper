import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import queue
import asyncio
from datetime import datetime
from PIL import Image, ImageTk
import io
import json
import requests
from urllib.request import urlopen
from bs4 import BeautifulSoup
import feedparser
import re
import webbrowser

class NewsScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Ứng dụng Thu thập Tin tức & Hình ảnh")
        self.root.geometry("1400x800")
        
        # Queue để xử lý dữ liệu giữa các luồng
        self.data_queue = queue.Queue()
        self.image_queue = queue.Queue()
        
        # Thread control
        self.running = False
        self.loop = None
        
        self.setup_ui()
        
    def setup_ui(self):
        """Thiết lập giao diện 3 cột"""
        # Main container với PanedWindow để có thể resize
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Cột 1: Bài báo (40% width)
        article_frame = ttk.LabelFrame(main_paned, text="📰 Bài báo", padding=5)
        main_paned.add(article_frame, weight=4)
        
        # Canvas với scrollbar cho bài báo
        article_canvas_frame = ttk.Frame(article_frame)
        article_canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.article_canvas = tk.Canvas(article_canvas_frame, bg="white")
        article_scrollbar = ttk.Scrollbar(article_canvas_frame, orient=tk.VERTICAL, 
                                         command=self.article_canvas.yview)
        self.article_scrollable = ttk.Frame(self.article_canvas)
        
        self.article_scrollable.bind(
            "<Configure>",
            lambda e: self.article_canvas.configure(scrollregion=self.article_canvas.bbox("all"))
        )
        
        self.article_canvas.create_window((0, 0), window=self.article_scrollable, anchor="nw")
        self.article_canvas.configure(yscrollcommand=article_scrollbar.set)
        
        self.article_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        article_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind mousewheel
        self.article_canvas.bind_all("<Button-4>", lambda e: self.article_canvas.yview_scroll(-1, "units"))
        self.article_canvas.bind_all("<Button-5>", lambda e: self.article_canvas.yview_scroll(1, "units"))
        
        # Cột 2: Nội dung chi tiết (30% width)
        content_frame = ttk.LabelFrame(main_paned, text="📄 Nội dung", padding=5)
        main_paned.add(content_frame, weight=3)
        
        self.content_text = scrolledtext.ScrolledText(
            content_frame,
            wrap=tk.WORD,
            width=35,
            height=35,
            font=("Arial", 9)
        )
        self.content_text.pack(fill=tk.BOTH, expand=True)
        
        # Cột 3: Ngày giờ & Hình ảnh (30% width)
        media_frame = ttk.LabelFrame(main_paned, text="🕒 Thời gian & 🖼️ Hình ảnh", padding=5)
        main_paned.add(media_frame, weight=3)
        
        # Khung thời gian
        time_subframe = ttk.Frame(media_frame)
        time_subframe.pack(fill=tk.X, pady=5)
        
        ttk.Label(time_subframe, text="Thời gian cập nhật:", font=("Arial", 9, "bold")).pack(anchor=tk.W)
        self.time_label = ttk.Label(time_subframe, text="--:--:--", font=("Arial", 12))
        self.time_label.pack(anchor=tk.W, pady=2)
        
        # Canvas cho hình ảnh với scrollbar
        canvas_frame = ttk.Frame(media_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.image_canvas = tk.Canvas(canvas_frame, bg="white")
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.image_canvas.yview)
        self.scrollable_frame = ttk.Frame(self.image_canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.image_canvas.configure(scrollregion=self.image_canvas.bbox("all"))
        )
        
        self.image_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.image_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.image_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind mousewheel cho smooth scrolling
        self.image_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # Không cần configure grid weights vì dùng PanedWindow
        
        # Control panel
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.start_btn = ttk.Button(control_frame, text="▶ Bắt đầu", command=self.start_scraping)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="⏹ Dừng", command=self.stop_scraping, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(control_frame, text="Nguồn:").pack(side=tk.LEFT, padx=5)
        self.source_var = tk.StringVar(value="vnexpress")
        sources = [
            ("VnExpress", "vnexpress"),
            ("Tuổi Trẻ", "tuoitre"),
            ("Thanh Niên", "thanhnien"),
            ("BBC News", "bbc"),
            ("RSS Mix", "rss")
        ]
        for text, value in sources:
            ttk.Radiobutton(control_frame, text=text, variable=self.source_var, 
                          value=value).pack(side=tk.LEFT, padx=2)
        
        self.status_label = ttk.Label(control_frame, text="⚪ Sẵn sàng", foreground="gray")
        self.status_label.pack(side=tk.RIGHT, padx=5)
        
        # Image storage
        self.image_references = []
        self.article_thumbnails = []
        self.article_image_urls = []
        
    def _on_mousewheel(self, event):
        """Xử lý cuộn chuột mượt mà"""
        self.image_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
    def start_scraping(self):
        """Bắt đầu thu thập dữ liệu"""
        if not self.running:
            self.running = True
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_label.config(text="🟢 Đang chạy...", foreground="green")
            
            # Xóa dữ liệu cũ
            for widget in self.article_scrollable.winfo_children():
                widget.destroy()
            self.content_text.delete(1.0, tk.END)
            self.image_references.clear()
            self.article_thumbnails.clear()
            self.article_image_urls.clear()
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            
            # Bắt đầu thread mới
            thread = threading.Thread(target=self.run_async_scraping, daemon=True)
            thread.start()
            
            # Bắt đầu xử lý queue
            self.process_queue()
    
    def stop_scraping(self):
        """Dừng thu thập dữ liệu"""
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="🔴 Đã dừng", foreground="red")
        
    def run_async_scraping(self):
        """Chạy scraping trong thread riêng sử dụng requests (đồng bộ nhưng trong thread riêng)"""
        # Thread cho bài báo
        article_thread = threading.Thread(target=self.fetch_articles_sync, daemon=True)
        article_thread.start()
        
        # Thread cho hình ảnh
        image_thread = threading.Thread(target=self.fetch_images_sync, daemon=True)
        image_thread.start()
    
    def fetch_articles_sync(self):
        """Thu thập bài báo từng cái một (đồng bộ)"""
        try:
            source = self.source_var.get()
            articles = []
            
            if source == "vnexpress":
                articles = self.scrape_vnexpress()
            elif source == "tuoitre":
                articles = self.scrape_tuoitre()
            elif source == "thanhnien":
                articles = self.scrape_thanhnien()
            elif source == "bbc":
                articles = self.scrape_bbc()
            elif source == "rss":
                articles = self.scrape_rss()
            
            # Xử lý từng bài một để tránh lag
            for i, article in enumerate(articles[:15]):  # Giới hạn 15 bài
                if not self.running:
                    break
                    
                self.data_queue.put({
                    'type': 'article',
                    'data': article,
                    'index': i + 1
                })
                
                # Delay nhỏ giữa các bài
                threading.Event().wait(0.3)
        except Exception as e:
            self.data_queue.put({'type': 'error', 'message': f"Lỗi bài báo: {str(e)}"})
    
    def scrape_vnexpress(self):
        """Scrape tin tức từ VnExpress RSS"""
        articles = []
        try:
            feed = feedparser.parse('https://vnexpress.net/rss/tin-moi-nhat.rss')
            for entry in feed.entries:
                # Extract image từ description
                img_url = self.extract_image_from_description(entry.description if hasattr(entry, 'description') else '')
                
                articles.append({
                    'title': entry.title,
                    'body': entry.description if hasattr(entry, 'description') else 'Không có mô tả',
                    'link': entry.link,
                    'published': entry.published if hasattr(entry, 'published') else 'N/A',
                    'id': entry.id if hasattr(entry, 'id') else 'N/A',
                    'image': img_url
                })
        except Exception as e:
            print(f"Error scraping VnExpress: {e}")
        return articles
    
    def scrape_tuoitre(self):
        """Scrape tin tức từ Tuổi Trẻ RSS"""
        articles = []
        try:
            feed = feedparser.parse('https://tuoitre.vn/rss/tin-moi-nhat.rss')
            for entry in feed.entries:
                img_url = self.extract_image_from_description(entry.description if hasattr(entry, 'description') else '')
                
                articles.append({
                    'title': entry.title,
                    'body': entry.description if hasattr(entry, 'description') else 'Không có mô tả',
                    'link': entry.link,
                    'published': entry.published if hasattr(entry, 'published') else 'N/A',
                    'id': entry.id if hasattr(entry, 'id') else 'N/A',
                    'image': img_url
                })
        except Exception as e:
            print(f"Error scraping Tuoi Tre: {e}")
        return articles
    
    def scrape_thanhnien(self):
        """Scrape tin tức từ Thanh Niên RSS"""
        articles = []
        try:
            feed = feedparser.parse('https://thanhnien.vn/rss/home.rss')
            for entry in feed.entries:
                img_url = self.extract_image_from_description(entry.description if hasattr(entry, 'description') else '')
                
                articles.append({
                    'title': entry.title,
                    'body': entry.description if hasattr(entry, 'description') else 'Không có mô tả',
                    'link': entry.link,
                    'published': entry.published if hasattr(entry, 'published') else 'N/A',
                    'id': entry.id if hasattr(entry, 'id') else 'N/A',
                    'image': img_url
                })
        except Exception as e:
            print(f"Error scraping Thanh Nien: {e}")
        return articles
    
    def scrape_bbc(self):
        """Scrape tin tức từ BBC News RSS"""
        articles = []
        try:
            feed = feedparser.parse('http://feeds.bbci.co.uk/news/rss.xml')
            for entry in feed.entries:
                img_url = self.extract_image_from_description(entry.description if hasattr(entry, 'description') else '')
                if not img_url and hasattr(entry, 'media_thumbnail'):
                    img_url = entry.media_thumbnail[0]['url'] if entry.media_thumbnail else None
                
                articles.append({
                    'title': entry.title,
                    'body': entry.description if hasattr(entry, 'description') else 'No description',
                    'link': entry.link,
                    'published': entry.published if hasattr(entry, 'published') else 'N/A',
                    'id': entry.id if hasattr(entry, 'id') else 'N/A',
                    'image': img_url
                })
        except Exception as e:
            print(f"Error scraping BBC: {e}")
        return articles
    
    def scrape_rss(self):
        """Scrape từ nhiều nguồn RSS"""
        articles = []
        rss_feeds = [
            'https://vnexpress.net/rss/tin-moi-nhat.rss',
            'https://tuoitre.vn/rss/tin-moi-nhat.rss',
            'http://feeds.bbci.co.uk/news/rss.xml'
        ]
        
        for feed_url in rss_feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:5]:  # 5 bài từ mỗi nguồn
                    img_url = self.extract_image_from_description(entry.description if hasattr(entry, 'description') else '')
                    
                    articles.append({
                        'title': entry.title,
                        'body': entry.description if hasattr(entry, 'description') else 'Không có mô tả',
                        'link': entry.link,
                        'published': entry.published if hasattr(entry, 'published') else 'N/A',
                        'id': entry.id if hasattr(entry, 'id') else 'N/A',
                        'image': img_url
                    })
            except Exception as e:
                print(f"Error with feed {feed_url}: {e}")
        
        return articles
    
    def extract_image_from_description(self, description):
        """Trích xuất URL hình ảnh từ description HTML"""
        try:
            if not description:
                return None
            soup = BeautifulSoup(description, 'html.parser')
            img = soup.find('img')
            if img and img.get('src'):
                return img.get('src')
        except Exception as e:
            print(f"Error extracting image: {e}")
        return None
    
    def fetch_images_sync(self):
        """Thu thập hình ảnh từng cái một (đồng bộ)"""
        try:
            # Sử dụng API placeholder cho hình ảnh
            image_url_template = "https://picsum.photos/300/200?random="
            
            for i in range(15):  # 15 hình ảnh
                if not self.running:
                    break
                
                image_url = f"{image_url_template}{i}"
                
                try:
                    response = requests.get(image_url, timeout=10)
                    if response.status_code == 200:
                        image_data = response.content
                        self.image_queue.put({
                            'type': 'image',
                            'data': image_data,
                            'index': i + 1
                        })
                except Exception as e:
                    print(f"Error loading image {i}: {e}")
                
                # Delay giữa các request để tránh lag
                threading.Event().wait(0.5)
                
        except Exception as e:
            self.data_queue.put({'type': 'error', 'message': f"Lỗi hình ảnh: {str(e)}"})
    
    def process_queue(self):
        """Xử lý queue và cập nhật UI"""
        try:
            # Xử lý bài báo
            while not self.data_queue.empty():
                item = self.data_queue.get_nowait()
                
                if item['type'] == 'article':
                    self.add_article(item['data'], item['index'])
                elif item['type'] == 'error':
                    self.show_error(item['message'])
            
            # Xử lý hình ảnh
            while not self.image_queue.empty():
                item = self.image_queue.get_nowait()
                
                if item['type'] == 'image':
                    self.add_image(item['data'], item['index'])
            
            # Update thời gian
            current_time = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
            self.time_label.config(text=current_time)
            
        except queue.Empty:
            pass
        
        # Tiếp tục xử lý nếu đang chạy
        if self.running:
            self.root.after(100, self.process_queue)
    
    def add_article(self, article, index):
        """Thêm bài báo vào cột 1 và nội dung vào cột 2"""
        # Làm sạch HTML tags
        def clean_html(raw_html):
            if not raw_html:
                return ''
            cleanr = re.compile('<.*?>')
            cleantext = re.sub(cleanr, '', raw_html)
            return cleantext.strip()
        
        # Cột 1: Frame cho mỗi bài báo với ảnh thumbnail
        article_item_frame = ttk.Frame(self.article_scrollable, relief=tk.RIDGE, borderwidth=1)
        article_item_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Container với 2 cột: ảnh + nội dung
        content_container = ttk.Frame(article_item_frame)
        content_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Ảnh thumbnail bên trái
        img_frame = ttk.Frame(content_container)
        img_frame.pack(side=tk.LEFT, padx=(0, 10))
        
        # Load ảnh thumbnail
        img_url = article.get('image')
        if img_url:
            threading.Thread(target=self.load_article_thumbnail, 
                           args=(img_url, img_frame, index), daemon=True).start()
        else:
            # Placeholder nếu không có ảnh
            placeholder = tk.Label(img_frame, text="📰", font=("Arial", 40), 
                                  bg="lightgray", width=4, height=2)
            placeholder.pack()
        
        # Text frame bên phải
        text_frame = ttk.Frame(content_container)
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Số thứ tự
        index_label = tk.Label(text_frame, text=f"📌 Bài {index}", 
                              font=("Arial", 9, "bold"), fg="green", anchor=tk.W)
        index_label.pack(fill=tk.X)
        
        # Tiêu đề
        title_label = tk.Label(text_frame, text=article.get('title', 'No title'),
                              font=("Arial", 10, "bold"), fg="darkblue", 
                              wraplength=350, anchor=tk.W, justify=tk.LEFT)
        title_label.pack(fill=tk.X, pady=(2, 0))
        
        # Thời gian
        time_label = tk.Label(text_frame, text=f"🕒 {article.get('published', 'N/A')}",
                             font=("Arial", 8), fg="gray", anchor=tk.W)
        time_label.pack(fill=tk.X, pady=(2, 0))
        
        # Nút "Đọc bài" để mở link
        link_url = article.get('link', '')
        if link_url:
            read_btn = tk.Button(text_frame, text="📖 Đọc bài", 
                               font=("Arial", 8, "bold"), fg="white", bg="#007bff",
                               cursor="hand2", relief=tk.RAISED, borderwidth=1,
                               command=lambda url=link_url: self.open_link(url))
            read_btn.pack(anchor=tk.W, pady=(5, 0))
            
            # Hover effect
            read_btn.bind("<Enter>", lambda e: read_btn.config(bg="#0056b3"))
            read_btn.bind("<Leave>", lambda e: read_btn.config(bg="#007bff"))
        
        # Cột 2: Nội dung chi tiết
        self.content_text.insert(tk.END, f"═══════════════════════\n", "separator")
        self.content_text.insert(tk.END, f"📖 Nội dung bài {index}:\n\n", "header")
        
        body_text = clean_html(article.get('body', 'Không có nội dung'))
        self.content_text.insert(tk.END, f"{body_text}\n\n", "content")
        
        # Link có thể click
        link_url = article.get('link', 'N/A')
        self.content_text.insert(tk.END, f"🔗 Link: ", "meta")
        
        link_start = self.content_text.index(tk.END + "-1c")
        self.content_text.insert(tk.END, f"{link_url}\n", "link")
        link_end = self.content_text.index(tk.END + "-1c")
        
        # Tạo tag riêng cho link này
        link_tag = f"link_{index}"
        self.content_text.tag_add(link_tag, link_start, link_end)
        self.content_text.tag_config(link_tag, foreground="blue", underline=True)
        self.content_text.tag_bind(link_tag, "<Button-1>", lambda e, url=link_url: self.open_link(url))
        self.content_text.tag_bind(link_tag, "<Enter>", lambda e: self.content_text.config(cursor="hand2"))
        self.content_text.tag_bind(link_tag, "<Leave>", lambda e: self.content_text.config(cursor=""))
        
        self.content_text.insert(tk.END, f"═══════════════════════\n\n", "separator")
        
        # Style cho content text
        self.content_text.tag_config("header", font=("Arial", 10, "bold"), foreground="darkred")
        self.content_text.tag_config("content", font=("Arial", 9))
        self.content_text.tag_config("meta", font=("Arial", 8), foreground="gray")
        self.content_text.tag_config("link", font=("Arial", 7), foreground="blue", underline=True)
        
        # Auto scroll
        self.article_canvas.update_idletasks()
        self.article_canvas.yview_moveto(1.0)
        self.content_text.see(tk.END)
    
    def load_article_thumbnail(self, img_url, parent_frame, index):
        """Load ảnh thumbnail cho bài báo"""
        try:
            response = requests.get(img_url, timeout=5)
            if response.status_code == 200:
                image = Image.open(io.BytesIO(response.content))
                image.thumbnail((100, 80))  # Thumbnail nhỏ
                photo = ImageTk.PhotoImage(image)
                
                # Update UI trong main thread
                self.root.after(0, self._display_article_thumbnail, photo, parent_frame, index)
        except Exception as e:
            print(f"Error loading thumbnail {index}: {e}")
            # Hiển thị placeholder nếu lỗi
            self.root.after(0, self._display_article_placeholder, parent_frame)
    
    def _display_article_thumbnail(self, photo, parent_frame, index):
        """Hiển thị thumbnail trong UI"""
        for widget in parent_frame.winfo_children():
            widget.destroy()
        
        img_label = tk.Label(parent_frame, image=photo, bg="white", relief=tk.SUNKEN, borderwidth=1)
        img_label.image = photo
        img_label.pack()
        self.article_thumbnails.append(photo)
    
    def _display_article_placeholder(self, parent_frame):
        """Hiển thị placeholder nếu không load được ảnh"""
        for widget in parent_frame.winfo_children():
            widget.destroy()
        
        placeholder = tk.Label(parent_frame, text="🖼️", font=("Arial", 40), 
                             bg="lightgray", width=4, height=2)
        placeholder.pack()
    
    def open_link(self, url):
        """Mở link trong trình duyệt mặc định"""
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"Error opening link: {e}")
    
    def add_image(self, image_data, index):
        """Thêm hình ảnh vào cột 3 một cách tuần tự"""
        try:
            # Load image
            image = Image.open(io.BytesIO(image_data))
            image.thumbnail((280, 200))  # Resize
            photo = ImageTk.PhotoImage(image)
            
            # Frame cho mỗi hình
            img_frame = ttk.Frame(self.scrollable_frame, relief=tk.RIDGE, borderwidth=2)
            img_frame.pack(fill=tk.X, padx=5, pady=5)
            
            # Label cho hình ảnh
            img_label = tk.Label(img_frame, image=photo, bg="white")
            img_label.image = photo  # Giữ reference
            img_label.pack(pady=2)
            
            # Info
            info_label = ttk.Label(
                img_frame, 
                text=f"🖼️ Hình {index} - {datetime.now().strftime('%H:%M:%S')}",
                font=("Arial", 8)
            )
            info_label.pack(pady=2)
            
            # Lưu reference
            self.image_references.append(photo)
            
            # Auto scroll canvas
            self.image_canvas.update_idletasks()
            self.image_canvas.yview_moveto(1.0)
            
        except Exception as e:
            print(f"Error displaying image: {e}")
    
    def show_error(self, message):
        """Hiển thị lỗi"""
        self.article_text.insert(tk.END, f"❌ Lỗi: {message}\n", "error")
        self.article_text.tag_config("error", foreground="red")

def main():
    root = tk.Tk()
    app = NewsScraperApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
