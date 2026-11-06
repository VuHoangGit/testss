import 'package:flutter_test/flutter_test.dart';
import 'package:testss/presentation/voice/voice_controller.dart';

/// Ghi âm được tích luỹ trong `captured` và CHỈ gửi khi người dùng bấm Send:
/// `pendingCommand` là đúng nội dung sẽ được xử lý.
void main() {
  test('pendingCommand ghép phần đã chốt với phần đang nghe dở', () {
    const VoiceState state = VoiceState(
      captured: 'go to the documents tab',
      interim: 'and open',
    );
    expect(state.pendingCommand, 'go to the documents tab and open');
  });

  test('pendingCommand bỏ qua phần rỗng', () {
    expect(const VoiceState(captured: 'run ocr').pendingCommand, 'run ocr');
    expect(const VoiceState(interim: 'hello').pendingCommand, 'hello');
    expect(const VoiceState().pendingCommand, '');
    expect(const VoiceState(captured: '   ', interim: ' ').pendingCommand, '');
  });

  test('copyWith giữ captured khi chỉ đổi phase/interim', () {
    const VoiceState state = VoiceState(captured: 'delete the contract file');
    final VoiceState updated = state.copyWith(
      phase: VoicePhase.idle,
      interim: '',
    );
    expect(updated.captured, 'delete the contract file');
    expect(updated.phase, VoicePhase.idle);
  });

  test('copyWith xoá captured khi truyền chuỗi rỗng', () {
    const VoiceState state = VoiceState(captured: 'x');
    expect(state.copyWith(captured: '').captured, '');
  });
}
