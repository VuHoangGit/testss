import 'dart:typed_data';

class OcrResult {
  const OcrResult({required this.text, required this.keyValues});

  final String text;
  final Map<String, String> keyValues;
}

abstract interface class AiRepository {
  Future<OcrResult> ocr(String documentId);

  Future<Uint8List> ocrWord(String documentId);

  Future<String> translate(String text, {String targetLanguage = 'English'});

  Future<String> chat(String question, {required List<String> documentIds});
}
