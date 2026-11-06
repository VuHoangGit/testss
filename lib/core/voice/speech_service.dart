/// Bọc speech_to_text — nhận lệnh push-to-talk tiếng Anh (en-US).
///
/// Web (Edge/Chrome) dùng Web Speech API: mic chỉ bật sau khi người dùng
/// chủ động bấm nút (user gesture). Lỗi engine/quyền được báo qua callback
/// thay vì ném exception để UI hiển thị hướng dẫn.
library;

import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

class SpeechService {
  final SpeechToText _stt = SpeechToText();
  bool _initialized = false;
  bool _available = false;

  bool get isAvailable => _available;
  bool get isListening => _stt.isListening;

  /// Xin quyền + khởi tạo engine. Trả false khi mic không khả dụng.
  Future<bool> initialize({void Function(String message)? onError}) async {
    if (_initialized) return _available;
    try {
      _available = await _stt.initialize(
        onError: (SpeechRecognitionError error) =>
            onError?.call(error.errorMsg),
      );
    } on Exception {
      _available = false;
    }
    _initialized = true;
    return _available;
  }

  /// Bắt đầu nghe. [onResult] nhận transcript tạm (isFinal=false) hoặc cuối
  /// (isFinal=true). Trên web engine tự kết thúc khi người dùng ngừng nói —
  /// controller quyết định nghe tiếp hay không (không tự gửi đi).
  Future<void> listen({
    required void Function(String text, bool isFinal) onResult,
    required void Function(String message) onError,
  }) async {
    if (!_available) return;
    try {
      await _stt.listen(
        onResult: (SpeechRecognitionResult result) =>
            onResult(result.recognizedWords, result.finalResult),
        listenOptions: SpeechListenOptions(
          localeId: 'en-US',
          partialResults: true,
          cancelOnError: true,
          listenMode: ListenMode.dictation,
        ),
      );
    } on Exception catch (error) {
      // Engine có thể từ chối lệnh listen (đang chạy phiên khác trên web).
      onError('$error');
    }
  }

  Future<void> stop() async {
    try {
      await _stt.stop();
    } on Exception {
      // Engine có thể đã tự dừng — bỏ qua.
    }
  }

  Future<void> cancel() async {
    try {
      await _stt.cancel();
    } on Exception {
      // Engine có thể đã tự dừng — bỏ qua.
    }
  }
}
