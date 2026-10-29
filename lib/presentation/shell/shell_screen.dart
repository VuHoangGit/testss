/// Main application shell: Overview / Files / AI Center / Account.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/user.dart';
import '../documents/documents_screen.dart';
import '../ai/ai_screen.dart';
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

class _DesktopSidebar extends StatelessWidget {
  const _DesktopSidebar({
    required this.index,
    required this.destinations,
    required this.onSelected,
    required this.email,
  });

  final int index;
  final List<(String, IconData)> destinations;
  final ValueChanged<int> onSelected;
  final String email;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Container(
      width: 248,
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border(right: BorderSide(color: colors.outlineVariant)),
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
                      colors: <Color>[colors.primary, const Color(0xFF7C3AED)],
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
                  style: Theme.of(context).textTheme.titleLarge
                      ?.copyWith(fontWeight: FontWeight.w800),
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
              onTap: () => onSelected(1),
            ),
            _NavItem(
              title: 'Favorites',
              icon: Icons.star_outline_rounded,
              onTap: () => onSelected(1),
            ),
            const Spacer(),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: colors.primaryContainer.withValues(alpha: 0.45),
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
                      ),
                    ),
                  ),
                  const Icon(Icons.more_horiz, size: 18),
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
      color: Theme.of(context).colorScheme.outline,
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
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Material(
        color: selected ? colors.primaryContainer : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: onTap,
          child: SizedBox(
            height: 42,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Row(
                children: <Widget>[
                  Icon(
                    icon,
                    size: 20,
                    color: selected ? colors.primary : colors.onSurfaceVariant,
                  ),
                  const SizedBox(width: 10),
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                      color: selected
                          ? colors.primary
                          : colors.onSurfaceVariant,
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

class _TopBar extends StatelessWidget {
  const _TopBar({required this.title, required this.userEmail});
  final String title;
  final String userEmail;

  @override
  Widget build(BuildContext context) {
    final bool compact = MediaQuery.sizeOf(context).width < 760;
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Container(
      // Topbar 72px desktop (spec); mobile hạ còn 64px cho nội dung nhiều chỗ hơn
      height: compact ? 64 : 72,
      padding: EdgeInsets.symmetric(horizontal: compact ? 16 : 28),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border(bottom: BorderSide(color: colors.outlineVariant)),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              title,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.titleLarge
                  ?.copyWith(fontWeight: FontWeight.w700),
            ),
          ),
          // Search thu gọn thành icon khi màn hẹp — tránh overflow
          if (compact)
            IconButton(
              onPressed: () {},
              icon: const Icon(Icons.search),
              tooltip: 'Search documents',
            )
          else
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: SizedBox(
                width: 320,
                height: 40,
                child: TextField(
                  decoration: InputDecoration(
                    hintText: 'Search documents...',
                    prefixIcon: const Icon(Icons.search, size: 19),
                    isDense: true,
                    filled: true,
                    fillColor: colors.surfaceContainerHighest,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
              ),
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
              userEmail.isEmpty ? '?' : userEmail[0].toUpperCase(),
              style: TextStyle(
                color: colors.primary,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
