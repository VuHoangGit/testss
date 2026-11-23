import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:docvaultproject/domain/entities/document_entities.dart';
import 'package:docvaultproject/domain/entities/share_entities.dart';
import 'package:docvaultproject/domain/repositories/share_repository.dart';
import 'package:docvaultproject/presentation/shared/share_dialog.dart';
import 'package:docvaultproject/presentation/shared/share_providers.dart';
import 'package:docvaultproject/presentation/shared/shared_view_screen.dart';

class _FakeShareRepository implements ShareRepository {
  _FakeShareRepository({
    this.deadLink = false,
    this.permission = 'view',
    List<SharedComment> comments = const <SharedComment>[],
  }) : comments = List<SharedComment>.of(comments);

  final bool deadLink;
  final String permission;
  final List<SharedComment> comments;

  int createCalls = 0;

  final ShareLink createdLink = ShareLink(
    id: 'share-1',
    permission: 'view',
    isActive: true,
    viewCount: 0,
    createdAt: DateTime(2026, 1, 1),
    shareUrl: 'http://localhost:53123/?share=test-token',
  );

  @override
  Future<ShareLink> createShare(
    String documentId, {
    required String permission,
    int? expiresInHours,
  }) async {
    createCalls++;
    return createdLink;
  }

  @override
  Future<List<ShareLink>> listShares(String documentId) async => <ShareLink>[];

  @override
  Future<void> revokeShare(String documentId, String shareId) async {}

  @override
  Future<List<OwnerSharedComment>> listOwnerComments(String documentId) async =>
      <OwnerSharedComment>[];

  @override
  Future<void> deleteOwnerComment(String documentId, String commentId) async {}

  @override
  Future<SharedDocumentMeta> getSharedMeta(String token) async {
    if (deadLink) throw Exception('Link không tồn tại hoặc đã hết hạn');
    return SharedDocumentMeta(
      fileName: 'bao-cao.pdf',
      mimeType: 'application/pdf',
      sizeBytes: 4,
      pageCount: 1,
      permission: permission,
      ownerName: 'Chủ tài liệu',
    );
  }

  @override
  Future<Uint8List> downloadSharedFile(String token) async =>
      Uint8List.fromList(<int>[1, 2, 3, 4]);

  @override
  Future<List<SharedComment>> listComments(String token) async => comments;

  @override
  Future<SharedComment> addComment(
    String token, {
    required int pageNumber,
    required double normX,
    required double normY,
    required String authorName,
    required String body,
    String? parentId,
    bool isPinned = true,
  }) async {
    final SharedComment comment = SharedComment(
      id: 'comment-${comments.length + 1}',
      pageNumber: pageNumber,
      normX: normX,
      normY: normY,
      authorName: authorName.trim().isEmpty ? 'Khách' : authorName,
      body: body,
      parentId: parentId,
      isPinned: isPinned,
      createdAt: DateTime(2026, 1, 1),
    );
    comments.add(comment);
    return comment;
  }
}

DocumentItem _document() => DocumentItem(
  id: 'document-1',
  name: 'bao-cao.pdf',
  mimeType: 'application/pdf',
  sizeBytes: 4,
  pageCount: 1,
  createdAt: DateTime(2026, 1, 1),
);

Widget _withRepository(_FakeShareRepository repository, Widget child) =>
    ProviderScope(
      overrides: <Override>[
        shareRepositoryProvider.overrideWithValue(repository),
      ],
      child: MaterialApp(home: Scaffold(body: child)),
    );

void main() {
  testWidgets('share dialog creates and displays the share URL', (
    WidgetTester tester,
  ) async {
    final _FakeShareRepository repository = _FakeShareRepository();
    await tester.pumpWidget(
      _withRepository(
        repository,
        Builder(
          builder: (BuildContext context) => Consumer(
            builder: (BuildContext context, WidgetRef ref, Widget? child) =>
                ElevatedButton(
                  onPressed: () => showShareDialog(context, ref, _document()),
                  child: const Text('open'),
                ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tạo link'));
    await tester.pumpAndSettle();

    expect(repository.createCalls, 1);
    expect(
      find.textContaining('http://localhost:53123/?share=test-token'),
      findsOneWidget,
    );
    expect(find.text('Sao chép'), findsOneWidget);
    String? clipboard;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (MethodCall call) async {
        if (call.method == 'Clipboard.setData') {
          clipboard =
              (call.arguments as Map<dynamic, dynamic>)['text'] as String;
        }
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );

    await tester.ensureVisible(find.byIcon(Icons.copy));
    await tester.tap(find.byIcon(Icons.copy));
    await tester.pump();
    expect(clipboard, 'http://localhost:53123/?share=test-token');
    expect(find.text('Đã sao chép'), findsOneWidget);
  });

  testWidgets(
    'SharedView displays the owner banner and keeps the viewer read-only',
    (WidgetTester tester) async {
      final _FakeShareRepository repository = _FakeShareRepository();
      await tester.pumpWidget(
        _withRepository(
          repository,
          SharedViewScreen(
            token: 'test-token',
            previewPdfBuilder: (BuildContext context, Uint8List bytes) =>
                const ColoredBox(color: Colors.white),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Được chia sẻ bởi Chủ tài liệu'), findsOneWidget);
      expect(
        find.text('Tài liệu được chia sẻ bởi Chủ tài liệu'),
        findsOneWidget,
      );
      expect(find.byTooltip('Ghim bình luận'), findsNothing);
      expect(find.byTooltip('Bình luận'), findsNothing);
    },
  );

  testWidgets('SharedView lists shared comments and their PDF pages', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _withRepository(
        _FakeShareRepository(
          permission: 'comment',
          comments: <SharedComment>[
            SharedComment(
              id: 'comment-1',
              pageNumber: 3,
              normX: 0.25,
              normY: 0.75,
              authorName: 'Minh Anh',
              body: 'Cần kiểm tra lại đoạn này',
              createdAt: DateTime(2026, 1, 1),
            ),
          ],
        ),
        SharedViewScreen(token: 'test-token', previewPinLayer: true),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Minh Anh'), findsOneWidget);
    expect(find.text('Cần kiểm tra lại đoạn này'), findsOneWidget);
    expect(find.textContaining('trang 3'), findsOneWidget);
    expect(find.text('Bình luận (1)'), findsOneWidget);
    final double viewerWidth = tester
        .getSize(find.byKey(const Key('shared-pin-preview')))
        .width;
    expect(tester.getCenter(find.byType(CommentPin)), isNotNull);
    final Offset pinCenter = tester.getCenter(find.byType(CommentPin));
    expect(pinCenter.dx, viewerWidth * 0.25);
    expect(pinCenter.dy, greaterThan(0));

    expect(find.byTooltip('Đóng bình luận'), findsOneWidget);
  });

  test(
    'pin position follows normalized coordinates when zooming and panning',
    () {
      const Map<int, Size> pages = <int, Size>{
        1: Size(200, 400),
        2: Size(200, 400),
        3: Size(200, 400),
      };
      final Offset base = pinOffsetForPage(
        pageNumber: 3,
        normX: 0.25,
        normY: 0.75,
        pageSizes: pages,
        viewportWidth: 200,
        zoom: 1,
        scrollOffset: Offset.zero,
        pageSpacing: 4,
      );
      expect(base, const Offset(50, 1108));

      final Offset zoomed = pinOffsetForPage(
        pageNumber: 3,
        normX: 0.25,
        normY: 0.75,
        pageSizes: pages,
        viewportWidth: 200,
        zoom: 2,
        scrollOffset: Offset.zero,
        pageSpacing: 4,
      );
      expect(zoomed.dx, base.dx * 2);
      expect(zoomed.dy, base.dy * 2);

      final Offset panned = pinOffsetForPage(
        pageNumber: 3,
        normX: 0.25,
        normY: 0.75,
        pageSizes: pages,
        viewportWidth: 200,
        zoom: 2,
        scrollOffset: const Offset(20, 50),
        pageSpacing: 4,
      );
      expect(panned, zoomed - const Offset(20, 50));
    },
  );

  testWidgets('CommentPin reports taps and displays its thread number', (
    WidgetTester tester,
  ) async {
    int taps = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: CommentPin(number: 1, onTap: () => taps++)),
      ),
    );
    await tester.tap(find.byType(CommentPin));
    expect(taps, 1);
    expect(find.text('1'), findsOneWidget);
  });

  testWidgets('SharedView shows the dead-link screen for a 404 link', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      _withRepository(
        _FakeShareRepository(deadLink: true),
        const SharedViewScreen(token: 'dead-token'),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Link không tồn tại hoặc đã hết hạn'), findsOneWidget);
    expect(find.text('Về trang chủ'), findsOneWidget);
  });
}
