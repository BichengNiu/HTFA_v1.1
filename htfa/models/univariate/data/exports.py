"""本功能的表格文件序列化。"""
import pandas as pd


def serialize_workbook(tables: dict[str, pd.DataFrame]) -> bytes:
    """将命名表格序列化为不含行索引的 Excel 工作簿。"""
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in tables.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return output.getvalue()
