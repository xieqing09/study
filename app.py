#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音图片爬虫 - Web界面服务
基于Flask的可视化界面，支持网址输入和文件上传
"""

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Dict, Any

from flask import Flask, render_template, request, jsonify, Response
from werkzeug.utils import secure_filename

# 导入现有的爬虫模块
from douyin_image_crawler import DouyinImageCrawler
from linkrush import extract_links_from_file

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# 全局变量
crawl_status = {
    'running': False,
    'progress': 0,
    'status': '准备开始...',
    'results': None,
    'error': None
}

# 消息队列用于实时通信
message_queue = Queue()
crawl_thread = None

class CrawlProgressHandler:
    """爬虫进度处理器"""
    
    def __init__(self):
        self.total_images = 0
        self.processed_images = 0
        self.downloaded_images = 0
        self.failed_images = 0
        
    def update_total(self, total: int):
        """更新总图片数"""
        self.total_images = total
        self._send_progress()
        
    def update_processed(self, processed: int, downloaded: int, failed: int):
        """更新处理进度"""
        self.processed_images = processed
        self.downloaded_images = downloaded
        self.failed_images = failed
        self._send_progress()
        
    def send_log(self, message: str):
        """发送日志消息"""
        message_queue.put({
            'type': 'log',
            'message': message
        })
        
    def _send_progress(self):
        """发送进度更新"""
        if self.total_images > 0:
            progress = int((self.processed_images / self.total_images) * 100)
        else:
            progress = 0
            
        status = f"已处理 {self.processed_images}/{self.total_images} 张图片 (成功: {self.downloaded_images}, 失败: {self.failed_images})"
        
        message_queue.put({
            'type': 'progress',
            'progress': progress,
            'status': status
        })

# 创建上传目录
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/start_crawl', methods=['POST'])
def start_crawl():
    """开始爬取"""
    global crawl_thread, crawl_status
    
    if crawl_status['running']:
        return jsonify({'success': False, 'error': '爬取正在进行中'})
    
    try:
        # 获取参数
        crawl_type = request.form.get('crawl_type')
        save_dir = request.form.get('save_dir', 'douyin_images')
        max_images = int(request.form.get('max_images', 50))
        use_selenium = request.form.get('use_selenium') == 'true'
        save_metadata = request.form.get('save_metadata') == 'true'
        
        # 处理保存路径 - 支持绝对路径和相对路径
        save_dir = save_dir.strip()
        if not save_dir:
            save_dir = 'douyin_images'
        
        # 基本路径安全检查
        if '..' in save_dir or save_dir.startswith('/') and os.name == 'nt':
            return jsonify({'success': False, 'error': '路径包含不安全字符'})
        
        # 转换为Path对象以便处理
        try:
            save_path = Path(save_dir)
        except Exception as e:
            return jsonify({'success': False, 'error': f'路径格式无效: {str(e)}'})
        
        # 如果是相对路径，则相对于当前工作目录
        if not save_path.is_absolute():
            save_path = Path.cwd() / save_path
        
        # 确保目录存在
        try:
            save_path.mkdir(parents=True, exist_ok=True)
            save_dir = str(save_path.resolve())  # 获取绝对路径
        except PermissionError:
            return jsonify({'success': False, 'error': '没有权限创建该目录，请检查路径权限'})
        except Exception as e:
            return jsonify({'success': False, 'error': f'无法创建保存目录: {str(e)}'})
        
        print(f"保存路径设置为: {save_dir}")
        
        # 根据爬取类型获取URL列表
        urls = []
        
        if crawl_type == 'url':
            url = request.form.get('url')
            if not url:
                return jsonify({'success': False, 'error': '请提供有效的URL'})
            
            # 清理URL输入，去除多余的空白字符和引号
            original_url = url
            url = url.strip().strip('\'"`')
            
            # 如果URL包含多行或多个URL，只取第一个
            if '\n' in url:
                url = url.split('\n')[0].strip()
            
            print(f"网址爬取 - 原始URL: {repr(original_url)}")
            print(f"网址爬取 - 清理后URL: {repr(url)}")
            
            urls = [url]
            
        elif crawl_type == 'file':
            file = request.files.get('file')
            if not file or file.filename == '':
                return jsonify({'success': False, 'error': '请选择文件'})
            
            # 保存上传的文件
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # 从文件中提取链接
            try:
                urls = extract_links_from_file(file_path)
                print(f"文档爬取 - 从文件提取的URLs: {urls}")
                if not urls:
                    return jsonify({'success': False, 'error': '文件中未找到有效的链接'})
            except Exception as e:
                return jsonify({'success': False, 'error': f'解析文件失败: {str(e)}'})
        else:
            return jsonify({'success': False, 'error': '无效的爬取类型'})
        
        # 重置状态
        crawl_status.update({
            'running': True,
            'progress': 0,
            'status': '准备开始...',
            'results': None,
            'error': None
        })
        
        # 清空消息队列
        while not message_queue.empty():
            message_queue.get()
        
        # 启动爬取线程
        crawl_thread = threading.Thread(
            target=run_crawl_task,
            args=(urls, save_dir, max_images, use_selenium, save_metadata)
        )
        crawl_thread.daemon = True
        crawl_thread.start()
        
        return jsonify({'success': True, 'message': '爬取任务已启动'})
        
    except Exception as e:
        crawl_status['running'] = False
        return jsonify({'success': False, 'error': f'启动失败: {str(e)}'})

@app.route('/stop_crawl', methods=['POST'])
def stop_crawl():
    """停止爬取"""
    global crawl_status
    
    crawl_status['running'] = False
    message_queue.put({
        'type': 'log',
        'message': '收到停止信号，正在停止爬取...'
    })
    
    return jsonify({'success': True, 'message': '停止信号已发送'})

@app.route('/progress')
def progress():
    """SSE进度推送"""
    def generate():
        while True:
            try:
                # 获取消息
                if not message_queue.empty():
                    message = message_queue.get_nowait()
                    yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
                
                # 检查是否完成
                if not crawl_status['running'] and crawl_status.get('results'):
                    yield f"data: {json.dumps({'type': 'complete', 'results': crawl_status['results']}, ensure_ascii=False)}\n\n"
                    break
                elif not crawl_status['running'] and crawl_status.get('error'):
                    yield f"data: {json.dumps({'type': 'error', 'message': crawl_status['error']}, ensure_ascii=False)}\n\n"
                    break
                
                time.sleep(0.5)  # 避免过于频繁的检查
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
                break
    
    return Response(generate(), mimetype='text/event-stream')

def run_crawl_task(urls, save_dir, max_images, use_selenium, save_metadata):
    """运行爬取任务"""
    global crawl_status
    
    progress_handler = CrawlProgressHandler()
    
    try:
        progress_handler.send_log(f"开始爬取任务，共 {len(urls)} 个URL")
        progress_handler.send_log(f"保存目录: {save_dir}")
        progress_handler.send_log(f"最大图片数: {max_images}")
        progress_handler.send_log(f"使用Selenium: {use_selenium}")
        
        # 创建爬虫实例
        crawler = DouyinImageCrawler(download_dir=save_dir)
        
        total_results = {
            'total_images': 0,
            'downloaded_images': 0,
            'failed_downloads': 0,
            'processed_urls': 0,
            'method_used': 'selenium' if use_selenium else 'crawl4ai',
            'save_path': str(Path(save_dir).absolute()),
            'url_results': []
        }
        
        # 处理每个URL
        for i, url in enumerate(urls):
            if not crawl_status['running']:
                progress_handler.send_log("爬取已被用户停止")
                break
                
            progress_handler.send_log(f"正在处理第 {i+1}/{len(urls)} 个URL: {url}")
            
            try:
                # 运行异步爬取
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                result = loop.run_until_complete(
                    crawler.crawl_douyin_user_images(
                        user_url=url,
                        max_images=max_images,
                        save_metadata=save_metadata,
                        use_selenium=use_selenium
                    )
                )
                
                loop.close()
                
                # 更新总结果
                total_results['total_images'] += result.get('total_images', 0)
                total_results['downloaded_images'] += result.get('downloaded_images', 0)
                total_results['failed_downloads'] += result.get('failed_downloads', 0)
                total_results['processed_urls'] += 1
                total_results['url_results'].append({
                    'url': url,
                    'result': result
                })
                
                progress_handler.send_log(
                    f"URL {i+1} 完成: 下载 {result.get('downloaded_images', 0)} 张图片"
                )
                
                # 更新进度
                progress_handler.update_processed(
                    i + 1,
                    total_results['downloaded_images'],
                    total_results['failed_downloads']
                )
                
            except Exception as e:
                error_msg = f"处理URL {url} 时出错: {str(e)}"
                progress_handler.send_log(error_msg)
                total_results['url_results'].append({
                    'url': url,
                    'error': str(e)
                })
        
        # 完成
        crawl_status['results'] = total_results
        crawl_status['running'] = False
        
        progress_handler.send_log("爬取任务完成！")
        progress_handler.send_log(f"总计下载 {total_results['downloaded_images']} 张图片")
        
    except Exception as e:
        error_msg = f"爬取任务失败: {str(e)}"
        progress_handler.send_log(error_msg)
        crawl_status['error'] = error_msg
        crawl_status['running'] = False

@app.route('/status')
def get_status():
    """获取当前状态"""
    return jsonify(crawl_status)

if __name__ == '__main__':
    print("=" * 60)
    print("🎉 抖音图片爬虫 - Web界面服务")
    print("=" * 60)
    print("📱 访问地址: http://localhost:5000")
    print("🔧 功能特性:")
    print("   • 支持单个URL爬取")
    print("   • 支持批量文件爬取")
    print("   • 实时进度显示")
    print("   • Selenium模式支持")
    print("   • 自定义保存目录")
    print("=" * 60)
    print("⚠️  注意事项:")
    print("   • 请遵守抖音平台使用条款")
    print("   • 建议适度使用，避免频繁请求")
    print("   • 确保网络连接稳定")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)