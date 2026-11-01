# AInovel Web GUI — Giao Diện Trực Quan Cho Hệ Thống Sáng Tác Tiểu Thuyết

Giao diện Web GUI hiện đại, trực quan dành cho engine sáng tác tiểu thuyết `ainovel-cli-vietnamese`, chạy trực tiếp trên trình duyệt web tại `http://localhost:8080`.

---

## 🌟 Tính năng nổi bật

- **Studio Đa Tác Nhân (Multi-Agent Live Studio)**:
  - **Điều phối viên (Coordinator)**: Quản lý và kích hoạt toàn bộ vòng lặp sáng tác.
  - **Kiến trúc sư (Architect)**: Thiết lập bối cảnh, nhân vật và đề cương chi tiết.
  - **Người viết (Writer)**: Soạn thảo toàn văn chương truyện, stream trực tiếp văn bản và suy nghĩ (*Reasoning*).
  - **Biên tập viên (Editor)**: Thẩm định văn học chuyên sâu 7 chiều, chấm điểm (thang điểm 10), nhận xét ưu điểm và định hướng phát triển.
- **Thư viện Tác phẩm (Multi-Story Library)**:
  - Quản lý đồng thời nhiều bộ tiểu thuyết trong `workspace/novels/`.
  - Mở, chuyển đổi giữa các tác phẩm, xuất file `.txt` hoàn chỉnh, và xóa bỏ an toàn với hộp thoại xác nhận.
- **Cấu hình Model & API linh hoạt**:
  - Hỗ trợ OpenRouter, DeepSeek, Claude (Anthropic), GPT (OpenAI), Gemini, Ollama (Local).
  - Cho phép cấu hình model riêng biệt cho từng vai trò (Kiến trúc sư, Người viết, Biên tập viên, Điều phối viên).
- **Can thiệp Thời gian thực (Real-time Steering)**:
  - Nhập chỉ dẫn cho AI bất kỳ lúc nào để lồng ghép tình huống, đào sâu tâm lý nhân vật hoặc gài phục bút mà không làm gián đoạn luồng viết.
- **Trình đọc chương & Quản lý đề cương (Reader & Codex)**:
  - Xem danh sách chương, đọc bản thảo định dạng Markdown, tra cứu hồ sơ nhân vật và xem báo cáo đánh giá của Editor.

---

## 🚀 Hướng dẫn khởi chạy

### Yêu cầu
- Python 3.8+ (khuyên dùng Python 3.10+)

### Khởi động Web GUI
Chạy lệnh sau từ thư mục gốc của repository:

```bash
python gui/server.py
```

Hoặc di chuyển vào thư mục `gui/` và chạy:

```bash
cd gui
python server.py
```

Mở trình duyệt truy cập:
👉 **`http://localhost:8080`**

---

## 📁 Cấu trúc thư mục

```
ainovel-cli-vietnamese/
├── gui/
│   ├── index.html       # Giao diện Web GUI (HTML5 + TailwindCSS + FontAwesome)
│   ├── server.py        # Máy chủ đa luồng & Autonomous Multi-Agent Engine
│   └── README.md        # Hướng dẫn sử dụng Web GUI
└── workspace/
    └── novels/          # Lưu trữ các bộ tiểu thuyết riêng biệt
        └── <novel-id>/
            ├── chapters/    # Toàn văn các chương (*.md)
            ├── meta/        # Đề cương (outline), nhân vật, tiến độ
            ├── reviews/     # Báo cáo thẩm định của Editor (*.json, *.md)
            └── info.json    # Thông tin tóm tắt tác phẩm
```
