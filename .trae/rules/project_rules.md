# 项目规则与开发文档

## 基础规则
1. 当前项目仅服务于 Model Link。这意味着 api host 固定就是：`https://api.modellink.online` 。当用户给你的参考的方法中存在 api host 这个参数的时候你需要替换为 `https://api.modellink.online` 。
2. 当前项目是一个dify 插件。在开发功能是需要严格遵守 dify 插件开发规范以及范式。
3. 在处理工具参数时，需要检查参数值是否为字符串'variable'，如果是则将其设置为None。这是因为当页面元素默认设置为引用变量时，系统会传递字符串'variable'而不是实际值，导致Pydantic验证错误。
4. 所有工具插件必须在 `provider/api.yaml` 文件的 `tools` 列表中接入，而不是在 `manifest.yaml` 文件中直接添加。manifest.yaml 文件只需要包含提供者配置文件即可。

## 通用规范

### 插件结构
插件项目的基本结构如下：
```
plugin-directory/
├── _assets/              # 静态资源，如图标
├── provider/             # 提供者配置和代码
│   ├── provider.yaml     # 提供者配置文件
│   └── provider.py       # 提供者实现代码
├── tools/                # 工具配置和代码
│   ├── tool1.yaml        # 工具1配置文件
│   ├── tool1.py          # 工具1实现代码
│   ├── tool2.yaml        # 工具2配置文件
│   └── tool2.py          # 工具2实现代码
├── .env.example          # 环境变量示例
├── .gitignore            # Git忽略文件
├── main.py               # 插件入口
├── manifest.yaml         # 插件清单
├── privacy.md            # 隐私政策
├── README.md             # 插件说明文档
└── requirements.txt      # 依赖声明
```

### 命名规范
- 插件名称：使用小写字母，单词之间用下划线分隔
- 文件名称：使用小写字母，单词之间用下划线分隔
- 类名称：使用驼峰命名法，如 `OpenAIChatTool`
- 方法名称：使用小写字母，单词之间用下划线分隔
- 参数名称：使用小写字母，单词之间用下划线分隔

### 配置文件格式
所有配置文件必须使用 YAML 格式，并且符合 Dify 插件配置规范。

## Manifest 规范

Manifest 是一个符合 YAML 规范的文件，定义了**插件**最基本的信息，包括但不限于插件名称、作者、包含的工具、模型等。

### 核心字段
- `version`: 插件的版本
- `type`: 插件类型，目前仅支持 `plugin`
- `author`: 作者，定义为 Marketplace 中的组织名称
- `label`: 多语言名称
- `created_at`: 创建时间，Marketplace 要求不能晚于当前时间
- `icon`: 图标路径
- `resource`: 申请的资源，包括内存和权限
- `plugins`: 插件扩展的具体能力的 `yaml` 文件列表
- `meta`: 插件的元数据，包括支持的架构和运行时配置
- `privacy`: 指定插件隐私政策文件的相对路径或 URL

## 工具插件开发

### 工具提供者文件
工具提供者文件是一个 yaml 格式文件，可以理解为工具插件的基本配置入口，用于向工具提供必要的授权信息。

### 工具 YAML 文件
一个工具插件可以有多个工具功能，每个工具功能都需要一个 `yaml` 文件进行描述，包括工具功能的基本信息、参数、输出等。

### 参数类型
目前支持以下五种参数类型：
- `string`: 字符串
- `number`: 数字
- `boolean`: 布尔值
- `select`: 下拉框
- `secret-input`: 加密输入框

### 表单类型
- `llm`: 在智能体应用中，表示该参数由 LLM 自行推断；在工作流应用中，用作工具节点的输入变量
- `form`: 在智能体应用中，表示参数可以预先设置以使用此工具；在工作流应用中，需要由前端填写

### 工具实现
工具实现类必须继承自 `dify_plugin.Tool` 类，并实现 `_invoke` 方法。

## 多语言支持

### 多语言 README
- 在项目根目录创建 `readme` 文件夹，包含不同语言的 README 文件
- 支持的语言包括：`zh_Hans`、`en_US`、`pt_BR`、`ja_JP`
- 命名格式：`README_{language}.md`，如 `README_zh_Hans.md`

### 配置文件多语言
在配置文件中，所有用户可见的文本都应该支持多语言，包括：
- `label`
- `human_description`
- `llm_description`
- `placeholder`
- `help`
- `options.label`

## 日志输出

### 使用方法
导入 `plugin_logger_handler` 并将其添加到 logger 处理器中：

```python
# 导入 logging 和自定义处理器
import logging
from dify_plugin.config.logger_format import plugin_logger_handler

# 使用自定义处理器设置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)
```

### 日志级别
- `logger.info()`: 信息日志
- `logger.warning()`: 警告日志
- `logger.error()`: 错误日志

## 工具返回

### 消息类型
- `create_text_message()`: 返回文本消息
- `create_link_message()`: 返回链接消息
- `create_image_message()`: 返回图片 URL 消息
- `create_blob_message()`: 返回文件 blob 消息
- `create_json_message()`: 返回格式化 JSON 消息

### 变量
- `create_variable_message()`: 创建命名变量用于工作流集成
- `create_stream_variable_message()`: 创建流式变量，支持打字机效果

### 自定义输出变量
- 使用 JSON Schema 格式定义输出模式
- 在工具清单中添加 `output_schema` 字段
- 在实现代码中使用 `create_variable_message()` 实际返回变量

## 工具 OAuth 认证

### OAuth 流程
1. 在提供者配置文件中添加 OAuth 配置
2. 实现 `_get_authorization_url` 方法生成授权 URL
3. 实现 `_exchange_token` 方法兑换访问令牌
4. 实现 `_refresh_token` 方法刷新访问令牌
5. 实现 `_revoke_token` 方法撤销访问令牌

### OAuth 配置示例
```yaml
credentials_for_provider:
  oauth:
    type: oauth2
    required: true
    label:
      en_US: OAuth
      zh_Hans: OAuth认证
    authorization_url: https://example.com/oauth/authorize
    token_url: https://example.com/oauth/token
    scopes: [read, write]
    client_id: your-client-id
    client_secret: your-client-secret
    redirect_uri: https://cloud.dify.ai/console/plugin/oauth/callback
```

## 调试与打包

### 调试插件
1. 前往 [插件管理](https://cloud.dify.ai/plugins) 页面获取远程服务器地址和调试 Key
2. 复制 `.env.example` 文件并重命名为 `.env`，填写远程服务器地址和调试 Key
3. 运行 `python -m main` 命令启动插件

### 打包插件
```bash
dify plugin package ./plugin-directory
```

### 发布插件
确保插件符合 [发布到 Dify Marketplace](https://docs.dify.ai/zh/develop-plugin/publishing/marketplace-listing/release-to-dify-marketplace) 中的规范。

## 开发速查表

### 常用命令
- 初始化插件：`dify plugin init`
- 调试插件：`python -m main`
- 打包插件：`dify plugin package ./plugin-directory`
- 安装依赖：`pip install -r requirements.txt`
- 检查依赖：`pip check`

### 开发最佳实践
1. 始终使用类型提示
2. 编写清晰的文档字符串
3. 处理所有可能的异常
4. 记录详细的日志
5. 遵循 PEP 8 编码规范
6. 编写单元测试
7. 定期更新依赖

### 常见错误排查
- 配置文件格式错误：检查 YAML 语法是否正确
- 依赖冲突：检查 requirements.txt 中的依赖版本
- 权限问题：确保插件有正确的权限访问资源
- API 调用失败：检查 API 端点、请求参数和认证信息

## 发布 FAQ

### 1. 如何更新已发布的插件？
- 修改插件代码和配置
- 更新插件版本号
- 重新打包插件
- 在 Dify Marketplace 上传新版本

### 2. 插件审核需要多长时间？
- 通常需要 1-3 个工作日
- 复杂插件可能需要更长时间

### 3. 如何处理插件依赖？
- 在 requirements.txt 中明确声明所有依赖
- 尽量使用稳定版本的依赖
- 避免使用过多的依赖

### 4. 如何确保插件的安全性？
- 不要硬编码敏感信息
- 使用环境变量存储配置
- 验证所有输入
- 限制 API 调用频率
- 定期更新依赖以修复安全漏洞

## 贡献者行为准则

### 我们的承诺
作为项目贡献者和维护者，我们承诺尊重所有参与项目的人，无论其经验水平、性别、性别认同和表达、性取向、残疾、外貌、种族、年龄、宗教或国籍如何。

### 我们的标准
有助于创建积极环境的行为包括：
- 使用友好和包容的语言
- 尊重不同的观点和经验
- 优雅地接受建设性批评
- 专注于对社区最有利的事情
- 对其他社区成员表现出同理心

不可接受的行为包括：
- 使用性化语言或图像，以及不恰当的性关注或追求
- 挑衅、侮辱或贬损性评论，以及人身或政治攻击
- 公开或私下骚扰
- 未经明确许可发布他人的私人信息，如物理或电子地址
- 在专业环境中其他可能被合理认为不合适的行为

### 我们的责任
项目维护者有责任明确可接受行为的标准，并对任何不可接受行为的实例采取适当和公平的纠正措施。

### 适用范围
本行为准则适用于项目空间内的所有空间，以及在公共空间中代表项目或其社区时的个人。

### 执行
可通过 [Dify 插件社区](https://docs.dify.ai/zh/develop-plugin/publishing/standards/contributor-covenant-code-of-conduct) 报告辱骂、骚扰或其他不可接受的行为。

## 常见问题

### 1. select 类型参数的选项配置
- 应该使用 `options` 而不是 `enum` 来定义选项
- 每个选项必须是一个包含 `value` 和 `label` 字段的字典
- `label` 支持多语言配置

### 2. 参考图列表参数类型
- Dify 插件不支持 `array` 类型
- 将 `array` 类型改为 `string` 类型，通过 CSV 格式传入多个值
- 使用英文逗号作为分隔符

### 3. 参数类型说明
- 在 `human_description` 和 `help` 字段中明确说明参数的类型、格式和限制
- 提供示例，帮助用户理解如何使用

### 4. 多语言支持
- 在 `label`、`human_description`、`placeholder`、`help`、`options.label` 等字段中提供英文、中文、葡萄牙语和日语的文本
