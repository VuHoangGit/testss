import 'package:flutter/material.dart';

import '../../domain/entities/document_entities.dart';

class AiDocumentPicker extends StatelessWidget {
  const AiDocumentPicker({
    super.key,
    required this.documents,
    required this.value,
    required this.onChanged,
  });

  final List<DocumentItem> documents;
  final String? value;
  final ValueChanged<String?>? onChanged;

  @override
  Widget build(BuildContext context) {
    final List<DocumentItem> pdfs =
        documents.where((DocumentItem document) => document.isPdf).toList();
    return DropdownButtonFormField<String>(
      initialValue: value,
      decoration: const InputDecoration(
        labelText: 'Tài liệu PDF',
        prefixIcon: Icon(Icons.picture_as_pdf_outlined),
      ),
      items: <DropdownMenuItem<String>>[
        for (final DocumentItem document in pdfs)
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
