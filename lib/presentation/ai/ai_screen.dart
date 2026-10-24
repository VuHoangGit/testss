import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'ai_chat_screen.dart';
import 'ai_ocr_screen.dart';
import 'ai_providers.dart';
import 'ai_translate_screen.dart';

class AiScreen extends ConsumerWidget {
  const AiScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final int index = ref.watch(aiToolProvider);
    const List<(String, String, IconData)> tools = <(String, String, IconData)>[
      ('OCR & Word', 'Quét tài liệu và xuất Word', Icons.document_scanner_outlined),
      ('Chat với AI', 'Hỏi đáp theo tài liệu', Icons.forum_outlined),
      ('Dịch vùng chọn', 'Dịch đoạn văn nhanh chóng', Icons.translate_outlined),
    ];
    final List<Widget> pages = <Widget>[
      const AiOcrScreen(),
      const AiChatScreen(),
      const AiTranslateScreen(),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 8),
          child: Text(
            'Trung tâm AI',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Text(
            'Chọn một công cụ để bắt đầu làm việc với tài liệu của bạn.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ),
        const SizedBox(height: 16),
        SizedBox(
          height: 86,
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            scrollDirection: Axis.horizontal,
            itemCount: tools.length,
            separatorBuilder: (_, _) => const SizedBox(width: 12),
            itemBuilder: (BuildContext context, int i) {
              final (String title, String subtitle, IconData icon) = tools[i];
              final bool selected = index == i;
              return SizedBox(
                width: 230,
                child: Card(
                  elevation: selected ? 2 : 0,
                  color: selected
                      ? Theme.of(context).colorScheme.primaryContainer
                      : Theme.of(context).colorScheme.surfaceContainerHighest,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(12),
                    onTap: () => ref.read(aiToolProvider.notifier).setTool(i),
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Row(
                        children: <Widget>[
                          Icon(icon, color: selected
                              ? Theme.of(context).colorScheme.primary
                              : null),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: <Widget>[
                                Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
                                const SizedBox(height: 3),
                                Text(subtitle, maxLines: 1, overflow: TextOverflow.ellipsis),
                              ],
                            ),
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
        const SizedBox(height: 8),
        Expanded(
          child: IndexedStack(index: index, children: pages),
        ),
      ],
    );
  }
}
