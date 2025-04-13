import configparser
import os
import logging

logger = logging.getLogger(__name__)

# --- 配置和默认值 ---
CONFIG_FILE = 'batch_tool_config.ini' # 相对于项目根目录

DEFAULT_VALUES = {
    'Paths': {
        'InputFolder': '',
        'OutputFolder': '',
        'DraftFolder': 'D:\\DJianYingDrafts\\JianyingPro Drafts' # 您原来的默认值
    },
    'Settings': {
        'DraftName': '简单测试_4940', # 您原来的默认值
        'DeleteSource': 'True' # 注意：ConfigParser 通常读写字符串
    }
}

def load_config():
    """加载配置文件，如果文件或键不存在则使用默认值。"""
    config = configparser.ConfigParser()
    config_data = {}

    try:
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE, encoding='utf-8')
            logger.info(f"成功加载配置文件: {CONFIG_FILE}")
        else:
            logger.info(f"配置文件 {CONFIG_FILE} 不存在，将使用默认值。")

        # 从配置或默认值加载数据
        for section, defaults in DEFAULT_VALUES.items():
            config_data[section] = {}
            if section not in config:
                config.add_section(section) # 确保 section 存在以便保存
                logger.debug(f"配置文件中缺少 Section '{section}', 将使用默认值。")

            for key, default_value in defaults.items():
                # 使用 get 方法并提供 fallback
                value = config.get(section, key, fallback=default_value)
                config_data[section][key] = value
                logger.debug(f"加载配置: [{section}] {key} = {value}")

    except configparser.Error as e:
        logger.exception(f"加载配置 {CONFIG_FILE} 时发生错误，将完全使用默认值: {e}")
        # 如果解析出错，则完全重置为默认值
        config_data = DEFAULT_VALUES.copy()
    except Exception as e:
        logger.exception(f"加载配置时发生未知错误，将完全使用默认值: {e}")
        config_data = DEFAULT_VALUES.copy()

    # 特别处理布尔值
    try:
         config_data['Settings']['DeleteSource'] = config.getboolean(
             'Settings', 
             'DeleteSource', 
             fallback=DEFAULT_VALUES['Settings']['DeleteSource'].lower() == 'true'
         )
    except ValueError:
         logger.warning(f"无法将 [Settings] DeleteSource 的值解析为布尔值，使用默认值 True")
         config_data['Settings']['DeleteSource'] = True

    return config_data

def save_config(config_data):
    """将提供的配置数据保存到配置文件。"""
    config = configparser.ConfigParser()

    try:
        for section, values in config_data.items():
            if section not in config:
                config.add_section(section)
            for key, value in values.items():
                # ConfigParser 需要字符串值
                config.set(section, key, str(value))

        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        logger.info(f"配置已保存到: {CONFIG_FILE}")
        return True
    except Exception as e:
        logger.exception(f"保存配置到 {CONFIG_FILE} 时出错")
        return False

# --- Example Usage (可以取消注释进行测试) ---
# if __name__ == '__main__':
#     # 配置日志以便查看输出
#     logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
#
#     print("--- 加载配置 ---")
#     loaded_settings = load_config()
#     print("加载的设置:", loaded_settings)
#
#     print("\n--- 修改配置 ---")
#     loaded_settings['Paths']['InputFolder'] = 'C:/new_input'
#     loaded_settings['Settings']['DraftName'] = '测试模板'
#     loaded_settings['Settings']['DeleteSource'] = False
#     print("修改后的设置:", loaded_settings)
#
#     print("\n--- 保存配置 ---")
#     save_success = save_config(loaded_settings)
#     print(f"保存是否成功: {save_success}")
#
#     print("\n--- 重新加载配置检查 ---")
#     reloaded_settings = load_config()
#     print("重新加载的设置:", reloaded_settings)
#
#     # 检查布尔值是否正确
#     print(f"DeleteSource 类型: {type(reloaded_settings['Settings']['DeleteSource'])}, 值: {reloaded_settings['Settings']['DeleteSource']}") 