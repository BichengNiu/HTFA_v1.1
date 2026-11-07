from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from htfa.data.economic_workbook import SheetSeriesMetadata

PAYMENT_SHEET = "月度_CBUAE"
CUSTOMER_TRANSFERS_NUMBER = "阿联酋:FTS客户转账笔数(累计)Customer Transfers Number"
CUSTOMER_TRANSFERS_AMOUNT = "阿联酋:FTS客户转账金额(累计)Customer Transfers Amount"
CHEQUES_NUMBER = "阿联酋:支票清算笔数(累计)Cheques Cleared Number"
CHEQUES_AMOUNT = "阿联酋:支票清算金额(累计)Cheques Cleared Amount"
CUSTOMER_TRANSFERS_NUMBER_DISPLAY = "客户资金转账笔数（FTS）"
CUSTOMER_TRANSFERS_AMOUNT_DISPLAY = "客户资金转账金额（FTS）"
CHEQUES_NUMBER_DISPLAY = "支票清算笔数"
CHEQUES_AMOUNT_DISPLAY = "支票清算金额"
PAYMENT_INDICATORS: tuple[tuple[str, str, str], ...] = (
    (CUSTOMER_TRANSFERS_NUMBER_DISPLAY, CUSTOMER_TRANSFERS_NUMBER, "笔"),
    (CUSTOMER_TRANSFERS_AMOUNT_DISPLAY, CUSTOMER_TRANSFERS_AMOUNT, "百万迪拉姆"),
    (CHEQUES_NUMBER_DISPLAY, CHEQUES_NUMBER, "张"),
    (CHEQUES_AMOUNT_DISPLAY, CHEQUES_AMOUNT, "百万迪拉姆"),
)
CUSTOMER_TRANSFER_SERIES = (
    CUSTOMER_TRANSFERS_NUMBER_DISPLAY,
    CUSTOMER_TRANSFERS_AMOUNT_DISPLAY,
)
CHEQUE_SERIES = (CHEQUES_NUMBER_DISPLAY, CHEQUES_AMOUNT_DISPLAY)
PAYMENT_LABELS = {
    CUSTOMER_TRANSFERS_NUMBER_DISPLAY: "转账笔数",
    CUSTOMER_TRANSFERS_AMOUNT_DISPLAY: "转账金额",
    CHEQUES_NUMBER_DISPLAY: CHEQUES_NUMBER_DISPLAY,
    CHEQUES_AMOUNT_DISPLAY: CHEQUES_AMOUNT_DISPLAY,
}


@dataclass(frozen=True)
class PaymentData:
    """月度_CBUAE 支付指标及其来源元数据。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
