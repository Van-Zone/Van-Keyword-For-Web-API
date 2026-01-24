# VanBot 词库API 服务器

## 项目概述

VanBot词库API是一个基于FastAPI的HTTP服务，提供关键词词库的查询、管理和存储功能。该系统主要用于聊天机器人场景，支持多机器人、多用户、多群组的词库管理，并提供了完善的API接口供外部调用。

## 主要特性

### 核心功能
- **关键词查询**：支持精确匹配和模糊匹配两种模式
- **词库管理**：添加、删除、修改关键词及其回复
- **多词库支持**：用户、群组、公共词库多层级的词库管理
- **权限控制**：管理员权限机制和词条访问控制
- **变量支持**：支持`[n.数字]`格式的变量替换
- **CQ码兼容**：自动转换常见CQ码格式

### 技术特性
- **RESTful API**：基于FastAPI的标准HTTP接口
- **Token验证**：Bearer Token双重验证机制
- **异步处理**：全异步架构，高性能处理
- **日志系统**：完整的操作日志记录
- **文件存储**：本地JSON文件存储词库数据
- **配置管理**：灵活的配置系统

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

#### 2. 添加词条
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

#### 3. 删除词条
```json
{
  "action": "remove",
  "botid": 123456,
  "userid": 789012,
  "keyword": "要删除的关键词",
  "token": "API_TOKEN"
}
```

#### 4. 管理回复选项
- `add_r`: 为已有词条添加回复选项
- `remove_r`: 删除词条的某个回复选项

#### 5. 其他功能
- `get_config`: 获取系统配置
- `search`: 搜索关键词
- `list`: 列出所有词条
- `count`: 统计词条数量
- `test`: 测试接口连通性

## 配置文件

### 管理配置
- **管理员管理**: 通过`qq.txt`文件管理管理员QQ号
- **词库切换**: 支持按用户切换不同词库文件
- **群组开关**: 控制特定群组的词库使用

### 匹配模式
1. **精确匹配 (s=1)**: 关键词必须完全匹配
2. **模糊匹配 (s=0)**: 消息包含关键词即可
3. **管理员专用 (s=10)**: 仅管理员可访问

## 使用示例

### 启动服务
```bash
python Van_keyword.py
```

### API调用示例
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
```

### 安全设置
- 自动生成16位随机Token
- Bearer Token双重验证机制
- 管理员权限控制

## 日志系统

### 日志级别
- INFO: 常规操作记录
- DEBUG: 详细调试信息
- WARN: 警告信息
- ERROR: 错误信息

### 日志文件
- 位置: `api_log.txt`
- 格式: `[时间戳] [级别] 消息内容`

## 特殊功能

### 变量替换
支持`[n.1]`到`[n.5]`的变量占位符，匹配时自动填充。

### 符号转换
当`MISTAKE_TURN_TYPE=True`时，自动转换：
- 中文括号 `【】` → 英文括号 `[]`
- 中文括号 `（）` → 英文括号 `()`
- 中文冒号 `：` → 英文冒号 `:`

### CQ码支持
自动解析常见CQ码格式，如：
- `[CQ:at,qq=123456]` → `[at.123456]`
- `[CQ:image,url=http://...]` → `[image.http://...]`

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
   ```

4. **验证服务**:
   访问 `http://localhost:8889/docs` 或 [公开文档](http://white.oneplus.xin/api/dosc.html)查看API文档

## 故障排除

### 常见问题
1. **端口占用**: 修改`API_PORT`配置
2. **权限不足**: 检查管理员配置
3. **词库不生效**: 检查文件权限和路径

### 调试模式
启用详细日志：
```python
logger.debug("调试信息")
```

## 注意事项

1. **数据备份**: 定期备份词库文件
2. **权限控制**: 谨慎配置管理员权限
3. **性能优化**: 词库过大时考虑分库管理
4. **安全考虑**: 定期更换API Token

## 版本信息

- 版本: 1.0.0
- 作者: VanBot团队
- 更新日期: 2026年

---

**提示**: 首次启动时会显示API Token，请妥善保管。所有API调用都需要在Header或Body中提供正确的Token。
