"""
AInovel Web GUI Server & Autonomous Novel Engine
Tích hợp trực tiếp máy chủ web cục bộ và Autonomous Multi-Agent Engine (Architect -> Writer -> Editor -> Coordinator)
Hỗ trợ đa tác phẩm (Multi-story Library): Tạo mới, Danh sách, Chuyển đổi và Xóa tác phẩm.
"""

import http.server
import socketserver
import json
import os
import sys
import re
import time
import shutil
import threading
import urllib.request
import urllib.error
from pathlib import Path

# Đảm bảo UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PORT = 8080
BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_BASE = BASE_DIR.parent / "workspace"
NOVELS_DIR = WORKSPACE_BASE / "novels"
NOVELS_DIR.mkdir(parents=True, exist_ok=True)

# Vị trí lưu trữ mặc định ban đầu
LEGACY_WORKSPACE_DIR = WORKSPACE_BASE / "output" / "novel"
CONFIG_GLOBAL_DIR = Path.home() / ".ainovel"
CONFIG_GLOBAL_FILE = CONFIG_GLOBAL_DIR / "config.json"
WORKSPACE_CONFIG_FILE = BASE_DIR.parent / "config" / "config.json"

class NovelStudioState:
    def __init__(self):
        self.lock = threading.RLock()
        self.active_story_id = ""
        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        self.novel_name = ""
        self.style = "default"
        self.phase = "init"  # init -> architect -> writing -> review -> complete
        self.flow = "Chờ khởi tạo"
        self.in_progress_chapter = 0
        self.completed_count = 0
        self.total_word_count = 0
        self.total_cost = 0.0
        self.reasoning = ""
        self.stream_text = ""
        self.thinking_badge = "Sẵn sàng"
        self.stream_chapter_title = "Chưa có nội dung"
        self.outline = []
        self.characters = []
        self.reviews = []
        self.events = []
        self.steer_queue = []

    def add_event(self, category, summary, level="info"):
        with self.lock:
            ts = time.strftime("%H:%M:%S")
            self.events.insert(0, {
                "time": ts,
                "category": category,
                "summary": summary,
                "level": level
            })
            if len(self.events) > 100:
                self.events.pop()

    def add_steer(self, text):
        with self.lock:
            self.steer_queue.append(text)
        self.add_event("USER", f"[Người dùng can thiệp] {text}", "info")

    def pop_steer(self):
        with self.lock:
            if self.steer_queue:
                return self.steer_queue.pop(0)
            return None

    def reset(self):
        with self.lock:
            self.active_story_id = ""
            self.is_running = False
            self.is_paused = False
            self.should_stop = False
            self.novel_name = ""
            self.style = "default"
            self.phase = "init"
            self.flow = "Chờ khởi tạo"
            self.in_progress_chapter = 0
            self.completed_count = 0
            self.total_word_count = 0
            self.total_cost = 0.0
            self.reasoning = ""
            self.stream_text = ""
            self.thinking_badge = "Sẵn sàng"
            self.stream_chapter_title = "Chưa có nội dung"
            self.outline = []
            self.characters = []
            self.reviews = []

    def to_dict(self):
        with self.lock:
            return {
                "activeStoryId": self.active_story_id,
                "isRunning": self.is_running,
                "isPaused": self.is_paused,
                "novelName": self.novel_name,
                "style": self.style,
                "phase": self.phase,
                "flow": self.flow,
                "inProgressChapter": self.in_progress_chapter,
                "completedCount": self.completed_count,
                "totalWordCount": self.total_word_count,
                "totalCost": self.total_cost,
                "reasoning": self.reasoning,
                "streamText": self.stream_text,
                "thinkingBadge": self.thinking_badge,
                "streamChapterTitle": self.stream_chapter_title,
                "outline": self.outline,
                "characters": self.characters,
                "reviews": self.reviews,
                "events": self.events[:30]
            }

studio_state = NovelStudioState()

# =========================================================================
# QUẢN LÝ DANH SÁCH TÁC PHẨM (STORY LIBRARY)
# =========================================================================

def slugify(text):
    text = re.sub(r'[^\w\s-]', '', text.lower())
    return re.sub(r'[-\s]+', '-', text).strip('-_')

def get_story_dir(story_id):
    if not story_id or not isinstance(story_id, str):
        return None
    clean_id = Path(story_id.strip()).name
    if not clean_id or clean_id in ('.', '..'):
        return None
    target = (NOVELS_DIR / clean_id).resolve()
    try:
        if target.parent.resolve() != NOVELS_DIR.resolve():
            return None
    except Exception:
        return None
    return target

def list_all_stories():
    """Quét thư mục workspace/novels để lấy danh sách toàn bộ tác phẩm."""
    stories = []
    if not NOVELS_DIR.exists():
        return stories

    for folder in NOVELS_DIR.iterdir():
        if not folder.is_dir():
            continue
        sid = folder.name
        info_file = folder / "info.json"
        progress_file = folder / "meta" / "progress.json"
        premise_file = folder / "meta" / "premise.md"
        chapters_dir = folder / "chapters"

        info = {
            "id": sid,
            "title": sid.replace('-', ' ').title(),
            "style": "default",
            "completed_count": 0,
            "total_word_count": 0,
            "updated_at": time.strftime("%d/%m/%Y %H:%M", time.localtime(folder.stat().st_mtime)),
            "is_active": (sid == studio_state.active_story_id)
        }

        if info_file.exists():
            try:
                with open(info_file, "r", encoding="utf-8") as f:
                    saved_info = json.load(f)
                    info.update(saved_info)
            except Exception:
                pass
        elif progress_file.exists():
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    p = json.load(f)
                    info["title"] = p.get("novel_name", info["title"])
                    info["completed_count"] = len(p.get("completed_chapters", []))
                    info["total_word_count"] = p.get("total_word_count", 0)
            except Exception:
                pass

        if premise_file.exists() and info["title"] == sid.replace('-', ' ').title():
            try:
                with open(premise_file, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line.startswith("# "):
                        info["title"] = first_line[2:].strip()
            except Exception:
                pass

        if chapters_dir.exists():
            actual_count = len(list(chapters_dir.glob("*.md")))
            if actual_count > info["completed_count"]:
                info["completed_count"] = actual_count

        info["is_active"] = (sid == studio_state.active_story_id)
        stories.append(info)

    # Sắp xếp mới nhất lên đầu
    stories.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return stories

def switch_to_story(story_id):
    """Nạp một tác phẩm có sẵn vào giao diện Studio."""
    global studio_state
    folder = get_story_dir(story_id)
    if not folder or not folder.exists():
        return False

    with studio_state.lock:
        studio_state.active_story_id = story_id
        studio_state.is_running = False
        studio_state.is_paused = False

        # Load outline
        outline_file = folder / "meta" / "outline.json"
        if outline_file.exists():
            try:
                with open(outline_file, "r", encoding="utf-8") as f:
                    studio_state.outline = json.load(f)
            except Exception:
                studio_state.outline = []
        else:
            studio_state.outline = []

        # Load characters
        chars_file = folder / "meta" / "characters.json"
        if chars_file.exists():
            try:
                with open(chars_file, "r", encoding="utf-8") as f:
                    studio_state.characters = json.load(f)
            except Exception:
                studio_state.characters = []
        else:
            studio_state.characters = []

        # Load progress
        progress_file = folder / "meta" / "progress.json"
        if progress_file.exists():
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    p = json.load(f)
                    studio_state.novel_name = p.get("novel_name", story_id)
                    studio_state.completed_count = len(p.get("completed_chapters", []))
                    studio_state.total_word_count = p.get("total_word_count", 0)
                    studio_state.phase = p.get("phase", "writing")
            except Exception:
                pass
        else:
            studio_state.completed_count = len(list((folder / "chapters").glob("*.md"))) if (folder / "chapters").exists() else 0

        # Load premise if novel name not set
        premise_file = folder / "meta" / "premise.md"
        if premise_file.exists():
            try:
                with open(premise_file, "r", encoding="utf-8") as f:
                    first = f.readline().strip()
                    if first.startswith("# "):
                        studio_state.novel_name = first[2:].strip()
            except Exception:
                pass

        if not studio_state.novel_name:
            studio_state.novel_name = story_id.replace('-', ' ').title()

        # Hiển thị chương cuối cùng nếu có
        chapters_dir = folder / "chapters"
        if chapters_dir.exists():
            chs = sorted(list(chapters_dir.glob("*.md")))
            if chs:
                last_ch = chs[-1]
                try:
                    with open(last_ch, "r", encoding="utf-8") as f:
                        studio_state.stream_text = f.read()
                    ch_num = last_ch.stem
                    studio_state.stream_chapter_title = f"Chương {int(ch_num)} (Đã hoàn thành)"
                except Exception:
                    pass

        # Load reviews
        studio_state.reviews = []
        reviews_dir = folder / "reviews"
        if reviews_dir.exists():
            for r_file in sorted(list(reviews_dir.glob("*.json")), reverse=True):
                try:
                    with open(r_file, "r", encoding="utf-8") as f:
                        studio_state.reviews.append(json.load(f))
                except Exception:
                    pass

        studio_state.flow = f"Đã mở tác phẩm ({studio_state.completed_count} chương)"

    studio_state.add_event("SYSTEM", f"Đã chuyển sang tác phẩm: 《{studio_state.novel_name}》", "info")
    return True

def delete_story(story_id):
    """Xóa hoàn toàn một tác phẩm khỏi đĩa cứng."""
    global studio_state
    if not story_id or not str(story_id).strip():
        return False
    folder = get_story_dir(story_id)
    if not folder or not folder.exists() or folder.resolve() == NOVELS_DIR.resolve():
        return False

    try:
        shutil.rmtree(folder)
    except Exception as e:
        print(f"Lỗi xóa tác phẩm {story_id}: {e}")
        return False

    studio_state.add_event("SYSTEM", f"Đã xóa tác phẩm [{story_id}]", "warn")

    # Nếu đang mở tác phẩm vừa bị xóa, chuyển sang truyện khác hoặc reset
    if studio_state.active_story_id == story_id:
        remaining = list_all_stories()
        if remaining:
            switch_to_story(remaining[0]["id"])
        else:
            studio_state.reset()
            studio_state.add_event("SYSTEM", "Không còn tác phẩm nào trong thư viện. Sẵn sàng tạo mới.", "info")

    return True

# Auto-migration: nếu có legacy novel và thư viện đang rỗng
def check_initial_migration():
    if LEGACY_WORKSPACE_DIR.exists():
        stories = list_all_stories()
        if not stories:
            target = NOVELS_DIR / "tac-pham-hien-tai"
            try:
                shutil.copytree(LEGACY_WORKSPACE_DIR, target)
                switch_to_story("tac-pham-hien-tai")
            except Exception:
                pass
        elif not studio_state.active_story_id:
            switch_to_story(stories[0]["id"])

check_initial_migration()

# =========================================================================
# OPENROUTER STREAMING & NOVEL ENGINE
# =========================================================================

def call_openrouter_stream(api_key, model, messages, on_reasoning=None, on_content=None, base_url="https://openrouter.ai/api/v1"):
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8080",
        "X-Title": "AInovel Studio"
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 0.75
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers
    )

    full_content = []
    full_reasoning = []
    cost = 0.0

    with urllib.request.urlopen(req, timeout=120) as resp:
        for line in resp:
            raw = line.decode("utf-8").strip()
            if not raw or not raw.startswith("data: "):
                continue
            data_str = raw[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                if "usage" in chunk and "cost" in chunk["usage"]:
                    cost += chunk["usage"]["cost"] or 0.0

                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})

                r_delta = delta.get("reasoning", "")
                if r_delta:
                    full_reasoning.append(r_delta)
                    if on_reasoning:
                        on_reasoning(r_delta)

                c_delta = delta.get("content", "")
                if c_delta:
                    full_content.append(c_delta)
                    if on_content:
                        on_content(c_delta)

            except Exception:
                continue

    return "".join(full_content), "".join(full_reasoning), cost

def extract_json_from_text(text):
    text = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        text = match.group(1).strip()
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    try:
        return json.loads(text)
    except Exception:
        return None

def run_editor_review(ch_num, ch_title, ch_summary, full_text, current_novel_dir, config, api_key=None, base_url=None):
    """
    Thực hiện quy trình thẩm định văn học chuyên sâu (Editor Review) theo 7 tiêu chí:
    - Bật phase 'review' để sáng đèn agent Biên tập viên trên UI
    - Stream tiến trình suy nghĩ & nhận xét lên trung tâm Studio
    - Đính kèm toàn văn chương truyện
    - Trích xuất điểm số và lưu báo cáo vào thư mục reviews/
    """
    global studio_state
    roles = config.get("roles", {})
    editor_model = roles.get("editor", {}).get("model") or "anthropic/claude-haiku-5.5"

    provider = config.get("provider", "openrouter")
    p_cfg = config.get("providers", {}).get(provider, {})
    if not api_key:
        api_key = p_cfg.get("api_key", "").strip()
    if not base_url:
        base_url = p_cfg.get("base_url", "https://openrouter.ai/api/v1")

    word_count = len(full_text.split())
    pad_num = str(ch_num).zfill(2)

    with studio_state.lock:
        prev_phase = studio_state.phase
        studio_state.phase = "review"
        studio_state.flow = f"Biên tập viên thẩm định Chương {ch_num}"
        studio_state.thinking_badge = f"Editor • Đánh giá 7 chiều Chương {ch_num}"
        studio_state.reasoning = f"Biên tập viên ({editor_model}) đang đọc và phân tích toàn văn Chương {ch_num} ({word_count:,} từ)...\n\n"

    studio_state.add_event("REVIEW", f"Biên tập viên ({editor_model}) bắt đầu thẩm định Chương {ch_num}", "info")

    editor_system = (
        "Bạn là Biên tập viên văn học chuyên nghiệp (Senior Literary Editor) trong hệ thống đa tác nhân AInovel.\n"
        "Nhiệm vụ của bạn là đọc toàn văn chương tiểu thuyết vừa hoàn thành và đưa ra bản thẩm định chất lượng theo 7 chiều:\n"
        "1. Nhất quán bối cảnh & logic nhân vật\n"
        "2. Nhịp điệu trần thuật (Pacing)\n"
        "3. Văn phong & cảm xúc văn học\n"
        "4. Điểm móc (Hook) & kịch tính cuối chương.\n\n"
        "BẮT BUỘC trả về cấu trúc gồm:\n"
        "- ĐIỂM CHẤT LƯỢNG: [Điểm]/10 (Ví dụ: 8.8/10)\n"
        "- ĐIỂM SÁNG: 2-3 câu nhận xét đánh giá thực chất về văn phong, nhịp kể và điểm sáng của chương.\n"
        "- GÓP Ý CHUYÊN MÔN: 1-2 câu định hướng cho tác giả phát triển ở các chương tiếp theo."
    )

    # Giới hạn an toàn tránh vượt context window
    sample_text = full_text if len(full_text) < 25000 else full_text[:25000] + "\n...(còn tiếp)"

    editor_user = (
        f"Tác phẩm: 《{studio_state.novel_name}》\n"
        f"Chương {ch_num}: {ch_title}\n"
        f"Tóm tắt cốt truyện dự kiến: {ch_summary}\n\n"
        f"=== TOÀN VĂN NỘI DUNG CHƯƠNG {ch_num} ({word_count:,} từ) ===\n"
        f"{sample_text}\n"
        f"=== HẾT NỘI DUNG CHƯƠNG ===\n\n"
        "Hãy thẩm định chi tiết và chấm điểm cho chương truyện trên:"
    )

    def on_editor_stream(delta):
        studio_state.reasoning += delta

    try:
        review_text, _, e_cost = call_openrouter_stream(
            api_key, editor_model,
            [{"role": "system", "content": editor_system}, {"role": "user", "content": editor_user}],
            on_reasoning=on_editor_stream,
            on_content=on_editor_stream,
            base_url=base_url
        )
        studio_state.total_cost += e_cost
        clean_review = review_text.strip()

        score_match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', clean_review)
        score_str = f"{score_match.group(1)}/10" if score_match else "Đạt chuẩn"

        review_entry = {
            "chapter": ch_num,
            "title": ch_title,
            "score": score_str,
            "review": clean_review,
            "timestamp": time.strftime("%H:%M:%S")
        }

        with studio_state.lock:
            studio_state.reviews = [r for r in studio_state.reviews if r.get("chapter") != ch_num]
            studio_state.reviews.insert(0, review_entry)

        if current_novel_dir and current_novel_dir.exists():
            reviews_dir = current_novel_dir / "reviews"
            reviews_dir.mkdir(parents=True, exist_ok=True)
            with open(reviews_dir / f"{pad_num}.json", "w", encoding="utf-8") as f:
                json.dump(review_entry, f, ensure_ascii=False, indent=2)
            with open(reviews_dir / f"{pad_num}.md", "w", encoding="utf-8") as f:
                f.write(f"# Đánh giá Chương {ch_num}: {ch_title}\n\nĐiểm: {score_str}\n\n{clean_review}\n")

        first_line = clean_review.split("\n")[0][:70].replace('\n', ' ')
        studio_state.add_event("REVIEW", f"Chương {ch_num} [{score_str}]: {first_line}...", "success")
        return review_entry
    except Exception as e:
        studio_state.add_event("ERROR", f"Lỗi thẩm định Editor tại Chương {ch_num}: {e}", "error")
        return None
    finally:
        with studio_state.lock:
            if studio_state.is_running:
                studio_state.phase = "writing"
            else:
                studio_state.phase = prev_phase if prev_phase in ("writing", "complete", "init") else "idle"


def run_novel_pipeline(prompt, style, config):
    global studio_state

    provider = config.get("provider", "openrouter")
    p_cfg = config.get("providers", {}).get(provider, {})
    api_key = p_cfg.get("api_key", "").strip()
    base_url = p_cfg.get("base_url", "https://openrouter.ai/api/v1")
    default_model = config.get("model", "deepseek/deepseek-v4.1-flash-1017")

    roles = config.get("roles", {})
    architect_model = roles.get("architect", {}).get("model") or default_model
    writer_model = roles.get("writer", {}).get("model") or default_model
    editor_model = roles.get("editor", {}).get("model") or "anthropic/claude-haiku-5.5"

    if not api_key and provider != "ollama":
        studio_state.add_event("ERROR", f"Chưa cấu hình API Key cho {provider}!", "error")
        studio_state.is_running = False
        return

    # Tạo thư mục riêng cho tác phẩm mới
    story_id = f"novel-{int(time.time())}"
    current_novel_dir = get_story_dir(story_id)
    for sub in ["chapters", "meta", "reviews", "drafts"]:
        (current_novel_dir / sub).mkdir(parents=True, exist_ok=True)

    studio_state.active_story_id = story_id
    studio_state.is_running = True
    studio_state.is_paused = False
    studio_state.should_stop = False
    studio_state.style = style
    studio_state.phase = "architect"
    studio_state.flow = "Kiến trúc sư lập kế hoạch"
    studio_state.thinking_badge = "Architect • Foundation"
    studio_state.stream_chapter_title = "Lập kế hoạch thế giới & Đề cương"
    studio_state.reasoning = ""
    studio_state.stream_text = "Đang kết nối Kiến trúc sư AI để phân tích ý tưởng..."

    studio_state.add_event("SYSTEM", f"Khởi động dự án mới [{story_id}]. Provider: {provider}", "info")
    studio_state.add_event("DISPATCH", f"Coordinator điều phối Architect ({architect_model}) xây dựng nền tảng", "info")

    arch_system = (
        "Bạn là Kiến trúc sư tiểu thuyết (Master Story Architect). Nhiệm vụ của bạn là nhận ý tưởng sáng tác, "
        "sau đó thiết kế một tác phẩm hoàn chỉnh, lôi cuốn, có cấu trúc chặt chẽ.\n"
        "BẮT BUỘC chỉ trả về DUY NHẤT một khối JSON hợp lệ theo đúng cấu trúc sau (không kèm lời chào hay văn bản khác):\n"
        "{\n"
        '  "title": "Tên tiểu thuyết thật ấn tượng",\n'
        '  "premise": "Tóm tắt tiền đề câu chuyện và thông điệp chính...",\n'
        '  "characters": [\n'
        '    {"name": "Tên nhân vật", "role": "Chính diện / Phụ / Phản diện", "desc": "Mô tả thân phận, tính cách, động cơ"}\n'
        "  ],\n"
        '  "outline": [\n'
        '    {"chapter": 1, "title": "Tiêu đề chương 1", "summary": "Tóm tắt sự kiện then chốt của chương"},\n'
        '    {"chapter": 2, "title": "Tiêu đề chương 2", "summary": "Tóm tắt sự kiện then chốt của chương"},\n'
        '    {"chapter": 3, "title": "Tiêu đề chương 3", "summary": "Tóm tắt sự kiện then chốt của chương"},\n'
        '    {"chapter": 4, "title": "Tiêu đề chương 4", "summary": "Tóm tắt sự kiện then chốt của chương"},\n'
        '    {"chapter": 5, "title": "Tiêu đề chương 5", "summary": "Tóm tắt sự kiện then chốt của chương"}\n'
        "  ]\n"
        "}"
    )

    arch_user = f"Yêu cầu cốt truyện:\n\"\"\"{prompt}\"\"\"\nPhong cách: {style}. Hãy lập kế hoạch 5-8 chương đầu thật hấp dẫn."

    def on_arch_reasoning(delta):
        studio_state.reasoning += delta

    def on_arch_content(delta):
        studio_state.stream_text += delta

    studio_state.stream_text = ""
    try:
        content, reasoning, cost = call_openrouter_stream(
            api_key, architect_model,
            [{"role": "system", "content": arch_system}, {"role": "user", "content": arch_user}],
            on_reasoning=on_arch_reasoning,
            on_content=on_arch_content,
            base_url=base_url
        )
        studio_state.total_cost += cost
    except Exception as e:
        studio_state.add_event("ERROR", f"Lỗi gọi Architect: {e}", "error")
        studio_state.is_running = False
        return

    arch_data = extract_json_from_text(content)
    if not arch_data or "outline" not in arch_data:
        studio_state.novel_name = "Cuộc Sống Tại Google: Trọng Sinh 2010"
        studio_state.outline = [
            {"chapter": 1, "title": "Trở Về Điểm Khởi Đầu", "summary": "Lý Duy Minh thức tỉnh trong văn phòng Google tại S thị năm 2026, nhớ lại hành trình du học Stanford và bước ngoặt mở VP tại VN."},
            {"chapter": 2, "title": "Cuộc Họp Sáng Ở Tầng 32", "summary": "Gặp gỡ đội ngũ cốt cán, giải quyết khủng hoảng kỹ thuật đầu tiên."},
            {"chapter": 3, "title": "Những Cơn Sóng Ngầm", "summary": "Cuộc đấu trí với đối tác công nghệ nội địa và đối thủ giấu mặt."},
            {"chapter": 4, "title": "Đêm Không Ngủ Tại S Thị", "summary": "Phút lắng đọng sau giờ làm việc, nhìn lại ký ức 2010."},
            {"chapter": 5, "title": "Bước Tiến Đột Phá", "summary": "Thương vụ hợp tác lớn khẳng định vị thế của Google Việt Nam."}
        ]
        studio_state.characters = [
            {"name": "Lý Duy Minh", "role": "Nhân vật chính", "desc": "Giám đốc điều hành (MD) Google Việt Nam, tốt nghiệp Stanford, trọng sinh từ 2010."}
        ]
    else:
        studio_state.novel_name = arch_data.get("title", "Tiểu Thuyết Mới")
        studio_state.outline = arch_data.get("outline", [])
        studio_state.characters = arch_data.get("characters", [])

    # Lưu meta vào thư mục tác phẩm
    try:
        with open(current_novel_dir / "meta" / "outline.json", "w", encoding="utf-8") as f:
            json.dump(studio_state.outline, f, ensure_ascii=False, indent=2)
        with open(current_novel_dir / "meta" / "characters.json", "w", encoding="utf-8") as f:
            json.dump(studio_state.characters, f, ensure_ascii=False, indent=2)
        with open(current_novel_dir / "meta" / "premise.md", "w", encoding="utf-8") as f:
            f.write(f"# {studio_state.novel_name}\n\n{arch_data.get('premise', prompt) if arch_data else prompt}\n")
        with open(current_novel_dir / "info.json", "w", encoding="utf-8") as f:
            json.dump({
                "id": story_id,
                "title": studio_state.novel_name,
                "style": style,
                "created_at": time.strftime("%d/%m/%Y %H:%M"),
                "updated_at": time.strftime("%d/%m/%Y %H:%M"),
                "completed_count": 0,
                "total_word_count": 0
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Lỗi ghi meta: {e}")

    studio_state.add_event("TOOL", f"Kiến trúc sư hoàn tất: {len(studio_state.outline)} chương & {len(studio_state.characters)} nhân vật", "success")

    # =========================================================================
    # GIAI ĐOẠN 2: WRITER & EDITOR LOOP
    # =========================================================================
    studio_state.phase = "writing"

    for item in studio_state.outline:
        if studio_state.should_stop:
            break

        while studio_state.is_paused:
            time.sleep(0.5)
            if studio_state.should_stop:
                break

        ch_num = item.get("chapter", 1)
        ch_title = item.get("title", f"Chương {ch_num}")
        ch_summary = item.get("summary", "")

        studio_state.in_progress_chapter = ch_num
        studio_state.flow = f"Viết Chương {ch_num}"
        studio_state.thinking_badge = f"Writer • Chương {ch_num}"
        studio_state.stream_chapter_title = f"Chương {ch_num}: {ch_title}"
        studio_state.reasoning = ""
        studio_state.stream_text = ""

        steer_text = studio_state.pop_steer()
        steer_prompt_part = ""
        if steer_text:
            steer_prompt_part = f"\n\n[CHỈ ĐẠO CAN THIỆP TỪ ĐỌC GIẢ]: {steer_text}\n(Lồng ghép khéo léo yêu cầu này vào nội dung chương)."
            studio_state.add_event("USER", f"Tiêm can thiệp vào Chương {ch_num}: {steer_text}", "info")

        studio_state.add_event("DISPATCH", f"Coordinator điều phối Writer ({writer_model}) viết Chương {ch_num}: {ch_title}", "info")

        writer_system = (
            "Bạn là Nhà văn (Lead Novelist) viết tiểu thuyết bằng tiếng Việt với bút lực điêu luyện, cuốn hút và tự nhiên.\n"
            "Hãy viết toàn văn chương truyện thật chi tiết, có chiều sâu tâm lý, miêu tả khung cảnh chân thực, "
            "đối thoại sắc sảo, không dùng từ sáo rỗng hoặc lặp từ ngữ AI.\n"
            "Đầu chương hãy đặt tiêu đề theo dạng: # Chương [số]: [Tên chương]\n"
            "Độ dài chương yêu cầu: Viết trọn vẹn đầy đủ từ 1.500 đến 3.000 từ."
        )

        char_desc = "\n".join([f"- {c['name']} ({c.get('role','')}): {c.get('desc','')}" for c in studio_state.characters[:5]])
        writer_user = (
            f"Tác phẩm: 《{studio_state.novel_name}》\n"
            f"Phong cách: {style}\n"
            f"Bối cảnh & Nhân vật:\n{char_desc}\n\n"
            f"Nhiệm vụ: Viết toàn văn Chương {ch_num}: {ch_title}\n"
            f"Cốt truyện chương: {ch_summary}"
            f"{steer_prompt_part}\n\n"
            "Bắt đầu viết toàn văn chương ngay bây giờ:"
        )

        def on_writer_reasoning(delta):
            studio_state.reasoning += delta

        def on_writer_content(delta):
            studio_state.stream_text += delta

        try:
            full_text, r_text, cost = call_openrouter_stream(
                api_key, writer_model,
                [{"role": "system", "content": writer_system}, {"role": "user", "content": writer_user}],
                on_reasoning=on_writer_reasoning,
                on_content=on_writer_content,
                base_url=base_url
            )
            studio_state.total_cost += cost
        except Exception as e:
            studio_state.add_event("ERROR", f"Lỗi Writer tại Chương {ch_num}: {e}", "error")
            continue

        word_count = len(full_text.split())
        pad_num = str(ch_num).zfill(2)
        try:
            with open(current_novel_dir / "chapters" / f"{pad_num}.md", "w", encoding="utf-8") as f:
                f.write(full_text)
        except Exception as e:
            print(f"Lỗi ghi file chương: {e}")

        studio_state.completed_count += 1
        studio_state.total_word_count += word_count

        try:
            with open(current_novel_dir / "meta" / "progress.json", "w", encoding="utf-8") as f:
                json.dump({
                    "novel_name": studio_state.novel_name,
                    "phase": studio_state.phase,
                    "completed_chapters": list(range(1, studio_state.completed_count + 1)),
                    "total_word_count": studio_state.total_word_count,
                    "in_progress_chapter": ch_num
                }, f, ensure_ascii=False, indent=2)
            with open(current_novel_dir / "info.json", "w", encoding="utf-8") as f:
                json.dump({
                    "id": story_id,
                    "title": studio_state.novel_name,
                    "style": style,
                    "created_at": time.strftime("%d/%m/%Y %H:%M"),
                    "updated_at": time.strftime("%d/%m/%Y %H:%M"),
                    "completed_count": studio_state.completed_count,
                    "total_word_count": studio_state.total_word_count
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        studio_state.add_event("TOOL", f"Đã lưu bản thảo: chapters/{pad_num}.md ({word_count:,} từ)", "success")

        # GIAI ĐOẠN 3: BIÊN TẬP VIÊN THẨM ĐỊNH (EDITOR REVIEW)
        run_editor_review(
            ch_num=ch_num,
            ch_title=ch_title,
            ch_summary=ch_summary,
            full_text=full_text,
            current_novel_dir=current_novel_dir,
            config=config,
            api_key=api_key,
            base_url=base_url
        )

        time.sleep(1)

    studio_state.phase = "complete"
    studio_state.flow = "Hoàn thành tác phẩm"
    studio_state.is_running = False
    studio_state.add_event("SYSTEM", f"Sáng tác hoàn thành! Tổng cộng: {studio_state.completed_count} chương, {studio_state.total_word_count:,} từ", "success")


# =========================================================================
# HTTP REQUEST HANDLER
# =========================================================================

class AInovelHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            return super().do_GET()

        # API: Danh sách toàn bộ truyện trong thư viện
        if self.path == "/api/stories":
            stories = list_all_stories()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(stories, ensure_ascii=False).encode("utf-8"))
            return

        # API: Đọc cấu hình config.json
        if self.path == "/api/config":
            cfg = self.get_config()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8"))
            return

        # API: Lấy realtime status từ NovelStudioState
        if self.path == "/api/status" or self.path == "/api/snapshot":
            data = studio_state.to_dict()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            return

        # API: Đọc nội dung một chương của tác phẩm đang mở
        if self.path.startswith("/api/chapter/"):
            ch_num = self.path.replace("/api/chapter/", "").strip()
            content = self.get_chapter_content(ch_num)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"chapter": ch_num, "content": content}, ensure_ascii=False).encode("utf-8"))
            return

        # API: Xuất toàn bộ truyện thành TXT
        if self.path.startswith("/api/export/"):
            sid = self.path.replace("/api/export/", "").strip()
            if not sid:
                sid = studio_state.active_story_id
            txt = self.build_export_txt(sid)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{sid}.txt"')
            self.end_headers()
            self.wfile.write(txt.encode("utf-8"))
            return

        return super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        raw_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            raw_body = raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                raw_body = raw_bytes.decode('cp1252', errors='replace')
            except Exception:
                raw_body = raw_bytes.decode('utf-8', errors='replace')
        try:
            data = json.loads(raw_body)
        except Exception:
            data = {}

        # API: Chuyển đổi tác phẩm đang mở
        if self.path == "/api/stories/switch":
            sid = data.get("id", "").strip()
            success = switch_to_story(sid)
            self.send_response(200 if success else 404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok" if success else "error",
                "activeStoryId": studio_state.active_story_id,
                "novelName": studio_state.novel_name
            }, ensure_ascii=False).encode("utf-8"))
            return

        # API: Xóa tác phẩm
        if self.path == "/api/stories/delete":
            sid = data.get("id", "").strip()
            if not sid:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "ID truyện không hợp lệ"}, ensure_ascii=False).encode("utf-8"))
                return
            success = delete_story(sid)
            self.send_response(200 if success else 404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok" if success else "error",
                "deletedId": sid,
                "remaining": list_all_stories()
            }, ensure_ascii=False).encode("utf-8"))
            return

        # API: Lưu cấu hình config.json
        if self.path == "/api/config":
            saved_paths = self.save_config(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "message": "Đã lưu cấu hình thành công",
                "paths": saved_paths
            }, ensure_ascii=False).encode("utf-8"))
            return

        # API: Yêu cầu Biên tập viên thẩm định một chương cụ thể
        if self.path == "/api/review":
            ch_num = int(data.get("chapter", 1))
            current_cfg = self.get_config()
            target_novel_dir = get_story_dir(studio_state.active_story_id) if studio_state.active_story_id else LEGACY_WORKSPACE_DIR
            pad_num = str(ch_num).zfill(2)
            ch_file = target_novel_dir / "chapters" / f"{pad_num}.md"
            if not ch_file.exists():
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": f"Chưa có nội dung cho chương {ch_num}"}, ensure_ascii=False).encode("utf-8"))
                return

            with open(ch_file, "r", encoding="utf-8") as f:
                ch_content = f.read()

            ch_title = f"Chương {ch_num}"
            ch_summary = ""
            for item in studio_state.outline:
                if item.get("chapter") == ch_num:
                    ch_title = item.get("title", ch_title)
                    ch_summary = item.get("summary", "")
                    break

            threading.Thread(
                target=run_editor_review,
                args=(ch_num, ch_title, ch_summary, ch_content, target_novel_dir, current_cfg),
                daemon=True
            ).start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "message": f"Đang thẩm định Chương {ch_num}..."}).encode("utf-8"))
            return

        # API: Bắt đầu sáng tác tiểu thuyết mới
        if self.path == "/api/start":
            prompt = data.get("prompt", "").strip()
            style = data.get("style", "default")
            cfg = self.get_config()

            if not prompt:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "Thiếu prompt yêu cầu"}, ensure_ascii=False).encode("utf-8"))
                return

            t = threading.Thread(target=run_novel_pipeline, args=(prompt, style, cfg), daemon=True)
            t.start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "message": "Đã kích hoạt AI Engine sáng tác thành công!",
                "prompt": prompt,
                "style": style
            }, ensure_ascii=False).encode("utf-8"))
            return

        # API: Tạm dừng / Tiếp tục
        if self.path == "/api/pause":
            action = data.get("action", "pause")
            if action == "pause":
                studio_state.is_paused = True
                studio_state.add_event("SYSTEM", "Người dùng tạm dừng sáng tác", "warn")
            else:
                studio_state.is_paused = False
                studio_state.add_event("SYSTEM", "Người dùng tiếp tục sáng tác", "info")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "isPaused": studio_state.is_paused}, ensure_ascii=False).encode("utf-8"))
            return

        # API: Gửi can thiệp
        if self.path == "/api/steer":
            text = data.get("text", "").strip()
            if text:
                studio_state.add_steer(text)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "steer": text}, ensure_ascii=False).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def get_config(self):
        target = None
        if CONFIG_GLOBAL_FILE.exists():
            target = CONFIG_GLOBAL_FILE
        elif WORKSPACE_CONFIG_FILE.exists():
            target = WORKSPACE_CONFIG_FILE

        if target:
            try:
                with open(target, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        return {
            "provider": "openrouter",
            "model": "deepseek/deepseek-v4.1-flash-1017",
            "style": "default",
            "providers": {
                "openrouter": {
                    "api_key": "",
                    "base_url": "https://openrouter.ai/api/v1",
                    "models": [
                        "deepseek/deepseek-v4.1-flash-1017",
                        "anthropic/claude-haiku-5.5",
                        "openai/gpt-4o-mini"
                    ]
                }
            },
            "roles": {
                "architect": {"provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash-1017"},
                "writer": {"provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash-1017"},
                "editor": {"provider": "openrouter", "model": "anthropic/claude-haiku-5.5"},
                "coordinator": {"provider": "openrouter", "model": "openai/gpt-4o-mini"}
            }
        }

    def save_config(self, cfg):
        saved = []
        try:
            CONFIG_GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_GLOBAL_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            saved.append(str(CONFIG_GLOBAL_FILE))
        except Exception:
            pass
        return saved

    def get_chapter_content(self, ch_num):
        pad_num = str(ch_num).zfill(2)
        target_dir = get_story_dir(studio_state.active_story_id) if studio_state.active_story_id else None
        if not target_dir or not target_dir.exists():
            target_dir = LEGACY_WORKSPACE_DIR
        target = target_dir / "chapters" / f"{pad_num}.md"
        if target.exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"Lỗi đọc file chương: {e}"
        return "Chưa có nội dung cho chương này."

    def build_export_txt(self, story_id):
        target_dir = get_story_dir(story_id)
        if not target_dir or not target_dir.exists():
            target_dir = LEGACY_WORKSPACE_DIR

        title = story_id.replace('-', ' ').title()
        premise = ""
        p_file = target_dir / "meta" / "premise.md"
        if p_file.exists():
            try:
                with open(p_file, "r", encoding="utf-8") as f:
                    premise = f.read()
            except Exception:
                pass

        out = [f"=== {title} ===\n\n{premise}\n\n" + "="*40 + "\n\n"]
        chapters_dir = target_dir / "chapters"
        if chapters_dir.exists():
            chs = sorted(list(chapters_dir.glob("*.md")))
            for c in chs:
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        out.append(f.read() + "\n\n" + "-"*30 + "\n\n")
                except Exception:
                    pass
        return "".join(out)


class ReusableThreadingServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True


if __name__ == "__main__":
    print("=" * 65)
    print(f">> AInovel Web GUI Server & Multi-Story Engine dang chay tai: http://localhost:{PORT}")
    print(f">> Thu vien truyen: {NOVELS_DIR}")
    print("Mo trinh duyet truy cap http://localhost:8080 de su dung!")
    print("=" * 65)
    with ReusableThreadingServer(("", PORT), AInovelHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDa tat may chu.")
