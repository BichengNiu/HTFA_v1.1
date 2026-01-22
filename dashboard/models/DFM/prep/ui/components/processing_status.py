# -*- coding: utf-8 -*-
"""
DFM数据处理状态组件

提供数据处理执行、进度监控、状态展示和结果下载功能
"""

import streamlit as st
import pandas as pd
import io
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from dashboard.models.DFM.ui import DFMComponent
from dashboard.models.DFM.prep import prepare_dfm_data_simple
from dashboard.models.DFM.prep.api import load_mappings_once


logger = logging.getLogger(__name__)


class ProcessingStatusComponent(DFMComponent):
    """DFM数据处理状态组件"""
    
    def __init__(self):
        """初始化数据处理状态组件"""
        super().__init__()
        self._processing_stages = [
            "正在执行数据预处理...",
            "数据预处理完成，正在生成结果...",
            "正在处理结果数据...",
            "处理完成！"
        ]
    
    def get_component_id(self) -> str:
        """获取组件ID"""
        return "processing_status"
    
    def get_state_keys(self) -> list:
        """
        获取组件相关的状态键
        
        Returns:
            List[str]: 状态键列表
        """
        return [
            'dfm_export_base_name',
            'dfm_processing_status',
            'dfm_processing_progress',
            'dfm_processed_outputs',
            'dfm_prepared_data_df',
            'dfm_transform_log_obj',
            'dfm_industry_map_obj',
            'dfm_removed_vars_log_obj',
            'dfm_var_type_map_obj'
        ]
    
    def validate_input(self, data: Dict) -> bool:
        """
        验证输入数据
        
        Args:
            data: 输入数据字典，包含处理参数
            
        Returns:
            bool: 验证是否通过
        """
        try:
            # 检查必需参数
            required_params = [
                'export_base_name',
                'target_freq',
                'target_sheet_name',
                'target_variable',
                'data_start_date',
                'data_end_date',
                'type_mapping_sheet'
            ]
            
            for param in required_params:
                if param not in data or data[param] is None:
                    logger.warning(f"缺少必需参数: {param}")
                    return False
            
            # 验证导出名称不为空
            if not isinstance(data.get('export_base_name'), str) or not data['export_base_name'].strip():
                logger.warning("导出基础名称不能为空")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"参数验证失败: {e}")
            return False
    
    def handle_service_error(self, error: Exception) -> None:
        """
        处理服务错误
        
        Args:
            error: 异常对象
        """
        error_msg = f"数据处理服务错误: {str(error)}"
        logger.error(error_msg)
        st.error(error_msg)
    
    def render(self, st_obj) -> Optional[Dict[str, Any]]:
        """
        渲染数据处理状态组件
        
        Args:
            st_obj: Streamlit对象
            
        Returns:
            处理结果字典或None
        """
        try:
            st_obj.markdown("### [START] 数据处理与导出")
            
            # 渲染导出名称输入
            export_name = self._render_export_name_input(st_obj)
            
            # 渲染处理按钮和状态
            processing_result = self._render_processing_interface(st_obj)
            
            # 渲染下载按钮
            self._render_download_buttons(st_obj)
            
            return processing_result
                
        except Exception as e:
            self.handle_service_error(e)
            return None
    
    def _render_export_name_input(self, st_obj) -> str:
        """
        渲染导出名称输入
        
        Args:
            st_obj: Streamlit对象
            
        Returns:
            导出名称
        """
        export_name = st_obj.text_input(
            "导出文件基础名称",
            value=self._get_state('dfm_export_base_name', 'dfm_prepared_output'),
            key=f"{self.get_state_key_prefix()}_export_name_input",
            help="设置导出文件的基础名称，实际文件名会添加相应后缀"
        )
        
        # 保存到状态管理器
        self._set_state('dfm_export_base_name', export_name)
        
        return export_name
    
    def _render_processing_interface(self, st_obj) -> Optional[Dict[str, Any]]:
        """
        渲染处理界面
        
        Args:
            st_obj: Streamlit对象
            
        Returns:
            处理结果或None
        """
        if st_obj.button("运行数据预处理", 
                        key=f"{self.get_state_key_prefix()}_run_processing",
                        help="开始执行数据预处理流程"):
            
            # 获取所有处理参数
            processing_params = self._get_all_processing_params()
            
            # 验证参数
            if not self.validate_input(processing_params):
                st_obj.error("处理参数验证失败，请检查所有必需参数是否已正确设置。")
                return None
            
            # 创建进度指示器
            progress_bar = st_obj.progress(0)
            status_text = st_obj.empty()
            
            try:
                # 执行数据处理
                success = self._execute_data_processing(processing_params, progress_bar, status_text)
                
                if success:
                    # 完成进度指示器
                    self._update_processing_progress(progress_bar, status_text, 100, "[SUCCESS] 处理完成！")
                    
                    # 短暂延迟后清除进度指示器
                    import time
                    time.sleep(1)
                    progress_bar.empty()
                    status_text.empty()
                    
                    st_obj.success("[SUCCESS] 数据预处理完成！请查看下方的下载选项。")
                    
                    return self._get_state('dfm_processed_outputs')
                else:
                    progress_bar.empty()
                    status_text.empty()
                    return None
                    
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                self.handle_service_error(e)
                return None
        
        return None
    
    def _get_all_processing_params(self) -> Dict[str, Any]:
        """
        获取所有处理参数
        
        Returns:
            处理参数字典
        """
        return {
            'export_base_name': self._get_state('dfm_export_base_name', 'dfm_prepared_output'),
            'target_freq': self._get_state('dfm_param_target_freq', 'W-FRI'),
            'target_sheet_name': self._get_state('dfm_param_target_sheet_name', ''),
            'target_variable': self._get_state('dfm_param_target_variable', ''),
            'consecutive_nan_threshold': self._get_state('dfm_param_consecutive_nan_threshold', 10),
            'remove_consecutive_nans': self._get_state('dfm_param_remove_consecutive_nans', True),
            'data_start_date': self._get_state('dfm_param_data_start_date', '2020-01-01'),
            'data_end_date': self._get_state('dfm_param_data_end_date', '2025-04-30'),
            'type_mapping_sheet': self._get_state('dfm_param_type_mapping_sheet', '指标字典')
        }
    
    def _execute_data_processing(self, processing_params: Dict[str, Any], 
                               progress_bar, status_text) -> bool:
        """
        执行数据处理
        
        Args:
            processing_params: 处理参数
            progress_bar: 进度条对象
            status_text: 状态文本对象
            
        Returns:
            bool: 处理是否成功
        """
        try:
            # 获取上传的文件
            uploaded_file = self._get_state('dfm_training_data_file')
            if uploaded_file is None:
                st.error("未找到上传的数据文件，请先上传文件。")
                return False
            
            # 更新进度：开始处理
            self._update_processing_progress(progress_bar, status_text, 10, "[CONFIG] 正在准备数据处理...")
            
            # 准备文件对象
            file_bytes = uploaded_file.getvalue()
            excel_file_like_object = io.BytesIO(file_bytes)
            
            # 处理NaN阈值
            nan_threshold_int = None
            if processing_params['remove_consecutive_nans']:
                try:
                    nan_threshold_int = int(processing_params['consecutive_nan_threshold'])
                except (ValueError, TypeError):
                    logger.warning("连续NaN阈值无效，将忽略此设置")
                    nan_threshold_int = None
            
            # 更新进度：执行预处理
            self._update_processing_progress(progress_bar, status_text, 30, "[CONFIG] 正在执行数据预处理...")

            # 调用数据预处理函数
            result = prepare_dfm_data_simple(
                uploaded_file=excel_file_like_object,
                target_variable_name=processing_params['target_variable'],
                data_start_date=str(processing_params['data_start_date']),
                data_end_date=str(processing_params['data_end_date']),
                target_freq=processing_params['target_freq'],
                consecutive_nan_threshold=nan_threshold_int,
                reference_sheet_name=processing_params['type_mapping_sheet']
            )

            # 更新进度：处理结果
            self._update_processing_progress(progress_bar, status_text, 70, "[SUCCESS] 数据预处理完成，正在生成结果...")

            if result['status'] == 'success':
                # 从result中提取数据
                prepared_data = result['data']
                industry_map = result['metadata']['variable_mapping']
                transform_log = result['metadata']['transform_log']
                removed_variables_detailed_log = result['metadata']['removal_log']
                
                # 更新进度：分析结果
                self._update_processing_progress(progress_bar, status_text, 80, "[INFO] 正在处理结果数据...")
                
                # 分析移除的变量
                if removed_variables_detailed_log:
                    self._analyze_removed_variables(st, removed_variables_detailed_log, nan_threshold_int)
                
                # 加载映射数据（不影响主要数据处理流程）
                try:
                    mapping_file = excel_file_like_object
                    if mapping_file is None:
                        # 尝试从状态管理器获取已存在的文件
                        existing_file = self._get_state('dfm_training_data_file')
                        if existing_file is not None:
                            mapping_file = existing_file
                            logger.info("使用已存在的文件进行映射数据加载")

                    if mapping_file is not None:
                        self._load_mapping_data(mapping_file, processing_params['type_mapping_sheet'])
                    else:
                        logger.warning("没有可用的文件进行映射数据加载")
                        st.warning("[WARNING] 没有可用的文件进行映射数据加载")
                except Exception as e:
                    logger.warning(f"映射数据加载失败，但数据处理继续: {e}")
                    st.warning(f"[WARNING] 映射数据加载失败: {e}，但数据处理已完成")
                
                # 格式化处理结果
                processed_outputs = self._format_processing_results(
                    processing_params['export_base_name'],
                    prepared_data,
                    industry_map,
                    transform_log,
                    removed_variables_detailed_log
                )
                
                # 保存结果到状态管理器（不覆盖已保存的完整映射数据）
                self._save_processing_results(processed_outputs, prepared_data, transform_log,
                                            None, removed_variables_detailed_log)  # 传入None避免覆盖映射数据
                
                return True
            else:
                st.error(f"数据预处理失败: {result.get('message', '未知错误')}")
                self._clear_processing_results()
                return False
                
        except Exception as e:
            logger.error(f"数据处理执行失败: {e}")
            st.error(f"数据处理过程中发生错误: {e}")
            self._clear_processing_results()
            return False
    
    def _update_processing_progress(self, progress_bar, status_text, progress: int, message: str) -> None:
        """
        更新处理进度
        
        Args:
            progress_bar: 进度条对象
            status_text: 状态文本对象
            progress: 进度百分比
            message: 状态消息
        """
        try:
            progress_bar.progress(progress)
            status_text.text(message)
            
            # 保存进度到状态管理器
            self._set_state('dfm_processing_progress', progress)
            self._set_state('dfm_processing_status', message)
            
        except Exception as e:
            logger.error(f"更新进度失败: {e}")
    
    def _analyze_removed_variables(self, st_obj, removed_variables_log: List[Dict], 
                                 nan_threshold: Optional[int]) -> None:
        """
        分析移除的变量
        
        Args:
            st_obj: Streamlit对象
            removed_variables_log: 移除变量日志
            nan_threshold: NaN阈值
        """
        try:
            # 统计连续NaN移除的变量
            nan_removed = [item for item in removed_variables_log 
                          if 'consecutive_nan' in item.get('Reason', '').lower()]
            
            if nan_removed and nan_threshold is not None:
                st_obj.info(f"注意: {len(nan_removed)} 个变量因连续缺失值 ≥ {nan_threshold} 被移除。")
            
            # 显示详细的移除信息
            if len(removed_variables_log) > 0:
                with st_obj.expander("[VIEW] 查看被移除的变量详情", expanded=False):
                    removal_reasons = {}
                    for item in removed_variables_log:
                        reason = item.get('Reason', 'unknown')
                        if reason not in removal_reasons:
                            removal_reasons[reason] = []
                        removal_reasons[reason].append(item.get('Variable', 'unknown'))
                    
                    for reason, vars_list in removal_reasons.items():
                        st_obj.write(f"**{reason}**: {len(vars_list)} 个变量")
                        if 'consecutive_nan' in reason.lower():
                            st_obj.error(f"因连续缺失值过多被移除: {vars_list[:10]}")
                        else:
                            st_obj.write(f"变量: {vars_list[:5]}")
                            
        except Exception as e:
            logger.error(f"分析移除变量失败: {e}")
    
    def _load_mapping_data(self, excel_file, mapping_sheet_name: str) -> None:
        """
        加载映射数据

        Args:
            excel_file: Excel文件对象
            mapping_sheet_name: 映射表名称
        """
        try:
            result = load_mappings_once(
                excel_path=excel_file,
                reference_sheet_name=mapping_sheet_name,
                reference_column_name='指标名称'
            )

            if result['status'] != 'success':
                raise ValueError(result['message'])

            mappings = result['mappings']

            # 保存映射数据
            final_industry_map = mappings.get('var_industry_map', {})
            final_type_map = mappings.get('var_type_map', {})
            final_single_stage_map = mappings.get('single_stage_map', {})
            final_two_stage_map = mappings.get('second_stage_target_map', {})

            self._set_state("dfm_var_type_map_obj", final_type_map)
            self._set_state("dfm_industry_map_obj", final_industry_map)
            self._set_state("dfm_default_predictor_map", final_single_stage_map)
            self._set_state("dfm_target_variable_map", final_two_stage_map)

            st.info(f"[SUCCESS] 已成功加载映射：类型映射 {len(final_type_map)} 个，行业映射 {len(final_industry_map)} 个，预测变量 {len(final_single_stage_map)} 个，目标变量 {len(final_two_stage_map)} 个")

        except Exception as e:
            logger.error(f"加载映射数据失败: {e}")
            st.error(f"映射数据加载失败: {e}")
            self._set_state("dfm_var_type_map_obj", {})
            self._set_state("dfm_industry_map_obj", {})
            self._set_state("dfm_default_predictor_map", {})
            self._set_state("dfm_target_variable_map", {})
            raise RuntimeError(f"映射数据加载失败: {e}")

    def _format_processing_results(self, base_name: str, prepared_data: pd.DataFrame,
                                 industry_map: Dict, transform_log: Dict,
                                 removed_vars_log: List[Dict]) -> Dict[str, Any]:
        """
        格式化处理结果

        Args:
            base_name: 基础文件名
            prepared_data: 处理后的数据
            industry_map: 行业映射
            transform_log: 转换日志
            removed_vars_log: 移除变量日志

        Returns:
            格式化的处理结果
        """
        try:
            processed_outputs = {
                'base_name': base_name,
                'data': None,
                'industry_map': None,
                'transform_log': None,
                'removed_vars_log': None
            }

            # 处理主数据
            if prepared_data is not None and not prepared_data.empty:
                processed_outputs['data'] = prepared_data.to_csv(
                    index=False, encoding='utf-8-sig'
                ).encode('utf-8-sig')

            # 处理行业映射
            if industry_map:
                try:
                    industry_df = pd.DataFrame(list(industry_map.items()),
                                             columns=['Variable', 'Industry'])
                    processed_outputs['industry_map'] = industry_df.to_csv(
                        index=False, encoding='utf-8-sig'
                    ).encode('utf-8-sig')
                except Exception as e:
                    logger.warning(f"处理行业映射失败: {e}")
                    processed_outputs['industry_map'] = None

            # 处理转换日志
            if transform_log:
                try:
                    # 尝试格式化转换日志
                    if isinstance(transform_log, dict):
                        formatted_log_data = []
                        for var, actions in transform_log.items():
                            if isinstance(actions, list):
                                for action in actions:
                                    formatted_log_data.append({
                                        'Variable': var,
                                        'Action': str(action)
                                    })
                            else:
                                formatted_log_data.append({
                                    'Variable': var,
                                    'Action': str(actions)
                                })

                        if formatted_log_data:
                            transform_df = pd.DataFrame(formatted_log_data)
                            processed_outputs['transform_log'] = transform_df.to_csv(
                                index=False, encoding='utf-8-sig'
                            ).encode('utf-8-sig')
                        else:
                            processed_outputs['transform_log'] = json.dumps(
                                transform_log, ensure_ascii=False, indent=4
                            ).encode('utf-8-sig')
                    else:
                        processed_outputs['transform_log'] = json.dumps(
                            transform_log, ensure_ascii=False, indent=4
                        ).encode('utf-8-sig')

                except Exception as e:
                    logger.warning(f"处理转换日志失败: {e}")
                    processed_outputs['transform_log'] = None

            # 处理移除变量日志
            if removed_vars_log:
                try:
                    removed_df = pd.DataFrame(removed_vars_log)
                    processed_outputs['removed_vars_log'] = removed_df.to_csv(
                        index=False, encoding='utf-8-sig'
                    ).encode('utf-8-sig')
                except Exception as e:
                    logger.warning(f"处理移除变量日志失败: {e}")
                    processed_outputs['removed_vars_log'] = None

            return processed_outputs

        except Exception as e:
            logger.error(f"格式化处理结果失败: {e}")
            return {
                'base_name': base_name,
                'data': None,
                'industry_map': None,
                'transform_log': None,
                'removed_vars_log': None
            }

    def _save_processing_results(self, processed_outputs: Dict[str, Any],
                               prepared_data: pd.DataFrame, transform_log: Dict,
                               industry_map: Dict, removed_vars_log: List[Dict]) -> None:
        """
        保存处理结果到状态管理器

        Args:
            processed_outputs: 格式化的输出
            prepared_data: 处理后的数据
            transform_log: 转换日志
            industry_map: 行业映射（如果为None则不覆盖已有映射）
            removed_vars_log: 移除变量日志
        """
        try:
            # 保存格式化的输出
            self._set_state("dfm_processed_outputs", processed_outputs)

            # 保存原始数据对象
            self._set_state("dfm_prepared_data_df", prepared_data)
            self._set_state("dfm_transform_log_obj", transform_log)

            if industry_map is not None:
                self._set_state("dfm_industry_map_obj", industry_map)

            self._set_state("dfm_removed_vars_log_obj", removed_vars_log)

            logger.info("处理结果已保存到状态管理器")

        except Exception as e:
            logger.error(f"保存处理结果失败: {e}")

    def _clear_processing_results(self) -> None:
        """清除处理结果"""
        try:
            self._set_state("dfm_processed_outputs", None)
            self._set_state("dfm_prepared_data_df", None)
            self._set_state("dfm_transform_log_obj", None)
            self._set_state("dfm_industry_map_obj", None)
            self._set_state("dfm_removed_vars_log_obj", None)
            self._set_state("dfm_var_type_map_obj", None)

            logger.info("处理结果已清除")

        except Exception as e:
            logger.error(f"清除处理结果失败: {e}")

    def _render_download_buttons(self, st_obj) -> None:
        """
        渲染下载按钮

        Args:
            st_obj: Streamlit对象
        """
        processed_outputs = self._get_state("dfm_processed_outputs")

        if processed_outputs:
            st_obj.markdown("### 下载处理结果")

            base_name = processed_outputs['base_name']

            # 创建三列布局用于水平排列下载按钮
            col1, col2, col3 = st_obj.columns(3)

            with col1:
                if processed_outputs['data']:
                    st_obj.download_button(
                        label="下载处理后的数据",
                        data=processed_outputs['data'],
                        file_name=f"{base_name}_data_v3.csv",
                        mime='text/csv',
                        key=f"{self.get_state_key_prefix()}_download_data_csv",
                        help="下载经过预处理的主要数据文件"
                    )
                else:
                    st_obj.info("处理后的数据不可用")

            with col2:
                if processed_outputs['industry_map']:
                    st_obj.download_button(
                        label="下载行业映射",
                        data=processed_outputs['industry_map'],
                        file_name=f"{base_name}_industry_map_v3.csv",
                        mime='text/csv',
                        key=f"{self.get_state_key_prefix()}_download_industry_map_csv",
                        help="下载变量与行业的映射关系文件"
                    )
                else:
                    st_obj.info("行业映射不可用")

            with col3:
                if processed_outputs['transform_log']:
                    st_obj.download_button(
                        label="下载转换日志",
                        data=processed_outputs['transform_log'],
                        file_name=f"{base_name}_transform_log_v3.csv",
                        mime='text/csv',
                        key=f"{self.get_state_key_prefix()}_download_transform_log_csv",
                        help="下载数据转换过程的详细日志"
                    )
                else:
                    st_obj.info("转换日志不可用")

            # 第二行：移除变量日志
            if processed_outputs['removed_vars_log']:
                st_obj.download_button(
                    label="下载移除变量日志",
                    data=processed_outputs['removed_vars_log'],
                    file_name=f"{base_name}_removed_vars_log_v3.csv",
                    mime='text/csv',
                    key=f"{self.get_state_key_prefix()}_download_removed_vars_csv",
                    help="下载被移除变量的详细信息和原因"
                )

    def _get_state(self, key: str, default: Any = None) -> Any:
        """获取状态值"""
        import streamlit as st
        full_key = f'data_prep.{key}'
        return st.session_state.get(full_key, default)

    def _set_state(self, key: str, value: Any) -> None:
        """设置状态值"""
        import streamlit as st
        full_key = f'data_prep.{key}'
        st.session_state[full_key] = value
