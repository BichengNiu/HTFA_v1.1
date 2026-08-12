"""数据探索静态页面。"""


def render_data_exploration_welcome_page(st_obj) -> None:
    """渲染数据探索欢迎页面。"""

    st_obj.markdown(
        """
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
        """,
        unsafe_allow_html=True,
    )


__all__ = ["render_data_exploration_welcome_page"]
