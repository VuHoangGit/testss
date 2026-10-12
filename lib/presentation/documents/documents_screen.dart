/// Tab Tài liệu (Sprint 2): thư mục, upload, danh sách, tải xuống và
/// công cụ PDF (gộp/tách/mật khẩu).
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/document_entities.dart';
import 'documents_controller.dart';
import 'documents_providers.dart';

class DocumentsScreen extends ConsumerStatefulWidget {
  const DocumentsScreen({super.key});

  @override
  ConsumerState<DocumentsScreen> createState() => _DocumentsScreenState();
}

class _DocumentsScreenState extends ConsumerState<DocumentsScreen> {
  void _showSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  /// Chạy thao tác kèm bắt lỗi → SnackBar; [done] hiện khi thành công.
  Future<void> _guard(Future<void> Function() action, {String? done}) async {
    try {
      await action();
      if (done != null) _showSnack(done);
    } on Exception catch (e) {
      _showSnack(e.toString());
    }
  }

  Future<String?> _promptText(String title, {String hint = '', bool obscure = false}) async {
    final TextEditingController controller = TextEditingController();
    final String? result = await showDialog<String>(
      context: context,
      builder: (BuildContext ctx) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: controller,
          autofocus: true,
          obscureText: obscure,
          decoration: InputDecoration(hintText: hint),
          onSubmitted: (String v) => Navigator.of(ctx).pop(v),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(controller.text),
            child: const Text('Xong'),
          ),
        ],
      ),
    );
    final String trimmed = result?.trim() ?? '';
    return trimmed.isEmpty ? null : trimmed;
  }

  Future<bool> _confirm(String title, String message, {String confirmLabel = 'Xóa'}) async {
    final bool? ok = await showDialog<bool>(
      context: context,
      builder: (BuildContext ctx) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(confirmLabel),
          ),
        ],
      ),
    );
    return ok == true;
  }

  Future<void> _upload() async {
    final String? folderId =
        ref.read(documentsControllerProvider).value?.selectedFolderId;
    final ValueNotifier<double> progress = ValueNotifier<double>(0);
    bool dialogClosed = false;
    void closeDialog() {
      if (!dialogClosed && mounted) {
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
          title: const Text('Đang tải lên…'),
          content: ValueListenableBuilder<double>(
            valueListenable: progress,
            builder: (_, double v, _) => Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                LinearProgressIndicator(value: v <= 0 ? null : v),
                const SizedBox(height: 8),
                Text(v <= 0 ? 'Đang chuẩn bị…' : '${(v * 100).toStringAsFixed(0)}%'),
              ],
            ),
          ),
        ),
      ),
    );
    final DocumentsController notifier = ref.read(documentsControllerProvider.notifier);
    try {
      final String? name = await notifier.pickAndUpload(
        folderId: folderId,
        onProgress: (int sent, int total) {
          if (total > 0) progress.value = sent / total;
        },
      );
      if (name != null) _showSnack('Đã tải lên "$name"');
    } on Exception catch (e) {
      _showSnack(e.toString());
    } finally {
      closeDialog();
    }
  }

  Future<void> _download(DocumentItem doc) async {
    await _guard(
      () async {
        final String? saved =
            await ref.read(documentsControllerProvider.notifier).downloadDocument(doc);
        if (saved != null) _showSnack('Đã lưu "${doc.name}"');
      },
    );
  }

  Future<void> _deleteDocument(DocumentItem doc) async {
    final bool ok = await _confirm(
      'Xóa tài liệu?',
      '"${doc.name}" sẽ bị xóa vĩnh viễn. Thao tác không thể hoàn tác.',
    );
    if (!ok) return;
    await _guard(
      () => ref.read(documentsControllerProvider.notifier).deleteDocument(doc.id),
      done: 'Đã xóa "${doc.name}"',
    );
  }

  Future<void> _mergeSelected() async {
    final DocumentsState data = ref.read(documentsControllerProvider).value!;
    if (data.selection.length < 2) {
      _showSnack('Chọn ít nhất 2 file PDF để gộp');
      return;
    }
    final String? name = await _promptText('Tên file gộp', hint: 'VD: Hop dong 2026');
    if (name == null) return;
    await _guard(
      () async {
        final String newName =
            await ref.read(documentsControllerProvider.notifier).mergeSelected(name);
        _showSnack('Đã tạo "$newName"');
      },
    );
  }

  Future<void> _split(DocumentItem doc) async {
    if (!doc.isPdf) {
      _showSnack('Chỉ hỗ trợ tách file PDF');
      return;
    }
    final String? ranges =
        await _promptText('Tách trang', hint: 'VD: 1-3,5 (phân tách bởi dấu phẩy)');
    if (ranges == null) return;
    await _guard(
      () async {
        final List<String> names = await ref
            .read(documentsControllerProvider.notifier)
            .splitDocument(doc.id, ranges: ranges);
        _showSnack('Đã tạo ${names.length} file: ${names.join(', ')}');
      },
    );
  }

  Future<void> _protect(DocumentItem doc, {required bool removing}) async {
    if (!doc.isPdf) {
      _showSnack('Chỉ hỗ trợ file PDF');
      return;
    }
    final String? password = await _promptText(
      removing ? 'Gỡ mật khẩu' : 'Đặt mật khẩu',
      hint: removing ? 'Mật khẩu hiện tại' : 'Mật khẩu mới',
      obscure: true,
    );
    if (password == null) return;
    await _guard(
      () async {
        final DocumentsController notifier = ref.read(documentsControllerProvider.notifier);
        final String newName = removing
            ? await notifier.unprotectDocument(doc.id, password: password)
            : await notifier.protectDocument(doc.id, password: password);
        _showSnack('Đã tạo "$newName"');
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final AsyncValue<DocumentsState> async = ref.watch(documentsControllerProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (Object e, StackTrace _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text('Không tải được tài liệu: $e', textAlign: TextAlign.center),
            ),
            FilledButton(
              onPressed: () => ref.invalidate(documentsControllerProvider),
              child: const Text('Thử lại'),
            ),
          ],
        ),
      ),
      data: (DocumentsState data) {
        return Column(
          children: <Widget>[
            _buildToolbar(context, data),
            _buildFolderChips(context, data),
            const Divider(height: 1),
            Expanded(child: _buildList(context, data)),
          ],
        );
      },
    );
  }

  Widget _buildToolbar(BuildContext context, DocumentsState data) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: <Widget>[
          FilledButton.icon(
            onPressed: _upload,
            icon: const Icon(Icons.upload_file),
            label: const Text('Tải lên'),
          ),
          OutlinedButton.icon(
            onPressed: () async {
              final String? name = await _promptText('Thư mục mới', hint: 'Tên thư mục');
              if (name != null) {
                await _guard(
                  () => ref.read(documentsControllerProvider.notifier).createFolder(name),
                  done: 'Đã tạo thư mục "$name"',
                );
              }
            },
            icon: const Icon(Icons.create_new_folder_outlined),
            label: const Text('Thư mục mới'),
          ),
          if (data.selectionMode) ...<Widget>[
            OutlinedButton.icon(
              onPressed: data.selection.length >= 2 ? _mergeSelected : null,
              icon: const Icon(Icons.merge),
              label: Text('Gộp (${data.selection.length})'),
            ),
            TextButton(
              onPressed: () =>
                  ref.read(documentsControllerProvider.notifier).cancelSelection(),
              child: const Text('Hủy chọn'),
            ),
          ] else
            OutlinedButton.icon(
              onPressed: () =>
                  ref.read(documentsControllerProvider.notifier).enterSelectionMode(),
              icon: const Icon(Icons.checklist),
              label: const Text('Chọn để gộp'),
            ),
        ],
      ),
    );
  }

  Widget _buildFolderChips(BuildContext context, DocumentsState data) {
    final DocumentsController notifier = ref.read(documentsControllerProvider.notifier);
    final List<Widget> chips = <Widget>[
      Padding(
        padding: const EdgeInsets.only(left: 12),
        child: ChoiceChip(
          label: const Text('Tất cả'),
          selected: data.selectedFolderId == null,
          onSelected: (_) => _guard(() => notifier.selectFolder(null)),
        ),
      ),
      for (final DocumentFolder folder in data.folders)
        Padding(
          padding: const EdgeInsets.only(left: 8),
          child: InputChip(
            label: Text('${folder.name} (${folder.documentCount})'),
            selected: data.selectedFolderId == folder.id,
            onSelected: (_) => _guard(() => notifier.selectFolder(folder.id)),
            onDeleted: () async {
              final bool ok = await _confirm(
                'Xóa thư mục?',
                'Thư mục "${folder.name}" chỉ xóa được khi trống. Tiếp tục?',
              );
              if (ok) {
                await _guard(
                  () => notifier.deleteFolder(folder.id),
                  done: 'Đã xóa thư mục "${folder.name}"',
                );
              }
            },
          ),
        ),
    ];
    return SizedBox(
      height: 48,
      child: ListView(scrollDirection: Axis.horizontal, children: chips),
    );
  }

  Widget _buildList(BuildContext context, DocumentsState data) {
    if (data.documents.isEmpty) {
      return const Center(
        child: Text('Chưa có tài liệu — bấm "Tải lên" để thêm file đầu tiên'),
      );
    }
    final DocumentsController notifier = ref.read(documentsControllerProvider.notifier);
    return RefreshIndicator(
      onRefresh: () => notifier.selectFolder(data.selectedFolderId),
      child: ListView.separated(
        itemCount: data.documents.length,
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (BuildContext ctx, int index) {
          final DocumentItem doc = data.documents[index];
          return _DocumentTile(
            doc: doc,
            selectionMode: data.selectionMode,
            selected: data.selection.contains(doc.id),
            onToggleSelect: () => notifier.toggleSelect(doc.id),
            onDownload: () => _download(doc),
            onSplit: () => _split(doc),
            onProtect: () => _protect(doc, removing: false),
            onUnprotect: () => _protect(doc, removing: true),
            onDelete: () => _deleteDocument(doc),
          );
        },
      ),
    );
  }
}

class _DocumentTile extends StatelessWidget {
  const _DocumentTile({
    required this.doc,
    required this.selectionMode,
    required this.selected,
    required this.onToggleSelect,
    required this.onDownload,
    required this.onSplit,
    required this.onProtect,
    required this.onUnprotect,
    required this.onDelete,
  });

  final DocumentItem doc;
  final bool selectionMode;
  final bool selected;
  final VoidCallback onToggleSelect;
  final VoidCallback onDownload;
  final VoidCallback onSplit;
  final VoidCallback onProtect;
  final VoidCallback onUnprotect;
  final VoidCallback onDelete;

  IconData get _icon {
    if (doc.isPdf) return Icons.picture_as_pdf;
    if (doc.mimeType.startsWith('image/')) return Icons.image_outlined;
    return Icons.description_outlined;
  }

  String get _meta {
    final double mb = doc.sizeBytes / (1024 * 1024);
    final String size =
        mb >= 1 ? '${mb.toStringAsFixed(1)} MB' : '${(doc.sizeBytes / 1024).toStringAsFixed(0)} KB';
    return doc.pageCount != null ? '${doc.pageCount} trang · $size' : size;
  }

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(_icon, color: Theme.of(context).colorScheme.primary),
      title: Text(doc.name, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(_meta),
      trailing: selectionMode
          ? Checkbox(value: selected, onChanged: (bool? _) => onToggleSelect())
          : PopupMenuButton<String>(
              onSelected: (String action) {
                switch (action) {
                  case 'download':
                    onDownload();
                  case 'split':
                    onSplit();
                  case 'protect':
                    onProtect();
                  case 'unprotect':
                    onUnprotect();
                  case 'delete':
                    onDelete();
                }
              },
              itemBuilder: (BuildContext ctx) => const <PopupMenuEntry<String>>[
                PopupMenuItem<String>(value: 'download', child: Text('Tải xuống')),
                PopupMenuItem<String>(value: 'split', child: Text('Tách trang…')),
                PopupMenuItem<String>(value: 'protect', child: Text('Đặt mật khẩu…')),
                PopupMenuItem<String>(value: 'unprotect', child: Text('Gỡ mật khẩu…')),
                PopupMenuDivider(),
                PopupMenuItem<String>(value: 'delete', child: Text('Xóa')),
              ],
            ),
      onTap: selectionMode ? onToggleSelect : null,
    );
  }
}
