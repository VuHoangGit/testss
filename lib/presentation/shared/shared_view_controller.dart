/// Điều khiển SharedView: tải metadata + file, quản lý comment + pin.
///
/// 2 chế độ:
/// - **Người nhận** ([init] với token): mọi thứ qua API public /public/shares.
/// - **Chủ tài liệu** (FR-6.5): token raw không lưu được ở server nên không
///   thể mở link như người nhận — tải file qua API đăng nhập và comment qua
///   /documents/{id}/share-comments, có quyền xóa.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/share_entities.dart';
import '../../domain/repositories/share_repository.dart';
import '../documents/documents_providers.dart';
import 'guest_name_store.dart';
import 'share_providers.dart';

enum SharedViewStatus { loading, ready, linkDead, error }

class SharedViewState {
  const SharedViewState({
    this.status = SharedViewStatus.loading,
    this.meta,
    this.bytes,
    this.comments = const <SharedComment>[],
    this.commentError,
    this.pendingPin,
    this.isCommentsPanelOpen = false,
    this.isPinMode = false,
    this.highlightCommentId,
  });

  final SharedViewStatus status;

  /// null khi chưa tải xong / lỗi.
  final SharedDocumentMeta? meta;
  final Uint8List? bytes;

  /// Sort (page, createdAt) — server đã sort, giữ nguyên.
  final List<SharedComment> comments;

  /// Lỗi gần nhất khi thao tác comment (null = không có).
  final String? commentError;

  /// Vị trí pin đang chờ người dùng nhập nội dung (null = không có).
  final ({int pageNumber, double normX, double normY})? pendingPin;

  final bool isCommentsPanelOpen;

  /// Đang bật chế độ chạm để ghim comment (FR-6.4).
  final bool isPinMode;

  /// Comment vừa được nhảy tới từ sidebar → nhấp nháy pin (FR-6.2).
  final String? highlightCommentId;

  bool get isPdf => meta?.mimeType == 'application/pdf';

  bool get canComment => meta?.canComment ?? false;

  SharedViewState copyWith({
    SharedViewStatus? status,
    Object? meta = _sentinel,
    Object? bytes = _sentinel,
    List<SharedComment>? comments,
    Object? commentError = _sentinel,
    Object? pendingPin = _sentinel,
    bool? isCommentsPanelOpen,
    bool? isPinMode,
    Object? highlightCommentId = _sentinel,
  }) {
    return SharedViewState(
      status: status ?? this.status,
      meta: identical(meta, _sentinel)
          ? this.meta
          : meta as SharedDocumentMeta?,
      bytes: identical(bytes, _sentinel) ? this.bytes : bytes as Uint8List?,
      comments: comments ?? this.comments,
      commentError: identical(commentError, _sentinel)
          ? this.commentError
          : commentError as String?,
      pendingPin: identical(pendingPin, _sentinel)
          ? this.pendingPin
          : pendingPin as ({int pageNumber, double normX, double normY})?,
      isCommentsPanelOpen: isCommentsPanelOpen ?? this.isCommentsPanelOpen,
      isPinMode: isPinMode ?? this.isPinMode,
      highlightCommentId: identical(highlightCommentId, _sentinel)
          ? this.highlightCommentId
          : highlightCommentId as String?,
    );
  }

  static const Object _sentinel = Object();
}

class SharedViewController extends Notifier<SharedViewState> {
  ShareRepository get _repo => ref.read(shareRepositoryProvider);

  /// Token khi ở chế độ người nhận; rỗng ở chế độ chủ tài liệu.
  String _token = '';

  /// != null → chế độ CHỦ tài liệu (FR-6.5): đọc file qua API đăng nhập,
  /// comment qua /documents/{id}/share-comments, được xóa comment.
  String? _ownerDocumentId;

  /// Metadata dựng sẵn ở chế độ chủ tài liệu (từ DocumentItem phía caller).
  SharedDocumentMeta? _ownerMeta;

  /// Poll comment mỗi 30s khi màn còn mở; đóng panel chỉ ẩn giao diện.
  Timer? _pollTimer;
  bool _loadingComments = false;

  /// Tên tác giả lưu cục bộ, tự điền lại khi mở link sau (FR-4.3).
  String authorName = readGuestName();

  @override
  SharedViewState build() {
    ref.onDispose(_cancelPoll);
    return const SharedViewState();
  }

  void _cancelPoll() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  /// Chế độ người nhận: mọi thao tác qua token public.
  Future<void> init(String token, {bool? openComments}) async {
    _token = token;
    _ownerDocumentId = null;
    _ownerMeta = null;
    state = SharedViewState(isCommentsPanelOpen: openComments ?? false);
    await _loadRecipient(); // Panel tự mở khi link đã có bình luận.
  }

  /// Chế độ chủ tài liệu (FR-6.5): không cần token.
  Future<void> initOwner(
    String documentId,
    SharedDocumentMeta meta, {
    bool openComments = true,
  }) async {
    _token = '';
    _ownerDocumentId = documentId;
    _ownerMeta = meta;
    state = SharedViewState(isCommentsPanelOpen: openComments);
    await _loadOwner();
  }

  bool get canDeleteComments => _ownerDocumentId != null;

  Future<void> retry() =>
      _ownerDocumentId != null ? _loadOwner() : _loadRecipient();

  // -- Tải dữ liệu ----------------------------------------------------------

  Future<void> _loadRecipient() async {
    state = state.copyWith(status: SharedViewStatus.loading);
    try {
      final SharedDocumentMeta meta = await _repo.getSharedMeta(_token);
      final Uint8List bytes = await _repo.downloadSharedFile(_token);
      final List<SharedComment>? comments = await _tryComments();
      state = state.copyWith(
        status: SharedViewStatus.ready,
        meta: meta,
        bytes: bytes,
        comments: comments ?? const <SharedComment>[],
        isCommentsPanelOpen: comments?.isNotEmpty ?? false,
      );
      _restartPolling();
    } on Exception catch (e) {
      final String msg = e.toString();
      if (msg.contains('Link không tồn tại')) {
        state = state.copyWith(status: SharedViewStatus.linkDead);
      } else {
        state = state.copyWith(status: SharedViewStatus.error);
      }
    }
  }

  Future<void> _loadOwner() async {
    state = state.copyWith(status: SharedViewStatus.loading);
    try {
      final Uint8List bytes = await ref
          .read(documentsRepositoryProvider)
          .downloadDocument(_ownerDocumentId!);
      final List<OwnerSharedComment> ownerComments = await _repo
          .listOwnerComments(_ownerDocumentId!);
      state = state.copyWith(
        status: SharedViewStatus.ready,
        meta: _ownerMeta,
        bytes: bytes,
        comments: ownerComments, // OwnerSharedComment extends SharedComment
      );
      _restartPolling();
    } on Exception {
      state = state.copyWith(status: SharedViewStatus.error);
    }
  }

  /// Lỗi mạng trả null để giữ comment cũ; không xóa dữ liệu đang hiển thị.
  Future<List<SharedComment>?> _tryComments() async {
    try {
      return await _repo.listComments(_token);
    } on Exception {
      return null;
    }
  }

  // -- Panel + poll ---------------------------------------------------------

  void _restartPolling() {
    _cancelPoll();
    if (state.status != SharedViewStatus.ready) return;
    _pollTimer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => refreshComments(),
    );
  }

  void setPanelOpen(bool open) {
    state = state.copyWith(isCommentsPanelOpen: open);
    _restartPolling();
    if (open) refreshComments();
  }

  // -- Pin mode (P2) --------------------------------------------------------

  void togglePinMode() {
    state = state.copyWith(isPinMode: !state.isPinMode, pendingPin: null);
  }

  /// Người dùng bật chế độ pin rồi chạm lên PDF tại điểm đã chuẩn hóa (FR-6.4).
  void armPinAt({
    required int pageNumber,
    required double normX,
    required double normY,
  }) {
    if (!state.isPinMode) return;
    state = state.copyWith(
      pendingPin: (pageNumber: pageNumber, normX: normX, normY: normY),
      isPinMode: false,
    );
  }

  void cancelPendingPin() {
    state = state.copyWith(pendingPin: null);
  }

  void setAuthorName(String name) {
    authorName = name.trim();
    writeGuestName(authorName);
  }

  // -- Gửi comment (chỉ chế độ người nhận — owner không có token) -----------

  /// Comment không ghim: ảnh/text dùng trang 1; PDF dùng trang hiện tại nhưng
  /// gắn cờ [isPinned] = false để không tạo chấm trên nội dung (FR-4.8/6.4).
  Future<bool> addGeneralComment(String body, {required int currentPage}) =>
      _submit(
        body: body,
        pin: (
          pageNumber: state.isPdf ? currentPage : 1,
          normX: 0.5,
          normY: 0.5,
        ),
        parentId: null,
        isPinned: false,
      );

  Future<bool> submitPendingPin(String body) {
    final ({int pageNumber, double normX, double normY})? pin =
        state.pendingPin;
    if (pin == null) return Future<bool>.value(false);
    return _submit(body: body, pin: pin, parentId: null);
  }

  Future<bool> replyComment(String parentId, String body) {
    final SharedComment? parent = state.comments
        .where((SharedComment c) => c.id == parentId)
        .firstOrNull;
    if (parent == null) return Future<bool>.value(false);
    return _submit(
      body: body,
      pin: (
        pageNumber: parent.pageNumber,
        normX: parent.normX,
        normY: parent.normY,
      ),
      parentId: parentId,
    );
  }

  Future<bool> _submit({
    required String body,
    required ({int pageNumber, double normX, double normY}) pin,
    String? parentId,
    bool? isPinned,
  }) async {
    if (_ownerDocumentId != null) {
      return false; // owner không gửi được (không token)
    }
    final String trimmed = body.trim();
    if (trimmed.isEmpty) return false;
    try {
      await _repo.addComment(
        _token,
        pageNumber: pin.pageNumber,
        normX: pin.normX,
        normY: pin.normY,
        authorName: authorName,
        body: trimmed,
        parentId: parentId,
        isPinned: isPinned ?? parentId == null,
      );
      await refreshComments();
      state = state.copyWith(pendingPin: null, commentError: null);
      return true;
    } on Exception catch (e) {
      state = state.copyWith(commentError: e.toString());
      return false;
    }
  }

  /// Xóa comment — chỉ chủ tài liệu (FR-4.7); người nhận không có quyền.
  Future<bool> deleteComment(String commentId) async {
    final String? documentId = _ownerDocumentId;
    if (documentId == null) return false;
    try {
      await _repo.deleteOwnerComment(documentId, commentId);
      await refreshComments();
      return true;
    } on Exception catch (e) {
      state = state.copyWith(commentError: e.toString());
      return false;
    }
  }

  Future<void> refreshComments() async {
    if (_loadingComments || state.status != SharedViewStatus.ready) return;
    _loadingComments = true;
    try {
      final List<SharedComment>? fresh = _ownerDocumentId != null
          ? await _repo.listOwnerComments(_ownerDocumentId!)
          : await _tryComments();
      if (fresh != null) state = state.copyWith(comments: fresh);
    } on Exception {
      // Giữ danh sách cũ khi poll gặp lỗi mạng tạm thời.
    } finally {
      _loadingComments = false;
    }
  }

  // -- Highlight ------------------------------------------------------------

  /// Sidebar nhấn vào comment → viewer nhảy trang + nhấp nháy pin (FR-6.2).
  void highlightComment(String commentId) {
    state = state.copyWith(highlightCommentId: commentId);
  }

  void clearHighlight() {
    state = state.copyWith(highlightCommentId: null);
  }
}

final NotifierProvider<SharedViewController, SharedViewState>
sharedViewProvider = NotifierProvider<SharedViewController, SharedViewState>(
  SharedViewController.new,
);
