from __future__ import annotations

SMOOTH_WINDOW = 7
SMOOTH_POLYORDER = 2
SEARCH_SHEET = "月度_工作搜索热度"
WORK_DUBAI_COLUMN = "work in dubai"
WORK_UAE_COLUMN = "work in uae"
SEARCH_INDICATORS = (
    (WORK_DUBAI_COLUMN, "阿联酋:Google搜索热度(work in dubai)"),
    (WORK_UAE_COLUMN, "阿联酋:Google搜索热度(work in uae)"),
)
WORK_DUBAI_LABEL = "搜索“在迪拜工作”"
WORK_UAE_LABEL = "搜索“在阿联酋工作”"
SEARCH_SERIES = (
    (WORK_DUBAI_COLUMN, WORK_DUBAI_LABEL),
    (WORK_UAE_COLUMN, WORK_UAE_LABEL),
)
START_YEAR = 2023
SOURCE_TEXT = "谷歌趋势"
