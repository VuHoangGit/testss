import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/repositories/ai_repository_impl.dart';
import '../../domain/repositories/ai_repository.dart';
import '../providers.dart';

final Provider<AiRepository> aiRepositoryProvider = Provider<AiRepository>(
  (Ref ref) => AiRepositoryImpl(dio: ref.watch(apiDioProvider)),
);
