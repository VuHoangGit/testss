import 'dart:typed_data';

/// Nội dung một trang tài liệu sau OCR.
class OcrPage {
  const OcrPage({
    required this.page,
    required this.text,
    this.fromTextLayer = false,
  });

  /// Số trang, bắt đầu từ 1.
  final int page;
  final String text;

  /// True = chữ lấy từ lớp text của PDF (không gọi AI); false = AI đọc ảnh.
  final bool fromTextLayer;
}

class OcrResult {
  const OcrResult({
    required this.text,
    required this.keyValues,
    this.pages = const <OcrPage>[],
    this.warnings = const <String>[],
  });

  final String text;
  final Map<String, String> keyValues;

  /// Nội dung từng trang (rỗng với client cũ / khi server chỉ trả text).
  final List<OcrPage> pages;

  /// Cảnh báo hậu kiểm: chỗ không đọc được, ngày/số tiền nghi sai…
  final List<String> warnings;
}

/// Thư mục trong ngữ cảnh gửi kèm lệnh giọng nói (chỉ tên + id).
class VoiceFolderRef {
  const VoiceFolderRef({required this.id, required this.name});

  final String id;
  final String name;
}

/// Tài liệu trong ngữ cảnh gửi kèm lệnh giọng nói.
class VoiceDocumentRef {
  const VoiceDocumentRef({
    required this.id,
    required this.name,
    required this.mimeType,
  });

  final String id;
  final String name;
  final String mimeType;
}

/// Ngữ cảnh app tại thời điểm ra lệnh (tab, thư mục, tài liệu đang có).
class VoiceAppContext {
  const VoiceAppContext({
    this.currentTab,
    this.folders = const <VoiceFolderRef>[],
    this.documents = const <VoiceDocumentRef>[],
  });

  final String? currentTab;
  final List<VoiceFolderRef> folders;
  final List<VoiceDocumentRef> documents;
}

/// Kết quả phân tích lệnh giọng nói: action null = chỉ trả lời text.
class VoiceCommandResult {
  const VoiceCommandResult({
    required this.action,
    required this.params,
    required this.reply,
  });

  final String? action;
  final Map<String, dynamic> params;
  final String reply;
}

abstract interface class AiRepository {
  Future<OcrResult> ocr(String documentId);

  Future<Uint8List> ocrWord(String documentId);

  /// Trích văn bản của tài liệu (PDF/Word/txt/md) để hiển thị + dịch vùng chọn.
  Future<String> extractText(String documentId);

  /// [sourceLanguage] null/rỗng = tự phát hiện ngôn ngữ nguồn.
  Future<String> translate(
    String text, {
    String targetLanguage = 'English',
    String? sourceLanguage,
  });

  Future<String> chat(String question, {required List<String> documentIds});

  Future<VoiceCommandResult> voiceCommand(
    String transcript, {
    required VoiceAppContext context,
    required String sessionId,
  });
}
