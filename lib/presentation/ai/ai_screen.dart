import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart';
import 'ai_chat_screen.dart';
import 'ai_ocr_screen.dart';
import 'ai_providers.dart';
import 'ai_translate_screen.dart';
import '../forms/forms_screen.dart';

class AiScreen extends ConsumerWidget {
  const AiScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final int index = ref.watch(aiToolProvider);
    // Màu nhấn theo từng công cụ (spec: Chat violet, OCR xanh dương, Dịch xanh lá)
    final List<(String, String, IconData, Color)> tools =
        <(String, String, IconData, Color)>[
          (
            'OCR & Word',
            'Extract text and export',
            Icons.document_scanner_outlined,
            AppColors.info,
          ),
          (
            'AI Chat',
            'Ask questions about files',
            Icons.forum_outlined,
            AppColors.aiPrimary,
          ),
          (
            'Translate',
            'Translate selected text',
            Icons.translate_outlined,
            AppColors.success,
          ),
          (
            'Form',
            'Add company logo to document templates',
            Icons.description_outlined,
            AppColors.warning,
          ),
        ];
    final List<Widget> pages = <Widget>[
      const AiOcrScreen(),
      const AiChatScreen(),
      const AiTranslateScreen(),
      const FormsScreen(),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(28, 28, 28, 8),
          child: Text(
            'AI Center',
            style: Theme.of(context).textTheme.headlineSmall
                ?.copyWith(fontWeight: FontWeight.w800),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: Text(
            'Choose a tool to start working with your documents.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ),
        const SizedBox(height: 16),
        SizedBox(
          height: 176,
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: 28),
            scrollDirection: Axis.horizontal,
            itemCount: tools.length,
            separatorBuilder: (_, _) => const SizedBox(width: 12),
            itemBuilder: (BuildContext context, int i) {
              final (
                String title,
                String subtitle,
                IconData icon,
                Color color,
              ) = tools[i];
              final bool selected = index == i;
              return SizedBox(
                width: 250,
                child: Card(
                  elevation: selected ? 2 : 0,
                  color: selected
                      ? color.withValues(alpha: 0.10)
                      : Theme.of(context).colorScheme.surface,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                    side: BorderSide(
                      color: selected
                          ? color
                          : Theme.of(context).colorScheme.outline,
                      width: selected ? 1.5 : 1,
                    ),
                  ),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(16),
                    onTap: () => ref.read(aiToolProvider.notifier).setTool(i),
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Container(
                            width: 42,
                            height: 42,
                            decoration: BoxDecoration(
                              color: color.withValues(alpha: 0.14),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Icon(icon, color: color),
                          ),
                          const Spacer(),
                          Text(
                            title,
                            style: TextStyle(
                              fontWeight: FontWeight.w800,
                              fontSize: 15,
                              color: selected
                                  ? color
                                  : Theme.of(context).colorScheme.onSurface,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            subtitle,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
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
        const SizedBox(height: 8),
        Expanded(
          child: IndexedStack(index: index, children: pages),
        ),
      ],
    );
  }
}
