/// Panel trợ lý giọng nói: trạng thái mic, bản ghi đang chờ gửi (kèm nút
/// Send/Discard), transcript, phản hồi AI, công tắc TTS và ô nhập lệnh bằng
/// văn bản (fallback).
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'voice_controller.dart';

class VoicePanel extends ConsumerStatefulWidget {
  const VoicePanel({super.key});

  @override
  ConsumerState<VoicePanel> createState() => _VoicePanelState();
}

class _VoicePanelState extends ConsumerState<VoicePanel> {
  final TextEditingController _text = TextEditingController();

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final VoiceState voice = ref.watch(voiceControllerProvider);
    final ColorScheme colors = Theme.of(context).colorScheme;
    // Hiện khối ghi âm khi đang nghe hoặc đang có bản ghi chờ gửi.
    final bool showRecorder =
        voice.phase == VoicePhase.listening || voice.captured.isNotEmpty;
    final bool active =
        voice.phase != VoicePhase.idle ||
        (voice.reply?.isNotEmpty ?? false) ||
        showRecorder;

    if (!active) {
      return const SizedBox.shrink();
    }

    return Material(
      elevation: 2,
      color: colors.secondaryContainer,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                _statusIcon(voice, colors),
                const SizedBox(width: 10),
                Expanded(child: _statusText(voice)),
                if (voice.phase == VoicePhase.idle) ...<Widget>[
                  IconButton(
                    tooltip: voice.ttsEnabled
                        ? 'Turn off spoken replies'
                        : 'Turn on spoken replies',
                    onPressed: () => ref
                        .read(voiceControllerProvider.notifier)
                        .setTtsEnabled(!voice.ttsEnabled),
                    icon: Icon(
                      voice.ttsEnabled
                          ? Icons.volume_up_outlined
                          : Icons.volume_off_outlined,
                    ),
                  ),
                  IconButton(
                    tooltip: 'Close',
                    onPressed: () =>
                        ref.read(voiceControllerProvider.notifier).dismiss(),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ],
            ),
            if (voice.phase == VoicePhase.listening && voice.interim.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '„${voice.interim}"',
                  style: TextStyle(
                    fontStyle: FontStyle.italic,
                    color: colors.onSecondaryContainer.withValues(alpha: 0.8),
                  ),
                ),
              ),
            if (showRecorder) _recorder(colors, voice),
            if (voice.transcript != null && voice.phase != VoicePhase.listening)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  'You: ${voice.transcript}',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
            if (voice.reply != null &&
                voice.phase == VoicePhase.idle) ...<Widget>[
              const SizedBox(height: 6),
              Text(voice.reply!),
              const SizedBox(height: 8),
              _textInput(colors, voice),
            ],
          ],
        ),
      ),
    );
  }

  /// Khối bản ghi: nội dung đã nghe được + nút Gửi / Bỏ.
  Widget _recorder(ColorScheme colors, VoiceState voice) {
    final String recorded = voice.pendingCommand;
    final bool listening = voice.phase == VoicePhase.listening;
    final bool canSend = recorded.isNotEmpty;

    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: colors.surface.withValues(alpha: 0.7),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                color: listening ? colors.secondary : colors.outlineVariant,
              ),
            ),
            child: Text(
              recorded.isEmpty ? 'Speak your command…' : recorded,
              style: TextStyle(
                fontStyle: recorded.isEmpty
                    ? FontStyle.italic
                    : FontStyle.normal,
                color: recorded.isEmpty
                    ? colors.onSurfaceVariant
                    : colors.onSurface,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: <Widget>[
              FilledButton.icon(
                onPressed: canSend
                    ? () => ref
                          .read(voiceControllerProvider.notifier)
                          .sendRecording()
                    : null,
                icon: const Icon(Icons.send, size: 18),
                label: const Text('Send'),
              ),
              const SizedBox(width: 8),
              TextButton(
                onPressed: () => ref
                    .read(voiceControllerProvider.notifier)
                    .discardRecording(),
                child: const Text('Discard'),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  listening
                      ? 'Speak, then press Send. Nothing is sent until you do.'
                      : 'Press Send to run what you said.',
                  style: TextStyle(
                    fontSize: 12,
                    color: colors.onSecondaryContainer.withValues(alpha: 0.8),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _statusIcon(VoiceState voice, ColorScheme colors) {
    switch (voice.phase) {
      case VoicePhase.listening:
        // Violet (secondary) cho trạng thái đang nghe — khớp màu AI
        return Icon(Icons.mic, color: colors.secondary);
      case VoicePhase.processing:
      case VoicePhase.executing:
        return SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: colors.primary,
          ),
        );
      case VoicePhase.idle:
        return Icon(Icons.smart_toy_outlined, color: colors.primary);
    }
  }

  Widget _statusText(VoiceState voice) {
    const Map<VoicePhase, String> labels = <VoicePhase, String>{
      VoicePhase.idle: 'Assistant',
      VoicePhase.listening: 'Listening… speak, then press Send',
      VoicePhase.processing: 'Understanding the command…',
      VoicePhase.executing: 'Running the command…',
    };
    return Text(
      labels[voice.phase] ?? '',
      style: const TextStyle(fontWeight: FontWeight.w600),
    );
  }

  Widget _textInput(ColorScheme colors, VoiceState voice) {
    return TextField(
      controller: _text,
      enabled: voice.phase == VoicePhase.idle,
      onSubmitted: (String value) {
        ref.read(voiceControllerProvider.notifier).submitText(value);
        _text.clear();
      },
      decoration: InputDecoration(
        isDense: true,
        hintText:
            'Or type a command, e.g. "go to the documents tab", "run OCR on the contract file"',
        suffixIcon: IconButton(
          tooltip: 'Send command',
          icon: const Icon(Icons.send_outlined),
          onPressed: voice.phase == VoicePhase.idle
              ? () {
                  ref
                      .read(voiceControllerProvider.notifier)
                      .submitText(_text.text);
                  _text.clear();
                }
              : null,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: colors.outline),
        ),
      ),
    );
  }
}

/// Nút mic đặt trên AppBar — bấm để bắt đầu/dừng nghe.
class VoiceMicButton extends ConsumerWidget {
  const VoiceMicButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final VoiceState voice = ref.watch(voiceControllerProvider);
    final ColorScheme colors = Theme.of(context).colorScheme;
    final bool listening = voice.phase == VoicePhase.listening;

    return IconButton(
      tooltip: listening ? 'Stop recording' : 'Voice command',
      onPressed: () => ref.read(voiceControllerProvider.notifier).toggleMic(),
      icon: Icon(
        listening ? Icons.stop_circle : Icons.mic_none,
        color: listening ? colors.error : null,
      ),
    );
  }
}
