# -*- coding: utf-8 -*-
"""
文件上传组件
处理预处理数据和行业映射文件的上传与加载
"""

import streamlit as st
import pandas as pd
import unicodedata
from typing import Tuple, Optional, Dict, Any

from dashboard.models.DFM.train.ui.utils.text_helpers import normalize_variable_name


class FileUploaderComponent:
    """文件上传和加载组件"""

    def __init__(self, state_manager):
        """
        初始化文件上传组件

        Args:
            state_manager: 状态管理器，需要有get和set方法
        """
        self.state = state_manager

    def render(self, st_instance) -> Tuple[Optional[pd.DataFrame], Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str]]:
        """
        渲染文件上传UI并返回加载的数据

        Args:
            st_instance: Streamlit实例

        Returns:
            Tuple包含:
            - input_df: 预处理数据DataFrame
            - var_industry_map: 变量到行业的映射字典
            - dfm_default_map: DFM默认变量映射字典
            - var_frequency_map: 变量到频率的映射字典
            - var_unit_map: 变量到单位的映射字典
        """
        st_instance.markdown("#### 数据文件上传")

        # 检查是否已有上传的文件
        existing_excel = self.state.get('train_uploaded_excel_file', None)

        # Excel文件上传（推荐方式）
        uploaded_excel_file = st_instance.file_uploader(
            "上传数据准备模块导出的Excel文件",
            type=['xlsx', 'xls'],
            key="train_excel_upload",
            help="包含'数据'和'映射'两个sheet的Excel文件"
        )

        if uploaded_excel_file:
            self.state.set("train_uploaded_excel_file", uploaded_excel_file)

        # 加载Excel文件
        excel_file = self.state.get('train_uploaded_excel_file', None)

        if excel_file is not None:
            # 从Excel加载数据和映射
            input_df, var_industry_map, dfm_default_map, var_frequency_map, var_unit_map = self._load_excel_file(excel_file, st_instance)

            # 显示加载成功的信息
            if input_df is not None and var_industry_map:
                st_instance.success(f"成功加载Excel文件：数据{input_df.shape[0]}行×{input_df.shape[1]}列，映射{len(var_industry_map)}个变量")
        else:
            st_instance.warning("请上传数据准备模块导出的Excel文件")
            return None, {}, {}, {}, {}

        st_instance.markdown("---")

        # 数据验证
        if not self._validate_files(input_df, var_industry_map, excel_file, None, st_instance):
            return None, {}, {}, {}, {}

        return input_df, var_industry_map, dfm_default_map, var_frequency_map, var_unit_map

    def _get_file_id(self, file_obj) -> Optional[str]:
        """生成文件标识用于缓存检测"""
        if file_obj is None:
            return None
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
        name = getattr(file_obj, 'name', 'unknown')
        return f"{name}_{size}"

    def _clear_dependent_states(self, st_instance) -> None:
        """
        清除所有依赖于旧数据的状态

        当用户上传新文件时调用，确保页面状态与新数据一致

        Args:
            st_instance: Streamlit实例（用于打印日志）
        """
        # 1. 变量选择相关状态（StateManager命名空间内）
        variable_selection_keys = [
            'dfm_selected_indicators',
            'dfm_selected_industries',
            'dfm_selected_indicators_per_industry',
            'dfm_target_variable',
            'dfm_default_variables_map',
            'dfm_industry_map_filtered',
        ]

        # 2. 训练状态相关
        training_state_keys = [
            'dfm_training_status',
            'dfm_training_log',
            'dfm_model_results_paths',
            'dfm_model_results',
            'dfm_training_result',
            'dfm_training_error',
            'dfm_training_progress',
            'dfm_training_start_time',
            'dfm_training_end_time',
            'dfm_training_completed_timestamp',
            'dfm_page_initialized',
        ]

        # 3. 日期相关状态
        date_keys = [
            'dfm_training_start_date',
            'dfm_validation_start_date',
            'dfm_validation_end_date',
            'dfm_observation_start_date',
        ]

        # 5. 清空（无额外状态需要清除）

        # 清除StateManager命名空间内的状态
        all_keys = variable_selection_keys + training_state_keys + date_keys
        cleared_count = 0
        for key in all_keys:
            if self.state.exists(key):
                self.state.delete(key)
                cleared_count += 1

        # 5. 清除直接存储在st.session_state中的widget状态
        widget_prefixes = [
            'dfm_indicators_multiselect_',
            'dfm_select_all_',
        ]

        # 6. 清除日期输入等widget的key（这些widget key直接存储在st.session_state中）
        widget_exact_keys = [
            'dfm_training_start_date_input',
            'dfm_validation_start_date_input',
            'dfm_observation_start_date_input',
            'dfm_variable_selection_method_input',
            'dfm_target_alignment_mode_input',
            'dfm_factor_selection_strategy',
            'dfm_fixed_number_of_factors',
            'dfm_cumulative_variance_threshold_input',
            'dfm_kaiser_threshold_input',
            'dfm_factor_ar_order_input',
        ]

        widget_cleared_count = 0
        keys_to_delete = []

        # 清除前缀匹配的widget
        for key in st.session_state.keys():
            for prefix in widget_prefixes:
                if key.startswith(prefix) or key.startswith(f'train_model.{prefix}'):
                    keys_to_delete.append(key)
                    break

        # 清除精确匹配的widget
        for key in widget_exact_keys:
            if key in st.session_state:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del st.session_state[key]
            widget_cleared_count += 1

        print(f"[模型训练] 状态清除完成: {cleared_count}个命名空间状态 + {widget_cleared_count}个widget状态")

    def _load_excel_file(self, excel_file, st_instance) -> Tuple[Optional[pd.DataFrame], Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str]]:
        """
        从Excel文件加载数据和映射（带缓存）

        Excel文件应包含两个sheet：
        - '数据': 预处理数据（第一列为日期索引）
        - '映射': 行业映射表（包含Indicator、Industry、Frequency、Unit等列）

        Args:
            excel_file: Excel文件对象
            st_instance: Streamlit实例

        Returns:
            Tuple包含:
            - input_df: 预处理数据DataFrame
            - var_industry_map: 变量到行业的映射字典
            - dfm_default_map: DFM默认变量映射字典
            - var_frequency_map: 变量到频率的映射字典
            - var_unit_map: 变量到单位的映射字典
        """
        if excel_file is None:
            return None, {}, {}, {}, {}

        current_file_id = self._get_file_id(excel_file)
        cached_file_id = self.state.get('cached_excel_file_id', None)
        cached_df = self.state.get('dfm_prepared_data_df', None)
        cached_industry_map = self.state.get('dfm_industry_map_obj', None)
        cached_default_map = self.state.get('dfm_default_map', None)
        cached_frequency_map = self.state.get('dfm_frequency_map_obj', None)
        cached_unit_map = self.state.get('dfm_unit_map_obj', None)

        # 检查缓存（频率映射和单位映射必须非空）
        if (cached_df is not None and cached_industry_map is not None
            and cached_frequency_map and cached_unit_map and current_file_id == cached_file_id):
            print(f"[模型训练] 使用缓存的Excel数据: 数据={cached_df.shape}, 映射={len(cached_industry_map)}个变量, 频率={len(cached_frequency_map)}个变量, 单位={len(cached_unit_map)}个变量")

            # 验证所有必需的缓存数据都存在
            if cached_default_map is None:
                print("[模型训练] 警告: 缓存的默认变量映射为空，将重新加载")
                # 不使用缓存，强制重新加载
            else:
                return cached_df, cached_industry_map, cached_default_map, cached_frequency_map, cached_unit_map

        # 检测到新文件上传，清除所有依赖旧数据的状态
        is_new_file = cached_file_id is not None and current_file_id != cached_file_id
        if is_new_file:
            print(f"[模型训练] 检测到新文件上传，清除旧数据相关状态")
            self._clear_dependent_states(st_instance)
            st_instance.info("检测到新数据文件，已重置所有配置。请重新设置模型参数。")

        # 重新加载Excel
        try:
            excel_file.seek(0)
            print(f"[模型训练] 开始加载Excel文件: {excel_file.name}")

            # 读取'数据'sheet
            print("[模型训练] 读取'数据'sheet...")
            input_df = pd.read_excel(excel_file, sheet_name='数据', index_col=0, parse_dates=True)
            print(f"[模型训练] 数据shape: {input_df.shape}, 列数: {len(input_df.columns)}")
            print(f"[模型训练] 时间范围: {input_df.index.min()} 至 {input_df.index.max()}")

            # 读取'映射'sheet
            excel_file.seek(0)
            print("[模型训练] 读取'映射'sheet...")
            industry_map_df = pd.read_excel(excel_file, sheet_name='映射')
            print(f"[模型训练] 映射表shape: {industry_map_df.shape}, 列名: {list(industry_map_df.columns)}")

            # 验证必需列
            if '指标名称' not in industry_map_df.columns or '行业' not in industry_map_df.columns or '单位' not in industry_map_df.columns:
                st_instance.error("映射表格式错误：必须包含'指标名称'、'行业'和'单位'列")
                return None, {}, {}, {}, {}

            # 解析行业映射
            var_industry_map = {}
            filtered_count = 0

            for idx, (k, v) in enumerate(zip(industry_map_df['指标名称'], industry_map_df['行业'])):
                if pd.notna(k) and pd.notna(v) and str(k).strip() and str(v).strip():
                    normalized_key = normalize_variable_name(k)
                    var_industry_map[normalized_key] = str(v).strip()
                else:
                    filtered_count += 1

            if filtered_count > 0:
                print(f"[模型训练] 过滤掉{filtered_count}行空数据")

            print(f"[模型训练] 行业映射加载完成: {len(var_industry_map)}个变量")

            if len(var_industry_map) == 0:
                st_instance.error("行业映射为空，请检查Excel文件的'映射'sheet")
                return None, {}, {}, {}, {}

            # 解析默认变量配置
            dfm_default_vars = {}
            target_map = {}

            if '预测变量' in industry_map_df.columns:
                dfm_default_vars = {
                    normalize_variable_name(k): str(v).strip()
                    for k, v in zip(industry_map_df['指标名称'], industry_map_df['预测变量'])
                    if pd.notna(k) and pd.notna(v) and str(v).strip() == '是'
                }
                print(f"[模型训练] 预测变量: {len(dfm_default_vars)}个")

            if '目标变量' in industry_map_df.columns:
                target_map = {
                    normalize_variable_name(k): str(v).strip()
                    for k, v in zip(industry_map_df['指标名称'], industry_map_df['目标变量'])
                    if pd.notna(k) and pd.notna(v) and str(v).strip() == '是'
                }
                print(f"[模型训练] 目标变量标记: {len(target_map)}个")

                if len(target_map) == 0:
                    st_instance.error("映射表'目标变量'列中未标记任何变量。请在'目标变量'列中标记至少一个变量为'是'。")
                    return None, {}, {}, {}, {}
            else:
                st_instance.error("映射表格式错误：缺少'目标变量'列。请重新运行数据准备模块导出最新版本的Excel文件。")
                with st_instance.expander("查看解决方法"):
                    st_instance.markdown("""
                    **解决步骤：**
                    1. 切换到"数据准备"页面
                    2. 重新上传原始数据文件并运行数据处理
                    3. 导出新的Excel文件（将包含'目标变量'列）
                    4. 返回此页面，上传新导出的Excel文件

                    **说明：**
                    - '目标变量'列用于标记DFM模型的预测目标
                    - 不再支持旧的'二阶段目标'列名，请使用最新格式
                    """)
                return None, {}, {}, {}, {}

            # 解析频率映射（必需）
            if '频率' not in industry_map_df.columns:
                st_instance.error("映射表格式错误：缺少'频率'列。请重新运行数据准备模块导出最新版本的Excel文件。")
                with st_instance.expander("查看解决方法"):
                    st_instance.markdown("""
                    **解决步骤：**
                    1. 切换到"数据准备"页面
                    2. 重新上传原始数据文件并运行数据处理
                    3. 导出新的Excel文件（将包含12列映射表，包括频率和单位列）
                    4. 返回此页面，上传新导出的Excel文件

                    **说明：**
                    - 混频DFM需要每个变量的频率信息（D=日度, W=周度, 10D=旬度, M=月度）
                    - 需要每个变量的单位信息（用于平稳性检测策略）
                    """)
                return None, {}, {}, {}, {}

            # 频率标签转换映射（支持中英文）
            freq_label_map = {
                'D': 'D', '日': 'D', '日度': 'D',
                'W': 'W', '周': 'W', '周度': 'W',
                '10D': '10D', '旬': '10D', '旬度': '10D',
                'M': 'M', '月': 'M', '月度': 'M'
            }

            var_frequency_map = {}
            invalid_frequencies = []
            for k, v in zip(industry_map_df['指标名称'], industry_map_df['频率']):
                if pd.notna(k) and pd.notna(v) and str(v).strip():
                    normalized_key = normalize_variable_name(k)
                    freq_raw = str(v).strip()

                    # 转换频率标签
                    freq_code = freq_label_map.get(freq_raw)
                    if freq_code:
                        var_frequency_map[normalized_key] = freq_code
                    else:
                        invalid_frequencies.append((str(k).strip(), freq_raw))

            if invalid_frequencies:
                error_msg = "检测到无效的频率标签：\n\n"
                for var_name, freq_val in invalid_frequencies[:5]:
                    error_msg += f"- 变量 '{var_name}': 频率 '{freq_val}'\n"
                if len(invalid_frequencies) > 5:
                    error_msg += f"\n... 以及其他 {len(invalid_frequencies) - 5} 个变量"
                error_msg += "\n\n有效频率标签：D/日/日度（日度）, W/周/周度（周度）, 10D/旬/旬度（旬度）, M/月/月度（月度）"
                st_instance.error(error_msg)
                return None, {}, {}, {}, {}

            if len(var_frequency_map) == 0:
                st_instance.error("频率映射为空。请检查Excel文件的'映射'sheet中'频率'列是否填写完整。")
                return None, {}, {}, {}, {}

            print(f"[模型训练] 频率映射加载完成: {len(var_frequency_map)}个变量")

            # 解析单位映射（必需）
            var_unit_map = {}
            for k, v in zip(industry_map_df['指标名称'], industry_map_df['单位']):
                if pd.notna(k) and pd.notna(v) and str(v).strip():
                    normalized_key = normalize_variable_name(k)
                    var_unit_map[normalized_key] = str(v).strip()

            if len(var_unit_map) == 0:
                st_instance.error("单位映射为空。请检查Excel文件的'映射'sheet中'单位'列是否填写完整。")
                return None, {}, {}, {}, {}

            print(f"[模型训练] 单位映射加载完成: {len(var_unit_map)}个变量")

            # 缓存数据
            self.state.set('dfm_prepared_data_df', input_df)
            self.state.set('dfm_industry_map_obj', var_industry_map)
            self.state.set('dfm_default_map', dfm_default_vars)
            self.state.set('dfm_target_map', target_map)
            self.state.set('dfm_frequency_map_obj', var_frequency_map)
            self.state.set('dfm_unit_map_obj', var_unit_map)
            self.state.set('cached_excel_file_id', current_file_id)

            print("[模型训练] Excel文件加载成功并已缓存")

            return input_df, var_industry_map, dfm_default_vars, var_frequency_map, var_unit_map

        except ValueError as e:
            if "Worksheet named" in str(e):
                st_instance.error(f"Excel文件格式错误：缺少必需的sheet。需要包含'数据'和'映射'两个sheet。")
            else:
                st_instance.error(f"加载Excel文件失败: {e}")
            import traceback
            st_instance.code(traceback.format_exc(), language="python")
            return None, {}, {}, {}, {}
        except Exception as e:
            st_instance.error(f"加载Excel文件失败: {e}")
            import traceback
            st_instance.code(traceback.format_exc(), language="python")
            return None, {}, {}, {}, {}

    def _validate_files(self, input_df, var_industry_map, excel_file, _, st_instance) -> bool:
        """验证Excel文件是否已上传并成功解析"""
        if input_df is None or not var_industry_map:
            missing_details = []

            if input_df is None:
                if excel_file is None:
                    missing_details.append("Excel文件：未上传")
                else:
                    missing_details.append("Excel文件：上传成功但解析失败，请检查文件格式")

            if not var_industry_map:
                missing_details.append("行业映射：解析失败，请检查Excel文件的'映射'sheet是否包含'指标名称'和'行业'列")

            st_instance.error(f"数据验证失败：\n\n" + "\n\n".join([f"{i+1}. {detail}" for i, detail in enumerate(missing_details)]))

            # 添加排查建议
            with st_instance.expander("查看排查建议"):
                st_instance.markdown("""
                **Excel文件要求：**
                - 包含两个sheet：'数据'和'映射'
                - '数据'sheet：第一列为日期索引，其余列为变量
                - '映射'sheet：包含'指标名称'和'行业'等列

                **常见问题：**
                - Sheet名称错误：确保sheet名称为'数据'和'映射'
                - 列名拼写错误：检查列名是否完全匹配
                - 数据为空：确保文件中有有效数据行
                """)

            return False

        return True
