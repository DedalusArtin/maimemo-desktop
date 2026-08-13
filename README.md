# 墨墨背单词桌面版

> 🤖 **本项目由 AI 辅助生成**(代码、界面与文档均由 AI 编写/修改)

右下角常驻的墨墨风格单词学习悬浮窗 + 墨墨开放 API Web 端

## 功能

- **桌面悬浮窗**(`墨墨背单词.exe`):常驻屏幕角落轮播单词
  - 紧凑模式:左键 = 显示中文释义(含例句)/ 下一个;右键 = 展开学习视图;🔊 发音;◀ 回看;⏱ 自动/手动开关
  - 展开模式:词义列表 + 例句高亮 + 发音 + 认识/模糊/忘记 + 添加单词 + 云词本导入
  - 墨墨开放 API 联动:拉取今日学习单词、添加单词双向同步
  - 🔄 一键重新同步(设置面板),同步失败时悬浮窗提示具体原因(鼠标悬停状态标签可见)
  - 无 token 也能用:本地 words.txt + 有道词典自动补全音标/词义/例句(带缓存)
- **Web 端**(`web版/`):仿官方演示站的浏览器版,覆盖学习数据/单词/释义/例句/助记/云词本全部接口

## 快速开始(开发模式)

```bash
# 依赖
pip install -r requirements.txt

# 桌面悬浮窗
python app.py

# Web 端(自动打开 http://127.0.0.1:8790)
cd web版 && python server.py
```

## 墨墨开放 API 配置

1. 手机墨墨背单词 App:我的 → 更多设置 → 实验功能 → 开放 API,获取 token
2. 把 token 填入 `config.json`(已被 gitignore,模板见 `config.example.json`)
3. 需在 App 开启"自动同步",且当日先打开过一次 App 才会初始化今日词表

接口文档:https://open.maimemo.com/#/
OpenAPI 规范:https://open.maimemo.com/api_bundle.yaml

## 打包

### 1. PyInstaller 打包 exe

```bash
pyinstaller --noconfirm --clean --windowed --name 墨墨背单词 \
  --collect-all webview --collect-all cffi --hidden-import clr_loader.ffi.cffi \
  --add-data "web;web" app.py
```

(注意:pywebview 6 在 Windows 依赖 pythonnet + cffi,打包必须带上 `--collect-all cffi`)

### 2. Inno Setup 制作安装程序

安装 [Inno Setup](https://jrsoftware.org/isinfo.php) 后:

```bash
# 先确认 dist 产物复制到项目根目录(墨墨背单词.exe + _internal/)
ISCC.exe installer\installer.iss
```

安装包输出到 `安装包\`(含卸载程序,设置→应用 可卸载)。

## 说明

- `words.txt` 本地词表(每行 `单词 | 释义`)
- `mastered.txt` 已掌握单词(自动记录)
- `review.json` 模糊词间隔复习状态(自动记录)
- 频控:20次/10秒、40次/60秒、2000次/5小时 —— 程序已做缓存
- 隐私:token 只存在本地 `config.json`,本项目不收集、不上传任何个人数据
