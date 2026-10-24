/// Bộ khung ứng dụng: Dashboard / Tài liệu / AI / Tài khoản.
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
    final ShellTabController tabController =
        ref.read(shellTabProvider.notifier);
    final bool wide = MediaQuery.sizeOf(context).width >= 900;
    final List<Widget> tabs = <Widget>[
      DashboardTab(user: widget.session.user),
      const DocumentsScreen(),
      const AiScreen(),
      AccountTab(userEmail: widget.session.user.email),
    ];
    const List<(String, IconData)> destinations = <(String, IconData)>[
      ('Tổng quan', Icons.space_dashboard_outlined),
      ('Tài liệu', Icons.folder_outlined),
      ('AI', Icons.auto_awesome_outlined),
      ('Tài khoản', Icons.person_outline),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(
          '${destinations[index].$1} · DocuVault',
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        actions: <Widget>[const VoiceMicButton()],
      ),
      body: Column(
        children: <Widget>[
          const VoicePanel(),
          Expanded(
            child: Row(
              children: <Widget>[
                if (wide)
                  NavigationRail(
                    selectedIndex: index,
                    onDestinationSelected: tabController.setTab,
                    labelType: NavigationRailLabelType.all,
                    destinations: <NavigationRailDestination>[
                      for (final (String, IconData) d in destinations)
                        NavigationRailDestination(
                          icon: Icon(d.$2),
                          label: Text(d.$1),
                        ),
                    ],
                  ),
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
