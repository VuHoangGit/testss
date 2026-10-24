/// Tab đang mở của Shell — đặt trong provider để voice executor chuyển tab
/// được từ bên ngoài (trước đây là setState cục bộ trong ShellScreen).
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Index tab: 0 Tổng quan · 1 Tài liệu · 2 AI · 3 Tài khoản.
const List<String> shellTabIds = <String>['dashboard', 'documents', 'ai', 'account'];

final NotifierProvider<ShellTabController, int> shellTabProvider =
    NotifierProvider<ShellTabController, int>(ShellTabController.new);

class ShellTabController extends Notifier<int> {
  @override
  int build() => 0;

  void setTab(int index) {
    if (index >= 0 && index < shellTabIds.length) {
      state = index;
    }
  }

  /// Trả index theo id tab backend trả về ('documents'…), null nếu không khớp.
  int? indexById(String tabId) {
    final int index = shellTabIds.indexOf(tabId);
    return index < 0 ? null : index;
  }
}
