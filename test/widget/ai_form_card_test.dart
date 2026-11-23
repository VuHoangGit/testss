import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:docvaultproject/presentation/ai/ai_screen.dart';

void main() {
  testWidgets('AI Center shows Form as the fourth tool card', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: Scaffold(body: AiScreen())),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('AI Center'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Form'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(find.text('Form'), findsOneWidget);
    expect(find.text('Add company logo to document templates'), findsOneWidget);

    await tester.tap(find.text('Form'));
    await tester.pumpAndSettle();

    expect(find.text('Biểu mẫu'), findsOneWidget);
    expect(find.text('Chọn biểu mẫu'), findsOneWidget);
  });
}
