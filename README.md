# Ứng dụng Thu thập Tin tức & Hình ảnh

Ứng dụng GUI với giao thức bất đồng bộ và đa luồng để thu thập hình ảnh và bài báo từ mạng.

## Tính năng

- ✅ **Giao diện 3 cột:**
  - Cột 1: Danh sách bài báo (40%)
  - Cột 2: Nội dung chi tiết (30%)
  - Cột 3: Ngày giờ & Hình ảnh (30%)

- ✅ **Đa luồng (Multi-threading):** Xử lý dữ liệu trong thread riêng không block UI

- ✅ **Bất đồng bộ (Async):** Sử dụng `aiohttp` và `asyncio` để request song song

- ✅ **Request tuần tự:** Mỗi hình ảnh và bài báo được load từng cái một để tránh lag

- ✅ **Scroll mượt mà:** Canvas với scrollbar, không bị kẹt khi load dữ liệu

## Cài đặt

```powershell
# Cài đặt thư viện
pip install -r requirements.txt
```

## Chạy ứng dụng

```powershell
python news_scraper_gui.py
```

## Sử dụng

1. Nhấn nút "▶ Bắt đầu" để bắt đầu thu thập dữ liệu
2. Ứng dụng sẽ load bài báo và hình ảnh từng cái một
3. Scroll để xem các hình ảnh được thêm vào tuần tự
4. Nhấn "⏹ Dừng" để dừng quá trình

## Cấu trúc

- **Queue-based:** Sử dụng `queue.Queue()` để truyền dữ liệu giữa threads
- **Thread-safe:** UI chỉ được update từ main thread
- **Async requests:** Load dữ liệu song song nhưng hiển thị tuần tự

## Tùy chỉnh

Bạn có thể thay đổi URL API trong ô nhập liệu hoặc sửa code để kết nối với API khác.
