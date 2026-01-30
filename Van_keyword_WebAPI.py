import httpx, json, re, random, os, asyncio, time, secrets, threading, sys
from urllib.parse import quote
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Request, Body, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, validator
import uvicorn
import math
import base64
import hashlib
from urllib.parse import urlparse

# ==================== 配置 ====================
MISTAKE_TURN_TYPE = False  # 是否提高教词容错率，中文符自动转成英文符
API_HOST = "0.0.0.0"  # 监听所有网络接口
API_PORT = 8889  # API端口
API_TOKEN = secrets.token_hex(16)  # 生成随机token

print(f"\n{'='*50}")
print(f"🔐 API Token: {API_TOKEN}")
print(f"🌐 API地址: http://{API_HOST}:{API_PORT}")
print(f"🌍 WebUI地址: http://{API_HOST}:{API_PORT}/webui")
print(f"📖 API文档: http://{API_HOST}:{API_PORT}/docs")
print(f"{'='*50}\n")

# ==================== 全局变量 ====================
# 字典存储不同机器人的信息
global_group_ids = {}  # 消息环境
global_user_ids = {}  # 发送者
data_files = {}  # 词库文件
datas = {}  # 词库数据
global_bot_ids = {}  # 机器人
global_message_ids = {}  # 消息ID缓存
global_cache = {}  # 全局缓存

# 冷却时间数据
cooling_data = {}

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

async def get_cooling(bot_id, lexicon_id=None):
    """指令冷却处理"""
    try:
        if lexicon_id is None:
            return False
        
        file_content = await file_control(bot_id, f"cooling/{global_group_ids.get(bot_id, 'default')}.txt", "r")
        timestamp = datetime.now().timestamp()
        
        if not file_content or not file_content.strip():
            return False
        
        lines = file_content.strip().split('\n')
        for i, line in enumerate(lines):
            parts = line.split('=')
            if len(parts) == 3:
                user_id_part = parts[0].strip()
                lex_id_part = parts[1].strip()
                cool_time = parts[2].strip()
                
                try:
                    if (user_id_part == str(global_user_ids.get(bot_id, "")) and 
                        lex_id_part == str(lexicon_id)):
                        
                        cool_timestamp = float(cool_time)
                        if cool_timestamp <= timestamp:
                            return False
                        else:
                            remaining = int(cool_timestamp - timestamp)
                            return remaining
                except ValueError:
                    continue
        
        return False
    except Exception as e:
        logger.error(f"冷却检查错误: {e}")
        return False

# ==================== 词库操作函数 ====================
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
        
        # 检查是否是特殊恢复指令
        if value == "HUANYUAN":
            return ""
        
        group_user = await get_user_file(bot_id)
        if not group_user:
            group_user = global_group_ids.get(bot_id, "")
        
        logger.debug(f"group_user: {group_user}")
        
        # 首先检查主词库（datas）
        for item in datas[bot_id]["work"]:
            for key, val in item.items():
                logger.debug(f"检查词条: '{key}' (模式: {val.get('s', 0)}), 回复数: {len(val.get('r', []))}")
                
                # 检查权限
                if val.get('s') == 10 and str(global_user_ids.get(bot_id, "")) not in ADMIN_IDS:
                    logger.debug(f"跳过权限限制词条: {key}")
                    continue
                
                # 检查变量匹配 [n.?]
                tool_n = await get_n(key, value)
                if tool_n:
                    logger.info(f"变量匹配成功: {key}")
                    if val.get('r'):
                        text_n = random.choice(val['r'])
                        tool_n[0] = text_n
                        
                        if str(group_user).startswith('E'):
                            mapping = await file_control(bot_id, f"expand/{group_user}.json", "r")
                            if mapping:
                                tool_n[0] = replace_variable(text_n, mapping)
                        
                        return tool_n
                
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
                    
                    # 检查变量匹配 [n.?]
                    tool_n = await get_n(key, value)
                    if tool_n:
                        logger.info(f"变量匹配成功 (来自 {id}): {key}")
                        if val.get('r'):
                            text_n = random.choice(val['r'])
                            tool_n[0] = text_n
                            
                            if str(group_user).startswith('E'):
                                mapping = await file_control(bot_id, f"expand/{group_user}.json", "r")
                                if mapping:
                                    tool_n[0] = replace_variable(text_n, mapping)
                            
                            return tool_n
                    
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

# ==================== 消息转码和反编码 ====================
def _transcoding(text):
    """消息转码 - 将CQ码转换为内部格式"""
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

async def _decoding(bot_id, otext, group_id, cool_config=True, lexicon_id=0, lexicon_n=0, event_data=None):
    """
    消息反编码 - 将内部格式转换为实际内容
    
    Args:
        bot_id: 机器人ID
        otext: 原始文本
        group_id: 群组ID
        cool_config: 是否启用冷却
        lexicon_id: 词条ID（用于冷却）
        lexicon_n: 词库词条数
        event_data: 事件数据字典
    """
    
    # 冷却检查
    if cool_config and lexicon_id:
        cooling_time = await get_cooling(bot_id, lexicon_id)
        if cooling_time and cooling_time > 0:
            reply = await get_config(bot_id, '冷却中回复')
            if reply and '[冷却]' in reply:
                reply = reply.replace('[冷却]', str(cooling_time))
                logger.info(f"冷却中，剩余 {cooling_time} 秒")
                return {"type": "text", "content": reply}
    
    # 处理 [n.?] 变量
    if isinstance(otext, list):
        text = otext[0]
        # 替换变量
        for i in range(1, min(6, len(otext))):
            text = text.replace(f"[n.{i}]", otext[i])
        
        # 处理 .t 后缀
        text2 = []
        for item in otext:
            if isinstance(item, str) and '.' in item:
                parts = item.split('.', 1)
                if len(parts) > 1 and parts[1]:
                    match = re.search(r'[\d\w/.:?=&-]+', parts[1])
                    if match:
                        text2.append(match.group())
                    else:
                        text2.append(item)
                else:
                    text2.append(item)
            else:
                text2.append(item)
        
        # 替换 .t 变量
        for i in range(1, min(6, len(text2))):
            if i < len(text2):
                if i == 5:
                    text = text.replace(f"[n.{i}.t]", quote(text2[i]))
                else:
                    text = text.replace(f"[n.{i}.t]", text2[i])
    else:
        text = otext
    
    # 处理转义字符
    text = text.replace("\\n", "\n").replace("\\/", "/").replace("\\t", "\t").replace("\\r", "\r")
    
    # 检查分句发送
    clause = bool(re.search(r'\(-\d+-\)', text))
    if clause:
        logger.info("检测到分句发送语法")
        # 这里可以返回特殊标记，让调用者处理分句发送
        return {"type": "clause", "content": text}
    
    # 基础变量替换
    if event_data:
        # 群聊变量
        if 'group_id' in event_data:
            text = text.replace("[group]", str(event_data['group_id']))
            text = text.replace("[群号]", str(event_data['group_id']))
        
        # 用户变量
        if 'user_id' in event_data:
            text = text.replace("[qq]", str(event_data['user_id']))
            text = text.replace("[QQ号]", str(event_data['user_id']))
            text = text.replace("[qq2]", str(event_data.get('target_id', '')))
        
        # 机器人变量
        if 'self_id' in event_data:
            text = text.replace("[ai]", str(event_data['self_id']))
            text = text.replace("[AI号]", str(event_data['self_id']))
        
        # 昵称变量
        if 'sender' in event_data:
            sender = event_data['sender']
            if isinstance(sender, dict):
                text = text.replace("[name]", sender.get('nickname', ''))
                text = text.replace("[QQ名]", sender.get('nickname', ''))
                sender_card = sender.get('card', sender.get('nickname', ''))
                text = text.replace("[card]", sender_card)
                text = text.replace("[群昵称]", sender_card)
        
        # 消息ID
        if 'message_id' in event_data:
            text = text.replace("[id]", str(event_data['message_id']))
            text = text.replace("[消息id]", str(event_data['message_id']))
    
    # 词库相关变量
    text = text.replace("[词条id]", str(lexicon_id))
    text = text.replace("[词汇量]", str(int(lexicon_n) + 1))
    
    # 当前词库
    current_lexicon = await get_select_file(bot_id)
    text = text.replace("[当前词库]", str(current_lexicon))
    
    # 处理冷却时间设置 (60~)
    cooling_match = re.search(r'\((\d+)~\)', text)
    if cooling_match:
        cooling_seconds = int(cooling_match.group(1))
        if cooling_seconds == 0:
            # 当天午夜
            tomorrow = datetime.now() + timedelta(days=1)
            tomorrow_midnight = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
            cool_timestamp = tomorrow_midnight.timestamp()
        else:
            cool_timestamp = datetime.now().timestamp() + cooling_seconds
        
        # 保存冷却时间
        file_content = await file_control(bot_id, f"cooling/{global_group_ids.get(bot_id, 'default')}.txt", "r")
        line_type = False
        
        user_id = global_user_ids.get(bot_id, "")
        
        if not file_content or not file_content.strip():
            result = f"{user_id}={lexicon_id}={cool_timestamp}"
        else:
            lines = file_content.strip().split('\n')
            for i, line in enumerate(lines):
                parts = line.split('=')
                if len(parts) == 3 and parts[0] == str(user_id) and parts[1] == str(lexicon_id):
                    lines[i] = f"{user_id}={lexicon_id}={cool_timestamp}"
                    line_type = True
                    break
            
            if not line_type:
                lines.append(f"{user_id}={lexicon_id}={cool_timestamp}")
            result = '\n'.join(lines)
        
        await file_control(bot_id, f"cooling/{global_group_ids.get(bot_id, 'default')}.txt", "w", result)
        text = re.sub(r'\(\d+~\)', '', text)
        logger.info(f"设置冷却时间: {cooling_seconds}秒")
    
    # 处理随机数 (1-100)
    random_match = re.search(r'\((\d+)-(\d+)\)', text)
    if random_match:
        matches = re.findall(r'\(\d+-\d+\)', text)
        for m in matches:
            nums = list(map(int, m[1:-1].split('-')))
            rand_num = str(random.randint(nums[0], nums[1]))
            text = text.replace(m, rand_num, 1)
        logger.debug(f"生成随机数: {matches}")
    
    # 时间变量替换 (Y)、(M)、(D)、(h)、(m)、(s)
    now = datetime.now()
    time_replacements = {
        r'\(Y\)': str(now.year),
        r'\(M\)': str(now.month),
        r'\(D\)': str(now.day),
        r'\(h\)': str(now.hour),
        r'\(m\)': str(now.minute),
        r'\(s\)': str(now.second)
    }
    
    for pattern, replacement in time_replacements.items():
        text = re.sub(pattern, replacement, text)
    
    # 数学运算 (+运算式)
    def calc_all_plus_exprs(s, return_type="replaced_str"):
        pattern = r'\(\+((?:[^()]+|\((?:[^()]+|\([^()]*\))*\))*)\)'
        matches = re.findall(pattern, s)
        results = []
        
        for expr in matches:
            try:
                expr_calc = expr.replace("×", "*").replace("÷", "/")
                res = eval(expr_calc)
                results.append(res)
            except:
                results.append(f"(+{expr})")
        
        if return_type == "result_list":
            processed_results = []
            for res in results:
                if isinstance(res, float) and res.is_integer():
                    processed_results.append(int(res))
                else:
                    processed_results.append(res)
            return processed_results
        
        replaced = s
        for expr, res in zip(matches, results):
            if isinstance(res, float) and res.is_integer():
                res_processed = str(int(res))
            else:
                res_processed = str(res)
            replaced = replaced.replace(f"(+{expr})", res_processed)
        return replaced
    
    text = calc_all_plus_exprs(text)
    
    # 条件判断 {a>b}
    match_compare = re.search(r'\{(.*?)([><=])(.*?)\}', text)
    if match_compare:
        a = match_compare.group(1).strip()
        op = match_compare.group(2).strip()
        b = match_compare.group(3).strip()
        
        result = False
        try:
            a_val = float(a) if '.' in a or 'e' in a.lower() else int(a)
            b_val = float(b) if '.' in b or 'e' in b.lower() else int(b)
            
            if op == '>':
                result = a_val > b_val
            elif op == '<':
                result = a_val < b_val
            elif op == '=':
                result = a_val == b_val
        except:
            # 字符串比较
            if op == '=':
                result = a == b
        
        if result:
            text = re.sub(r'\{(\d+)([><=])(\d+)\}', '', text)
        else:
            reply = await get_config(bot_id, '判断不对时回复')
            if reply:
                return {"type": "text", "content": reply}
    
    # 处理CQ码/多媒体消息
    parts = re.split(r'(\[.*?\])', text)
    parts = [part for part in parts if part.strip()]
    
    result_messages = []
    
    for item in parts:
        if item.startswith('[') and item.endswith(']') and '.' in item:
            # 移除括号
            item = item[1:-1]
            # 分割类型和内容
            item_parts = item.split('.', 1)
            if len(item_parts) >= 2:
                cq_type = item_parts[0]
                cq_content = item_parts[1]
                
                # 处理不同类型的CQ码
                if cq_type in ["text", "文本"]:
                    result_messages.append({
                        "type": "text",
                        "content": cq_content
                    })
                
                elif cq_type in ["face", "表情"]:
                    result_messages.append({
                        "type": "face",
                        "id": cq_content
                    })
                
                elif cq_type in ["image", "图片"]:
                    result_messages.append({
                        "type": "image",
                        "url": cq_content
                    })
                
                elif cq_type in ["at", "艾特"]:
                    result_messages.append({
                        "type": "at",
                        "qq": cq_content
                    })
                
                elif cq_type in ["reply", "回复"]:
                    result_messages.append({
                        "type": "reply",
                        "id": cq_content
                    })
                
                elif cq_type in ["video", "视频"]:
                    result_messages.append({
                        "type": "video",
                        "url": cq_content
                    })
                
                elif cq_type in ["record", "语音"]:
                    result_messages.append({
                        "type": "record",
                        "url": cq_content
                    })
                
                elif cq_type == "json":
                    try:
                        json_data = json.loads(cq_content)
                        result_messages.append({
                            "type": "json",
                            "data": json_data
                        })
                    except:
                        result_messages.append({
                            "type": "text",
                            "content": cq_content
                        })
                
                elif cq_type == "music":
                    # 音乐消息格式：title.url
                    music_parts = cq_content.split('.', 1)
                    if len(music_parts) == 2:
                        title, url = music_parts
                        result_messages.append({
                            "type": "music",
                            "title": title,
                            "url": url
                        })
                
                elif cq_type == "share":
                    result_messages.append({
                        "type": "share",
                        "url": cq_content
                    })
                
                else:
                    # 未知类型，作为文本处理
                    result_messages.append({
                        "type": "text",
                        "content": f"[{item}]"
                    })
            else:
                result_messages.append({
                    "type": "text",
                    "content": f"[{item}]"
                })
        else:
            # 普通文本
            result_messages.append({
                "type": "text",
                "content": item
            })
    
    # 如果只有一条文本消息，直接返回文本内容
    if len(result_messages) == 1 and result_messages[0]["type"] == "text":
        return {"type": "text", "content": result_messages[0]["content"]}
    elif len(result_messages) == 0:
        return {"type": "text", "content": ""}
    else:
        return {"type": "mixed", "messages": result_messages}

# ==================== HTTP请求工具 ====================
async def get_data(url):
    """HTTP请求工具"""
    # URL编码处理
    text = url
    first_index = text.find('http')
    second_index = text.find('http', first_index + 1)
    if second_index != -1:
        url = text[:second_index] + quote(text[second_index:])
    
    logger.debug(f"HTTP请求: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 检查缓存
    cache_key = hashlib.md5(url.encode()).hexdigest()
    if cache_key in global_cache:
        cached_time, cached_data = global_cache[cache_key]
        if time.time() - cached_time < 300:  # 5分钟缓存
            logger.debug(f"使用缓存: {url}")
            return cached_data
    
    try:
        async with httpx.AsyncClient(timeout=60, verify=False) as client:
            resp = await client.get(url, headers=headers)
            data = resp.text.strip()
            # 更新缓存
            global_cache[cache_key] = (time.time(), data)
            return data
    except httpx.HTTPError as e:
        logger.error(f"HTTP请求失败: {e}")
        return ""
    except asyncio.TimeoutError:
        logger.error(f"HTTP请求超时: {url}")
        return ""
    except Exception as e:
        logger.error(f"HTTP请求异常: {e}")
        return ""

def json_to_text(data, indent=0, key_mapping=None):
    """JSON转文本工具"""
    # 解析键名映射
    if isinstance(key_mapping, str):
        key_mapping = {}
        for item in key_mapping.split(','):
            if item.strip():
                kv = item.split('=', 1)
                if len(kv) == 2:
                    key_mapping[kv[0].strip()] = kv[1].strip()
    
    try:
        if isinstance(data, str):
            data = json.loads(data)
    except:
        return data
    
    result = []
    space = ' ' * indent
    
    def format_value(value):
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return value
        return str(value)
    
    if isinstance(data, dict):
        keys_to_remove = []
        for key, value in data.items():
            if key_mapping and key in key_mapping and key_mapping[key] == "":
                keys_to_remove.append(key)
                continue
            
            mapped_key = key_mapping.get(key, key) if key_mapping else key
            
            if isinstance(value, (dict, list)):
                result.append(f"{space}{mapped_key}:")
                result.append(json_to_text(value, indent + 1, key_mapping))
            else:
                result.append(f"{space}{mapped_key}: {format_value(value)}")
        
        for key in keys_to_remove:
            data.pop(key, None)
        
        return '\n'.join(result)
    
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                result.append(f"{space}- ")
                result.append(json_to_text(item, indent + 1, key_mapping).strip())
            else:
                result.append(f"{space}- {format_value(item)}")
        return '\n'.join(result)
    
    else:
        return f"{space}{format_value(data)}"

# ==================== API相关定义 ====================
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证Token"""
    if credentials.credentials != API_TOKEN:
        logger.error(f"Token验证失败: {credentials.credentials}")
        raise HTTPException(status_code=401, detail="无效的Token")
    return credentials.credentials

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

# ==================== WebUI HTML模板 ====================
WEBUI_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VanBot 词库管理系统</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background-color: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 20px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        h1 {
            font-size: 28px;
            margin-bottom: 10px;
        }
        
        .subtitle {
            font-size: 16px;
            opacity: 0.9;
        }
        
        .api-info {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            border-left: 4px solid #667eea;
            font-family: monospace;
            font-size: 14px;
            color: #333;
        }
        
        .tab-container {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-bottom: 20px;
            background: white;
            padding: 10px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }
        
        .tab {
            padding: 12px 24px;
            background: #f0f0f0;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s ease;
        }
        
        .tab:hover {
            background: #e0e0e0;
        }
        
        .tab.active {
            background: #667eea;
            color: white;
        }
        
        .content-section {
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
            display: none;
        }
        
        .content-section.active {
            display: block;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .section-title {
            font-size: 18px;
            color: #667eea;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #f0f0f0;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: bold;
            color: #555;
        }
        
        input, select, textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 6px;
            font-size: 14px;
            transition: border-color 0.3s ease;
        }
        
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        
        textarea {
            min-height: 100px;
            resize: vertical;
            font-family: monospace;
        }
        
        .btn {
            background: #667eea;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        
        .btn:hover {
            background: #5a67d8;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(102, 126, 234, 0.3);
        }
        
        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        
        .btn-secondary {
            background: #48bb78;
        }
        
        .btn-secondary:hover {
            background: #38a169;
            box-shadow: 0 4px 8px rgba(72, 187, 120, 0.3);
        }
        
        .btn-danger {
            background: #f56565;
        }
        
        .btn-danger:hover {
            background: #e53e3e;
            box-shadow: 0 4px 8px rgba(245, 101, 101, 0.3);
        }
        
        .btn-group {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .result-area {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 6px;
            margin-top: 20px;
            border: 1px solid #e9ecef;
            max-height: 300px;
            overflow-y: auto;
        }
        
        .result-title {
            font-weight: bold;
            margin-bottom: 10px;
            color: #667eea;
        }
        
        .result-content {
            font-family: monospace;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .status-bar {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #333;
            color: white;
            padding: 10px 20px;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            display: none;
            z-index: 1000;
            font-size: 14px;
        }
        
        .status-bar.success {
            background: #48bb78;
        }
        
        .status-bar.error {
            background: #f56565;
        }
        
        .status-bar.info {
            background: #4299e1;
        }
        
        .grid-2 {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
        }
        
        .grid-3 {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }
        
        @media (max-width: 768px) {
            .grid-2, .grid-3 {
                grid-template-columns: 1fr;
            }
            
            .tab {
                padding: 10px 15px;
                font-size: 13px;
            }
        }
        
        .lexicon-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 10px;
            border-left: 4px solid #667eea;
        }
        
        .lexicon-keyword {
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }
        
        .lexicon-info {
            display: flex;
            gap: 15px;
            font-size: 13px;
            color: #666;
        }
        
        .mode-badge {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            background: #e9ecef;
        }
        
        .mode-exact {
            background: #bee3f8;
            color: #2c5282;
        }
        
        .mode-fuzzy {
            background: #fed7d7;
            color: #c53030;
        }
        
        .mode-admin {
            background: #fefcbf;
            color: #744210;
        }
        
        .reply-list {
            margin-top: 10px;
            padding-left: 20px;
        }
        
        .reply-item {
            background: white;
            padding: 8px 12px;
            margin-bottom: 5px;
            border-radius: 4px;
            border: 1px solid #e9ecef;
            font-size: 13px;
        }
        
        .collapsible {
            cursor: pointer;
            padding: 10px;
            background: #f0f0f0;
            border-radius: 6px;
            margin: 10px 0;
            font-weight: bold;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .collapsible:hover {
            background: #e0e0e0;
        }
        
        .collapsible-content {
            padding: 10px;
            display: none;
            animation: slideDown 0.3s ease;
        }
        
        @keyframes slideDown {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .monospace {
            font-family: 'Courier New', monospace;
        }
        
        .small {
            font-size: 12px;
            color: #666;
        }
        
        .inline-form {
            display: flex;
            gap: 10px;
            align-items: flex-end;
        }
        
        .inline-form .form-group {
            flex: 1;
            margin-bottom: 0;
        }
        
        .alert {
            padding: 15px;
            border-radius: 6px;
            margin: 20px 0;
        }
        
        .alert-info {
            background: #ebf8ff;
            border-left: 4px solid #4299e1;
            color: #2c5282;
        }
        
        .alert-warning {
            background: #fff5f5;
            border-left: 4px solid #f56565;
            color: #c53030;
        }
        
        .alert-success {
            background: #f0fff4;
            border-left: 4px solid #48bb78;
            color: #22543d;
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body>
    <div class="container">
        <header>
            <h1><i class="fas fa-robot"></i> VanBot 词库管理系统</h1>
            <div class="subtitle">功能完整的词库Web管理界面</div>
            <div class="api-info">
                API地址: <span id="api-url">加载中...</span> | Token: <span id="api-token">加载中...</span>
            </div>
        </header>
        
        <div class="tab-container">
            <button class="tab active" data-tab="status"><i class="fas fa-server"></i> 服务器状态</button>
            <button class="tab" data-tab="query"><i class="fas fa-search"></i> 关键词查询</button>
            <button class="tab" data-tab="decode"><i class="fas fa-code"></i> 消息解码</button>
            <button class="tab" data-tab="lexicon"><i class="fas fa-book"></i> 词库管理</button>
            <button class="tab" data-tab="search"><i class="fas fa-search-plus"></i> 搜索词条</button>
            <button class="tab" data-tab="config"><i class="fas fa-cog"></i> 配置管理</button>
            <button class="tab" data-tab="tools"><i class="fas fa-tools"></i> 工具集</button>
            <button class="tab" data-tab="examples"><i class="fas fa-graduation-cap"></i> 使用示例</button>
        </div>
        
        <!-- 服务器状态 -->
        <section id="status" class="content-section active">
            <h2 class="section-title"><i class="fas fa-server"></i> 服务器状态</h2>
            
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> 服务器状态每30秒自动刷新一次
            </div>
            
            <div class="grid-3">
                <div class="form-group">
                    <label>API主机</label>
                    <input type="text" id="status-host" readonly>
                </div>
                <div class="form-group">
                    <label>API端口</label>
                    <input type="text" id="status-port" readonly>
                </div>
                <div class="form-group">
                    <label>运行状态</label>
                    <input type="text" id="status-running" readonly>
                </div>
            </div>
            
            <div class="form-group">
                <label>数据目录</label>
                <input type="text" id="status-datadir" readonly>
            </div>
            
            <div class="form-group">
                <label>支持功能</label>
                <div class="result-area">
                    <div id="status-features">加载中...</div>
                </div>
            </div>
            
            <div class="btn-group">
                <button class="btn" onclick="refreshStatus()">
                    <i class="fas fa-sync-alt"></i> 刷新状态
                </button>
                <button class="btn btn-secondary" onclick="testConnection()">
                    <i class="fas fa-plug"></i> 测试连接
                </button>
            </div>
            
            <div class="result-area" id="status-result" style="display: none;">
                <div class="result-title">连接测试结果</div>
                <div class="result-content" id="status-test-result"></div>
            </div>
        </section>
        
        <!-- 关键词查询 -->
        <section id="query" class="content-section">
            <h2 class="section-title"><i class="fas fa-search"></i> 关键词查询</h2>
            
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> 查询关键词是否在词库中，支持精确匹配和模糊匹配
            </div>
            
            <div class="grid-3">
                <div class="form-group">
                    <label>机器人ID</label>
                    <input type="number" id="query-botid" placeholder="例如: 123456" value="123456">
                </div>
                <div class="form-group">
                    <label>用户ID</label>
                    <input type="number" id="query-userid" placeholder="例如: 789012" value="789012">
                </div>
                <div class="form-group">
                    <label>群组ID (可选)</label>
                    <input type="number" id="query-groupid" placeholder="例如: 987654">
                </div>
            </div>
            
            <div class="grid-2">
                <div class="form-group">
                    <label>查询消息</label>
                    <textarea id="query-msg" placeholder="输入要查询的消息内容...">你好</textarea>
                </div>
                <div class="form-group">
                    <label>匹配模式</label>
                    <select id="query-mode">
                        <option value="0">模糊匹配 (关键词在消息中)</option>
                        <option value="1" selected>精确匹配 (完全匹配)</option>
                    </select>
                    <div class="small">
                        精确模式: 消息必须完全等于关键词<br>
                        模糊模式: 消息中包含关键词即可
                    </div>
                </div>
            </div>
            
            <div class="btn-group">
                <button class="btn" onclick="queryKeyword()">
                    <i class="fas fa-search"></i> 查询关键词
                </button>
                <button class="btn btn-secondary" onclick="testQuery()">
                    <i class="fas fa-vial"></i> 测试查询
                </button>
            </div>
            
            <div class="result-area" id="query-result" style="display: none;">
                <div class="result-title">查询结果</div>
                <div class="result-content" id="query-result-content"></div>
            </div>
        </section>
        
        <!-- 消息解码 -->
        <section id="decode" class="content-section">
            <h2 class="section-title"><i class="fas fa-code"></i> 消息解码</h2>
            
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> 将包含变量的消息解码为实际内容，支持时间、数学运算、随机数等
            </div>
            
            <div class="grid-3">
                <div class="form-group">
                    <label>机器人ID</label>
                    <input type="number" id="decode-botid" placeholder="例如: 123456" value="123456">
                </div>
                <div class="form-group">
                    <label>用户ID</label>
                    <input type="number" id="decode-userid" placeholder="例如: 789012" value="789012">
                </div>
                <div class="form-group">
                    <label>群组ID (可选)</label>
                    <input type="number" id="decode-groupid" placeholder="例如: 987654">
                </div>
            </div>
            
            <div class="form-group">
                <label>待解码文本</label>
                <textarea id="decode-text" placeholder="输入包含变量的文本...">现在是(Y)年(M)月(D)日 (h):(m):(s)，随机数(1-100)</textarea>
                <div class="small monospace">
                    可用变量: [qq], [name], [群号], [词条id], [词汇量], (Y), (M), (D), (h), (m), (s), (1-100), (+1+2), (60~), {a>b}
                </div>
            </div>
            
            <div class="collapsible" onclick="toggleCollapse('decode-advanced')">
                高级设置 <i class="fas fa-chevron-down"></i>
            </div>
            <div id="decode-advanced" class="collapsible-content">
                <div class="grid-3">
                    <div class="form-group">
                        <label>词条ID (用于冷却)</label>
                        <input type="number" id="decode-lexiconid" value="0">
                    </div>
                    <div class="form-group">
                        <label>词库词条数</label>
                        <input type="number" id="decode-lexiconn" value="0">
                    </div>
                    <div class="form-group">
                        <label>启用冷却检查</label>
                        <select id="decode-coolconfig">
                            <option value="true">是</option>
                            <option value="false">否</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>事件数据 (JSON)</label>
                    <textarea id="decode-eventdata">{
  "user_id": 789012,
  "group_id": 987654,
  "self_id": 123456,
  "message_id": 123456789,
  "sender": {
    "nickname": "测试用户",
    "card": "测试昵称"
  }
}</textarea>
                </div>
            </div>
            
            <div class="btn-group">
                <button class="btn" onclick="decodeMessage()">
                    <i class="fas fa-code"></i> 解码消息
                </button>
                <button class="btn btn-secondary" onclick="decodeTest()">
                    <i class="fas fa-vial"></i> 测试解码
                </button>
            </div>
            
            <div class="result-area" id="decode-result" style="display: none;">
                <div class="result-title">解码结果</div>
                <div class="result-content" id="decode-result-content"></div>
            </div>
        </section>
        
        <!-- 词库管理 -->
        <section id="lexicon" class="content-section">
            <h2 class="section-title"><i class="fas fa-book"></i> 词库管理</h2>
            
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> 管理词库中的关键词和回复，支持增删改查
            </div>
            
            <div class="grid-3">
                <div class="form-group">
                    <label>机器人ID</label>
                    <input type="number" id="lexicon-botid" placeholder="例如: 123456" value="123456">
                </div>
                <div class="form-group">
                    <label>用户ID</label>
                    <input type="number" id="lexicon-userid" placeholder="例如: 789012" value="789012">
                </div>
                <div class="form-group">
                    <label>操作类型</label>
                    <select id="lexicon-optype">
                        <option value="add">添加词条</option>
                        <option value="remove">删除词条</option>
                        <option value="add_r">添加回复</option>
                        <option value="remove_r">删除回复</option>
                    </select>
                </div>
            </div>
            
            <div class="form-group">
                <label>关键词</label>
                <input type="text" id="lexicon-keyword" placeholder="输入关键词...">
            </div>
            
            <div class="form-group" id="lexicon-reply-group">
                <label>回复内容</label>
                <textarea id="lexicon-reply" placeholder="输入回复内容..."></textarea>
            </div>
            
            <div class="form-group" id="lexicon-mode-group">
                <label>匹配模式</label>
                <select id="lexicon-mode">
                    <option value="1">精确匹配</option>
                    <option value="0">模糊匹配</option>
                    <option value="10">管理员专用</option>
                </select>
            </div>
            
            <div class="btn-group">
                <button class="btn" onclick="lexiconOperation()">
                    <i class="fas fa-play"></i> 执行操作
                </button>
                <button class="btn btn-secondary" onclick="listLexicon()">
                    <i class="fas fa-list"></i> 列出词条
                </button>
                <button class="btn btn-secondary" onclick="countLexicon()">
                    <i class="fas fa-calculator"></i> 统计词数
                </button>
            </div>
            
            <div class="result-area" id="lexicon-result" style="display: none;">
                <div class="result-title">操作结果</div>
                <div class="result-content" id="lexicon-result-content"></div>
            </div>
            
            <div class="result-area" id="lexicon-list" style="display: none;">
                <div class="result-title">词条列表</div>
                <div id="lexicon-list-content"></div>
            </div>
        </section>
        
        <!-- 搜索词条 -->
        <section id="search" class="content-section">
            <h2 class="section-title"><i class="fas fa-search-plus"></i> 搜索词条</h2>
            
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> 在词库中搜索包含特定关键词的词条
            </div>
            
            <div class="grid-2">
                <div class="form-group">
                    <label>机器人ID</label>
                    <input type="number" id="search-botid" placeholder="例如: 123456" value="123456">
                </div>
                <div class="form-group">
                    <label>用户ID</label>
                    <input type="number" id="search-userid" placeholder="例如: 789012" value="789012">
                </div>
            </div>
            
            <div class="form-group">
                <label>搜索关键词</label>
                <input type="text" id="search-keyword" placeholder="输入要搜索的关键词...">
            </div>
            
            <button class="btn" onclick="searchLexicon()">
                <i class="fas fa-search"></i> 搜索词条
            </button>
            
            <div class="result-area" id="search-result" style="display: none;">
                <div class="result-title">搜索结果</div>
                <div id="search-result-content"></div>
            </div>
        </section>
        
        <!-- 配置管理 -->
        <section id="config" class="content-section">
            <h2 class="section-title"><i class="fas fa-cog"></i> 配置管理</h2>
            
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> 查看和管理机器人的配置信息
            </div>
            
            <div class="grid-2">
                <div class="form-group">
                    <label>机器人ID</label>
                    <input type="number" id="config-botid" placeholder="例如: 123456" value="123456">
                </div>
                <div class="form-group">
                    <label>用户ID</label>
                    <input type="number" id="config-userid" placeholder="例如: 789012" value="789012">
                </div>
            </div>
            
            <button class="btn" onclick="getConfig()">
                <i class="fas fa-download"></i> 获取配置
            </button>
            
            <div class="result-area" id="config-result" style="display: none;">
                <div class="result-title">配置信息</div>
                <div class="result-content" id="config-result-content"></div>
            </div>
        </section>
        
        <!-- 工具集 -->
        <section id="tools" class="content-section">
            <h2 class="section-title"><i class="fas fa-tools"></i> 工具集</h2>
            
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> 各种实用工具，包括消息转码、JSON格式化等
            </div>
            
            <div class="collapsible" onclick="toggleCollapse('tool-transcode')">
                <i class="fas fa-exchange-alt"></i> 消息转码 <i class="fas fa-chevron-down"></i>
            </div>
            <div id="tool-transcode" class="collapsible-content">
                <div class="form-group">
                    <label>待转码文本 (CQ码转内部格式)</label>
                    <textarea id="tool-transcode-text" placeholder="输入包含CQ码的文本...">[CQ:at,qq=123456] 你好 [CQ:image,url=http://example.com/img.jpg]</textarea>
                </div>
                <button class="btn" onclick="toolTranscode()">
                    <i class="fas fa-exchange-alt"></i> 执行转码
                </button>
                <div class="result-area" id="tool-transcode-result" style="display: none; margin-top: 10px;">
                    <div class="result-title">转码结果</div>
                    <div class="result-content" id="tool-transcode-result-content"></div>
                </div>
            </div>
            
            <div class="collapsible" onclick="toggleCollapse('tool-json')">
                <i class="fas fa-code"></i> JSON格式化 <i class="fas fa-chevron-down"></i>
            </div>
            <div id="tool-json" class="collapsible-content">
                <div class="form-group">
                    <label>JSON文本</label>
                    <textarea id="tool-json-text" placeholder="输入JSON文本...">{"name":"测试","value":123}</textarea>
                </div>
                <button class="btn" onclick="toolFormatJson()">
                    <i class="fas fa-indent"></i> 格式化JSON
                </button>
                <div class="result-area" id="tool-json-result" style="display: none; margin-top: 10px;">
                    <div class="result-title">格式化结果</div>
                    <div class="result-content" id="tool-json-result-content"></div>
                </div>
            </div>
            
            <div class="collapsible" onclick="toggleCollapse('tool-admin')">
                <i class="fas fa-user-shield"></i> 管理员管理 <i class="fas fa-chevron-down"></i>
            </div>
            <div id="tool-admin" class="collapsible-content">
                <div class="form-group">
                    <label>管理员操作</label>
                    <select id="tool-admin-op">
                        <option value="view">查看管理员</option>
                        <option value="add">添加管理员</option>
                        <option value="remove">删除管理员</option>
                    </select>
                </div>
                <div class="form-group" id="tool-admin-user-group" style="display: none;">
                    <label>用户ID</label>
                    <input type="number" id="tool-admin-user" placeholder="输入用户ID...">
                </div>
                <button class="btn" onclick="toolAdmin()">
                    <i class="fas fa-cog"></i> 执行操作
                </button>
                <div class="result-area" id="tool-admin-result" style="display: none; margin-top: 10px;">
                    <div class="result-title">操作结果</div>
                    <div class="result-content" id="tool-admin-result-content"></div>
                </div>
            </div>
        </section>
        
        <!-- 使用示例 -->
        <section id="examples" class="content-section">
            <h2 class="section-title"><i class="fas fa-graduation-cap"></i> 使用示例</h2>
            
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> 查看各种功能的使用示例和代码
            </div>
            
            <div class="collapsible" onclick="toggleCollapse('example-query')">
                <i class="fas fa-search"></i> 查询示例 <i class="fas fa-chevron-down"></i>
            </div>
            <div id="example-query" class="collapsible-content">
                <div class="form-group">
                    <label>curl命令示例</label>
                    <textarea id="example-query-curl" readonly rows="4"></textarea>
                </div>
                <div class="form-group">
                    <label>JavaScript示例</label>
                    <textarea id="example-query-js" readonly rows="6"></textarea>
                </div>
                <button class="btn btn-secondary" onclick="copyExample('query')">
                    <i class="fas fa-copy"></i> 复制curl示例
                </button>
            </div>
            
            <div class="collapsible" onclick="toggleCollapse('example-decode')">
                <i class="fas fa-code"></i> 解码示例 <i class="fas fa-chevron-down"></i>
            </div>
            <div id="example-decode" class="collapsible-content">
                <div class="form-group">
                    <label>curl命令示例</label>
                    <textarea id="example-decode-curl" readonly rows="4"></textarea>
                </div>
                <div class="form-group">
                    <label>JavaScript示例</label>
                    <textarea id="example-decode-js" readonly rows="6"></textarea>
                </div>
                <button class="btn btn-secondary" onclick="copyExample('decode')">
                    <i class="fas fa-copy"></i> 复制curl示例
                </button>
            </div>
            
            <div class="collapsible" onclick="toggleCollapse('example-add')">
                <i class="fas fa-plus"></i> 添加词条示例 <i class="fas fa-chevron-down"></i>
            </div>
            <div id="example-add" class="collapsible-content">
                <div class="form-group">
                    <label>curl命令示例</label>
                    <textarea id="example-add-curl" readonly rows="4"></textarea>
                </div>
                <div class="form-group">
                    <label>JavaScript示例</label>
                    <textarea id="example-add-js" readonly rows="6"></textarea>
                </div>
                <button class="btn btn-secondary" onclick="copyExample('add')">
                    <i class="fas fa-copy"></i> 复制curl示例
                </button>
            </div>
        </section>
    </div>
    
    <div class="status-bar" id="status-bar"></div>
    
    <script>
        // 全局变量
        let apiUrl = '';
        let apiToken = '';
        let statusInterval = null;
        
        // 页面加载完成
        document.addEventListener('DOMContentLoaded', function() {
            // 初始化标签页切换
            initTabs();
            
            // 初始化页面数据
            initPage();
            
            // 开始自动刷新状态
            startStatusRefresh();
            
            // 更新示例
            updateExamples();
            
            // 监听操作类型变化
            document.getElementById('lexicon-optype').addEventListener('change', function() {
                updateLexiconForm();
            });
            
            // 监听管理员操作变化
            document.getElementById('tool-admin-op').addEventListener('change', function() {
                updateAdminForm();
            });
            
            // 设置API信息
            apiUrl = window.location.origin;
            apiToken = "{{api_token}}";
            updateApiInfo();
        });
        
        // 初始化标签页
        function initTabs() {
            const tabs = document.querySelectorAll('.tab');
            const sections = document.querySelectorAll('.content-section');
            
            tabs.forEach(tab => {
                tab.addEventListener('click', function() {
                    const tabId = this.getAttribute('data-tab');
                    
                    // 更新标签状态
                    tabs.forEach(t => t.classList.remove('active'));
                    this.classList.add('active');
                    
                    // 显示对应内容
                    sections.forEach(section => {
                        section.classList.remove('active');
                        if (section.id === tabId) {
                            section.classList.add('active');
                        }
                    });
                });
            });
        }
        
        // 初始化页面数据
        function initPage() {
            // 尝试从本地存储获取API信息
            const savedApiUrl = localStorage.getItem('vanbot_api_url');
            const savedApiToken = localStorage.getItem('vanbot_api_token');
            
            if (savedApiUrl && savedApiToken) {
                apiUrl = savedApiUrl;
                apiToken = savedApiToken;
                updateApiInfo();
            }
            
            // 从页面获取API信息
            const apiUrlElement = document.getElementById('api-url');
            const apiTokenElement = document.getElementById('api-token');
            
            if (apiUrlElement && apiTokenElement) {
                apiUrl = apiUrlElement.textContent.replace('加载中...', '').trim() || window.location.origin;
                apiToken = apiTokenElement.textContent.replace('加载中...', '').trim();
                
                // 保存到本地存储
                localStorage.setItem('vanbot_api_url', apiUrl);
                localStorage.setItem('vanbot_api_token', apiToken);
            }
        }
        
        // 更新API信息显示
        function updateApiInfo() {
            document.getElementById('api-url').textContent = apiUrl;
            document.getElementById('api-token').textContent = apiToken;
        }
        
        // 开始自动刷新状态
        function startStatusRefresh() {
            // 先立即刷新一次
            refreshStatus();
            
            // 然后每30秒刷新一次
            statusInterval = setInterval(refreshStatus, 30000);
        }
        
        // 刷新服务器状态
        function refreshStatus() {
            if (!apiUrl) return;
            
            const button = document.querySelector('#status .btn');
            const originalHtml = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> 刷新中...';
            button.disabled = true;
            
            fetch(`${apiUrl}/status`)
                .then(response => response.json())
                .then(data => {
                    // 更新状态显示
                    document.getElementById('status-host').value = data.host || '未知';
                    document.getElementById('status-port').value = data.port || '未知';
                    document.getElementById('status-running').value = data.running ? '运行中' : '停止';
                    document.getElementById('status-datadir').value = data.data_dir || '未知';
                    
                    // 更新功能列表
                    const features = data.features || [];
                    const featuresHtml = features.map(f => `<div>✓ ${f}</div>`).join('');
                    document.getElementById('status-features').innerHTML = featuresHtml;
                    
                    showStatus('状态已刷新', 'success');
                })
                .catch(err => {
                    console.error('获取状态失败:', err);
                    showStatus('无法获取服务器状态', 'error');
                })
                .finally(() => {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                });
        }
        
        // 测试连接
        function testConnection() {
            const button = document.querySelector('#status .btn-secondary');
            const originalHtml = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> 测试中...';
            button.disabled = true;
            
            const resultArea = document.getElementById('status-result');
            const resultContent = document.getElementById('status-test-result');
            
            fetch(`${apiUrl}/`)
                .then(response => {
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    return response.json();
                })
                .then(data => {
                    resultContent.textContent = JSON.stringify(data, null, 2);
                    resultArea.style.display = 'block';
                    showStatus('连接测试成功', 'success');
                })
                .catch(err => {
                    resultContent.textContent = `连接失败: ${err.message}`;
                    resultArea.style.display = 'block';
                    showStatus('连接测试失败', 'error');
                })
                .finally(() => {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                });
        }
        
        // 查询关键词
        function queryKeyword() {
            const botid = document.getElementById('query-botid').value;
            const userid = document.getElementById('query-userid').value;
            const groupid = document.getElementById('query-groupid').value;
            const msg = document.getElementById('query-msg').value;
            const mode = document.getElementById('query-mode').value;
            
            if (!botid || !userid || !msg) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
            const button = document.querySelector('#query .btn');
            const originalHtml = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> 查询中...';
            button.disabled = true;
            
            const payload = {
                action: 'query',
                botid: parseInt(botid),
                userid: parseInt(userid),
                msg: msg,
                mode: parseInt(mode),
                token: apiToken
            };
            
            if (groupid) {
                payload.groupid = parseInt(groupid);
            }
            
            callApi(payload, 'query-result', 'query-result-content')
                .then(data => {
                    if (data.success) {
                        showStatus('查询成功', 'success');
                    } else {
                        showStatus('查询完成但未找到匹配', 'info');
                    }
                })
                .catch(() => {
                    showStatus('查询失败', 'error');
                })
                .finally(() => {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                });
        }
        
        // 测试查询
        function testQuery() {
            document.getElementById('query-botid').value = '123456';
            document.getElementById('query-userid').value = '789012';
            document.getElementById('query-groupid').value = '987654';
            document.getElementById('query-msg').value = '你好';
            document.getElementById('query-mode').value = '1';
            queryKeyword();
        }
        
        // 解码消息
        function decodeMessage() {
            const botid = document.getElementById('decode-botid').value;
            const userid = document.getElementById('decode-userid').value;
            const groupid = document.getElementById('decode-groupid').value;
            const text = document.getElementById('decode-text').value;
            const lexiconid = document.getElementById('decode-lexiconid').value;
            const lexiconn = document.getElementById('decode-lexiconn').value;
            const coolconfig = document.getElementById('decode-coolconfig').value;
            const eventdata = document.getElementById('decode-eventdata').value;
            
            if (!botid || !userid || !text) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
            const button = document.querySelector('#decode .btn');
            const originalHtml = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> 解码中...';
            button.disabled = true;
            
            const payload = {
                action: 'decode',
                botid: parseInt(botid),
                userid: parseInt(userid),
                text: text,
                token: apiToken
            };
            
            if (groupid) {
                payload.groupid = parseInt(groupid);
            }
            
            if (lexiconid) {
                payload.lexicon_id = parseInt(lexiconid);
            }
            
            if (lexiconn) {
                payload.lexicon_n = parseInt(lexiconn);
            }
            
            payload.cool_config = coolconfig === 'true';
            
            try {
                payload.event_data = JSON.parse(eventdata);
            } catch (e) {
                payload.event_data = {};
            }
            
            callApi(payload, 'decode-result', 'decode-result-content')
                .then(() => {
                    showStatus('解码成功', 'success');
                })
                .catch(() => {
                    showStatus('解码失败', 'error');
                })
                .finally(() => {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                });
        }
        
        // 测试解码
        function decodeTest() {
            document.getElementById('decode-botid').value = '123456';
            document.getElementById('decode-userid').value = '789012';
            document.getElementById('decode-groupid').value = '987654';
            document.getElementById('decode-text').value = '现在是(Y)年(M)月(D)日 (h):(m):(s)，随机数(1-100)，数学运算(+2*3+5)';
            decodeMessage();
        }
        
        // 词库操作
        function lexiconOperation() {
            const botid = document.getElementById('lexicon-botid').value;
            const userid = document.getElementById('lexicon-userid').value;
            const optype = document.getElementById('lexicon-optype').value;
            const keyword = document.getElementById('lexicon-keyword').value;
            const reply = document.getElementById('lexicon-reply').value;
            const mode = document.getElementById('lexicon-mode').value;
            
            if (!botid || !userid || !keyword) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
            if ((optype === 'add' || optype === 'add_r') && !reply) {
                showStatus('请填写回复内容', 'error');
                return;
            }
            
            if (optype === 'remove_r' && !reply) {
                showStatus('请填写要删除的回复内容', 'error');
                return;
            }
            
            const button = document.querySelector('#lexicon .btn');
            const originalHtml = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> 执行中...';
            button.disabled = true;
            
            const payload = {
                action: optype,
                botid: parseInt(botid),
                userid: parseInt(userid),
                token: apiToken
            };
            
            if (optype === 'add') {
                payload.keyword = keyword;
                payload.reply = reply;
                payload.mode = parseInt(mode);
            } else if (optype === 'remove') {
                payload.keyword = keyword;
            } else if (optype === 'add_r') {
                payload.keyword = keyword;
                payload.reply = reply;
            } else if (optype === 'remove_r') {
                payload.keyword = keyword;
                payload.reply = reply;
            }
            
            callApi(payload, 'lexicon-result', 'lexicon-result-content')
                .then(data => {
                    if (data.success) {
                        showStatus('操作成功', 'success');
                        // 清空表单
                        document.getElementById('lexicon-keyword').value = '';
                        document.getElementById('lexicon-reply').value = '';
                    } else {
                        showStatus('操作失败: ' + (data.message || '未知错误'), 'error');
                    }
                })
                .catch(() => {
                    showStatus('操作失败', 'error');
                })
                .finally(() => {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                });
        }
        
        // 列出词条
        function listLexicon() {
            const botid = document.getElementById('lexicon-botid').value;
            const userid = document.getElementById('lexicon-userid').value;
            
            if (!botid || !userid) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
            const button = document.querySelector('#lexicon .btn-secondary:nth-child(2)');
            const originalHtml = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> 加载中...';
            button.disabled = true;
            
            const payload = {
                action: 'list',
                botid: parseInt(botid),
                userid: parseInt(userid),
                token: apiToken
            };
            
            callApi(payload, null, null)
                .then(data => {
                    if (data.success) {
                        const listArea = document.getElementById('lexicon-list');
                        const listContent = document.getElementById('lexicon-list-content');
                        
                        let html = '';
                        
                        if (data.items && data.items.length > 0) {
                            html += `<div class="small">共 ${data.count} 个词条</div>`;
                            
                            data.items.forEach(item => {
                                const modeText = item.mode === 1 ? '精确' : item.mode === 10 ? '管理' : '模糊';
                                const modeClass = item.mode === 1 ? 'mode-exact' : item.mode === 10 ? 'mode-admin' : 'mode-fuzzy';
                                
                                html += `
                                <div class="lexicon-item">
                                    <div class="lexicon-keyword">${item.keyword}</div>
                                    <div class="lexicon-info">
                                        <span>ID: ${item.id}</span>
                                        <span class="mode-badge ${modeClass}">${modeText}匹配</span>
                                        <span>回复数: ${item.reply_count}</span>
                                    </div>
                                </div>`;
                            });
                        } else {
                            html = '<div>词库为空</div>';
                        }
                        
                        listContent.innerHTML = html;
                        listArea.style.display = 'block';
                        showStatus('加载词条列表成功', 'success');
                    }
                })
                .catch(() => {
                    showStatus('加载词条列表失败', 'error');
                })
                .finally(() => {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                });
        }
        
        // 统计词数
        function countLexicon() {
            const botid = document.getElementById('lexicon-botid').value;
            const userid = document.getElementById('lexicon-userid').value;
            
            if (!botid || !userid) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
            const button = document.querySelector('#lexicon .btn-secondary:nth-child(3)');
            const originalHtml = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> 统计中...';
            button.disabled = true;
            
            const payload = {
                action: 'count',
                botid: parseInt(botid),
                userid: parseInt(userid),
                token: apiToken
            };
            
            callApi(payload, 'lexicon-result', 'lexicon-result-content')
                .then(data => {
                    if (data.success) {
                        showStatus(`统计完成: 关键词 ${data.keyword_count} 个，回复 ${data.reply_count} 条`, 'success');
                    }
                })
                .catch(() => {
                    showStatus('统计失败', 'error');
                })
                .finally(() => {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                });
        }
        
        // 搜索词条
        function searchLexicon() {
            const botid = document.getElementById('search-botid').value;
            const userid = document.getElementById('search-userid').value;
            const keyword = document.getElementById('search-keyword').value;
            
            if (!botid || !userid || !keyword) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
            const button = document.querySelector('#search .btn');
            const originalHtml = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> 搜索中...';
            button.disabled = true;
            
            const payload = {
                action: 'search',
                botid: parseInt(botid),
                userid: parseInt(userid),
                keyword: keyword,
                token: apiToken
            };
            
            callApi(payload, null, null)
                .then(data => {
                    if (data.success) {
                        const resultArea = document.getElementById('search-result');
                        const resultContent = document.getElementById('search-result-content');
                        
                        let html = '';
                        
                        if (data.results && data.results.length > 0) {
                            html += `<div class="small">找到 ${data.count} 个结果</div>`;
                            
                            data.results.forEach(item => {
                                const modeText = item.mode === 1 ? '精确' : item.mode === 10 ? '管理' : '模糊';
                                const modeClass = item.mode === 1 ? 'mode-exact' : item.mode === 10 ? 'mode-admin' : 'mode-fuzzy';
                                
                                html += `
                                <div class="lexicon-item">
                                    <div class="lexicon-keyword">${item.keyword}</div>
                                    <div class="lexicon-info">
                                        <span>ID: ${item.id}</span>
                                        <span class="mode-badge ${modeClass}">${modeText}匹配</span>
                                        <span>回复数: ${item.reply_count}</span>
                                    </div>
                                </div>`;
                            });
                        } else {
                            html = '<div>未找到匹配的词条</div>';
                        }
                        
                        resultContent.innerHTML = html;
                        resultArea.style.display = 'block';
                        showStatus('搜索完成', 'success');
                    }
                })
                .catch(() => {
                    showStatus('搜索失败', 'error');
                })
                .finally(() => {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                });
        }
        
        // 获取配置
        function getConfig() {
            const botid = document.getElementById('config-botid').value;
            const userid = document.getElementById('config-userid').value;
            
            if (!botid || !userid) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
            const button = document.querySelector('#config .btn');
            const originalHtml = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> 获取中...';
            button.disabled = true;
            
            const payload = {
                action: 'get_config',
                botid: parseInt(botid),
                userid: parseInt(userid),
                token: apiToken
            };
            
            callApi(payload, 'config-result', 'config-result-content')
                .then(() => {
                    showStatus('获取配置成功', 'success');
                })
                .catch(() => {
                    showStatus('获取配置失败', 'error');
                })
                .finally(() => {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                });
        }
        
        // 工具 - 消息转码
        function toolTranscode() {
            const text = document.getElementById('tool-transcode-text').value;
            
            if (!text) {
                showStatus('请输入待转码文本', 'error');
                return;
            }
            
            const payload = {
                action: 'transcode',
                text: text,
                token: apiToken
            };
            
            const resultArea = document.getElementById('tool-transcode-result');
            const resultContent = document.getElementById('tool-transcode-result-content');
            
            callApi(payload, null, null)
                .then(data => {
                    if (data.success) {
                        resultContent.textContent = `原始: ${data.original}\n\n转码后: ${data.transcoded}`;
                        resultArea.style.display = 'block';
                        showStatus('转码成功', 'success');
                    }
                })
                .catch(() => {
                    showStatus('转码失败', 'error');
                });
        }
        
        // 工具 - JSON格式化
        function toolFormatJson() {
            const text = document.getElementById('tool-json-text').value;
            
            if (!text) {
                showStatus('请输入JSON文本', 'error');
                return;
            }
            
            try {
                const obj = JSON.parse(text);
                const formatted = JSON.stringify(obj, null, 2);
                
                const resultArea = document.getElementById('tool-json-result');
                const resultContent = document.getElementById('tool-json-result-content');
                
                resultContent.textContent = formatted;
                resultArea.style.display = 'block';
                showStatus('格式化成功', 'success');
            } catch (e) {
                showStatus('JSON格式错误: ' + e.message, 'error');
            }
        }
        
        // 工具 - 管理员管理
        function toolAdmin() {
            const op = document.getElementById('tool-admin-op').value;
            const user = document.getElementById('tool-admin-user').value;
            
            const resultArea = document.getElementById('tool-admin-result');
            const resultContent = document.getElementById('tool-admin-result-content');
            
            // 通过API操作管理员
            const payload = {
                action: 'admin_manage',
                op: op,
                token: apiToken
            };
            
            if (op === 'add' || op === 'remove') {
                if (!user) {
                    showStatus('请输入用户ID', 'error');
                    return;
                }
                payload.user = user;
            }
            
            const button = document.querySelector('#tool-admin .btn');
            const originalHtml = button.innerHTML;
            button.innerHTML = '<div class="loading"></div> 处理中...';
            button.disabled = true;
            
            callApi(payload, null, null)
                .then(data => {
                    if (data.success) {
                        resultContent.textContent = data.message || '操作成功';
                        resultArea.style.display = 'block';
                        showStatus(data.message || '操作成功', 'success');
                    }
                })
                .catch(err => {
                    resultContent.textContent = '操作失败: ' + err.message;
                    resultArea.style.display = 'block';
                    showStatus('操作失败', 'error');
                })
                .finally(() => {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                });
        }
        
        // 更新词库表单显示
        function updateLexiconForm() {
            const optype = document.getElementById('lexicon-optype').value;
            const replyGroup = document.getElementById('lexicon-reply-group');
            const modeGroup = document.getElementById('lexicon-mode-group');
            
            if (optype === 'add') {
                replyGroup.style.display = 'block';
                modeGroup.style.display = 'block';
                document.getElementById('lexicon-keyword').placeholder = '输入新关键词...';
            } else if (optype === 'remove') {
                replyGroup.style.display = 'none';
                modeGroup.style.display = 'none';
                document.getElementById('lexicon-keyword').placeholder = '输入要删除的关键词...';
            } else if (optype === 'add_r') {
                replyGroup.style.display = 'block';
                modeGroup.style.display = 'none';
                document.getElementById('lexicon-keyword').placeholder = '输入已有关键词...';
            } else if (optype === 'remove_r') {
                replyGroup.style.display = 'block';
                modeGroup.style.display = 'none';
                document.getElementById('lexicon-keyword').placeholder = '输入已有关键词...';
            }
        }
        
        // 更新管理员表单显示
        function updateAdminForm() {
            const op = document.getElementById('tool-admin-op').value;
            const userGroup = document.getElementById('tool-admin-user-group');
            
            if (op === 'add' || op === 'remove') {
                userGroup.style.display = 'block';
            } else {
                userGroup.style.display = 'none';
            }
        }
        
        // 切换折叠区域
        function toggleCollapse(id) {
            const content = document.getElementById(id);
            const icon = content.previousElementSibling.querySelector('.fa-chevron-down');
            
            if (content.style.display === 'block') {
                content.style.display = 'none';
                icon.className = 'fas fa-chevron-down';
            } else {
                content.style.display = 'block';
                icon.className = 'fas fa-chevron-up';
            }
        }
        
        // 调用API
        async function callApi(payload, resultAreaId, resultContentId) {
            const headers = {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${apiToken}`
            };
            
            const response = await fetch(`${apiUrl}/api/v1/keyword`, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`API请求失败: ${response.status} - ${errorText}`);
            }
            
            const data = await response.json();
            
            // 如果有结果区域ID，则显示结果
            if (resultAreaId && resultContentId) {
                const resultArea = document.getElementById(resultAreaId);
                const resultContent = document.getElementById(resultContentId);
                
                resultContent.textContent = JSON.stringify(data, null, 2);
                resultArea.style.display = 'block';
            }
            
            return data;
        }
        
        // 显示状态消息
        function showStatus(message, type) {
            const statusBar = document.getElementById('status-bar');
            statusBar.textContent = message;
            statusBar.className = 'status-bar ' + type;
            statusBar.style.display = 'block';
            
            // 3秒后自动隐藏
            setTimeout(() => {
                statusBar.style.display = 'none';
            }, 3000);
        }
        
        // 更新使用示例
        function updateExamples() {
            // 查询示例
            document.getElementById('example-query-curl').value = `curl -X POST ${apiUrl}/api/v1/keyword \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${apiToken}" \\
  -d '{
    "action": "query",
    "botid": 123456,
    "userid": 789012,
    "msg": "你好",
    "token": "${apiToken}"
  }'`;
            
            document.getElementById('example-query-js').value = `fetch('${apiUrl}/api/v1/keyword', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ${apiToken}'
  },
  body: JSON.stringify({
    action: 'query',
    botid: 123456,
    userid: 789012,
    msg: '你好',
    token: '${apiToken}'
  })
})
.then(response => response.json())
.then(data => console.log(data));`;
            
            // 解码示例
            document.getElementById('example-decode-curl').value = `curl -X POST ${apiUrl}/api/v1/keyword \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${apiToken}" \\
  -d '{
    "action": "decode",
    "botid": 123456,
    "userid": 789012,
    "text": "现在是(Y)年(M)月(D)日",
    "token": "${apiToken}"
  }'`;
            
            document.getElementById('example-decode-js').value = `fetch('${apiUrl}/api/v1/keyword', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ${apiToken}'
  },
  body: JSON.stringify({
    action: 'decode',
    botid: 123456,
    userid: 789012,
    text: '现在是(Y)年(M)月(D)日',
    token: '${apiToken}'
  })
})
.then(response => response.json())
.then(data => console.log(data));`;
            
            // 添加词条示例
            document.getElementById('example-add-curl').value = `curl -X POST ${apiUrl}/api/v1/keyword \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${apiToken}" \\
  -d '{
    "action": "add",
    "botid": 123456,
    "userid": 789012,
    "keyword": "测试",
    "reply": "这是一个测试回复",
    "mode": 1,
    "token": "${apiToken}"
  }'`;
            
            document.getElementById('example-add-js').value = `fetch('${apiUrl}/api/v1/keyword', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ${apiToken}'
  },
  body: JSON.stringify({
    action: 'add',
    botid: 123456,
    userid: 789012,
    keyword: '测试',
    reply: '这是一个测试回复',
    mode: 1,
    token: '${apiToken}'
  })
})
.then(response => response.json())
.then(data => console.log(data));`;
        }
        
        // 复制示例
        function copyExample(type) {
            const textarea = document.getElementById(`example-${type}-curl`);
            textarea.select();
            textarea.setSelectionRange(0, 99999); // 移动端支持
            document.execCommand('copy');
            showStatus('已复制到剪贴板', 'success');
        }
    </script>
</body>
</html>
"""

# ==================== API路由 ====================
@api_app.get("/")
async def root():
    """API根目录"""
    return {
        "status": "online",
        "service": "VanBot Keyword API",
        "webui": f"http://{API_HOST}:{API_PORT}/webui",
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
        "data_dir": data_dir,
        "features": [
            "关键词查询",
            "词条管理",
            "变量替换系统",
            "多媒体消息处理",
            "冷却时间系统",
            "时间变量",
            "数学运算",
            "随机数生成",
            "WebUI管理界面"
        ]
    }

@api_app.get("/webui")
async def webui():
    """WebUI主界面"""
    # 替换HTML中的变量
    html_content = WEBUI_HTML.replace("{{api_token}}", API_TOKEN)
    return HTMLResponse(content=html_content)

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
        elif action == "decode":
            return await handle_decode_direct(request_data)
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
        elif action == "transcode":
            return await handle_transcode_direct(request_data)
        elif action == "admin_manage":
            return await handle_admin_manage_direct(request_data)
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

async def handle_decode_direct(request_data: Dict[str, Any]):
    """处理解码请求 - 支持完整的变量替换"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    groupid = request_data.get("groupid")
    text = request_data.get("text", "")
    lexicon_id = int(request_data.get("lexicon_id", 0))
    lexicon_n = int(request_data.get("lexicon_n", 0))
    event_data = request_data.get("event_data", {})
    cool_config = request_data.get("cool_config", True)
    
    logger.info(f"解码请求: botid={botid}, text='{text[:50]}...', lexicon_id={lexicon_id}")
    
    if not botid or not userid:
        logger.error("缺少botid或userid参数")
        raise HTTPException(status_code=400, detail="缺少botid或userid参数")
    
    # 初始化全局信息
    data_file = f"M_{userid}"
    await _global_file(botid, userid, groupid, data_file)
    
    # 解码处理
    result = await _decoding(
        botid, 
        text, 
        groupid, 
        cool_config, 
        lexicon_id, 
        lexicon_n, 
        event_data
    )
    
    logger.info(f"解码完成: 类型={result.get('type')}")
    return {
        "success": True,
        "action": "decode",
        "result": result,
        "timestamp": time.time()
    }

async def handle_transcode_direct(request_data: Dict[str, Any]):
    """处理转码请求 - CQ码转内部格式"""
    text = request_data.get("text", "")
    
    logger.info(f"转码请求: text='{text[:50]}...'")
    
    result = _transcoding(text)
    
    return {
        "success": True,
        "action": "transcode",
        "original": text,
        "transcoded": result,
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
        "data_dir": get_data_dir(),
        "features": [
            "基础查询功能",
            "变量替换系统 [qq], [name], [群号]",
            "时间变量 (Y), (M), (D), (h), (m), (s)",
            "数学运算 (+1+2)",
            "随机数生成 (1-100)",
            "冷却时间系统 (60~)",
            "多媒体消息处理 [image], [face], [at]",
            "条件判断 {a>b}"
        ]
    }

async def handle_admin_manage_direct(request_data: Dict[str, Any]):
    """管理员管理"""
    op = request_data.get("op", "view")
    user = request_data.get("user")
    
    if op == "view":
        admin_list = ADMIN_IDS
        return {
            "success": True,
            "action": "admin_manage",
            "op": op,
            "admins": admin_list,
            "count": len(admin_list),
            "message": f"当前有 {len(admin_list)} 个管理员",
            "timestamp": time.time()
        }
    elif op == "add":
        if not user:
            raise HTTPException(status_code=400, detail="缺少用户ID参数")
        
        # 添加管理员
        refresh_admin(user, "add")
        admin_list = ADMIN_IDS
        
        return {
            "success": True,
            "action": "admin_manage",
            "op": op,
            "user": user,
            "admins": admin_list,
            "message": f"已添加管理员 {user}",
            "timestamp": time.time()
        }
    elif op == "remove":
        if not user:
            raise HTTPException(status_code=400, detail="缺少用户ID参数")
        
        # 删除管理员
        refresh_admin(user, "rm")
        admin_list = ADMIN_IDS
        
        return {
            "success": True,
            "action": "admin_manage",
            "op": op,
            "user": user,
            "admins": admin_list,
            "message": f"已删除管理员 {user}",
            "timestamp": time.time()
        }
    else:
        raise HTTPException(status_code=400, detail="不支持的操作类型")

# ==================== 示例API调用 ====================
@api_app.get("/api/v1/examples")
async def get_examples():
    """获取API使用示例"""
    return {
        "examples": {
            "query_example": {
                "method": "POST",
                "url": f"http://{API_HOST}:{API_PORT}/api/v1/keyword",
                "headers": {
                    "Authorization": f"Bearer {API_TOKEN}",
                    "Content-Type": "application/json"
                },
                "body": {
                    "action": "query",
                    "botid": 123456,
                    "userid": 789012,
                    "groupid": 987654,
                    "msg": "你好",
                    "token": API_TOKEN
                }
            },
            "decode_example": {
                "method": "POST",
                "url": f"http://{API_HOST}:{API_PORT}/api/v1/keyword",
                "headers": {
                    "Authorization": f"Bearer {API_TOKEN}",
                    "Content-Type": "application/json"
                },
                "body": {
                    "action": "decode",
                    "botid": 123456,
                    "userid": 789012,
                    "text": "现在是(Y)年(M)月(D)日 (h):(m):(s)",
                    "event_data": {
                        "user_id": 789012,
                        "group_id": 987654,
                        "self_id": 123456,
                        "message_id": 123456789
                    },
                    "token": API_TOKEN
                }
            },
            "add_example": {
                "method": "POST",
                "url": f"http://{API_HOST}:{API_PORT}/api/v1/keyword",
                "headers": {
                    "Authorization": f"Bearer {API_TOKEN}",
                    "Content-Type": "application/json"
                },
                "body": {
                    "action": "add",
                    "botid": 123456,
                    "userid": 789012,
                    "keyword": "测试",
                    "reply": "这是一个测试回复",
                    "mode": 1,
                    "token": API_TOKEN
                }
            }
        }
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
        logger.info(f"🌍 WebUI地址: http://{API_HOST}:{API_PORT}/webui")
        logger.info(f"🔑 访问Token: {API_TOKEN}")
        logger.info(f"📚 API文档: http://{API_HOST}:{API_PORT}/docs")
        logger.info(f"🛡️  验证方式: Bearer {API_TOKEN}")
        logger.info(f"📂 数据目录: {get_data_dir()}")
        logger.info(f"📝 日志文件: {os.path.join(directory, 'api_log.txt')}")
        logger.info(f"{'='*50}")
        
        print(f"\n💡 新增功能说明:")
        print(f"  ✅ 完整的变量替换系统: [qq], [name], [群号], [词条id], [词汇量]")
        print(f"  ✅ 时间变量: (Y), (M), (D), (h), (m), (s)")
        print(f"  ✅ 数学运算: (+1+2), (+2*3/4)")
        print(f"  ✅ 随机数: (1-100)")
        print(f"  ✅ 冷却时间: (60~)")
        print(f"  ✅ 条件判断: a>b")
        print(f"  ✅ 多媒体消息: [image.url], [face.id], [at.qq], [reply.id]")
        print(f"  ✅ 消息转码: CQ码转内部格式")
        print(f"  ✅ WebUI管理界面: 访问 /webui")
        
        print(f"\n💡 使用示例:")
        print(f"curl -X POST http://{API_HOST}:{API_PORT}/api/v1/keyword \\")
        print(f"  -H \"Content-Type: application/json\" \\")
        print(f"  -H \"Authorization: Bearer {API_TOKEN}\" \\")
        print(f"  -d '{{\"action\":\"decode\",\"botid\":123456,\"userid\":789012,\"text\":\"现在是(Y)年(M)月(D)日 [image.http://example.com/img.jpg]\",\"token\":\"{API_TOKEN}\"}}'")
        
        print(f"\n🌐 打开浏览器访问: http://{API_HOST}:{API_PORT}/webui")
        
        # 保存Token到文件
        asyncio.run(file_control(123456, "Van_keyword_token.txt", "w", API_TOKEN))
        
        asyncio.run(server.serve())
    except Exception as e:
        logger.error(f"API服务器启动失败: {e}")
        import traceback
        traceback.print_exc()

# ==================== 主程序 ====================
if __name__ == "__main__":
    print(f"🎯 VanBot关键词API服务器 (集成WebUI)")
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