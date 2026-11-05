/// Cài đặt PaymentsRepository bằng Dio gọi backend FastAPI.
library;

import 'package:dio/dio.dart';

import '../../core/network/dio_error_mapper.dart';
import '../../domain/entities/payment_entities.dart';
import '../../domain/repositories/payments_repository.dart';
import '../models/payment_models.dart';

class PaymentsRepositoryImpl implements PaymentsRepository {
  PaymentsRepositoryImpl({required this.dio});

  final Dio dio;

  @override
  Future<List<PricingPackage>> listPackages() async {
    try {
      final Response<dynamic> res = await dio.get<dynamic>('/payments/pricing');
      final List<dynamic> items =
          (res.data as List<dynamic>? ?? const <dynamic>[]);
      return items
          .map(
            (dynamic e) =>
                PricingPackageModel.fromJson(e as Map<String, dynamic>),
          )
          .toList(growable: false);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tải được bảng giá');
    }
  }

  @override
  Future<CreditBalance> getBalance() async {
    try {
      final Response<dynamic> res =
          await dio.get<dynamic>('/payments/credits');
      return CreditBalanceModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tải được số dư credit');
    }
  }

  @override
  Future<PaymentOrder> createOrder(String packageCode) async {
    try {
      final Response<dynamic> res = await dio.post<dynamic>(
        '/payments/orders',
        data: <String, String>{'code': packageCode},
      );
      return PaymentOrderModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tạo được đơn thanh toán');
    }
  }

  @override
  Future<PaymentOrder> getOrder(String orderId) async {
    try {
      final Response<dynamic> res =
          await dio.get<dynamic>('/payments/orders/$orderId');
      return PaymentOrderModel.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tải được trạng thái đơn');
    }
  }

  @override
  Future<List<PaymentOrder>> listOrders() async {
    try {
      final Response<dynamic> res = await dio.get<dynamic>('/payments/orders');
      final List<dynamic> items =
          (res.data as List<dynamic>? ?? const <dynamic>[]);
      return items
          .map(
            (dynamic e) =>
                PaymentOrderModel.fromJson(e as Map<String, dynamic>),
          )
          .toList(growable: false);
    } on DioException catch (e) {
      throw mapDioException(e, fallback: 'Không tải được lịch sử thanh toán');
    }
  }
}
