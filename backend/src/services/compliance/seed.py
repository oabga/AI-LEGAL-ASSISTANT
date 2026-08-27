"""Danh mục nghĩa vụ tuân thủ định kỳ của doanh nghiệp nhỏ và vừa.

Mỗi rule kèm ``legal_refs`` trỏ về đúng Điều luật trong corpus để người dùng
kiểm chứng được nguồn, thay vì tin vào một con số hạn chót không rõ căn cứ.

``applies_to`` là điều kiện lọc theo hồ sơ doanh nghiệp:

- ``vat_period``: chỉ áp dụng khi doanh nghiệp khai thuế GTGT theo kỳ đó
- ``min_employees``: chỉ áp dụng khi số lao động >= ngưỡng
"""
from __future__ import annotations

from typing import Any

from src.models.enums import ComplianceFrequency

# due_month_offset: số tháng cộng thêm sau khi kỳ kết thúc.
# due_fixed_month: dùng cho nghĩa vụ theo năm có tháng đến hạn cố định.
COMPLIANCE_RULES: list[dict[str, Any]] = [
    {
        "code": "VAT_MONTHLY",
        "title": "Khai và nộp thuế giá trị gia tăng theo tháng",
        "description": (
            "Doanh nghiệp khai thuế GTGT theo tháng phải nộp hồ sơ khai thuế và tiền thuế "
            "chậm nhất ngày 20 của tháng liền sau tháng phát sinh nghĩa vụ."
        ),
        "frequency": ComplianceFrequency.MONTHLY,
        "due_day": 20,
        "due_month_offset": 1,
        "category": "Thuế",
        "legal_refs": [
            "38/2019/QH14|Luật Quản lý thuế|Điều 44",
            "38/2019/QH14|Luật Quản lý thuế|Điều 55",
        ],
        "applies_to": {"vat_period": "monthly"},
    },
    {
        "code": "VAT_QUARTERLY",
        "title": "Khai và nộp thuế giá trị gia tăng theo quý",
        "description": (
            "Doanh nghiệp khai thuế GTGT theo quý phải nộp hồ sơ khai thuế chậm nhất ngày "
            "cuối cùng của tháng đầu quý liền sau quý phát sinh nghĩa vụ."
        ),
        "frequency": ComplianceFrequency.QUARTERLY,
        "due_day": 31,
        "due_month_offset": 1,
        "category": "Thuế",
        "legal_refs": [
            "38/2019/QH14|Luật Quản lý thuế|Điều 44",
            "126/2020/NĐ-CP|Nghị định Quy định chi tiết một số điều của Luật Quản lý thuế|Điều 8",
        ],
        "applies_to": {"vat_period": "quarterly"},
    },
    {
        "code": "CIT_PROVISIONAL",
        "title": "Tạm nộp thuế thu nhập doanh nghiệp theo quý",
        "description": (
            "Tạm nộp thuế TNDN của quý, chậm nhất ngày 30 của tháng đầu quý sau. "
            "Không phải nộp hồ sơ khai thuế tạm tính theo quý."
        ),
        "frequency": ComplianceFrequency.QUARTERLY,
        "due_day": 30,
        "due_month_offset": 1,
        "category": "Thuế",
        "legal_refs": [
            "38/2019/QH14|Luật Quản lý thuế|Điều 55",
            "126/2020/NĐ-CP|Nghị định Quy định chi tiết một số điều của Luật Quản lý thuế|Điều 8",
        ],
        "applies_to": {},
    },
    {
        "code": "CIT_FINALIZATION",
        "title": "Quyết toán thuế thu nhập doanh nghiệp năm",
        "description": (
            "Hồ sơ quyết toán thuế TNDN năm phải nộp chậm nhất ngày cuối cùng của tháng thứ 3 "
            "kể từ ngày kết thúc năm dương lịch hoặc năm tài chính."
        ),
        "frequency": ComplianceFrequency.ANNUAL,
        "due_day": 31,
        "due_month_offset": 0,
        "due_fixed_month": 3,
        "category": "Thuế",
        "legal_refs": [
            "38/2019/QH14|Luật Quản lý thuế|Điều 44",
            "14/2008/QH12|Luật Thuế thu nhập doanh nghiệp|Điều 12",
        ],
        "applies_to": {},
    },
    {
        "code": "PIT_FINALIZATION",
        "title": "Quyết toán thuế thu nhập cá nhân năm",
        "description": (
            "Tổ chức trả thu nhập quyết toán thuế TNCN thay cho người lao động, "
            "chậm nhất ngày cuối cùng của tháng thứ 3 kể từ khi kết thúc năm."
        ),
        "frequency": ComplianceFrequency.ANNUAL,
        "due_day": 31,
        "due_month_offset": 0,
        "due_fixed_month": 3,
        "category": "Thuế",
        "legal_refs": [
            "38/2019/QH14|Luật Quản lý thuế|Điều 44",
            "04/2007/QH12|Luật Thuế thu nhập cá nhân|Điều 24",
        ],
        "applies_to": {"min_employees": 1},
    },
    {
        "code": "BUSINESS_LICENSE_FEE",
        "title": "Nộp lệ phí môn bài năm",
        "description": "Lệ phí môn bài của năm phải nộp chậm nhất ngày 30 tháng 01 hằng năm.",
        "frequency": ComplianceFrequency.ANNUAL,
        "due_day": 30,
        "due_month_offset": 0,
        "due_fixed_month": 1,
        "category": "Thuế",
        "legal_refs": [
            "139/2016/NĐ-CP|Nghị định Quy định về lệ phí môn bài|Điều 5",
            "126/2020/NĐ-CP|Nghị định Quy định chi tiết một số điều của Luật Quản lý thuế|Điều 10",
        ],
        "applies_to": {},
    },
    {
        "code": "SOCIAL_INSURANCE_MONTHLY",
        "title": "Đóng bảo hiểm xã hội, y tế, thất nghiệp hằng tháng",
        "description": (
            "Người sử dụng lao động trích tiền đóng BHXH bắt buộc và đóng vào quỹ "
            "chậm nhất ngày cuối cùng của tháng."
        ),
        "frequency": ComplianceFrequency.MONTHLY,
        "due_day": 31,
        "due_month_offset": 0,
        "category": "Bảo hiểm xã hội",
        "legal_refs": [
            "41/2024/QH15|Luật Bảo hiểm xã hội|Điều 34",
            "58/2020/NĐ-CP|Nghị định Quy định về mức đóng bảo hiểm xã hội bắt buộc vào Quỹ bảo hiểm tai nạn lao động, bệnh nghề nghiệp|Điều 4",
        ],
        "applies_to": {"min_employees": 1},
    },
    {
        "code": "LABOUR_REPORT_H1",
        "title": "Báo cáo tình hình sử dụng lao động 6 tháng đầu năm",
        "description": (
            "Báo cáo tình hình thay đổi lao động gửi Sở Lao động - Thương binh và Xã hội "
            "trước ngày 05 tháng 6."
        ),
        "frequency": ComplianceFrequency.ANNUAL,
        "due_day": 5,
        "due_month_offset": 0,
        "due_fixed_month": 6,
        "category": "Lao động",
        "legal_refs": [
            "45/2019/QH14|Bộ luật Lao động|Điều 12",
            "145/2020/NĐ-CP|Nghị định Quy định chi tiết và hướng dẫn thi hành một số điều của Bộ luật Lao động về điều kiện lao động và quan hệ lao động|Điều 4",
        ],
        "applies_to": {"min_employees": 1},
    },
    {
        "code": "LABOUR_REPORT_H2",
        "title": "Báo cáo tình hình sử dụng lao động 6 tháng cuối năm",
        "description": (
            "Báo cáo tình hình thay đổi lao động gửi Sở Lao động - Thương binh và Xã hội "
            "trước ngày 05 tháng 12."
        ),
        "frequency": ComplianceFrequency.ANNUAL,
        "due_day": 5,
        "due_month_offset": 0,
        "due_fixed_month": 12,
        "category": "Lao động",
        "legal_refs": [
            "45/2019/QH14|Bộ luật Lao động|Điều 12",
            "145/2020/NĐ-CP|Nghị định Quy định chi tiết và hướng dẫn thi hành một số điều của Bộ luật Lao động về điều kiện lao động và quan hệ lao động|Điều 4",
        ],
        "applies_to": {"min_employees": 1},
    },
    {
        "code": "LABOUR_SAFETY_REPORT",
        "title": "Báo cáo công tác an toàn, vệ sinh lao động năm",
        "description": (
            "Báo cáo tổng hợp công tác an toàn, vệ sinh lao động gửi cơ quan quản lý "
            "trước ngày 10 tháng 01 của năm sau."
        ),
        "frequency": ComplianceFrequency.ANNUAL,
        "due_day": 10,
        "due_month_offset": 0,
        "due_fixed_month": 1,
        "category": "An toàn lao động",
        "legal_refs": [
            "84/2015/QH13|Luật An toàn, vệ sinh lao động|Điều 81",
        ],
        "applies_to": {"min_employees": 10},
    },
    {
        "code": "FINANCIAL_STATEMENT",
        "title": "Nộp báo cáo tài chính năm",
        "description": (
            "Báo cáo tài chính năm của doanh nghiệp nhỏ và vừa phải nộp cho cơ quan thuế "
            "và cơ quan thống kê trong thời hạn 90 ngày kể từ ngày kết thúc năm tài chính."
        ),
        "frequency": ComplianceFrequency.ANNUAL,
        "due_day": 31,
        "due_month_offset": 0,
        "due_fixed_month": 3,
        "category": "Kế toán",
        "legal_refs": [
            "88/2015/QH13|Luật Kế toán|Điều 29",
            "133/2016/TT-BTC|Thông tư Hướng dẫn Chế độ kế toán doanh nghiệp nhỏ và vừa|Điều 80",
        ],
        "applies_to": {},
    },
    {
        "code": "INVOICE_USAGE_CHECK",
        "title": "Rà soát hóa đơn điện tử và dữ liệu gửi cơ quan thuế",
        "description": (
            "Kiểm tra việc lập, gửi và lưu trữ hóa đơn điện tử theo đúng thời điểm quy định "
            "để tránh bị xử phạt."
        ),
        "frequency": ComplianceFrequency.QUARTERLY,
        "due_day": 15,
        "due_month_offset": 1,
        "category": "Thuế",
        "legal_refs": [
            "123/2020/NĐ-CP|Nghị định Quy định về hóa đơn, chứng từ|Điều 9",
            "78/2021/TT-BTC|Thông tư Hướng dẫn thực hiện một số điều của Luật Quản lý thuế ngày 13 tháng 6 năm 2019, Nghị định số 123/2020/NĐ-CP ngày 19 tháng 10 năm 2020 của Chính phủ quy định về hóa đơn, chứng từ|Điều 6",
        ],
        "applies_to": {},
    },
]
