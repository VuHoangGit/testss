/// State machine của trợ lý giọng nói:
/// idle → listening (push-to-talk) → processing (gọi API) → executing → idle.
///
/// Chống gửi trùng (không nhận lệnh mới khi đang xử lý); mic phải do người
/// dùng bấm (Web Speech API yêu cầu user gesture).
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
    this.transcript,
    this.reply,
    this.ttsEnabled = true,
    this.micAvailable = true,
    this.lastError,
  });

  final VoicePhase phase;
  final String interim;
  final String? transcript;
  final String? reply;
  final bool ttsEnabled;
  final bool micAvailable;
  final String? lastError;

  VoiceState copyWith({
    VoicePhase? phase,
    String? interim,
    String? transcript,
    String? reply,
    bool? ttsEnabled,
    bool? micAvailable,
    String? lastError,
  }) =>
      VoiceState(
        phase: phase ?? this.phase,
        interim: interim ?? this.interim,
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

  /// Bấm nút mic: bắt đầu nghe nếu rảnh, dừng nghe nếu đang nghe.
  Future<void> toggleMic() async {
    switch (state.phase) {
      case VoicePhase.idle:
        await startListening();
      case VoicePhase.listening:
        await _speech.stop();
        // Người dùng chủ động dừng: nếu chưa có kết quả cuối thì hủy.
        state = state.copyWith(phase: VoicePhase.idle, interim: '');
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
            'Không dùng được micro. Hãy kiểm tra quyền micro cho trang web này '
            'trong cài đặt trình duyệt, hoặc gõ lệnh vào ô văn bản.',
      );
      return;
    }
    state = state.copyWith(
      phase: VoicePhase.listening,
      interim: '',
      transcript: null,
      lastError: null,
    );
    await _speech.listen(
      onResult: (String text, bool isFinal) {
        if (isFinal) {
          if (text.trim().length < 2) {
            // Nghe được nhưng quá ngắn — coi như không nghe rõ.
            state = state.copyWith(
              phase: VoicePhase.idle,
              interim: '',
              reply: 'Không nghe rõ, bạn thử nói lại nhé.',
            );
            return;
          }
          _process(text.trim());
        } else {
          state = state.copyWith(interim: text);
        }
      },
      onError: (String message) => _onSpeechError(message),
    );
  }

  void _onSpeechError(String message) {
    final bool permission = message.toLowerCase().contains('permission');
    state = state.copyWith(
      phase: VoicePhase.idle,
      interim: '',
      lastError: message,
      reply: permission
          ? 'Chưa cấp quyền micro. Hãy cho phép micro cho trang này trong '
              'cài đặt trình duyệt rồi bấm nút mic lại.'
          : 'Lỗi nhận dạng giọng nói ($message). Thử lại hoặc gõ lệnh vào ô văn bản.',
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
    );
    try {
      final VoiceCommandResult decision = await ref
          .read(aiRepositoryProvider)
          .voiceCommand(transcript, context: _buildContext(), sessionId: _sessionId);
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
        reply: 'Không thực hiện được lệnh: $error',
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

  /// Đóng panel phản hồi.
  void dismiss() {
    _tts.stop();
    state = VoiceState(
      ttsEnabled: state.ttsEnabled,
      micAvailable: state.micAvailable,
    );
  }
}
