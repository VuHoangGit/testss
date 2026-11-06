/// Files tab: folders, uploads, downloads, and PDF tools.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/files/file_saver.dart';
import '../../domain/entities/document_entities.dart';
import '../ai/ai_providers.dart';
import 'documents_controller.dart';
import 'documents_providers.dart';
import 'upload_flow.dart';
import 'viewer_opener.dart';

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

  Future<String?> _promptText(
    String title, {
    String hint = '',
    bool obscure = false,
  }) async {
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
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(controller.text),
            child: const Text('Done'),
          ),
        ],
      ),
    );
    final String trimmed = result?.trim() ?? '';
    return trimmed.isEmpty ? null : trimmed;
  }

  Future<bool> _confirm(
    String title,
    String message, {
    String confirmLabel = 'Delete',
    bool destructive = true,
  }) async {
    final bool? ok = await showDialog<bool>(
      context: context,
      builder: (BuildContext ctx) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: destructive
                  ? Theme.of(ctx).colorScheme.error
                  : null,
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
    await pickAndUploadWithProgress(context, ref);
  }

  Future<void> _download(DocumentItem doc) async {
    await _guard(() async {
      final String? saved = await ref
          .read(documentsControllerProvider.notifier)
          .downloadDocument(doc);
      if (saved != null) _showSnack('Saved "${doc.name}"');
    });
  }

  Future<void> _openViewer(DocumentItem doc) async {
    // Đánh dấu đã mở (feed Recent) — không chặn việc mở viewer nếu lỗi
    unawaited(
      ref.read(documentsControllerProvider.notifier).markOpened(doc.id),
    );
    await _guard(
      () => openDocumentViewer(
        repository: ref.read(documentsRepositoryProvider),
        aiRepository: ref.read(aiRepositoryProvider),
        doc: doc,
      ),
    );
  }

  /// Xuất tài liệu sang Word (.docx): OCR nội dung rồi lưu file giữ cấu trúc.
  ///
  /// Đây là thao tác AI (tốn 50 credit, có thể lâu với tài liệu scan) nên hỏi
  /// trước; trong lúc chờ hiện dialog tiến trình để người dùng biết app không
  /// treo.
  Future<void> _exportWord(DocumentItem doc) async {
    if (!(doc.isPdf || doc.isImage)) {
      _showSnack('Only PDF and image files can be exported to Word');
      return;
    }
    final bool ok = await _confirm(
      'Export to Word?',
      'AI reads "${doc.name}" and saves it as a .docx file that keeps headings, '
          'tables and lists.\n\nThis uses 50 credits. Scanned pages take about '
          '15 seconds each.',
      confirmLabel: 'Export',
      destructive: false,
    );
    if (!ok || !mounted) return;

    final NavigatorState navigator = Navigator.of(context, rootNavigator: true);
    unawaited(
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (BuildContext ctx) => PopScope(
          canPop: false,
          child: AlertDialog(
            content: Row(
              children: <Widget>[
                const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2.5),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    'Reading "${doc.name}"…\nLarge or scanned files can take a '
                    'few minutes.',
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    try {
      final Uint8List bytes = await ref
          .read(aiRepositoryProvider)
          .ocrWord(doc.id);
      final String fileName = '${_fileStem(doc.name)}.docx';
      final String? saved = await const FileSaver().saveBytes(
        fileName: fileName,
        bytes: bytes,
        mimeType:
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      );
      if (saved != null) _showSnack('Exported "$fileName"');
    } on Exception catch (e) {
      _showSnack(e.toString());
    } finally {
      if (mounted) navigator.pop();
    }
  }

  /// "Báo cáo.pdf" → "Báo cáo" (bỏ đuôi file, giữ phần còn lại nguyên vẹn).
  String _fileStem(String name) {
    final int dot = name.lastIndexOf('.');
    return dot > 0 ? name.substring(0, dot) : name;
  }

  Future<void> _toggleFavorite(DocumentItem doc) async {
    await _guard(
      () =>
          ref.read(documentsControllerProvider.notifier).toggleFavorite(doc.id),
    );
  }

  Future<void> _deleteDocument(DocumentItem doc) async {
    final bool ok = await _confirm(
      'Delete document?',
      '"${doc.name}" will be permanently deleted. This cannot be undone.',
    );
    if (!ok) return;
    await _guard(
      () =>
          ref.read(documentsControllerProvider.notifier).deleteDocument(doc.id),
      done: 'Deleted "${doc.name}"',
    );
  }

  Future<void> _mergeSelected() async {
    final DocumentsState data = ref.read(documentsControllerProvider).value!;
    if (data.selection.length < 2) {
      _showSnack('Select at least 2 PDF files to merge');
      return;
    }
    final String? name = await _promptText(
      'Merged file name',
      hint: 'e.g. Contract 2026',
    );
    if (name == null) return;
    await _guard(() async {
      final String newName = await ref
          .read(documentsControllerProvider.notifier)
          .mergeSelected(name);
      _showSnack('Created "$newName"');
    });
  }

  Future<void> _split(DocumentItem doc) async {
    if (!doc.isPdf) {
      _showSnack('Only PDF files can be split');
      return;
    }
    final String? ranges = await _promptText(
      'Split pages',
      hint: 'e.g. 1-3,5 (separate with commas)',
    );
    if (ranges == null) return;
    await _guard(() async {
      final List<String> names = await ref
          .read(documentsControllerProvider.notifier)
          .splitDocument(doc.id, ranges: ranges);
      _showSnack('Created ${names.length} files: ${names.join(', ')}');
    });
  }

  Future<void> _protect(DocumentItem doc, {required bool removing}) async {
    if (!doc.isPdf) {
      _showSnack('Only PDF files are supported');
      return;
    }
    final String? password = await _promptText(
      removing ? 'Remove password' : 'Set password',
      hint: removing ? 'Current password' : 'New password',
      obscure: true,
    );
    if (password == null) return;
    await _guard(() async {
      final DocumentsController notifier = ref.read(
        documentsControllerProvider.notifier,
      );
      final String newName = removing
          ? await notifier.unprotectDocument(doc.id, password: password)
          : await notifier.protectDocument(doc.id, password: password);
      _showSnack('Created "$newName"');
    });
  }

  @override
  Widget build(BuildContext context) {
    final AsyncValue<DocumentsState> async = ref.watch(
      documentsControllerProvider,
    );
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (Object e, StackTrace _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                'Unable to load documents: $e',
                textAlign: TextAlign.center,
              ),
            ),
            FilledButton(
              onPressed: () => ref.invalidate(documentsControllerProvider),
              child: const Text('Try again'),
            ),
          ],
        ),
      ),
      data: (DocumentsState data) {
        return Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(28, 26, 28, 4),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          'My Files',
                          style: Theme.of(context).textTheme.headlineSmall
                              ?.copyWith(fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Manage, organize and secure your documents.',
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.outline,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    '${data.documents.length} files',
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.outline,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
            _buildToolbar(context, data),
            _buildFolderChips(context, data),
            Expanded(child: _buildList(context, data)),
          ],
        );
      },
    );
  }

  Widget _buildToolbar(BuildContext context, DocumentsState data) {
    final DocumentsController notifier = ref.read(
      documentsControllerProvider.notifier,
    );
    final bool filtered = data.viewFilter != DocumentsViewFilter.all;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 8),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: <Widget>[
          if (filtered)
            InputChip(
              avatar: Icon(
                data.viewFilter == DocumentsViewFilter.favorites
                    ? Icons.star_rounded
                    : Icons.schedule_rounded,
                size: 16,
                color: Theme.of(context).colorScheme.primary,
              ),
              label: Text(
                data.viewFilter == DocumentsViewFilter.favorites
                    ? 'Favorites'
                    : 'Recent',
              ),
              onDeleted: () =>
                  _guard(() => notifier.setViewFilter(DocumentsViewFilter.all)),
            ),
          FilledButton.icon(
            onPressed: _upload,
            icon: const Icon(Icons.upload_file),
            label: const Text('Upload'),
          ),
          OutlinedButton.icon(
            onPressed: () async {
              final String? name = await _promptText(
                'New folder',
                hint: 'Folder name',
              );
              if (name != null) {
                await _guard(
                  () => ref
                      .read(documentsControllerProvider.notifier)
                      .createFolder(name),
                  done: 'Created folder "$name"',
                );
              }
            },
            icon: const Icon(Icons.create_new_folder_outlined),
            label: const Text('New folder'),
          ),
          if (data.selectionMode) ...<Widget>[
            OutlinedButton.icon(
              onPressed: data.selection.length >= 2 ? _mergeSelected : null,
              icon: const Icon(Icons.merge),
              label: Text('Merge (${data.selection.length})'),
            ),
            TextButton(
              onPressed: () => ref
                  .read(documentsControllerProvider.notifier)
                  .cancelSelection(),
              child: const Text('Cancel selection'),
            ),
          ] else
            OutlinedButton.icon(
              onPressed: () => ref
                  .read(documentsControllerProvider.notifier)
                  .enterSelectionMode(),
              icon: const Icon(Icons.checklist),
              label: const Text('Select to merge'),
            ),
          // Xuất PDF/ảnh sang Word ngay tại chỗ dựng file, cạnh "Select to merge".
          OutlinedButton.icon(
            onPressed: () => _exportWordFromToolbar(data),
            icon: const Icon(Icons.description_outlined),
            label: const Text('Export to Word'),
          ),
        ],
      ),
    );
  }

  /// Nút toolbar: chọn tài liệu PDF/ảnh rồi xuất Word (kèm tải file về máy).
  ///
  /// Đang ở chế độ chọn và chọn đúng 1 file hợp lệ → xuất luôn file đó; còn
  /// lại mở hộp chọn để không phải đoán người dùng muốn file nào.
  Future<void> _exportWordFromToolbar(DocumentsState data) async {
    final List<DocumentItem> eligible = <DocumentItem>[
      for (final DocumentItem doc in data.documents)
        if (doc.isPdf || doc.isImage) doc,
    ];
    if (eligible.isEmpty) {
      _showSnack('No PDF or image files to export');
      return;
    }
    final List<DocumentItem> selected = <DocumentItem>[
      for (final DocumentItem doc in eligible)
        if (data.selection.contains(doc.id)) doc,
    ];
    final DocumentItem? target = selected.length == 1
        ? selected.single
        : await _pickDocumentForWord(eligible);
    if (target == null) return;
    await _exportWord(target);
  }

  Future<DocumentItem?> _pickDocumentForWord(List<DocumentItem> documents) {
    return showDialog<DocumentItem>(
      context: context,
      builder: (BuildContext ctx) => SimpleDialog(
        title: const Text('Export to Word'),
        children: <Widget>[
          SizedBox(
            width: 440,
            height: 340,
            child: ListView.builder(
              itemCount: documents.length,
              itemBuilder: (BuildContext _, int index) {
                final DocumentItem doc = documents[index];
                return ListTile(
                  leading: Icon(
                    doc.isPdf
                        ? Icons.picture_as_pdf_outlined
                        : Icons.image_outlined,
                  ),
                  title: Text(
                    doc.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  subtitle: Text(doc.isPdf ? 'PDF' : 'Image'),
                  onTap: () => Navigator.of(ctx).pop(doc),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFolderChips(BuildContext context, DocumentsState data) {
    final DocumentsController notifier = ref.read(
      documentsControllerProvider.notifier,
    );

    Future<void> deleteFolder(DocumentFolder folder) async {
      final bool ok = await _confirm(
        'Delete folder?',
        'Folder "${folder.name}" can only be deleted when empty. Continue?',
      );
      if (ok) {
        await _guard(
          () => notifier.deleteFolder(folder.id),
          done: 'Deleted folder "${folder.name}"',
        );
      }
    }

    final List<Widget> cards = <Widget>[
      _FolderCard(
        name: 'All',
        count: data.documents.length,
        selected: data.selectedFolderId == null,
        onTap: () => _guard(() => notifier.selectFolder(null)),
      ),
      for (final DocumentFolder folder in data.folders)
        _FolderCard(
          name: folder.name,
          count: folder.documentCount,
          selected: data.selectedFolderId == folder.id,
          onTap: () => _guard(() => notifier.selectFolder(folder.id)),
          onDelete: () => deleteFolder(folder),
        ),
    ];
    return SizedBox(
      height: 84,
      child: ListView.separated(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 6),
        scrollDirection: Axis.horizontal,
        itemCount: cards.length,
        separatorBuilder: (_, _) => const SizedBox(width: 12),
        itemBuilder: (_, int i) => cards[i],
      ),
    );
  }

  Widget _buildList(BuildContext context, DocumentsState data) {
    if (data.documents.isEmpty) {
      final bool favoritesView =
          data.viewFilter == DocumentsViewFilter.favorites;
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              favoritesView
                  ? Icons.star_border_rounded
                  : Icons.folder_open_rounded,
              size: 44,
              color: Theme.of(context).colorScheme.outline,
            ),
            const SizedBox(height: 12),
            Text(
              favoritesView ? 'No favorites yet' : 'No documents yet',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            Text(
              favoritesView
                  ? 'Star a file from its menu to see it here'
                  : 'No documents yet — tap "Upload" to add your first file',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      );
    }
    final DocumentsController notifier = ref.read(
      documentsControllerProvider.notifier,
    );
    return RefreshIndicator(
      onRefresh: () => notifier.selectFolder(data.selectedFolderId),
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(28, 8, 28, 24),
        itemCount: data.documents.length,
        separatorBuilder: (_, _) => const SizedBox(height: 8),
        itemBuilder: (BuildContext ctx, int index) {
          final DocumentItem doc = data.documents[index];
          return _DocumentTile(
            doc: doc,
            selectionMode: data.selectionMode,
            selected: data.selection.contains(doc.id),
            onToggleSelect: () => notifier.toggleSelect(doc.id),
            onDownload: () => _download(doc),
            onExportWord: () => _exportWord(doc),
            onToggleFavorite: () => _toggleFavorite(doc),
            onSplit: () => _split(doc),
            onProtect: () => _protect(doc, removing: false),
            onUnprotect: () => _protect(doc, removing: true),
            onDelete: () => _deleteDocument(doc),
            onOpenViewer: () => _openViewer(doc),
          );
        },
      ),
    );
  }
}

/// Card thư mục ngang (spec: 180–200px) — chọn để lọc, icon xóa có confirm.
class _FolderCard extends StatelessWidget {
  const _FolderCard({
    required this.name,
    required this.count,
    required this.selected,
    required this.onTap,
    this.onDelete,
  });

  final String name;
  final int count;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return SizedBox(
      width: 190,
      child: Card(
        color: selected ? colors.primaryContainer : colors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: selected ? colors.primary : colors.outline),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: Row(
              children: <Widget>[
                Icon(
                  selected ? Icons.folder_rounded : Icons.folder_outlined,
                  size: 24,
                  color: selected ? colors.primary : colors.onSurfaceVariant,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: selected
                              ? FontWeight.w700
                              : FontWeight.w600,
                          color: selected ? colors.primary : colors.onSurface,
                        ),
                      ),
                      Text(
                        count == 1 ? '1 file' : '$count files',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                if (onDelete != null)
                  InkWell(
                    customBorder: const CircleBorder(),
                    onTap: onDelete,
                    child: Icon(
                      Icons.close,
                      size: 16,
                      color: colors.onSurfaceVariant,
                    ),
                  ),
              ],
            ),
          ),
        ),
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
    required this.onExportWord,
    required this.onToggleFavorite,
    required this.onSplit,
    required this.onProtect,
    required this.onUnprotect,
    required this.onDelete,
    required this.onOpenViewer,
  });

  final DocumentItem doc;
  final bool selectionMode;
  final bool selected;
  final VoidCallback onToggleSelect;
  final VoidCallback onDownload;
  final VoidCallback onExportWord;
  final VoidCallback onToggleFavorite;
  final VoidCallback onSplit;
  final VoidCallback onProtect;
  final VoidCallback onUnprotect;
  final VoidCallback onDelete;
  final VoidCallback onOpenViewer;

  IconData get _icon {
    if (doc.isPdf) return Icons.picture_as_pdf;
    if (doc.mimeType.startsWith('image/')) return Icons.image_outlined;
    return Icons.description_outlined;
  }

  Color _iconTint(ColorScheme colors) =>
      doc.isPdf ? colors.error : colors.primary;

  String get _meta {
    final double mb = doc.sizeBytes / (1024 * 1024);
    final String size = mb >= 1
        ? '${mb.toStringAsFixed(1)} MB'
        : '${(doc.sizeBytes / 1024).toStringAsFixed(0)} KB';
    return doc.pageCount != null ? '${doc.pageCount} trang · $size' : size;
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: selected ? colors.primary : colors.outline,
          width: selected ? 1.5 : 1,
        ),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: selectionMode ? onToggleSelect : onOpenViewer,
        child: SizedBox(
          height: 64,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: Row(
              children: <Widget>[
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: _iconTint(colors).withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(_icon, size: 21, color: _iconTint(colors)),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        doc.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(_meta, style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                ),
                if (selectionMode)
                  Checkbox(
                    value: selected,
                    onChanged: (bool? _) => onToggleSelect(),
                  )
                else ...<Widget>[
                  IconButton(
                    visualDensity: VisualDensity.compact,
                    tooltip: doc.isFavorite ? 'Unfavorite' : 'Favorite',
                    onPressed: onToggleFavorite,
                    icon: Icon(
                      doc.isFavorite
                          ? Icons.star_rounded
                          : Icons.star_border_rounded,
                      size: 22,
                      color: doc.isFavorite
                          ? Colors.amber
                          : colors.onSurfaceVariant,
                    ),
                  ),
                  PopupMenuButton<String>(
                    icon: Icon(Icons.more_vert, color: colors.onSurfaceVariant),
                    onSelected: (String action) {
                      switch (action) {
                        case 'download':
                          onDownload();
                        case 'exportWord':
                          onExportWord();
                        case 'favorite':
                          onToggleFavorite();
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
                    itemBuilder: (BuildContext ctx) => <PopupMenuEntry<String>>[
                      const PopupMenuItem<String>(
                        value: 'download',
                        child: Text('Download'),
                      ),
                      // OCR chỉ đọc được PDF và ảnh → ẩn với các loại khác
                      if (doc.isPdf || doc.isImage)
                        const PopupMenuItem<String>(
                          value: 'exportWord',
                          child: Text('Export to Word…'),
                        ),
                      PopupMenuItem<String>(
                        value: 'favorite',
                        child: Text(doc.isFavorite ? 'Unfavorite' : 'Favorite'),
                      ),
                      const PopupMenuItem<String>(
                        value: 'split',
                        child: Text('Split pages…'),
                      ),
                      const PopupMenuItem<String>(
                        value: 'protect',
                        child: Text('Set password…'),
                      ),
                      const PopupMenuItem<String>(
                        value: 'unprotect',
                        child: Text('Remove password…'),
                      ),
                      const PopupMenuDivider(),
                      PopupMenuItem<String>(
                        value: 'delete',
                        child: Text(
                          'Delete',
                          style: TextStyle(color: colors.error),
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
