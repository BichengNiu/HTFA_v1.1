"""动态回归模型库的领域对象与进程内共享存储。"""

from __future__ import annotations

from collections.abc import MutableMapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from secrets import token_urlsafe
from threading import RLock
from typing import Any, Callable


SUPPORTED_MODEL_FAMILIES = ("SARIMAX", "RDL", "ARDL")
MODEL_LIBRARY_TOKEN_KEY = "model_library.token"


@dataclass(frozen=True)
class ModelContext:
    """保存模型对象之外的来源和管理上下文。"""

    dataset_fingerprint: str
    mode: str
    target: str
    exog_names: tuple[str, ...] = ()
    training_range: tuple[Any, Any] | None = None
    preprocessing: tuple[str, ...] = ()
    missing_value_method: str = "无"
    response_log: bool = False
    exog_log_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("dataset_fingerprint", self.dataset_fingerprint),
            ("mode", self.mode),
            ("target", self.target),
            ("missing_value_method", self.missing_value_method),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{name} 必须是字符串")
        if not self.target.strip():
            raise ValueError("target 不能为空")
        exog_names = tuple(str(name) for name in self.exog_names)
        exog_log_names = tuple(str(name) for name in self.exog_log_names)
        preprocessing = tuple(str(item) for item in self.preprocessing)
        if len(set(exog_names)) != len(exog_names):
            raise ValueError("exog_names 不能包含重复变量")
        if len(set(exog_log_names)) != len(exog_log_names):
            raise ValueError("exog_log_names 不能包含重复变量")
        unknown = set(exog_log_names).difference(exog_names)
        if unknown:
            raise ValueError(
                "exog_log_names 必须是 exog_names 的子集，"
                f"未知变量：{sorted(unknown)!r}"
            )
        if not isinstance(self.response_log, bool):
            raise TypeError("response_log 必须是布尔值")
        training_range = self.training_range
        if training_range is not None:
            if not isinstance(training_range, (tuple, list)) or len(
                training_range
            ) != 2:
                raise ValueError("training_range 必须是起止值二元组")
            training_range = (training_range[0], training_range[1])
        object.__setattr__(self, "exog_names", exog_names)
        object.__setattr__(self, "exog_log_names", exog_log_names)
        object.__setattr__(self, "preprocessing", preprocessing)
        object.__setattr__(self, "training_range", training_range)


@dataclass(frozen=True)
class ModelRecord:
    """模型库中的一个已保存模型记录。"""

    record_id: str
    family: str
    signature: str
    context: ModelContext
    label: str
    saved_at: datetime
    model_object: Any = field(repr=False)


class ModelLibrary:
    """保存同一模型库标识下的动态回归模型记录。"""

    def __init__(self, *, record_id_factory: Callable[[], str] = token_urlsafe) -> None:
        self._records: dict[str, ModelRecord] = {}
        self._lock = RLock()
        self._record_id_factory = record_id_factory

    @property
    def records(self) -> tuple[ModelRecord, ...]:
        """按保存时间倒序返回模型记录。"""

        with self._lock:
            return tuple(
                sorted(
                    self._records.values(),
                    key=lambda record: record.saved_at,
                    reverse=True,
                )
            )

    def save(
        self,
        model_object: Any,
        *,
        family: str,
        signature: str,
        context: ModelContext,
        label: str | None = None,
        saved_at: datetime | None = None,
    ) -> ModelRecord:
        """深拷贝并保存模型对象，按签名覆盖已有记录。"""

        self._validate_save_arguments(family, signature, context)
        saved_at = _normalise_saved_at(saved_at)
        copied_model = deepcopy(model_object)
        with self._lock:
            existing = self._record_by_signature(signature)
            if existing is None:
                record_id = str(self._record_id_factory())
                record_label = label.strip() if isinstance(label, str) else ""
                record_label = record_label or _default_label(family, context, saved_at)
            else:
                record_id = existing.record_id
                record_label = existing.label
            record = ModelRecord(
                record_id=record_id,
                family=family,
                signature=signature,
                context=context,
                label=record_label,
                saved_at=saved_at,
                model_object=copied_model,
            )
            self._records[record_id] = record
            return record

    def get(self, record_id: str) -> ModelRecord | None:
        """按记录 ID 返回模型记录。"""

        with self._lock:
            return self._records.get(record_id)

    def delete(self, record_id: str) -> bool:
        """显式删除一个模型记录。"""

        with self._lock:
            return self._records.pop(record_id, None) is not None

    def clear(self) -> int:
        """清空模型库并返回删除的记录数。"""

        with self._lock:
            count = len(self._records)
            self._records.clear()
            return count

    def _record_by_signature(self, signature: str) -> ModelRecord | None:
        return next(
            (
                record
                for record in self._records.values()
                if record.signature == signature
            ),
            None,
        )

    @staticmethod
    def _validate_save_arguments(
        family: str,
        signature: str,
        context: ModelContext,
    ) -> None:
        if family not in SUPPORTED_MODEL_FAMILIES:
            raise ValueError(
                f"模型族必须是 {SUPPORTED_MODEL_FAMILIES} 之一，got {family!r}"
            )
        if not isinstance(signature, str) or not signature.strip():
            raise ValueError("模型签名不能为空")
        if not isinstance(context, ModelContext):
            raise TypeError("context 必须是 ModelContext")


class ModelLibraryStore:
    """按不透明模型库标识共享进程内模型库。"""

    def __init__(self, *, token_factory: Callable[[], str] | None = None) -> None:
        self._libraries: dict[str, ModelLibrary] = {}
        self._lock = RLock()
        self._token_factory = token_factory or (lambda: token_urlsafe(32))

    def create(self) -> str:
        """创建一个新的模型库并返回其不透明标识。"""

        with self._lock:
            token = self._new_token()
            self._libraries[token] = ModelLibrary()
            return token

    def get(self, token: str | None) -> ModelLibrary | None:
        """返回标识对应的模型库；无效标识返回 ``None``。"""

        if not isinstance(token, str) or not token:
            return None
        with self._lock:
            return self._libraries.get(token)

    def get_or_create(self, token: str | None = None) -> tuple[str, ModelLibrary]:
        """取得现有模型库，或为缺失标识创建一个新的模型库。"""

        with self._lock:
            library = self._libraries.get(token) if isinstance(token, str) else None
            if library is not None:
                return token, library
            new_token = self._new_token()
            library = ModelLibrary()
            self._libraries[new_token] = library
            return new_token, library

    def reset(self) -> None:
        """清空进程内全部模型库，供服务重启语义和测试使用。"""

        with self._lock:
            self._libraries.clear()

    def _new_token(self) -> str:
        token = str(self._token_factory())
        while not token or token in self._libraries:
            token = str(self._token_factory())
        return token


model_library_store = ModelLibraryStore()


def ensure_model_library(
    state: MutableMapping[str, Any],
    *,
    store: ModelLibraryStore = model_library_store,
) -> tuple[str, ModelLibrary]:
    """为页面状态取得或初始化模型库标识和模型库。"""

    token, library = store.get_or_create(state.get(MODEL_LIBRARY_TOKEN_KEY))
    state[MODEL_LIBRARY_TOKEN_KEY] = token
    return token, library


def _normalise_saved_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        raise TypeError("saved_at 必须是 datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _default_label(
    family: str,
    context: ModelContext,
    saved_at: datetime,
) -> str:
    return f"{family} | {context.target} | {saved_at:%Y-%m-%d %H:%M}"


__all__ = [
    "MODEL_LIBRARY_TOKEN_KEY",
    "SUPPORTED_MODEL_FAMILIES",
    "ModelContext",
    "ModelLibrary",
    "ModelLibraryStore",
    "ModelRecord",
    "ensure_model_library",
    "model_library_store",
]
