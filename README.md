# Travel AI Assistant

## 项目定位

本项目面向准备前往杭州旅游或正在杭州旅行的用户，根据已收集的杭州旅游资料，提供景点查询、偏好推荐、路线建议和预算参考。

## 支持的功能

- 查询已收录景点的介绍、位置和游玩信息
- 根据用户的景点偏好提供推荐
- 推荐资料中已收录的附近景点和美食
- 根据基础花销信息估算旅行预算
- 对候选路线及其预计花销进行比较
- 展示回答所依据的资料来源

## 暂不支持的功能

- 不使用爬虫自动收集旅游资料
- 不识别扫描版 PDF，不提供 OCR 功能
- 不解析图片和复杂表格
- 不提供实时天气、客流、交通和票价信息
- 不提供订票、酒店预订和支付功能
- 不保证覆盖杭州全部景点和路线
- 暂不回答杭州以外地区的旅游问题

## 第一版知识范围

第一版使用人工收集的 8～15 份杭州旅游资料，优先覆盖代表性景点、基础路线、附近美食和常见花销。系统仅根据已经导入的资料回答问题；没有资料支持的内容，应明确提示用户暂时无法回答。

# 项目结构

- app/: 项目主要代码
- data/rew/: 待处理的原始旅游资料
- logs: 程序运行日志
- tests/: 自动化测试
- .env.example: 环境变量配置示例
- requirement.txt: Python 依赖列表

# 环境与安装

建议使用python 3.10 或者更高版本

创建虚拟环境：

```powershell
python -m venv .venv
```
激活虚拟环境：
```powershell
.\.venv\Scrupts\Activate.ps1
```
安装依赖：
```powershell
python -m pip install -r requirements.txt
```

## 当前支持的文档处理

- 读取 UTF-8 编码的 TXT 和 Markdown 文件
- 按自然段整理 TXT 和 Markdown 内容
- 使用 pypdf 逐页提取文字型 PDF
- 保留 PDF 的真实页码和来源信息
- 对空白 PDF 页面和损坏 PDF 给出明确结果

## 当前限制

- 暂不支持扫描型 PDF 和 OCR
- 暂不保证复杂表格、多栏排版的提取效果
- 暂不进行文本切块和向量检索

## 运行测试

```powershell
python -m pytest -v
```

## SQLite 文档登记

- 使用 `data/documents.db` 持久保存文档登记信息
- `init_db()` 初始化 `documents` 表
- `register_document()` 使用参数化 SQL 登记文档
- 使用 `file_hash` 唯一约束识别重复内容
- 保存处理状态和错误信息
- 重复登记返回 `False`，不会中断程序
- 本地数据库文件已加入 `.gitignore`