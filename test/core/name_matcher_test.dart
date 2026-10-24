import 'package:flutter_test/flutter_test.dart';
import 'package:testss/core/voice/name_matcher.dart';

void main() {
  group('removeVietnameseDiacritics', () {
    test('bỏ dấu tiếng Việt', () {
      expect(
        removeVietnameseDiacritics('Hợp Đồng Đấu Thầu 2024'),
        'Hop Dong Dau Thau 2024',
      );
    });

    test('giữ nguyên chữ không dấu', () {
      expect(removeVietnameseDiacritics('bao-cao.docx'), 'bao-cao.docx');
    });
  });

  group('normalizeName', () {
    test('bỏ dấu, chữ thường, gộp khoảng trắng, bỏ đuôi file', () {
      expect(normalizeName('  Hợp Đồng  2024.PDF '), 'hop dong 2024');
    });
  });

  group('matchByName', () {
    test('khớp chính xác (không dấu, có đuôi file)', () {
      final NameMatch<String> match = matchByName<String>(
        query: 'hợp đồng',
        items: <String>['hop-dong-2024.pdf', 'bao-cao.docx'],
        nameOf: (String s) => s,
      );
      expect(match.status, NameMatchStatus.unique);
      expect(match.item, 'hop-dong-2024.pdf');
    });

    test('khớp chứa', () {
      final NameMatch<String> match = matchByName<String>(
        query: 'báo cáo',
        items: <String>['hop-dong.pdf', 'bao-cao-2024.pdf'],
        nameOf: (String s) => s,
      );
      expect(match.status, NameMatchStatus.unique);
      expect(match.item, 'bao-cao-2024.pdf');
    });

    test('nhiều ứng viên → mơ hồ, trả danh sách để hỏi lại', () {
      final NameMatch<String> match = matchByName<String>(
        query: 'hợp đồng',
        items: <String>['hop-dong-1.pdf', 'hop-dong-2.pdf', 'bao-cao.pdf'],
        nameOf: (String s) => s,
      );
      expect(match.status, NameMatchStatus.ambiguous);
      expect(match.candidates, <String>['hop-dong-1.pdf', 'hop-dong-2.pdf']);
    });

    test('không khớp → gợi ý theo từ khóa chung', () {
      final NameMatch<String> match = matchByName<String>(
        query: 'hợp đồng đấu thầu',
        items: <String>['hop-dong-2024.pdf', 'bao-cao.pdf'],
        nameOf: (String s) => s,
      );
      expect(match.status, NameMatchStatus.none);
      expect(match.candidates, contains('hop-dong-2024.pdf'));
    });

    test('không khớp và không có gợi ý nào', () {
      final NameMatch<String> match = matchByName<String>(
        query: 'nhạc lofi',
        items: <String>['hop-dong.pdf'],
        nameOf: (String s) => s,
      );
      expect(match.status, NameMatchStatus.none);
      expect(match.candidates, isEmpty);
    });
  });
}
