import httpx, json, re, random, os, asyncio, time, secrets, threading, sys
from urllib.parse import quote
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Request, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, validator
import uvicorn
from contextvars import ContextVar

# ==================== 配置 ====================
MISTAKE_TURN_TYPE = False  # 是否提高教词容错率，中文符自动转成英文符
API_HOST = "0.0.0.0"  # 监听所有网络接口
API_PORT = 8889  # API端口
API_TOKEN = secrets.token_hex(16)  # 生成随机token

print(f"\n{'='*50}")
print(f"🔐 API Token: {API_TOKEN}")
print(f"🌐 API地址: http://{API_HOST}:{API_PORT}")
print(f"📖 API文档: http://{API_HOST}:{API_PORT}/docs")
print(f"{'='*50}\n")

# ==================== 全局变量 ====================
# 字典存储不同机器人的信息
global_group_ids = {}  # 消息环境
global_user_ids = {}  # 发送者
data_files = {}  # 词库文件
datas = {}  # 词库数据
global_bot_ids = {}  # 机器人

# 使用当前脚本所在目录
if getattr(sys, 'frozen', False):
    # 如果是打包后的exe
    directory = os.path.dirname(sys.executable)
else:
    # 如果是脚本文件
    directory = os.path.dirname(os.path.abspath(__file__))

print(f"📁 工作目录: {directory}")

# ==================== 日志系统 ====================
class Logger:
    def __init__(self):
        self.log_file = os.path.join(directory, "api_log.txt")
        self.ensure_log_file()
    
    def ensure_log_file(self):
        """确保日志文件存在"""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(f"VanBot API 日志文件 - 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    def log(self, level: str, message: str):
        """记录日志"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] [{level.upper()}] {message}"
        
        # 打印到控制台
        print(log_message)
        
        # 写入文件
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_message + "\n")
        except Exception as e:
            print(f"⚠️  写入日志失败: {e}")
    
    def info(self, message: str):
        self.log("INFO", message)
    
    def debug(self, message: str):
        self.log("DEBUG", message)
    
    def error(self, message: str):
        self.log("ERROR", message)
    
    def warn(self, message: str):
        self.log("WARN", message)

logger = Logger()

# ==================== 辅助函数 ====================
def ensure_dir(path):
    """确保目录存在"""
    if not os.path.exists(path):
        try:
            os.makedirs(path, exist_ok=True)
            logger.info(f"已创建目录: {path}")
        except Exception as e:
            logger.error(f"创建目录失败 {path}: {e}")
            # 尝试在当前目录创建
            base_dir = os.path.basename(path)
            fallback = os.path.join(os.getcwd(), base_dir)
            if not os.path.exists(fallback):
                os.makedirs(fallback, exist_ok=True)
            return fallback
    return path

def get_data_dir():
    """获取数据目录"""
    # 优先尝试在脚本同级目录创建
    data_dir = os.path.join(directory, "Van_keyword_data")
    data_dir = ensure_dir(data_dir)
    return data_dir

# ==================== 文件操作 ====================
async def file_control(bot_id, filename, mode, content=None):
    """文件操作函数"""
    try:
        if mode == 'w' and content is None:
            raise ValueError("缺参数")
        
        data_dir = get_data_dir()
        bot_dir = os.path.join(data_dir, str(bot_id))
        ensure_dir(bot_dir)
        
        file_path = os.path.join(bot_dir, filename)
        
        # 确保父目录存在
        parent_dir = os.path.dirname(file_path)
        if parent_dir:
            ensure_dir(parent_dir)
        
        if mode == 'r':
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    result = f.read()
                    logger.debug(f"读取文件: {file_path}, 大小: {len(result)} 字节")
                    return result
            else:
                logger.debug(f"文件不存在: {file_path}")
                # 文件不存在时返回默认值
                if filename == "switch.txt" or filename.startswith("cooling") or filename == "select.txt":
                    return "official_group=1019070322"
                elif filename.startswith("config"):
                    return ""
                elif filename.endswith(".json"):
                    return json.dumps({"work": []})
                else:
                    return ""
        elif mode == 'w':
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"写入文件: {file_path}, 大小: {len(content)} 字节")
            return "写入成功"
    except Exception as e:
        logger.error(f"文件操作失败：{str(e)}")
        return None

# ==================== 核心函数 ====================
def refresh_admin(user=None, op=None):
    """刷新管理员列表"""
    data_dir = get_data_dir()
    path = os.path.join(data_dir, "qq.txt")
    
    ADMIN_IDS = []
    
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            if lines:
                if "," in lines[0]:
                    ADMIN_IDS = lines[0].split(",")
                else:
                    ADMIN_IDS = lines.copy()
            logger.debug(f"加载管理员列表: {ADMIN_IDS}")
        except Exception as e:
            logger.error(f"读取管理员文件失败: {e}")
            ADMIN_IDS = []
    
    need_write = False
    if op == "add" and user and user not in ADMIN_IDS:
        ADMIN_IDS.append(user)
        need_write = True
    elif op == "rm" and user and user in ADMIN_IDS:
        ADMIN_IDS.remove(user)
        need_write = True
    
    if need_write:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(",".join(ADMIN_IDS))
            logger.info(f"更新管理员列表: {ADMIN_IDS}")
        except Exception as e:
            logger.error(f"写入管理员文件失败: {e}")
    
    return ADMIN_IDS

ADMIN_IDS = refresh_admin()

async def _global_file(bot_id, user_id, group_id=None, data_file=None):
    """初始化全局信息"""
    global_user_ids[bot_id] = user_id
    global_bot_ids[bot_id] = bot_id
    
    if group_id:
        global_group_ids[bot_id] = group_id
        if not data_file:
            data_file = await get_select_file(bot_id)
        data_files[bot_id] = f"lexicon/{data_file}.json"
    else:
        if not data_file:
            data_file = await get_select_file(bot_id)
        global_group_ids[bot_id] = data_file
        data_files[bot_id] = f"lexicon/{global_group_ids[bot_id]}.json"
    
    logger.debug(f"_global_file: bot_id={bot_id}, user_id={user_id}, data_file={data_file}")
    
    # 加载词库数据
    data_content = await file_control(bot_id, data_files[bot_id], "r")
    if data_content:
        try:
            datas[bot_id] = json.loads(data_content)
            logger.info(f"加载词库数据成功: bot_id={bot_id}, 词条数={len(datas[bot_id].get('work', []))}")
        except Exception as e:
            logger.error(f"解析词库JSON失败: {e}")
            datas[bot_id] = {"work": []}
    else:
        logger.debug(f"无词库数据，创建空词库: bot_id={bot_id}")
        datas[bot_id] = {"work": []}
    
    return True

async def get_select_file(bot_id):
    """获取选择的词库文件"""
    data_dict = {}
    file_content = await file_control(bot_id, "select.txt", "r")
    
    if file_content:
        lines = file_content.split('\n')
        for line in lines:
            line = line.strip()
            if '=' in line:
                key, value = line.split('=', 1)
                data_dict[key] = value
    
    user_id = global_user_ids.get(bot_id, "")
    if str(user_id) in data_dict:
        return data_dict[str(user_id)]
    else:
        return f"M_{user_id}"

async def get_user_file(bot_id):
    """获取用户词库文件"""
    data_dict = {}
    file_content = await file_control(bot_id, "switch.txt", "r")
    
    if file_content:
        lines = file_content.split('\n')
        for line in lines:
            line = line.strip()
            if '=' in line:
                key, value = line.split('=', 1)
                data_dict[key] = value
    
    group_id = global_group_ids.get(bot_id, "")
    if str(group_id) in data_dict:
        return data_dict[str(group_id)]
    else:
        return ""

async def get_config(bot_id, key):
    """获取配置"""
    text = await file_control(bot_id, f"config/M_{global_user_ids.get(bot_id, '')}.txt", "r")
    
    if text and '***' in text:
        start_index = text.find('***') + 3
        end_index = text.find('***', start_index)
        content = text[start_index:end_index].strip()
        
        data_dict = {}
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line and '=' in line:
                parts = line.split('=', 1)
                data_dict[parts[0]] = parts[1]
        
        return data_dict.get(key, "")
    
    return ""

async def get_n(key, text):
    """处理变量[n.?]"""
    safe_key = key.replace('[', r'\[').replace(']', r'\]')
    placeholders = re.findall(r'\\\[n\.(\d+)\\\]', safe_key)
    pattern_str = r'^' + re.sub(r'\\\[n\.(\d+)\\\]', r'(.+?)', safe_key) + r'$'
    
    try:
        pattern = re.compile(pattern_str)
        match = pattern.match(text)
    except re.error as e:
        logger.error(f"正则表达式错误：{e}")
        return False
    
    if match:
        result = ["", "", "", "", "", ""]
        for index, placeholder in enumerate(placeholders):
            if int(placeholder) < len(result):
                result[int(placeholder)] = str(match.group(index + 1))
        return False if all(item == '' for item in result) else result
    else:
        return False

async def lexicon_operation(bot_id, op_type, **kwargs):
    """词库操作函数"""
    def clean_special_chars(text):
        if MISTAKE_TURN_TYPE:
            return text.replace('【', '[').replace('】', ']')\
                .replace('（', '(').replace('）', ')')\
                .replace('｛', '{').replace('｝', '}').replace('：', ':')
        return text
    
    def replace_variable(text, mapping_str):
        try:
            mapping_data = json.loads(mapping_str)
            if "variable" in mapping_data:
                replace_pairs = mapping_data["variable"]
                for old, new in replace_pairs:
                    text = text.replace(old, new)
        except:
            pass
        return text
    
    valid_ops = {"get", "add", "remove", "add_r", "remove_r"}
    if op_type not in valid_ops:
        logger.error(f"无效操作类型: {op_type}")
        return f"无效操作类型！支持：{list(valid_ops)}"
    
    # 确保datas存在
    if bot_id not in datas:
        datas[bot_id] = {"work": []}
    
    # 查询词条
    if op_type == "get":
        value = kwargs.get("value", "")
        if not value:
            logger.debug(f"查询值为空: bot_id={bot_id}")
            return ""
        
        logger.info(f"开始查询词条: bot_id={bot_id}, value='{value}'")
        
        group_user = await get_user_file(bot_id)
        if not group_user:
            group_user = global_group_ids.get(bot_id, "")
        
        logger.debug(f"group_user: {group_user}")
        
        # 首先检查主词库（datas）
        found = False
        for item in datas[bot_id]["work"]:
            for key, val in item.items():
                logger.debug(f"检查词条: '{key}' (模式: {val.get('s', 0)}), 回复数: {len(val.get('r', []))}")
                
                # 检查权限
                if val.get('s') == 10 and str(global_user_ids.get(bot_id, "")) not in ADMIN_IDS:
                    logger.debug(f"跳过权限限制词条: {key}")
                    continue
                
                # 精确匹配
                if key == value and val.get('s') == 1:
                    logger.info(f"精确匹配成功: '{key}'")
                    if val.get('r'):
                        result = random.choice(val['r'])
                        logger.info(f"返回回复: '{result}'")
                        if str(group_user).startswith('E'):
                            mapping = await file_control(bot_id, f"expand/{group_user}.json", "r")
                            if mapping:
                                result = replace_variable(result, mapping)
                        return result
                
                # 模糊匹配
                if key in value and val.get('s') == 0:
                    logger.info(f"模糊匹配成功: '{key}' in '{value}'")
                    if val.get('r'):
                        result = random.choice(val['r'])
                        logger.info(f"返回回复: '{result}'")
                        if str(group_user).startswith('E'):
                            mapping = await file_control(bot_id, f"expand/{group_user}.json", "r")
                            if mapping:
                                result = replace_variable(result, mapping)
                        return result
        
        # 如果没有找到，尝试加载其他词库文件
        data_id = [str(global_group_ids.get(bot_id, "")), str(group_user), "common"]
        logger.debug(f"搜索数据源: {data_id}")
        
        for id in data_id:
            if not id or id == str(global_group_ids.get(bot_id, "")):
                continue  # 已经检查过了
                
            logger.debug(f"尝试加载词库: {id}")
            data_path = f"lexicon/{id}.json"
            data_content = await file_control(bot_id, data_path, "r")
            
            if not data_content:
                continue
                
            try:
                data = json.loads(data_content)
            except Exception as e:
                logger.error(f"解析词库文件失败 {data_path}: {e}")
                continue
            
            for item in data.get('work', []):
                for key, val in item.items():
                    logger.debug(f"检查词库 {id} 的词条: '{key}' (模式: {val.get('s', 0)})")
                    
                    # 检查权限
                    if val.get('s') == 10 and str(global_user_ids.get(bot_id, "")) not in ADMIN_IDS:
                        continue
                    
                    # 精确匹配
                    if key == value and val.get('s') == 1:
                        logger.info(f"精确匹配成功 (来自 {id}): '{key}'")
                        if val.get('r'):
                            result = random.choice(val['r'])
                            if str(group_user).startswith('E'):
                                mapping = await file_control(bot_id, f"expand/{group_user}.json", "r")
                                if mapping:
                                    result = replace_variable(result, mapping)
                            return result
                    
                    # 模糊匹配
                    if key in value and val.get('s') == 0:
                        logger.info(f"模糊匹配成功 (来自 {id}): '{key}' in '{value}'")
                        if val.get('r'):
                            result = random.choice(val['r'])
                            if str(group_user).startswith('E'):
                                mapping = await file_control(bot_id, f"expand/{group_user}.json", "r")
                                if mapping:
                                    result = replace_variable(result, mapping)
                            return result
        
        logger.info(f"未找到匹配的词条: '{value}'")
        return ""
    
    # 添加词条
    elif op_type == "add":
        n = kwargs.get("n")
        r = kwargs.get("r")
        s = kwargs.get("s", 1)
        
        if not all([n, r]):
            logger.error("添加词条缺少参数")
            return "缺少参数"
        
        n = clean_special_chars(n)
        r = clean_special_chars(r)
        
        # 检查是否已存在
        for item in datas[bot_id]["work"]:
            if n in item:
                logger.info(f"词条已存在: '{n}'")
                return False  # 词条已存在
        
        # 添加新词条
        new_item = {n: {"r": [r], "s": s}}
        datas[bot_id]["work"].append(new_item)
        logger.info(f"添加词条成功: '{n}' -> '{r}', 模式: {s}")
        
        return json.dumps(datas[bot_id], indent=4, ensure_ascii=False)
    
    # 删除词条
    elif op_type == "remove":
        key_to_delete = kwargs.get("key_to_delete")
        if not key_to_delete:
            logger.error("删除词条缺少参数")
            return "缺少参数"
        
        original_count = len(datas[bot_id]["work"])
        new_work = [item for item in datas[bot_id]["work"] if list(item.keys())[0] != key_to_delete]
        datas[bot_id]["work"] = new_work
        
        deleted_count = original_count - len(new_work)
        if deleted_count > 0:
            logger.info(f"删除词条成功: '{key_to_delete}', 删除了 {deleted_count} 个词条")
        else:
            logger.info(f"未找到要删除的词条: '{key_to_delete}'")
        
        return json.dumps(datas[bot_id], indent=4, ensure_ascii=False)
    
    # 添加回复选项
    elif op_type == "add_r":
        name = kwargs.get("name")
        value = kwargs.get("value")
        
        if not all([name, value]):
            logger.error("添加回复缺少参数")
            return "缺少参数"
        
        value = clean_special_chars(value)
        updated = False
        
        for item in datas[bot_id]["work"]:
            if name in item:
                if 'r' not in item[name]:
                    item[name]['r'] = []
                original_count = len(item[name]['r'])
                item[name]['r'].append(value)
                updated = True
                logger.info(f"添加回复成功: '{name}' -> '{value}', 原回复数: {original_count}, 现回复数: {len(item[name]['r'])}")
                break
        
        if not updated:
            logger.info(f"添加回复失败，词条不存在: '{name}'")
            return False
        
        return json.dumps(datas[bot_id], indent=4, ensure_ascii=False)
    
    # 删除回复选项
    elif op_type == "remove_r":
        name = kwargs.get("name")
        value = kwargs.get("value")
        
        if not all([name, value]):
            logger.error("删除回复缺少参数")
            return "缺少参数"
        
        updated = False
        for item in datas[bot_id]["work"]:
            if name in item and 'r' in item[name] and value in item[name]['r']:
                original_count = len(item[name]['r'])
                item[name]['r'].remove(value)
                updated = True
                logger.info(f"删除回复成功: '{name}' -> '{value}', 原回复数: {original_count}, 现回复数: {len(item[name]['r'])}")
                break
        
        if not updated:
            logger.info(f"删除回复失败，词条或回复不存在: '{name}' -> '{value}'")
            return False
        
        return json.dumps(datas[bot_id], indent=4, ensure_ascii=False)

def _transcoding(text):
    """消息转码"""
    # CQ码转换
    def parse_cq_code(cq_str, keep_params=None):
        default_keep = {
            'reply': 'id',
            'at': 'qq',
            'face': 'id',
            'image': 'url',
            'video': 'url',
            'record': 'url',
            'forward': 'id',
            'file': 'file_id',
            'json': 'data'
        }
        if keep_params is None:
            keep_params = default_keep
        
        cq_str = str(cq_str)
        pattern = r'\[CQ:(\w+),(.*?)\]'
        
        def replace_func(match):
            cq_type = match.group(1)
            params = dict(re.findall(r'(\w+)=([^,]+)', match.group(2)))
            if cq_type in keep_params:
                target_key = keep_params[cq_type]
                if target_key in params:
                    return f'[{cq_type}.{params[target_key]}]'
            return match.group(0)
        
        if re.search(pattern, cq_str):
            result = re.sub(pattern, replace_func, cq_str)
        else:
            result = cq_str
        
        result = result.replace('&#91;', '[').replace('&#93;', ']').replace('&amp;', '&')
        return result
    
    return parse_cq_code(text, keep_params=None)

# ==================== API相关定义 ====================
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证Token"""
    if credentials.credentials != API_TOKEN:
        logger.error(f"Token验证失败: {credentials.credentials}")
        raise HTTPException(status_code=401, detail="无效的Token")
    return credentials.credentials

# 修改 KeywordRequest 模型
class KeywordRequest(BaseModel):
    action: str
    mode: int = 0
    botid: int  # 改为int类型
    userid: int  # 改为int类型
    groupid: Optional[int] = None
    msg: Optional[str] = ""
    keyword: Optional[str] = None
    reply: Optional[str] = None
    token: str
    
    # 添加验证器处理大整数
    @validator('botid', 'userid', pre=True)
    def validate_ids(cls, v):
        # 确保正确处理大整数
        if isinstance(v, str) and v.isdigit():
            try:
                return int(v)
            except ValueError:
                try:
                    return int(v)
                except:
                    return 0
        elif isinstance(v, int):
            return v
        elif isinstance(v, float):
            return int(v)
        return 0
    
    class Config:
        extra = "allow"
        json_encoders = {
            int: lambda v: v,
            float: lambda v: v,
        }

# 创建FastAPI应用
api_app = FastAPI(
    title="VanBot关键词API",
    description="提供关键词查询和管理功能的API接口",
    version="1.0.0"
)

@api_app.get("/")
async def root():
    """API根目录"""
    return {
        "status": "online",
        "service": "VanBot Keyword API",
        "docs": f"http://{API_HOST}:{API_PORT}/docs",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@api_app.get("/status")
async def get_status():
    """获取API状态"""
    data_dir = get_data_dir()
    return {
        "host": API_HOST,
        "port": API_PORT,
        "token": API_TOKEN[:8] + "..." if len(API_TOKEN) > 8 else API_TOKEN,
        "running": True,
        "data_dir": data_dir
    }

# 主要API端点
@api_app.post("/api/v1/keyword")
async def keyword_api(
    request_data: Dict[str, Any] = Body(...),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """关键词API主接口 - 直接接收字典"""
    
    # 验证Header中的Token
    if credentials.credentials != API_TOKEN:
        logger.error(f"Header Token验证失败: {credentials.credentials}")
        raise HTTPException(status_code=401, detail="无效的Token")
    
    logger.info(f"收到API请求: action={request_data.get('action')}, botid={request_data.get('botid')}")
    
    try:
        # 验证请求体中的Token
        if request_data.get("token") != API_TOKEN:
            logger.error(f"Body Token验证失败: {request_data.get('token')}")
            raise HTTPException(status_code=401, detail="Token验证失败")
        
        action = request_data.get("action", "")
        
        # 根据action执行不同的操作
        if action == "query":
            return await handle_query_direct(request_data)
        elif action == "add":
            return await handle_add_direct(request_data)
        elif action == "remove":
            return await handle_remove_direct(request_data)
        elif action == "remove_r":
            return await handle_remove_reply_direct(request_data)
        elif action == "add_r":
            return await handle_add_reply_direct(request_data)
        elif action == "get_config":
            return await handle_get_config_direct(request_data)
        elif action == "search":
            return await handle_search_direct(request_data)
        elif action == "list":
            return await handle_list_direct(request_data)
        elif action == "count":
            return await handle_count_direct(request_data)
        elif action == "test":
            return await handle_test_direct(request_data)
        else:
            logger.error(f"不支持的操作: {action}")
            raise HTTPException(status_code=400, detail=f"不支持的操作: {action}")
    except HTTPException as he:
        logger.error(f"HTTP异常: {he.detail}")
        raise
    except Exception as e:
        logger.error(f"处理请求时出错: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 直接处理函数 ====================
async def handle_query_direct(request_data: Dict[str, Any]):
    """处理查询请求"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    groupid = request_data.get("groupid")
    msg = request_data.get("msg", "")
    mode = int(request_data.get("mode", 0))  # 默认为模糊匹配
    
    logger.info(f"查询请求: botid={botid}, userid={userid}, msg='{msg}', mode={mode}")
    
    if not botid or not userid:
        logger.error("缺少botid或userid参数")
        raise HTTPException(status_code=400, detail="缺少botid或userid参数")
    
    # 初始化全局信息
    data_file = f"M_{userid}"
    await _global_file(botid, userid, groupid, data_file)
    
    # 转换消息
    message = _transcoding(msg)
    logger.debug(f"转换后的消息: '{message}'")
    
    # 查询关键词
    otext = await lexicon_operation(botid, "get", value=message)
    
    if not otext:
        logger.info(f"未找到匹配的词条: '{message}'")
        return {
            "success": True,
            "action": "query",
            "found": False,
            "reply": "",
            "timestamp": time.time()
        }
    
    # 处理变量替换
    reply_text = otext
    if isinstance(otext, list) and len(otext) > 0:
        reply_text = otext[0]
        for i in range(1, min(6, len(otext))):
            reply_text = reply_text.replace(f"[n.{i}]", otext[i])
    
    logger.info(f"查询成功: '{message}' -> '{reply_text}'")
    return {
        "success": True,
        "action": "query",
        "found": True,
        "reply": reply_text,
        "mode": "exact" if isinstance(otext, list) else "fuzzy",
        "timestamp": time.time()
    }

async def handle_add_direct(request_data: Dict[str, Any]):
    """处理添加词条请求"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword")
    reply = request_data.get("reply")
    mode = int(request_data.get("mode", 1))  # 默认为精确匹配
    
    if not all([botid, userid, keyword, reply]):
        logger.error("添加词条缺少必要参数")
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"添加词条: botid={botid}, keyword='{keyword}', reply='{reply}', mode={mode}")
    
    # 初始化全局信息
    data_file = f"M_{userid}"
    await _global_file(botid, userid, None, data_file)
    
    # 添加词条
    result = await lexicon_operation(
        botid,
        "add",
        n=keyword,
        r=reply,
        s=mode
    )
    
    if result is False:
        logger.info(f"词条已存在: '{keyword}'")
        return {
            "success": False,
            "action": "add",
            "message": "词条已存在",
            "timestamp": time.time()
        }
    
    if isinstance(result, str):
        # 保存到文件
        save_result = await file_control(botid, data_files[botid], "w", result)
        if save_result == "写入成功":
            logger.info(f"词条保存成功: '{keyword}'")
            return {
                "success": True,
                "action": "add",
                "message": "添加成功",
                "keyword": keyword,
                "mode": mode,
                "timestamp": time.time()
            }
        else:
            logger.error(f"词条保存失败: '{keyword}'")
            raise HTTPException(status_code=500, detail="词条保存失败")
    
    logger.error(f"添加词条未知错误: '{keyword}'")
    raise HTTPException(status_code=500, detail="添加失败")

async def handle_remove_direct(request_data: Dict[str, Any]):
    """处理删除词条请求"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword")
    
    if not all([botid, userid, keyword]):
        logger.error("删除词条缺少必要参数")
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"删除词条: botid={botid}, keyword='{keyword}'")
    
    # 初始化全局信息
    data_file = f"M_{userid}"
    await _global_file(botid, userid, None, data_file)
    
    result = await lexicon_operation(
        botid,
        "remove",
        key_to_delete=keyword
    )
    
    if isinstance(result, str):
        # 保存到文件
        save_result = await file_control(botid, data_files[botid], "w", result)
        if save_result == "写入成功":
            logger.info(f"词条删除成功: '{keyword}'")
            return {
                "success": True,
                "action": "remove",
                "message": "删除成功",
                "keyword": keyword,
                "timestamp": time.time()
            }
        else:
            logger.error(f"词条删除保存失败: '{keyword}'")
            raise HTTPException(status_code=500, detail="词条删除保存失败")
    
    logger.info(f"词条不存在: '{keyword}'")
    raise HTTPException(status_code=404, detail="词条不存在")

async def handle_add_reply_direct(request_data: Dict[str, Any]):
    """处理添加回复选项"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword")
    reply = request_data.get("reply")
    
    if not all([botid, userid, keyword, reply]):
        logger.error("添加回复缺少必要参数")
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"添加回复: botid={botid}, keyword='{keyword}', reply='{reply}'")
    
    # 初始化全局信息
    data_file = f"M_{userid}"
    await _global_file(botid, userid, None, data_file)
    
    result = await lexicon_operation(
        botid,
        "add_r",
        name=keyword,
        value=reply
    )
    
    if isinstance(result, str):
        # 保存到文件
        save_result = await file_control(botid, data_files[botid], "w", result)
        if save_result == "写入成功":
            logger.info(f"回复添加成功: '{keyword}' -> '{reply}'")
            return {
                "success": True,
                "action": "add_r",
                "message": "添加回复成功",
                "keyword": keyword,
                "timestamp": time.time()
            }
        else:
            logger.error(f"回复添加保存失败: '{keyword}'")
            raise HTTPException(status_code=500, detail="回复添加保存失败")
    
    logger.info(f"词条不存在: '{keyword}'")
    raise HTTPException(status_code=404, detail="词条不存在")

async def handle_remove_reply_direct(request_data: Dict[str, Any]):
    """处理删除回复选项"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword")
    reply = request_data.get("reply")
    
    if not all([botid, userid, keyword, reply]):
        logger.error("删除回复缺少必要参数")
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"删除回复: botid={botid}, keyword='{keyword}', reply='{reply}'")
    
    # 初始化全局信息
    data_file = f"M_{userid}"
    await _global_file(botid, userid, None, data_file)
    
    result = await lexicon_operation(
        botid,
        "remove_r",
        name=keyword,
        value=reply
    )
    
    if isinstance(result, str):
        # 保存到文件
        save_result = await file_control(botid, data_files[botid], "w", result)
        if save_result == "写入成功":
            logger.info(f"回复删除成功: '{keyword}' -> '{reply}'")
            return {
                "success": True,
                "action": "remove_r",
                "message": "删除回复成功",
                "keyword": keyword,
                "timestamp": time.time()
            }
        else:
            logger.error(f"回复删除保存失败: '{keyword}'")
            raise HTTPException(status_code=500, detail="回复删除保存失败")
    
    logger.info(f"词条或回复不存在: '{keyword}' -> '{reply}'")
    raise HTTPException(status_code=404, detail="词条或回复不存在")

async def handle_get_config_direct(request_data: Dict[str, Any]):
    """获取配置信息"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    
    if not all([botid, userid]):
        logger.error("获取配置缺少botid或userid参数")
        raise HTTPException(status_code=400, detail="缺少botid或userid参数")
    
    logger.info(f"获取配置: botid={botid}, userid={userid}")
    
    # 初始化全局信息
    data_file = f"M_{userid}"
    await _global_file(botid, userid, None, data_file)
    
    config_keys = [
        '添加主人', '删除主人', '词库备份', '词库清空',
        '开启本群', '关闭本群', '切换词库', '精准问答',
        '模糊问答', '加选项', '删选项', '删词', '查词', '查id'
    ]
    
    config_values = {}
    for key in config_keys:
        value = await get_config(botid, key)
        if value:
            config_values[key] = value
    
    logger.info(f"配置获取成功: {len(config_values)} 项")
    return {
        "success": True,
        "action": "get_config",
        "config": config_values,
        "timestamp": time.time()
    }

async def handle_search_direct(request_data: Dict[str, Any]):
    """搜索关键词"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword")
    
    if not all([botid, userid, keyword]):
        logger.error("搜索关键词缺少必要参数")
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"搜索关键词: botid={botid}, keyword='{keyword}'")
    
    # 初始化全局信息
    data_file = f"M_{userid}"
    await _global_file(botid, userid, None, data_file)
    
    results = []
    bot_data = datas.get(botid, {"work": []})
    
    for idx, item in enumerate(bot_data["work"], 1):
        for key in item.keys():
            if keyword in key:
                results.append({
                    "id": idx,
                    "keyword": key,
                    "reply_count": len(item[key].get("r", [])),
                    "mode": item[key].get("s", 0)
                })
    
    logger.info(f"搜索完成: 找到 {len(results)} 个结果")
    return {
        "success": True,
        "action": "search",
        "keyword": keyword,
        "results": results,
        "count": len(results),
        "timestamp": time.time()
    }

async def handle_list_direct(request_data: Dict[str, Any]):
    """列出词条"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    
    if not all([botid, userid]):
        logger.error("列出词条缺少botid或userid参数")
        raise HTTPException(status_code=400, detail="缺少botid或userid参数")
    
    logger.info(f"列出词条: botid={botid}, userid={userid}")
    
    # 初始化全局信息
    data_file = f"M_{userid}"
    await _global_file(botid, userid, None, data_file)
    
    bot_data = datas.get(botid, {"work": []})
    items = []
    
    for idx, item in enumerate(bot_data["work"], 1):
        for key, value in item.items():
            items.append({
                "id": idx,
                "keyword": key,
                "mode": value.get("s", 0),
                "replies": value.get("r", []),
                "reply_count": len(value.get("r", []))
            })
    
    logger.info(f"列出词条完成: 共 {len(items)} 个词条")
    return {
        "success": True,
        "action": "list",
        "count": len(items),
        "items": items[:100],  # 限制返回数量
        "total": len(items),
        "timestamp": time.time()
    }

async def handle_count_direct(request_data: Dict[str, Any]):
    """统计词条数量"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    
    logger.info(f"统计词数: botid={botid}, userid={userid}")
    
    if not all([botid, userid]):
        logger.error("统计词数缺少botid或userid参数")
        raise HTTPException(status_code=400, detail="缺少botid或userid参数")
    
    # 初始化全局信息
    data_file = f"M_{userid}"
    await _global_file(botid, userid, None, data_file)
    
    bot_data = datas.get(botid, {"work": []})
    total_keywords = len(bot_data["work"])
    
    total_replies = 0
    for item in bot_data["work"]:
        for value in item.values():
            total_replies += len(value.get("r", []))
    
    logger.info(f"统计完成: 关键词={total_keywords}, 回复={total_replies}")
    
    return {
        "success": True,
        "action": "count",
        "keyword_count": total_keywords,
        "reply_count": total_replies,
        "timestamp": time.time()
    }

async def handle_test_direct(request_data: Dict[str, Any]):
    """测试接口"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    
    logger.info(f"测试接口: botid={botid}, userid={userid}")
    
    return {
        "success": True,
        "action": "test",
        "message": "API服务器运行正常",
        "timestamp": time.time(),
        "data_dir": get_data_dir()
    }

# ==================== 启动API服务器 ====================
def start_api_server():
    """启动API服务器"""
    try:
        config = uvicorn.Config(
            api_app,
            host=API_HOST,
            port=API_PORT,
            log_level="info",
            access_log=True
        )
        server = uvicorn.Server(config)
        
        logger.info(f"{'='*50}")
        logger.info(f"🚀 API服务器正在启动...")
        logger.info(f"📡 监听地址: {API_HOST}:{API_PORT}")
        logger.info(f"🔑 访问Token: {API_TOKEN}")
        logger.info(f"📚 API文档: http://{API_HOST}:{API_PORT}/docs")
        logger.info(f"🛡️  验证方式: Bearer {API_TOKEN}")
        logger.info(f"📂 数据目录: {get_data_dir()}")
        logger.info(f"📝 日志文件: {os.path.join(directory, 'api_log.txt')}")
        logger.info(f"{'='*50}")
        
        print(f"\n💡 使用示例:")
        print(f"curl -X POST http://{API_HOST}:{API_PORT}/api/v1/keyword \\")
        print(f"  -H \"Content-Type: application/json\" \\")
        print(f"  -H \"Authorization: Bearer {API_TOKEN}\" \\")
        print(f"  -d '{{\"action\":\"test\",\"botid\":123456,\"userid\":789012,\"token\":\"{API_TOKEN}\"}}'")
        
        # 保存Token到文件
        asyncio.run(file_control(123456, "Van_keyword_token.txt", "w", API_TOKEN))
        
        asyncio.run(server.serve())
    except Exception as e:
        logger.error(f"API服务器启动失败: {e}")
        import traceback
        traceback.print_exc()

# ==================== 主程序 ====================
if __name__ == "__main__":
    print(f"🎯 VanBot关键词API服务器")
    print(f"📂 工作目录: {directory}")
    
    # 确保数据目录存在
    data_dir = get_data_dir()
    print(f"📁 数据目录: {data_dir}")
    
    # 测试文件操作
    print(f"🔄 测试文件系统...")
    test_result = asyncio.run(file_control(123456, "test.txt", "w", "test content"))
    if test_result == "写入成功":
        print(f"✅ 文件系统测试通过")
    else:
        print(f"⚠️  文件系统可能有问题: {test_result}")
    
    # 启动API服务器
    start_api_server()