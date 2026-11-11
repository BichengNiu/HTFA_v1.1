"""DFM 导出文件的存储与序列化。"""
import io
import os
import pickle
import tempfile
from pathlib import Path
import joblib
import pandas as pd

def create_output_directory(path=None, *, prefix="dfm_results_"):
    """创建输出目录；未指定路径时使用临时目录。"""
    if path is None:
        return tempfile.mkdtemp(prefix=prefix)
    os.makedirs(path, exist_ok=True)
    return path

def save_model(model, path):
    """保存训练模型。"""
    joblib.dump(model, path, compress=3)

def save_metadata(metadata, path):
    """保存已验证的模型元数据。"""
    with open(path, 'wb') as stream:
        pickle.dump(metadata, stream, protocol=pickle.HIGHEST_PROTOCOL)

def save_text(text, path):
    """保存 UTF-8 文本。"""
    Path(path).write_text(text, encoding='utf-8')

def write_csv(frame, path, *, heading=""):
    """保存带可选说明的 UTF-8 BOM CSV。"""
    with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
        stream.write(heading)
        frame.to_csv(stream, index=False)

def serialize_prepared_workbook(data, mapping):
    """将处理后的数据与映射序列化为 Excel。"""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        data.to_excel(writer, sheet_name='数据', index=True, index_label='Date')
        mapping.to_excel(writer, sheet_name='映射', index=False)
    return buffer.getvalue()
