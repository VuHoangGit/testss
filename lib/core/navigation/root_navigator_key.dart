/// Navigator key toàn cục — cho voice executor mở viewer/dialog mà không
/// cần BuildContext của screen đang hiển thị.
library;

import 'package:flutter/material.dart';

final GlobalKey<NavigatorState> rootNavigatorKey = GlobalKey<NavigatorState>();
