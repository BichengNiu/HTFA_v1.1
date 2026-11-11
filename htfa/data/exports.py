"""表格导出文件的序列化。"""
import pandas as pd

def serialize_csv(frame: pd.DataFrame, *, index: bool = True) -> bytes:
    """将表格序列化为 Excel 可读取的 UTF-8 BOM CSV。"""
    return frame.to_csv(index=index).encode("utf-8-sig")


def serialize_workbook(tables: dict[str, pd.DataFrame]) -> bytes:
    """将命名表格序列化为不含行索引的 Excel 工作簿。"""
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in tables.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return output.getvalue()
