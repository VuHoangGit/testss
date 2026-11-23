/// Main application shell: Overview / Files / AI Center / Account.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart' show AppColors;
import '../../domain/entities/document_entities.dart';
import '../../domain/entities/user.dart';
import '../ai/ai_providers.dart';
import '../ai/ai_screen.dart';
import '../documents/documents_controller.dart';
import '../documents/documents_providers.dart';
import '../documents/documents_screen.dart';
import '../documents/viewer_opener.dart';
import '../voice/voice_panel.dart';
import 'account_tab.dart';
import 'dashboard_tab.dart';
import 'shell_providers.dart';
import '../theme/theme_toggle_button.dart';

class ShellScreen extends ConsumerStatefulWidget {
  const ShellScreen({super.key, required this.session});

  final AuthSession session;

  @override
  ConsumerState<ShellScreen> createState() => _ShellScreenState();
}

class _ShellScreenState extends ConsumerState<ShellScreen> {
  /// TOOLS → Recent/Favorites: sang tab Files và bật bộ lọc tương ứng.
  void _openDocumentsView(DocumentsViewFilter filter) {
    ref.read(shellTabProvider.notifier).setTab(1);
    unawaited(
      ref.read(documentsControllerProvider.notifier).setViewFilter(filter),
    );
  }

  @override
  Widget build(BuildContext context) {
    final int index = ref.watch(shellTabProvider);
    final ShellTabController tabController = ref.read(
      shellTabProvider.notifier,
    );
    final bool wide = MediaQuery.sizeOf(context).width >= 900;
    final List<Widget> tabs = <Widget>[
      DashboardTab(user: widget.session.user),
      const DocumentsScreen(),
      const AiScreen(),
      AccountTab(userEmail: widget.session.user.email),
    ];
    const List<(String, IconData)> destinations = <(String, IconData)>[
      ('Overview', Icons.space_dashboard_outlined),
      ('Files', Icons.folder_outlined),
      ('AI Center', Icons.auto_awesome_outlined),
      ('Account', Icons.person_outline),
    ];

    return Scaffold(
      body: Row(
        children: <Widget>[
          if (wide)
            _DesktopSidebar(
              index: index,
              destinations: destinations,
              onSelected: tabController.setTab,
              onOpenView: _openDocumentsView,
              email: widget.session.user.email,
            ),
          Expanded(
            child: Column(
              children: <Widget>[
                _TopBar(
                  title: destinations[index].$1,
                  userEmail: widget.session.user.email,
                ),
                const VoicePanel(),
                Expanded(
                  child: IndexedStack(index: index, children: tabs),
                ),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: wide
          ? null
          : NavigationBar(
              selectedIndex: index,
              onDestinationSelected: tabController.setTab,
              destinations: <Widget>[
                for (final (String, IconData) d in destinations)
                  NavigationDestination(icon: Icon(d.$2), label: d.$1),
              ],
            ),
    );
  }
}

class _DesktopSidebar extends ConsumerWidget {
  const _DesktopSidebar({
    required this.index,
    required this.destinations,
    required this.onSelected,
    required this.onOpenView,
    required this.email,
  });

  final int index;
  final List<(String, IconData)> destinations;
  final ValueChanged<int> onSelected;
  final ValueChanged<DocumentsViewFilter> onOpenView;
  final String email;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    // null-safe: provider lỗi mạng vẫn highlight đúng mặc định All
    final DocumentsViewFilter viewFilter =
        ref.watch(documentsControllerProvider).value?.viewFilter ??
        DocumentsViewFilter.all;
    // Sidebar navy đậm cố định (kiểu ảnh mẫu: rail tối, nội dung sáng)
    return Container(
      width: 248,
      decoration: const BoxDecoration(
        color: AppColors.sidebarBg,
        border: Border(right: BorderSide(color: AppColors.sidebarBorder)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: <Color>[colors.primary, const Color(0xFF3B82F6)],
                    ),
                    borderRadius: BorderRadius.circular(11),
                  ),
                  child: const Icon(
                    Icons.folder_special_rounded,
                    color: Colors.white,
                    size: 21,
                  ),
                ),
                const SizedBox(width: 10),
                Text(
                  'DocuVault',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 32),
            _sectionLabel(context, 'WORKSPACE'),
            const SizedBox(height: 8),
            for (int i = 0; i < destinations.length; i++)
              _NavItem(
                title: destinations[i].$1,
                icon: destinations[i].$2,
                selected: index == i,
                onTap: () => onSelected(i),
              ),
            const SizedBox(height: 24),
            _sectionLabel(context, 'TOOLS'),
            const SizedBox(height: 8),
            _NavItem(
              title: 'Recent',
              icon: Icons.schedule_outlined,
              selected: index == 1 && viewFilter == DocumentsViewFilter.recent,
              onTap: () => onOpenView(DocumentsViewFilter.recent),
            ),
            _NavItem(
              title: 'Favorites',
              icon: Icons.star_outline_rounded,
              selected:
                  index == 1 && viewFilter == DocumentsViewFilter.favorites,
              onTap: () => onOpenView(DocumentsViewFilter.favorites),
            ),
            const Spacer(),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(
                children: <Widget>[
                  CircleAvatar(
                    radius: 17,
                    backgroundColor: colors.primary,
                    foregroundColor: colors.onPrimary,
                    child: Text(email.isEmpty ? '?' : email[0].toUpperCase()),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      email,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
                      ),
                    ),
                  ),
                  const Icon(
                    Icons.more_horiz,
                    size: 18,
                    color: AppColors.sidebarMuted,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionLabel(BuildContext context, String label) => Text(
    label,
    style: Theme.of(context).textTheme.labelSmall?.copyWith(
      letterSpacing: 1.1,
      fontWeight: FontWeight.w700,
      color: AppColors.sidebarMuted,
    ),
  );
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.title,
    required this.icon,
    this.selected = false,
    required this.onTap,
  });
  final String title;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    // Pill trên nền navy: mục chọn = nền accent + chữ trắng (kiểu ảnh mẫu)
    final Color bg = selected ? AppColors.primary : Colors.transparent;
    final Color fg = selected ? Colors.white : AppColors.sidebarMuted;
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Material(
        color: bg,
        borderRadius: BorderRadius.circular(999),
        child: InkWell(
          borderRadius: BorderRadius.circular(999),
          onTap: onTap,
          child: SizedBox(
            height: 42,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14),
              child: Row(
                children: <Widget>[
                  Icon(icon, size: 20, color: fg),
                  const SizedBox(width: 10),
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                      color: fg,
                    ),
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

/// Topbar với ô search: gõ ≥ 2 ký tự (debounce 300ms) → gọi API tìm theo tên,
/// dropdown tối đa 8 kết quả dưới ô; chọn kết quả = đánh dấu đã mở + mở viewer.
class _TopBar extends ConsumerStatefulWidget {
  const _TopBar({required this.title, required this.userEmail});
  final String title;
  final String userEmail;

  @override
  ConsumerState<_TopBar> createState() => _TopBarState();
}

class _TopBarState extends ConsumerState<_TopBar> {
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  final LayerLink _layerLink = LayerLink();
  final OverlayPortalController _overlayController = OverlayPortalController();
  Timer? _debounce;
  List<DocumentItem> _results = const <DocumentItem>[];
  bool _searching = false;
  bool _expandedCompactSearch = false;

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _hideOverlay() {
    if (_overlayController.isShowing) {
      _overlayController.hide();
    }
  }

  void _onQueryChanged(String query) {
    _debounce?.cancel();
    final String q = query.trim();
    if (q.length < 2) {
      if (mounted) {
        setState(() => _results = const <DocumentItem>[]);
      }
      _hideOverlay();
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 300), () => _runSearch(q));
  }

  Future<void> _runSearch(String query) async {
    setState(() => _searching = true);
    try {
      final List<DocumentItem> docs = await ref
          .read(documentsRepositoryProvider)
          .listDocuments(search: query);
      if (!mounted) return;
      setState(() {
        _searching = false;
        _results = docs.take(8).toList(growable: false);
      });
      _overlayController.show();
    } on Exception {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _openResult(DocumentItem doc) async {
    _hideOverlay();
    _focusNode.unfocus();
    _searchController.clear();
    setState(() {
      _results = const <DocumentItem>[];
      _expandedCompactSearch = false;
    });
    // Đánh dấu đã mở (feed Recent) — không chặn việc mở viewer
    unawaited(
      ref.read(documentsControllerProvider.notifier).markOpened(doc.id),
    );
    try {
      await openDocumentViewer(
        repository: ref.read(documentsRepositoryProvider),
        aiRepository: ref.read(aiRepositoryProvider),
        doc: doc,
      );
    } on Exception catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(e.toString())));
      }
    }
  }

  Widget _buildField(BuildContext context, {required bool compactField}) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return CompositedTransformTarget(
      link: _layerLink,
      child: TextField(
        controller: _searchController,
        focusNode: _focusNode,
        onChanged: _onQueryChanged,
        decoration: InputDecoration(
          hintText: 'Search documents...',
          prefixIcon: const Icon(Icons.search, size: 19),
          suffixIcon: _searching
              ? const Padding(
                  padding: EdgeInsets.all(10),
                  child: SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                )
              : null,
          isDense: true,
          filled: true,
          fillColor: colors.surfaceContainerHighest,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(999),
            borderSide: BorderSide.none,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bool compact = MediaQuery.sizeOf(context).width < 760;
    final ColorScheme colors = Theme.of(context).colorScheme;
    return OverlayPortal(
      controller: _overlayController,
      overlayChildBuilder: (BuildContext ctx) =>
          _buildSearchOverlay(ctx, compact: compact),
      child: Container(
        // Topbar 72px desktop (spec); mobile hạ còn 64px cho nội dung nhiều chỗ hơn
        height: compact ? 64 : 72,
        padding: EdgeInsets.symmetric(horizontal: compact ? 16 : 28),
        decoration: BoxDecoration(
          color: colors.surface,
          border: Border(bottom: BorderSide(color: colors.outlineVariant)),
        ),
        child: Row(
          children: <Widget>[
            if (compact && !_expandedCompactSearch) ...<Widget>[
              Expanded(
                child: Text(
                  widget.title,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleLarge
                      ?.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
            ],
            // Search: desktop luôn hiện ô 320px; mobile bung từ icon (ánh xạ dropdown neo phải)
            if (!compact)
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: SizedBox(
                  width: 320,
                  height: 40,
                  child: _buildField(context, compactField: false),
                ),
              )
            else if (_expandedCompactSearch)
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: SizedBox(
                    height: 40,
                    child: _buildField(context, compactField: true),
                  ),
                ),
              )
            else
              IconButton(
                onPressed: () => setState(() => _expandedCompactSearch = true),
                icon: const Icon(Icons.search),
                tooltip: 'Search documents',
              ),
            const VoiceMicButton(),
            const ThemeToggleButton(),
            IconButton(
              onPressed: () {},
              icon: const Icon(Icons.notifications_none_rounded),
              tooltip: 'Notifications',
            ),
            CircleAvatar(
              radius: 16,
              backgroundColor: colors.primaryContainer,
              child: Text(
                widget.userEmail.isEmpty
                    ? '?'
                    : widget.userEmail[0].toUpperCase(),
                style: TextStyle(
                  color: colors.primary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Nội dung overlay dropdown kết quả search (neo dưới ô tìm kiếm).
  Widget _buildSearchOverlay(BuildContext context, {required bool compact}) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Stack(
      children: <Widget>[
        // Barrier: chạm ra ngoài dropdown để đóng
        Positioned.fill(
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {
              _hideOverlay();
              _focusNode.unfocus();
            },
          ),
        ),
        CompositedTransformFollower(
          link: _layerLink,
          targetAnchor: Alignment.bottomLeft,
          followerAnchor: compact ? Alignment.topRight : Alignment.topLeft,
          showWhenUnlinked: false,
          child: Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Material(
              elevation: 6,
              borderRadius: BorderRadius.circular(12),
              color: colors.surface,
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  maxWidth: 360,
                  maxHeight: 380,
                ),
                child: _results.isEmpty
                    ? const Padding(
                        padding: EdgeInsets.all(16),
                        child: Text('No documents found'),
                      )
                    : ListView.builder(
                        shrinkWrap: true,
                        itemCount: _results.length,
                        itemBuilder: (BuildContext itemCtx, int i) {
                          final DocumentItem doc = _results[i];
                          return ListTile(
                            dense: true,
                            leading: Icon(
                              doc.isPdf
                                  ? Icons.picture_as_pdf
                                  : doc.isImage
                                  ? Icons.image_outlined
                                  : Icons.description_outlined,
                              size: 20,
                              color: doc.isPdf ? colors.error : colors.primary,
                            ),
                            title: Text(
                              doc.name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            subtitle: Text(
                              doc.lastOpenedAt == null
                                  ? 'Not opened yet'
                                  : 'Opened ${_relativeTime(doc.lastOpenedAt!)}',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                            onTap: () => _openResult(doc),
                          );
                        },
                      ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  static String _relativeTime(DateTime time) {
    final Duration diff = DateTime.now().difference(time);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inHours < 1) return '${diff.inMinutes} min ago';
    if (diff.inDays < 1) return '${diff.inHours} h ago';
    return '${diff.inDays} d ago';
  }
}
