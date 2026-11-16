"""So sánh hai phiên bản tài liệu: diff cục bộ (miễn phí) + tóm tắt bằng AI.

Diff bằng `difflib.unified_diff` trên từng dòng văn bản đã trích xuất — chạy
ngay trong process, không tốn lượt gọi AI. Tóm tắt "thay đổi gì về nghĩa"
mới gọi AI (1 lượt, charge theo pattern AI khác: lỗi thì hoàn credit).
"""

import difflib

from app.services import ai_service

# Giới hạn nội dung gửi AI: 2 tài liệu lớn ghép lại dễ vượt context window.
_MAX_AI_INPUT_CHARS = 60_000


def compute_line_diff(old_text: str, new_text: str) -> list[str]:
    """Diff dạng unified (không context) giữa hai văn bản, từng dòng.

    2 dòng đầu của `unified_diff` luôn là header `---`/`+++` (file cũ/mới) —
    bỏ đúng 2 dòng đó bằng slice thay vì lọc prefix, vì dòng nội dung thật có
    thể bắt đầu bằng `---` (đường phân cách markdown) và phải được giữ lại.
    Trả rỗng = hai bản giống hệt nhau.
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff = difflib.unified_diff(
        old_lines, new_lines, fromfile="old", tofile="new", lineterm="", n=0
    )
    return list(diff)[2:]


def diff_stats(diff_lines: list[str]) -> dict[str, int]:
    """Thống kê nhanh số dòng thêm/bớt cho UI hiển thị badge."""
    added = sum(1 for line in diff_lines if line.startswith("+"))
    removed = sum(1 for line in diff_lines if line.startswith("-"))
    return {"added": added, "removed": removed}


def summarize_changes(old_text: str, new_text: str) -> str:
    """AI tóm tắt thay đổi chính giữa hai bản — tiếng Việt, gạch đầu dòng.

    Chỉ gửi phần khác biệt (nếu có) thay vì toàn bộ hai văn bản để tiết kiệm
    token; hai bản không khác nhau thì không gọi AI.
    """
    diff = compute_line_diff(old_text, new_text)
    if not diff:
        return "Hai bản không có khác biệt về văn bản."

    diff_body = "\n".join(diff)[:_MAX_AI_INPUT_CHARS]
    return ai_service.request_anthropic(
        [{
            "type": "text",
            "text": (
                "Bạn là trợ lý soạn thảo tài liệu pháp lý. Dưới đây là kết quả "
                "so sánh dòng văn bản giữa bản CŨ và bản MỚI của một tài liệu: "
                "dòng bắt đầu '-' chỉ có ở bản cũ, dòng '+' chỉ có ở bản mới.\n"
                "Hãy tóm tắt NHỮNG THAY ĐỔI VỀ NỘI DUNG quan trọng nhất (điều "
                "khoản sửa, số tiền/ngày thay đổi, mục thêm/bớt) bằng tiếng "
                "Việt, tối đa 10 gạch đầu dòng, mỗi dòng ngắn gọn. Chỉ dựa vào "
                "diff, không suy đoán. Nếu chỉ khác formatting (khoảng trắng, "
                "xuống dòng) thì nói rõ là không có thay đổi về nội dung.\n\n"
                f"DIFF:\n{diff_body}"
            ),
        }],
        temperature=0,
    ).strip()
