# Spec giao diện — màn Files (hướng A: tinh tế nhưng có màu)

Mục tiêu: màn `lib/presentation/documents/documents_screen.dart` hết "nhạt" mà
không phá chất SaaS (Linear/Notion). **Chỉ đổi trình bày** — menu ⋮, các dialog,
controller, logic nghiệp vụ giữ nguyên 100%.

Vì sao màn này đang nhạt (đối chiếu code hiện tại):

| Vấn đề | Chỗ trong code |
|---|---|
| Tài liệu là danh sách 64px một cột, chỉ có 1 icon 40px là có màu | `_DocumentTile` |
| 5 nút toolbar cùng trọng lượng, không phân cấp | `_buildToolbar` |
| Thư mục là card 190px chiếm 84px chiều cao, đọc như panel | `_FolderCard` |
| Card trắng trên nền `#F7F8FC` gần trắng, viền xám 1px, không bóng | `cardTheme` |
| Empty state = 1 icon xám 44px | `_buildList` |

---

## 1. Ba tầng nền (làm trước, ảnh hưởng cả app)

| Tầng | Light | Dark |
|---|---|---|
| Nền app | `#F6F7FB` (giữ `lightBg`) | `#0F1115` |
| Panel (sidebar/topbar) | `#FFFFFF` + viền `#E9EBF2` | `#171A21` + viền `#262B36` |
| Card | `#FFFFFF`, **bỏ viền**, bóng `0 1px 2px rgba(16,24,40,.05)` + `0 4px 14px rgba(16,24,40,.05)` | `#1B1F28`, bóng `0 4px 14px rgba(0,0,0,.45)` |

Card nổi khỏi nền là thứ tạo 50% cảm giác "xịn". Hiện `cardTheme` để
`elevation: 0` + viền 1px nên mọi thứ phẳng như nhau.

## 2. Accent theo loại tệp

Dùng cho icon tile, badge trên thumbnail, viền khi chọn.

| Loại | Màu | Nền nhạt |
|---|---|---|
| PDF | `#E5484D` | `#FEF1F2` |
| Word / DOCX | `#2563EB` | `#EFF6FF` |
| Ảnh | `#7C3AED` | `#F5F3FF` |
| Text / MD | `#475569` | `#F1F5F9` |

Dark mode dùng bản sáng hơn: `#F87171` / `#60A5FA` / `#A78BFA` / `#94A3B8`,
nền = màu đó với alpha 16%.

## 3. Header (cao 72px, padding 28)

```
My Files                                      ┌──────────────────────┐
Manage, organize and secure your documents.   │ 24 files · 128.4 MB  │
                                              └──────────────────────┘
```

- "My Files": 24px / w800.
- Phụ đề: 13px, màu muted.
- Bên phải: **pill** thống kê (nền trắng, viền 1px, radius 999, 13px/w600)
  thay cho chữ rời `'${n} files'` hiện tại.

## 4. Toolbar — phân cấp lại

Một hàng, cách nhau 8px:

`[↑ Upload]` (FilledButton, primary) · `[📁 New folder]` (Outlined) ·
`[⤓ Export to Word]` (Outlined) · `Select to merge` (**TextButton** — hành động
phụ, không được tranh chỗ với Upload).

Bên phải (đẩy sang bằng `Spacer`): segmented **Grid / List** + dropdown sắp xếp
`Last modified ▾`.

Khi vào chế độ chọn: ẩn `Select to merge`, hiện **thanh dưới đáy** thay vì nhét
`Merge (n)` vào toolbar:

```
┌──────────────────────────────────────────────────┐
│ 2 selected            [ Merge (2) ]   Cancel     │   ← sticky, nền trắng, shadow trên
└──────────────────────────────────────────────────┘
```

## 5. Thư mục: card 190px → chip pill (cao 36)

```
( 📁 All  24 )  ( 📁 Contracts  7 )  ( 📁 Lectures  4 )  (+ New)
```

- Chip: icon folder 16 + tên 13px/w600 + badge số đếm (nền xám nhạt, radius 999).
- Đang chọn: nền `#EEF2FF`, viền `#4F46E5`, chữ `#4F46E5`.
- Nút xóa thư mục (X) chỉ hiện khi chip đang chọn hoặc hover — hiện tại nó luôn
  hiện nên 6 thư mục là 6 dấu X, rất rối.
- Lợi ích: tiết kiệm ~48px chiều cao (84 → 36) → nhường chỗ cho danh sách tệp.

## 6. Danh sách tệp: card có thumbnail (thay đổi lớn nhất)

Grid 3–4 cột (ngưỡng: >1100px → 4, >760px → 3, còn lại 2; mobile 1).

```
┌─────────────────┐
│▛▀▀▀▀▀▀▀▀▀▀▀▀▀▜★│   ← sao favorite góc phải trên
│▌ ▭▭▭▭▭▭▭▭▭▭  ▐ │   ← vùng thumbnail: tờ giấy trắng
│▌ ▭▭▭▭▭▭▭     ▐ │      + vài dòng kẻ xám + badge PDF
│▌ ▭▭▭▭▭▭▭▭    ▐ │
│▙▄▄▄▄▄▄▄▄▄▄▄▄▄▟ │
├─────────────────┤
│ hop-dong-thue   │   ← 14px / w600, 1 dòng, ellipsis
│ 3 pages · 1.2 MB│   ← 12px muted
│ 2 days ago      │
└─────────────────┘
```

- Card: radius 14, padding 12, bóng như mục 1; hover → bóng tăng + hiện `⋮`.
- **Thumbnail vẽ bằng widget** (backend chưa render ảnh trang đầu):
  - PDF: nền trắng, 4–5 dòng kẻ `#E5E7EB` so le, badge đỏ `PDF` góc trên trái.
  - Ảnh: nền `#F5F3FF`, icon `image` 32px màu `#7C3AED` ở giữa, badge `IMG`.
  - Word/Text: nền `#EFF6FF`, icon `description` 32px màu `#2563EB`, badge `DOCX`.
  - Ghi chú: khi backend có thumbnail thật thì chỉ thay phần này bằng `Image`,
    không đổi gì khác.
- Chế độ chọn: checkbox góc trên trái, viền card `#4F46E5` 2px, ảnh mờ 85%.
- Chế độ List (segmented): card 64px như hiện tại nhưng icon tile 40px **có màu
  theo loại tệp** thay vì đỏ/tím cho tất cả.

## 7. Empty state

```
        ╭─────────╮
        │  📁 ✨  │   ← vòng tròn 72px, nền gradient #EEF2FF → #F5F3FF
        ╰─────────╯
      No documents yet
  Upload your first file to get started
      [ ↑ Upload a file ]
```

Chỉ hiện nút khi đang ở bộ lọc "All" (Favorites rỗng thì nút là "Browse all
files").

## 8. Dark mode

Giữ nguyên bố cục. Điểm dễ sai: nền chip/thư mục đang chọn phải là
`primary.withValues(alpha: .16)` chứ không dùng pastel light (sẽ chói).

---

## Thứ tự làm (mỗi bước build xanh rồi mới sang bước sau)

| Bước | Nội dung | File | Ước lượng |
|---|---|---|---|
| 1 | Nền 3 tầng + bóng card + token accent | `core/theme/app_theme.dart` | 30 phút |
| 2 | Header, toolbar, folder chip | `documents_screen.dart` | 1 giờ |
| 3 | Grid thumbnail, selection bar, empty state | `documents_screen.dart` | 2 giờ |

Bước 1 làm cả app đổi tông (dashboard, account, AI dùng chung `cardTheme`) nên
nên duyệt kỹ trước khi làm bước 2–3.

## Không nằm trong spec này

Menu ⋮ và các mục của nó, dialog (New folder / Split / Set password / Delete),
`DocumentsController`, `_guard`, logic upload/merge/export — **không đổi**.

## Rủi ro

- Grid nhiều cột làm mất `RefreshIndicator` kéo-để-tải-lại (hiện đang bọc
  `ListView`). Giữ bằng cách bọc `GridView` trong `RefreshIndicator` + `Stack`.
- Ảnh thumbnail giả không phản ánh nội dung thật → người dùng có thể tưởng app
  đã render trang. Nên để dòng kẻ rất nhạt (opacity thấp) để đọc là "placeholder".
- Bước 1 đổi `cardTheme` ảnh hưởng mọi màn: phải xem lại dashboard + account sau
  khi đổi, không chỉ màn Files.
