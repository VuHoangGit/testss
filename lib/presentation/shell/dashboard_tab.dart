/// Tab tổng quan (Dashboard) — Sprint 1 là khung chào mừng; Sprint 2 sẽ thay
/// bằng thống kê tài liệu thật.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/user.dart';

class DashboardTab extends ConsumerWidget {
  const DashboardTab({super.key, required this.user});

  final User user;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: <Widget>[
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(
              children: <Widget>[
                CircleAvatar(radius: 28, child: Text(_initial, style: const TextStyle(fontSize: 22))),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        'Xin chào, ${user.name ?? user.email}',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 4),
                      Text(user.email, style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Bắt đầu dùng DocuVault', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                const Text(
                  '• Mở tab "Tài liệu" để tải lên và quản lý file\n'
                  '• Tạo thư mục để sắp xếp\n'
                  '• Dùng công cụ PDF: gộp, tách trang, mật khẩu',
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  String get _initial {
    final String? name = user.name;
    if (name != null && name.trim().isNotEmpty) {
      return name.trim().characters.first.toUpperCase();
    }
    return user.email.isEmpty ? '?' : user.email[0].toUpperCase();
  }
}
