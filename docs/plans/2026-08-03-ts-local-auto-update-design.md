# Ts 本地启动自动更新设计

## 目标

HTFA 通过 Windows `start.bat` 启动时检查
`https://github.com/BichengNiu/Ts` 的 `main` 分支。联网且存在新提交时，
下载并验证最新版；离线、下载失败或验证失败时，继续使用最近一次验证成功
的缓存版本，最终回退到仓库内置的 `Ts/`。

Docker 继续使用镜像内固定版本，不在容器运行时自更新。更新器不执行
`pip install`，不修改仓库内置 `Ts/`，也不依赖 UAE Excel 文件。

## 架构

`start.bat` 不再直接调用 `streamlit run`，而是调用 Python 启动器。启动器先
运行更新器，再把选定版本的父目录放到 `sys.path` 首位并预加载 `Ts`，最后
在同一 Python 进程中启动 Streamlit。预加载确保 Streamlit 后续添加项目根
目录时不会重新选择仓库内置包。

版本优先级：

1. 本次下载并通过验证的 `main` HEAD；
2. 最近一次验证成功的在线缓存版本；
3. 仓库内置 `Ts/`。

## 本地存储

运行时缓存位于：

```text
%LOCALAPPDATA%\HTFA\ts-runtime\
├── state.json
├── update.lock
└── versions\
    ├── <current-commit>\
    │   ├── metadata.json
    │   └── Ts\
    └── <previous-commit>\
        ├── metadata.json
        └── Ts\
```

内置版本由 `Ts/VENDORED.json` 描述。`state.json` 使用临时文件加
`os.replace()` 原子写入，记录最近检查、活动 commit、下载包 SHA-256 和
最近错误。

## 更新流程

1. 读取机器可读的内置版本元数据和本地状态。
2. 通过本机 Git 和已有 GitHub Credential Manager 凭据获取私有仓库
   `main` HEAD，查询超时 3 秒且禁止交互式凭据提示。
3. HEAD 已缓存且有效时直接选择该版本。
4. 发现新提交时，用 Git 浅层获取指定 commit，超时 30 秒；如果 Git、网络
   或私有仓库凭据不可用，则按离线处理。
5. 从已获取 commit 生成本地 ZIP，限制为 25 MiB；拒绝绝对路径、`..` 和
   异常 ZIP 路径，只复制根 `__init__.py` 与六个运行时子包的直接 `.py`
   文件。
6. 校验目录结构及 HTFA 使用的公共接口。
7. 使用当前 Python 在独立子进程中导入候选版本；不安装缺失依赖。
8. 验证成功后原子发布到 `versions/<commit>` 并更新状态。
9. 只保留最近两个验证成功的在线版本；清理发生在新版本成功发布之后。
10. 启动器预加载所选版本并启动 Streamlit。

## 故障策略

- 断网、DNS、HTTP、限流和超时：使用最近可用版本。
- Git 不可用、凭据失效、ZIP 损坏、路径异常、结构缺失或接口不兼容：拒绝
  候选版本并回退。
- 新版缺少第三方依赖：不运行 `pip`，记录错误并回退。
- 状态文件损坏：忽略状态，扫描验证过的缓存；仍不可用则使用内置版本。
- 缓存版本预加载失败：清理部分导入模块并回退到内置版本。
- 并发启动：文件锁保证只有一个更新器写缓存，其他启动器使用现有版本。

更新失败不阻断 HTFA；只有仓库内置版本本身也无法导入时才停止启动。

## 安全边界

- 仓库和分支固定为 `BichengNiu/Ts:main`。
- Git 只获取 `ls-remote` 返回的完整 commit SHA，不跟踪下载过程中的移动
  分支；本地生成 ZIP 并记录 SHA-256。
- 限制下载体积并防御 ZIP 路径穿越。
- 候选源码不会覆盖项目文件，只能进入专用缓存目录。
- 跟踪 `main` 仍然继承上游账号和分支的供应链风险；HTTPS、commit 固定和
  本地验证不能替代发布签名。

## 验收

- 在线发现新提交后下载、验证并在本次启动中激活。
- 已是最新版时不重复下载。
- 离线时在 3 秒检查窗口后使用最近可用版本。
- 更新失败时保持系统可启动并记录原因。
- Streamlit rerun 不重复联网检查。
- 不修改仓库内 `Ts/`，不执行 `pip install`，不读取 UAE Excel。
- 自动更新单元测试、内置包契约测试和 Ts 相关 Explore 回归全部通过。
