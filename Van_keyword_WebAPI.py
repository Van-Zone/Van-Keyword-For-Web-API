import httpx, json, re, random, os, asyncio, time, secrets, threading, sys
from urllib.parse import quote
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Request, Body, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, validator, Field
import uvicorn
import math
import base64
import hashlib
from urllib.parse import urlparse
import ast

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
send_message_n = 0  # 发消息数
get_message_n = 0  # 收消息数

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
    data_dir = os.path.join(directory, "Van_keyword")
    data_dir = ensure_dir(data_dir)
    return data_dir

# ==================== 文件操作 ====================
async def file_control(bot_id, filename, mode, content=None):
    """文件操作函数 - 完全匹配原版"""
    try:
        if mode == 'w' and content is None:
            raise ValueError("缺参数")
        
        if bot_id and filename:
            file_path = f"{directory}/Van_keyword/{bot_id}/{filename}"
        elif bot_id == "updata":
            file_path = f"{directory}/Van_keyword/Van_keyword.py"
        elif filename:
            file_path = f"{directory}/Van_keyword/{filename}"
        else:
            file_path = f"{directory}/qq.txt"
        
        dir_path = os.path.dirname(file_path)

        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

        if not os.path.exists(file_path):
            with open(file_path, "w", encoding='utf-8') as f:
                if filename.startswith("lexicon") or filename.startswith("coins.json"):
                    config = json.dumps({"work": []})
                    f.write(config)
                else:
                    config = ""
                    f.write(config)
            print(f"文件不存在，已自动创建：{filename}")

        with open(file_path, mode, encoding='utf-8') as f:
            if mode == 'r':
                return f.read()
            elif mode == 'w':
                f.write(content)
                return "写入成功"
    except Exception as e:
        logger.error(f"文件操作失败：{str(e)}")
        return None

# ==================== 管理词库函数 ====================
async def get_select_file(bot_id, admin_id=None, new_value=None):
    """管理使用的词库 - 完全匹配原版"""
    data_dict = {}
    file_content = await file_control(bot_id, "select.txt", "r")
    if file_content:
        lines = file_content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or '=' not in line:
                continue
            key, value = line.split('=', 1)
            data_dict[key.strip()] = value.strip()
    
    if admin_id is not None and new_value is not None:
        admin_id_str = str(admin_id)
        data_dict[admin_id_str] = new_value
        new_data = '\n'.join([f"{k}={v}" for k, v in data_dict.items()])
        await file_control(bot_id, "select.txt", "w", new_data)
    
    if admin_id and str(admin_id) in data_dict:
        return data_dict[str(admin_id)]
    else:
        return f"M_{admin_id}" if admin_id else "common"

async def get_user_file(bot_id, env, env_id, new_value=None):
    """群/用户使用的词库 - 完全匹配原版"""
    if env == "group":
        lexicon_name = str(env_id)
    elif env == "private":
        lexicon_name = "private"

    data_dict = {}
    file_content = await file_control(bot_id, "switch.txt", "r")
    if file_content:
        lines = file_content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or '=' not in line:
                continue
            key, value = line.split('=', 1)
            data_dict[key.strip()] = value.strip()
    
    if new_value is not None:
        data_dict[lexicon_name] = new_value
        new_data = '\n'.join([f"{k}={v}" for k, v in data_dict.items()])
        await file_control(bot_id, "switch.txt", "w", new_data)
    
    if lexicon_name in data_dict:
        group_user = data_dict[lexicon_name]
    else:
        group_user = ""
    if not group_user:
        group_user = lexicon_name
    return group_user

# ==================== 核心函数 ====================
def refresh_admin(user=None, op=None):
    """刷新管理员列表"""
    path = os.path.join(directory, "qq.txt")
    
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

async def get_n(key, text):
    """处理变量[n.?] - 完全匹配原版"""
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

async def get_cooling(bot_id, user_id, group_id, lexicon_id):
    """指令冷却处理 - 完全匹配原版"""
    file_content = await file_control(bot_id, f"cooling/{group_id}.txt", "r")
    timestamp = datetime.now().timestamp()
    
    if not file_content or not file_content.strip():
        return False
    
    lines = file_content.strip().split('\n')
    for line in lines:
        parts = line.split('=')
        if len(parts) == 3 and int(parts[0]) == int(user_id) and int(parts[1]) == int(lexicon_id):
            if float(parts[2]) > float(timestamp):
                return int(float(parts[2]) - float(timestamp))
            else:
                return False
    return False

# ==================== 词库操作函数 ====================
async def lexicon_operation(bot_id, data_id, op_type, **kwargs):
    """
    词库操作函数 - 完全匹配原版 Van_keyword.py
    
    Args:
        bot_id: 机器人ID
        data_id: 词库数组 [common, 群ID/用户ID, 使用的词库名]
        op_type: 操作类型 (get, add, remove_name, remove_id, look_name, look_id)
        **kwargs: 其他参数
    """
    valid_ops = {"get", "add", "remove_name", "remove_id", "look_name", "look_id"}
    if op_type not in valid_ops:
        return f"无效操作类型！支持：{list(valid_ops)}"
    
    # 查询词条
    if op_type == "get":
        value = kwargs.get("value")
        if not value:
            return ""
        
        global get_message_n, send_message_n
        get_message_n += 1
        
        group_user = data_id[1]
        
        # 查词条
        lexicon_id_counter = 0
        for id in data_id:
            data = await file_control(bot_id, f"lexicon/{id}.json", "r")
            try:
                data = json.loads(data)
            except:
                data = {"work": []}
            
            if id == data_id[1]:
                lexicon_n = len(data.get('work', []))
                # 内置词条
                default_item = {
                    "echo [n.1]": {
                        "r": ["{[qq]in[主人列表]}[n.1]"]
                    }
                }
                data['work'].insert(0, default_item)
            
            for item in data['work']:
                for key in item:
                    lexicon_id_counter += 1
                    tool_n = await get_n(key, value)
                    if tool_n:
                        text_n = random.choice(item[key]['r'])
                        tool_n[0] = text_n
                        return tool_n
                    if key in value:
                        if item[key].get('s', 0) == 0:
                            result = random.choice(item[key]['r'])
                            return result
                        elif item[key].get('s', 0) == 1 and key == value:
                            result = random.choice(item[key]['r'])
                            return result
        
        if value == "HUANYUAN":
            return ""
        return ""
    
    # 添加词条
    elif op_type == "add":
        n = kwargs.get("n")
        r = kwargs.get("r")
        s = kwargs.get("s")
        
        if not all([n, r, s is not None]):
            return "缺少参数"

        datas = await file_control(bot_id, f"lexicon/{data_id}.json", "r")
        try:
            datas = json.loads(datas)
        except:
            datas = {"work": []}
        
        for item in datas["work"]:
            if n in item.keys():
                return "词条已存在"

        new_item = {n: {"r": [f"{r}"], "s": s}}
        datas["work"].append(new_item)
        result = json.dumps(datas, indent=4, ensure_ascii=False)
        await file_control(bot_id, f"lexicon/{data_id}.json", "w", result)
        return "添加成功"

    # 删除词条
    elif op_type == "remove_name":
        remove_name = kwargs.get("remove_name")
        if not remove_name:
            return "缺少参数"
        
        datas = await file_control(bot_id, f"lexicon/{data_id}.json", "r")
        try:
            datas = json.loads(datas)
        except:
            return "词库文件错误"
        
        new_work = [item for item in datas["work"] if list(item.keys())[0] != remove_name]
        new_work = {"work": new_work}
        result = json.dumps(new_work, indent=4, ensure_ascii=False)
        await file_control(bot_id, f"lexicon/{data_id}.json", "w", result)
        return "删词成功"
    
    elif op_type == "remove_id":
        remove_id = kwargs.get("remove_id")
        if not remove_id:
            return "缺少参数"
            
        datas = await file_control(bot_id, f"lexicon/{data_id}.json", "r")
        try:
            datas = json.loads(datas)
        except:
            return "词库文件错误"
        
        try:
            target_id = int(remove_id)
            if target_id <= 0:
                return "id必须是正整数哦~"
            if target_id > len(datas["work"]):
                return f"不存在id为 {target_id} 的词条哦~"
            deleted_item = datas["work"].pop(target_id - 1)
            deleted_key = list(deleted_item.keys())[0]
            result = json.dumps(datas, indent=4, ensure_ascii=False)
            await file_control(bot_id, f"lexicon/{data_id}.json", "w", result)
            return f"已成功删除id为 {target_id} 的词条（触发词：{deleted_key}）"
        except ValueError:
            return "id必须是数字哦~"
        except Exception as e:
            return f"词条删除失败：{str(e)}"
    
    elif op_type == "look_id":
        look_id = kwargs.get("look_id")
        if not look_id:
            return "缺少参数"

        datas = await file_control(bot_id, f"lexicon/{data_id}.json", "r")
        try:
            datas = json.loads(datas)
        except:
            return "词库文件错误"
        
        if '-' not in look_id:
            look_id = look_id + '-' + look_id
        look_id = look_id.split('-')
        message = []
        i = 0
        ii = 0
        for item in datas["work"]:
            for key, value in item.items():
                i = i+1
                if i >= int(look_id[0]) and i <= int(look_id[1]):
                    if len(value['r']) > 1:
                        if look_id[0] == look_id[1]:
                            message.append(f"\n{i}.{key}\n")
                            if value.get('s', 0) == 1:
                                message.append("[精准模式]")
                            elif value.get('s', 0) == 0:
                                message.append("[模糊模式]")
                            for value_much in value['r']:
                                ii = ii+1
                                message.append(f"\n({ii}){value_much}")
                        else:
                            message.append(f"\n{i}.{key}")
                    else:
                        if look_id[0] == look_id[1]:
                            message.append(f"\n{i}.{key}\n")
                            if value.get('s', 0) == 1:
                                message.append("[精准模式]")
                            elif value.get('s', 0) == 0:
                                message.append("[模糊模式]")
                            message.append(f"\n{value['r'][0]}")
                        else:
                            message.append(f"\n{i}.{key}")
        message.append(f"\n\n共{i}个词，当前查询{look_id[0]}-{look_id[1]}")
        return "".join(message)

    elif op_type == "look_name":
        look_name = kwargs.get("look_name")
        if not look_name:
            return "缺少参数"
        
        datas = await file_control(bot_id, f"lexicon/{data_id}.json", "r")
        try:
            datas = json.loads(datas)
        except:
            return "词库文件错误"
        
        result = []
        found = False
        i = 0
        for item in datas["work"]:
            for key, value in item.items():
                i += 1
                if look_name in key:
                    found = True
                    result.append(f"{i}.{key}\n")
        if not found:
            result.append("未找到包含该关键词的词条呢~")
        return '\n'.join(result)

# ==================== 消息转码和反编码 ====================
async def _transcoding(text):
    """消息转码 - 将CQ码转换为内部格式 - 完全匹配原版"""
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

async def _decoding(otext, bot_id, env, env_id, event=None, cool_config=True):
    """
    消息反编码 - 将内部格式转换为实际内容 - 完全匹配原版 Van_keyword.py
    """
    bot_id = str(bot_id)
    env_id = str(env_id)
    
    # [n.?]变量的进一步处理
    if isinstance(otext, list):
        text = otext[0]
        text = text.replace("[n.1]", otext[1]).replace("[n.2]", otext[2]).replace("[n.3]", otext[3]).replace("[n.4]", otext[4]).replace("[n.5]", otext[5])
        # text2 为提取.后面字符
        text2 = []
        for item in otext:
            if '.' in item:
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
        text = text.replace("[n.1.t]", text2[1] if len(text2) > 1 else "").replace("[n.2.t]", text2[2] if len(text2) > 2 else "").replace("[n.3.t]", text2[3] if len(text2) > 3 else "").replace("[n.4.t]", text2[4] if len(text2) > 4 else "").replace("[n.5.t]", quote(text2[5]) if len(text2) > 5 else "")
    else:
        text = otext

    # 处理拓展词库变量
    def replace_variable(text, map):
        for line in map.split('\n'):
            if line.startswith('变量[') and ']:' in line:
                key = line.split('[')[1].split(']')[0]
                val = line.split(']:', 1)[1]
                text = text.replace(f'[{key}]', val)
        return text
    
    select_lexicon = await get_select_file(bot_id, event.user_id if event else None)
    map_content = await file_control(bot_id, f"expand/{select_lexicon}.van", "r") or ""
    text = replace_variable(text, map_content)
    
    # 教词相关变量
    match = re.search(r'#精准加词\|([^|]*)\|(.*)#', text)
    if match:
        a = match.group(1).replace(",", ".")
        b = match.group(2).replace(",", ".")
        result = await lexicon_operation(bot_id, select_lexicon, "add", n=a, r=b, s=1)
        text = re.sub(r'#精准加词\|[^|]*\|.*#', result, text)
    match = re.search(r'#模糊加词\|([^|]*)\|(.*)#', text)
    if match:
        a = match.group(1).replace(",", ".")
        b = match.group(2).replace(",", ".")
        result = await lexicon_operation(bot_id, select_lexicon, "add", n=a, r=b, s=0)
        text = re.sub(r'#模糊加词\|[^|]*\|.*#', result, text)
    match = re.search(r'#删词\|([^|]*)#', text)
    if match:
        a = match.group(1)
        result = await lexicon_operation(bot_id, select_lexicon, "remove_name", remove_name=a)
        text = re.sub(r'#删词\|[^|]*#', result, text)
    match = re.search(r'#删id\|([^|]*)#', text)
    if match:
        a = match.group(1)
        result = await lexicon_operation(bot_id, select_lexicon, "remove_id", remove_id=a)
        text = re.sub(r'#删id\|[^|]*#', result, text)
    match = re.search(r'#查id\|([^|]*)#', text)
    if match:
        a = match.group(1)
        result = await lexicon_operation(bot_id, select_lexicon, "look_id", look_id=a)
        return {"type": "api_result", "content": result, "should_send": True}
    match = re.search(r'#查词\|([^|]*)#', text)
    if match:
        a = match.group(1)
        result = await lexicon_operation(bot_id, select_lexicon, "look_name", look_name=a)
        return {"type": "api_result", "content": result, "should_send": True}

    # 字符串处理
    text = text.replace("\\n", "\n").replace("\\/", "/").replace("\\t", "\t").replace("\\r", "\r")
    # 选择变量
    text = random.choice(text.split('[or]'))
    # 出错回复
    match = re.search(r'\(!(.*?)!\)', text)
    error_text = match.group(1) if match else ""
    text = re.sub(r"\(!.*?!\)", "", text)
    
    # 分情况处理
    user_id = str(event.user_id) if event else ""
    group_id = str(env_id)
    
    # 冷却变量
    if event and cool_config:
        lexicon_id_for_cool = 0  # 需要从外部传入
        type = await get_cooling(bot_id, user_id, group_id, lexicon_id_for_cool)
        if type:
            reply = error_text
            reply = reply.replace("[冷却]", str(type))
            return {"type": "text", "content": reply}
    
    # 分段延迟变量
    clause = bool(re.search(r'\(-\d+-\)', text))
    if clause:
        return {"type": "clause", "content": text}
    
    if env == 'group':
        text = text.replace("[group]", f"{group_id}")
        text = text.replace("[群号]", f"{group_id}")
    
    text = text.replace("[qq]", user_id)
    text = text.replace("[QQ号]", user_id)
    
    if event and hasattr(event, 'message_id'):
        text = text.replace("[id]", f"{event.message_id}")
        text = text.replace("[消息id]", f"{event.message_id}")

    if event and hasattr(event, 'sender'):
        if hasattr(event.sender, 'nickname'):
            text = text.replace("[name]", getattr(event.sender, 'nickname', ''))
            text = text.replace("[QQ名]", getattr(event.sender, 'nickname', ''))
            text = text.replace("[名字]", getattr(event.sender, 'nickname', ''))
        sender_card = event.sender.card if hasattr(event.sender, 'card') and event.sender.card else (event.sender.nickname if hasattr(event.sender, 'nickname') else '')
        text = text.replace("[card]", sender_card)
        text = text.replace("[群昵称]", sender_card)
    
    # 不管怎样都处理
    global send_message_n, get_message_n
    if "]" in text:
        text = text.replace("[收消息数]", f"{get_message_n}")
        text = text.replace("[发消息数]", f"{send_message_n}")
        # 需要从外部传入 lexicon_id 和 lexicon_n
        # text = text.replace("[词条id]", f"{lexicon_id}")
        # text = text.replace("[词汇量]", f"{int(lexicon_n)}")
        text = text.replace("[选择的词库]", f"{select_lexicon}")
        text = text.replace("[使用的词库]", f"{await get_user_file(bot_id, env, env_id)}")
        text = text.replace("[ai]", bot_id)
        text = text.replace("[AI号]", bot_id)
    
    # 身份列表
    if "主人列表" in text:
        master_list = await file_control("", "", "r") or ""
        text = text.replace("[主人列表]", f"[{master_list}]")
        text = text.replace("<主人列表>", f"<{master_list}>")
    if "高管列表" in text:
        manage_list = await file_control("", "qq.txt", "r") or ""
        text = text.replace("[高管列表]", f"[{manage_list}]")
        text = text.replace("<高管列表>", f"<{manage_list}>")
    if "代管列表" in text:
        manage_list = await file_control(bot_id, "qq.txt", "r") or ""
        text = text.replace("[代管列表]", f"[{manage_list}]")
        text = text.replace("<代管列表>", f"<{manage_list}>")
    
    # Cookie相关
    if '[qun_skey' in text:
        text = text.replace('[qun_skey]', 'p_skey_example')
    if '[ti_skey' in text:
        text = text.replace('[ti_skey]', 'p_skey_example')
    if '[vip_skey' in text:
        text = text.replace('[vip_skey]', 'p_skey_example')
    if '[skey]' in text:
        text = text.replace('[skey]', 'skey_example')
    if '[vantk]' in text:
        text = text.replace('[vantk]', 'vantk_example')

    # 循环变量
    match = re.search(r'\[循环\.(\d+)\.(\d+)\]', text)
    if match:
        time_val = match.group(1)
        times = match.group(2)
        text = re.sub(r"\[循环[^\]]*\]", "", text)
        return {"type": "cycle", "content": text, "time": time_val, "times": times}
    
    # 冷却变量
    cooling = re.search(r'\((\d+)~\)', text)
    if cooling and event:
        if env == "private":
            group_id = "private"
        if cooling.group(1) == "0":
            tomorrow = datetime.now() + timedelta(days=1)
            tomorrow_midnight = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
            colling_time = tomorrow_midnight.timestamp()
        else:
            colling_time = int(cooling.group(1)) + datetime.now().timestamp()
        
        file_content = await file_control(bot_id, f"cooling/{group_id}.txt", "r") or ""
        line_type = False
        if not file_content.strip():
            result = f"{user_id}={lexicon_id_for_cool}={colling_time}"
        else:
            lines = file_content.strip().split('\n')
            for i, line in enumerate(lines):
                parts = line.split('=')
                if len(parts) == 3 and int(parts[0]) == int(user_id) and int(parts[1]) == int(lexicon_id_for_cool):
                    lines[i] = f"{parts[0]}={parts[1]}={colling_time}"
                    line_type = True
            if not line_type:
                lines.append(f"{user_id}={lexicon_id_for_cool}={colling_time}")
            result = '\n'.join(lines)
        await file_control(bot_id, f"cooling/{group_id}.txt", "w", result)
        text = re.sub(r'\(\d+~\)', '', text)
    
    # 随机数变量
    match = re.search(r'\((\d+)-(\d+)\)', text)
    if match:
        matches = re.findall(r'\(\d+-\d+\)', text)
        for m in matches:
            nums = [int(x) for x in m[1:-1].split('-')]
            rand_num = str(random.randint(nums[0], nums[1]))
            text = text.replace(m, rand_num, 1)
    
    # 时间变量
    now = datetime.now()
    replace_dict = {
        r'\(Y\)': now.year,
        r'\(M\)': now.month,
        r'\(D\)': now.day,
        r'\(h\)': now.hour,
        r'\(m\)': now.minute,
        r'\(s\)': now.second
    }
    for key, value in replace_dict.items():
        text = re.sub(key, str(value), text)

    # 数学运算
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

    # 判断变量
    def judge(text):
        parts = re.split(r'(\{.*?\})', text)
        res = []
        skip = False
        def strip_quotes(x):
            return x.replace("'", "").replace('"', "")
        def check(e):
            s = e[1:-1]
            nm = re.match(r'^(.+)notin(\[.+\])$', s)
            if nm:
                v, ls = nm.groups()
                try:
                    v = strip_quotes(v)
                    result = v not in [strip_quotes(str(x)) for x in ast.literal_eval(ls)]
                    return (True, result)
                except:
                    return (False, False)
            im = re.match(r'^(.+)in(\[.+\])$', s)
            if im:
                v, ls = im.groups()
                try:
                    v = strip_quotes(v)
                    result = v in [strip_quotes(str(x)) for x in ast.literal_eval(ls)]
                    return (True, result)
                except:
                    return (False, False)
            om = re.search(r'(!=|[><=])', s)
            if om:
                op = om.group(1)
                a, b = s.split(op, 1)
                a = strip_quotes(a)
                b = strip_quotes(b)
                if op == '=':
                    return (True, a == b)
                elif op == '!=':
                    return (True, a != b)
                try:
                    fa, fb = float(a), float(b)
                    if op == '>':
                        return (True, fa > fb)
                    elif op == '<':
                        return (True, fa < fb)
                except:
                    return (False, False)
            return (False, False)
        for p in parts:
            if p.startswith('{') and p.endswith('}'):
                is_valid, cond_result = check(p)
                if is_valid:
                    if not skip:
                        skip = not cond_result
                else:
                    if not skip:
                        res.append(p)
            else:
                if p:
                    if not skip:
                        res.append(p)
                    skip = False
        return ''.join(res)
    text = judge(text)

    # 其他变量和多媒体消息
    parts = re.split(r'(\[.*?\])', text)
    parts = [part for part in parts if part.strip()]
    message = []
    
    for item in parts:
        if "[" in item and "." in item and "]" in item:
            item = item[1:-1]
            item = re.split(r'(?<!\.)\.(?!\.)', item)
            logger.debug(f"解析多媒体消息: {item}")
            
            if item[0] in ["text", "文本"]:
                text_content = item[1] if len(item) > 1 else ""
                message.append({"type": "text", "content": text_content})
            elif item[0] in ["at", "艾特"]:
                if len(item) >= 2 and item[1] != '':
                    message.append({"type": "at", "qq": item[1]})
                elif event:
                    message.append({"type": "at", "qq": event.user_id})
            elif item[0] in ["face", "表情"]:
                message.append({"type": "face", "id": item[1] if len(item) > 1 else ""})
            elif item[0] in ["image", "图片"]:
                text = '.'.join(item[1::])
                message.append({"type": "image", "file": text})
            elif item[0] in ["reply", "回复"]:
                if len(item) >= 2 and item[1] != '':
                    message.append({"type": "reply", "id": item[1]})
                elif event:
                    message.append({"type": "reply", "id": event.message_id})
            elif item[0] in ["video", "视频"]:
                text = '.'.join(item[1::])
                message.append({"type": "video", "file": text})
            elif item[0] in ["record", "语音"]:
                text = '.'.join(item[1::])
                message.append({"type": "record", "file": text})
            elif item[0] in ["poke", "戳一戳"]:
                if len(item) >= 2 and item[1] != '':
                    message.append({"type": "poke", "user_id": item[1]})
                elif event:
                    message.append({"type": "poke", "user_id": event.user_id})
            elif item[0] in ["json"]:
                json_text = '.'.join(item[1::])
                try:
                    json_data = json.loads(json_text)
                    message.append({"type": "json", "data": json_data})
                except:
                    message.append({"type": "text", "content": json_text})
            else:
                message.append({"type": "text", "content": f"[{item}]"})
        else:
            if item.strip():
                message.append({"type": "text", "content": item})
    
    if not message:
        return {"type": "text", "content": ""}
    elif len(message) == 1:
        return message[0]
    else:
        return {"type": "mixed", "messages": message}

# ==================== HTTP请求工具 ====================
async def get_data(url):
    """HTTP请求工具 - 完全匹配原版"""
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

# ==================== API相关定义 ====================
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证Token"""
    if credentials.credentials != API_TOKEN:
        logger.error(f"Token验证失败: {credentials.credentials}")
        raise HTTPException(status_code=401, detail="无效的Token")
    return credentials.credentials

# 创建FastAPI应用
api_app = FastAPI(
    title="VanBot关键词API",
    description="提供关键词查询和管理功能的API接口 - 完全匹配原版Van_keyword.py",
    version="1.0.0"
)

# ==================== WebUI HTML模板 ====================
# 保留原有的WEBUI_HTML模板内容，此处省略以节省空间
WEBUI_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VanBot 词库管理系统</title>
    <style>
        /* 原有的CSS样式保持不变 */
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
            <div class="subtitle">功能完整的词库Web管理界面 - 完全匹配原版功能</div>
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
                <i class="fas fa-info-circle"></i> 将包含变量的消息解码为实际内容，支持所有原版变量
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
                <textarea id="decode-text" placeholder="输入包含变量的文本...">现在是(Y)年(M)月(D)日 (h):(m):(s)，随机数(1-100)，数学运算(+2*3+5)</textarea>
                <div class="small monospace">
                    可用变量: [qq], [name], [card], [group], [ai], [收消息数], [发消息数], [选择的词库], [使用的词库]<br>
                    时间: (Y), (M), (D), (h), (m), (s) | 随机: (1-100) | 数学: (+1+2) | 冷却: (60~) | 判断: {a>b}
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
                <i class="fas fa-info-circle"></i> 支持原版所有词库操作：添加、删除、查询
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
                        <option value="look_name">查词(关键词)</option>
                        <option value="look_id">查词(ID范围)</option>
                        <option value="remove_id">删除(ID)</option>
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
                </select>
            </div>
            <div class="btn-group">
                <button class="btn" onclick="lexiconOperation()">
                    <i class="fas fa-play"></i> 执行操作
                </button>
                <button class="btn btn-secondary" onclick="countLexicon()">
                    <i class="fas fa-calculator"></i> 统计词数
                </button>
            </div>
            <div class="result-area" id="lexicon-result" style="display: none;">
                <div class="result-title">操作结果</div>
                <div class="result-content" id="lexicon-result-content"></div>
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
                <i class="fas fa-info-circle"></i> 各种实用工具
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
    </div>
    
    <div class="status-bar" id="status-bar"></div>
    
    <script>
        // 全局变量
        let apiUrl = '';
        let apiToken = '';
        let statusInterval = null;
        
        document.addEventListener('DOMContentLoaded', function() {
            initTabs();
            initPage();
            startStatusRefresh();
            updateExamples();
            
            document.getElementById('lexicon-optype').addEventListener('change', function() {
                updateLexiconForm();
            });
            
            document.getElementById('tool-admin-op').addEventListener('change', function() {
                updateAdminForm();
            });
            
            apiUrl = window.location.origin;
            apiToken = "{{api_token}}";
            updateApiInfo();
        });
        
        function initTabs() {
            const tabs = document.querySelectorAll('.tab');
            const sections = document.querySelectorAll('.content-section');
            
            tabs.forEach(tab => {
                tab.addEventListener('click', function() {
                    const tabId = this.getAttribute('data-tab');
                    
                    tabs.forEach(t => t.classList.remove('active'));
                    this.classList.add('active');
                    
                    sections.forEach(section => {
                        section.classList.remove('active');
                        if (section.id === tabId) {
                            section.classList.add('active');
                        }
                    });
                });
            });
        }
        
        function initPage() {
            const savedApiUrl = localStorage.getItem('vanbot_api_url');
            const savedApiToken = localStorage.getItem('vanbot_api_token');
            
            if (savedApiUrl && savedApiToken) {
                apiUrl = savedApiUrl;
                apiToken = savedApiToken;
                updateApiInfo();
            }
        }
        
        function updateApiInfo() {
            document.getElementById('api-url').textContent = apiUrl;
            document.getElementById('api-token').textContent = apiToken;
            localStorage.setItem('vanbot_api_url', apiUrl);
            localStorage.setItem('vanbot_api_token', apiToken);
        }
        
        function startStatusRefresh() {
            refreshStatus();
            statusInterval = setInterval(refreshStatus, 30000);
        }
        
        function refreshStatus() {
            if (!apiUrl) return;
            
            fetch(`${apiUrl}/status`)
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status-host').value = data.host || '未知';
                    document.getElementById('status-port').value = data.port || '未知';
                    document.getElementById('status-running').value = data.running ? '运行中' : '停止';
                    document.getElementById('status-datadir').value = data.data_dir || '未知';
                    
                    const features = data.features || [];
                    const featuresHtml = features.map(f => `<div>✓ ${f}</div>`).join('');
                    document.getElementById('status-features').innerHTML = featuresHtml;
                    
                    showStatus('状态已刷新', 'success');
                })
                .catch(err => {
                    console.error('获取状态失败:', err);
                    showStatus('无法获取服务器状态', 'error');
                });
        }
        
        function testConnection() {
            fetch(`${apiUrl}/`)
                .then(response => response.json())
                .then(data => {
                    showStatus('连接测试成功', 'success');
                })
                .catch(err => {
                    showStatus('连接测试失败', 'error');
                });
        }
        
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
                });
        }
        
        function testQuery() {
            document.getElementById('query-botid').value = '123456';
            document.getElementById('query-userid').value = '789012';
            document.getElementById('query-groupid').value = '987654';
            document.getElementById('query-msg').value = '你好';
            document.getElementById('query-mode').value = '1';
            queryKeyword();
        }
        
        function decodeMessage() {
            const botid = document.getElementById('decode-botid').value;
            const userid = document.getElementById('decode-userid').value;
            const groupid = document.getElementById('decode-groupid').value;
            const text = document.getElementById('decode-text').value;
            
            if (!botid || !userid || !text) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
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
            
            callApi(payload, 'decode-result', 'decode-result-content')
                .then(() => {
                    showStatus('解码成功', 'success');
                })
                .catch(() => {
                    showStatus('解码失败', 'error');
                });
        }
        
        function decodeTest() {
            document.getElementById('decode-botid').value = '123456';
            document.getElementById('decode-userid').value = '789012';
            document.getElementById('decode-groupid').value = '987654';
            document.getElementById('decode-text').value = '现在是(Y)年(M)月(D)日 (h):(m):(s)，随机数(1-100)，数学运算(+2*3+5)';
            decodeMessage();
        }
        
        function lexiconOperation() {
            const botid = document.getElementById('lexicon-botid').value;
            const userid = document.getElementById('lexicon-userid').value;
            const optype = document.getElementById('lexicon-optype').value;
            const keyword = document.getElementById('lexicon-keyword').value;
            const reply = document.getElementById('lexicon-reply').value;
            const mode = document.getElementById('lexicon-mode').value;
            
            if (!botid || !userid) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
            if ((optype === 'add' || optype === 'add') && !keyword) {
                showStatus('请填写关键词', 'error');
                return;
            }
            
            if (optype === 'add' && !reply) {
                showStatus('请填写回复内容', 'error');
                return;
            }
            
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
            } else if (optype === 'remove' || optype === 'remove_id' || optype === 'look_name') {
                payload.keyword = keyword;
            } else if (optype === 'look_id') {
                payload.keyword = keyword || '1-10';
            }
            
            callApi(payload, 'lexicon-result', 'lexicon-result-content')
                .then(data => {
                    if (data.success) {
                        showStatus('操作成功', 'success');
                        if (optype === 'add') {
                            document.getElementById('lexicon-keyword').value = '';
                            document.getElementById('lexicon-reply').value = '';
                        }
                    } else {
                        showStatus('操作失败: ' + (data.message || '未知错误'), 'error');
                    }
                })
                .catch(() => {
                    showStatus('操作失败', 'error');
                });
        }
        
        function countLexicon() {
            const botid = document.getElementById('lexicon-botid').value;
            const userid = document.getElementById('lexicon-userid').value;
            
            if (!botid || !userid) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
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
                });
        }
        
        function searchLexicon() {
            const botid = document.getElementById('search-botid').value;
            const userid = document.getElementById('search-userid').value;
            const keyword = document.getElementById('search-keyword').value;
            
            if (!botid || !userid || !keyword) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
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
                                const modeText = item.mode === 1 ? '精确' : '模糊';
                                const modeClass = item.mode === 1 ? 'mode-exact' : 'mode-fuzzy';
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
                });
        }
        
        function getConfig() {
            const botid = document.getElementById('config-botid').value;
            const userid = document.getElementById('config-userid').value;
            
            if (!botid || !userid) {
                showStatus('请填写必要参数', 'error');
                return;
            }
            
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
                });
        }
        
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
            
            callApi(payload, 'tool-transcode-result', 'tool-transcode-result-content')
                .then(() => {
                    showStatus('转码成功', 'success');
                })
                .catch(() => {
                    showStatus('转码失败', 'error');
                });
        }
        
        function toolAdmin() {
            const op = document.getElementById('tool-admin-op').value;
            const user = document.getElementById('tool-admin-user').value;
            
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
            
            callApi(payload, 'tool-admin-result', 'tool-admin-result-content')
                .then(data => {
                    showStatus(data.message || '操作成功', 'success');
                })
                .catch(err => {
                    showStatus('操作失败', 'error');
                });
        }
        
        function updateLexiconForm() {
            const optype = document.getElementById('lexicon-optype').value;
            const replyGroup = document.getElementById('lexicon-reply-group');
            const modeGroup = document.getElementById('lexicon-mode-group');
            
            if (optype === 'add') {
                replyGroup.style.display = 'block';
                modeGroup.style.display = 'block';
            } else {
                replyGroup.style.display = 'none';
                modeGroup.style.display = 'none';
            }
        }
        
        function updateAdminForm() {
            const op = document.getElementById('tool-admin-op').value;
            const userGroup = document.getElementById('tool-admin-user-group');
            
            if (op === 'add' || op === 'remove') {
                userGroup.style.display = 'block';
            } else {
                userGroup.style.display = 'none';
            }
        }
        
        function toggleCollapse(id) {
            const content = document.getElementById(id);
            const icon = content.previousElementSibling.querySelector('.fa-chevron-down');
            
            if (content.style.display === 'block') {
                content.style.display = 'none';
                if (icon) icon.className = 'fas fa-chevron-down';
            } else {
                content.style.display = 'block';
                if (icon) icon.className = 'fas fa-chevron-up';
            }
        }
        
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
            
            if (resultAreaId && resultContentId) {
                const resultArea = document.getElementById(resultAreaId);
                const resultContent = document.getElementById(resultContentId);
                resultContent.textContent = JSON.stringify(data, null, 2);
                resultArea.style.display = 'block';
            }
            
            return data;
        }
        
        function showStatus(message, type) {
            const statusBar = document.getElementById('status-bar');
            statusBar.textContent = message;
            statusBar.className = 'status-bar ' + type;
            statusBar.style.display = 'block';
            
            setTimeout(() => {
                statusBar.style.display = 'none';
            }, 3000);
        }
        
        function updateExamples() {
            // 示例更新逻辑保持不变
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
        "version": "3.3.9",
        "webui": f"http://{API_HOST}:{API_PORT}/webui",
        "docs": f"http://{API_HOST}:{API_PORT}/docs",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "features": [
            "完全匹配原版 Van_keyword.py 功能",
            "支持所有变量类型：[n.1], [n.1.t], [qq], [name], [card], [group]",
            "支持教词语法：#精准加词|关键词|回复#",
            "支持词库管理：添加、删除、查询、ID查询",
            "支持冷却系统、随机数、时间变量、数学运算",
            "支持条件判断：{a in [list]}, {a>b}"
        ]
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
            "关键词查询 (支持精确/模糊匹配)",
            "词条管理 (添加/删除/查询)",
            "变量替换系统 [n.1], [n.1.t]",
            "多媒体消息处理 [image], [face], [at], [reply]",
            "冷却时间系统 (60~)",
            "时间变量 (Y), (M), (D), (h), (m), (s)",
            "数学运算 (+1+2)",
            "随机数生成 (1-100)",
            "条件判断 {a>b}, {a in [list]}",
            "教词语法 #精准加词|关键词|回复#",
            "词库统计功能"
        ]
    }

@api_app.get("/webui")
async def webui():
    """WebUI主界面"""
    html_content = WEBUI_HTML.replace("{{api_token}}", API_TOKEN)
    return HTMLResponse(content=html_content)

# 主要API端点
@api_app.post("/api/v1/keyword")
async def keyword_api(
    request_data: Dict[str, Any] = Body(...),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """关键词API主接口 - 完全匹配原版功能"""
    
    # 验证Header中的Token
    if credentials.credentials != API_TOKEN:
        logger.error(f"Header Token验证失败: {credentials.credentials}")
        raise HTTPException(status_code=401, detail="无效的Token")
    
    # 验证请求体中的Token
    if request_data.get("token") != API_TOKEN:
        logger.error(f"Body Token验证失败: {request_data.get('token')}")
        raise HTTPException(status_code=401, detail="Token验证失败")
    
    action = request_data.get("action", "")
    logger.info(f"收到API请求: action={action}, botid={request_data.get('botid')}")
    
    try:
        if action == "query":
            return await handle_query(request_data)
        elif action == "decode":
            return await handle_decode(request_data)
        elif action == "add":
            return await handle_add(request_data)
        elif action == "remove":
            return await handle_remove(request_data)
        elif action == "remove_name":
            return await handle_remove_name(request_data)
        elif action == "remove_id":
            return await handle_remove_id(request_data)
        elif action == "look_name":
            return await handle_look_name(request_data)
        elif action == "look_id":
            return await handle_look_id(request_data)
        elif action == "get_config":
            return await handle_get_config(request_data)
        elif action == "search":
            return await handle_search(request_data)
        elif action == "count":
            return await handle_count(request_data)
        elif action == "transcode":
            return await handle_transcode(request_data)
        elif action == "admin_manage":
            return await handle_admin_manage(request_data)
        elif action == "test":
            return {"success": True, "message": "API服务器运行正常", "timestamp": time.time()}
        else:
            logger.error(f"不支持的操作: {action}")
            raise HTTPException(status_code=400, detail=f"不支持的操作: {action}")
    except Exception as e:
        logger.error(f"处理请求时出错: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 处理函数 ====================
async def handle_query(request_data: Dict[str, Any]):
    """处理查询请求 - 完全匹配原版"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    groupid = request_data.get("groupid")
    msg = request_data.get("msg", "")
    
    logger.info(f"查询请求: botid={botid}, userid={userid}, msg='{msg}'")
    
    if not botid or not userid:
        raise HTTPException(status_code=400, detail="缺少botid或userid参数")
    
    # 构建data_id数组
    data_id = ["common"]
    env = "group" if groupid else "private"
    env_id = groupid if groupid else userid
    data_id.append(env_id)
    
    lexicon_name = await get_user_file(str(botid), env, env_id)
    data_id.append(lexicon_name)
    
    # 转换消息
    message = await _transcoding(msg)
    logger.debug(f"转换后的消息: '{message}'")
    
    # 查询关键词
    otext = await lexicon_operation(str(botid), data_id, "get", value=message)
    
    if not otext:
        logger.info(f"未找到匹配的词条: '{message}'")
        return {
            "success": True,
            "action": "query",
            "found": False,
            "reply": "",
            "timestamp": time.time()
        }
    
    logger.info(f"查询成功: '{message}' -> '{otext}'")
    return {
        "success": True,
        "action": "query",
        "found": True,
        "reply": otext if isinstance(otext, str) else otext[0],
        "raw": otext,
        "timestamp": time.time()
    }

async def handle_decode(request_data: Dict[str, Any]):
    """处理解码请求 - 完全匹配原版"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    groupid = request_data.get("groupid")
    text = request_data.get("text", "")
    
    logger.info(f"解码请求: botid={botid}, text='{text[:50]}...'")
    
    if not botid or not userid:
        raise HTTPException(status_code=400, detail="缺少botid或userid参数")
    
    # 构建事件对象
    class SimpleEvent:
        def __init__(self, user_id, group_id, self_id):
            self.user_id = user_id
            self.group_id = group_id
            self.self_id = self_id
            self.message_id = 123456
            self.sender = type('Sender', (), {
                'nickname': '测试用户',
                'card': '测试昵称'
            })
    
    event = SimpleEvent(userid, groupid, botid)
    env = "group" if groupid else "private"
    env_id = groupid if groupid else userid
    
    # 解码处理
    result = await _decoding(text, str(botid), env, env_id, event, cool_config=False)
    
    logger.info(f"解码完成: {result}")
    return {
        "success": True,
        "action": "decode",
        "result": result,
        "timestamp": time.time()
    }

async def handle_add(request_data: Dict[str, Any]):
    """处理添加词条请求 - 完全匹配原版"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword")
    reply = request_data.get("reply")
    mode = int(request_data.get("mode", 1))
    
    if not all([botid, userid, keyword, reply]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"添加词条: botid={botid}, keyword='{keyword}', mode={mode}")
    
    # 获取词库名
    select_lexicon = await get_select_file(str(botid), userid)
    
    # 添加词条
    result = await lexicon_operation(
        str(botid),
        select_lexicon,
        "add",
        n=keyword,
        r=reply,
        s=mode
    )
    
    if result == "词条已存在":
        return {
            "success": False,
            "action": "add",
            "message": "词条已存在",
            "timestamp": time.time()
        }
    elif result == "添加成功":
        return {
            "success": True,
            "action": "add",
            "message": "添加成功",
            "keyword": keyword,
            "mode": mode,
            "timestamp": time.time()
        }
    else:
        raise HTTPException(status_code=500, detail=result)

async def handle_remove_name(request_data: Dict[str, Any]):
    """处理删除词条请求 (按名称)"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword")
    
    if not all([botid, userid, keyword]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"删除词条: botid={botid}, keyword='{keyword}'")
    
    select_lexicon = await get_select_file(str(botid), userid)
    
    result = await lexicon_operation(
        str(botid),
        select_lexicon,
        "remove_name",
        remove_name=keyword
    )
    
    return {
        "success": True,
        "action": "remove_name",
        "message": result,
        "keyword": keyword,
        "timestamp": time.time()
    }

async def handle_remove_id(request_data: Dict[str, Any]):
    """处理删除词条请求 (按ID)"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword")  # 这里keyword是ID
    
    if not all([botid, userid, keyword]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"删除词条ID: botid={botid}, id='{keyword}'")
    
    select_lexicon = await get_select_file(str(botid), userid)
    
    result = await lexicon_operation(
        str(botid),
        select_lexicon,
        "remove_id",
        remove_id=keyword
    )
    
    return {
        "success": True,
        "action": "remove_id",
        "message": result,
        "id": keyword,
        "timestamp": time.time()
    }

async def handle_look_name(request_data: Dict[str, Any]):
    """处理查询词条请求 (按关键词)"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword")
    
    if not all([botid, userid, keyword]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"查询词条: botid={botid}, keyword='{keyword}'")
    
    select_lexicon = await get_select_file(str(botid), userid)
    
    result = await lexicon_operation(
        str(botid),
        select_lexicon,
        "look_name",
        look_name=keyword
    )
    
    return {
        "success": True,
        "action": "look_name",
        "result": result,
        "keyword": keyword,
        "timestamp": time.time()
    }

async def handle_look_id(request_data: Dict[str, Any]):
    """处理查询词条请求 (按ID范围)"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword", "1-10")  # 默认查询1-10
    
    if not all([botid, userid]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"查询词条ID范围: botid={botid}, range='{keyword}'")
    
    select_lexicon = await get_select_file(str(botid), userid)
    
    result = await lexicon_operation(
        str(botid),
        select_lexicon,
        "look_id",
        look_id=keyword
    )
    
    return {
        "success": True,
        "action": "look_id",
        "result": result,
        "range": keyword,
        "timestamp": time.time()
    }

async def handle_search(request_data: Dict[str, Any]):
    """搜索词条"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    keyword = request_data.get("keyword")
    
    if not all([botid, userid, keyword]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"搜索词条: botid={botid}, keyword='{keyword}'")
    
    select_lexicon = await get_select_file(str(botid), userid)
    
    # 获取词库数据
    data = await file_control(str(botid), f"lexicon/{select_lexicon}.json", "r")
    try:
        data = json.loads(data)
    except:
        data = {"work": []}
    
    results = []
    for idx, item in enumerate(data["work"], 1):
        for key in item.keys():
            if keyword in key:
                results.append({
                    "id": idx,
                    "keyword": key,
                    "reply_count": len(item[key].get("r", [])),
                    "mode": item[key].get("s", 0)
                })
    
    return {
        "success": True,
        "action": "search",
        "keyword": keyword,
        "results": results,
        "count": len(results),
        "timestamp": time.time()
    }

async def handle_count(request_data: Dict[str, Any]):
    """统计词条数量"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    
    if not all([botid, userid]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"统计词数: botid={botid}, userid={userid}")
    
    select_lexicon = await get_select_file(str(botid), userid)
    
    # 获取词库数据
    data = await file_control(str(botid), f"lexicon/{select_lexicon}.json", "r")
    try:
        data = json.loads(data)
    except:
        data = {"work": []}
    
    total_keywords = len(data["work"])
    total_replies = 0
    for item in data["work"]:
        for value in item.values():
            total_replies += len(value.get("r", []))
    
    return {
        "success": True,
        "action": "count",
        "keyword_count": total_keywords,
        "reply_count": total_replies,
        "timestamp": time.time()
    }

async def handle_transcode(request_data: Dict[str, Any]):
    """处理转码请求"""
    text = request_data.get("text", "")
    
    logger.info(f"转码请求: text='{text[:50]}...'")
    
    result = await _transcoding(text)
    
    return {
        "success": True,
        "action": "transcode",
        "original": text,
        "transcoded": result,
        "timestamp": time.time()
    }

async def handle_get_config(request_data: Dict[str, Any]):
    """获取配置信息"""
    botid = int(request_data.get("botid", 0))
    userid = int(request_data.get("userid", 0))
    
    if not all([botid, userid]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    logger.info(f"获取配置: botid={botid}, userid={userid}")
    
    select_lexicon = await get_select_file(str(botid), userid)
    
    return {
        "success": True,
        "action": "get_config",
        "config": {
            "select_lexicon": select_lexicon,
            "user_file": await get_user_file(str(botid), "private", userid)
        },
        "timestamp": time.time()
    }

async def handle_admin_manage(request_data: Dict[str, Any]):
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
        logger.info(f"📂 数据目录: {get_data_dir()}")
        logger.info(f"📝 日志文件: {os.path.join(directory, 'api_log.txt')}")
        logger.info(f"{'='*50}")
        
        print(f"  ✅ 关键词查询 (精确/模糊匹配)")
        print(f"  ✅ 词库管理 (添加/删除/查询)")
        print(f"  ✅ 变量替换系统 [n.1], [n.1.t]")
        print(f"  ✅ 时间变量 (Y), (M), (D), (h), (m), (s)")
        print(f"  ✅ 数学运算 (+1+2), (+2*3/4)")
        print(f"  ✅ 随机数 (1-100)")
        print(f"  ✅ 冷却时间 (60~)")
        print(f"  ✅ 条件判断")
        print(f"  ✅ 多媒体消息 [image.url], [face.id], [at.qq], [reply.id]")
        print(f"  ✅ 教词语法 #精准加词|关键词|回复#")
        print(f"  ✅ 词库统计功能")
        
        print(f"\n🌐 打开浏览器访问: http://{API_HOST}:{API_PORT}/webui")
        print(f"📝 使用 Token: {API_TOKEN}")
        
        asyncio.run(server.serve())
    except Exception as e:
        logger.error(f"API服务器启动失败: {e}")
        import traceback
        traceback.print_exc()

# ==================== 主程序 ====================
if __name__ == "__main__":
    print(f"📂 工作目录: {directory}")
    
    # 确保数据目录存在
    data_dir = get_data_dir()
    print(f"📁 数据目录: {data_dir}")
    
    # 启动API服务器
    start_api_server()