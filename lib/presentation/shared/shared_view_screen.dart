/// SharedView — màn xem tài liệu qua link chia sẻ (SRS FR-3, FR-6).
///
/// Viewer chỉ đọc (ẩn công cụ), banner "Tài liệu được chia sẻ bởi {owner}",
/// pin comment overlay (P2) + sidebar thread kiểu Google Docs. Chủ tài liệu
/// mở từ "Bình luận chia sẻ" thì có quyền xóa comment.
///
/// Hình học pin (FR-6.3): continuous vertical layout xếp trang theo kích thước
/// đã fit viewport. Transformation của viewer áp cho cả trang và lớp pin nên
/// zoom/pan/scroll không làm lệch tọa độ chuẩn hóa đã lưu.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:syncfusion_flutter_pdf/pdf.dart';
import 'package:syncfusion_flutter_pdfviewer/pdfviewer.dart';

import '../../domain/entities/share_entities.dart';
import 'share_navigation.dart';
import 'shared_view_controller.dart';

/// Khoảng cách giữa 2 trang trong viewer (Syncfusion mặc định 4 logical px).
const double _kPageSpacing = 4.0;

/// Quy đổi tọa độ comment chuẩn hóa sang tọa độ vùng viewer (logical px).
/// Công thức dùng chung khi vẽ pin và khi test zoom/pan/lật trang.
@visibleForTesting
Offset pinOffsetForPage({
  required int pageNumber,
  required double normX,
  required double normY,
  required Map<int, Size> pageSizes,
  required double viewportWidth,
  required double zoom,
  required Offset scrollOffset,
  double pageSpacing = _kPageSpacing,
}) {
  if (pageNumber < 1 ||
      normX < 0 ||
      normX > 1 ||
      normY < 0 ||
      normY > 1 ||
      zoom <= 0) {
    return const Offset(double.nan, double.nan);
  }
  double top = 0;
  for (int page = 1; page <= pageNumber; page++) {
    final Size? pdfSize = pageSizes[page];
    if (pdfSize == null || pdfSize.width <= 0 || pdfSize.height <= 0) {
      return const Offset(double.nan, double.nan);
    }
    final Size display = Size(
      viewportWidth,
      viewportWidth * pdfSize.height / pdfSize.width,
    );
    if (page == pageNumber) {
      final double scaledWidth = display.width * zoom;
      final double leftInset = scaledWidth < viewportWidth
          ? (viewportWidth - scaledWidth) / 2
          : 0;
      return Offset(
        leftInset + normX * scaledWidth - scrollOffset.dx,
        (top + normY * display.height) * zoom - scrollOffset.dy,
      );
    }
    top += display.height + pageSpacing;
  }
  return const Offset(double.nan, double.nan);
}

class SharedViewScreen extends ConsumerStatefulWidget {
  const SharedViewScreen({
    super.key,
    this.token,
    this.ownerDocumentId,
    this.ownerMeta,
    this.previewPdfBuilder,
    this.previewPinLayer = false,
  });

  /// Token từ URL ?share=TOKEN (chế độ người nhận).
  final String? token;

  /// != null → chế độ chủ tài liệu: đọc file qua API đăng nhập, được xóa comment.
  final String? ownerDocumentId;
  final SharedDocumentMeta? ownerMeta;

  /// Test widget không cần native PDF engine; production luôn dùng SfPdfViewer.
  @visibleForTesting
  final Widget Function(BuildContext context, Uint8List bytes)?
  previewPdfBuilder;

  /// Test dùng lớp pin thuần Flutter với PDF trang 3 kích thước 200×400.
  /// Production luôn null và dùng SfPdfViewer.
  @visibleForTesting
  final bool previewPinLayer;

  @override
  ConsumerState<SharedViewScreen> createState() => _SharedViewScreenState();
}

class _SharedViewScreenState extends ConsumerState<SharedViewScreen> {
  final PdfViewerController _pdfController = PdfViewerController();
  final Map<String, GlobalKey> _commentKeys = <String, GlobalKey>{};

  /// Key vùng viewer để quy đổi tọa độ chạm → tọa độ viewport.
  final GlobalKey _viewerKey = GlobalKey();

  /// Kích thước trang (PDF points) theo số trang — lấy lúc document load.
  Map<int, Size> _pdfPageSizes = <int, Size>{};

  /// Bề rộng viewport của vùng viewer (logical px).
  double _viewportWidth = 0;

  double _zoom = 1.0;
  int _currentPage = 1;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.ownerDocumentId != null) {
        ref
            .read(sharedViewProvider.notifier)
            .initOwner(widget.ownerDocumentId!, widget.ownerMeta!);
      } else {
        ref.read(sharedViewProvider.notifier).init(widget.token ?? '');
      }
    });
  }

  /// Vị trí pin (tọa độ vùng viewer) cho comment tại trang/norm — null khi
  /// chưa đủ hình học để tính.
  Offset? _pinOffset(int pageNumber, double normX, double normY) {
    final Offset result = pinOffsetForPage(
      pageNumber: pageNumber,
      normX: normX,
      normY: normY,
      pageSizes: _pdfPageSizes,
      viewportWidth: _viewportWidth,
      zoom: _zoom,
      scrollOffset: _pdfController.scrollOffset,
    );
    return result.dx.isFinite && result.dy.isFinite ? result : null;
  }

  Timer? _scrollRefreshTimer;

  /// Syncfusion không phát ScrollNotification cho pan/pinch. Lấy mẫu vị trí
  /// trong thao tác con trỏ để pin bám theo nội dung mà không rebuild liên tục
  /// khi màn hình đang đứng yên.
  void _refreshPinsFromViewport() {
    if (!mounted || _pdfPageSizes.isEmpty) return;
    setState(() {});
    _scrollRefreshTimer?.cancel();
    _scrollRefreshTimer = Timer(const Duration(milliseconds: 120), () {
      if (mounted) setState(() {});
    });
  }

  Timer? _highlightTimer;

  @override
  void dispose() {
    _highlightTimer?.cancel();
    _scrollRefreshTimer?.cancel();
    _pdfController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final SharedViewState s = ref.watch(sharedViewProvider);
    final SharedDocumentMeta? meta = s.meta;
    final ThemeData theme = Theme.of(context);

    Widget body;
    switch (s.status) {
      case SharedViewStatus.loading:
        body = const Center(child: CircularProgressIndicator());
      case SharedViewStatus.linkDead:
        body = _DeadLinkView(onHome: _goHome);
      case SharedViewStatus.error:
        body = _ErrorView(
          onRetry: () => ref.read(sharedViewProvider.notifier).retry(),
        );
      case SharedViewStatus.ready:
        body = _buildReady(context, s, meta!);
    }

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              meta?.fileName ?? 'Tài liệu chia sẻ',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
            ),
            Text(
              'Được chia sẻ bởi ${meta?.ownerName ?? ''}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11.5,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        actions: <Widget>[
          if (widget.ownerDocumentId != null)
            IconButton(
              tooltip: 'Quay lại',
              onPressed: () => Navigator.of(context).maybePop(),
              icon: const Icon(Icons.arrow_back),
            ),
          if (s.isPdf) ...<Widget>[
            IconButton(
              tooltip: 'Trang trước',
              onPressed: () => _pdfController.previousPage(),
              icon: const Icon(Icons.chevron_left),
            ),
            IconButton(
              tooltip: 'Trang sau',
              onPressed: () => _pdfController.nextPage(),
              icon: const Icon(Icons.chevron_right),
            ),
            IconButton(
              tooltip: 'Phóng to',
              onPressed: _zoom < 3
                  ? () => _pdfController.zoomLevel = _zoom + 0.25
                  : null,
              icon: const Icon(Icons.zoom_in),
            ),
            IconButton(
              tooltip: 'Thu nhỏ',
              onPressed: _zoom > 1
                  ? () => _pdfController.zoomLevel = _zoom - 0.25
                  : null,
              icon: const Icon(Icons.zoom_out),
            ),
          ],
          if (s.canComment && s.isPdf)
            IconButton(
              tooltip: s.isPinMode ? 'Tắt ghim' : 'Ghim bình luận',
              onPressed: () =>
                  ref.read(sharedViewProvider.notifier).togglePinMode(),
              icon: Icon(
                s.isPinMode ? Icons.push_pin : Icons.push_pin_outlined,
                color: s.isPinMode
                    ? theme.colorScheme.primary
                    : theme.colorScheme.onSurfaceVariant,
              ),
            ),
          if (s.canComment)
            IconButton(
              tooltip: s.isCommentsPanelOpen ? 'Đóng bình luận' : 'Bình luận',
              onPressed: () => ref
                  .read(sharedViewProvider.notifier)
                  .setPanelOpen(!s.isCommentsPanelOpen),
              icon: Badge(
                isLabelVisible: s.comments.isNotEmpty,
                label: Text('${s.comments.length}'),
                child: const Icon(Icons.mode_comment_outlined),
              ),
            ),
        ],
      ),
      body: body,
    );
  }

  void _goHome() {
    // Link public là màn đầu: không pop (sẽ thành màn đen). Về trang chủ bằng
    // cách xóa token khỏi URL rồi reload; phiên đăng nhập vẫn do Supabase giữ.
    clearShareLinkAndGoHome();
  }

  Widget _buildReady(
    BuildContext context,
    SharedViewState s,
    SharedDocumentMeta meta,
  ) {
    final Uint8List? bytes = s.bytes;
    if (bytes == null) {
      return _ErrorView(
        onRetry: () => ref.read(sharedViewProvider.notifier).retry(),
      );
    }
    final bool isPdf = meta.mimeType == 'application/pdf';

    return Column(
      children: <Widget>[
        Material(
          color: Theme.of(context).colorScheme.secondaryContainer,
          child: ListTile(
            dense: true,
            leading: Icon(
              Icons.share_outlined,
              color: Theme.of(context).colorScheme.onSecondaryContainer,
            ),
            title: Text(
              'Tài liệu được chia sẻ bởi ${meta.ownerName}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 13,
                color: Theme.of(context).colorScheme.onSecondaryContainer,
              ),
            ),
            subtitle: Text(
              s.canComment
                  ? 'Chế độ chỉ đọc · Bạn có thể bình luận'
                  : 'Chế độ chỉ đọc',
              style: TextStyle(
                fontSize: 11.5,
                color: Theme.of(context).colorScheme.onSecondaryContainer,
              ),
            ),
          ),
        ),
        Expanded(
          child: Row(
            children: <Widget>[
              Expanded(
                child: widget.previewPinLayer
                    ? _buildPinPreview(s)
                    : widget.previewPdfBuilder != null && isPdf
                    ? widget.previewPdfBuilder!(context, bytes)
                    : isPdf
                    ? _buildPdfViewer(context, s, bytes)
                    : _buildFallbackViewer(meta, bytes),
              ),
              if (s.isCommentsPanelOpen && s.canComment) ...<Widget>[
                const VerticalDivider(width: 1),
                SizedBox(
                  width: 320,
                  child: _CommentsSidebar(
                    currentPage: _currentPage,
                    commentKeys: _commentKeys,
                    onJumpToComment: (SharedComment c) {
                      if (c.isPinned && !widget.previewPinLayer) {
                        _pdfController.jumpToPage(c.pageNumber);
                      }
                      _showThread(c);
                    },
                    onDelete:
                        ref.read(sharedViewProvider.notifier).canDeleteComments
                        ? (SharedComment c) async {
                            final bool ok = await ref
                                .read(sharedViewProvider.notifier)
                                .deleteComment(c.id);
                            if (!ok && mounted) {
                              ScaffoldMessenger.of(this.context).showSnackBar(
                                const SnackBar(
                                  content: Text('Không xóa được bình luận'),
                                ),
                              );
                            }
                          }
                        : null,
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  /// Tự tắt highlight sau 1.6s (pin nhấp nháy đủ thấy).
  void _clearHighlightSoon() {
    _highlightTimer?.cancel();
    _highlightTimer = Timer(const Duration(milliseconds: 1600), () {
      if (mounted) ref.read(sharedViewProvider.notifier).clearHighlight();
    });
  }

  Widget _buildPdfViewer(
    BuildContext context,
    SharedViewState s,
    Uint8List bytes,
  ) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        _viewportWidth = constraints.maxWidth;
        return Stack(
          key: _viewerKey,
          children: <Widget>[
            Positioned.fill(
              child: Listener(
                behavior: HitTestBehavior.translucent,
                onPointerMove: (_) => _refreshPinsFromViewport(),
                onPointerSignal: (_) => _refreshPinsFromViewport(),
                child: SfPdfViewer.memory(
                  bytes,
                  controller: _pdfController,
                  pageSpacing: _kPageSpacing,
                  scrollDirection: PdfScrollDirection.vertical,
                  pageLayoutMode: PdfPageLayoutMode.continuous,
                  onTap: (PdfGestureDetails details) {
                    // pagePosition là tọa độ PDF points, không phụ thuộc zoom/pan.
                    if (!s.isPinMode || details.pageNumber < 1) return;
                    final Size? pageSize = _pdfPageSizes[details.pageNumber];
                    if (pageSize == null || pageSize.isEmpty) return;
                    ref
                        .read(sharedViewProvider.notifier)
                        .armPinAt(
                          pageNumber: details.pageNumber,
                          normX: (details.pagePosition.dx / pageSize.width)
                              .clamp(0.0, 1.0),
                          normY: (details.pagePosition.dy / pageSize.height)
                              .clamp(0.0, 1.0),
                        );
                  },
                  onDocumentLoadFailed: (PdfDocumentLoadFailedDetails details) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          details.description.toLowerCase().contains('password')
                              ? 'File có mật khẩu. Hãy nhập mật khẩu để mở.'
                              : 'Không mở được PDF. Vui lòng thử lại.',
                        ),
                      ),
                    );
                  },
                  canShowScrollHead: true,
                  canShowScrollStatus: true,
                  enableDoubleTapZooming: true,
                  onDocumentLoaded: (PdfDocumentLoadedDetails details) {
                    final PdfDocument doc = details.document;
                    final Map<int, Size> sizes = <int, Size>{};
                    for (int i = 0; i < doc.pages.count; i++) {
                      final PdfPage page = doc.pages[i];
                      sizes[i + 1] = Size(
                        page.size.width.toDouble(),
                        page.size.height.toDouble(),
                      );
                    }
                    setState(() => _pdfPageSizes = sizes);
                  },
                  onPageChanged: (PdfPageChangedDetails details) {
                    setState(() => _currentPage = details.newPageNumber);
                  },
                  onZoomLevelChanged: (PdfZoomDetails details) {
                    setState(() => _zoom = details.newZoomLevel);
                  },
                ),
              ),
            ),
            ..._buildPins(context, s),
            if (s.isPinMode)
              Positioned(
                top: 12,
                left: 0,
                right: 0,
                child: Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 8,
                    ),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.inverseSurface,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      'Chạm vào vị trí cần ghim bình luận',
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.onInverseSurface,
                        fontSize: 12.5,
                      ),
                    ),
                  ),
                ),
              ),
            if (s.pendingPin != null)
              Positioned.fill(
                child: _PendingPinDialog(
                  state: s,
                  onSubmit: (String body) => ref
                      .read(sharedViewProvider.notifier)
                      .submitPendingPin(body),
                  onCancel: () =>
                      ref.read(sharedViewProvider.notifier).cancelPendingPin(),
                  onAuthorName: (String name) =>
                      ref.read(sharedViewProvider.notifier).setAuthorName(name),
                ),
              ),
          ],
        );
      },
    );
  }

  void _showThread(SharedComment comment) {
    final SharedViewController controller = ref.read(
      sharedViewProvider.notifier,
    );
    controller.setPanelOpen(true);
    controller.highlightComment(comment.id);
    _clearHighlightSoon();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final BuildContext? tile = _commentKeys[comment.id]?.currentContext;
      if (tile != null && tile.mounted) {
        Scrollable.ensureVisible(
          tile,
          duration: const Duration(milliseconds: 250),
          alignment: 0.2,
        );
      }
    });
  }

  /// Lớp pin thật với PDF giả lập cho widget test; không có logic nghiệp vụ mới.
  Widget _buildPinPreview(SharedViewState state) {
    return LayoutBuilder(
      key: const Key('shared-pin-preview'),
      builder: (BuildContext context, BoxConstraints constraints) {
        _viewportWidth = constraints.maxWidth;
        _pdfPageSizes = const <int, Size>{
          1: Size(200, 400),
          2: Size(200, 400),
          3: Size(200, 400),
        };
        return Stack(
          children: <Widget>[
            const Positioned.fill(child: ColoredBox(color: Colors.white)),
            ..._buildPins(context, state),
          ],
        );
      },
    );
  }

  List<Widget> _buildPins(BuildContext context, SharedViewState s) {
    // Đánh số theo thứ tự comment gốc (FR-6.2); chỉ vẽ trang đang hiển thị
    final List<SharedComment> roots = s.comments
        .where((SharedComment c) => c.parentId == null)
        .toList(growable: false);
    final Map<String, int> numberById = <String, int>{};
    for (int i = 0; i < roots.length; i++) {
      if (roots[i].isPinned) numberById[roots[i].id] = numberById.length + 1;
    }

    final List<Widget> pins = <Widget>[];
    for (final SharedComment comment in roots) {
      if (!comment.isPinned) continue;
      final Offset? offset = _pinOffset(
        comment.pageNumber,
        comment.normX,
        comment.normY,
      );
      if (offset == null) continue;
      final bool highlight =
          s.highlightCommentId == comment.id ||
          s.comments.any(
            (SharedComment c) =>
                c.parentId == comment.id && c.id == s.highlightCommentId,
          );
      pins.add(
        Positioned(
          left: offset.dx - 13,
          top: offset.dy - 13,
          child: CommentPin(
            number: numberById[comment.id] ?? 0,
            highlighted: highlight,
            onTap: () {
              final SharedViewController controller = ref.read(
                sharedViewProvider.notifier,
              );
              controller.setPanelOpen(true);
              controller.highlightComment(comment.id);
              _clearHighlightSoon();
              WidgetsBinding.instance.addPostFrameCallback((_) {
                final BuildContext? tile =
                    _commentKeys[comment.id]?.currentContext;
                if (tile != null && tile.mounted) {
                  Scrollable.ensureVisible(
                    tile,
                    duration: const Duration(milliseconds: 250),
                    alignment: 0.2,
                  );
                }
              });
            },
          ),
        ),
      );
    }
    return pins;
  }

  /// Ảnh / text — chỉ đọc; giải mã UTF-8, thay ký tự hỏng thay vì hiện mojibake.
  Widget _buildFallbackViewer(SharedDocumentMeta meta, Uint8List bytes) {
    if (meta.mimeType.startsWith('image/')) {
      return InteractiveViewer(
        maxScale: 8,
        child: Center(child: Image.memory(bytes, fit: BoxFit.contain)),
      );
    }
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: SelectableText(utf8.decode(bytes, allowMalformed: true)),
      ),
    );
  }
}

/// Chấm tròn đánh số (FR-6.2) — nhấp nháy khi được highlight.
@visibleForTesting
class CommentPin extends StatefulWidget {
  const CommentPin({
    super.key,
    required this.number,
    required this.onTap,
    this.highlighted = false,
  });

  final int number;
  final bool highlighted;
  final VoidCallback onTap;

  @override
  State<CommentPin> createState() => _CommentPinState();
}

class _CommentPinState extends State<CommentPin>
    with SingleTickerProviderStateMixin {
  late final AnimationController _blink = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 450),
  );

  @override
  void initState() {
    super.initState();
    if (widget.highlighted) _blink.repeat(reverse: true);
  }

  @override
  void didUpdateWidget(covariant CommentPin oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.highlighted && !_blink.isAnimating) {
      _blink.repeat(reverse: true);
    } else if (!widget.highlighted && _blink.isAnimating) {
      _blink.stop();
      _blink.value = 0;
    }
  }

  @override
  void dispose() {
    _blink.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return GestureDetector(
      onTap: widget.onTap,
      child: ScaleTransition(
        scale: Tween<double>(
          begin: 1,
          end: 1.3,
        ).animate(CurvedAnimation(parent: _blink, curve: Curves.easeInOut)),
        child: Container(
          width: 26,
          height: 26,
          decoration: BoxDecoration(
            color: theme.colorScheme.primary,
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white, width: 2),
            boxShadow: const <BoxShadow>[
              BoxShadow(color: Colors.black26, blurRadius: 4),
            ],
          ),
          alignment: Alignment.center,
          child: Text(
            '${widget.number}',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ),
    );
  }
}

/// Hộp nhập nội dung comment tại pin vừa đặt.
class _PendingPinDialog extends ConsumerStatefulWidget {
  const _PendingPinDialog({
    required this.state,
    required this.onSubmit,
    required this.onCancel,
    required this.onAuthorName,
  });

  final SharedViewState state;
  final Future<bool> Function(String body) onSubmit;
  final VoidCallback onCancel;
  final void Function(String name) onAuthorName;

  @override
  ConsumerState<_PendingPinDialog> createState() => _PendingPinDialogState();
}

class _PendingPinDialogState extends ConsumerState<_PendingPinDialog> {
  late final TextEditingController _body = TextEditingController();
  late final TextEditingController _author = TextEditingController(
    text: ref.read(sharedViewProvider.notifier).authorName,
  );
  bool _sending = false;

  @override
  void dispose() {
    _body.dispose();
    _author.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_body.text.trim().isEmpty) return;
    setState(() => _sending = true);
    widget.onAuthorName(_author.text);
    final bool ok = await widget.onSubmit(_body.text);
    if (!mounted) return;
    setState(() => _sending = false);
    if (!ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            ref.read(sharedViewProvider).commentError ??
                'Không gửi được bình luận',
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onCancel,
      child: Container(
        color: Colors.black38,
        alignment: Alignment.center,
        child: GestureDetector(
          onTap: () {},
          child: Material(
            elevation: 6,
            borderRadius: BorderRadius.circular(14),
            child: Container(
              width: 380,
              padding: const EdgeInsets.all(18),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'Bình luận tại trang ${widget.state.pendingPin?.pageNumber ?? ''}',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _author,
                    maxLength: 80,
                    decoration: const InputDecoration(
                      labelText: 'Tên của bạn',
                      counterText: '',
                      isDense: true,
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _body,
                    maxLines: 4,
                    maxLength: 2000,
                    autofocus: true,
                    decoration: const InputDecoration(
                      hintText: 'Nội dung bình luận…',
                    ),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: <Widget>[
                      TextButton(
                        onPressed: widget.onCancel,
                        child: const Text('Hủy'),
                      ),
                      FilledButton(
                        onPressed: _sending ? null : _submit,
                        child: _sending
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Text('Gửi'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Sidebar thread kiểu Google Docs (FR-6.1/6.2).
class _CommentsSidebar extends ConsumerWidget {
  const _CommentsSidebar({
    required this.currentPage,
    required this.commentKeys,
    required this.onJumpToComment,
    this.onDelete,
  });

  final int currentPage;
  final Map<String, GlobalKey> commentKeys;
  final void Function(SharedComment comment) onJumpToComment;
  final Future<void> Function(SharedComment comment)? onDelete;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final SharedViewState s = ref.watch(sharedViewProvider);
    final List<SharedComment> comments = s.comments;
    final ThemeData theme = Theme.of(context);
    final bool canAddComment = onDelete == null;

    if (comments.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                Icons.mode_comment_outlined,
                size: 40,
                color: theme.colorScheme.outline,
              ),
              const SizedBox(height: 8),
              const Text(
                'Chưa có bình luận nào',
                style: TextStyle(fontSize: 13),
              ),
              if (canAddComment) ...<Widget>[
                const SizedBox(height: 12),
                _AddCommentBox(
                  initialAuthorName: ref
                      .read(sharedViewProvider.notifier)
                      .authorName,
                  onAuthorName: ref
                      .read(sharedViewProvider.notifier)
                      .setAuthorName,
                  onSubmitted: (String body) => ref
                      .read(sharedViewProvider.notifier)
                      .addGeneralComment(body, currentPage: currentPage),
                ),
              ],
            ],
          ),
        ),
      );
    }

    final Map<String, List<SharedComment>> repliesByParent =
        <String, List<SharedComment>>{};
    for (final SharedComment c in comments) {
      if (c.parentId != null) {
        repliesByParent
            .putIfAbsent(c.parentId!, () => <SharedComment>[])
            .add(c);
      }
    }
    final List<SharedComment> roots = comments
        .where((SharedComment c) => c.parentId == null)
        .toList(growable: false);

    return Column(
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
          child: Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  'Bình luận (${comments.length})',
                  style: theme.textTheme.titleSmall,
                ),
              ),
              IconButton(
                tooltip: 'Làm mới',
                onPressed: () =>
                    ref.read(sharedViewProvider.notifier).refreshComments(),
                icon: const Icon(Icons.refresh, size: 20),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.only(bottom: 12),
            itemCount: roots.length + (canAddComment ? 1 : 0),
            itemBuilder: (BuildContext context, int index) {
              if (index == roots.length && canAddComment) {
                return Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                  child: _AddCommentBox(
                    initialAuthorName: ref
                        .read(sharedViewProvider.notifier)
                        .authorName,
                    onAuthorName: ref
                        .read(sharedViewProvider.notifier)
                        .setAuthorName,
                    onSubmitted: (String body) => ref
                        .read(sharedViewProvider.notifier)
                        .addGeneralComment(body, currentPage: currentPage),
                  ),
                );
              }
              final SharedComment root = roots[index];
              return _CommentTile(
                key: commentKeys.putIfAbsent(root.id, GlobalKey.new),
                comment: root,
                number: index + 1,
                replies: repliesByParent[root.id] ?? const <SharedComment>[],
                highlighted: s.highlightCommentId == root.id,
                onTap: () => onJumpToComment(root),
                onDelete: onDelete != null ? () => onDelete!(root) : null,
                onReply: (String body) => ref
                    .read(sharedViewProvider.notifier)
                    .replyComment(root.id, body),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _AddCommentBox extends StatefulWidget {
  const _AddCommentBox({
    required this.initialAuthorName,
    required this.onAuthorName,
    required this.onSubmitted,
  });

  final String initialAuthorName;
  final void Function(String name) onAuthorName;
  final Future<bool> Function(String body) onSubmitted;

  @override
  State<_AddCommentBox> createState() => _AddCommentBoxState();
}

class _AddCommentBoxState extends State<_AddCommentBox> {
  late final TextEditingController _authorController = TextEditingController(
    text: widget.initialAuthorName,
  );
  final TextEditingController _controller = TextEditingController();
  bool _sending = false;

  @override
  void dispose() {
    _authorController.dispose();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    if (_controller.text.trim().isEmpty) return;
    setState(() => _sending = true);
    widget.onAuthorName(_authorController.text);
    final bool ok = await widget.onSubmitted(_controller.text);
    if (!mounted) return;
    setState(() => _sending = false);
    if (ok) _controller.clear();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Expanded(
          child: Column(
            children: <Widget>[
              TextField(
                controller: _authorController,
                maxLength: 80,
                decoration: const InputDecoration(
                  labelText: 'Tên của bạn',
                  counterText: '',
                  isDense: true,
                ),
              ),
              TextField(
                controller: _controller,
                maxLength: 2000,
                decoration: const InputDecoration(
                  hintText: 'Thêm bình luận…',
                  isDense: true,
                ),
                onSubmitted: (_) => _send(),
              ),
            ],
          ),
        ),
        IconButton(
          onPressed: _sending ? null : _send,
          icon: _sending
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.send, size: 18),
        ),
      ],
    );
  }
}

class _CommentTile extends StatelessWidget {
  const _CommentTile({
    super.key,
    required this.comment,
    required this.number,
    required this.replies,
    required this.highlighted,
    required this.onTap,
    this.onDelete,
    this.onReply,
  });

  final SharedComment comment;
  final int number;
  final List<SharedComment> replies;
  final bool highlighted;
  final VoidCallback onTap;
  final VoidCallback? onDelete;
  final Future<bool> Function(String body)? onReply;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return InkWell(
      onTap: onTap,
      child: Container(
        color: highlighted ? theme.highlightColor : null,
        padding: const EdgeInsets.fromLTRB(16, 10, 12, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                _Avatar(name: comment.authorName, radius: 12, fontSize: 11),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    comment.authorName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
                    ),
                  ),
                ),
                Text(
                  _relativeTime(comment.createdAt),
                  style: TextStyle(
                    fontSize: 11,
                    color: theme.colorScheme.outline,
                  ),
                ),
                if (onDelete != null)
                  IconButton(
                    tooltip: 'Xóa',
                    visualDensity: VisualDensity.compact,
                    onPressed: onDelete,
                    icon: Icon(
                      Icons.delete_outline,
                      size: 16,
                      color: theme.colorScheme.error,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(comment.body, style: const TextStyle(fontSize: 13)),
            const SizedBox(height: 4),
            Text(
              comment.isPinned
                  ? 'Ghim tại trang ${comment.pageNumber}'
                  : 'Bình luận chung',
              style: TextStyle(fontSize: 11, color: theme.colorScheme.outline),
            ),
            for (final SharedComment reply in replies)
              Padding(
                padding: const EdgeInsets.only(left: 20, top: 8),
                child: _ReplyTile(comment: reply, onDelete: onDelete),
              ),
            if (onReply != null) _ReplyBox(onReply: onReply!),
          ],
        ),
      ),
    );
  }
}

class _ReplyTile extends StatelessWidget {
  const _ReplyTile({required this.comment, this.onDelete});

  final SharedComment comment;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        _Avatar(
          name: comment.authorName,
          radius: 10,
          fontSize: 10,
          background: theme.colorScheme.secondaryContainer,
        ),
        const SizedBox(width: 6),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      comment.authorName,
                      style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 12,
                      ),
                    ),
                  ),
                  Text(
                    _relativeTime(comment.createdAt),
                    style: TextStyle(
                      fontSize: 10.5,
                      color: theme.colorScheme.outline,
                    ),
                  ),
                  if (onDelete != null)
                    IconButton(
                      tooltip: 'Xóa',
                      visualDensity: VisualDensity.compact,
                      onPressed: onDelete,
                      icon: Icon(
                        Icons.delete_outline,
                        size: 14,
                        color: theme.colorScheme.error,
                      ),
                    ),
                ],
              ),
              Text(comment.body, style: const TextStyle(fontSize: 12.5)),
            ],
          ),
        ),
      ],
    );
  }
}

/// Avatar chữ cái đầu tên (FR-6.1) — an toàn với chuỗi unicode.
class _Avatar extends StatelessWidget {
  const _Avatar({
    required this.name,
    required this.radius,
    required this.fontSize,
    this.background,
  });

  final String name;
  final double radius;
  final double fontSize;
  final Color? background;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String trimmed = name.trim();
    final String letter = trimmed.isEmpty
        ? 'K'
        : String.fromCharCode(trimmed.runes.first).toUpperCase();
    return CircleAvatar(
      radius: radius,
      backgroundColor: background ?? theme.colorScheme.primaryContainer,
      child: Text(
        letter,
        style: TextStyle(
          fontSize: fontSize,
          fontWeight: FontWeight.w700,
          color: background == null
              ? theme.colorScheme.onPrimaryContainer
              : null,
        ),
      ),
    );
  }
}

class _ReplyBox extends StatefulWidget {
  const _ReplyBox({required this.onReply});

  final Future<bool> Function(String body) onReply;

  @override
  State<_ReplyBox> createState() => _ReplyBoxState();
}

class _ReplyBoxState extends State<_ReplyBox> {
  final TextEditingController _controller = TextEditingController();
  bool _visible = false;
  bool _sending = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    if (_controller.text.trim().isEmpty) return;
    setState(() => _sending = true);
    final bool ok = await widget.onReply(_controller.text);
    if (!mounted) return;
    setState(() => _sending = false);
    if (ok) {
      _controller.clear();
      setState(() => _visible = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_visible) {
      return TextButton(
        onPressed: () => setState(() => _visible = true),
        child: const Text('Trả lời', style: TextStyle(fontSize: 12)),
      );
    }
    return Row(
      children: <Widget>[
        Expanded(
          child: TextField(
            controller: _controller,
            autofocus: true,
            decoration: const InputDecoration(
              hintText: 'Trả lời…',
              isDense: true,
            ),
            onSubmitted: (_) => _send(),
          ),
        ),
        IconButton(
          onPressed: _sending ? null : _send,
          icon: _sending
              ? const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.send, size: 16),
        ),
      ],
    );
  }
}

/// Thời gian tương đối kiểu "5 phút trước" (FR-6.1).
String _relativeTime(DateTime time) {
  final Duration diff = DateTime.now().difference(time);
  if (diff.inMinutes < 1) return 'vừa xong';
  if (diff.inMinutes < 60) return '${diff.inMinutes} phút trước';
  if (diff.inHours < 24) return '${diff.inHours} giờ trước';
  return '${diff.inDays} ngày trước';
}

/// Link chết → màn lỗi thân thiện + nút "Về trang chủ" (FR-3.3).
class _DeadLinkView extends StatelessWidget {
  const _DeadLinkView({required this.onHome});

  final VoidCallback onHome;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            Icons.link_off,
            size: 56,
            color: Theme.of(context).colorScheme.outline,
          ),
          const SizedBox(height: 12),
          const Text(
            'Link không tồn tại hoặc đã hết hạn',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          Text(
            'Hãy liên hệ người chia sẻ để nhận link mới.',
            style: TextStyle(
              fontSize: 13,
              color: Theme.of(context).colorScheme.outline,
            ),
          ),
          const SizedBox(height: 18),
          FilledButton(onPressed: onHome, child: const Text('Về trang chủ')),
        ],
      ),
    );
  }
}

/// Lỗi/timeout → "Không tải được tài liệu" + thử lại (FR-3.5).
class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            Icons.cloud_off,
            size: 56,
            color: Theme.of(context).colorScheme.outline,
          ),
          const SizedBox(height: 12),
          const Text(
            'Không tải được tài liệu',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 18),
          OutlinedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Thử lại'),
          ),
        ],
      ),
    );
  }
}
