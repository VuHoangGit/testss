/// Xem ảnh đã upload (png/jpg...) — phóng to/thu nhỏ bằng cử chỉ hoặc cuộn.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';

class ImageViewerScreen extends StatelessWidget {
  const ImageViewerScreen({
    super.key,
    required this.fileName,
    required this.bytes,
  });

  final String fileName;
  final Uint8List bytes;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(fileName, maxLines: 1, overflow: TextOverflow.ellipsis),
      ),
      backgroundColor: Colors.black,
      body: InteractiveViewer(
        maxScale: 8,
        child: Center(child: Image.memory(bytes, fit: BoxFit.contain)),
      ),
    );
  }
}
