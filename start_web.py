#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音图片爬虫 - Web服务启动脚本
"""

import os
import sys
import webbrowser
import time
import threading

def open_browser():
    """延迟打开浏览器"""
    time.sleep(2)  # 等待服务器启动
    webbrowser.open('http://localhost:5000')

def main():
    """主函数"""
    print("=" * 60)
    print("🚀 启动抖音图片爬虫 Web 服务")
    print("=" * 60)
    
    # 检查必要文件
    required_files = ['app.py', 'douyin_image_crawler.py', 'linkrush.py']
    missing_files = []
    
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("❌ 缺少必要文件:")
        for file in missing_files:
            print(f"   • {file}")
        print("\n请确保所有文件都在当前目录中。")
        input("按回车键退出...")
        return
    
    # 检查templates目录
    if not os.path.exists('templates'):
        print("❌ 缺少 templates 目录")
        print("请确保 templates/index.html 文件存在。")
        input("按回车键退出...")
        return
    
    if not os.path.exists('templates/index.html'):
        print("❌ 缺少 templates/index.html 文件")
        input("按回车键退出...")
        return
    
    print("✅ 所有必要文件检查完成")
    print("🌐 准备启动Web服务...")
    print("📱 服务地址: http://localhost:5000")
    print("⏰ 正在启动服务器...")
    
    # 启动浏览器线程
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    # 启动Flask应用
    try:
        from app import app
        app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
    except KeyboardInterrupt:
        print("\n\n🛑 服务已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {str(e)}")
        input("按回车键退出...")

if __name__ == '__main__':
    main()