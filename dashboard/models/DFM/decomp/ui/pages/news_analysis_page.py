# -*- coding: utf-8 -*-
"""
DFM影响分解页面 - 纽约联储风格

完全重构版本，采用上下布局：图在上，表在下
"""

import streamlit as st
import pandas as pd
import traceback
from datetime import datetime
from typing import Dict, Any

# 导入影响分解执行函数
from dashboard.models.DFM.decomp import execute_news_analysis


def get_dfm_state(key, default=None):
    """获取DFM状态值"""
    full_key = f'news_analysis.{key}'
    return st.session_state.get(full_key, default)


def set_dfm_state(key, value):
    """设置DFM状态值"""
    full_key = f'news_analysis.{key}'
    st.session_state[full_key] = value


def render_dfm_news_analysis_page(st_module: Any) -> Dict[str, Any]:
    """
    渲染纽约联储风格的影响分解页面

    Args:
        st_module: Streamlit模块

    Returns:
        渲染结果字典
    """
    try:

        # 文件上传区域
        st_module.markdown("### 模型文件上传")

        col_model, col_metadata = st_module.columns(2)

        with col_model:
            st_module.markdown("**模型文件 (.joblib)**")
            uploaded_model_file = st_module.file_uploader(
                "选择模型文件",
                type=['joblib'],
                key="news_model_upload",
                help="上传模型训练模块导出的DFM模型文件"
            )

            if uploaded_model_file:
                set_dfm_state("dfm_model_file_news", uploaded_model_file)
            else:
                existing_model = get_dfm_state('dfm_model_file_news', None)
                if existing_model is not None and hasattr(existing_model, 'name'):
                    st_module.info(f"当前文件: {existing_model.name}")

        with col_metadata:
            st_module.markdown("**元数据文件 (.pkl)**")
            uploaded_metadata_file = st_module.file_uploader(
                "选择元数据文件",
                type=['pkl'],
                key="news_metadata_upload",
                help="上传模型训练模块导出的元数据文件"
            )

            if uploaded_metadata_file:
                set_dfm_state("dfm_metadata_file_news", uploaded_metadata_file)
            else:
                existing_metadata = get_dfm_state('dfm_metadata_file_news', None)
                if existing_metadata is not None and hasattr(existing_metadata, 'name'):
                    st_module.info(f"当前文件: {existing_metadata.name}")

        st_module.markdown("---")

        # 检查文件是否已上传
        model_file = get_dfm_state('dfm_model_file_news', None)
        metadata_file = get_dfm_state('dfm_metadata_file_news', None)

        if model_file is None or metadata_file is None:
            missing = []
            if model_file is None:
                missing.append("模型文件")
            if metadata_file is None:
                missing.append("元数据文件")
            st_module.warning(f"缺少必要文件: {', '.join(missing)}。请上传后再继续。")
            return {'status': 'error', 'error': '缺少模型文件'}

        # 参数设置区域，获取用户选择的目标月份
        selected_target_month = _render_parameter_section(st_module)

        # 执行按钮和结果渲染
        if st_module.button("执行影响分解", type="primary", width='stretch', key="execute_news_analysis_btn"):
            result = _execute_analysis(st_module, model_file, metadata_file, selected_target_month)
            # 如果分析成功，直接渲染结果，不使用rerun
            if result and result['returncode'] == 0:
                _render_results(st_module, result)
        else:
            # 非按钮点击时，检查是否有已完成的分析结果
            if get_dfm_state('news_analysis_completed', False):
                _render_results(st_module)

        return {'status': 'success', 'page': 'news_analysis'}

    except Exception as e:
        st_module.error(f"页面渲染失败: {str(e)}")
        return {'status': 'error', 'error': str(e)}


def _render_parameter_section(st_module):
    """渲染参数设置区域，返回用户选择的目标月份"""
    import joblib
    import io

    # 1. 尝试从session_state获取已选月份
    current_target_month = get_dfm_state('news_target_month', None)

    if current_target_month:
        default_value = datetime.strptime(current_target_month, '%Y-%m').replace(day=1)
    else:
        # 2. 从元数据获取最新数据月份 (observation_period_end是实际最新数据日期)
        metadata_file = get_dfm_state('dfm_metadata_file_news', None)
        metadata_file.seek(0)
        metadata = joblib.load(io.BytesIO(metadata_file.read()))
        metadata_file.seek(0)
        end_date_str = metadata['observation_period_end']
        default_value = pd.to_datetime(end_date_str).to_pydatetime().replace(day=1)

    target_date = st_module.date_input(
        "**目标月份**",
        value=default_value,
        key="news_target_month_selector",
        help="选择要分析的目标月份"
    )

    # 更新状态并返回选择的月份
    selected_month = target_date.strftime('%Y-%m')
    set_dfm_state('news_target_month', selected_month)

    return selected_month


def _execute_analysis(st_module, model_file, metadata_file, target_month):
    """执行影响分解，返回结果"""
    with st_module.spinner("正在执行影响分解，请稍候..."):
        try:
            # 调用后端API
            result = execute_news_analysis(
                dfm_model_file_content=model_file.getbuffer(),
                dfm_metadata_file_content=metadata_file.getbuffer(),
                target_month=target_month
            )

            if result['returncode'] == 0:
                serializable_result = {
                    'returncode': result['returncode'],
                    'csv_paths': result['csv_paths'],
                    'csv_contents': result['csv_contents'],
                    'summary': result['summary'],
                    'data_flow': result['data_flow'],
                    'workspace_dir': result['workspace_dir']
                }

                # 保存结果到状态（用于页面刷新后恢复）
                set_dfm_state('news_analysis_completed', True)
                set_dfm_state('news_analysis_result', serializable_result)
                set_dfm_state('news_target_month_executed', target_month)

                st_module.success("分析执行成功！")
                return serializable_result
            else:
                st_module.error(f"分析执行失败: {result['error_message']}")
                return None

        except Exception as e:
            st_module.error(f"执行过程中发生错误: {str(e)}")
            st_module.code(traceback.format_exc(), language="python")
            return None


def _render_results(st_module, result=None):
    """渲染分析结果"""
    if result is None:
        result = get_dfm_state('news_analysis_result')

    st_module.markdown("---")
    _render_summary_cards(st_module, result)
    st_module.markdown("---")
    _render_data_flow_table(st_module, result)
    _render_download_section(st_module, result)


def _build_variable_df(data_flow):
    """构建按指标分解DataFrame"""
    variable_stats = {}
    for date_entry in data_flow:
        for release in date_entry.get('releases', []):
            var_name = release['variable']
            industry = release['industry']
            impact = release['impact']
            if var_name not in variable_stats:
                variable_stats[var_name] = {
                    'industry': industry, 'impact': 0.0, 'count': 0,
                    'positive_impact': 0.0, 'negative_impact': 0.0
                }
            variable_stats[var_name]['impact'] += impact
            variable_stats[var_name]['count'] += 1
            if impact > 0:
                variable_stats[var_name]['positive_impact'] += impact
            elif impact < 0:
                variable_stats[var_name]['negative_impact'] += impact

    variable_data = [
        {
            '指标名称': var_name,
            '所属行业': stats['industry'],
            '净影响': stats['impact'],
            '数据发布数': stats['count'],
            '正向影响': stats['positive_impact'],
            '负向影响': stats['negative_impact']
        }
        for var_name, stats in variable_stats.items()
    ]
    df = pd.DataFrame(variable_data)
    if not df.empty:
        df = df.sort_values(by='净影响', key=abs, ascending=False)
    return df


def _build_industry_df(industry_breakdown):
    """构建按行业分解DataFrame"""
    industry_data = [
        {
            '行业': industry,
            '净影响': stats['impact'],
            '数据发布数': stats['count'],
            '正向影响': stats['positive_impact'],
            '负向影响': stats['negative_impact']
        }
        for industry, stats in industry_breakdown.items()
    ]
    df = pd.DataFrame(industry_data)
    if not df.empty:
        df = df.sort_values(by='净影响', key=abs, ascending=False)
    return df


def _render_data_flow_table(st_module, result):
    """渲染数据发布影响明细表（按指标聚合）"""
    data_flow = result['data_flow']

    if not data_flow:
        st_module.info("没有数据流信息")
        return

    variable_df = _build_variable_df(data_flow)
    if variable_df.empty:
        st_module.info("没有数据发布记录")
        return

    st_module.markdown("##### 按指标分解")
    st_module.dataframe(variable_df, width='stretch', hide_index=True)


def _render_summary_cards(st_module, result):
    """渲染统计摘要卡片"""
    summary = result['summary']

    st_module.markdown("##### 影响摘要")
    start_date = summary['analysis_start']
    end_date = summary['analysis_end']
    if start_date and end_date:
        st_module.info(f"以下指标基于 {start_date} 至 {end_date} 期间的数据计算")

    col1, col2, col3, col4, col5, col6 = st_module.columns(6)

    with col1:
        st_module.metric(
            label="数据发布数",
            value=f"{summary['total_releases']}",
            help="分析期内发布的数据点数量"
        )

    with col2:
        st_module.metric(
            label="首次预测",
            value=f"{summary['first_nowcast']:.4f}",
            help="目标月份的首次Nowcast预测值"
        )

    with col3:
        st_module.metric(
            label="正向影响",
            value=f"{summary['positive_impact_sum']:.4f}",
            delta="+",
            delta_color="inverse",
            help="提升nowcast值的数据发布净影响"
        )

    with col4:
        st_module.metric(
            label="负向影响",
            value=f"{summary['negative_impact_sum']:.4f}",
            delta="-",
            delta_color="inverse",
            help="降低nowcast值的数据发布净影响"
        )

    with col5:
        st_module.metric(
            label="净影响",
            value=f"{summary['total_impact']:.4f}",
            help="所有数据发布对nowcast的累积影响"
        )

    with col6:
        st_module.metric(
            label="最新预测",
            value=f"{summary['last_nowcast']:.4f}",
            help="目标月份的最新Nowcast预测值"
        )

    # 算法说明
    with st_module.expander("算法说明"):
        st_module.markdown("""
**影响值（Impact）**：表示该数据发布导致目标变量预测值的变动量（可正可负）。

**计算公式**：

```
影响值 = [λ_y' × K_t[:, i] × (观测值 - 期望值)] × σ_y
```

**分步计算过程**：
1. **因子状态变化**：`Δf = K_t[:, i] × v_i`，其中 v_i = 观测值 - 期望值（新息）
2. **目标变量变化**（标准化尺度）：`Δy_标准化 = λ_y' × Δf`
3. **反标准化**（原始尺度）：`影响值 = Δy_标准化 × σ_y`

**参数说明**：
- `λ_y`：目标变量的因子载荷向量（n_factors维），从因子载荷矩阵H中提取
- `K_t[:, i]`：第t期卡尔曼增益矩阵的第i列（n_factors维），表示变量i对各因子的影响权重
- `新息（News）`：观测值与卡尔曼滤波先验预测的偏差，正向新息表示数据好于预期
- `σ_y`：目标变量的标准差，用于将标准化尺度转换回原始尺度

**性质**：
- 影响值 > 0：该数据发布提升了预测值
- 影响值 < 0：该数据发布降低了预测值
- **加性分解**：所有变量的影响值之和严格等于预测值的总变动量

**示例**：GDP增长率预测从5.0%变为5.2%（总变动+0.2个百分点），其中工业增加值影响值为+0.15，出口影响值为+0.05，则工业增加值贡献了75%的预测变动。
        """)

    # 行业分解
    industry_breakdown = summary['industry_breakdown']
    if industry_breakdown:
        st_module.markdown("##### 按行业分解")
        industry_df = _build_industry_df(industry_breakdown)
        st_module.dataframe(industry_df, width='stretch', hide_index=True)


def _render_download_section(st_module, result):
    """渲染下载区域"""
    import io

    st_module.markdown("##### 数据导出")

    summary = result['summary']
    data_flow = result['data_flow']

    # Sheet 1: 影响摘要
    summary_data = [
        {'指标': '数据发布数', '值': summary['total_releases']},
        {'指标': '首次预测', '值': summary['first_nowcast']},
        {'指标': '正向影响', '值': summary['positive_impact_sum']},
        {'指标': '负向影响', '值': summary['negative_impact_sum']},
        {'指标': '净影响', '值': summary['total_impact']},
        {'指标': '最新预测', '值': summary['last_nowcast']},
        {'指标': '分析起始日期', '值': summary.get('analysis_start', '')},
        {'指标': '分析结束日期', '值': summary.get('analysis_end', '')}
    ]
    summary_df = pd.DataFrame(summary_data)

    # Sheet 2: 按行业分解
    industry_breakdown = summary.get('industry_breakdown', {})
    industry_df = _build_industry_df(industry_breakdown)

    # Sheet 3: 按指标分解
    variable_df = _build_variable_df(data_flow)

    # 生成Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='影响摘要', index=False)
        industry_df.to_excel(writer, sheet_name='按行业分解', index=False)
        variable_df.to_excel(writer, sheet_name='按指标分解', index=False)

    target_month = get_dfm_state('news_target_month_executed', 'unknown')
    st_module.download_button(
        label="下载分析结果",
        data=output.getvalue(),
        file_name=f"影响分解_{target_month}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        key="download_impact_excel"
    )
