/// Bọc flutter_tts — đọc phản hồi tiếng Anh (giọng en-US nếu có).
library;

import 'package:flutter_tts/flutter_tts.dart';

class TtsService {
  final FlutterTts _tts = FlutterTts();
  bool _initialized = false;

  Future<void> _ensureInit() async {
    if (_initialized) return;
    try {
      await _tts.setLanguage('en-US');
      await _tts.setSpeechRate(0.5);
      await _tts.awaitSpeakCompletion(true);
    } on Exception {
      // Web engine có thể không cho cấu hình — vẫn thử speak().
    }
    _initialized = true;
  }

  /// Đọc một đoạn text; lỗi engine bị nuốt im lặng (TTS chỉ là bổ sung).
  Future<void> speak(String text) async {
    if (text.trim().isEmpty) return;
    await _ensureInit();
    try {
      await _tts.speak(text);
    } on Exception {
      // Không đọc được thì hiển thị text là đủ.
    }
  }

  Future<void> stop() async {
    if (!_initialized) return;
    try {
      await _tts.stop();
    } on Exception {
      // Đang không phát — bỏ qua.
    }
  }
}
