import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:testss/domain/repositories/ai_repository.dart';
import 'package:testss/presentation/ai/ai_providers.dart';
import 'package:testss/presentation/documents/documents_controller.dart';
import 'package:testss/presentation/documents/documents_providers.dart';
import 'package:testss/presentation/shell/shell_providers.dart';
import 'package:testss/presentation/voice/voice_action_executor.dart';

VoiceCommandResult _decision(String action, Map<String, dynamic> params) =>
    VoiceCommandResult(action: action, params: params, reply: '...');

/// Provider trung gian để lấy một Ref dùng được trong test (giữ subscription
/// suốt test bằng container.listen).
final Provider<Ref> _refCaptureProvider = Provider<Ref>((Ref ref) => ref);

void main() {
  // Executor chạm rootNavigatorKey (GlobalKey) → cần binding đã init.
  TestWidgetsFlutterBinding.ensureInitialized();

  late ProviderContainer container;
  late Ref ref;

  setUp(() {
    container = ProviderContainer(
      overrides: [
        documentsControllerProvider.overrideWith(_EmptyDocumentsController.new),
      ],
    );
    addTearDown(container.dispose);
    container.listen<Ref>(_refCaptureProvider, (_, _) {});
    ref = container.read(_refCaptureProvider);
  });

  test('navigate_tab đổi shellTabProvider', () async {
    final String feedback = await executeVoiceAction(
      ref,
      _decision('navigate_tab', <String, dynamic>{'tab': 'ai'}),
    );
    expect(container.read(shellTabProvider), 2);
    expect(feedback, contains('AI'));
  });

  test('open_ai_tool mở tab AI + đúng sub-tool', () async {
    final String feedback = await executeVoiceAction(
      ref,
      _decision('open_ai_tool', <String, dynamic>{'tool': 'ocr'}),
    );
    expect(container.read(shellTabProvider), 2);
    expect(container.read(aiToolProvider), 0);
    expect(feedback, isNotEmpty);
  });

  test('read_aloud đọc kết quả OCR gần nhất', () async {
    ref
        .read(lastAiResultsProvider.notifier)
        .setOcr('Nội dung hợp đồng', <String, String>{});
    final String feedback = await executeVoiceAction(
      ref,
      _decision('read_aloud', <String, dynamic>{'what': 'ocr_result'}),
    );
    expect(feedback, 'Nội dung hợp đồng');
  });

  test('read_aloud khi chưa có kết quả → báo chưa có', () async {
    final String feedback = await executeVoiceAction(
      ref,
      _decision('read_aloud', <String, dynamic>{'what': 'translation'}),
    );
    expect(feedback, 'There is no translation yet.');
  });

  test('select_folder không khớp → phản hồi không tìm thấy', () async {
    final String feedback = await executeVoiceAction(
      ref,
      _decision('select_folder', <String, dynamic>{'folder_name': 'abc'}),
    );
    expect(feedback, contains('No folder named'));
  });

  test('list_documents rỗng → báo chưa có tài liệu', () async {
    final String feedback = await executeVoiceAction(
      ref,
      _decision('list_documents', <String, dynamic>{}),
    );
    expect(feedback, 'There are no documents yet.');
  });

  test('action lạ → không thực thi, trả thông báo', () async {
    final String feedback = await executeVoiceAction(
      ref,
      _decision('open_youtube', <String, dynamic>{'url': 'x'}),
    );
    expect(feedback, contains('not supported by voice'));
    expect(container.read(shellTabProvider), 0);
  });
}

/// Controller trả state rỗng, không đụng repository thật.
class _EmptyDocumentsController extends DocumentsController {
  @override
  Future<DocumentsState> build() async => const DocumentsState();
}
