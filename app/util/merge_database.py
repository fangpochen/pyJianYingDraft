import os
import sqlite3
import logging
import json
import hashlib
from typing import List, Dict, Optional, Tuple, Set

logger = logging.getLogger(__name__)

class MergeDatabase:
    """管理视频融合记录的数据库"""
    
    def __init__(self, db_path="merge_history.db"):
        """
        初始化数据库
        
        Args:
            db_path (str): 数据库文件路径，默认在当前目录
        """
        self.db_path = db_path
        self.conn = None
        self.init_database()
    
    def init_database(self):
        """初始化数据库连接和表结构"""
        try:
            # 确保数据库目录存在
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir)
            
            # 创建数据库连接
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            
            # 创建合并任务表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS merge_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_hash TEXT UNIQUE,
                output_file TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # 创建源文件表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS merge_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                file_path TEXT,
                file_name TEXT,
                base_name TEXT,
                FOREIGN KEY (task_id) REFERENCES merge_tasks(id)
            )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_hash ON merge_tasks(task_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_base_name ON merge_sources(base_name)')
            
            self.conn.commit()
            logger.info(f"成功初始化融合记录数据库: {self.db_path}")
            
        except Exception as e:
            logger.error(f"初始化数据库失败: {e}")
            if self.conn:
                self.conn.close()
                self.conn = None
            raise
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        """支持 with 语句"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时关闭数据库连接"""
        self.close()
    
    def generate_task_hash(self, file_paths: List[str]) -> str:
        """
        生成任务哈希值，用于唯一标识一组源文件
        
        Args:
            file_paths: 源文件路径列表
            
        Returns:
            str: 任务哈希值
        """
        # 提取文件名并排序，确保相同文件组合有相同的哈希值
        file_names = sorted([os.path.basename(path) for path in file_paths])
        # 使用JSON序列化以保持一致性，然后计算MD5
        json_str = json.dumps(file_names, sort_keys=True)
        return hashlib.md5(json_str.encode('utf-8')).hexdigest()
    
    def add_merge_task(self, file_paths: List[str], output_file: str) -> bool:
        """
        添加一个新的合并任务记录
        
        Args:
            file_paths: 源文件路径列表
            output_file: 输出文件路径
            
        Returns:
            bool: 是否成功添加
        """
        if not self.conn:
            logger.error("数据库未初始化")
            return False
        
        try:
            task_hash = self.generate_task_hash(file_paths)
            cursor = self.conn.cursor()
            
            # 插入任务记录
            cursor.execute(
                'INSERT INTO merge_tasks (task_hash, output_file) VALUES (?, ?)',
                (task_hash, output_file)
            )
            task_id = cursor.lastrowid
            
            # 插入每个源文件记录
            for file_path in file_paths:
                file_name = os.path.basename(file_path)
                # 提取基本名称（不包含扩展名），用于后续搜索
                base_name = os.path.splitext(file_name)[0]
                cursor.execute(
                    'INSERT INTO merge_sources (task_id, file_path, file_name, base_name) VALUES (?, ?, ?, ?)',
                    (task_id, file_path, file_name, base_name)
                )
            
            self.conn.commit()
            logger.info(f"成功记录合并任务 {task_hash}，包含 {len(file_paths)} 个源文件")
            return True
            
        except sqlite3.IntegrityError as e:
            # 如果任务哈希已存在（完全相同的文件组合）
            logger.warning(f"合并任务已存在于数据库中: {e}")
            self.conn.rollback()
            return False
        except Exception as e:
            logger.error(f"添加合并任务记录失败: {e}")
            self.conn.rollback()
            return False
    
    def is_exact_combination_used(self, file_paths: List[str]) -> bool:
        """
        检查是否已使用过完全相同的文件组合
        
        Args:
            file_paths: 源文件路径列表
            
        Returns:
            bool: 是否已使用过此组合
        """
        if not self.conn:
            logger.error("数据库未初始化")
            return False
        
        try:
            task_hash = self.generate_task_hash(file_paths)
            cursor = self.conn.cursor()
            
            cursor.execute('SELECT id FROM merge_tasks WHERE task_hash = ?', (task_hash,))
            result = cursor.fetchone()
            
            return result is not None
            
        except Exception as e:
            logger.error(f"检查合并任务是否存在时出错: {e}")
            return False
    
    def find_unused_combinations(self, available_files: List[str], required_count: int) -> List[List[str]]:
        """
        从可用文件中找出未使用过的组合
        
        Args:
            available_files: 可用的文件路径列表
            required_count: 每个组合需要的文件数量
            
        Returns:
            List[List[str]]: 未使用过的文件组合列表
        """
        if not self.conn or len(available_files) < required_count:
            return []
        
        # 提取所有已使用的文件组合
        used_combinations = self.get_all_used_combinations()
        
        # 生成候选组合
        from itertools import combinations
        candidate_combinations = list(combinations(available_files, required_count))
        
        # 过滤出未使用过的组合
        unused_combinations = []
        for combo in candidate_combinations:
            combo_list = list(combo)
            combo_hash = self.generate_task_hash(combo_list)
            if combo_hash not in used_combinations:
                unused_combinations.append(combo_list)
        
        return unused_combinations
    
    def get_all_used_combinations(self) -> Set[str]:
        """
        获取所有已使用过的组合哈希
        
        Returns:
            Set[str]: 已使用组合的哈希集合
        """
        if not self.conn:
            return set()
        
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT task_hash FROM merge_tasks')
            return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"获取已使用组合时出错: {e}")
            return set()
    
    def suggest_new_files(self, base_files: List[str], all_available_files: List[str], required_count: int) -> List[str]:
        """
        基于已有文件，推荐需要补充的文件，以避免使用已有组合
        
        Args:
            base_files: 已确定要使用的文件列表
            all_available_files: 所有可用的文件列表
            required_count: 组合中需要的文件总数
            
        Returns:
            List[str]: 推荐添加的文件列表
        """
        if not self.conn:
            return []
        
        # 如果已有文件数量达到要求，检查是否为已使用的组合
        if len(base_files) >= required_count:
            if self.is_exact_combination_used(base_files[:required_count]):
                logger.warning("所选文件组合已经被使用过")
                return []
            return base_files[:required_count]
        
        # 计算还需要的文件数量
        needed_count = required_count - len(base_files)
        
        # 过滤掉已选择的文件
        base_file_names = {os.path.basename(f) for f in base_files}
        available_files = [f for f in all_available_files if os.path.basename(f) not in base_file_names]
        
        if len(available_files) < needed_count:
            logger.warning("可用文件数量不足")
            return []
        
        # 获取所有已使用的组合
        used_combinations = self.get_all_used_combinations()
        
        # 逐一尝试不同组合
        from itertools import combinations
        for combo in combinations(available_files, needed_count):
            test_combination = base_files + list(combo)
            combo_hash = self.generate_task_hash(test_combination)
            if combo_hash not in used_combinations:
                return test_combination
        
        logger.warning("未找到未使用过的文件组合")
        return []
    
    def get_file_usage_stats(self) -> Dict[str, int]:
        """
        获取每个文件的使用频率统计
        
        Returns:
            Dict[str, int]: 文件名到使用次数的映射
        """
        if not self.conn:
            return {}
        
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT file_name, COUNT(*) FROM merge_sources GROUP BY file_name')
            return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"获取文件使用统计时出错: {e}")
            return {}
    
    def get_least_used_files(self, available_files: List[str], limit: int = 10) -> List[str]:
        """
        获取使用频率最低的文件
        
        Args:
            available_files: 可用的文件路径列表
            limit: 返回结果的最大数量
            
        Returns:
            List[str]: 使用频率最低的文件路径列表
        """
        if not self.conn:
            return []
        
        # 获取使用统计
        usage_stats = self.get_file_usage_stats()
        
        # 提取文件名
        available_file_names = [os.path.basename(f) for f in available_files]
        
        # 对文件名按使用频率排序（未使用过的优先）
        sorted_files = sorted(
            zip(available_files, available_file_names),
            key=lambda x: usage_stats.get(x[1], 0)
        )
        
        # 返回使用频率最低的文件
        return [f[0] for f in sorted_files[:limit]]
    
    def get_used_files_in_current_batch(self, hours_threshold: int = 1) -> List[str]:
        """
        获取当前批次中已使用的视频文件名列表
        
        Args:
            hours_threshold: 时间阈值，获取最近多少小时内的记录，默认为1小时
            
        Returns:
            List[str]: 最近使用的文件名列表
        """
        if not self.conn:
            logger.error("数据库未初始化")
            return []
        
        try:
            cursor = self.conn.cursor()
            
            # 查询最近hours_threshold小时内添加的任务
            cursor.execute(
                '''
                SELECT ms.file_name 
                FROM merge_sources ms
                JOIN merge_tasks mt ON ms.task_id = mt.id
                WHERE mt.timestamp >= datetime('now', ?) 
                GROUP BY ms.file_name
                ''', 
                (f'-{hours_threshold} hours',)
            )
            
            # 返回文件名列表
            results = cursor.fetchall()
            file_names = [row[0] for row in results]
            
            logger.info(f"找到最近{hours_threshold}小时内使用的{len(file_names)}个文件")
            return file_names
            
        except Exception as e:
            logger.error(f"获取最近使用的文件时出错: {e}")
            return []
    
    def get_used_files(self) -> Set[str]:
        """
        获取所有已经使用过的文件名称集合
        
        Returns:
            Set[str]: 已使用过的文件名称集合
        """
        if not self.conn:
            logger.error("数据库未初始化")
            return set()
        
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT file_name FROM merge_sources')
            used_files = {row[0] for row in cursor.fetchall()}
            logger.info(f"从数据库获取到 {len(used_files)} 个已使用过的文件")
            return used_files
        except Exception as e:
            logger.error(f"获取已使用文件时出错: {e}")
            return set() 