"""不依赖 Streamlit 的当前会话工作区。"""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Any


_ASSETS_PREFIX = "workspace.assets."
_PAGES_PREFIX = "workspace.pages."
_ACTIVE_PAGE_KEY = "workspace.active_page"


@dataclass(frozen=True)
class FileAsset:
    """保存在当前会话内的原始文件资产。"""

    slot: str
    name: str
    content: bytes
    fingerprint: str


@dataclass(frozen=True)
class AssetUpdate:
    """文件槽位更新的结果。"""

    asset: FileAsset
    changed: bool


class NamedBytesIO(BytesIO):
    """带文件名的内存文件视图，供既有读取器使用。"""

    def __init__(self, content: bytes, name: str):
        super().__init__(content)
        self.name = name


class SessionWorkspace:
    """管理一次 Streamlit 会话中的文件资产和页面输入快照。"""

    def __init__(self, state: MutableMapping[str, Any]):
        self._state = state

    def put_asset(self, slot: str, file_input: Any) -> AssetUpdate:
        """把上传文件保存为原始 bytes，并报告内容是否改变。"""

        content = self._read_content(file_input)
        name = str(getattr(file_input, "name", "未命名文件"))
        fingerprint = sha256(content).hexdigest()
        previous = self.get_asset(slot)
        if previous is not None and previous.fingerprint == fingerprint:
            return AssetUpdate(asset=previous, changed=False)

        asset = FileAsset(slot=slot, name=name, content=content, fingerprint=fingerprint)
        self._state[self._asset_key(slot)] = asset
        return AssetUpdate(asset=asset, changed=True)

    def get_asset(self, slot: str) -> FileAsset | None:
        """返回指定槽位的文件资产。"""

        asset = self._state.get(self._asset_key(slot))
        return asset if isinstance(asset, FileAsset) else None

    def open_asset(self, slot: str) -> NamedBytesIO | None:
        """返回供解析器读取的、带文件名的内存文件。"""

        asset = self.get_asset(slot)
        if asset is None:
            return None
        return NamedBytesIO(asset.content, asset.name)

    def clear_asset(self, slot: str) -> bool:
        """明确删除一个文件槽位，不影响其他槽位或页面。"""

        key = self._asset_key(slot)
        if key not in self._state:
            return False
        del self._state[key]
        return True

    def begin_page(
        self,
        page_id: str,
        *,
        keys: Iterable[str] = (),
        prefixes: Iterable[str] = (),
    ) -> None:
        """恢复本页快照并登记当前渲染周期的输入规范。"""

        inputs = self._state.get(self._inputs_key(page_id), {})
        if isinstance(inputs, dict):
            for key, value in inputs.items():
                if key not in self._state:
                    self._state[key] = value
        self._state[self._spec_key(page_id)] = {
            "keys": tuple(keys),
            "prefixes": tuple(prefixes),
        }
        self._state[_ACTIVE_PAGE_KEY] = page_id

    def end_page(self, page_id: str) -> None:
        """保存本页已登记输入；活动页保留给导航边界再次快照。"""

        if self._state.get(_ACTIVE_PAGE_KEY) == page_id:
            self._snapshot_page(page_id)

    def snapshot_active_page(self) -> None:
        """保存当前活动页的已登记输入。"""

        page_id = self._state.get(_ACTIVE_PAGE_KEY)
        if isinstance(page_id, str):
            self._snapshot_page(page_id)

    def reset_page(self, page_id: str) -> None:
        """清空本页影子快照和当前已登记 widget 值。"""

        spec = self._state.get(self._spec_key(page_id), {})
        for key in self._matching_keys(spec):
            self._state.pop(key, None)
        self._state.pop(self._inputs_key(page_id), None)

    def _snapshot_page(self, page_id: str) -> None:
        spec = self._state.get(self._spec_key(page_id), {})
        self._state[self._inputs_key(page_id)] = {
            key: self._state[key]
            for key in self._matching_keys(spec)
            if key in self._state
        }

    def _matching_keys(self, spec: Any) -> set[str]:
        if not isinstance(spec, dict):
            return set()
        keys = {
            key
            for key in spec.get("keys", ())
            if isinstance(key, str)
        }
        prefixes = tuple(
            prefix
            for prefix in spec.get("prefixes", ())
            if isinstance(prefix, str)
        )
        if prefixes:
            keys.update(
                key
                for key in self._state
                if isinstance(key, str) and key.startswith(prefixes)
            )
        return keys

    @staticmethod
    def _read_content(file_input: Any) -> bytes:
        if file_input is None:
            raise TypeError("文件输入不能为空")
        position = None
        if hasattr(file_input, "tell") and hasattr(file_input, "seek"):
            position = file_input.tell()
        if hasattr(file_input, "getvalue"):
            content = file_input.getvalue()
        elif hasattr(file_input, "read"):
            content = file_input.read()
        else:
            raise TypeError("文件输入必须提供 getvalue() 或 read()")
        if position is not None:
            file_input.seek(position)
        if not isinstance(content, bytes):
            raise TypeError("文件输入必须提供 bytes 内容")
        return content

    @staticmethod
    def _asset_key(slot: str) -> str:
        return f"{_ASSETS_PREFIX}{slot}"

    @staticmethod
    def _inputs_key(page_id: str) -> str:
        return f"{_PAGES_PREFIX}{page_id}.inputs"

    @staticmethod
    def _spec_key(page_id: str) -> str:
        return f"{_PAGES_PREFIX}{page_id}.spec"


__all__ = ["AssetUpdate", "FileAsset", "NamedBytesIO", "SessionWorkspace"]
