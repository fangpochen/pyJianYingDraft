from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLineEdit, QPushButton, QLabel, QTextEdit, QMessageBox, QDialog, QHBoxLayout, QFileDialog
from PyQt5.QtCore import QThread, pyqtSignal
from DrissionPage import ChromiumPage
from concurrent.futures import ThreadPoolExecutor
import sys
import os
import requests
import re
from time import sleep
from key_verification import KeyVerificationDialog

headers = {
    'cookie': 'douyin.com; __ac_referer=https://www.douyin.com/user/MS4wLjABAAAAigqzHQAcgU_2m304EziVH-7NARJKGtPcl-MGlifra3Y?previous_page=app_code_link; bd_ticket_guard_client_web_domain=2; passport_csrf_token=699d7006536bef10f878b56b846f4c12; passport_csrf_token_default=699d7006536bef10f878b56b846f4c12; d_ticket=e4b76aadcd8468f75c7e8ad4908cdc8685279; passport_assist_user=Cjxsc2EjpbrMVrEMXTrg-XgavCXG-Gqa5ms-TOwknHe03jeOqvIREfKUa2_zYoANGTMvNxPSc_jpU83wTVUaSgo8cdUq2n4WCYpKVWHsjV-fRiDx2dXSMqnZO4DBH-U4QcPEJGdFEs-qqwdjfvhzAmNhGN5OEnkg6-9IteOKEILc3w0Yia_WVCABIgED6vRgxA%3D%3D; n_mh=8k9yh14QzDGpU6JLMgA0aldgFCrMmgt3IbqPzsNrwwY; sso_uid_tt=c6f314d7de177dc9643ccdd793d207a1; sso_uid_tt_ss=c6f314d7de177dc9643ccdd793d207a1; toutiao_sso_user=e3365eeadde3f3ffcc82931033fff44d; toutiao_sso_user_ss=e3365eeadde3f3ffcc82931033fff44d; sid_ucp_sso_v1=1.0.0-KGFhYjU2YjRhNGE3MDA1N2VkYjAzZTZmMDViN2I3MTFmMjQwMjcxZjAKHgi6_rGaOBDHuO-4BhjaFiAOMJrSqLkFOAZA9AdIBhoCbGYiIGUzMzY1ZWVhZGRlM2YzZmZjYzgyOTMxMDMzZmZmNDRk; ssid_ucp_sso_v1=1.0.0-KGFhYjU2YjRhNGE3MDA1N2VkYjAzZTZmMDViN2I3MTFmMjQwMjcxZjAKHgi6_rGaOBDHuO-4BhjaFiAOMJrSqLkFOAZA9AdIBhoCbGYiIGUzMzY1ZWVhZGRlM2YzZmZjYzgyOTMxMDMzZmZmNDRk; uid_tt=832fc23997102dc48cf2d3361d18d421; uid_tt_ss=832fc23997102dc48cf2d3361d18d421; sid_tt=e4d9139940a6f1bbf7557402fa93f728; sessionid=e4d9139940a6f1bbf7557402fa93f728; sessionid_ss=e4d9139940a6f1bbf7557402fa93f728; is_staff_user=false; _bd_ticket_crypt_doamin=2; _bd_ticket_crypt_cookie=e5e09823a7674d2216e080504453c48f; __security_server_data_status=1; sid_guard=e4d9139940a6f1bbf7557402fa93f728%7C1729879116%7C5183998%7CTue%2C+24-Dec-2024+17%3A58%3A34+GMT; sid_ucp_v1=1.0.0-KGI4ODZjNDIxODhhY2MzNGI0MDUwNjg3MDE4NWZhYzhkMzQ0YWFiMTkKGAi6_rGaOBDMuO-4BhjaFiAOOAZA9AdIBBoCbGYiIGU0ZDkxMzk5NDBhNmYxYmJmNzU1NzQwMmZhOTNmNzI4; ssid_ucp_v1=1.0.0-KGI4ODZjNDIxODhhY2MzNGI0MDUwNjg3MDE4NWZhYzhkMzQ0YWFiMTkKGAi6_rGaOBDMuO-4BhjaFiAOOAZA9AdIBBoCbGYiIGU0ZDkxMzk5NDBhNmYxYmJmNzU1NzQwMmZhOTNmNzI4; ttwid=1%7Cp7ag0ioVIIRjdBiR1oXB5AMSITPf0J4ZsA_S-L8m9vQ%7C1730046797%7Cbcfb3cd3713a8124b1dc5c0fd7b5e53eab635dba12011a475da4ef371b85aba5; UIFID_TEMP=60b2ef133e5e740633c50bb923c1ddfcacd13dfeee1bbba287269d01840b457b34219358fdf92d185910e3b7bac5b988504b5ba57ff715854ce6e3162aa643827af00d41cb24b876c35f271b2e3dadc9035ecea52a9bd915508c43ac0c1b15ab45e182f95d623695412811599c0d99d9; s_v_web_id=verify_m34irgxy_at0AfdxM_ABda_4Vid_A8Yu_EhoA6YSz4hTn; hevc_supported=true; csrf_session_id=d2db9ca83bfb13dd86139c8f2fce886d; SelfTabRedDotControl=%5B%7B%22id%22%3A%227173497603785492518%22%2C%22u%22%3A48%2C%22c%22%3A0%7D%2C%7B%22id%22%3A%227068855797047887879%22%2C%22u%22%3A148%2C%22c%22%3A0%7D%5D; fpk1=U2FsdGVkX182+uaGbj88Jld73uxONWhx/bOVPqIIhKZq61j2o6lVr5oqX0sLnvOgOn2vaLOUR8WcI2/+w0IHwA==; fpk2=16453d6e2683b8800ded2a27c7f595d9; store-region=cn-fj; store-region-src=uid; UIFID=60b2ef133e5e740633c50bb923c1ddfcacd13dfeee1bbba287269d01840b457bc4cfbe8bc33d2fa3312f40b153e0a2ea208cbcbef7744fb1a18e9d30b313f419fe993b66f9e97ba03a059ae4d365973a39b3fb1ee5bcbde4cf6c9557ad08bb39a890a2395cdf7728b81db2785fe61e29a9784fc2101048d3ff74f622c7adf3d048e976130b5b428da05d5f764524727f90c9ecdab8013b04208a3473c94ba491a4792a7ffc9ce6d2172880a3dd825971423693afa5b7e3cbe381e8229a1437e1; douyin.com; device_web_cpu_core=12; device_web_memory_size=8; architecture=amd64; xg_device_score=7.496591075245761; passport_fe_beating_status=true; SEARCH_RESULT_LIST_TYPE=%22single%22; x-web-secsdk-uid=f8663c41-5fc6-4b58-a2fc-2328fd26e80e; __live_version__=%221.1.2.4961%22; webcast_local_quality=null; live_use_vvc=%22false%22; webcast_leading_last_show_time=1731165458474; webcast_leading_total_show_times=1; dy_swidth=1920; dy_sheight=1080; is_dash_user=1; publish_badge_show_info=%221%2C0%2C0%2C1732361930465%22; volume_info=%7B%22isUserMute%22%3Atrue%2C%22isMute%22%3Atrue%2C%22volume%22%3A1%7D; XIGUA_PARAMS_INFO=%7B%7D; my_rd=2; pwa2=%220%7C0%7C3%7C0%22; WallpaperGuide=%7B%22showTime%22%3A0%2C%22closeTime%22%3A0%2C%22showCount%22%3A0%2C%22cursor1%22%3A22%2C%22cursor2%22%3A6%7D; __ac_signature=_02B4Z6wo00f01vXT7awAAIDCwvcp859Mm2L18-kAANo-8a; strategyABtestKey=%221732627767.147%22; biz_trace_id=9bb2ebda; __ac_nonce=06745d6f6009845a720b; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A1920%2C%5C%22screen_height%5C%22%3A1080%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A12%2C%5C%22device_memory%5C%22%3A8%2C%5C%22downlink%5C%22%3A10%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A50%7D%22; FOLLOW_LIVE_POINT_INFO=%22MS4wLjABAAAAV1KffaypXMNVJqOFtGBUKZ2ARDFTBz40zPRjQuSXx04%2F1732636800000%2F0%2F0%2F1732630995063%22; FOLLOW_NUMBER_YELLOW_POINT_INFO=%22MS4wLjABAAAAV1KffaypXMNVJqOFtGBUKZ2ARDFTBz40zPRjQuSXx04%2F1732636800000%2F0%2F1732630395063%2F0%22; home_can_add_dy_2_desktop=%221%22; bd_ticket_guard_client_data=eyJiZC10aWNrZXQtZ3VhcmQtdmVyc2lvbiI6MiwiYmQtdGlja2V0LWd1YXJkLWl0ZXJhdGlvbi12ZXJzaW9uIjoxLCJiZC10aWNrZXQtZ3VhcmQtcmVlLXB1YmxpYy1rZXkiOiJCTmxva3dDVmFQRlowZU1UbWVvOWplVXFib1ZMeWxBTm40RVZoTm5PQlJaTlUwakRyTXArbGt4Qk5jMUpzcFpHN2pwSXBuYlFPcVhLZEErOXJ2SVo2aU09IiwiYmQtdGlja2V0LWd1YXJkLXdlYi12ZXJzaW9uIjoyfQ%3D%3D; IsDouyinActive=false; odin_tt=23e69b2a2b9c1cbb28f441251cbaed54cf22eab61160aabd4dce30f2df816c037c3bb5b6f66c8322e056c5bccd6e9bff',
    'referer': 'https://www.douyin.com/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}

# 快手相关的headers
kuaishou_headers = {
    'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    'Origin': 'https://www.kuaishou.com',
    'Referer': 'https://www.kuaishou.com/profile/3xi3vdjhpahu2yq',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"'
}

# 快手cookies
kuaishou_cookies = {
    'kpf': 'PC_WEB',
    'kpn': 'KUAISHOU_VISION',
    'clientid': '3',
    'did': 'web_a02289317f0d01d3f126ec2a98086990',
    'userId': '2544353729',
    'kuaishou.server.web_st': 'ChZrdWFpc2hvdS5zZXJ2ZXIud2ViLnN0EqABxBzJMGW0lUKBBj75r_aE2fCTg3zNQFCQ6PxkJtqF3OYLSRGCz_ZDijXdnR8eoMrMCOGK43Y2b5uMWVTEVK9UxHPY87iGi-VzG1n5pW4_h3rqfzxHPuPdGNUbvXWdzzWvjk0nGvkSdWG86b6pzqx1o6ZR4kPZOLLcO19MBk70b53GDmF5TqHdCqPqSICdprvcaRsYxqSAUf_0pSbsXWkDTiWZhbE2QKUU_-lA6hoSUPVpLrQxjvUEjnVA3RA_4Mn7IigtDpKDDQPqwwR3WRtBFVdNmhS6OfRDJ3UZP8m7DpJrlZ7LdiigBTAB',
    'kuaishou.server.web_ph': 'aa9ddb59eca74bc1e0b49634ae2cdf7a2ca1',
    'clientid': '3',
    'didv': '1687075909133',
    'client_key': '3c2cd3f3',
    '_did': 'web_436059559EC29725',
    'userId': '1148758508',
    '__security_server_data_status': '1',
    'userId': '1148758508',
    'needInterest': 'false',
    'kuaishoulite.json': '{"ip":"60.251.227.235","userId":"1148758508","region":"cn-dl-ec","lastUserId":"1148758508"}',
    'from_page': 'search',
    'ktrace-context': '1|MS43NjQ1ODM2OTgyODY2OTgyLjQxNDg4MjQ2LjE3MzQzNzYxNjYwODYuMTg0MDg0MDA=|MS43NjQ1ODM2OTgyODY2OTgyLjM1MzgzNzE4LjE3MzQzNzYxNjYwODYuMTg0MDg0MDE=|0|graphql-server|webservice|false|NA==',
    'extId': 'd63c3e5b9c5da09ab0d27f9e71cccb76',
    'GCID': '6e23f90-f38a7fd-5e6bda0-e46f3d9',
    'GCESS': 'BQYEqVx4Y30EBN1zP3gLAQEAAdAIAAD5AgALBAAAAAAAC18DAAQGACAFBACUBAEABQ..',
    'e1': 'www.google.com',
    'e2': 'https%3A%2F%2Fwww.google.com%2F',
    'WEBLOGGER_HTTP_SEQ_ID': '0',
    'WEBLOGGER_ID': 'a8b48830-51a6-450a-9300-0a9c4ad44c7b',
    'passHostname': 'www.kuaishou.com',
    'passUrl': 'https://www.kuaishou.com/new-reco'
}

def download_video(video_info):
    """下载单个视频和封面图片的函数"""
    max_retries = 3  # 最大重试次数
    retry_delay = 2  # 重试延迟（秒）
    
    try:
        # 获取用户昵称作为文件夹名
        nickname = video_info.get('author', {}).get('nickname', 'unknown')
        nickname = clean_filename(nickname)
        
        video_url = video_info.get('video', {}).get('play_addr', {}).get('url_list', [None])[0]
        if not video_url:
            return None

        title = video_info.get('desc', '')
        clean_title = clean_filename(title)

        # 创建视频和图片的文件夹
        video_dir = os.path.join('videos', nickname)
        image_dir = os.path.join('videos', f'{nickname}_jpg')
        os.makedirs(video_dir, exist_ok=True)
        os.makedirs(image_dir, exist_ok=True)

        # 视频输出路径
        video_path = os.path.join(video_dir, f'{clean_title}.mp4')
        if os.path.exists(video_path):
            video_path = os.path.join(video_dir, f'{clean_title}_{video_info.get("aweme_id")}.mp4')

        # 获取文件大小，带重试机制
        file_size = 0
        for retry in range(max_retries):
            try:
                response = requests.head(video_url, headers=headers, timeout=10)
                file_size = int(response.headers.get('content-length', 0))
                break
            except Exception as e:
                if retry == max_retries - 1:
                    raise Exception(f"获取文件大小失败: {str(e)}")
                sleep(retry_delay)
                continue
        
        # 如果文件大小为0，使用普通下载方式，带重试机制
        if file_size == 0:
            for retry in range(max_retries):
                try:
                    response = requests.get(video_url, headers=headers, stream=True, timeout=30)
                    response.raise_for_status()
                    with open(video_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=1024*1024):  # 1MB的块大小
                            if chunk:
                                f.write(chunk)
                    break
                except Exception as e:
                    if retry == max_retries - 1:
                        raise Exception(f"下载视频失败: {str(e)}")
                    sleep(retry_delay)
                    continue
        else:
            # 使用4MB大小进行分块下载
            chunk_size = 4 * 1024 * 1024  # 4MB的块大小
            ranges = [(i, min(i + chunk_size - 1, file_size - 1)) 
                     for i in range(0, file_size, chunk_size)]
            
            # 创建临时文件
            temp_files = []
            download_success = False
            
            for retry in range(max_retries):
                try:
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = []
                        for i, (start, end) in enumerate(ranges):
                            temp_path = f"{video_path}.part{i}"
                            temp_files.append(temp_path)
                            futures.append(
                                executor.submit(
                                    download_chunk, video_url, temp_path, start, end, headers
                                )
                            )
                        
                        # 等待所有分块下载完成
                        for future in futures:
                            future.result()
                    
                    # 合并文件
                    with open(video_path, 'wb') as outfile:
                        for temp_file in temp_files:
                            if os.path.exists(temp_file):
                                with open(temp_file, 'rb') as infile:
                                    outfile.write(infile.read())
                                os.remove(temp_file)  # 删除临时文件
                    
                    download_success = True
                    break
                except Exception as e:
                    # 清理临时文件
                    for temp_file in temp_files:
                        if os.path.exists(temp_file):
                            try:
                                os.remove(temp_file)
                            except:
                                pass
                    
                    if retry == max_retries - 1:
                        raise Exception(f"分块下载失败: {str(e)}")
                    sleep(retry_delay)
                    continue
            
            if not download_success:
                raise Exception("所有重试都失败了")

        # 下载封面图片
        cover_url = video_info.get('video', {}).get('raw_cover', {}).get('url_list', [None])[0]
        if cover_url:
            image_path = os.path.join(image_dir, f'{clean_title}.jpg')
            if os.path.exists(image_path):
                image_path = os.path.join(image_dir, f'{clean_title}_{video_info.get("aweme_id")}.jpg')
            
            # 下载封面图片，带重试机制
            for retry in range(max_retries):
                try:
                    img_response = requests.get(cover_url, headers=headers, timeout=10)
                    img_response.raise_for_status()
                    with open(image_path, 'wb') as f:
                        f.write(img_response.content)
                    return f"视频和封面已保存:\n视频: {nickname}/{clean_title}\n封面: {nickname}_jpg/{os.path.basename(image_path)}"
                except Exception as e:
                    if retry == max_retries - 1:
                        return f"视频已保存，但封面下载失败: {nickname}/{clean_title}\n错误: {str(e)}"
                    sleep(retry_delay)
                    continue
                    
        return f"视频已保存: {nickname}/{clean_title}"
    except Exception as e:
        # 确保清理所有临时文件
        try:
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        except:
            pass
        return f"下载失败 - {nickname}/{clean_title}: {str(e)}"

def download_chunk(url, temp_path, start, end, headers):
    """下载文件的一个分块"""
    chunk_headers = headers.copy()
    chunk_headers['Range'] = f'bytes={start}-{end}'
    
    try:
        response = requests.get(url, headers=chunk_headers, stream=True)
        response.raise_for_status()
        
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=64 * 1024):  # 64KB的块大小
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e

def clean_filename(filename):
    """清理文件名，移除非法字符"""
    illegal_chars = r'[\\/:*?"<>|\n#]'
    clean_name = re.sub(illegal_chars, '', filename)
    keywords = ['dou', '抖音', '抖', 'DOU+']
    for keyword in keywords:
        clean_name = clean_name.replace(keyword, '')
    clean_name = clean_name.strip()[:50]
    return clean_name or 'video'

def clean_user_id(url):
    """从URL中提取用户ID"""
    try:
        # 查找 user/ 和 ? 之间的内容
        if 'user/' in url and '?' in url:
            user_id = url[url.find('user/') + 5:url.find('?')]
            return user_id
        # 如果没有 ? 但有 user/
        elif 'user/' in url:
            user_id = url[url.find('user/') + 5:]
            return user_id
        # 如果输入的就是纯ID
        return url.strip()
    except:
        return url.strip()

def clean_kuaishou_user_id(url):
    """从快手URL中提取用户ID"""
    try:
        # 查找 profile/ 和 ? 之间的内容
        if 'profile/' in url and '?' in url:
            user_id = url[url.find('profile/') + 8:url.find('?')]
            return user_id
        # 如果没有 ? 但有 profile/
        elif 'profile/' in url:
            user_id = url[url.find('profile/') + 8:]
            return user_id
        # 如果输入的就是纯ID
        return url.strip()
    except:
        return url.strip()

def download_kuaishou_video(video_info):
    """下载单个快手视频和封面图片的函数"""
    try:
        # 获取用户昵称作为文件夹名
        nickname = video_info.get('author', {}).get('name', 'unknown')
        nickname = clean_filename(nickname)
        
        # 获取视频信息
        photo_info = video_info.get('photo', {})
        if not photo_info:
            return None

        # 获取视频标题
        title = photo_info.get('caption', '')
        clean_title = clean_filename(title)
        if not clean_title:
            clean_title = f"无标题_{photo_info.get('id', '')}"

        # 创建视频和图片的文件夹
        video_dir = os.path.join('videos', nickname)
        image_dir = os.path.join('videos', f'{nickname}_jpg')
        os.makedirs(video_dir, exist_ok=True)
        os.makedirs(image_dir, exist_ok=True)

        # 视频输出路径
        video_path = os.path.join(video_dir, f'{clean_title}.mp4')
        if os.path.exists(video_path):
            video_path = os.path.join(video_dir, f'{clean_title}_{photo_info.get("id")}.mp4')

        # 获取视频URL
        video_url = photo_info.get('photoUrl')
        if not video_url:
            return f"无法获取视频URL: {nickname}/{clean_title}"

        # 获取文件大小
        max_retries = 3
        retries = 0
        file_size = 0
        
        while retries < max_retries:
            try:
                response = requests.head(video_url, headers=kuaishou_headers, cookies=kuaishou_cookies, timeout=10)
                if response.status_code == 200:
                    file_size = int(response.headers.get('content-length', 0))
                    break
                else:
                    retries += 1
                    sleep(2)
            except Exception as e:
                retries += 1
                if retries >= max_retries:
                    return f"获取视频文件大小失败: {str(e)}"
                sleep(2)
        
        # 如果文件大小为0或小于1KB，使用普通下载方式
        if file_size < 1024:  # 小于1KB可能是无效文件
            retries = 0
            while retries < max_retries:
                try:
                    response = requests.get(video_url, headers=kuaishou_headers, cookies=kuaishou_cookies, stream=True, timeout=30)
                    if response.status_code == 200:
                        with open(video_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=4*1024*1024):  # 4MB的块大小
                                if chunk:
                                    f.write(chunk)
                        break
                    else:
                        retries += 1
                        sleep(2)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        return f"下载视频文件失败: {str(e)}"
                    sleep(2)
        else:
            # 使用4MB大小进行分块下载
            chunk_size = 4 * 1024 * 1024  # 4MB的块大小
            ranges = [(i, min(i + chunk_size - 1, file_size - 1)) 
                     for i in range(0, file_size, chunk_size)]
            
            # 创建临时文件
            temp_files = []
            download_success = False
            
            for retry in range(max_retries):
                try:
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = []
                        for i, (start, end) in enumerate(ranges):
                            temp_path = f"{video_path}.part{i}"
                            temp_files.append(temp_path)
                            futures.append(
                                executor.submit(
                                    download_chunk_with_cookies, 
                                    video_url, 
                                    temp_path, 
                                    start, 
                                    end, 
                                    kuaishou_headers,
                                    kuaishou_cookies
                                )
                            )
                        
                        # 等待所有分块下载完成
                        for future in futures:
                            future.result()
                    
                    # 合并文件
                    with open(video_path, 'wb') as outfile:
                        for temp_file in temp_files:
                            if os.path.exists(temp_file):
                                with open(temp_file, 'rb') as infile:
                                    outfile.write(infile.read())
                                os.remove(temp_file)  # 删除临时文件
                    
                    download_success = True
                    break
                except Exception as e:
                    # 清理临时文件
                    for temp_file in temp_files:
                        if os.path.exists(temp_file):
                            try:
                                os.remove(temp_file)
                            except:
                                pass
                    
                    if retry == max_retries - 1:
                        return f"分块下载失败: {str(e)}"
                    sleep(2)
                    continue
            
            if not download_success:
                return f"所有重试都失败了: {nickname}/{clean_title}"

        # 下载封面图片
        cover_url = photo_info.get('coverUrl')
        if cover_url:
            image_path = os.path.join(image_dir, f'{clean_title}.jpg')
            if os.path.exists(image_path):
                image_path = os.path.join(image_dir, f'{clean_title}_{photo_info.get("id")}.jpg')
            
            retries = 0
            while retries < max_retries:
                try:
                    img_response = requests.get(cover_url, headers=kuaishou_headers, cookies=kuaishou_cookies, timeout=15)
                    if img_response.status_code == 200:
                        with open(image_path, 'wb') as f:
                            f.write(img_response.content)
                        return f"视频和封面已保存:\n视频: {nickname}/{clean_title}\n封面: {nickname}_jpg/{os.path.basename(image_path)}"
                    else:
                        retries += 1
                        sleep(2)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        return f"视频已保存，但封面下载失败: {nickname}/{clean_title}\n错误: {str(e)}"
                    sleep(2)
                    
        return f"视频已保存: {nickname}/{clean_title}"
    except Exception as e:
        # 确保清理所有临时文件
        try:
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        except:
            pass
        return f"下载失败 - {clean_filename(video_info.get('author', {}).get('name', 'unknown'))}/{clean_title if 'clean_title' in locals() else '未知标题'}: {str(e)}"

def download_chunk_with_cookies(url, temp_path, start, end, headers, cookies):
    """下载文件的一个分块（带cookies）"""
    chunk_headers = headers.copy()
    chunk_headers['Range'] = f'bytes={start}-{end}'
    
    try:
        response = requests.get(url, headers=chunk_headers, cookies=cookies, stream=True)
        response.raise_for_status()
        
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=64 * 1024):  # 64KB的块大小
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e

class DownloadThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    
    def __init__(self, url, parent=None, browser_instance=None):
        super().__init__(parent)
        self.url = url
        self.is_running = True
        self.browser_instance = browser_instance
    
    def stop(self):
        self.is_running = False
    
    def run(self):
        dp = None
        try:
            # 使用已有的浏览器实例或创建新的
            if self.browser_instance:
                dp = self.browser_instance
                self.progress_signal.emit('使用已存在的浏览器实例')
                
                # 重新设置监听
                dp.listen.stop() if dp.listen.listening else None
                dp.listen.start('/web/aweme/post')
                
                # 导航到新页面
                self.progress_signal.emit(f'正在打开抖音用户页面: https://www.douyin.com/user/{self.url}')
                dp.get(f'https://www.douyin.com/user/{self.url}')
            else:
                # 如果没有提供浏览器实例，则创建新的
                from DrissionPage import ChromiumOptions
                import random
                
                # 随机化调试端口，避免端口冲突
                debug_port = random.randint(9222, 9999)
                
                # 创建并配置浏览器选项
                options = ChromiumOptions()
                
                # 设置用户数据目录，这样可以保存登录状态
                user_data_dir = os.path.join(os.path.expanduser('~'), '.douyin_browser_data')
                os.makedirs(user_data_dir, exist_ok=True)
                
                # 配置浏览器选项
                options.set_paths(
                    local_port=debug_port,
                    user_data_dir=user_data_dir  # 添加用户数据目录配置
                )
                
                options.set_argument('--no-sandbox')
                options.set_argument('--disable-dev-shm-usage')
                options.set_argument('--disable-gpu')
                options.set_argument('--disable-features=TranslateUI')
                options.set_argument('--disable-extensions')
                options.set_argument('--disable-popup-blocking')
                options.set_argument('--blink-settings=imagesEnabled=true')
                options.set_argument(f'--remote-debugging-port={debug_port}')
                
                self.progress_signal.emit(f'正在启动浏览器(端口:{debug_port})...')
                
                # 创建浏览器实例
                dp = ChromiumPage(options)
                self.progress_signal.emit('浏览器启动成功')
                
                dp.listen.start('/web/aweme/post')
                self.progress_signal.emit(f'正在打开抖音用户页面: https://www.douyin.com/user/{self.url}')
                dp.get(f'https://www.douyin.com/user/{self.url}')

            total_downloaded = 0
            no_response_count = 0
            current_page = 1
            
            self.progress_signal.emit('等待页面加载完成...')
            sleep(5)  # 增加等待时间，确保页面完全加载
            
            # 获取页面URL和标题，确认我们在正确的页面上
            page_url = dp.url
            page_title = dp.title
            self.progress_signal.emit(f"当前页面: {page_title}")
            self.progress_signal.emit(f"页面URL: {page_url}")
            
            with ThreadPoolExecutor(max_workers=20) as executor:
                while self.is_running:
                    try:
                        self.progress_signal.emit(f'正在滚动第 {current_page} 页...')
                        
                        # 尝试多种可能的滚动容器查找方式
                        scroll_container = None
                        
                        # 直接使用JavaScript滚动方法 - 更强大的版本
                        self.progress_signal.emit("使用高级JavaScript滚动方法...")
                        scroll_success = False
                        
                        try:
                            # 方法1: 尝试通用的滚动方法
                            dp.run_js("""
                                function smoothScroll() {
                                    // 滚动到页面底部
                                    window.scrollTo({
                                        top: document.body.scrollHeight,
                                        behavior: 'smooth'
                                    });
                                    
                                    // 尝试滚动所有可能的容器
                                    var containers = document.querySelectorAll('div.scroll-container, div.main-content, main, [class*="scroll"], [class*="container"]');
                                    for(var i=0; i<containers.length; i++) {
                                        try {
                                            containers[i].scrollTo({
                                                top: containers[i].scrollHeight,
                                                behavior: 'smooth'
                                            });
                                        } catch(e) {}
                                    }
                                    
                                    // 尝试查找并点击"加载更多"按钮
                                    var loadMoreBtns = document.querySelectorAll('button, a, div, span');
                                    for(var i=0; i<loadMoreBtns.length; i++) {
                                        var text = loadMoreBtns[i].innerText || '';
                                        if(text.includes('更多') || text.includes('加载') || text.includes('展开')) {
                                            loadMoreBtns[i].click();
                                            return "找到并点击了加载更多按钮";
                                        }
                                    }
                                    
                                    return "完成滚动";
                                }
                                return smoothScroll();
                            """)
                            self.progress_signal.emit("JavaScript滚动完成")
                            scroll_success = True
                            sleep(2)  # 等待内容加载
                        except Exception as e:
                            self.progress_signal.emit(f"高级JavaScript滚动失败: {str(e)}")
                        
                        # 如果JavaScript方法失败，尝试传统方法
                        if not scroll_success:
                            # 如果找到了滚动容器，就滚动
                            if scroll_container:
                                try:
                                    self.progress_signal.emit(f"开始滚动...")
                                    for _ in range(3):  # 尝试多次小幅滚动
                                        scroll_container.scroll.to_bottom(200)  # 每次滚动200像素
                                        sleep(0.5)
                                    self.progress_signal.emit(f"滚动完成")
                                    sleep(2)
                                except Exception as e:
                                    self.progress_signal.emit(f"滚动操作失败: {str(e)}")
                            else:
                                # 如果所有方法都找不到容器，使用页面级别的滚动
                                self.progress_signal.emit(f"未找到专用滚动容器，尝试页面级滚动")
                                try:
                                    for _ in range(5):  # 尝试多次小幅滚动
                                        dp.scroll.down(300)  # 每次向下滚动300像素
                                        sleep(0.5)
                                    sleep(2)
                                except Exception as e:
                                    self.progress_signal.emit(f"页面级滚动失败: {str(e)}")
                        
                        # 等待新内容加载
                        self.progress_signal.emit(f"等待接收视频数据...")
                        resp_videos = dp.listen.wait(timeout=5)
                        if not resp_videos:
                            no_response_count += 1
                            self.progress_signal.emit(f"未获取到新视频，正在重试... ({no_response_count}/5)")
                            
                            if no_response_count >= 5:
                                self.progress_signal.emit(f"连续5次未获取到新视频，采集完成！\n共采集 {current_page-1} 页内容")
                                # 直接跳出循环，确保可以正确处理下一个URL
                                break
                            
                            # 在重试之前先再滚动一下页面，使用更强力的方法
                            try:
                                self.progress_signal.emit("重试前使用强力滚动方法...")
                                dp.run_js("""
                                    // 强制滚动到页面底部
                                    window.scrollTo(0, document.body.scrollHeight);
                                    
                                    // 模拟鼠标滚轮事件
                                    var scrollEvent = new WheelEvent('wheel', {
                                        'view': window,
                                        'bubbles': true,
                                        'cancelable': true,
                                        'deltaY': 1000
                                    });
                                    document.dispatchEvent(scrollEvent);
                                    
                                    // 强制点击所有可能的加载更多按钮
                                    var buttons = document.querySelectorAll('button, a, div[role="button"]');
                                    var clicked = false;
                                    for(var i=0; i<buttons.length; i++) {
                                        var text = buttons[i].innerText || '';
                                        if(text.includes('更多') || text.includes('加载') || text.includes('展开')) {
                                            buttons[i].click();
                                            clicked = true;
                                        }
                                    }
                                    
                                    return "强力滚动完成" + (clicked ? "，并点击了加载按钮" : "");
                                """)
                                sleep(3)
                            except:
                                pass
                                
                            continue
                        
                        no_response_count = 0
                        
                        # 检查响应数据
                        try:
                            info_json = resp_videos.response.body
                            if not info_json:
                                self.progress_signal.emit("响应体为空")
                                continue
                                
                            if 'aweme_list' not in info_json:
                                self.progress_signal.emit(f"响应数据中没有 aweme_list，数据结构: {list(info_json.keys())}")
                                continue
                                
                            video_list = info_json['aweme_list']
                            if not video_list:
                                self.progress_signal.emit("视频列表为空")
                                continue
                                
                            self.progress_signal.emit(f"成功获取到 {len(video_list)} 条视频数据")
                        except Exception as e:
                            self.progress_signal.emit(f"解析响应数据失败: {str(e)}")
                            continue

                        self.progress_signal.emit(f'正在下载第 {current_page} 页的视频...')
                        
                        futures = []
                        for video_info in video_list:
                            future = executor.submit(download_video, video_info)
                            futures.append(future)
                            
                        for future in futures:
                            result = future.result()
                            if result:
                                total_downloaded += 1
                                self.progress_signal.emit(f'第 {current_page} 页 - 已下载 {total_downloaded} 个视频\n{result}')

                        current_page += 1

                    except Exception as e:
                        self.progress_signal.emit(f'第 {current_page} 页处理出错: {str(e)}')
                        import traceback
                        self.progress_signal.emit(f"详细错误: {traceback.format_exc()}")
                        continue
            
            self.finished_signal.emit()
            self.progress_signal.emit(f"下载完成！\n共采集 {current_page-1} 页，下载 {total_downloaded} 个视频")
            
        except Exception as e:
            self.progress_signal.emit(f'发生严重错误: {str(e)}')
            import traceback
            self.progress_signal.emit(f"详细错误: {traceback.format_exc()}")
            # 确保出错时也发送完成信号
            self.finished_signal.emit()
        finally:
            # 如果是自己创建的浏览器实例（而非共享的），才关闭它
            if dp is not None and dp != self.browser_instance:
                try:
                    self.progress_signal.emit("正在关闭临时浏览器...")
                    dp.quit()
                    sleep(2)  # 等待浏览器完全关闭
                    self.progress_signal.emit("临时浏览器已关闭")
                except Exception as e:
                    self.progress_signal.emit(f"关闭浏览器时出错: {str(e)}")
                    pass

class KuaishouDownloadThread(QThread):
    """快手视频下载线程"""
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    
    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self.is_running = True
    
    def stop(self):
        self.is_running = False
    
    def get_video_list(self, user_id, pcursor=""):
        """获取快手视频列表"""
        # 更新Referer
        kuaishou_headers['Referer'] = f'https://www.kuaishou.com/profile/{user_id}'
        
        # 新的API请求参数
        json_data = {
            'operationName': 'visionProfilePhotoList',
            'variables': {
                'userId': user_id,
                'pcursor': pcursor if pcursor else "",
                'page': 'profile',
                'webPageArea': 'profile',
            },
            'query': 'fragment photoContent on PhotoEntity {\n  id\n  duration\n  caption\n  originCaption\n  likeCount\n  viewCount\n  commentCount\n  realLikeCount\n  coverUrl\n  photoUrl\n  photoH265Url\n  manifest\n  manifestH265\n  videoResource\n  coverUrls {\n    url\n    __typename\n  }\n  timestamp\n  expTag\n  animatedCoverUrl\n  distance\n  videoRatio\n  liked\n  stereoType\n  profileUserTopPhoto\n  musicBlocked\n  __typename\n}\n\nfragment feedContent on Feed {\n  type\n  author {\n    id\n    name\n    headerUrl\n    following\n    headerUrls {\n      url\n      __typename\n    }\n    __typename\n  }\n  photo {\n    ...photoContent\n    __typename\n  }\n  canAddComment\n  llsid\n  status\n  currentPcursor\n  tags {\n    type\n    name\n    __typename\n  }\n  __typename\n}\n\nquery visionProfilePhotoList($pcursor: String, $userId: String, $page: String, $webPageArea: String) {\n  visionProfilePhotoList(pcursor: $pcursor, userId: $userId, page: $page, webPageArea: $webPageArea) {\n    result\n    llsid\n    webPageArea\n    feeds {\n      ...feedContent\n      __typename\n    }\n    hostName\n    pcursor\n    __typename\n  }\n}'
        }
        
        try:
            # 增加超时和重试
            session = requests.Session()
            retries = 3
            retry_delay = 2
            
            for attempt in range(retries):
                try:
                    response = session.post(
                        'https://www.kuaishou.com/graphql',
                        cookies=kuaishou_cookies,
                        headers=kuaishou_headers,
                        json=json_data,
                        timeout=(10, 20)  # 连接超时10秒，读取超时20秒
                    )
                    response.raise_for_status()
                    return response.json()
                except requests.exceptions.RequestException as e:
                    if attempt < retries - 1:
                        self.progress_signal.emit(f"请求失败: {str(e)}，等待{retry_delay}秒后重试...")
                        sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                        continue
                    else:
                        raise e
        except requests.exceptions.Timeout:
            self.progress_signal.emit("请求超时，正在重试...")
            return None
        except Exception as e:
            self.progress_signal.emit(f"获取视频列表失败: {str(e)}")
            return None
    
    def run(self):
        try:
            total_downloaded = 0
            current_page = 1
            pcursor = ""  # 初始页面的pcursor为空字符串
            retry_count = 0  # 添加重试计数器
            api_error_count = 0  # API错误计数器
            
            # 记录开始时间
            import time
            start_time = time.time()
            self.progress_signal.emit(f"开始处理快手链接: {self.url}")
            
            with ThreadPoolExecutor(max_workers=20) as executor:
                while self.is_running:
                    try:
                        self.progress_signal.emit(f'正在获取第 {current_page} 页视频列表...')
                        
                        # 获取视频列表
                        response_data = self.get_video_list(self.url, pcursor)
                        if not response_data:
                            retry_count += 1
                            if retry_count >= 5:  # 增加到5次重试
                                self.progress_signal.emit("获取视频列表失败，已达到最大重试次数")
                                break
                            sleep(3)  # 增加到3秒等待时间
                            self.progress_signal.emit(f"第{retry_count}次重试中...")
                            continue
                            
                        retry_count = 0  # 重置重试计数器
                        
                        # 从返回数据中获取视频列表
                        profile_photo_list = response_data.get('data', {}).get('visionProfilePhotoList', {})
                        
                        # 检查API返回的错误信息
                        if not profile_photo_list:
                            # 检查是否有错误信息
                            if 'result' in response_data and response_data.get('result') != 1:
                                api_error_count += 1
                                error_msg = response_data.get('error_msg', '未知错误')
                                request_id = response_data.get('request_id', '无ID')
                                self.progress_signal.emit(f"API返回错误: 结果码={response_data.get('result')}, 错误={error_msg}, 请求ID={request_id}")
                                
                                if api_error_count >= 3:
                                    self.progress_signal.emit("API持续返回错误，可能是账号限制或网络问题，暂停下载")
                                    # 但这里不退出循环，尝试更换pcursor继续获取
                                else:
                                    # 尝试延长等待时间并继续
                                    self.progress_signal.emit(f"等待5秒后尝试继续...")
                                    sleep(5)
                                    continue
                            
                            self.progress_signal.emit(f"获取不到视频列表数据: {response_data}")
                            if total_downloaded > 0:
                                self.progress_signal.emit("似乎已经获取完所有可用视频，结束下载")
                                break
                            else:
                                # 如果一个视频都没下载到，等待更久再重试
                                sleep(5)
                                continue
                            
                        video_list = profile_photo_list.get('feeds', [])
                        if not video_list:
                            self.progress_signal.emit("当前页没有视频")
                            # 如果到这一步还没获取到视频，但之前已经下载了视频，可能是到达了末尾
                            if total_downloaded > 0:
                                break
                            else:
                                # 如果一个视频都没下载，增加重试次数
                                retry_count += 1
                                sleep(3)
                                continue
                            
                        # 获取下一页的cursor
                        next_pcursor = profile_photo_list.get('pcursor')
                        
                        # 检查是否还有下一页
                        if not next_pcursor or next_pcursor == "no_more" or next_pcursor == pcursor:
                            self.progress_signal.emit("已到达最后一页")
                            break

                        self.progress_signal.emit(f'正在下载第 {current_page} 页的视频...')
                        
                        # 下载当前页的视频
                        futures = []
                        for video_info in video_list:
                            if not self.is_running:  # 检查是否需要停止
                                break
                            future = executor.submit(download_kuaishou_video, video_info)
                            futures.append(future)
                            
                        for future in futures:
                            if not self.is_running:  # 检查是否需要停止
                                break
                            result = future.result()
                            if result:
                                total_downloaded += 1
                                self.progress_signal.emit(f'第 {current_page} 页 - 已下载 {total_downloaded} 个视频\n{result}')

                        if not self.is_running:  # 检查是否需要停止
                            break

                        # 更新pcursor，准备获取下一页
                        pcursor = next_pcursor
                        current_page += 1
                        
                        # 重置API错误计数器，因为已成功获取数据
                        api_error_count = 0
                        
                        # 添加适当的延迟，避免请求过快
                        sleep(2)  # 增加延迟到2秒

                    except Exception as e:
                        self.progress_signal.emit(f'第 {current_page} 页处理出错: {str(e)}')
                        retry_count += 1
                        if retry_count >= 5:  # 增加到5次重试
                            self.progress_signal.emit("处理出错，已达到最大重试次数")
                            break
                        sleep(3)  # 增加到3秒等待
                        continue
            
            # 计算总耗时
            end_time = time.time()
            total_time = int(end_time - start_time)
            self.progress_signal.emit(f"链接处理完成，总耗时: {total_time}秒")
            
            self.finished_signal.emit()
            self.progress_signal.emit(f"下载完成！\n共采集 {current_page-1} 页，下载 {total_downloaded} 个视频")
            
        except Exception as e:
            self.progress_signal.emit(f'发生严重错误: {str(e)}')
            import traceback
            self.progress_signal.emit(f"详细错误: {traceback.format_exc()}")
            # 确保异常情况下也发送完成信号
            self.finished_signal.emit()

class ConfigDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Chrome配置')
        self.setFixedWidth(500)
        
        layout = QVBoxLayout()
        
        # Chrome路径输入
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText('请输入Chrome浏览器路径，例如: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe')
        browse_btn = QPushButton('浏览')
        browse_btn.clicked.connect(self.browse_chrome)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(browse_btn)
        
        # 按钮
        btn_layout = QHBoxLayout()
        save_btn = QPushButton('保存')
        save_btn.clicked.connect(self.save_config)
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        
        # 添加到主布局
        layout.addLayout(path_layout)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
        # 尝试加载现有配置
        self.load_existing_config()
        
    def browse_chrome(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择Chrome浏览器",
            "",
            "Chrome浏览器 (chrome.exe)"
        )
        if file_path:
            self.path_input.setText(file_path)
    
    def load_existing_config(self):
        try:
            config_path = os.path.join(os.path.expanduser('~'), '.DrissionPage', 'config.json')
            if os.path.exists(config_path):
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    chrome_path = config.get('browser_path', '')
                    if chrome_path:
                        self.path_input.setText(chrome_path)
        except:
            pass
    
    def save_config(self):
        chrome_path = self.path_input.text().strip()
        if not chrome_path:
            QMessageBox.warning(self, '警告', '请输入Chrome浏览器路径！')
            return
            
        if not os.path.exists(chrome_path):
            QMessageBox.warning(self, '警告', '指定的Chrome浏览器路径不存在！')
            return
            
        try:
            from DrissionPage import ChromiumOptions
            co = ChromiumOptions()
            co.set_browser_path(chrome_path)
            co.save()
            QMessageBox.information(self, '成功', 'Chrome配置已保存！')
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, '错误', f'保存配置失败：{str(e)}')

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('视频下载器')
        self.setGeometry(100, 100, 800, 600)
        self.download_thread = None
        # 添加URL队列
        self.url_queue = []
        self.current_url_index = 0
        # 共享的浏览器实例
        self.browser_instance = None

        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 创建URL输入框，改为文本框支持多行输入
        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText('请输入抖音/快手用户URL或ID，每行一个链接')
        self.url_input.setMinimumHeight(100)
        layout.addWidget(self.url_input)

        # 创建平台选择按钮组
        platform_layout = QHBoxLayout()
        self.douyin_radio = QPushButton('抖音')
        self.kuaishou_radio = QPushButton('快手')
        self.douyin_radio.setCheckable(True)
        self.kuaishou_radio.setCheckable(True)
        self.douyin_radio.setChecked(True)  # 默认选中抖音
        platform_layout.addWidget(self.douyin_radio)
        platform_layout.addWidget(self.kuaishou_radio)
        
        # 添加测试连接按钮
        self.test_connection_btn = QPushButton('测试连接')
        self.test_connection_btn.clicked.connect(self.test_platform_connection)
        platform_layout.addWidget(self.test_connection_btn)
        
        # 连接按钮点击事件
        self.douyin_radio.clicked.connect(lambda: self.select_platform('douyin'))
        self.kuaishou_radio.clicked.connect(lambda: self.select_platform('kuaishou'))
        
        layout.addLayout(platform_layout)

        # 创建按钮布局
        button_layout = QVBoxLayout()
        
        # 创建开始下载按钮
        self.start_btn = QPushButton('开始下载')
        self.start_btn.clicked.connect(self.start_download)
        button_layout.addWidget(self.start_btn)
        
        # 创建停止按钮
        self.stop_btn = QPushButton('停止下载')
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)
        
        # 添加配置按钮
        config_btn = QPushButton('配置Chrome')
        config_btn.clicked.connect(self.show_config)
        button_layout.addWidget(config_btn)
        
        layout.addLayout(button_layout)

        # 创建日志显示区域
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)

        # 初始化提示
        self.log_area.append('准备就绪\n下载的视频将保存在 videos 文件夹中\n可输入多个链接，每行一个，下载完成一个会自动下载下一个')
        
        # 当前选择的平台
        self.current_platform = 'douyin'
        
    def test_platform_connection(self):
        """测试当前选择平台的连接是否正常"""
        if self.current_platform == 'douyin':
            self.test_douyin_connection()
        else:
            self.test_kuaishou_connection()
    
    def test_douyin_connection(self):
        """测试抖音连接"""
        self.log_area.append('正在测试抖音连接...')
        try:
            # 初始化浏览器
            if self.browser_instance is None:
                self.init_browser()
                if self.browser_instance is None:
                    self.log_area.append('浏览器初始化失败，无法测试连接')
                    return
            
            # 尝试访问抖音首页
            self.browser_instance.get('https://www.douyin.com/')
            self.log_area.append(f'抖音连接测试成功! 页面标题: {self.browser_instance.title}')
        except Exception as e:
            self.log_area.append(f'抖音连接测试失败: {str(e)}')
    
    def test_kuaishou_connection(self):
        """测试快手连接并更新cookie"""
        self.log_area.append('正在测试快手连接...')
        try:
            # 使用简单的API请求测试
            test_url = 'https://www.kuaishou.com/graphql'
            test_headers = kuaishou_headers.copy()
            test_json = {
                'operationName': 'publicFeedsQuery',
                'variables': {
                    'pcursor': '',
                    'page': 'home'
                },
                'query': 'query publicFeedsQuery($pcursor: String, $page: String) {\n  publicFeeds(pcursor: $pcursor, page: $page) {\n    pcursor\n    hostName\n    __typename\n  }\n}'
            }
            
            response = requests.post(
                test_url,
                headers=test_headers,
                cookies=kuaishou_cookies,
                json=test_json,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'data' in result and 'publicFeeds' in result['data']:
                    self.log_area.append('快手API连接测试成功!')
                else:
                    self.log_area.append(f'快手API返回了非预期的数据结构: {result}')
                    self.log_area.append('请考虑使用新的cookie或升级程序')
            else:
                self.log_area.append(f'快手API连接测试失败，状态码: {response.status_code}')
                self.log_area.append('请考虑使用新的cookie或升级程序')
        except Exception as e:
            self.log_area.append(f'快手连接测试失败: {str(e)}')
            self.log_area.append('请考虑使用新的cookie或升级程序')

    def init_browser(self):
        """初始化浏览器实例"""
        if self.browser_instance is not None:
            return
            
        try:
            # 直接创建浏览器实例，不使用任何特殊配置
            self.browser_instance = ChromiumPage()
            self.log_area.append('浏览器启动成功')
        except Exception as e:
            self.log_area.append(f'浏览器初始化失败: {str(e)}')
            import traceback
            self.log_area.append(f"详细错误: {traceback.format_exc()}")
            self.browser_instance = None

    def select_platform(self, platform):
        """选择平台"""
        self.current_platform = platform
        if platform == 'douyin':
            self.douyin_radio.setChecked(True)
            self.kuaishou_radio.setChecked(False)
            self.url_input.setPlaceholderText('请输入抖音用户URL或ID，每行一个链接')
        else:
            self.douyin_radio.setChecked(False)
            self.kuaishou_radio.setChecked(True)
            self.url_input.setPlaceholderText('请输入快手用户URL或ID，每行一个链接')

    def start_download(self):
        # 获取所有URL，按行分割
        urls_text = self.url_input.toPlainText().strip()
        if not urls_text:
            self.log_area.append('请输入有效的URL或ID')
            return
            
        # 分割多行URL，并过滤掉空行
        self.url_queue = [url.strip() for url in urls_text.split('\n') if url.strip()]
        if not self.url_queue:
            self.log_area.append('请输入有效的URL或ID')
            return
        
        # 只有抖音平台才需要初始化浏览器
        if self.current_platform == 'douyin':
            # 初始化浏览器（如果还没有）
            self.init_browser()
            if self.browser_instance is None:
                self.log_area.append('浏览器初始化失败，无法开始下载')
                return
            
        self.current_url_index = 0
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log_area.clear()
        self.log_area.append(f'开始批量下载，共有 {len(self.url_queue)} 个URL需要下载')
        
        # 开始下载第一个URL
        self.download_next_url()

    def download_next_url(self):
        """下载队列中的下一个URL"""
        # 确保 URL 队列不为空
        if not self.url_queue:
            self.log_area.append('URL队列为空，无法继续下载！')
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            return
            
        if self.current_url_index >= len(self.url_queue):
            # 所有URL已下载完成
            self.log_area.append('所有URL下载完成!')
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            return
            
        current_url = self.url_queue[self.current_url_index]
        self.log_area.append(f'\n开始下载第 {self.current_url_index + 1}/{len(self.url_queue)} 个URL: {current_url}')
        
        # 根据不同平台处理URL，提取用户ID
        if self.current_platform == 'douyin':
            user_id = clean_user_id(current_url)
            self.download_thread = DownloadThread(user_id, self, self.browser_instance)
            self.log_area.append(f'开始下载抖音用户 {user_id} 的视频...\n程序会自动滚动页面\n超过5秒没有新视频就会自动完成')
        else:
            user_id = clean_kuaishou_user_id(current_url)
            self.download_thread = KuaishouDownloadThread(user_id, self)
            self.log_area.append(f'开始下载快手用户 {user_id} 的视频...\n通过API直接获取，不会打开浏览器')
        
        self.download_thread.progress_signal.connect(self.update_log)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.start()

    def stop_download(self, clear_queue=True):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
            self.log_area.append('正在停止下载...')
            self.stop_btn.setEnabled(False)
            # 仅在指定参数为 True 时清空 URL 队列
            if clear_queue:
                self.url_queue = []

    def update_log(self, message):
        self.log_area.append(message)
        # 滚动到底部
        self.log_area.verticalScrollBar().setValue(
            self.log_area.verticalScrollBar().maximum()
        )
        
        # 检测特定消息，可能表示下载中断
        if "连续5次未获取到新视频，采集完成" in message:
            # 只停止当前线程，不清空队列
            if self.download_thread and self.download_thread.isRunning():
                self.stop_download(clear_queue=False)

    def download_finished(self):
        # 确保当前线程已完全结束
        if self.download_thread and self.download_thread.isRunning():
            try:
                self.download_thread.wait(1000)  # 等待最多1秒让线程结束
            except:
                pass
        
        # 将线程设为None，帮助垃圾回收
        self.download_thread = None
        
        # 短暂延迟
        sleep(1)
        
        self.current_url_index += 1
        if self.current_url_index < len(self.url_queue):
            # 还有URL待下载，继续下载下一个
            self.log_area.append(f'链接 {self.current_url_index}/{len(self.url_queue)} 处理完成')
            self.log_area.append(f'准备切换到下一个链接: {self.url_queue[self.current_url_index]}')
            self.log_area.append(f'开始处理链接 {self.current_url_index+1}/{len(self.url_queue)}...')
            self.download_next_url()
        else:
            # 所有URL已下载完成
            self.log_area.append('所有URL下载完成!')
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def closeEvent(self, event):
        # 如果下载线程正在运行，先停止它
        if self.download_thread and self.download_thread.isRunning():
            self.log_area.append("应用程序正在关闭，停止所有下载任务...")
            self.download_thread.stop()
            # 等待线程结束，最多等待3秒
            if not self.download_thread.wait(3000):
                self.log_area.append("下载线程未能在预期时间内终止，强制退出")
            
            # 强制清理一些资源
            self.download_thread = None
        
        # 关闭浏览器
        if self.browser_instance:
            try:
                self.log_area.append("正在关闭浏览器...")
                self.browser_instance.quit()
            except:
                pass
            self.browser_instance = None
            
        # 清空URL队列
        self.url_queue = []
        
        # 接受关闭事件
        event.accept()

    def show_config(self):
        dialog = ConfigDialog()
        dialog.exec_()

def get_chrome_path():
    try:
        # 首先尝试使用便携版Chrome
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        portable_chrome = os.path.join(base_path, 'browser', 'chrome.exe')
        
        if os.path.exists(portable_chrome):
            return portable_chrome
            
        # 如果便携版不存在，尝试系统安装的Chrome
        system_paths = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            os.path.expanduser('~') + r'\AppData\Local\Google\Chrome\Application\chrome.exe'
        ]
        
        for path in system_paths:
            if os.path.exists(path):
                return path
                
        raise Exception("未找到Chrome浏览器")
    except Exception as e:
        print(f"获取Chrome路径出错: {e}")
        raise

def execute_dp_config():
    """执行 dp.py 配置"""
    try:
        if getattr(sys, 'frozen', False):
            # 打包后的路径
            dp_path = os.path.join(sys._MEIPASS, 'dp.py')
        else:
            # 开发时的路径
            dp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dp.py')
            
        print(f"正在执行配置文件: {dp_path}")
        
        if os.path.exists(dp_path):
            with open(dp_path, 'r', encoding='utf-8') as f:
                exec(f.read())
            print("配置文件执行成功")
            return True
        else:
            print(f"找不到配置文件: {dp_path}")
            return False
    except Exception as e:
        print(f"执行配置文件失败: {e}")
        return False

def main():
    # 先创建QApplication
    app = QApplication(sys.argv)
    
    # 显示验证窗口
    verification_dialog = KeyVerificationDialog()
    verification_dialog.show()
    
    # 等待验证窗口关闭
    if not verification_dialog.exec_():
        return 0  # 如果用户关闭验证窗口，则退出程序
    # 检查程序是否在有效期内
    from datetime import datetime
    current_date = datetime.now()
    expiry_date = datetime(2025, 6, 3)
    
    if current_date > expiry_date:
        QMessageBox.critical(None, '错误', '程序已过期,请联系管理员更新!')
        return 0
    try:
        # 创建并显示主窗口
        window = MainWindow()
        window.show()
        return app.exec_()
    except Exception as e:
        # 显示错误对话框
        QMessageBox.critical(None, '错误', f'程序启动失败：{str(e)}')
        return 1

if __name__ == '__main__':
    main() 