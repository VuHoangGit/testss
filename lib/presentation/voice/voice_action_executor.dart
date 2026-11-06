/// Thực thi action do backend (LLM) chọn.
///
/// Nguyên tắc: chỉ thực thi action nằm trong danh sách đã biết; resolve
/// TÊN → tài liệu/thư mục bằng name_matcher trên danh sách client đang có
/// (không tin id từ AI); hành động phá hủy (xóa/gộp/tách) luôn qua dialog
/// xác nhận/tự điền tham số để người dùng duyệt tay.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/navigation/root_navigator_key.dart';
import '../../core/voice/name_matcher.dart';
import '../../domain/entities/document_entities.dart';
import '../../domain/repositories/ai_repository.dart';
import '../ai/ai_providers.dart';
import '../documents/documents_controller.dart';
import '../documents/documents_providers.dart';
import '../documents/viewer_opener.dart';
import '../shell/shell_providers.dart';

const Map<String, int> _aiToolIndexes = <String, int>{
  'ocr': 0,
  'chat': 1,
  'translate': 2,
};

/// Nhãn hiển thị của các tab (đọc lên bằng TTS cho tự nhiên).
const Map<String, String> _tabLabels = <String, String>{
  'dashboard': 'Overview',
  'documents': 'Documents',
  'ai': 'AI',
  'account': 'Account',
};

/// Thực thi và trả về câu phản hồi cuối (hiển thị + đọc bằng TTS).
/// Mọi exception đã được bắt trong này — không ném ra ngoài.
Future<String> executeVoiceAction(Ref ref, VoiceCommandResult decision) async {
  final String? action = decision.action;
  if (action == null) {
    return decision.reply;
  }
  try {
    return await switch (action) {
      'navigate_tab' => _navigateTab(ref, _param(decision, 'tab')),
      'open_ai_tool' => _openAiTool(ref, _param(decision, 'tool')),
      'select_folder' => _selectFolder(ref, _param(decision, 'folder_name')),
      'list_documents' => _listDocuments(ref),
      'open_document' => _openDocument(ref, _param(decision, 'name_query')),
      'run_ocr' => _runOcr(ref, _param(decision, 'name_query')),
      'ask_chat' => _askChat(
        ref,
        _param(decision, 'question'),
        decision.params['name_query'] as String?,
      ),
      'translate_text' => _translateText(ref, decision.params),
      'read_aloud' => _readAloud(ref, _param(decision, 'what')),
      'stop_speaking' => 'Stopped reading.',
      'delete_document' => _deleteDocument(ref, _param(decision, 'name_query')),
      'merge_documents' => _mergeDocuments(ref, decision.params),
      'split_document' => _splitDocument(ref, decision.params),
      _ => 'The "$action" feature is not supported by voice yet.',
    };
  } on Exception catch (error) {
    return 'Action failed: $error';
  }
}

String _param(VoiceCommandResult decision, String name) =>
    decision.params[name]?.toString() ?? '';

DocumentsState _documents(Ref ref) =>
    ref.read(documentsControllerProvider).value ?? const DocumentsState();

/// Đóng viewer đang mở (nếu có) trước khi đổi tab.
void _popViewerIfOpen() {
  final NavigatorState? navigator = rootNavigatorKey.currentState;
  if (navigator != null && navigator.canPop()) {
    navigator.pop();
  }
}

Future<String> _navigateTab(Ref ref, String tabId) async {
  final int? index = ref.read(shellTabProvider.notifier).indexById(tabId);
  if (index == null) {
    return 'Could not recognize the tab "$tabId".';
  }
  _popViewerIfOpen();
  ref.read(shellTabProvider.notifier).setTab(index);
  return 'Switched to the ${_tabLabels[tabId] ?? tabId} tab.';
}

Future<String> _openAiTool(Ref ref, String toolId) async {
  final int? toolIndex = _aiToolIndexes[toolId];
  if (toolIndex == null) {
    return 'Could not recognize the tool "$toolId".';
  }
  _popViewerIfOpen();
  ref.read(shellTabProvider.notifier).setTab(2); // tab AI
  ref.read(aiToolProvider.notifier).setTool(toolIndex);
  return 'Opened the requested AI tool.';
}

Future<String> _selectFolder(Ref ref, String folderName) async {
  final DocumentsState data = _documents(ref);
  final NameMatch<DocumentFolder> match = matchByName<DocumentFolder>(
    query: folderName,
    items: data.folders,
    nameOf: (DocumentFolder folder) => folder.name,
  );
  if (match.status == NameMatchStatus.ambiguous) {
    return _askAgain(
      'Folder "$folderName"',
      match.candidates.map((DocumentFolder folder) => folder.name).toList(),
    );
  }
  if (match.item == null) {
    return 'No folder named "$folderName" was found.';
  }
  _popViewerIfOpen();
  ref.read(shellTabProvider.notifier).setTab(1); // tab Tài liệu
  await ref
      .read(documentsControllerProvider.notifier)
      .selectFolder(match.item!.id);
  return 'Filtered by the "${match.item!.name}" folder.';
}

Future<String> _listDocuments(Ref ref) async {
  final DocumentsState data = _documents(ref);
  _popViewerIfOpen();
  ref.read(shellTabProvider.notifier).setTab(1);
  if (data.documents.isEmpty) {
    return 'There are no documents yet.';
  }
  final List<String> names = data.documents
      .take(10)
      .map((DocumentItem doc) => doc.name)
      .toList();
  final String suffix = data.documents.length > 10
      ? ' and ${data.documents.length - 10} more files'
      : '';
  return 'You have ${data.documents.length} documents: ${names.join(', ')}$suffix.';
}

Future<DocumentItem?> _resolveDocument(
  Ref ref,
  String nameQuery, {
  required void Function(String feedback) onAmbiguous,
}) {
  final DocumentsState data = _documents(ref);
  final NameMatch<DocumentItem> match = matchByName<DocumentItem>(
    query: nameQuery,
    items: data.documents,
    nameOf: (DocumentItem doc) => doc.name,
  );
  switch (match.status) {
    case NameMatchStatus.unique:
      return Future<DocumentItem?>.value(match.item);
    case NameMatchStatus.ambiguous:
      onAmbiguous(
        _askAgain(
          'Document "$nameQuery"',
          match.candidates.map((DocumentItem doc) => doc.name).toList(),
        ),
      );
    case NameMatchStatus.none:
      final String hint = match.candidates.isEmpty
          ? 'The document list is empty or has no similarly named file.'
          : 'Similar files: ${match.candidates.take(5).map((DocumentItem d) => d.name).join(', ')}.';
      onAmbiguous('No document named "$nameQuery" was found. $hint');
  }
  return Future<DocumentItem?>.value(null);
}

String _askAgain(String title, List<String> candidates) {
  final String list = candidates
      .take(5)
      .toList()
      .asMap()
      .entries
      .map((MapEntry<int, String> entry) => '${entry.key + 1}. ${entry.value}')
      .join('; ');
  return '$title matches several choices: $list. Please say the full name again.';
}

Future<String> _openDocument(Ref ref, String nameQuery) async {
  late String feedback;
  final DocumentItem? doc = await _resolveDocument(
    ref,
    nameQuery,
    onAmbiguous: (String message) => feedback = message,
  );
  if (doc == null) return feedback;
  return openDocumentViewer(
    repository: ref.read(documentsRepositoryProvider),
    aiRepository: ref.read(aiRepositoryProvider),
    doc: doc,
  );
}

Future<String> _runOcr(Ref ref, String nameQuery) async {
  late String feedback;
  final DocumentItem? doc = await _resolveDocument(
    ref,
    nameQuery,
    onAmbiguous: (String message) => feedback = message,
  );
  if (doc == null) return feedback;
  if (!doc.isPdf) {
    return 'OCR currently supports PDF files only.';
  }
  ref.read(shellTabProvider.notifier).setTab(2);
  ref.read(aiToolProvider.notifier).setTool(0); // OCR
  ref.read(aiDocumentIdProvider.notifier).select(doc.id);
  final OcrResult result = await ref.read(aiRepositoryProvider).ocr(doc.id);
  ref.read(lastAiResultsProvider.notifier).setOcrResult(result);
  return 'Ran OCR on "${doc.name}". Say "read the result" to hear the content.';
}

Future<String> _askChat(Ref ref, String question, String? nameQuery) async {
  String? documentId = ref.read(aiDocumentIdProvider);
  if (nameQuery != null && nameQuery.isNotEmpty) {
    late String feedback;
    final DocumentItem? doc = await _resolveDocument(
      ref,
      nameQuery,
      onAmbiguous: (String message) => feedback = message,
    );
    if (doc == null) return feedback;
    if (!doc.isPdf) {
      return 'AI chat currently supports PDF files only.';
    }
    documentId = doc.id;
    ref.read(aiDocumentIdProvider.notifier).select(doc.id);
  }
  if (documentId == null) {
    return 'No document selected. Say the command again with the file name, for example "ask about the contract file".';
  }
  ref.read(shellTabProvider.notifier).setTab(2);
  ref.read(aiToolProvider.notifier).setTool(1); // Chat
  final ChatMessagesController messages = ref.read(
    chatMessagesProvider.notifier,
  );
  messages.add(question, fromUser: true);
  try {
    final String answer = await ref
        .read(aiRepositoryProvider)
        .chat(question, documentIds: <String>[documentId]);
    messages.add(answer, fromUser: false);
    ref.read(lastAiResultsProvider.notifier).setChat(question, answer);
    return answer;
  } on Exception catch (error) {
    messages.add('$error', fromUser: false);
    rethrow;
  }
}

Future<String> _translateText(Ref ref, Map<String, dynamic> params) async {
  final String text = params['text']?.toString() ?? '';
  if (text.isEmpty) {
    return 'There is no text to translate.';
  }
  final String targetLanguage =
      params['target_language']?.toString() ?? 'English';
  ref.read(shellTabProvider.notifier).setTab(2);
  ref.read(aiToolProvider.notifier).setTool(2); // Dịch
  final String translation = await ref
      .read(aiRepositoryProvider)
      .translate(text, targetLanguage: targetLanguage);
  ref.read(lastAiResultsProvider.notifier).setTranslation(text, translation);
  return translation;
}

Future<String> _readAloud(Ref ref, String what) async {
  final LastAiResults last = ref.read(lastAiResultsProvider);
  return switch (what) {
    'ocr_result' => last.ocrText ?? 'There is no OCR result yet.',
    'chat_answer' => last.chatAnswer ?? 'There is no AI answer yet.',
    'translation' => last.translation ?? 'There is no translation yet.',
    _ =>
      last.chatAnswer ??
          last.translation ??
          last.ocrText ??
          'There is nothing to read yet.',
  };
}

Future<String> _deleteDocument(Ref ref, String nameQuery) async {
  late String feedback;
  final DocumentItem? doc = await _resolveDocument(
    ref,
    nameQuery,
    onAmbiguous: (String message) => feedback = message,
  );
  if (doc == null) return feedback;
  final BuildContext? context = rootNavigatorKey.currentContext;
  if (context == null || !context.mounted) {
    return 'Could not open the confirmation dialog.';
  }
  final bool? ok = await showDialog<bool>(
    context: context,
    builder: (BuildContext ctx) => AlertDialog(
      title: const Text('Delete document?'),
      content: Text(
        'A voice command asked to delete "${doc.name}". The file will be deleted permanently, '
        'and this cannot be undone.',
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: Theme.of(ctx).colorScheme.error,
          ),
          onPressed: () => Navigator.of(ctx).pop(true),
          child: const Text('Delete'),
        ),
      ],
    ),
  );
  if (ok != true) {
    return 'Delete cancelled.';
  }
  await ref.read(documentsControllerProvider.notifier).deleteDocument(doc.id);
  return 'Deleted "${doc.name}".';
}

Future<String> _mergeDocuments(Ref ref, Map<String, dynamic> params) async {
  final DocumentsController notifier = ref.read(
    documentsControllerProvider.notifier,
  );
  final List<String> names = (params['names'] as List<dynamic>? ?? <dynamic>[])
      .map((dynamic name) => name.toString())
      .where((String name) => name.isNotEmpty)
      .toList();
  List<String> documentIds = <String>[];
  if (names.isNotEmpty) {
    for (final String name in names) {
      late String feedback;
      final DocumentItem? doc = await _resolveDocument(
        ref,
        name,
        onAmbiguous: (String message) => feedback = message,
      );
      if (doc == null) return feedback;
      documentIds.add(doc.id);
    }
  } else {
    documentIds = _documents(ref).selection.toList();
  }
  final List<DocumentItem> all = _documents(ref).documents;
  documentIds = documentIds
      .where((String id) => all.any((DocumentItem d) => d.id == id && d.isPdf))
      .toList();
  if (documentIds.length < 2) {
    return 'Merging needs at least 2 PDF files. Say it again with the file names, '
        'for example "merge file a and file b".';
  }
  final String? name = await _promptText(
    'Merge ${documentIds.length} documents',
    hint: 'Merged file name',
    initial: params['new_name']?.toString(),
  );
  if (name == null || name.isEmpty) {
    return 'Merge cancelled.';
  }
  notifier.setSelection(documentIds);
  ref.read(shellTabProvider.notifier).setTab(1);
  final String newName = await notifier.mergeSelected(name);
  return 'Created the merged file "$newName".';
}

Future<String> _splitDocument(Ref ref, Map<String, dynamic> params) async {
  late String feedback;
  final DocumentItem? doc = await _resolveDocument(
    ref,
    params['name_query']?.toString() ?? '',
    onAmbiguous: (String message) => feedback = message,
  );
  if (doc == null) return feedback;
  if (!doc.isPdf) {
    return 'Only PDF files can be split.';
  }
  final String? ranges = await _promptText(
    'Split pages of "${doc.name}"',
    hint: 'e.g. 1-3,5',
    initial: params['ranges']?.toString(),
  );
  if (ranges == null || ranges.isEmpty) {
    return 'Split cancelled.';
  }
  final List<String> parts = await ref
      .read(documentsControllerProvider.notifier)
      .splitDocument(doc.id, ranges: ranges);
  ref.read(shellTabProvider.notifier).setTab(1);
  return 'Created ${parts.length} files: ${parts.join(', ')}.';
}

Future<String?> _promptText(
  String title, {
  required String hint,
  String? initial,
}) async {
  final BuildContext? context = rootNavigatorKey.currentContext;
  if (context == null || !context.mounted) return null;
  final TextEditingController controller = TextEditingController(
    text: initial ?? '',
  );
  final String? result = await showDialog<String>(
    context: context,
    builder: (BuildContext ctx) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: controller,
        autofocus: true,
        decoration: InputDecoration(hintText: hint),
        onSubmitted: (String value) => Navigator.of(ctx).pop(value),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(ctx).pop(controller.text),
          child: const Text('Done'),
        ),
      ],
    ),
  );
  return result?.trim();
}
