/// So khớp tên tài liệu/thư mục từ lệnh nói.
///
/// Lệnh nói thường sai dấu, thiếu đuôi file hay thừa/thiếu từ — chuẩn hóa
/// về dạng không dấu, chữ thường rồi so: khớp chính xác → khớp chứa duy
/// nhất → không khớp (kèm gợi ý theo từ khóa chung để hỏi lại người dùng).
library;

const String _diacriticsSource =
    'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
    'ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ';
const String _diacriticsTarget =
    'aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd'
    'AAAAAAAAAAAAAAAAAEEEEEEEEEEEIIIIIOOOOOOOOOOOOOOOOOUUUUUUUUUUUYYYYYD';

final List<int> _sourceRunes = _diacriticsSource.runes.toList();
final List<int> _targetRunes = _diacriticsTarget.runes.toList();

/// Bỏ dấu tiếng Việt (à→a, Đ→D...). Không dùng gói ngoài — bảng map tĩnh.
String removeVietnameseDiacritics(String input) {
  final StringBuffer buffer = StringBuffer();
  for (final int code in input.runes) {
    final int index = _sourceRunes.indexOf(code);
    buffer.writeCharCode(index >= 0 ? _targetRunes[index] : code);
  }
  return buffer.toString();
}

/// Chuẩn hóa để so khớp: bỏ dấu, chữ thường, bỏ đuôi file, mọi dấu phân cách
/// (gạch nối/gạch dưới…) thành một khoảng trắng.
String normalizeName(String input) {
  final String noDiacritics =
      removeVietnameseDiacritics(input).toLowerCase().trim();
  final String withoutExtension =
      noDiacritics.replaceFirst(RegExp(r'\.[a-z0-9]{1,6}$'), '');
  return withoutExtension
      .replaceAll(RegExp(r'[^a-z0-9]+'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
}

enum NameMatchStatus { unique, ambiguous, none }

class NameMatch<T> {
  const NameMatch({required this.status, this.item, this.candidates = const []});

  final NameMatchStatus status;

  /// Đối tượng khớp duy nhất (chỉ có nghĩa khi status == unique).
  final T? item;

  /// Ứng viên khi mơ hồ, hoặc gợi ý khi không khớp (để hỏi lại người dùng).
  final List<T> candidates;
}

/// Tìm [query] trong [items] theo tên đã chuẩn hóa.
NameMatch<T> matchByName<T>({
  required String query,
  required Iterable<T> items,
  required String Function(T) nameOf,
}) {
  final String q = normalizeName(query);
  if (q.isEmpty) {
    return NameMatch<T>(status: NameMatchStatus.none, candidates: items.toList());
  }

  final Map<T, String> normalized = <T, String>{
    for (final T item in items) item: normalizeName(nameOf(item)),
  };

  // 1) Khớp chính xác.
  final List<T> exact = <T>[
    for (final MapEntry<T, String> entry in normalized.entries)
      if (entry.value == q) entry.key,
  ];
  if (exact.length == 1) {
    return NameMatch<T>(status: NameMatchStatus.unique, item: exact.first);
  }
  if (exact.length > 1) {
    return NameMatch<T>(status: NameMatchStatus.ambiguous, candidates: exact);
  }

  // 2) Khớp chứa (một phía chứa phía kia), bỏ qua từ quá ngắn.
  final List<T> contains = <T>[
    for (final MapEntry<T, String> entry in normalized.entries)
      if (entry.value.contains(q) || q.contains(entry.value)) entry.key,
  ];
  if (contains.length == 1) {
    return NameMatch<T>(status: NameMatchStatus.unique, item: contains.first);
  }
  if (contains.length > 1) {
    return NameMatch<T>(status: NameMatchStatus.ambiguous, candidates: contains);
  }

  // 3) Không khớp — gợi ý theo từ khóa chung (từ ≥ 3 ký tự, bỏ "pdf"...).
  final Set<String> queryTokens = _tokens(q);
  final List<T> suggestions = <T>[
    for (final MapEntry<T, String> entry in normalized.entries)
      if (_tokens(entry.value).any(queryTokens.contains)) entry.key,
  ];
  return NameMatch<T>(status: NameMatchStatus.none, candidates: suggestions);
}

Set<String> _tokens(String normalized) => <String>{
      for (final String token in normalized.split(RegExp(r'[^a-z0-9]+')))
        if (token.length >= 3 && token != 'pdf' && token != 'docx') token,
    };
