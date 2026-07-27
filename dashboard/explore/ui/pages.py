"""
数据探索欢迎页面
"""


from dashboard.core.ui.components.base import UIComponent
from dashboard.core.ui.constants import UIConstants


class DataExplorationWelcomePage(UIComponent):
    """数据探索欢迎页面"""

    def __init__(self):
        super().__init__("DataExplorationWelcomePage")
        self.constants = UIConstants
        self.module_config = self.constants.SUB_MODULES["数据探索"]

    def render(self, st_obj, **_kwargs) -> None:
        """渲染数据探索欢迎页面"""
        st_obj.markdown("""
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 60vh;
            text-align: center;
        ">
            <h1 style="font-size: 3em; margin-bottom: 1rem;">欢迎使用数据探索</h1>
            <hr style="width: 50%; border: 1px solid #ccc; margin-top: 1rem;">
        </div>
        """, unsafe_allow_html=True)

    def get_state_keys(self) -> list[str]:
        """获取组件相关的状态键"""
        return []
