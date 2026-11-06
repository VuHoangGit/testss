/// State machine của trợ lý giọng nói:
/// idle → listening (ghi âm) → [người dùng bấm Gửi] → processing (gọi API)
/// → executing → idle.
///
/// Ghi âm KHÔNG tự gửi: transcript được tích luỹ trong `captured`, người dùng
/// bấm nút Send thì mới xử lý (hoặc Discard để bỏ). Chống gửi trùng (không nhận
/// lệnh mới khi đang xử lý); mic phải do người dùng bấm (Web Speech API yêu cầu
/// user gesture).
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/voice/speech_service.dart';
import '../../core/voice/tts_service.dart';
import '../../domain/entities/document_entities.dart';
import '../../domain/repositories/ai_repository.dart';
import '../ai/ai_providers.dart';
import '../documents/documents_controller.dart';
import '../documents/documents_providers.dart';
import '../shell/shell_providers.dart';
import 'voice_action_executor.dart';

enum VoicePhase { idle, listening, processing, executing }

class VoiceState {
  const VoiceState({
    this.phase = VoicePhase.idle,
    this.interim = '',
    this.captured = '',
    this.transcript,
    this.reply,
    this.ttsEnabled = true,
    this.micAvailable = true,
    this.lastError,
  });

  final VoicePhase phase;

  /// Văn bản đang nghe dở (chưa chốt) của engine nhận dạng.
  final String interim;

  /// Văn bản đã chốt trong lần ghi âm hiện tại — chờ người dùng bấm Gửi.
  final String captured;
  final String? transcript;
  final String? reply;
  final bool ttsEnabled;
  final bool micAvailable;
  final String? lastError;

  /// Toàn bộ nội dung sẽ gửi đi nếu bấm Gửi ngay lúc này.
  String get pendingCommand => <String>[
    captured,
    interim,
  ].where((String part) => part.trim().isNotEmpty).join(' ').trim();

  VoiceState copyWith({
    VoicePhase? phase,
    String? interim,
    String? captured,
    String? transcript,
    String? reply,
    bool? ttsEnabled,
    bool? micAvailable,
    String? lastError,
  }) => VoiceState(
    phase: phase ?? this.phase,
    interim: interim ?? this.interim,
    captured: captured ?? this.captured,
    transcript: transcript ?? this.transcript,
    reply: reply ?? this.reply,
    ttsEnabled: ttsEnabled ?? this.ttsEnabled,
    micAvailable: micAvailable ?? this.micAvailable,
    lastError: lastError ?? this.lastError,
  );
}

final NotifierProvider<VoiceController, VoiceState> voiceControllerProvider =
    NotifierProvider<VoiceController, VoiceState>(VoiceController.new);

class VoiceController extends Notifier<VoiceState> {
  final SpeechService _speech = SpeechService();
  final TtsService _tts = TtsService();

  /// Id phiên voice của lần chạy app này — server giữ ngữ cảnh theo id này.
  static final String _sessionId =
      'app-${DateTime.now().millisecondsSinceEpoch}';

  @override
  VoiceState build() => const VoiceState();

  /// Bấm nút mic: bắt đầu ghi âm nếu rảnh, dừng ghi âm nếu đang nghe.
  ///
  /// Dừng ghi âm KHÔNG gửi đi — nội dung vẫn nằm trong `captured` để người dùng
  /// kiểm tra rồi bấm Gửi (hoặc Discard).
  Future<void> toggleMic() async {
    switch (state.phase) {
      case VoicePhase.idle:
        await startListening();
      case VoicePhase.listening:
        // Đặt phase trước khi stop để callback final (nếu có) không tự nghe lại.
        state = state.copyWith(phase: VoicePhase.idle, interim: '');
        await _speech.stop();
      case VoicePhase.processing:
      case VoicePhase.executing:
        // Đang bận — bỏ qua lượt bấm trùng (chống gửi trùng).
        break;
    }
  }

  Future<void> startListening() async {
    final bool ok = await _speech.initialize(
      onError: (String message) => _onSpeechError(message),
    );
    if (!ok) {
      state = state.copyWith(
        phase: VoicePhase.idle,
        micAvailable: false,
        reply:
            'Microphone unavailable. Check the microphone permission for this site '
            'in your browser settings, or type the command in the text box.',
      );
      return;
    }
    _restarts = 0;
    state = state.copyWith(
      phase: VoicePhase.listening,
      interim: '',
      captured: '',
      transcript: null,
      lastError: null,
    );
    await _listenOnce();
  }

  /// Số lần tự nghe lại sau khi engine tự kết thúc một đoạn (Chrome kết thúc
  /// nhận dạng khi người dùng ngừng nói) — chặn vòng lặp vô hạn.
  int _restarts = 0;
  static const int _maxRestarts = 40;

  Future<void> _listenOnce() async {
    await _speech.listen(
      onResult: (String text, bool isFinal) {
        if (isFinal) {
          final String piece = text.trim();
          if (piece.isNotEmpty) {
            _appendCaptured(piece);
          }
          // Engine (web) tự kết thúc khi ngừng nói: nghe tiếp để người dùng có
          // thể nói thêm, vẫn KHÔNG tự gửi. Nghe được đoạn rỗng → dừng hẳn.
          if (state.phase == VoicePhase.listening) {
            if (piece.isEmpty || _restarts >= _maxRestarts) {
              state = state.copyWith(phase: VoicePhase.idle, interim: '');
            } else {
              _restarts++;
              _listenOnce();
            }
          }
        } else {
          state = state.copyWith(interim: text);
        }
      },
      onError: (String message) => _onSpeechError(message),
    );
  }

  /// Nối đoạn văn bản vừa chốt vào bản ghi, tránh lặp khi engine trả lại cả câu.
  void _appendCaptured(String piece) {
    final String current = state.captured.trim();
    String merged;
    if (current.isEmpty) {
      merged = piece;
    } else if (current == piece || current.endsWith(piece)) {
      merged = current;
    } else if (piece.startsWith(current)) {
      merged = piece;
    } else {
      merged = '$current $piece';
    }
    state = state.copyWith(captured: merged, interim: '');
  }

  /// Bấm Gửi: đưa toàn bộ nội dung đã ghi âm đi xử lý.
  Future<void> sendRecording() async {
    if (state.phase == VoicePhase.processing ||
        state.phase == VoicePhase.executing) {
      return;
    }
    final String command = state.pendingCommand;
    if (command.isEmpty) {
      state = state.copyWith(
        phase: VoicePhase.idle,
        reply:
            'Nothing was recorded. Press the mic button, say your command, '
            'then press Send.',
      );
      return;
    }
    await _process(command);
  }

  /// Bỏ bản ghi âm hiện tại, không gửi đi.
  Future<void> discardRecording() async {
    state = state.copyWith(
      phase: VoicePhase.idle,
      captured: '',
      interim: '',
      transcript: null,
    );
    await _speech.stop();
  }

  void _onSpeechError(String message) {
    final bool permission = message.toLowerCase().contains('permission');
    state = state.copyWith(
      phase: VoicePhase.idle,
      interim: '',
      lastError: message,
      reply: permission
          ? 'Microphone permission is not granted. Allow the microphone for this page '
                'in your browser settings, then press the mic button again.'
          : 'Speech recognition error ($message). Try again or type the command in the text box.',
    );
  }

  /// Vào lệnh bằng văn bản (fallback khi không muốn/mic không dùng được).
  Future<void> submitText(String text) async {
    final String trimmed = text.trim();
    if (trimmed.isEmpty) return;
    if (state.phase != VoicePhase.idle) return;
    await _process(trimmed);
  }

  Future<void> _process(String transcript) async {
    await _speech.stop();
    state = state.copyWith(
      phase: VoicePhase.processing,
      transcript: transcript,
      interim: '',
      captured: '',
    );
    try {
      final VoiceCommandResult decision = await ref
          .read(aiRepositoryProvider)
          .voiceCommand(
            transcript,
            context: _buildContext(),
            sessionId: _sessionId,
          );
      state = state.copyWith(phase: VoicePhase.executing);
      String feedback = decision.reply;
      if (decision.action == 'stop_speaking') {
        await _tts.stop();
      } else {
        feedback = await executeVoiceAction(ref, decision);
      }
      state = state.copyWith(phase: VoicePhase.idle, reply: feedback);
      if (state.ttsEnabled) {
        await _tts.speak(feedback);
      }
    } on Exception catch (error) {
      state = state.copyWith(
        phase: VoicePhase.idle,
        reply: 'Could not run the command: $error',
      );
    }
  }

  VoiceAppContext _buildContext() {
    final DocumentsState documents =
        ref.read(documentsControllerProvider).value ?? const DocumentsState();
    final int tabIndex = ref.read(shellTabProvider);
    return VoiceAppContext(
      currentTab: tabIndex < shellTabIds.length ? shellTabIds[tabIndex] : null,
      folders: <VoiceFolderRef>[
        for (final DocumentFolder folder in documents.folders)
          VoiceFolderRef(id: folder.id, name: folder.name),
      ],
      documents: <VoiceDocumentRef>[
        for (final DocumentItem doc in documents.documents)
          VoiceDocumentRef(id: doc.id, name: doc.name, mimeType: doc.mimeType),
      ],
    );
  }

  void setTtsEnabled(bool enabled) {
    state = state.copyWith(ttsEnabled: enabled);
    if (!enabled) {
      _tts.stop();
    }
  }

  Future<void> stopSpeaking() => _tts.stop();

  /// Đóng panel phản hồi (dừng đọc + dừng ghi âm, bỏ bản ghi đang chờ).
  void dismiss() {
    _tts.stop();
    _speech.stop();
    state = VoiceState(
      ttsEnabled: state.ttsEnabled,
      micAvailable: state.micAvailable,
    );
  }
}
