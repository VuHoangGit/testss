import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart';
import '../../domain/entities/user.dart';
import '../../domain/entities/document_entities.dart';
import '../ai/ai_providers.dart';
import '../documents/documents_providers.dart';
import 'shell_providers.dart';

class DashboardTab extends ConsumerWidget {
  const DashboardTab({super.key, required this.user});

  final User user;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final List<DocumentItem> documents =
        ref.watch(documentsControllerProvider).value?.documents ??
        const <DocumentItem>[];
    final List<DocumentItem> recent = documents.take(5).toList();
    final int totalBytes = documents.fold(
      0,
      (int sum, DocumentItem d) => sum + d.sizeBytes,
    );

    return ListView(
      padding: const EdgeInsets.fromLTRB(28, 28, 28, 40),
      children: <Widget>[
        Row(
          children: <Widget>[
            CircleAvatar(
              radius: 24,
              backgroundColor: Theme.of(context).colorScheme.primaryContainer,
              child: Text(
                _initial,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.primary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'Good morning, ${user.name ?? 'Hoang'}',
                    style: Theme.of(context).textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Here is what is happening with your workspace today.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            FilledButton.icon(
              onPressed: () => ref.read(shellTabProvider.notifier).setTab(1),
              icon: const Icon(Icons.upload_file_outlined, size: 18),
              label: const Text('Upload document'),
            ),
          ],
        ),
        const SizedBox(height: 28),
        LayoutBuilder(
          builder: (BuildContext context, BoxConstraints constraints) {
            final int columns = constraints.maxWidth > 900
                ? 4
                : constraints.maxWidth > 560
                ? 2
                : 1;
            return GridView.count(
              crossAxisCount: columns,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisSpacing: 16,
              mainAxisSpacing: 16,
              childAspectRatio: 2.25,
              children: <Widget>[
                _MetricCard(
                  label: 'Total files',
                  value: '${documents.length}',
                  detail: documents.isEmpty
                      ? 'Nothing uploaded yet'
                      : 'Across all folders',
                  icon: Icons.description_outlined,
                  color: Theme.of(context).colorScheme.primary,
                ),
                _MetricCard(
                  label: 'Storage used',
                  value: _size(totalBytes),
                  detail: documents.isEmpty
                      ? 'No files yet'
                      : 'Sum of all files',
                  icon: Icons.cloud_outlined,
                  color: AppColors.warning,
                ),
                _MetricCard(
                  label: 'AI queries',
                  value: '—',
                  detail: 'Coming soon',
                  icon: Icons.auto_awesome_outlined,
                  color: AppColors.aiPrimary,
                ),
                _MetricCard(
                  label: 'Shared files',
                  value: '—',
                  detail: 'Coming soon',
                  icon: Icons.people_outline,
                  color: AppColors.success,
                ),
              ],
            );
          },
        ),
        const SizedBox(height: 32),
        Text(
          'Quick actions',
          style: Theme.of(context).textTheme.titleMedium
              ?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 12),
        SizedBox(
          height: 124,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: 3,
            separatorBuilder: (_, _) => const SizedBox(width: 12),
            itemBuilder: (_, int index) {
              final actions = <(String, String, IconData, Color)>[
                (
                  'Upload file',
                  'Add to your vault',
                  Icons.upload_file,
                  Theme.of(context).colorScheme.primaryContainer,
                ),
                (
                  'Scan document',
                  'Extract text with OCR',
                  Icons.document_scanner_outlined,
                  const Color(0xFFDBEAFE),
                ),
                (
                  'Ask AI',
                  'Chat with your documents',
                  Icons.forum_outlined,
                  const Color(0xFFDCFCE7),
                ),
              ];
              final (String, String, IconData, Color) action = actions[index];
              return SizedBox(
                width: 210,
                child: Card(
                  child: InkWell(
                    borderRadius: BorderRadius.circular(16),
                    onTap: () {
                      final ShellTabController tabs = ref.read(
                        shellTabProvider.notifier,
                      );
                      if (index == 0) {
                        tabs.setTab(1);
                      } else {
                        // Scan → OCR, Ask AI → Chat: mở đúng công cụ trong AI Center
                        tabs.setTab(2);
                        ref
                            .read(aiToolProvider.notifier)
                            .setTool(index == 1 ? 0 : 1);
                      }
                    },
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          CircleAvatar(
                            radius: 17,
                            backgroundColor: action.$4,
                            child: Icon(
                              action.$3,
                              size: 19,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            action.$1,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          Text(
                            action.$2,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(height: 32),
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                'Recent documents',
                style: Theme.of(context).textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
            ),
            TextButton(
              onPressed: () => ref.read(shellTabProvider.notifier).setTab(1),
              child: const Text('View all'),
            ),
          ],
        ),
        const SizedBox(height: 4),
        if (recent.isEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 24),
              child: Column(
                children: <Widget>[
                  Icon(
                    Icons.cloud_upload_outlined,
                    size: 40,
                    color: Theme.of(context).colorScheme.outline,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'No documents yet',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Upload your first file — PDF, image or text — to get started.',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          )
        else
          for (final DocumentItem doc in recent)
            Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                leading: _FileIcon(isPdf: doc.isPdf, isImage: doc.isImage),
                title: Text(
                  doc.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: Text(_size(doc.sizeBytes)),
                trailing: const Icon(Icons.chevron_right, size: 20),
                onTap: () => ref.read(shellTabProvider.notifier).setTab(1),
              ),
            ),
      ],
    );
  }

  String get _initial =>
      (user.name?.trim().isNotEmpty == true
              ? user.name!.trim()[0]
              : user.email[0])
          .toUpperCase();

  static String _size(int bytes) => bytes >= 1024 * 1024
      ? '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB'
      : '${(bytes / 1024).toStringAsFixed(0)} KB';
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.label,
    required this.value,
    required this.detail,
    required this.icon,
    required this.color,
  });

  final String label;
  final String value;
  final String detail;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  Text(label, style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(height: 5),
                  Text(
                    value,
                    style: Theme.of(context).textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    detail,
                    style: TextStyle(
                      color: color,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: color, size: 20),
            ),
          ],
        ),
      ),
    );
  }
}

class _FileIcon extends StatelessWidget {
  const _FileIcon({required this.isPdf, required this.isImage});
  final bool isPdf;
  final bool isImage;
  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return CircleAvatar(
      backgroundColor: isPdf ? colors.errorContainer : colors.primaryContainer,
      child: Icon(
        isPdf
            ? Icons.picture_as_pdf
            : isImage
            ? Icons.image_outlined
            : Icons.description_outlined,
        color: isPdf ? colors.error : colors.primary,
        size: 20,
      ),
    );
  }
}
