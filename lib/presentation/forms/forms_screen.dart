import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/files/file_saver.dart';
import '../providers.dart';

enum FormProcessStatus { idle, loadingTemplates, uploading, success, error }

class FormTemplateItem {
  const FormTemplateItem({
    required this.name,
    required this.sizeBytes,
    required this.type,
  });
  final String name;
  final int sizeBytes;
  final String type;
}

/// Vị trí logo chuẩn hóa (0–1) theo trang PDF: (x, y) là góc trên-trái,
/// (w, h) là kích thước — trùng khớp công thức backend khi đóng dấu.
class _LogoPlacement {
  const _LogoPlacement({
    required this.bytes,
    required this.name,
    required this.x,
    required this.y,
    required this.w,
    required this.h,
  });

  final Uint8List bytes;
  final String name;
  final double x;
  final double y;
  final double w;
  final double h;

  _LogoPlacement copyWith({double? x, double? y, double? w, double? h}) {
    return _LogoPlacement(
      bytes: bytes,
      name: name,
      x: x ?? this.x,
      y: y ?? this.y,
      w: w ?? this.w,
      h: h ?? this.h,
    );
  }
}

class _FormsState {
  const _FormsState({
    this.status = FormProcessStatus.idle,
    this.templates = const <FormTemplateItem>[],
    this.selectedTemplates = const <FormTemplateItem>{},
    this.resultBytes,
    this.resultName,
    this.message,
    this.previewImage,
    this.previewTemplateName,
    this.previewPage = 0,
    this.previewPageCount = 1,
    this.previewAspect = 1 / 1.414,
    this.isWatermark = false,
    this.password,
  });

  final FormProcessStatus status;
  final List<FormTemplateItem> templates;
  final Set<FormTemplateItem> selectedTemplates;
  final Uint8List? resultBytes;
  final String? resultName;
  final String? message;
  final Uint8List? previewImage;
  final String? previewTemplateName;
  final int previewPage;
  final int previewPageCount;
  final double previewAspect; // width / height của trang
  final bool isWatermark;
  final String? password;

  _FormsState copyWith({
    FormProcessStatus? status,
    List<FormTemplateItem>? templates,
    Set<FormTemplateItem>? selectedTemplates,
    Uint8List? resultBytes,
    Object? resultName = _sentinel,
    String? message,
    Object? previewImage = _sentinel,
    Object? previewTemplateName = _sentinel,
    int? previewPage,
    int? previewPageCount,
    double? previewAspect,
    bool? isWatermark,
    String? password,
  }) {
    return _FormsState(
      status: status ?? this.status,
      templates: templates ?? this.templates,
      selectedTemplates: selectedTemplates ?? this.selectedTemplates,
      resultBytes: resultBytes ?? this.resultBytes,
      resultName: resultName == _sentinel
          ? this.resultName
          : resultName as String?,
      message: message,
      previewImage: previewImage == _sentinel
          ? this.previewImage
          : previewImage as Uint8List?,
      previewTemplateName: previewTemplateName == _sentinel
          ? this.previewTemplateName
          : previewTemplateName as String?,
      previewPage: previewPage ?? this.previewPage,
      previewPageCount: previewPageCount ?? this.previewPageCount,
      previewAspect: previewAspect ?? this.previewAspect,
      isWatermark: isWatermark ?? this.isWatermark,
      password: password ?? this.password,
    );
  }

  static const Object _sentinel = Object();
}

class FormsScreen extends ConsumerStatefulWidget {
  const FormsScreen({super.key});
  @override
  ConsumerState<FormsScreen> createState() => _FormsScreenState();
}

class _FormsScreenState extends ConsumerState<FormsScreen> {
  _FormsState _state = const _FormsState(
    status: FormProcessStatus.loadingTemplates,
  );
  final List<_LogoPlacement> _logos = <_LogoPlacement>[];
  int _activeLogoIndex = 0;

  @override
  void initState() {
    super.initState();
    _loadTemplates();
  }

  Future<void> _loadTemplates() async {
    setState(
      () =>
          _state = _state.copyWith(status: FormProcessStatus.loadingTemplates),
    );
    try {
      final Response<dynamic> response = await ref
          .read(apiDioProvider)
          .get<dynamic>('/forms/templates');
      final List<dynamic> items =
          response.data as List<dynamic>? ?? <dynamic>[];
      final List<FormTemplateItem> templates = <FormTemplateItem>[
        for (final dynamic item in items)
          FormTemplateItem(
            name: item['name'] as String,
            sizeBytes: (item['size_bytes'] as num).toInt(),
            type: item['type'] as String,
          ),
      ];
      if (!mounted) return;
      setState(() {
        _state = _FormsState(
          status: FormProcessStatus.idle,
          templates: templates,
          selectedTemplates: templates.isEmpty
              ? <FormTemplateItem>{}
              : <FormTemplateItem>{templates.first},
        );
      });
      if (templates.isNotEmpty) {
        await _loadPreviewPage(templates.first.name, 0);
      }
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() {
        _state = _state.copyWith(
          status: FormProcessStatus.error,
          message: _dioDetail(error, 'Không tải được danh sách biểu mẫu'),
        );
      });
    }
  }

  Future<void> _loadPreviewPage(String templateName, int page) async {
    setState(
      () =>
          _state = _state.copyWith(status: FormProcessStatus.loadingTemplates),
    );
    try {
      final Response<List<int>> response = await ref
          .read(apiDioProvider)
          .get<List<int>>(
            '/forms/preview-document?template_name=${Uri.encodeQueryComponent(templateName)}&page=$page',
            options: Options(
              responseType: ResponseType.bytes,
              receiveTimeout: const Duration(minutes: 2),
            ),
          );
      final int pageCount =
          int.tryParse(response.headers.value('x-page-count') ?? '') ?? 1;
      final double pageW =
          double.tryParse(response.headers.value('x-page-width-pt') ?? '') ??
          595.0;
      final double pageH =
          double.tryParse(response.headers.value('x-page-height-pt') ?? '') ??
          842.0;
      if (!mounted) return;
      setState(() {
        _state = _state.copyWith(
          status: FormProcessStatus.idle,
          previewImage: Uint8List.fromList(response.data ?? <int>[]),
          previewTemplateName: templateName,
          previewPage: page,
          previewPageCount: pageCount,
          previewAspect: pageH > 0 ? pageW / pageH : 1 / 1.414,
          message: null,
        );
      });
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() {
        _state = _state.copyWith(
          status: FormProcessStatus.error,
          previewImage: null,
          message: _dioDetail(error, 'Không tạo được preview biểu mẫu'),
        );
      });
    }
  }

  /// Đọc kích thước gốc của ảnh (không giải mã toàn bộ) để đặt tỉ lệ logo khớp.
  Future<double> _imageAspect(Uint8List bytes) async {
    try {
      final ui.ImmutableBuffer buffer = await ui.ImmutableBuffer.fromUint8List(
        bytes,
      );
      final ui.ImageDescriptor descriptor = await ui.ImageDescriptor.encoded(
        buffer,
      );
      final double aspect = descriptor.height / descriptor.width;
      buffer.dispose();
      descriptor.dispose();
      return aspect > 0 ? aspect : 0.5;
    } catch (_) {
      return 0.5;
    }
  }

  Future<void> _pickLogo() async {
    // file_picker 13: pickFiles luôn cho chọn nhiều file (allowMultiple đã bỏ)
    final List<PlatformFile> picked = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: <String>['png', 'jpg', 'jpeg'],
    );
    if (picked.isEmpty) return;
    final double pageAspect = _state.previewAspect; // w/h của trang
    final List<_LogoPlacement> added = <_LogoPlacement>[];
    for (final PlatformFile file in picked) {
      final Uint8List bytes = await file.readAsBytes();
      final double imgAspect = await _imageAspect(bytes); // h/w của ảnh
      // Hộp logo ôm sát tỉ lệ ảnh: h = w × (imgAspect × pageAspect).
      double w = 0.18;
      double h = w * imgAspect * pageAspect;
      if (h > 0.30) {
        h = 0.30;
        w = h / (imgAspect * pageAspect);
      }
      if (w > 0.80) {
        w = 0.80;
        h = w * imgAspect * pageAspect;
      }
      final int offset = _logos.length + added.length;
      added.add(
        _LogoPlacement(
          bytes: bytes,
          name: file.name,
          x: (0.78 - (offset * 0.16) % 0.72).clamp(0.0, 0.82 - w),
          y: 0.04 + (offset * 0.12) % 0.6,
          w: w,
          h: h,
        ),
      );
    }
    if (!mounted || added.isEmpty) return;
    setState(() {
      _logos.addAll(added);
      _activeLogoIndex = _logos.length - added.length;
    });
  }

  Future<void> _process() async {
    final Set<FormTemplateItem> templates = _state.selectedTemplates;
    final List<_LogoPlacement> logos = List<_LogoPlacement>.of(_logos);
    if (templates.isEmpty || logos.isEmpty) {
      setState(() {
        _state = _state.copyWith(
          status: FormProcessStatus.error,
          message: 'Vui lòng chọn ít nhất một biểu mẫu và một logo',
        );
      });
      return;
    }
    setState(() {
      _state = _state.copyWith(
        status: FormProcessStatus.uploading,
        message: null,
      );
    });

    try {
      final FormData formData = FormData.fromMap(<String, dynamic>{
        'logos': <MultipartFile>[
          for (final _LogoPlacement logo in logos)
            MultipartFile.fromBytes(
              logo.bytes,
              filename: logo.name,
              contentType: DioMediaType.parse(
                logo.name.toLowerCase().endsWith('.png')
                    ? 'image/png'
                    : 'image/jpeg',
              ),
            ),
        ],
        'logo_placements': jsonEncode(<Map<String, Object>>[
          for (final _LogoPlacement logo in logos)
            <String, Object>{
              'x': logo.x,
              'y': logo.y,
              'w': logo.w,
              'h': logo.h,
            },
        ]),
        'template_names': <String>[
          for (final FormTemplateItem template in templates) template.name,
        ],
        'is_watermark': _state.isWatermark,
        if (_state.password != null && _state.password!.isNotEmpty)
          'password': _state.password,
      });
      final Response<List<int>> response = await ref
          .read(apiDioProvider)
          .post<List<int>>(
            '/forms/process',
            data: formData,
            options: Options(
              responseType: ResponseType.bytes,
              receiveTimeout: const Duration(minutes: 5),
            ),
          );
      final Uint8List result = Uint8List.fromList(response.data ?? <int>[]);
      final String disposition =
          response.headers.value('content-disposition') ?? '';
      final String resultName =
          _filenameFromDisposition(disposition) ?? 'processed-forms.zip';
      if (!mounted) return;
      setState(() {
        _state = _state.copyWith(
          status: FormProcessStatus.success,
          resultBytes: result,
          resultName: resultName,
          message: 'Đã tạo ZIP gồm ${templates.length} biểu mẫu',
        );
      });
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() {
        _state = _state.copyWith(
          status: FormProcessStatus.error,
          message: _dioDetail(error, 'Không xử lý được biểu mẫu'),
        );
      });
    }
  }

  Future<void> _download() async {
    final Uint8List? bytes = _state.resultBytes;
    final String? name = _state.resultName;
    if (bytes == null || name == null) return;
    final String lowerName = name.toLowerCase();
    final String mimeType = lowerName.endsWith('.zip')
        ? 'application/zip'
        : lowerName.endsWith('.pdf')
        ? 'application/pdf'
        : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    await const FileSaver().saveBytes(
      fileName: name,
      bytes: bytes,
      mimeType: mimeType,
    );
  }

  String _dioDetail(DioException error, String fallback) {
    final dynamic data = error.response?.data;
    if (data is Map && data['detail'] is String) {
      return data['detail'] as String;
    }
    return fallback;
  }

  String? _filenameFromDisposition(String disposition) {
    final RegExpMatch? ascii = RegExp(r'filename="([^"]+)"')
        .firstMatch(disposition);
    if (ascii != null) return ascii.group(1);
    final RegExpMatch? utf8 = RegExp(r"filename\*=UTF-8''([^;]+)")
        .firstMatch(disposition);
    if (utf8 != null) return Uri.decodeComponent(utf8.group(1)!);
    return null;
  }

  String _sizeLabel(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool busy =
        _state.status == FormProcessStatus.loadingTemplates ||
        _state.status == FormProcessStatus.uploading;
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(28, 26, 28, 32),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              'Biểu mẫu',
              style: theme.textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 18),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 760),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text('Chọn biểu mẫu', style: theme.textTheme.titleSmall),
                      const SizedBox(height: 8),
                      if (_state.status == FormProcessStatus.loadingTemplates &&
                          _state.templates.isEmpty)
                        const LinearProgressIndicator()
                      else if (_state.templates.isEmpty)
                        const Text(
                          'Thư mục biểu mẫu chưa có PDF, DOCX hoặc DOC.',
                        )
                      else
                        Wrap(
                          spacing: 8,
                          runSpacing: 4,
                          children: <Widget>[
                            for (final FormTemplateItem template
                                in _state.templates)
                              FilterChip(
                                label: Text(
                                  '${template.name} · ${_sizeLabel(template.sizeBytes)}',
                                ),
                                selected: _state.selectedTemplates.contains(
                                  template,
                                ),
                                onSelected: busy
                                    ? null
                                    : (bool selected) async {
                                        final Set<FormTemplateItem> next =
                                            Set<FormTemplateItem>.of(
                                              _state.selectedTemplates,
                                            );
                                        if (selected) {
                                          next.add(template);
                                        } else {
                                          next.remove(template);
                                        }
                                        setState(() {
                                          _state = _state.copyWith(
                                            status: FormProcessStatus.idle,
                                            selectedTemplates: next,
                                            message: null,
                                          );
                                        });
                                        if (selected) {
                                          await _loadPreviewPage(
                                            template.name,
                                            0,
                                          );
                                        }
                                      },
                              ),
                          ],
                        ),
                      const SizedBox(height: 18),
                      Text('Logo công ty', style: theme.textTheme.titleSmall),
                      const SizedBox(height: 8),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          OutlinedButton.icon(
                            onPressed: busy ? null : _pickLogo,
                            icon: const Icon(
                              Icons.add_photo_alternate_outlined,
                            ),
                            label: const Text('Thêm nhiều logo'),
                          ),
                          if (_logos.isNotEmpty) ...<Widget>[
                            const SizedBox(width: 16),
                            Expanded(
                              child: Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: <Widget>[
                                  for (
                                    int index = 0;
                                    index < _logos.length;
                                    index++
                                  )
                                    ChoiceChip(
                                      label: Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: <Widget>[
                                          Image.memory(
                                            _logos[index].bytes,
                                            width: 28,
                                            height: 28,
                                            fit: BoxFit.contain,
                                          ),
                                          const SizedBox(width: 6),
                                          Text(_logos[index].name),
                                          IconButton(
                                            tooltip: 'Xóa logo',
                                            visualDensity:
                                                VisualDensity.compact,
                                            onPressed: () {
                                              setState(() {
                                                _logos.removeAt(index);
                                                if (_activeLogoIndex >=
                                                    _logos.length) {
                                                  _activeLogoIndex = 0;
                                                }
                                              });
                                            },
                                            icon: const Icon(
                                              Icons.close,
                                              size: 16,
                                            ),
                                          ),
                                        ],
                                      ),
                                      selected: _activeLogoIndex == index,
                                      onSelected: (_) {
                                        setState(
                                          () => _activeLogoIndex = index,
                                        );
                                      },
                                    ),
                                ],
                              ),
                            ),
                          ],
                        ],
                      ),
                      if (_state.previewImage != null) ...<Widget>[
                        const SizedBox(height: 18),
                        Row(
                          children: <Widget>[
                            Text(
                              'Kéo logo tới vị trí mong muốn · kéo góc phải-dưới để đổi kích thước',
                              style: theme.textTheme.titleSmall,
                            ),
                            const Spacer(),
                            if (_state.previewPageCount > 1) ...<Widget>[
                              IconButton(
                                tooltip: 'Trang trước',
                                onPressed: _state.previewPage > 0
                                    ? () => _loadPreviewPage(
                                        _state.previewTemplateName ??
                                            _state.templates.first.name,
                                        _state.previewPage - 1,
                                      )
                                    : null,
                                icon: const Icon(Icons.chevron_left),
                              ),
                              Text(
                                '${_state.previewPage + 1}/${_state.previewPageCount}',
                              ),
                              IconButton(
                                tooltip: 'Trang sau',
                                onPressed:
                                    _state.previewPage + 1 <
                                        _state.previewPageCount
                                    ? () => _loadPreviewPage(
                                        _state.previewTemplateName ??
                                            _state.templates.first.name,
                                        _state.previewPage + 1,
                                      )
                                    : null,
                                icon: const Icon(Icons.chevron_right),
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: 8),
                        if (_logos.isEmpty)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Text(
                              'Chưa có logo — bấm "Thêm nhiều logo" để bắt đầu kéo thả.',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ),
                        LayoutBuilder(
                          builder:
                              (
                                BuildContext context,
                                BoxConstraints constraints,
                              ) {
                                final double pageW = constraints.maxWidth;
                                final double pageH =
                                    pageW / _state.previewAspect;
                                return Center(
                                  child: SizedBox(
                                    width: pageW,
                                    height: pageH,
                                    child: ClipRRect(
                                      borderRadius: BorderRadius.circular(8),
                                      child: Stack(
                                        fit: StackFit.expand,
                                        children: <Widget>[
                                          Image.memory(
                                            _state.previewImage!,
                                            fit: BoxFit.fill,
                                            gaplessPlayback: true,
                                          ),
                                          for (
                                            int index = 0;
                                            index < _logos.length;
                                            index++
                                          )
                                            _buildLogoOverlay(
                                              theme,
                                              index,
                                              pageW,
                                              pageH,
                                            ),
                                        ],
                                      ),
                                    ),
                                  ),
                                );
                              },
                        ),
                      ],
                      const SizedBox(height: 18),
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        value: _state.isWatermark,
                        title: const Text('Đóng dấu chìm toàn trang'),
                        onChanged: busy
                            ? null
                            : (bool? value) {
                                setState(() {
                                  _state = _state.copyWith(
                                    isWatermark: value ?? false,
                                  );
                                });
                              },
                      ),
                      TextField(
                        obscureText: true,
                        decoration: const InputDecoration(
                          labelText: 'Mật khẩu bảo vệ (PDF)',
                          border: OutlineInputBorder(),
                        ),
                        onChanged: (String value) {
                          _state = _state.copyWith(password: value);
                        },
                      ),
                      const SizedBox(height: 20),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed: busy ? null : _process,
                          icon: busy
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.auto_fix_high),
                          label: Text(
                            _state.status == FormProcessStatus.uploading
                                ? 'Đang xử lý…'
                                : 'Chèn logo',
                          ),
                        ),
                      ),
                      if (_state.status == FormProcessStatus.error)
                        Padding(
                          padding: const EdgeInsets.only(top: 12),
                          child: Text(
                            _state.message ?? 'Đã xảy ra lỗi',
                            style: TextStyle(color: theme.colorScheme.error),
                          ),
                        ),
                      if (_state.status ==
                          FormProcessStatus.success) ...<Widget>[
                        const SizedBox(height: 12),
                        Text(
                          _state.message ?? 'Đã tạo biểu mẫu',
                          style: TextStyle(
                            color: theme.colorScheme.primary,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 8),
                        FilledButton.icon(
                          onPressed: _download,
                          icon: const Icon(Icons.download),
                          label: const Text('Tải về'),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Hộp logo kéo thả trên nền preview — tọa độ khớp công thức backend.
  Widget _buildLogoOverlay(
    ThemeData theme,
    int index,
    double pageW,
    double pageH,
  ) {
    final _LogoPlacement logo = _logos[index];
    final bool active = _activeLogoIndex == index;
    final double boxW = logo.w * pageW;
    final double boxH = logo.h * pageH;
    final double left = (logo.x * pageW).clamp(0.0, pageW - boxW);
    final double top = (logo.y * pageH).clamp(0.0, pageH - boxH);
    final double minW = 0.04 * pageW;

    return Positioned(
      left: left,
      top: top,
      width: boxW,
      height: boxH,
      child: GestureDetector(
        onTap: () => setState(() => _activeLogoIndex = index),
        onPanUpdate: (DragUpdateDetails details) {
          setState(() {
            _activeLogoIndex = index;
            final double nextX = (_logos[index].x + details.delta.dx / pageW)
                .clamp(0.0, 1.0 - logo.w);
            final double nextY = (_logos[index].y + details.delta.dy / pageH)
                .clamp(0.0, 1.0 - logo.h);
            _logos[index] = _logos[index].copyWith(x: nextX, y: nextY);
          });
        },
        child: Stack(
          clipBehavior: Clip.none,
          children: <Widget>[
            Container(
              width: boxW,
              height: boxH,
              decoration: BoxDecoration(
                border: Border.all(
                  color: active
                      ? theme.colorScheme.primary
                      : theme.colorScheme.outline,
                  width: active ? 2 : 1,
                ),
              ),
              child: Opacity(
                opacity: _state.isWatermark ? 0.12 : 1,
                child: Image.memory(logo.bytes, fit: BoxFit.contain),
              ),
            ),
            // Tay cầm resize góc phải-dưới, giữ nguyên tỉ lệ ảnh.
            Positioned(
              right: -7,
              bottom: -7,
              child: GestureDetector(
                onPanUpdate: (DragUpdateDetails details) {
                  setState(() {
                    _activeLogoIndex = index;
                    final double currentW = _logos[index].w;
                    final double currentH = _logos[index].h;
                    if (currentW <= 0 || currentH <= 0) return;
                    double nextW = (currentW + details.delta.dx / pageW).clamp(
                      minW / pageW,
                      1.0 - _logos[index].x,
                    );
                    double nextH = nextW * currentH / currentW;
                    if (nextH > 1.0 - _logos[index].y) {
                      nextH = 1.0 - _logos[index].y;
                      nextW = nextH * currentW / currentH;
                    }
                    _logos[index] = _logos[index].copyWith(w: nextW, h: nextH);
                  });
                },
                child: MouseRegion(
                  cursor: SystemMouseCursors.resizeDownRight,
                  child: Container(
                    width: 14,
                    height: 14,
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: theme.colorScheme.onPrimary,
                        width: 2,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
