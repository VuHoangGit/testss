/// Dialog "Chia sẻ…" của chủ tài liệu (SRS FR-1): tạo link, danh sách link,
/// copy URL, thu hồi từng link.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/entities/document_entities.dart';
import '../../domain/entities/share_entities.dart';
import 'share_providers.dart';

/// Mở dialog chia sẻ; trả về true nếu có thay đổi (đã tạo/thu hồi link).
Future<bool> showShareDialog(BuildContext context, WidgetRef ref, DocumentItem doc) async {
  final bool? changed = await showDialog<bool>(
    context: context,
    builder: (BuildContext ctx) => _ShareDialog(doc: doc),
  );
  return changed == true;
}

class _ExpiryChoice {
  const _ExpiryChoice(this.label, this.hours);
  final String label;

  /// null = không hết hạn.
  final int? hours;
}

const List<_ExpiryChoice> _kExpiryChoices = <_ExpiryChoice>[
  _ExpiryChoice('1 ngày', 24),
  _ExpiryChoice('7 ngày', 24 * 7),
  _ExpiryChoice('30 ngày', 24 * 30),
  _ExpiryChoice('Không hết hạn', null),
];

class _ShareDialog extends ConsumerStatefulWidget {
  const _ShareDialog({required this.doc});

  final DocumentItem doc;

  @override
  ConsumerState<_ShareDialog> createState() => _ShareDialogState();
}

class _ShareDialogState extends ConsumerState<_ShareDialog> {
  List<ShareLink>? _links;
  String? _error;

  /// Link vừa tạo (hiện URL + nút copy) — token chỉ có lần này.
  ({ShareLink link, String url})? _freshLink;

  bool _creating = false;
  bool _changed = false;
  int _expiryIndex = 1; // mặc định 7 ngày (kịch bản nghiệm thu)
  bool _commentPermission = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      final List<ShareLink> links = await ref
          .read(shareRepositoryProvider)
          .listShares(widget.doc.id);
      if (mounted) setState(() => _links = links);
    } on Exception catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  Future<void> _create() async {
    setState(() => _creating = true);
    try {
      final ShareLink link = await ref
          .read(shareRepositoryProvider)
          .createShare(
            widget.doc.id,
            permission: _commentPermission ? 'comment' : 'view',
            expiresInHours: _kExpiryChoices[_expiryIndex].hours,
          );
      if (!mounted) return;
      setState(() {
        _freshLink = (link: link, url: link.shareUrl);
        _changed = true;
        _error = null;
      });
      await _reload();
    } on Exception catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<void> _revoke(ShareLink link) async {
    final bool? ok = await showDialog<bool>(
      context: context,
      builder: (BuildContext ctx) => AlertDialog(
        title: const Text('Thu hồi link này?'),
        content: const Text(
          'Người có link sẽ không còn xem được tài liệu. Thao tác không thể hoàn tác.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Thu hồi'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref
          .read(shareRepositoryProvider)
          .revokeShare(widget.doc.id, link.id);
      setState(() => _changed = true);
      await _reload();
    } on Exception catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  Future<void> _copyUrl(String url) async {
    await Clipboard.setData(ClipboardData(text: url));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã sao chép')),
      );
    }
  }

  String _formatDate(DateTime? time) {
    if (time == null) return 'vô hạn';
    return '${time.day}/${time.month}/${time.year}';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Chia sẻ "${widget.doc.name}"'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              // FR-3.4: PDF có mật khẩu — cảnh báo cho chủ tài liệu
              if (widget.doc.isPdf)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Text(
                    'Lưu ý: nếu file có mật khẩu, người nhận cần biết mật khẩu để mở.',
                    style: TextStyle(
                      fontSize: 12,
                      color: theme.colorScheme.outline,
                    ),
                  ),
                ),
              Text('Thời hạn', style: theme.textTheme.titleSmall),
              const SizedBox(height: 6),
              Wrap(
                spacing: 8,
                children: <Widget>[
                  for (int i = 0; i < _kExpiryChoices.length; i++)
                    ChoiceChip(
                      label: Text(_kExpiryChoices[i].label),
                      selected: _expiryIndex == i,
                      onSelected: (_) => setState(() => _expiryIndex = i),
                    ),
                ],
              ),
              const SizedBox(height: 10),
              Text('Quyền', style: theme.textTheme.titleSmall),
              const SizedBox(height: 6),
              Wrap(
                spacing: 8,
                children: <Widget>[
                  ChoiceChip(
                    label: const Text('Chỉ xem'),
                    selected: !_commentPermission,
                    onSelected: (_) => setState(() => _commentPermission = false),
                  ),
                  // P2: chủ tài liệu chọn link cho phép bình luận. Nhãn "sắp
                  // có" của P1 được gỡ khi giao pha bình luận.
                  ChoiceChip(
                    label: const Text('Bình luận'),
                    selected: _commentPermission,
                    onSelected: (_) => setState(() => _commentPermission = true),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _creating ? null : _create,
                  icon: _creating
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.link),
                  label: const Text('Tạo link'),
                ),
              ),
              if (_freshLink != null) ...<Widget>[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        _freshLink!.url,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12.5),
                      ),
                      const SizedBox(height: 6),
                      Align(
                        alignment: Alignment.centerRight,
                        child: TextButton.icon(
                          icon: const Icon(Icons.copy, size: 16),
                          label: const Text('Sao chép'),
                          onPressed: () => _copyUrl(_freshLink!.url),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    _error!,
                    style: TextStyle(color: theme.colorScheme.error, fontSize: 12.5),
                  ),
                ),
              const Divider(height: 24),
              Text('Link đã tạo', style: theme.textTheme.titleSmall),
              const SizedBox(height: 4),
              if (_links == null)
                const Padding(
                  padding: EdgeInsets.all(12),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_links!.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(12),
                  child: Text('Chưa có link nào.'),
                )
              else
                ..._links!.map((ShareLink link) {
                  return ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(
                      link.isUsable ? Icons.link : Icons.link_off,
                      color: link.isUsable
                          ? theme.colorScheme.primary
                          : theme.colorScheme.outline,
                    ),
                    title: Text(
                      '${link.statusLabel} · ${link.permission == 'comment' ? 'Bình luận' : 'Chỉ xem'}',
                      style: const TextStyle(fontSize: 13),
                    ),
                    subtitle: Text(
                      'Hết hạn: ${_formatDate(link.expiresAt)} · Tạo ${_formatDate(link.createdAt)} · ${link.viewCount} lượt xem',
                      style: const TextStyle(fontSize: 11.5),
                    ),
                    trailing: link.isUsable
                        ? TextButton(
                            onPressed: () => _revoke(link),
                            child: const Text('Thu hồi'),
                          )
                        : null,
                  );
                }),
            ],
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(_changed),
          child: const Text('Đóng'),
        ),
      ],
    );
  }
}
