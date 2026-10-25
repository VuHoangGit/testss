import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/user.dart';
import '../../domain/entities/document_entities.dart';
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
    final recent = documents.take(4).toList();
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
      children: <Widget>[
        Row(
          children: <Widget>[
            CircleAvatar(
              radius: 24,
              backgroundColor: const Color(0xFFE0E7FF),
              child: Text(_initial, style: const TextStyle(
                  color: Color(0xFF4F46E5), fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text('Good morning, ${user.name ?? 'Hoang'}',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text('Here is what is happening with your workspace',
                      style: TextStyle(color: Theme.of(context).colorScheme.outline)),
                ]),
            ),
            IconButton(onPressed: () {}, icon: const Icon(Icons.notifications_none),
                tooltip: 'Notifications'),
          ],
        ),
        const SizedBox(height: 24),
        Text('Quick actions', style: Theme.of(context).textTheme.titleMedium
            ?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        SizedBox(
          height: 112,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: 3,
            separatorBuilder: (_, _) => const SizedBox(width: 12),
            itemBuilder: (_, int index) {
              final actions = <(String, String, IconData, Color)>[
                ('Upload file', 'Add to vault', Icons.upload_file, const Color(0xFFE0E7FF)),
                ('Scan document', 'Capture with AI', Icons.document_scanner_outlined, const Color(0xFFDCFCE7)),
                ('Merge PDFs', 'Combine files', Icons.merge_type, const Color(0xFFFFEDD5)),
              ];
              final action = actions[index];
              return SizedBox(
                width: 150,
                child: Card(
                  child: InkWell(
                    borderRadius: BorderRadius.circular(12),
                    onTap: () {
                      if (index == 0) {
                        ref.read(shellTabProvider.notifier).setTab(1);
                      } else if (index == 1) {
                        ref.read(shellTabProvider.notifier).setTab(2);
                      }
                    },
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          CircleAvatar(radius: 18, backgroundColor: action.$4,
                              child: Icon(action.$3, size: 19, color: const Color(0xFF4F46E5))),
                          const Spacer(),
                          Text(action.$1, style: const TextStyle(fontWeight: FontWeight.w700)),
                          Text(action.$2, style: TextStyle(fontSize: 11,
                              color: Theme.of(context).colorScheme.outline)),
                        ]),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(height: 28),
        Row(children: <Widget>[
          Expanded(child: Text('Recent documents', style: Theme.of(context).textTheme.titleMedium
              ?.copyWith(fontWeight: FontWeight.w700))),
          TextButton(onPressed: () => ref.read(shellTabProvider.notifier).setTab(1),
              child: const Text('View all')),
        ]),
        const SizedBox(height: 4),
        if (recent.isEmpty)
          const Card(child: Padding(padding: EdgeInsets.all(24),
              child: Center(child: Text('No documents yet. Upload your first file.'))))
        else
          for (final doc in recent)
            Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                leading: _FileIcon(isPdf: doc.isPdf, isImage: doc.isImage),
                title: Text(doc.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                subtitle: Text(_size(doc.sizeBytes)),
                trailing: const Icon(Icons.chevron_right, size: 20),
                onTap: () => ref.read(shellTabProvider.notifier).setTab(1),
              ),
            ),
      ],
    );
  }

  String get _initial => (user.name?.trim().isNotEmpty == true
      ? user.name!.trim()[0] : user.email[0]).toUpperCase();

  static String _size(int bytes) => bytes >= 1024 * 1024
      ? '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB'
      : '${(bytes / 1024).toStringAsFixed(0)} KB';
}

class _FileIcon extends StatelessWidget {
  const _FileIcon({required this.isPdf, required this.isImage});
  final bool isPdf;
  final bool isImage;
  @override
  Widget build(BuildContext context) => CircleAvatar(
    backgroundColor: isPdf ? const Color(0xFFFEE2E2) : const Color(0xFFE0E7FF),
    child: Icon(isPdf ? Icons.picture_as_pdf : isImage ? Icons.image_outlined : Icons.description_outlined,
        color: isPdf ? const Color(0xFFDC2626) : const Color(0xFF4F46E5), size: 20),
  );
}
