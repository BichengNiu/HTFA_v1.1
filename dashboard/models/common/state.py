"""可复用的模型工作流状态生命周期。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class StateStore(Protocol):
    """最小的命名空间状态读写协议。"""

    def get(self, key: str, default: Any = None) -> Any:
        """读取状态值。"""

    def set(self, key: str, value: Any) -> None:
        """写入状态值。"""


@dataclass(frozen=True)
class ModelStateLifecycle:
    """按拟合结果依赖关系清理模型工作流状态。

    Parameters
    ----------
    store : StateStore
        命名空间状态存储。
    fit_result_keys : tuple[str, ...]
        拟合结果及其签名键。
    downstream_result_keys : tuple[str, ...]
        诊断、预测等依赖拟合结果的键。
    widget_keys : tuple[str, ...]
        页面可清理的 Streamlit widget 键。
    """

    store: StateStore
    fit_result_keys: tuple[str, ...]
    downstream_result_keys: tuple[str, ...]
    widget_keys: tuple[str, ...]

    def clear_fit_results(self) -> None:
        """清除拟合结果及全部下游结果。"""
        self._clear(self.fit_result_keys)
        self.clear_downstream_results()

    def store_fit_result(self, result: Any, signature: Any) -> None:
        """发布新的拟合结果并原子地清除全部下游结果。"""
        if len(self.fit_result_keys) != 2:
            raise ValueError("fit_result_keys 必须包含结果键和签名键")
        self.store.set(self.fit_result_keys[0], result)
        self.store.set(self.fit_result_keys[1], signature)
        self.clear_downstream_results()

    def clear_downstream_results(self) -> None:
        """清除诊断、预测等下游结果。"""
        self._clear(self.downstream_result_keys)

    def clear_widget_state(self, st_obj, keys: tuple[str, ...] | None = None) -> None:
        """只删除声明过的 widget 状态，保留无关页面状态。"""
        session = getattr(st_obj, "session_state", None)
        if session is None:
            return
        allowed = set(self.widget_keys)
        selected = self.widget_keys if keys is None else keys
        for key in selected:
            if key in allowed:
                session.pop(key, None)

    def _clear(self, keys: tuple[str, ...]) -> None:
        for key in keys:
            self.store.set(key, None)


__all__ = ["ModelStateLifecycle", "StateStore"]
