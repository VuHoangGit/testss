import 'package:flutter/material.dart';

import '../../domain/entities/document_entities.dart';

class AiDocumentPicker extends StatelessWidget {
  const AiDocumentPicker({
    super.key,
    required this.documents,
    required this.value,
    required this.onChanged,
    this.filter,
    this.labelText = 'Tài liệu PDF',
    this.prefixIcon = Icons.picture_as_pdf_outlined,
    this.emptyHint = 'Chưa có tài liệu nào',
  });

  final List<DocumentItem> documents;
  final String? value;
  final ValueChanged<String?>? onChanged;

  /// Lọc loại tài liệu hiển thị; mặc định chỉ PDF (giữ hành vi OCR/Chat).
  final bool Function(DocumentItem document)? filter;
  final String labelText;
  final IconData prefixIcon;
  final String emptyHint;

  @override
  Widget build(BuildContext context) {
    final List<DocumentItem> items = documents
        .where(filter ?? (DocumentItem document) => document.isPdf)
        .toList();
    if (items.isEmpty) {
      return DropdownButtonFormField<String>(
        initialValue: null,
        decoration: InputDecoration(
          labelText: labelText,
          prefixIcon: Icon(prefixIcon),
          helperText: emptyHint,
        ),
        items: const <DropdownMenuItem<String>>[],
        onChanged: null,
      );
    }
    return DropdownButtonFormField<String>(
      initialValue: value,
      decoration: InputDecoration(
        labelText: labelText,
        prefixIcon: Icon(prefixIcon),
      ),
      items: <DropdownMenuItem<String>>[
        for (final DocumentItem document in items)
          DropdownMenuItem<String>(
            value: document.id,
            child: Text(document.name, overflow: TextOverflow.ellipsis),
          ),
      ],
      onChanged: onChanged,
    );
  }
}

class AiPageHeader extends StatelessWidget {
  const AiPageHeader({
    super.key,
    required this.title,
    required this.subtitle,
    required this.icon,
  });

  final String title;
  final String subtitle;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        CircleAvatar(
          radius: 22,
          child: Icon(icon),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(title, style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 4),
              Text(subtitle),
            ],
          ),
        ),
      ],
    );
  }
}
