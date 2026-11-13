# 旺销王质检放大助手

Windows + Microsoft Edge 的个人质检辅助扩展。读取当前订单扫码页，显示大图、黑色大码数、数量和当前订单备注。数量达到两双时红色加粗，无备注时自动收起备注栏。

不提交扫码、验货、打印或订单API请求，不收集账号、Cookie或订单资料。页面结构变化可能需要调整适配器。

## 安装和在线更新

从 [最新版本](https://github.com/hxs496061112/wxw-qc-helper/releases/latest) 下载 `wxw-qc-installer.zip`，解压并运行“安装或升级.cmd”。详细步骤见 [INSTALL.txt](INSTALL.txt)。

首次运行安装器，再将 `%LOCALAPPDATA%\WxwQcHelper\extension` 加载为 Edge 解压扩展。安装器会注册仅限此助手使用的本机更新组件（当前用户，无需管理员）。

以后直接点击 Edge 扩展管理页的“重新加载”：助手自动检查、下载并应用新版，图标显示 OK 后刷新业务页。失败显示 !，继续使用已安装版本。无需先点桌面更新。没有后台定时任务或常驻服务。

更新依然依赖质检电脑能访问 GitHub；不需要登录，但不能保证没有 VPN 时一定能下载。质检电脑尚需实地验证网络。详见 INSTALL.txt。

## 发布机制

- 更新源固定为本仓库 GitHub Releases，无需质检电脑登录GitHub。
- `latest.json` 是精确字节签名的发布清单；`latest.sig` 是RSA-SHA256签名。
- 固定公钥验证签名，校验ZIP与每个文件的SHA-256，拒绝不受支持路径与异常大小。
- 替换前备份，并记录事务；失败恢复旧版，中断后下次运行先恢复。
- 私钥仅在维护电脑仓库外保存，绝不提交，也不随安装包分发。
- 本仓库没有持续部署工作流。代码推送不等于发布，只有明确创建的Release才进入更新渠道。

## 维护

仓库中的 `extension/` 是正式扩展源；`manager/` 是Windows更新器；`scripts/build_release.py` 构建离线安装包和在线更新资产。

修改后提高 `extension/manifest.json` 的version，同步content.js诊断版本和安装说明。测试通过再运行构建脚本；签名私钥路径见签名脚本参数。将四个资产 `latest.json`、`latest.sig`、`wxw-qc-update.zip`、`wxw-qc-installer.zip` 一起上传为新版本Release，全部上传后再公开该Release。

不要改写已发布版本或复用版本号。发布失败时保持旧Release为latest。完整发布后，以未登录的下载请求验证签名和安装包。
