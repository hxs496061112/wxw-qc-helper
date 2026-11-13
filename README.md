# 旺销王质检放大助手

Windows + Microsoft Edge 的个人质检辅助扩展。读取当前订单扫码页，显示大图、黑色大码数、数量和当前订单备注。数量达到两双时红色加粗，无备注时自动收起备注栏。

扫码框固定在页面左上方约四分之一宽，原单资料集中到左侧窄栏。放大图按浏览器可用高度调整，首屏为扫码记录开头留出空间。记录表保持原来的完整高度，使用浏览器右侧滚动条向下查看全部记录、验货按钮和分页，不限制为内部小滚动框。常见桌面窗口下，1–3 个 SKU 和普通备注可完整显示；极长备注或过小窗口保留滚动，不截断关键文字。扩展保留网站原来的输入框和扫码事件。

不提交扫码、验货、打印或订单API请求，不收集账号、Cookie或订单资料。页面结构变化可能需要调整适配器。

## 安装和在线更新

从 [最新版本](https://github.com/hxs496061112/wxw-qc-helper/releases/latest) 下载 `wxw-qc-installer.zip`，解压并运行“安装或升级.cmd”。安装窗口会保留成功或失败结果，核对文件和 Edge 更新组件后才报告成功；详细步骤见 [INSTALL.txt](INSTALL.txt)。

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

### 离线界面预览

没有扫码枪时，可以使用已保存的真实扫码网页修改和验证布局。在 Edge 的已扫码页面按 Ctrl+S，保存类型选择“网页，全部”，保留 HTML 和旁边的 `_files` 文件夹。构建器不访问业务网站：

```powershell
$previewDir = Join-Path $env:USERPROFILE 'Documents\旺销王质检资料\离线预览'
py scripts/build_preview.py --source "$env:USERPROFILE\Desktop\订单扫码 _ 旺销王ERP.html" --output-dir $previewDir
```

双击输出目录的 `打开预览.html` 即可，不需要 Python、扫码枪、登录或联网。默认用存档的原生页面结构、图片和数据，应用构建时 `extension/` 的插件代码。支持单款数量 1/2、两款数量 1+1/1+2、三款合并、有无备注、重复扫码、其他失败和等待结果；演练场景用克隆的原生节点构造，不是网站真实业务结果。显示模式可以切换到没有放大助手的原页面结构。

以后代码改好，用已留存的私有快照重新生成即可，无需再保存业务网页：

```powershell
py scripts/build_preview.py --snapshot "$previewDir\page-snapshot.json" --output-dir $previewDir
py tests/test_offline_preview.py
py tests/test_offline_preview.py --preview "$previewDir\打开预览.html"
```

输出包括原始网页 ZIP 备份、私有快照、预览和说明。**这些文件含现场订单和商品资料，必须留在仓库外，不能提交或上传到公开更新仓库。** 构建器拒绝向本仓库内输出，及覆盖未标记的非空目录。仓库仅保留无业务数据的构建器、模板和合成测试。

用户已另行授权将桌面存档备份到独立私有仓库 `hxs496061112/wxw-qc-private-backup`，不能与本公开更新仓库混用。本机预览已移至上面的“文档”路径，原始 HTML 与 `_files` 目录在相邻的“原始网页”目录。已登记在办公电脑 Edge 的旧桌面扩展目录仍保留，迁移前先处理其加载路径。

预览清除网站脚本、外部链接及表单提交，用限制脚本来源的 CSP 和隔离 iframe 禁止联网与跳转。只执行本地演练控制器与正式插件的界面代码；正式代码仅在预览副本中适配主机、路径和本地图片。它不加载安装更新器，也不修改已安装扩展。未保存的远程字体/小图标可能与现场不同。网站后端扫码成功、合并逻辑和接口变化仍须在质检电脑正常操作时验证。

### 构建发布

仓库中的 `extension/` 是正式扩展源；`manager/` 是Windows更新器；`scripts/build_release.py` 构建离线安装包和在线更新资产。

修改后提高 `extension/manifest.json` 的version，同步content.js诊断版本和安装说明。测试通过再运行构建脚本；签名私钥路径见签名脚本参数。将四个资产 `latest.json`、`latest.sig`、`wxw-qc-update.zip`、`wxw-qc-installer.zip` 一起上传为新版本Release，全部上传后再公开该Release。

不要改写已发布版本或复用版本号。发布失败时保持旧Release为latest。完整发布后，以未登录的下载请求验证签名和安装包。
