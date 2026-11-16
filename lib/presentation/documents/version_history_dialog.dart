/// Dialog "Version history" của một tài liệu: xem các bản cũ, upload bản mới,
/// khôi phục, xóa bản cũ và so sánh 2 bản (diff + tóm tắt AI).
///
/// Gọi trực tiếp [DocumentsRepository] (không qua controller) vì đây là thao
/// tác theo tài liệu đơn lẻ; dialog trả true khi có thay đổi để bên gọi reload.
library;

import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/document_entities.dart';
import 'documents_providers.dart';

/// Mở dialog lịch sử phiên bản cho [document].
///
/// Trả true nếu có thay đổi (upload/restore/xóa) — bên gọi nên reload danh sách.
Future<bool> showVersionHistoryDialog(
  WidgetRef ref,
  BuildContext context,
  DocumentItem document,
) {
  return showDialog<bool>(
    context: context,
    builder: (BuildContext ctx) => _VersionHistoryDialog(document: document),
  ).then((bool? changed) => changed ?? false);
}

class _VersionHistoryDialog extends ConsumerStatefulWidget {
  const _VersionHistoryDialog({required this.document});

  final DocumentItem document;

  @override
  ConsumerState<_VersionHistoryDialog> createState() =>
      _VersionHistoryDialogState();
}

class _VersionHistoryDialogState extends ConsumerState<_VersionHistoryDialog> {
  bool _busy = false;
  bool _changed = false;
  List<DocumentVersionItem> _versions = <DocumentVersionItem>[];
  String? _error;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      _versions = await ref
          .read(documentsRepositoryProvider)
          .listVersions(widget.document.id);
    } on Exception catch (error) {
      _error = error.toString();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Chạy thao tác đổi dữ liệu: bắt lỗi → SnackBar, luôn đánh dấu _changed.
  Future<void> _mutate(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
      _changed = true;
    } on Exception catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text('$error')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
      await _reload();
    }
  }

  Future<void> _uploadNewVersion() async {
    final List<String> extensions = _allowedExtensionsFor(widget.document);
    // file_picker 13: API static; trả về danh sách rỗng nếu người dùng hủy.
    final List<PlatformFile> picked = await FilePicker.pickFiles(
      // FileType.custom với danh sách rỗng sẽ lỗi — loại lạ thì mở mọi file.
      type: extensions.isEmpty ? FileType.any : FileType.custom,
      allowedExtensions: extensions.isEmpty ? null : extensions,
    );
    if (picked.isEmpty) return; // người dùng huỷ
    final PlatformFile file = picked.first;
    final Uint8List bytes = await file.readAsBytes();

    final String? label = await _promptLabel();
    if (!mounted || label == null) return;

    await _mutate(
      () => ref
          .read(documentsRepositoryProvider)
          .uploadNewVersion(
            documentId: widget.document.id,
            fileName: file.name,
            bytes: bytes,
            label: label.trim(),
          ),
    );
  }

  /// Chỉ cho chọn file cùng loại với tài liệu (backend chặn khác MIME).
  List<String> _allowedExtensionsFor(DocumentItem doc) {
    if (doc.isPdf) return <String>['pdf'];
    if (doc.isImage) return <String>['jpg', 'jpeg', 'png', 'gif'];
    if (doc.isWordDoc) return <String>['docx'];
    if (doc.isTextFile) return <String>['txt', 'md'];
    return const <String>[];
  }

  Future<String?> _promptLabel() {
    final TextEditingController controller = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (BuildContext ctx) => AlertDialog(
        title: const Text('Version note (optional)'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: 'e.g. after the client edited clause 4',
          ),
          onSubmitted: (String value) => Navigator.of(ctx).pop(value),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(''),
            child: const Text('Skip note'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(controller.text),
            child: const Text('Upload'),
          ),
        ],
      ),
    );
  }

  Future<void> _restore(DocumentVersionItem version) async {
    final bool? ok = await showDialog<bool>(
      context: context,
      builder: (BuildContext ctx) => AlertDialog(
        title: Text('Restore version ${version.versionNumber}?'),
        content: Text(
          'The current file is kept in the history. The document will show '
          'the content of version ${version.versionNumber}.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Restore'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await _mutate(
      () => ref
          .read(documentsRepositoryProvider)
          .restoreVersion(
            documentId: widget.document.id,
            versionId: version.id,
          ),
    );
  }

  Future<void> _delete(DocumentVersionItem version) async {
    final bool? ok = await showDialog<bool>(
      context: context,
      builder: (BuildContext ctx) => AlertDialog(
        title: Text('Delete version ${version.versionNumber}?'),
        content: const Text(
          'This removes the old file from the history for good. '
          'This cannot be undone.',
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
    if (ok != true) return;
    await _mutate(
      () => ref
          .read(documentsRepositoryProvider)
          .deleteVersion(
            documentId: widget.document.id,
            versionId: version.id,
          ),
    );
  }

  /// So sánh bản cũ với bản hiện tại: hiện diff + tóm tắt AI trong dialog con.
  Future<void> _diff(DocumentVersionItem version) async {
    setState(() => _busy = true);
    VersionDiffResult? result;
    String? error;
    try {
      result = await ref
          .read(documentsRepositoryProvider)
          .diffVersions(
            documentId: widget.document.id,
            oldVersionId: version.id,
          );
    } on Exception catch (e) {
      error = e.toString();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
    if (!mounted || result == null) {
      if (error != null && mounted) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(error)));
      }
      return;
    }
    final VersionDiffResult diffResult = result;
    await showDialog<void>(
      context: context,
      builder: (BuildContext ctx) => _VersionDiffDialog(
        versionNumber: version.versionNumber,
        result: diffResult,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Version history — ${widget.document.name}'),
      content: SizedBox(
        width: 560,
        height: 420,
        child: _buildBody(context),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(_changed),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_busy && _versions.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(child: Text(_error!));
    }
    if (_versions.isEmpty) {
      return _EmptyVersions(
        onUpload: _busy ? null : _uploadNewVersion,
      );
    }
    return _VersionList(
      versions: _versions,
      busy: _busy,
      onUpload: _uploadNewVersion,
      onRestore: _restore,
      onDelete: _delete,
      onDiff: _diff,
    );
  }
}

/// Trạng thái chưa có bản cũ nào.
class _EmptyVersions extends StatelessWidget {
  const _EmptyVersions({required this.onUpload});

  final VoidCallback? onUpload;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            Icons.history_rounded,
            size: 44,
            color: Theme.of(context).colorScheme.outline,
          ),
          const SizedBox(height: 12),
          Text('No old versions yet', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 4),
          Text(
            'Upload a newer file to keep the current one in the history.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: onUpload,
            icon: const Icon(Icons.upload_file),
            label: const Text('Upload new version'),
          ),
        ],
      ),
    );
  }
}

/// Danh sách phiên bản + nút hành động từng bản.
class _VersionList extends StatelessWidget {
  const _VersionList({
    required this.versions,
    required this.busy,
    required this.onUpload,
    required this.onRestore,
    required this.onDelete,
    required this.onDiff,
  });

  final List<DocumentVersionItem> versions;
  final bool busy;
  final VoidCallback onUpload;
  final ValueChanged<DocumentVersionItem> onRestore;
  final ValueChanged<DocumentVersionItem> onDelete;
  final ValueChanged<DocumentVersionItem> onDiff;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                '${versions.length} old version(s) — newest first',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            FilledButton.tonalIcon(
              onPressed: busy ? null : onUpload,
              icon: const Icon(Icons.upload_file, size: 18),
              label: const Text('Upload new version'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Expanded(
          child: ListView.separated(
            itemCount: versions.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (BuildContext ctx, int index) {
              final DocumentVersionItem version = versions[index];
              final String meta =
                  '${_formatBytes(version.sizeBytes)} · ${_formatDate(version.uploadedAt)}';
              return ListTile(
                leading: SizedBox(
                  width: 34,
                  child: Text(
                    'v${version.versionNumber}',
                    style: Theme.of(ctx).textTheme.titleMedium,
                  ),
                ),
                title: version.label.isEmpty
                    ? Text(meta, style: Theme.of(ctx).textTheme.bodySmall)
                    : Text(version.label, maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                subtitle: version.label.isEmpty
                    ? null
                    : Text(meta, style: Theme.of(ctx).textTheme.bodySmall),
                trailing: busy
                    ? null
                    : Row(
                        mainAxisSize: MainAxisSize.min,
                        children: <Widget>[
                          IconButton(
                            tooltip: 'Compare with current',
                            onPressed: () => onDiff(version),
                            icon: const Icon(Icons.compare_arrows_rounded),
                          ),
                          IconButton(
                            tooltip: 'Restore this version',
                            onPressed: () => onRestore(version),
                            icon: const Icon(
                              Icons.settings_backup_restore_rounded,
                            ),
                          ),
                          IconButton(
                            tooltip: 'Delete this old version',
                            onPressed: () => onDelete(version),
                            icon: const Icon(Icons.delete_outline),
                          ),
                        ],
                      ),
              );
            },
          ),
        ),
      ],
    );
  }
}

/// Dialog con hiển thị kết quả so sánh: thống kê + tóm tắt AI + diff từng dòng.
class _VersionDiffDialog extends StatelessWidget {
  const _VersionDiffDialog({
    required this.versionNumber,
    required this.result,
  });

  final int versionNumber;
  final VersionDiffResult result;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return AlertDialog(
      title: Text('Compare — v$versionNumber vs current'),
      content: SizedBox(
        width: 640,
        height: 460,
        child: result.diffLines.isEmpty
            ? Center(
                child: Text(
                  'The two versions have the same text content.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    '+${result.addedCount} added · −${result.removedCount} removed',
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                      color: colors.primary,
                    ),
                  ),
                  if (result.aiSummary != null) ...<Widget>[
                    const SizedBox(height: 12),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: colors.primaryContainer.withValues(alpha: 0.4),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: SelectableText(
                        result.aiSummary!,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  const Divider(height: 1),
                  const SizedBox(height: 8),
                  Expanded(
                    child: ListView.builder(
                      itemCount: result.diffLines.length,
                      itemBuilder: (BuildContext ctx, int index) {
                        final String line = result.diffLines[index];
                        final bool added = line.startsWith('+');
                        final bool removed = line.startsWith('-');
                        final Color? background = added
                            ? Colors.green.withValues(alpha: 0.12)
                            : removed
                                ? Colors.red.withValues(alpha: 0.12)
                                : null;
                        return Container(
                          color: background,
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 1,
                          ),
                          child: Text(
                            line,
                            style: const TextStyle(
                              fontFamily: 'monospace',
                              fontSize: 12,
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                ],
              ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }
}

String _formatBytes(int bytes) {
  if (bytes <= 0) return '0 B';
  const List<String> units = <String>['B', 'KB', 'MB', 'GB'];
  int value = bytes;
  int unit = 0;
  while (value > 1024 && unit < units.length - 1) {
    value = (value / 1024).round();
    unit += 1;
  }
  return '$value ${units[unit]}';
}

String _twoDigits(int value) => value.toString().padLeft(2, '0');

String _formatDate(DateTime dt) =>
    '${dt.year.toString().padLeft(4, '0')}-'
    '${_twoDigits(dt.month)}-${_twoDigits(dt.day)} '
    '${_twoDigits(dt.hour)}:${_twoDigits(dt.minute)}';
