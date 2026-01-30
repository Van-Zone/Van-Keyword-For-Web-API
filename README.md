为了结合新添加的 WebUI 功能，我们需要更新 README.md 文件，添加关于 WebUI 的详细说明。以下是更新后的 README.md 内容：

---

# VanBot 词库API 服务器

## 项目概述

VanBot词库API是一个基于FastAPI的HTTP服务，提供关键词词库的查询、管理和存储功能。该系统主要用于聊天机器人场景，支持多机器人、多用户、多群组的词库管理，并提供了完善的API接口供外部调用。

**新特性**：集成了功能完整的WebUI管理界面，支持可视化操作，无需命令行即可管理词库、测试功能、查看状态。

## 主要特性

### 核心功能
- **关键词查询**：支持精确匹配和模糊匹配两种模式
- **词库管理**：添加、删除、修改关键词及其回复
- **多词库支持**：用户、群组、公共词库多层级的词库管理
- **权限控制**：管理员权限机制和词条访问控制
- **变量支持**：支持`[n.数字]`格式的变量替换
- **CQ码兼容**：自动转换常见CQ码格式

### 高级功能（新增）
- **完整消息解码系统**：支持复杂变量替换和多媒体消息处理
- **时间变量系统**：`(Y)`, `(M)`, `(D)`, `(h)`, `(m)`, `(s)` 时间变量
- **数学运算**：支持 `(+1+2)`, `(+2*3/4)` 等数学表达式
- **随机数生成**：`(1-100)` 生成随机数
- **冷却时间系统**：`(60~)` 设置冷却时间，基于用户ID和词条ID
- **条件判断**：`{a>b}` 数值比较和字符串判断
- **分句发送**：`(-5-)` 分句发送语法检测

### 技术特性
- **RESTful API**：基于FastAPI的标准HTTP接口
- **Token验证**：Bearer Token双重验证机制
- **异步处理**：全异步架构，高性能处理
- **日志系统**：完整的操作日志记录
- **文件存储**：本地JSON文件存储词库数据
- **配置管理**：灵活的配置系统

### WebUI功能（新增）
- **可视化操作界面**：浏览器即可管理所有功能
- **实时状态监控**：服务器状态、连接测试、功能验证
- **交互式测试**：关键词查询、消息解码、词库操作
- **词库可视化**：词条列表、搜索、统计信息
- **工具集成**：消息转码、JSON格式化、管理员管理
- **示例代码**：提供curl和JavaScript调用示例

## 系统架构

### 数据存储结构
```
Van_keyword_data/
├── {bot_id}/                    # 机器人独立目录
│   ├── lexicon/                 # 词库文件
│   │   ├── M_{user_id}.json    # 用户个人词库
│   │   └── common.json         # 公共词库
│   ├── config/                  # 配置文件
│   ├── expand/                  # 扩展变量文件
│   └── cooling/                 # 冷却相关文件
├── qq.txt                       # 管理员列表
└── Van_keyword_token.txt       # API Token备份
```

### 全局变量管理
- `global_group_ids`: 消息环境标识
- `global_user_ids`: 发送者标识
- `global_bot_ids`: 机器人标识
- `data_files`: 词库文件映射
- `datas`: 内存中的词库数据

## API接口

### 主要端点

#### 1. 查询关键词
**POST** `/api/v1/keyword`
```json
{
  "action": "query",
  "botid": 123456,
  "userid": 789012,
  "groupid": 112233,   // 可选
  "msg": "查询内容",
  "mode": 0,           // 0:模糊匹配，1:精确匹配
  "token": "API_TOKEN"
}
```

#### 2. 消息解码（新增）
**POST** `/api/v1/keyword`
```json
{
  "action": "decode",
  "botid": 123456,
  "userid": 789012,
  "text": "你好[qq]！现在是(Y)年(M)月(D)日 [image.http://example.com/test.jpg]",
  "event_data": {
    "user_id": 789012,
    "group_id": 987654,
    "self_id": 123456
  },
  "lexicon_id": 1001,    // 可选，用于冷却
  "lexicon_n": 50,       // 可选，词库词条数
  "cool_config": true,   // 可选，是否启用冷却
  "token": "API_TOKEN"
}
```

#### 3. 消息转码（新增）
**POST** `/api/v1/keyword`
```json
{
  "action": "transcode",
  "text": "[CQ:image,url=http://example.com/img.jpg]",
  "token": "API_TOKEN"
}
```

#### 4. 添加词条
```json
{
  "action": "add",
  "botid": 123456,
  "userid": 789012,
  "keyword": "关键词",
  "reply": "回复内容",
  "mode": 1,
  "token": "API_TOKEN"
}
```

#### 5. 删除词条
```json
{
  "action": "remove",
  "botid": 123456,
  "userid": 789012,
  "keyword": "要删除的关键词",
  "token": "API_TOKEN"
}
```

#### 6. 管理回复选项
- `add_r`: 为已有词条添加回复选项
- `remove_r`: 删除词条的某个回复选项

#### 7. 其他功能
- `get_config`: 获取系统配置
- `search`: 搜索关键词
- `list`: 列出所有词条
- `count`: 统计词条数量
- `test`: 测试接口连通性

#### 8. 管理员管理（新增）
```json
{
  "action": "admin_manage",
  "op": "view/add/remove",
  "user": "用户ID（添加/删除时需提供）",
  "token": "API_TOKEN"
}
```

#### 9. 示例接口（新增）
**GET** `/api/v1/examples` - 获取API使用示例

#### 10. 状态接口（新增）
**GET** `/status` - 获取服务器状态信息
**GET** `/` - API根目录信息

## WebUI界面（新增）

### 访问方式
启动服务后，在浏览器中访问：`http://服务器IP:8889/webui`

### 主要功能区域

#### 1. 服务器状态
- 实时显示API服务器运行状态
- 查看连接信息、数据目录
- 测试API连通性
- 自动刷新（每30秒）

#### 2. 关键词查询
- 交互式关键词查询界面
- 支持精确/模糊匹配模式
- 实时显示查询结果
- 预置测试数据

#### 3. 消息解码
- 完整变量替换测试
- 支持所有变量类型：[qq]、[name]、[群号]等
- 时间变量、数学运算、随机数生成
- 事件数据配置（JSON格式）
- 冷却系统测试

#### 4. 词库管理
- 可视化添加/删除词条
- 管理回复选项
- 列出所有词条（支持分页）
- 词条统计信息
- 支持管理员专用模式

#### 5. 搜索词条
- 关键词搜索功能
- 结果显示关键词、ID、匹配模式
- 回复数量统计

#### 6. 配置管理
- 查看机器人配置
- 配置项列表展示

#### 7. 工具集
- **消息转码**：CQ码 ↔ 内部格式转换
- **JSON格式化**：JSON数据美化显示
- **管理员管理**：添加/删除/查看管理员

#### 8. 使用示例
- 提供curl命令示例
- 提供JavaScript调用示例
- 一键复制功能

### WebUI特点
- **响应式设计**：适配桌面和移动设备
- **实时反馈**：操作结果即时显示
- **状态提示**：成功/失败/加载中状态清晰显示
- **数据持久化**：API信息本地存储
- **交互友好**：表单验证、错误提示、加载动画

## 变量系统（增强）

### 基础变量
- `[qq]` - 用户QQ号
- `[name]` - 用户昵称
- `[群号]` - 群组ID
- `[词条id]` - 词条ID
- `[词汇量]` - 词库词条数
- `[当前词库]` - 当前使用的词库名称
- `[n.1]`~`[n.5]` - 匹配变量占位符

### 时间变量（新增）
| 变量 | 说明 | 示例输出 |
|------|------|----------|
| `(Y)` | 年份 | 2024 |
| `(M)` | 月份 | 12 |
| `(D)` | 日期 | 25 |
| `(h)` | 小时 | 14 |
| `(m)` | 分钟 | 30 |
| `(s)` | 秒数 | 45 |

**示例**：`现在是(Y)年(M)月(D)日 (h):(m):(s)` → `现在是2024年12月25日 14:30:45`

### 数学运算（新增）
支持复杂的数学表达式计算：
- `(+1+2)` → `3`
- `(+2*3/4)` → `1.5`
- `(+10-5*2)` → `0`
- 支持 `×` (乘法) 和 `÷` (除法) 符号
- 支持浮点数运算

### 随机数生成（新增）
- `(1-100)` → 生成1到100的随机整数
- 支持多个随机数同时生成
- 示例：`你的幸运数字是(1-10)` → `你的幸运数字是7`

### 冷却时间系统（增强）
- `(60~)` → 设置60秒冷却时间
- `(0~)` → 冷却到当天午夜（0点）
- 基于用户ID和词条ID的冷却检查
- 可自定义冷却中回复消息

### 条件判断（新增）
- `{a>b}` → 数值比较（大于）
- `{a<b}` → 数值比较（小于）
- `{a=b}` → 相等判断（支持数字和字符串）
- 判断失败时可返回自定义回复

## 多媒体消息处理（增强）

### 支持的消息类型：

| 类型 | 内部格式 | CQ码格式 | 说明 |
|------|----------|----------|------|
| 文本 | `[text.内容]` | `[CQ:text,content=内容]` | 文本消息 |
| 图片 | `[image.URL]` | `[CQ:image,url=URL]` | 图片消息 |
| 表情 | `[face.ID]` | `[CQ:face,id=ID]` | 表情ID |
| @某人 | `[at.QQ号]` | `[CQ:at,qq=QQ号]` | @特定用户 |
| 回复 | `[reply.消息ID]` | `[CQ:reply,id=消息ID]` | 回复消息 |
| 视频 | `[video.URL]` | `[CQ:video,url=URL]` | 视频消息 |
| 语音 | `[record.URL]` | `[CQ:record,url=URL]` | 语音消息 |
| 音乐 | `[music.标题.URL]` | `[CQ:music,title=标题,url=URL]` | 音乐分享 |
| 分享 | `[share.URL]` | `[CQ:share,url=URL]` | 链接分享 |
| JSON | `[json.JSON数据]` | `[CQ:json,data=JSON数据]` | JSON格式消息 |

## 配置文件

### 管理配置
- **管理员管理**: 通过`qq.txt`文件管理管理员QQ号
- **词库切换**: 支持按用户切换不同词库文件
- **群组开关**: 控制特定群组的词库使用

### 匹配模式
1. **精确匹配 (s=1)**: 关键词必须完全匹配
2. **模糊匹配 (s=0)**: 消息包含关键词即可
3. **管理员专用 (s=10)**: 仅管理员可访问

### 新增配置支持
```python
# 冷却相关配置
COOLING_ENABLED = True  # 启用冷却系统
DEFAULT_COOLING_TIME = 60  # 默认冷却时间（秒）

# 变量替换配置
ENABLE_VARIABLE_REPLACE = True
ENABLE_TIME_VARIABLES = True
ENABLE_MATH_EXPRESSIONS = True

# 多媒体处理配置
ALLOW_IMAGE_MESSAGES = True
ALLOW_AUDIO_MESSAGES = True
MAX_MESSAGE_LENGTH = 5000
```

## 使用示例

### 启动服务
```bash
python Van_keyword.py
```

### 访问WebUI
启动后，在浏览器中打开：`http://localhost:8889/webui`

### API调用示例

#### 基础查询
```bash
# 测试连接
curl -X POST http://localhost:8889/api/v1/keyword \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {API_TOKEN}" \
  -d '{"action":"test","botid":123456,"userid":789012,"token":"{API_TOKEN}"}'

# 查询关键词
curl -X POST http://localhost:8889/api/v1/keyword \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {API_TOKEN}" \
  -d '{"action":"query","botid":123456,"userid":789012,"msg":"你好","token":"{API_TOKEN}"}'
```

#### 高级功能示例（新增）
```bash
# 复杂消息解码
curl -X POST http://localhost:8889/api/v1/keyword \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer API_TOKEN" \
  -d '{
    "action": "decode",
    "botid": 123456,
    "userid": 789012,
    "text": "欢迎[qq]！\\n今日日期：(Y)/(M)/(D)\\n随机数：(1-100)\\n数学运算：(+5*3/2)\\n[image.http://example.com/avatar.jpg]",
    "event_data": {
      "user_id": 789012,
      "group_id": 987654,
      "self_id": 123456,
      "sender": {
        "nickname": "小明",
        "card": "技术宅"
      }
    },
    "token": "API_TOKEN"
  }'

# CQ码转码
curl -X POST http://localhost:8889/api/v1/keyword \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer API_TOKEN" \
  -d '{
    "action": "transcode",
    "text": "[CQ:image,url=http://example.com/img.jpg][CQ:at,qq=123456]",
    "token": "API_TOKEN"
  }'
```

## WebUI使用示例

### 1. 首次使用
1. 启动服务后，控制台会显示访问地址和Token
2. 打开浏览器访问 `http://localhost:8889/webui`
3. API Token会自动填充，无需手动输入

### 2. 测试功能
1. 切换到"服务器状态"标签页
2. 点击"测试连接"按钮
3. 查看连接状态和服务器信息

### 3. 管理词库
1. 切换到"词库管理"标签页
2. 填写机器人ID和用户ID
3. 选择操作类型（添加/删除/查看）
4. 执行操作并查看结果

### 4. 测试变量
1. 切换到"消息解码"标签页
2. 输入测试文本：`现在是(Y)年(M)月(D)日`
3. 点击"解码消息"按钮
4. 查看替换后的结果

## 环境要求

### 依赖包
```
fastapi==0.104.1
uvicorn==0.24.0
httpx==0.25.1
pydantic==2.5.0
```

### Python版本
- Python 3.8+

## 配置选项

### 启动参数
```python
MISTAKE_TURN_TYPE = False  # 是否自动转换中文符号
API_HOST = "0.0.0.0"       # 监听地址
API_PORT = 8889           # 监听端口
ENABLE_ADVANCED_FEATURES = True  # 启用高级功能
MAX_CACHE_SIZE = 1000      # 缓存大小
LOG_LEVEL = "INFO"         # 日志级别
```

### 安全设置
- 自动生成16位随机Token
- Bearer Token双重验证机制
- 管理员权限控制
- Token加密存储

## 日志系统

### 日志级别
- INFO: 常规操作记录
- DEBUG: 详细调试信息
- WARN: 警告信息
- ERROR: 错误信息

### 新增日志类别：
- `DECODE` - 消息解码日志
- `VARIABLE` - 变量替换日志
- `MEDIA` - 多媒体处理日志
- `COOLING` - 冷却系统日志
- `MATH` - 数学运算日志

### 日志文件
- 位置: `api_log.txt`
- 格式: `[时间戳] [级别] 消息内容`
- 示例:
  ```
  [2024-01-25 14:30:45] [DECODE] 开始解码消息: length=256
  [2024-01-25 14:30:45] [VARIABLE] 替换变量: [qq] -> 789012
  [2024-01-25 14:30:45] [TIME] 时间变量: (Y) -> 2024
  ```

## 特殊功能

### 变量替换
支持`[n.1]`到`[n.5]`的变量占位符，匹配时自动填充。

### 符号转换
当`MISTAKE_TURN_TYPE=True`时，自动转换：
- 中文括号 `【】` → 英文括号 `[]`
- 中文括号 `（）` → 英文括号 `()`
- 中文冒号 `：` → 英文冒号 `:`

### CQ码支持（增强）
自动解析常见CQ码格式，如：
- `[CQ:at,qq=123456]` → `[at.123456]`
- `[CQ:image,url=http://...]` → `[image.http://...]`
- `[CQ:face,id=123]` → `[face.123]`
- `[CQ:reply,id=456]` → `[reply.456]`

### 分句发送（新增）
检测分句发送语法：
- `(-5-)` → 分句发送标记
- 返回特殊类型，由调用方处理

### 缓存机制（新增）
- HTTP请求结果缓存（5分钟）
- 词库数据内存缓存
- 配置信息缓存
- 冷却时间缓存

## 部署说明

1. **安装依赖**:
   ```bash
   pip install fastapi uvicorn httpx pydantic
   ```

2. **配置权限**:
   编辑`Van_keyword_data/qq.txt`添加管理员QQ号

3. **启动服务**:
   ```bash
   python Van_keyword.py
   # 或使用uvicorn
   uvicorn Van_keyword_WebAPI:api_app --host 0.0.0.0 --port 8889 --reload
   ```

4. **访问WebUI**:
   打开浏览器访问 `http://localhost:8889/webui`

5. **验证服务**:
   访问 `http://localhost:8889/docs` 或 [公开文档](http://white.oneplus.xin/api/dosc.html) 或 [位于Github的文档](https://github.com/Van-Zone/Van-Keyword-For-Web-API/blob/main/dosc.html)查看API文档

## 故障排除

### 常见问题
1. **端口占用**: 修改`API_PORT`配置
2. **权限不足**: 检查管理员配置
3. **词库不生效**: 检查文件权限和路径
4. **变量不生效**: 检查event_data参数是否完整
5. **多媒体消息无法显示**: 确认URL格式正确，检查网络连通性
6. **WebUI无法访问**: 检查防火墙设置，确保端口开放

### 调试模式
启用详细日志：
```python
logger.debug("调试信息")
```

### 新增问题排查：

1. **数学运算错误**
   - 检查表达式格式：`(+1+2)` 不是 `(1+2)`
   - 避免除零错误
   - 查看运算日志

2. **冷却时间异常**
   - 检查冷却文件权限
   - 确认时间戳格式
   - 查看冷却日志

3. **内存使用过高**
   - 词库较大时注意监控内存
   - 调整缓存大小设置
   - 定期清理日志文件

4. **WebUI显示异常**
   - 检查浏览器控制台错误
   - 确认API Token正确
   - 验证网络连接

## 注意事项

1. **数据备份**: 定期备份词库文件
2. **权限控制**: 谨慎配置管理员权限
3. **性能优化**: 词库过大时考虑分库管理
4. **安全考虑**: 定期更换API Token
5. **升级兼容性**: v2.0完全兼容v1.0，无需迁移数据
6. **日志管理**: 建议定期清理日志文件，避免磁盘空间不足
7. **WebUI安全**: 建议在生产环境中使用HTTPS，避免Token泄露

## 版本信息

- **版本**: 3.0.0
- **作者**: VanBot团队
- **更新日期**: 2026年1月30日
- **主要更新**:
  1. 完整的消息解码系统
  2. 多媒体消息支持
  3. 时间变量系统
  4. 数学运算功能
  5. 冷却时间增强
  6. 条件判断支持
  7. API端点扩展
  8. **WebUI管理界面**
  9. 性能优化改进

---

**提示**: 
- 首次启动时会显示API Token，请妥善保管。所有API调用都需要在Header或Body中提供正确的Token。
- **新增WebUI功能**：提供可视化操作界面，无需命令行即可管理所有功能。
- 新版本提供了更强大的消息处理能力，特别适合需要复杂交互和多媒体消息的聊天机器人场景。
- 所有原有功能保持不变，可以无缝升级。

---

## 写在最后的话：
**有些功能可能并不很适合在Web API服务器使用，但我还是硬写过来了**
**WebUI的加入使得操作更加直观，降低了使用门槛**
**希望各位可以及时反馈一些BUG和问题**
**Van词库交流群：1019070322**

---

主要更新点：
1. 在"主要特性"部分添加了WebUI功能描述
2. 新增"WebUI界面"完整章节，详细介绍所有功能
3. 更新"使用示例"部分，添加WebUI访问说明
4. 在"故障排除"中添加WebUI相关问题
5. 在"注意事项"中补充WebUI安全建议
6. 在"版本信息"中突出WebUI作为主要更新
7. 在最后的提示部分强调WebUI的易用性

这些更新让README.md完整反映了新添加的WebUI功能，为用户提供全面的使用指南。