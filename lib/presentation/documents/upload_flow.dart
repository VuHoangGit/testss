/// Luồng upload dùng chung: mở file picker → dialog tiến độ → SnackBar kết quả.
///
/// Dashboard (Upload document / Quick actions) và Files tab cùng gọi một flow
/// để hành vi nhất quán — không copy-paste dialog tiến độ.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'documents_controller.dart';
import 'documents_providers.dart';

/// [folderId] null = thư mục đang chọn trong Files (dashboard truyền null
/// để upload vào kho chung).
Future<void> pickAndUploadWithProgress(
  BuildContext context,
  WidgetRef ref, {
  String? folderId,
}) async {
  final String? targetFolder =
      folderId ?? ref.read(documentsControllerProvider).value?.selectedFolderId;
  final ValueNotifier<double> progress = ValueNotifier<double>(0);
  bool dialogClosed = false;
  void closeDialog() {
    if (!dialogClosed && context.mounted) {
      dialogClosed = true;
      Navigator.of(context, rootNavigator: true).pop();
    }
  }

  showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (BuildContext ctx) => PopScope<void>(
      canPop: false,
      child: AlertDialog(
        title: const Text('Uploading…'),
        content: ValueListenableBuilder<double>(
          valueListenable: progress,
          builder: (_, double v, _) => Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              LinearProgressIndicator(value: v <= 0 ? null : v),
              const SizedBox(height: 8),
              Text(v <= 0 ? 'Preparing…' : '${(v * 100).toStringAsFixed(0)}%'),
            ],
          ),
        ),
      ),
    ),
  );
  final DocumentsController notifier = ref.read(
    documentsControllerProvider.notifier,
  );
  try {
    final String? name = await notifier.pickAndUpload(
      folderId: targetFolder,
      onProgress: (int sent, int total) {
        if (total > 0) progress.value = sent / total;
      },
    );
    if (name != null && context.mounted) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text('Uploaded "$name"')));
    }
  } on Exception catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(e.toString())));
    }
  } finally {
    closeDialog();
  }
}
