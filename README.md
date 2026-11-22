# Antigravity 桌面版简体中文补丁

为 macOS 上的 Google Antigravity 桌面 App **2.34.0** 提供简体中文界面。已在 Apple Silicon 上验证主界面、设置页和 macOS 顶层菜单。部分动态文案和原生弹窗可能仍显示英文。

## 安装

需要已安装的 Antigravity 2.34.0、Python 3.8 或更新版本，以及 Node.js 18 或更新版本。

下载并解压本仓库源码。保存工作并按 **⌘Q** 退出 Antigravity，然后在解压目录运行：

```sh
python3 antigravity_zh_cn.py install
python3 antigravity_zh_cn.py status
```

重新打开 Antigravity 即可。脚本默认为 `/Applications/Antigravity.app`。应用安装在其他目录时，可用 `--app "/路径/Antigravity.app"` 指定。

安装脚本读取你本机的官方 ASAR，在本地生成补丁，保留原版备份后再替换。仓库和 GitHub Release 提供脚本与词典。安装前可运行 `python3 antigravity_zh_cn.py build`，单独生成 `app.zh-cn.asar`。

## 恢复英文

退出 Antigravity 后，在同一目录运行：

```sh
python3 antigravity_zh_cn.py restore
```

若 macOS 拒绝启动补丁版，先运行恢复命令。要恢复应用的官方签名，可使用 Google 提供的安装包重新安装。升级 Antigravity 后，请使用与新版本匹配的补丁。

## 来源与许可

翻译词典与 DOM 翻译引擎来自 [Antigravity-Chinese-Localization 的固定提交](https://github.com/antigravity-cn-community/Antigravity-Chinese-Localization/tree/3bbafcac43ed86e847a4e6fcbd7f2168bd54f0de)。此仓库提供本地 ASAR 构建、macOS 菜单适配、版本检查和恢复脚本。使用 [MIT 许可](LICENSE)。查看 [上游许可与版权声明](vendor/LICENSE)。
